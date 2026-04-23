"""
Binary sensor platform for FusionSolar Charger.

Exposes:
  - Is charging (True when chargeStatus == 2)
  - Is connected (True when a vehicle is plugged in, status 1-5)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FusionSolarCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class FusionSolarBinarySensorDescription(BinarySensorEntityDescription):
    """Extended description with a value function."""
    is_on_fn: Callable[[dict], bool] = lambda _: False


BINARY_SENSOR_DESCRIPTIONS: tuple[FusionSolarBinarySensorDescription, ...] = (
    FusionSolarBinarySensorDescription(
        key="is_charging",
        name="Charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        icon="mdi:ev-station",
        # chargeStatus 2 == "Charging"
        is_on_fn=lambda data: (
            (data.get("charger_status") and data["charger_status"].charge_status == 2)
        ),
    ),
    FusionSolarBinarySensorDescription(
        key="is_connected",
        name="Vehicle connected",
        device_class=BinarySensorDeviceClass.PLUG,
        icon="mdi:car-electric",
        # chargeStatus 1-5 means a vehicle is present (Preparing → Finishing)
        is_on_fn=lambda data: (
            data.get("charger_status") is not None
            and 1 <= data["charger_status"].charge_status <= 5
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up FusionSolar binary sensor entities."""
    coordinator: FusionSolarCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        FusionSolarBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class FusionSolarBinarySensor(
    CoordinatorEntity[FusionSolarCoordinator], BinarySensorEntity
):
    """Binary sensor entity for the FusionSolar charger."""

    entity_description: FusionSolarBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FusionSolarCoordinator,
        description: FusionSolarBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.dn_id}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, str(self.coordinator.dn_id))},
            name=self.coordinator.device_name,
            manufacturer="Huawei",
            model="FusionSolar EV Charger",
        )

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.is_on_fn(self.coordinator.data)
