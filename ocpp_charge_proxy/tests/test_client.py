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
