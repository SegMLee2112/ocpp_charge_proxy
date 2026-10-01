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
