import pytest
from unittest.mock import AsyncMock
from aiohttp import ClientSession

from src.ha_bridge import HABridge


def test_standalone_mode():
    bridge = HABridge(supervisor_token="")
    assert bridge._standalone is True


def test_ha_mode():
    bridge = HABridge(supervisor_token="test-token")
    assert bridge._standalone is False
