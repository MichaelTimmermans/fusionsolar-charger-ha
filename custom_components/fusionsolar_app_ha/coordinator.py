"""
FusionSolar Charger — DataUpdateCoordinator.

Polls the API every SCAN_INTERVAL seconds and makes the data available
to all platform entities (sensor, binary_sensor, etc.).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FusionSolarApi, FusionSolarApiError, FusionSolarAuthError
from .const import (
    DOMAIN,
    REALTIME_SIGNAL_IDS,
    SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class FusionSolarCoordinator(DataUpdateCoordinator):
    """
    Coordinator for a single FusionSolar charger device.

    Fetches:
    - Charger status (charge-status endpoint)
    - Real-time signals (get-realtime-info endpoint)
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: FusionSolarApi,
        dn_id: int,
        device_name: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{dn_id}",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.api = api
        self.dn_id = dn_id
        self.device_name = device_name

    async def _async_update_data(self) -> dict:
        """
        Called by HA every SCAN_INTERVAL seconds.
        Returns a dict consumed by sensor entities.
        """
        try:
            # Fetch charger status
            charger_status = await self.api.get_charger_status(
                dn_id=self.dn_id,
                gun_number=1,
                need_real_time_status=True,
            )

            # Fetch real-time signals (power, current, voltage, energy)
            signals = await self.api.get_realtime_info(
                dn_id=self.dn_id,
                signal_ids=REALTIME_SIGNAL_IDS,
            )

            # Index signals by ID for easy lookup in sensor entities
            signals_by_id = {s.signal_id: s for s in signals}

            return {
                "charger_status": charger_status,
                "signals": signals_by_id,
            }

        except FusionSolarAuthError as exc:
            raise UpdateFailed(f"Authentication error: {exc}") from exc
        except FusionSolarApiError as exc:
            raise UpdateFailed(f"API error: {exc}") from exc
