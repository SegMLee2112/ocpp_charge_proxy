"""Config flow."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ocpp_charge_proxy.const import DOMAIN

from .common import URL

FLOW = "custom_components.ocpp_charge_proxy.config_flow"


async def test_user_flow_creates_entry(hass):
    with patch(f"{FLOW}._candidate_urls", return_value=[URL]), \
         patch(f"{FLOW}._try_connect", return_value=True), \
         patch("custom_components.ocpp_charge_proxy.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER},
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"api_url": URL},
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"api_url": URL}
    assert result["options"] == {}


async def test_user_flow_cannot_connect(hass):
    with patch(f"{FLOW}._candidate_urls", return_value=[URL]), \
         patch(f"{FLOW}._try_connect", return_value=False):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"api_url": URL},
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
