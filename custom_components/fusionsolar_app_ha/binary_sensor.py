"""
Binary sensor platform for FusionSolar App HA.
"""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ChargerCoordinator, StationCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    charger_coordinator: ChargerCoordinator = data["charger"]
    station_coordinator: StationCoordinator | None = data["station"]

    entities: list[BinarySensorEntity] = [
        ChargerConnectivitySensor(charger_coordinator),
        IsChargingSensor(charger_coordinator),
        VehicleConnectedSensor(charger_coordinator),
    ]
    if station_coordinator is not None:
        entities.append(StationConnectivitySensor(station_coordinator))

    async_add_entities(entities)

def _charger_device_info(coordinator: ChargerCoordinator) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"charger_{coordinator.dn_id}")},
        name=coordinator.device_name,
        manufacturer="Huawei",
        model="FusionSolar EV Charger",
    )

class ChargerConnectivitySensor(CoordinatorEntity[ChargerCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Connectivity"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: ChargerCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.dn_id}_charger_connectivity"

    @property
    def device_info(self) -> DeviceInfo:
        return _charger_device_info(self.coordinator)

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success

class IsChargingSensor(CoordinatorEntity[ChargerCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator: ChargerCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.dn_id}_is_charging"

    @property
    def device_info(self) -> DeviceInfo:
        return _charger_device_info(self.coordinator)

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        status = self.coordinator.data.get("signal_status", "")
        # Check op beide laad-statussen om "Charging" aan te zetten
        if status in ("Charging", "PV power charging"):
            return True
        if status in ("No car connected", "Charging complete", "Standby", "Faulted"):
            return False
        
        power = self.coordinator.data.get("charging_power")
        if power is not None:
            return float(power) > 0
        return self.coordinator.data.get("status_code") == 2

class VehicleConnectedSensor(CoordinatorEntity[ChargerCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Vehicle connected"
    _attr_device_class = BinarySensorDeviceClass.PLUG
    _attr_icon = "mdi:car-electric"

    def __init__(self, coordinator: ChargerCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.dn_id}_vehicle_connected"

    @property
    def device_info(self) -> DeviceInfo:
        return _charger_device_info(self.coordinator)

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        status = self.coordinator.data.get("signal_status", "")
        if status == "No car connected":
            return False
        if status:
            return True
        code = self.coordinator.data.get("status_code", -1)
        return 1 <= int(code) <= 5

class StationConnectivitySensor(CoordinatorEntity[StationCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Connectivity"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: StationCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.station_dn_id}_station_connectivity"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"station_{self.coordinator.station_dn_id}")},
            name=self.coordinator.station_name,
            manufacturer="Huawei",
            model="FusionSolar Solar Plant",
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success and bool(self.coordinator.data)