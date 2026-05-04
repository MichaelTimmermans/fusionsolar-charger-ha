"""
Switch platform for FusionSolar App HA.

Charger switch: start / stop charging.
  - start-charge: POST with dnId, gunNumber, accountId
  - stop-charge:  POST with dnId, gunNumber, orderNumber, serialNumber
    (orderNumber and serialNumber come from the coordinator's process data)
"""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ChargerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    charger: ChargerCoordinator = data["charger"]
    user_id: str = data.get("user_id", "")

    async_add_entities([ChargingSwitch(charger, user_id)])


class ChargingSwitch(CoordinatorEntity[ChargerCoordinator], SwitchEntity):
    """
    Switch that starts or stops EV charging.

    ON  → start-charge (requires accountId from user_info)
    OFF → stop-charge  (requires orderNumber + serialNumber from process data)

    The switch state reflects whether charging is currently active,
    based on signal_status from the coordinator.
    """

    _attr_has_entity_name = True
    _attr_name = "Charging"
    _attr_icon = "mdi:ev-station"

    # Statuses that mean charging is active
    _CHARGING_STATUSES = {"Charging", "PV power charging", "Starting charging"}

    def __init__(self, coordinator: ChargerCoordinator, user_id: str) -> None:
        super().__init__(coordinator)
        self._user_id = user_id
        self._attr_unique_id = f"{coordinator.dn_id}_charging_switch"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"charger_{self.coordinator.dn_id}")},
            name=self.coordinator.device_name,
            manufacturer="Huawei",
            model="FusionSolar EV Charger",
        )

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        status = self.coordinator.data.get("signal_status", "")
        return status in self._CHARGING_STATUSES

    @property
    def available(self) -> bool:
        """Available when charger is connected and a vehicle is present."""
        if not super().available or not self.coordinator.data:
            return False
        status = self.coordinator.data.get("signal_status", "")
        # Not available when no car connected or faulted
        return status not in ("No car connected", "Faulted", "Upgrading", "")

    async def async_turn_on(self, **kwargs) -> None:
        """Start charging."""
        _LOGGER.info("Starting charge on charger %s", self.coordinator.dn_id)

        # accountId comes from process data (preferred) or stored user_id
        account_id = (
            self.coordinator.data.get("account_id")
            or self._user_id
        ) if self.coordinator.data else self._user_id

        if not account_id:
            _LOGGER.error(
                "Cannot start charge: no accountId available. "
                "Ensure user_info was fetched at startup."
            )
            return

        success = await self.coordinator.api.start_charge(
            dn_id=self.coordinator.dn_id,
            account_id=account_id,
            gun_number=1,
        )

        if success:
            _LOGGER.info("Charge started successfully")
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to start charge")

    async def async_turn_off(self, **kwargs) -> None:
        """Stop charging."""
        _LOGGER.info("Stopping charge on charger %s", self.coordinator.dn_id)

        data = self.coordinator.data or {}
        order_number  = data.get("order_number", "")
        serial_number = data.get("serial_number", "")

        success = await self.coordinator.api.stop_charge(
            dn_id=self.coordinator.dn_id,
            order_number=order_number,
            serial_number=serial_number,
            gun_number=1,
        )

        if success:
            _LOGGER.info("Charge stopped successfully")
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to stop charge")
