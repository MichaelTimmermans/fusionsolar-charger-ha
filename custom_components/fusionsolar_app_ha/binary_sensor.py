"""Binary sensor platform for FusionSolar App HA."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass, BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import (
    BatteryCoordinator,
    ChargerCoordinator,
    InverterCoordinator,
    StationCoordinator,
)

_CHARGING_STATUSES = {"Charging", "PV power charging", "Starting charging"}
_CONNECTED_STATUSES = {
    "Standby", "Timed charging — waiting", "Charging",
    "Charging complete", "Orderly charging — waiting",
    "Starting charging", "Alarm", "PV power — waiting", "PV power charging",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = []

    charger = data["charger"]
    entities += [
        ChargerConnectivity(charger),
        IsCharging(charger),
        VehicleConnected(charger),
    ]

    for inv in data.get("inverters", []):
        entities.append(InverterConnectivity(inv))

    for bat in data.get("batteries", []):
        entities.append(BatteryConnectivity(bat))
        entities.append(BatteryCharging(bat))

    station = data.get("station")
    if station:
        entities.append(StationConnectivity(station))

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Charger binary sensors
# ---------------------------------------------------------------------------

class ChargerConnectivity(CoordinatorEntity[ChargerCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Connectivity"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: ChargerCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.dn_id}_charger_connectivity"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"charger_{self.coordinator.dn_id}")},
            name=self.coordinator.device_name,
            manufacturer="Huawei",
            model="FusionSolar EV Charger",
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success


class IsCharging(CoordinatorEntity[ChargerCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Charging active"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator: ChargerCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.dn_id}_is_charging"

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
        if status in _CHARGING_STATUSES:
            return True
        if status:
            return False
        # Fallback: check power
        power = self.coordinator.data.get("charging_power")
        if power is not None:
            return float(power) > 0
        return self.coordinator.data.get("status_code") == 2


class VehicleConnected(CoordinatorEntity[ChargerCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Vehicle connected"
    _attr_device_class = BinarySensorDeviceClass.PLUG
    _attr_icon = "mdi:car-electric"

    def __init__(self, coordinator: ChargerCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.dn_id}_vehicle_connected"

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
        if status == "No car connected":
            return False
        if status in _CONNECTED_STATUSES:
            return True
        if status:
            return False
        code = self.coordinator.data.get("status_code", -1)
        return 1 <= int(code) <= 5 if code != -1 else None


# ---------------------------------------------------------------------------
# Inverter binary sensors
# ---------------------------------------------------------------------------

class InverterConnectivity(CoordinatorEntity[InverterCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Connectivity"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: InverterCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.dn_id}_inverter_connectivity"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"inverter_{self.coordinator.dn_id}")},
            name=self.coordinator.device_name,
            manufacturer="Huawei",
            model="FusionSolar Inverter",
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success


# ---------------------------------------------------------------------------
# Battery binary sensors
# ---------------------------------------------------------------------------

class BatteryConnectivity(CoordinatorEntity[BatteryCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Connectivity"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: BatteryCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.dn_id}_battery_connectivity"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"battery_{self.coordinator.dn_id}")},
            name=self.coordinator.device_name,
            manufacturer="Huawei",
            model="LUNA2000 Battery",
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success


class BatteryCharging(CoordinatorEntity[BatteryCoordinator], BinarySensorEntity):
    """True when battery power is positive (charging from PV/grid)."""
    _attr_has_entity_name = True
    _attr_name = "Charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
    _attr_icon = "mdi:battery-charging"

    def __init__(self, coordinator: BatteryCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.dn_id}_battery_charging"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"battery_{self.coordinator.dn_id}")},
            name=self.coordinator.device_name,
            manufacturer="Huawei",
            model="LUNA2000 Battery",
        )

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        power = self.coordinator.data.get("battery_power")
        if power is None:
            return None
        return float(power) > 0


# ---------------------------------------------------------------------------
# Station binary sensor
# ---------------------------------------------------------------------------

class StationConnectivity(CoordinatorEntity[StationCoordinator], BinarySensorEntity):
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
