"""Communication with Home Assistant via the Supervisor API."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class HABridge:
    """Minimal bridge — config updates handled by bashio in the s6 run script."""

    def __init__(self, supervisor_token: str):
        self._standalone = not supervisor_token
        if self._standalone:
            logger.info("No SUPERVISOR_TOKEN — HA bridge disabled (standalone mode)")
