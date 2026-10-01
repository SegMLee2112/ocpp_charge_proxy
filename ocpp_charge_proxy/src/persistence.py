from __future__ import annotations

import json
import logging
import os
import random

logger = logging.getLogger(__name__)

_ENERGY_FILE = "energy_register.json"
_SERIAL_FILE = "serial_number.json"


class Persistence:
    def __init__(self, data_dir: str = "/data"):
        self._data_dir = data_dir

    def _read(self, filename: str, key: str, default):
        path = os.path.join(self._data_dir, filename)
        try:
            with open(path) as f:
                data = json.load(f)
                return data.get(key, default)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return default

    def _write(self, filename: str, key: str, value):
        path = os.path.join(self._data_dir, filename)
        try:
            with open(path, "w") as f:
                json.dump({key: value}, f)
        except OSError:
            logger.warning("Failed to write %s", path)

    def load_energy_register_wh(self) -> int:
        return self._read(_ENERGY_FILE, "energy_wh", 0)

    def save_energy_register_wh(self, value: int) -> None:
        self._write(_ENERGY_FILE, "energy_wh", value)

    def seed_energy_register_wh(self, value: int) -> bool:
        """Set the register to `value` only if that's higher than what's stored.

        A lifetime meter must never go backwards, so a seed value left in the
        add-on options (or entered too low) is ignored. Returns True if applied.
        """
        current = self.load_energy_register_wh()
        if value <= current:
            return False
        self.save_energy_register_wh(value)
        return True

    def load_serial_number(self) -> str:
        serial = self._read(_SERIAL_FILE, "serial", "")
        if not serial:
            serial = str(random.randint(100000, 999999))
            self.save_serial_number(serial)
            logger.info("Generated charger serial number: %s", serial)
        return serial

    def save_serial_number(self, value: str) -> None:
        self._write(_SERIAL_FILE, "serial", value)
