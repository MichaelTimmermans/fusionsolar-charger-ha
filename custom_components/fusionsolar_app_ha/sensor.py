"""Sensor platform for FusionSolar App HA."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfElectricCurrent, UnitOfElectricPotential,
    UnitOfEnergy, UnitOfPower, UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ChargerCoordinator, StationCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class FusionSensorDescription(SensorEntityDescription):
    data_key: str = ""


CHARGER_SENSORS: tuple[FusionSensorDescription, ...] = (
    # ── Status ────────────────────────────────────────────────────────
    FusionSensorDescription(
        key="signal_status", data_key="signal_status",
        name="Status", icon="mdi:ev-station",
    ),
    # ── Live session (from query-process-data) ────────────────────────
    FusionSensorDescription(
        key="charging_power", data_key="charging_power",
        name="Charging power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        icon="mdi:flash",
    ),
    FusionSensorDescription(
        key="charging_voltage", data_key="charging_voltage",
        name="Charging voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
    ),
    FusionSensorDescription(
        key="charging_current", data_key="charging_current",
        name="Charging current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
    ),
    FusionSensorDescription(
        key="session_energy", data_key="session_energy",
        name="Session energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:battery-charging",
    ),
    FusionSensorDescription(
        key="session_duration_s", data_key="session_duration_s",
        name="Charging duration",
        icon="mdi:timer",
    ),
    # ── Lifetime total ────────────────────────────────────────────────
    FusionSensorDescription(
        key="total_energy_kwh", data_key="total_energy_kwh",
        name="Total energy delivered",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:counter",
    ),
    # ── Gun settings ──────────────────────────────────────────────────
    FusionSensorDescription(
        key="max_current", data_key="max_current",
        name="Max charging current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
    ),
    FusionSensorDescription(
        key="working_mode", data_key="working_mode",
        name="Working mode", icon="mdi:solar-power",
    ),
    FusionSensorDescription(
        key="max_grid_power", data_key="max_grid_power",
        name="Max power from grid",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        icon="mdi:transmission-tower-import",
    ),
    FusionSensorDescription(
        key="surplus_power_start", data_key="surplus_power_start",
        name="PV surplus to start charging",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        icon="mdi:solar-power-variant",
    ),
    FusionSensorDescription(
        key="phase_switch", data_key="phase_switch",
        name="Phase switch", icon="mdi:lightning-bolt-circle",
    ),
    FusionSensorDescription(
        key="locking_mode", data_key="locking_mode",
        name="Connector locking mode", icon="mdi:lock",
    ),
    # ── Parent settings ───────────────────────────────────────────────
    FusionSensorDescription(
        key="max_power_limit", data_key="max_power_limit",
        name="Dynamic charging power limit",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        icon="mdi:lightning-bolt-circle",
    ),
    FusionSensorDescription(
        key="networking_mode", data_key="networking_mode",
        name="Networking mode", icon="mdi:network",
    ),
    FusionSensorDescription(
        key="charger_alias", data_key="charger_alias",
        name="Charger alias", icon="mdi:tag",
    ),
    FusionSensorDescription(
        key="wifi_signal", data_key="wifi_signal",
        name="WiFi signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        icon="mdi:wifi",
    ),
)

STATION_SENSORS: tuple[FusionSensorDescription, ...] = (
    FusionSensorDescription(
        key="current_power", data_key="current_power", name="PV power",
        device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT, icon="mdi:solar-power",
    ),
    FusionSensorDescription(
        key="battery_power", data_key="battery_power", name="Battery power",
        device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT, icon="mdi:battery-charging",
    ),
    FusionSensorDescription(
        key="daily_energy", data_key="daily_energy", name="Energy today",
        device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:solar-power-variant",
    ),
    FusionSensorDescription(
        key="daily_on_grid", data_key="daily_on_grid", name="Grid export today",
        device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:transmission-tower-export",
    ),
    FusionSensorDescription(
        key="daily_buy", data_key="daily_buy", name="Grid import today",
        device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:transmission-tower-import",
    ),
    FusionSensorDescription(
        key="daily_use", data_key="daily_use", name="House consumption today",
        device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:home-lightning-bolt",
    ),
    FusionSensorDescription(
        key="daily_self_use", data_key="daily_self_use", name="Self-consumed today",
        device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:home-battery",
    ),
    FusionSensorDescription(
        key="month_energy", data_key="month_energy", name="Energy this month",
        device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:calendar-month",
    ),
    FusionSensorDescription(
        key="year_energy", data_key="year_energy", name="Energy this year",
        device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:calendar",
    ),
    FusionSensorDescription(
        key="cumulative_energy", data_key="cumulative_energy", name="Lifetime energy",
        device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:counter",
    ),
    FusionSensorDescription(
        key="battery_capacity", data_key="battery_capacity", name="Battery capacity",
        device_class=SensorDeviceClass.ENERGY_STORAGE, state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, icon="mdi:battery",
    ),
    FusionSensorDescription(
        key="plant_status", data_key="plant_status",
        name="Plant status", icon="mdi:information-outline",
    ),
    FusionSensorDescription(
        key="installed_capacity", data_key="installed_capacity", name="Installed capacity",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT, icon="mdi:solar-panel-large",
    ),
    FusionSensorDescription(
        key="eq_power_hours", data_key="eq_power_hours",
        name="Equivalent power hours today",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="h", icon="mdi:clock-outline",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    charger: ChargerCoordinator = data["charger"]
    station: StationCoordinator | None = data["station"]

    entities: list[SensorEntity] = [
        FusionSensor(charger, desc, is_station=False) for desc in CHARGER_SENSORS
    ]
    if station is not None:
        entities.extend(
            FusionSensor(station, desc, is_station=True) for desc in STATION_SENSORS
        )
    async_add_entities(entities)


class FusionSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, description: FusionSensorDescription, is_station: bool) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._is_station = is_station
        if is_station:
            self._attr_unique_id = f"{coordinator.station_dn_id}_station_{description.key}"
        else:
            self._attr_unique_id = f"{coordinator.dn_id}_charger_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        if self._is_station:
            return DeviceInfo(
                identifiers={(DOMAIN, f"station_{self.coordinator.station_dn_id}")},
                name=self.coordinator.station_name,
                manufacturer="Huawei",
                model="FusionSolar Solar Plant",
            )
        return DeviceInfo(
            identifiers={(DOMAIN, f"charger_{self.coordinator.dn_id}")},
            name=self.coordinator.device_name,
            manufacturer="Huawei",
            model="FusionSolar EV Charger",
        )

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self.entity_description.data_key)