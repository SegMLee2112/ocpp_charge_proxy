"""Config and options flows."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    assert result["options"] == {"power_entity": "", "soc_entity": ""}


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


def _entry(hass, options=None):
    entry = MockConfigEntry(domain=DOMAIN, data={"api_url": URL}, options=options or {})
    entry.add_to_hass(hass)
    return entry


async def test_options_saved(hass):
    entry = _entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "soc_entity": "sensor.car_soc",
        "auto_plug": True,
        "auto_plug_soc": 25,
    })
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        "power_entity": "",
        "soc_entity": "sensor.car_soc",
        "plug_entity": "",
        "auto_plug": True,
        "auto_plug_entity": "",
        "auto_plug_soc": 25,
    }


async def test_options_car_connected_sensor_with_auto_plug(hass):
    """Both can be set: the sensor and auto plug-in each only ever plug in."""
    entry = _entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "plug_entity": "binary_sensor.car_cable",
        "soc_entity": "sensor.car_soc",
        "auto_plug": True,
        "auto_plug_soc": 30,
    })
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["plug_entity"] == "binary_sensor.car_cable"
    assert entry.options["auto_plug"] is True


async def test_options_car_connected_sensor_alone_is_fine(hass):
    entry = _entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "plug_entity": "binary_sensor.car_cable",
        "auto_plug": False,
        "auto_plug_soc": 30,
    })
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["plug_entity"] == "binary_sensor.car_cable"


async def test_options_cleared_sensor_is_unset(hass):
    entry = _entry(hass, {"power_entity": "sensor.power", "soc_entity": "sensor.car_soc"})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "auto_plug": False, "auto_plug_soc": 30,  # both pickers cleared
    })
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["power_entity"] == ""
    assert entry.options["soc_entity"] == ""
