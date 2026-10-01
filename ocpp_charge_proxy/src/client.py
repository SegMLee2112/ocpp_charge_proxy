from __future__ import annotations

import asyncio
import datetime
import logging
import time
from typing import Optional

import websockets
from ocpp.routing import on
from ocpp.v16 import ChargePoint as BaseChargePoint
from ocpp.v16 import call, call_result
from ocpp.v16.enums import (
    Action,
    AvailabilityStatus,
    AvailabilityType,
    ChargePointErrorCode,
    ChargePointStatus,
    ClearCacheStatus,
    ConfigurationStatus,
    DataTransferStatus,
    Reason,
    RegistrationStatus,
    RemoteStartStopStatus,
    ResetStatus,
    ResetType,
    TriggerMessageStatus,
    UnlockStatus,
    UpdateStatus,
)

from src.charger_sim import ChargerReading, ChargerSimulator
from src.charging_profile import ChargingProfileScheduler
from src.meter_values import build_charging_meter_values, build_idle_meter_values
from src.persistence import Persistence
from src.shared_state import SharedState

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ChargePoint(BaseChargePoint):
    def __init__(
        self,
        id: str,
        connection,
        persistence: Persistence,
        current_amps: int = 32,
        shared_state: SharedState | None = None,
    ):
        super().__init__(id, connection)
        self.connector_id = 1
        self.state = ChargePointStatus.available
        self._persistence = persistence
        self._power_override: Optional[float] = None  # kW, set via API
        self._shared_state = shared_state or SharedState()
        self._energy_register_wh: int = persistence.load_energy_register_wh()
        self._transaction_id: Optional[int] = None
        self._transaction_start_energy_wh: int = 0
        self._last_meter_time: float = time.monotonic()
        self._meter_value_interval: int = 60  # default, updated by ChangeConfiguration
        self._server_config: dict[str, str] = {}  # stores config sent by server
        self._local_list_version: int = 0
        self._local_auth_list: dict[str, dict] = {}
        self._config_store: dict[str, tuple[str, bool]] = {
            # key: (value, readonly)
            "MeterValueSampleInterval": ("60", False),
            "HeartbeatInterval": ("30", False),
            "NumberOfConnectors": ("1", True),
            "ChargeProfileMaxStackLevel": ("3", True),
            "ChargingScheduleAllowedChargingRateUnit": ("Current,Power", True),
            "ChargingScheduleMaxPeriods": ("24", True),
            "MaxChargingProfilesInstalled": ("5", True),
            "SupportedFeatureProfiles": (
                "Core,SmartCharging,LocalAuthListManagement,RemoteTrigger", True
            ),
            "AuthorizeRemoteTxRequests": ("true", False),
            "LocalAuthListEnabled": ("true", False),
            "LocalAuthListMaxLength": ("20", True),
            "SendLocalListMaxLength": ("20", True),
            "StopTransactionOnInvalidId": ("false", False),
            "StopTransactionOnEVSideDisconnect": ("true", True),
            "UnlockConnectorOnEVSideDisconnect": ("true", True),
            "WebSocketPingInterval": ("30", True),
            "MeterValuesAlignedData": ("", False),
            "MeterValuesSampledData": (
                "Energy.Active.Import.Register,Power.Active.Import", False
            ),
            "ConnectorPhaseRotation": ("1.RST", True),
            "GetConfigurationMaxKeys": ("50", True),
        }
        self._charger_sim = ChargerSimulator(current_amps=current_amps)
        self._profile_scheduler = ChargingProfileScheduler(
            rated_power_w=self._charger_sim.rated_power_kw * 1000
        )

    @property
    def energy_register_kwh(self) -> float:
        return self._energy_register_wh / 1000.0

    def _zero_power_state(self) -> None:
        """Zero out power-related shared state values."""
        self._shared_state.power_kw = 0.0
        self._shared_state.current_a = 0.0
        self._shared_state.power_offered_kw = 0.0
        self._shared_state.power_source = "simulated"
        self._shared_state.power_entity_value = None

    async def send_boot_notification(
        self, model: str, vendor: str,
        serial_number: str = "", firmware_version: str = "",
    ) -> int:
        request = call.BootNotificationPayload(
            charge_point_model=model,
            charge_point_vendor=vendor,
            charge_point_serial_number=serial_number,
            charge_box_serial_number=serial_number,
            firmware_version=firmware_version,
            meter_type="Internal NON compliant",
            meter_serial_number="",
            iccid="",
            imsi="",
        )

        while True:
            response: call_result.BootNotificationPayload = await self.call(request)

            if response.status == RegistrationStatus.accepted:
                self._shared_state.connected_to_server = True
                await self._send_status_for_connector(0)
                await self.send_status()
                interval = response.interval
                return interval if interval and interval > 0 else 30
            elif response.status == RegistrationStatus.pending:
                wait = response.interval if response.interval and response.interval > 0 else 30
                logger.info("BootNotification pending, retrying in %ds", wait)
                await asyncio.sleep(wait)
            else:
                logger.error("BootNotification rejected")
                raise SystemExit("BootNotification rejected by server")

    async def heartbeat_loop(self, interval: int) -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                await self.call(call.HeartbeatPayload())
            except websockets.exceptions.ConnectionClosed:
                # Socket is gone — exit so the supervisor reconnects instead of
                # leaving a zombie loop spamming a dead connection.
                logger.info("Heartbeat loop stopping: connection closed")
                raise
            except Exception:
                logger.warning("Heartbeat cycle failed", exc_info=True)

    async def meter_values_loop(self) -> None:
        while True:
            await asyncio.sleep(self._meter_value_interval)
            try:
                await self.send_meter_values()
            except websockets.exceptions.ConnectionClosed:
                logger.info("Meter values loop stopping: connection closed")
                raise
            except Exception:
                logger.warning("Meter values cycle failed", exc_info=True)

    async def _send_status_for_connector(self, connector_id: int, status: ChargePointStatus | None = None) -> None:
        """Send StatusNotification for a connector."""
        request = call.StatusNotificationPayload(
            connector_id=connector_id,
            error_code=ChargePointErrorCode.no_error,
            status=status or self.state,
            timestamp=_now_iso(),
            info="",
            vendor_id="",
            vendor_error_code="",
        )
        await self.call(request)

    async def send_status(self) -> None:
        await self._send_status_for_connector(self.connector_id)

    async def send_status_unavailable(self) -> None:
        await self._send_status_for_connector(
            self.connector_id, ChargePointStatus.unavailable,
        )

    async def send_meter_values(self) -> None:
        now = time.monotonic()
        elapsed_hours = (now - self._last_meter_time) / 3600.0
        self._last_meter_time = now

        # Check charging profile to see if we should be charging or paused
        if self._transaction_id is not None and self._profile_scheduler.has_profile:
            limit_kw = self._profile_scheduler.get_current_limit_kw()
            if limit_kw is not None:
                if limit_kw <= 0 and self._charger_sim.is_charging:
                    logger.info("Profile says pause — suspending charge")
                    self._charger_sim.stop_charging()
                    self.state = ChargePointStatus.suspended_evse
                    self._shared_state.state = self.state
                    self._zero_power_state()
                    await self.send_status()
                elif limit_kw > 0 and not self._charger_sim.is_charging:
                    logger.info("Profile says charge at %.1f kW — resuming", limit_kw)
                    self._charger_sim.start_charging()
                    self.state = ChargePointStatus.charging
                    self._shared_state.state = self.state
                    await self.send_status()

        if self.state == ChargePointStatus.charging:
            sim_reading = self._charger_sim.sample()

            # Use power override from integration if available
            real_power = self._power_override
            if real_power is not None:
                # Clamp negatives to 0 (e.g. solar export), cap at charger max
                capped_power = max(0.0, min(real_power, sim_reading.power_kw))
                current_a = round((capped_power * 1000) / sim_reading.voltage, 2) if capped_power > 0 else 0.0
                reading = ChargerReading(
                    power_kw=capped_power,
                    voltage=sim_reading.voltage,
                    current_a=current_a,
                    frequency_hz=sim_reading.frequency_hz,
                    power_offered_kw=sim_reading.power_offered_kw,
                    current_offered_a=sim_reading.current_offered_a,
                )
                self._shared_state.power_source = "entity"
                self._shared_state.power_entity_value = real_power
            else:
                reading = sim_reading
                self._shared_state.power_source = "simulated"
                self._shared_state.power_entity_value = None

            energy_added_kwh = reading.power_kw * elapsed_hours
            self._energy_register_wh += round(energy_added_kwh * 1000)
            self._persistence.save_energy_register_wh(self._energy_register_wh)

            meter_value = build_charging_meter_values(
                reading=reading,
                energy_register_wh=self._energy_register_wh,
            )
            request = call.MeterValuesPayload(
                connector_id=self.connector_id,
                transaction_id=self._transaction_id,
                meter_value=meter_value,
            )

            # Update shared state with charging values
            self._shared_state.power_kw = reading.power_kw
            self._shared_state.voltage = reading.voltage
            self._shared_state.current_a = reading.current_a
            self._shared_state.frequency_hz = reading.frequency_hz
            self._shared_state.power_offered_kw = reading.power_offered_kw
            self._shared_state.energy_kwh = self.energy_register_kwh
        else:
            meter_value = build_idle_meter_values(
                energy_register_wh=self._energy_register_wh,
            )
            request = call.MeterValuesPayload(
                connector_id=self.connector_id,
                meter_value=meter_value,
            )
            self._shared_state.energy_kwh = self.energy_register_kwh
            # Bug 7 fix: zero out power values when idle
            self._zero_power_state()

        await self.call(request)

    async def _do_start_transaction(self) -> None:
        """Start a charging transaction."""
        try:
            # Send OCPP protocol states but don't update shared_state with
            # intermediate values (Bug 1 fix) — the API should only see the
            # final stable state (Charging).
            self.state = ChargePointStatus.available
            await self.send_status()
            await self._send_status_for_connector(0)

            self.state = ChargePointStatus.suspended_ev
            await self.send_status()

            self._charger_sim.start_charging()
            self._transaction_start_energy_wh = self._energy_register_wh
            request = call.StartTransactionPayload(
                connector_id=self.connector_id,
                id_tag="NoAuthorization",
                meter_start=self._energy_register_wh,
                timestamp=_now_iso(),
            )
            response: call_result.StartTransactionPayload = await self.call(request)
            self._transaction_id = response.transaction_id
            logger.info("Transaction started: %s", self._transaction_id)

            # Transition to Charging — now update shared_state atomically
            self.state = ChargePointStatus.charging
            self._shared_state.state = self.state
            self._shared_state.transaction_id = self._transaction_id
            await self.send_status()
        except Exception:
            # Bug 2 fix: reset to consistent state on failure
            logger.error("Failed to start transaction", exc_info=True)
            self._charger_sim.stop_charging()
            self._transaction_id = None
            self.state = ChargePointStatus.preparing
            self._shared_state.state = self.state
            self._shared_state.transaction_id = None
            self._zero_power_state()

    async def _do_stop_transaction(
        self, final_state: ChargePointStatus = ChargePointStatus.preparing,
    ) -> None:
        """Stop the active transaction. final_state controls where we end up."""
        try:
            transaction_id = self._transaction_id
            energy_delivered_kwh = (self._energy_register_wh - self._transaction_start_energy_wh) / 1000.0
            self._charger_sim.stop_charging()
            self._profile_scheduler.clear_profile()

            # Send Finishing status before StopTransaction
            self.state = ChargePointStatus.finishing
            await self.send_status()

            request = call.StopTransactionPayload(
                transaction_id=transaction_id,
                id_tag="ffffffffffffff7f",
                meter_stop=self._energy_register_wh,
                timestamp=_now_iso(),
                reason=Reason.remote,
                transaction_data=[],
            )
            response: call_result.StopTransactionPayload = await self.call(request)
            logger.info("Transaction %s stopped, response: %s", transaction_id, response)
        except Exception:
            logger.error("Failed to stop transaction", exc_info=True)
        finally:
            self._transaction_id = None
            self._shared_state.transaction_id = None
            self._zero_power_state()
            # Bug 3 fix: use caller-specified final state
            self.state = final_state
            self._shared_state.state = self.state

    @on(Action.RemoteStartTransaction)
    async def on_remote_start_transaction(self, id_tag: str, charging_profile: dict = None, **kwargs):
        # Bug 6 fix: only accept when car is plugged in (Preparing)
        if self.state not in (ChargePointStatus.preparing, ChargePointStatus.suspended_ev, ChargePointStatus.suspended_evse):
            logger.warning("RemoteStart rejected: state is %s (not plugged in)", self.state)
            return call_result.RemoteStartTransactionPayload(
                status=RemoteStartStopStatus.rejected
            )

        if charging_profile:
            self._profile_scheduler.set_profile(charging_profile)

        self._shared_state.plugged_in = True
        asyncio.create_task(self._do_start_transaction())
        return call_result.RemoteStartTransactionPayload(
            status=RemoteStartStopStatus.accepted
        )

    @on(Action.RemoteStopTransaction)
    async def on_remote_stop_transaction(self, transaction_id: int, **kwargs):
        if self._transaction_id is None:
            logger.warning("RemoteStop rejected: no active transaction")
            return call_result.RemoteStopTransactionPayload(
                status=RemoteStartStopStatus.rejected
            )
        if transaction_id != self._transaction_id:
            # Workaround: some CSMS backends (seen with Octopus) send a
            # RemoteStop with a transactionId that doesn't match the one they
            # issued in the StartTransaction response (e.g. 1 vs 1790607644).
            # We only have one connector and one active transaction, so the
            # server can only mean that one — accept and stop it, otherwise
            # the car never stops charging.
            logger.warning(
                "RemoteStop transaction_id mismatch (%s != current %s) — "
                "accepting anyway, single active transaction",
                transaction_id, self._transaction_id,
            )
        asyncio.create_task(self._do_stop_transaction())
        return call_result.RemoteStopTransactionPayload(
            status=RemoteStartStopStatus.accepted
        )

    @on(Action.GetConfiguration)
    async def on_get_configuration(self, key: list[str] = None, **kwargs):
        """Return configuration keys. Returns all keys if none specified."""
        configuration_key = []
        unknown_key = []

        keys_to_return = key if key else list(self._config_store.keys())

        for k in keys_to_return:
            if k in self._config_store:
                value, readonly = self._config_store[k]
                configuration_key.append({
                    "key": k,
                    "readonly": readonly,
                    "value": value,
                })
            else:
                unknown_key.append(k)

        return call_result.GetConfigurationPayload(
            configuration_key=configuration_key,
            unknown_key=unknown_key,
        )

    @on(Action.ChangeConfiguration)
    async def on_change_configuration(self, key: str, value: str, **kwargs):
        """Handle configuration changes from the server."""
        logger.info("Server set config: %s = %s", key, value)

        if key in self._config_store:
            _, readonly = self._config_store[key]
            if readonly:
                logger.info("ChangeConfiguration: key %s is read-only", key)
                return call_result.ChangeConfigurationPayload(
                    status=ConfigurationStatus.rejected
                )
            self._config_store[key] = (value, False)

        self._server_config[key] = value
        self._shared_state.server_config = dict(self._server_config)

        if key == "MeterValueSampleInterval":
            try:
                interval = int(value)
                if interval < 1:
                    raise ValueError("interval must be >= 1")
                self._meter_value_interval = interval
                self._shared_state.meter_interval = self._meter_value_interval
                logger.info("Meter value interval updated to %ds", self._meter_value_interval)
            except ValueError:
                logger.warning("Invalid MeterValueSampleInterval: %s, ignoring", value)
        elif key == "chargingALimitConn1":
            amps = int(value)
            try:
                self._charger_sim.current_amps = amps
                self._shared_state.current_amps_setting = amps
            except ValueError:
                logger.warning("Server set unsupported current %dA, ignoring", amps)

        return call_result.ChangeConfigurationPayload(
            status=ConfigurationStatus.accepted
        )

    @on(Action.GetLocalListVersion)
    async def on_get_local_list_version(self, **kwargs):
        """Return the current local authorization list version."""
        return call_result.GetLocalListVersionPayload(
            list_version=self._local_list_version
        )

    @on(Action.SendLocalList)
    async def on_send_local_list(
        self,
        list_version: int,
        update_type: str,
        local_authorization_list: list[dict] = None,
        **kwargs,
    ):
        """Handle local authorization list updates."""
        logger.info(
            "SendLocalList: version=%d type=%s entries=%d",
            list_version, update_type,
            len(local_authorization_list) if local_authorization_list else 0,
        )

        if update_type == "Full":
            self._local_auth_list.clear()

        if local_authorization_list:
            for entry in local_authorization_list:
                id_tag = entry.get("id_tag", entry.get("idTag", ""))
                if id_tag:
                    self._local_auth_list[id_tag] = entry

        self._local_list_version = list_version
        return call_result.SendLocalListPayload(status=UpdateStatus.accepted)

    @on(Action.SetChargingProfile)
    async def on_set_charging_profile(self, connector_id: int, cs_charging_profiles: dict, **kwargs):
        logger.info("SetChargingProfile received for connector %s", connector_id)
        self._profile_scheduler.set_profile(cs_charging_profiles)
        return call_result.SetChargingProfilePayload(
            status="Accepted"
        )

    @on(Action.ClearChargingProfile)
    async def on_clear_charging_profile(self, **kwargs):
        logger.info("ClearChargingProfile received: %s", kwargs)
        self._profile_scheduler.clear_profile(
            profile_id=kwargs.get("id"),
            connector_id=kwargs.get("connector_id"),
            purpose=kwargs.get("charging_profile_purpose"),
            stack_level=kwargs.get("stack_level"),
        )
        return call_result.ClearChargingProfilePayload(
            status="Accepted"
        )

    @on(Action.TriggerMessage)
    async def on_trigger_message(self, requested_message: str, connector_id: int = 0, **kwargs):
        """Handle TriggerMessage: server requests the CP to send a specific message."""
        supported = {
            "BootNotification", "Heartbeat", "MeterValues", "StatusNotification",
        }
        if requested_message not in supported:
            logger.warning("TriggerMessage for unsupported message: %s", requested_message)
            return call_result.TriggerMessagePayload(
                status=TriggerMessageStatus.not_implemented
            )

        logger.info("TriggerMessage accepted: %s", requested_message)
        asyncio.create_task(self._handle_triggered_message(requested_message, connector_id))
        return call_result.TriggerMessagePayload(
            status=TriggerMessageStatus.accepted
        )

    async def _handle_triggered_message(self, message: str, connector_id: int) -> None:
        """Execute the triggered message after returning the response."""
        try:
            if message == "StatusNotification":
                await self._send_status_for_connector(connector_id or self.connector_id)
            elif message == "MeterValues":
                await self.send_meter_values()
            elif message == "Heartbeat":
                await self.call(call.HeartbeatPayload())
            elif message == "BootNotification":
                await self.call(call.BootNotificationPayload(
                    charge_point_model="",
                    charge_point_vendor="",
                ))
        except Exception:
            logger.warning("Failed to send triggered %s", message, exc_info=True)

    @on(Action.ChangeAvailability)
    async def on_change_availability(self, connector_id: int, type: str, **kwargs):
        """Handle ChangeAvailability: server requests connector operative/inoperative."""
        logger.info("ChangeAvailability: connector=%d type=%s", connector_id, type)

        if type == AvailabilityType.inoperative:
            if self._transaction_id is not None:
                logger.info("Transaction active, will change availability after completion")
                return call_result.ChangeAvailabilityPayload(
                    status=AvailabilityStatus.scheduled
                )
            self.state = ChargePointStatus.unavailable
            self._shared_state.state = self.state
            await self.send_status()
        else:
            if self.state == ChargePointStatus.unavailable:
                self.state = ChargePointStatus.available
                self._shared_state.state = self.state
                await self.send_status()

        return call_result.ChangeAvailabilityPayload(
            status=AvailabilityStatus.accepted
        )

    @on(Action.UnlockConnector)
    async def on_unlock_connector(self, connector_id: int, **kwargs):
        """Handle UnlockConnector: server requests to unlock a connector."""
        logger.info("UnlockConnector: connector=%d", connector_id)

        if connector_id != self.connector_id:
            return call_result.UnlockConnectorPayload(
                status=UnlockStatus.not_supported
            )

        if self._transaction_id is not None:
            asyncio.create_task(self._do_stop_transaction(
                final_state=ChargePointStatus.available
            ))

        self._shared_state.plugged_in = False
        self.state = ChargePointStatus.available
        self._shared_state.state = self.state

        return call_result.UnlockConnectorPayload(
            status=UnlockStatus.unlocked
        )

    @on(Action.Reset)
    async def on_reset(self, type: str, **kwargs):
        """Handle Reset: server requests a hard or soft reset."""
        logger.info("Reset requested: type=%s", type)

        if self._transaction_id is not None:
            await self._do_stop_transaction(final_state=ChargePointStatus.available)

        self._profile_scheduler.clear_profile()

        if type == ResetType.hard:
            asyncio.create_task(self._perform_hard_reset())
        else:
            self.state = ChargePointStatus.available
            self._shared_state.state = self.state
            self._shared_state.plugged_in = False
            self._zero_power_state()
            await self.send_status()

        return call_result.ResetPayload(status=ResetStatus.accepted)

    async def _perform_hard_reset(self) -> None:
        """Simulate a hard reset by triggering reconnection."""
        await asyncio.sleep(2)
        raise SystemExit("Hard reset requested by server")

    @on(Action.ClearCache)
    async def on_clear_cache(self, **kwargs):
        """Handle ClearCache: server requests clearing the authorization cache."""
        logger.info("ClearCache requested")
        return call_result.ClearCachePayload(
            status=ClearCacheStatus.accepted
        )

    @on(Action.DataTransfer)
    async def on_data_transfer(
        self, vendor_id: str, message_id: str = "", data: str = "", **kwargs
    ):
        """Handle DataTransfer: vendor-specific messaging."""
        logger.info(
            "DataTransfer: vendor=%s message_id=%s data_len=%d",
            vendor_id, message_id, len(data) if data else 0,
        )
        return call_result.DataTransferPayload(
            status=DataTransferStatus.unknown_vendor_id,
            data="",
        )
