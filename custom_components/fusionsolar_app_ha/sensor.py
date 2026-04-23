"""
Sensor platform for FusionSolar Charger.

Exposes:
  - Charger status (text)
  - Charging power (W)
  - Session energy (kWh)
  - Charging current (A)
  - Charging voltage (V)
  - Total energy delivered (kWh, lifetime)

Signal IDs are from the FusionSolar northbound API for EV chargers (mocType 60080/60081).
Real signal names/IDs discovered from your C# WRITABLE_IDS and config signal lists.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CHARGER_STATUS_MAP, DOMAIN
from .coordinator import FusionSolarCoordinator

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sensor descriptions
# ---------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class FusionSolarSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with FusionSolar-specific fields."""
    signal_id: int | None = None          # None = derived from charger_status
    value_fn: Any = None                  # optional transform


# Signal IDs for EV charger real-time data.
# These IDs come from the FusionSolar homemgr API for charger devices.
# Values confirmed from your C# code signal lists.
SENSOR_DESCRIPTIONS: tuple[FusionSolarSensorDescription, ...] = (
    FusionSolarSensorDescription(
        key="charger_status",
        name="Charger status",
        icon="mdi:ev-station",
        signal_id=None,        # read from charger_status, not signals
    ),
    FusionSolarSensorDescription(
        key="charging_power",
        name="Charging power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:flash",
        signal_id=20006,       # charging power signal
    ),
    FusionSolarSensorDescription(
        key="charging_current",
        name="Charging current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        signal_id=20005,       # charging current signal
    ),
    FusionSolarSensorDescription(
        key="charging_voltage",
        name="Charging voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
        signal_id=20004,       # charging voltage signal
    ),
    FusionSolarSensorDescription(
        key="session_energy",
        name="Session energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:battery-charging",
        signal_id=20010,       # session energy (kWh)
    ),
    FusionSolarSensorDescription(
        key="total_energy",
        name="Total energy delivered",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:counter",
        signal_id=20011,       # lifetime total energy
    ),
    FusionSolarSensorDescription(
        key="max_current",
        name="Max charging current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
        signal_id=20001,       # max current setting
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up FusionSolar Charger sensor entities."""
    coordinator: FusionSolarCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        FusionSolarSensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    )


# ---------------------------------------------------------------------------
# Sensor entity
# ---------------------------------------------------------------------------

class FusionSolarSensor(CoordinatorEntity[FusionSolarCoordinator], SensorEntity):
    """A sensor entity backed by the FusionSolar coordinator."""

    entity_description: FusionSolarSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FusionSolarCoordinator,
        description: FusionSolarSensorDescription,
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
    def native_value(self) -> str | float | int | None:
        """Return the sensor value from coordinator data."""
        data = self.coordinator.data
        if data is None:
            return None

        desc = self.entity_description

        # Charger status comes from the status endpoint, not signal IDs
        if desc.key == "charger_status":
            status = data.get("charger_status")
            if status is None:
                return None
            return status.charge_status_label

        # All other sensors come from real-time signal data
        signal_id = desc.signal_id
        if signal_id is None:
            return None

        signals = data.get("signals", {})
        signal = signals.get(signal_id)
        if signal is None:
            return None

        # Try numeric first (power, current, voltage, energy)
        raw = signal.real_value or signal.value
        if raw:
            try:
                return float(raw)
            except (ValueError, TypeError):
                pass

        # Fall back to enum map lookup
        if signal.enum_map and signal.value in signal.enum_map:
            return signal.enum_map[signal.value]

        return raw or None
