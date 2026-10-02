import os
from unittest.mock import patch

from src.config import Config, load_config


def test_load_config_from_env():
    env = {
        "IO_SERVER_HOSTNAME": "ocpp.example.com",
        "IO_CHARGEPOINT_ID": "CP001",
        "IO_PASSWORD": "secret",
        "IO_CHARGER_MODEL": "PLP2-0-2-2",
        "IO_CHARGER_VENDOR": "Wall Box Chargers",
        "IO_CURRENT_AMPS": "32",
        "IO_LOG_LEVEL": "info",
    }
    with patch.dict(os.environ, env, clear=False):
        cfg = load_config()

    assert cfg.server_hostname == "ocpp.example.com"
    assert cfg.chargepoint_id == "CP001"
    assert cfg.password == "secret"
    assert cfg.current_amps == 32
    assert cfg.log_level == "info"


def test_config_websocket_url():
    cfg = Config(
        server_hostname="ocpp.example.com",
        chargepoint_id="CP001",
        password="secret",
        charger_model="PLP2-0-2-2",
        charger_vendor="Wall Box Chargers",
        charger_serial="",
        firmware_version="6.11.16",
        current_amps=32,
        initial_energy_wh=0,
        log_level="info",
    )
    assert cfg.websocket_url == "wss://CP001:secret@ocpp.example.com/CP001"


def test_config_redacted_url():
    cfg = Config(
        server_hostname="ocpp.example.com",
        chargepoint_id="CP001",
        password="secret",
        charger_model="PLP2-0-2-2",
        charger_vendor="Wall Box Chargers",
        charger_serial="",
        firmware_version="6.11.16",
        current_amps=32,
        initial_energy_wh=0,
        log_level="info",
    )
    assert "secret" not in cfg.redacted_url
    assert "CP001" in cfg.redacted_url


def test_replug_options_from_env():
    env = {
        "IO_SERVER_HOSTNAME": "h", "IO_CHARGEPOINT_ID": "c", "IO_PASSWORD": "p",
        "IO_REPLUG_ENABLED": "false", "IO_REPLUG_AFTER_MIN": "15", "IO_REPLUG_ATTEMPTS": "99",
    }
    with patch.dict(os.environ, env, clear=False):
        cfg = load_config()
    assert cfg.replug_enabled is False and cfg.replug_after_min == 15
    assert cfg.replug_attempts == 20  # clamped
    with patch.dict(os.environ, {**env, "IO_REPLUG_ENABLED": "", "IO_REPLUG_AFTER_MIN": "null"}, clear=False):
        cfg = load_config()
    assert cfg.replug_enabled is True and cfg.replug_after_min == 10
