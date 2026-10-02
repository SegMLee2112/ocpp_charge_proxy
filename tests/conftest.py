"""Home Assistant test harness (pytest-homeassistant-custom-component)."""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let HA load custom_components/ocpp_charge_proxy."""
    yield


@pytest.fixture
def expected_lingering_timers() -> bool:
    # The coordinator's poll timer / refresh debouncer can outlive a test by a tick
    return True
