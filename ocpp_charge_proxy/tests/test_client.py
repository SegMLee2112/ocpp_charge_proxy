import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from ocpp.v16.enums import (
    ChargePointStatus, RegistrationStatus, RemoteStartStopStatus, Action,
)
from ocpp.v16 import call, call_result

from src.client import ChargePoint


@pytest.fixture
def mock_connection():
    conn = AsyncMock()
    conn.send = AsyncMock()
    conn.recv = AsyncMock()
    return conn


@pytest.fixture
def mock_persistence():
    p = MagicMock()
    p.load_energy_register_wh.return_value = 5000
    p.save_energy_register_wh = MagicMock()
    return p


def make_cp(connection, persistence):
    cp = ChargePoint(
        id="CP001",
        connection=connection,
        persistence=persistence,
        current_amps=32,
    )
    return cp


def test_initial_state(mock_connection, mock_persistence):
    cp = make_cp(mock_connection, mock_persistence)
    assert cp.state == ChargePointStatus.available


def test_remote_start_when_available_rejected(mock_connection, mock_persistence):
    """RemoteStart rejected when no car plugged in (Available state)."""
    cp = make_cp(mock_connection, mock_persistence)
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(
        cp.on_remote_start_transaction(id_tag="TAG001", connector_id=1)
    )
    loop.close()
    assert result.status == RemoteStartStopStatus.rejected


def test_remote_start_when_preparing(mock_connection, mock_persistence):
    """RemoteStart accepted when car is plugged in (Preparing state)."""
    cp = make_cp(mock_connection, mock_persistence)
    cp.state = ChargePointStatus.preparing
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(
        cp.on_remote_start_transaction(id_tag="TAG001", connector_id=1)
    )
    loop.close()
    assert result.status == RemoteStartStopStatus.accepted


def test_remote_start_when_already_charging(mock_connection, mock_persistence):
    cp = make_cp(mock_connection, mock_persistence)
    cp.state = ChargePointStatus.charging
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(
        cp.on_remote_start_transaction(id_tag="TAG001", connector_id=1)
    )
    loop.close()
    assert result.status == RemoteStartStopStatus.rejected


def test_remote_stop_mismatched_transaction_id_accepted(mock_connection, mock_persistence):
    """Octopus workaround: RemoteStop with a different tx id still stops the only active tx."""
    cp = make_cp(mock_connection, mock_persistence)
    cp._transaction_id = 1790607644
    cp.state = ChargePointStatus.charging
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(
        cp.on_remote_stop_transaction(transaction_id=1)
    )
    loop.close()
    assert result.status == RemoteStartStopStatus.accepted


def test_remote_stop_no_transaction_rejected(mock_connection, mock_persistence):
    cp = make_cp(mock_connection, mock_persistence)
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(
        cp.on_remote_stop_transaction(transaction_id=1)
    )
    loop.close()
    assert result.status == RemoteStartStopStatus.rejected


def _config_value(cp, key):
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(cp.on_get_configuration(key=[key]))
    loop.close()
    return result.configuration_key[0]["value"]


def test_heartbeat_interval_reported_after_set(mock_connection, mock_persistence):
    """Interval from BootNotification is what GetConfiguration reports."""
    cp = make_cp(mock_connection, mock_persistence)
    assert _config_value(cp, "HeartbeatInterval") == "30"
    cp._set_heartbeat_interval(10)
    assert cp._heartbeat_interval == 10
    assert _config_value(cp, "HeartbeatInterval") == "10"


def test_change_configuration_heartbeat_interval(mock_connection, mock_persistence):
    cp = make_cp(mock_connection, mock_persistence)
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(
        cp.on_change_configuration(key="HeartbeatInterval", value="120")
    )
    loop.close()
    assert result.status == "Accepted"
    assert cp._heartbeat_interval == 120
    assert _config_value(cp, "HeartbeatInterval") == "120"


def test_change_configuration_heartbeat_interval_invalid(mock_connection, mock_persistence):
    cp = make_cp(mock_connection, mock_persistence)
    loop = asyncio.new_event_loop()
    for bad in ("0", "-5", "abc"):
        result = loop.run_until_complete(
            cp.on_change_configuration(key="HeartbeatInterval", value=bad)
        )
        assert result.status == "Rejected"
    loop.close()
    assert cp._heartbeat_interval == 30
    assert _config_value(cp, "HeartbeatInterval") == "30"


def test_heartbeat_loop_picks_up_new_interval(mock_connection, mock_persistence):
    """Changing the interval mid-sleep takes effect without waiting out the old one."""
    cp = make_cp(mock_connection, mock_persistence)
    cp.call = AsyncMock()

    async def scenario():
        task = asyncio.create_task(cp.heartbeat_loop(300))
        await asyncio.sleep(0.05)
        cp._set_heartbeat_interval(0.1)
        await asyncio.sleep(0.35)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(scenario())
    loop.close()
    assert cp.call.await_count >= 2


# --- Clock-aligned meter values ---

import datetime as _dt
from src.client import _next_aligned


def _utc(h, m, sec=0):
    return _dt.datetime(2026, 10, 1, h, m, sec, tzinfo=_dt.timezone.utc)


def test_next_aligned_mid_slot():
    delay, boundary = _next_aligned(_utc(15, 7, 30), 900)
    assert delay == 450
    assert boundary == _utc(15, 15)


def test_next_aligned_exactly_on_boundary_is_full_interval():
    delay, boundary = _next_aligned(_utc(15, 15), 900)
    assert delay == 900
    assert boundary == _utc(15, 30)


def test_next_aligned_rolls_to_midnight():
    delay, boundary = _next_aligned(_utc(23, 50), 900)
    assert delay == 600
    assert boundary == _dt.datetime(2026, 10, 2, tzinfo=_dt.timezone.utc)


def test_next_aligned_uneven_interval_caps_at_midnight():
    # 700s doesn't divide 86400; last slot of the day ends at midnight
    delay, boundary = _next_aligned(_utc(23, 59, 50), 700)
    assert delay == 10
    assert boundary == _dt.datetime(2026, 10, 2, tzinfo=_dt.timezone.utc)


def test_change_configuration_clock_aligned(mock_connection, mock_persistence):
    cp = make_cp(mock_connection, mock_persistence)
    assert _config_value(cp, "ClockAlignedDataInterval") == "0"
    loop = asyncio.new_event_loop()
    r1 = loop.run_until_complete(
        cp.on_change_configuration(key="ClockAlignedDataInterval", value="900"))
    r2 = loop.run_until_complete(cp.on_change_configuration(
        key="MeterValuesAlignedData",
        value="Energy.Active.Import.Register, Power.Active.Import"))
    r3 = loop.run_until_complete(
        cp.on_change_configuration(key="ClockAlignedDataInterval", value="-1"))
    loop.close()
    assert r1.status == "Accepted" and r2.status == "Accepted"
    assert r3.status == "Rejected"
    assert cp._clock_aligned_interval == 900
    assert _config_value(cp, "ClockAlignedDataInterval") == "900"
    assert cp._aligned_measurands == [
        "Energy.Active.Import.Register", "Power.Active.Import",
    ]


def _sent_payload(cp):
    return cp.call.await_args.args[0]


def test_clock_aligned_idle_payload(mock_connection, mock_persistence):
    cp = make_cp(mock_connection, mock_persistence)
    cp.call = AsyncMock()
    cp._aligned_measurands = ["Energy.Active.Import.Register", "Power.Active.Import"]
    loop = asyncio.new_event_loop()
    loop.run_until_complete(cp.send_clock_aligned_meter_values(_utc(15, 15)))
    loop.close()
    payload = _sent_payload(cp)
    assert payload.transaction_id is None
    mv = payload.meter_value[0]
    assert mv["timestamp"] == "2026-10-01T15:15:00Z"
    assert {sv["measurand"]: sv["value"] for sv in mv["sampledValue"]} == {
        "Energy.Active.Import.Register": "5000.0",
        "Power.Active.Import": "0.0",
    }
    assert all(sv["context"] == "Sample.Clock" for sv in mv["sampledValue"])


def test_clock_aligned_charging_includes_transaction(mock_connection, mock_persistence):
    cp = make_cp(mock_connection, mock_persistence)
    cp.call = AsyncMock()
    cp._aligned_measurands = ["Energy.Active.Import.Register", "Power.Active.Import"]
    cp._transaction_id = 1790866844
    cp.state = ChargePointStatus.charging
    cp._charger_sim.start_charging()
    loop = asyncio.new_event_loop()
    loop.run_until_complete(cp.send_clock_aligned_meter_values(_utc(15, 15)))
    loop.close()
    payload = _sent_payload(cp)
    assert payload.transaction_id == 1790866844
    values = {sv["measurand"]: float(sv["value"]) for sv in payload.meter_value[0]["sampledValue"]}
    assert values["Power.Active.Import"] > 0


def test_aligned_and_periodic_share_energy_register(mock_connection, mock_persistence):
    """Two readings over the same span add the same energy as one."""
    cp = make_cp(mock_connection, mock_persistence)
    cp.state = ChargePointStatus.charging
    cp._charger_sim.start_charging()
    cp._power_override = 7.0  # fixed power for a deterministic result
    cp._last_meter_time -= 3600  # one hour ago
    cp._take_reading()
    after_one = cp._energy_register_wh
    cp._take_reading()  # immediately again: ~no extra time elapsed
    assert after_one - 5000 > 0
    assert cp._energy_register_wh - after_one <= 1


# --- Energy accounting at charging state changes ---

from ocpp.v16 import call as _call


def _call_recorder(transaction_id=4242):
    """AsyncMock for cp.call that records requests and answers StartTransaction."""
    sent = []

    async def fake_call(request):
        sent.append(request)
        if isinstance(request, _call.StartTransactionPayload):
            return MagicMock(transaction_id=transaction_id)
        return MagicMock()

    return AsyncMock(side_effect=fake_call), sent


def test_start_transaction_does_not_add_phantom_energy(mock_connection, mock_persistence):
    """Idle time before a start must not be billed at charging power."""
    cp = make_cp(mock_connection, mock_persistence)
    cp.call, sent = _call_recorder()
    cp.state = ChargePointStatus.preparing
    cp._power_override = 5.0
    cp._last_meter_time -= 3600  # last reading was an hour ago, while idle

    loop = asyncio.new_event_loop()
    loop.run_until_complete(cp._do_start_transaction())
    start = [r for r in sent if isinstance(r, _call.StartTransactionPayload)][0]
    assert start.meter_start == 5000
    loop.run_until_complete(cp.send_meter_values())  # immediately after start
    loop.close()

    assert cp.state == ChargePointStatus.charging
    assert cp._energy_register_wh - 5000 <= 1  # previously ~+5000 Wh phantom


def test_stop_transaction_counts_energy_since_last_reading(mock_connection, mock_persistence):
    """meterStop includes energy delivered after the last periodic reading."""
    cp = make_cp(mock_connection, mock_persistence)
    cp.call, sent = _call_recorder()
    cp.state = ChargePointStatus.charging
    cp._charger_sim.start_charging()
    cp._transaction_id = 4242
    cp._transaction_start_energy_wh = 5000
    cp._power_override = 5.0
    cp._last_meter_time -= 1800  # 30 min charging since the last reading

    loop = asyncio.new_event_loop()
    loop.run_until_complete(cp._do_stop_transaction())
    loop.close()

    stop = [r for r in sent if isinstance(r, _call.StopTransactionPayload)][0]
    assert 7400 <= stop.meter_stop <= 7600  # 5000 + 5 kW x 0.5 h = 7500


def test_unlock_connector_captures_energy_before_state_change(mock_connection, mock_persistence):
    cp = make_cp(mock_connection, mock_persistence)
    cp.call, sent = _call_recorder()
    cp.state = ChargePointStatus.charging
    cp._charger_sim.start_charging()
    cp._transaction_id = 4242
    cp._power_override = 5.0
    cp._last_meter_time -= 1800

    async def scenario():
        await cp.on_unlock_connector(connector_id=1)
        await asyncio.sleep(0)  # let the stop task run
        await asyncio.sleep(0)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(scenario())
    loop.close()

    stop = [r for r in sent if isinstance(r, _call.StopTransactionPayload)][0]
    assert 7400 <= stop.meter_stop <= 7600
