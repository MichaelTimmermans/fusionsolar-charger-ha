"""Sensor platform for FusionSolar App HA — all device types."""
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
    UnitOfEnergy, UnitOfPower, UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import (
    BatteryCoordinator,
    ChargerCoordinator,
    InverterCoordinator,
    MeterCoordinator,
    StationCoordinator,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class FusionSensorDescription(SensorEntityDescription):
    data_key: str = ""


# ---------------------------------------------------------------------------
# EV Charger sensors
# ---------------------------------------------------------------------------

CHARGER_SENSORS: tuple[FusionSensorDescription, ...] = (
    FusionSensorDescription(
        key="signal_status", data_key="signal_status",
        name="Status", icon="mdi:ev-station",
    ),
    FusionSensorDescription(
        key="charging_power", data_key="charging_power",
        name="Charging power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
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
    FusionSensorDescription(
        key="total_energy_kwh", data_key="total_energy_kwh",
        name="Total energy delivered",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:counter",
    ),
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


# ---------------------------------------------------------------------------
# Inverter sensors
# ---------------------------------------------------------------------------

INVERTER_SENSORS: tuple[FusionSensorDescription, ...] = (
    FusionSensorDescription(
        key="running_status", data_key="running_status",
        name="Status", icon="mdi:solar-panel-large",
    ),
    FusionSensorDescription(
        key="active_power", data_key="active_power",
        name="Active power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:solar-power",
    ),
    FusionSensorDescription(
        key="daily_energy", data_key="daily_energy",
        name="Daily energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:solar-power-variant",
    ),
    FusionSensorDescription(
        key="month_energy", data_key="month_energy",
        name="Monthly energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:calendar-month",
    ),
    FusionSensorDescription(
        key="year_energy", data_key="year_energy",
        name="Yearly energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:calendar",
    ),
    FusionSensorDescription(
        key="grid_voltage_a", data_key="grid_voltage_a",
        name="Grid voltage A",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
    ),
    FusionSensorDescription(
        key="grid_voltage_b", data_key="grid_voltage_b",
        name="Grid voltage B",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
    ),
    FusionSensorDescription(
        key="grid_voltage_c", data_key="grid_voltage_c",
        name="Grid voltage C",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
    ),
    FusionSensorDescription(
        key="grid_current_a", data_key="grid_current_a",
        name="Grid current A",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
    ),
    FusionSensorDescription(
        key="grid_current_b", data_key="grid_current_b",
        name="Grid current B",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
    ),
    FusionSensorDescription(
        key="grid_current_c", data_key="grid_current_c",
        name="Grid current C",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
    ),
    FusionSensorDescription(
        key="temperature", data_key="temperature",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:thermometer",
    ),
)


# ---------------------------------------------------------------------------
# Battery sensors
# ---------------------------------------------------------------------------

BATTERY_SENSORS: tuple[FusionSensorDescription, ...] = (
    FusionSensorDescription(
        key="running_status", data_key="running_status",
        name="Status", icon="mdi:battery",
    ),
    FusionSensorDescription(
        key="battery_power", data_key="battery_power",
        name="Battery power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:battery-charging",
    ),
    FusionSensorDescription(
        key="voltage", data_key="voltage",
        name="Battery voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
    ),
    FusionSensorDescription(
        key="charge_capacity", data_key="charge_capacity",
        name="Charge capacity",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:battery-plus",
    ),
    FusionSensorDescription(
        key="discharge_capacity", data_key="discharge_capacity",
        name="Discharge capacity",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:battery-minus",
    ),
    FusionSensorDescription(
        key="charge_mode", data_key="charge_mode",
        name="Charge mode", icon="mdi:cog",
    ),
)


# ---------------------------------------------------------------------------
# Grid meter sensors
# ---------------------------------------------------------------------------

METER_SENSORS: tuple[FusionSensorDescription, ...] = (
    FusionSensorDescription(
        key="active_power", data_key="active_power",
        name="Active power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:transmission-tower",
    ),
    FusionSensorDescription(
        key="active_energy", data_key="active_energy",
        name="Grid export energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:transmission-tower-export",
    ),
    FusionSensorDescription(
        key="reverse_energy", data_key="reverse_energy",
        name="Grid import energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:transmission-tower-import",
    ),
    FusionSensorDescription(
        key="voltage_a", data_key="voltage_a",
        name="Voltage A",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        icon="mdi:sine-wave",
    ),
    FusionSensorDescription(
        key="current_a", data_key="current_a",
        name="Current A",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-ac",
    ),
)


# ---------------------------------------------------------------------------
# Station sensors
# ---------------------------------------------------------------------------

STATION_SENSORS: tuple[FusionSensorDescription, ...] = (
    FusionSensorDescription(
        key="current_power", data_key="current_power",
        name="PV power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        icon="mdi:solar-power",
    ),
    FusionSensorDescription(
        key="daily_energy", data_key="daily_energy",
        name="Energy today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:solar-power-variant",
    ),
    FusionSensorDescription(
        key="month_energy", data_key="month_energy",
        name="Energy this month",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:calendar-month",
    ),
    FusionSensorDescription(
        key="year_energy", data_key="year_energy",
        name="Energy this year",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:calendar",
    ),
    FusionSensorDescription(
        key="cumulative_energy", data_key="cumulative_energy",
        name="Lifetime energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:counter",
    ),
    FusionSensorDescription(
        key="daily_self_use", data_key="daily_self_use",
        name="Self-consumed today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:home-battery",
    ),
    FusionSensorDescription(
        key="daily_use", data_key="daily_use",
        name="House consumption today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:home-lightning-bolt",
    ),
)


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []

    # Charger sensors
    charger = data["charger"]
    entities.extend(
        FusionSensor(charger, desc, "charger", charger.dn_id)
        for desc in CHARGER_SENSORS
    )

    # Inverter sensors
    for inv_coord in data.get("inverters", []):
        entities.extend(
            FusionSensor(inv_coord, desc, "inverter", inv_coord.dn_id)
            for desc in INVERTER_SENSORS
        )

    # Battery sensors
    for bat_coord in data.get("batteries", []):
        entities.extend(
            FusionSensor(bat_coord, desc, "battery", bat_coord.dn_id)
            for desc in BATTERY_SENSORS
        )

    # Meter sensors
    for meter_coord in data.get("meters", []):
        entities.extend(
            FusionSensor(meter_coord, desc, "meter", meter_coord.dn_id)
            for desc in METER_SENSORS
        )

    # Station sensors
    station = data.get("station")
    if station:
        entities.extend(
            FusionSensor(station, desc, "station", station.station_dn_id)
            for desc in STATION_SENSORS
        )

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Generic sensor entity
# ---------------------------------------------------------------------------

class FusionSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        description: FusionSensorDescription,
        device_type: str,
        device_id: int,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._device_type = device_type
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}_{device_type}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        c = self.coordinator
        if self._device_type == "charger":
            return DeviceInfo(
                identifiers={(DOMAIN, f"charger_{c.dn_id}")},
                name=c.device_name,
                manufacturer="Huawei",
                model="FusionSolar EV Charger",
            )
        if self._device_type == "inverter":
            return DeviceInfo(
                identifiers={(DOMAIN, f"inverter_{c.dn_id}")},
                name=c.device_name,
                manufacturer="Huawei",
                model="FusionSolar Inverter",
            )
        if self._device_type == "battery":
            return DeviceInfo(
                identifiers={(DOMAIN, f"battery_{c.dn_id}")},
                name=c.device_name,
                manufacturer="Huawei",
                model="LUNA2000 Battery",
            )
        if self._device_type == "meter":
            return DeviceInfo(
                identifiers={(DOMAIN, f"meter_{c.dn_id}")},
                name=c.device_name,
                manufacturer="Huawei",
                model="FusionSolar Grid Meter",
            )
        # station
        return DeviceInfo(
            identifiers={(DOMAIN, f"station_{c.station_dn_id}")},
            name=c.station_name,
            manufacturer="Huawei",
            model="FusionSolar Solar Plant",
        )

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self.entity_description.data_key)
