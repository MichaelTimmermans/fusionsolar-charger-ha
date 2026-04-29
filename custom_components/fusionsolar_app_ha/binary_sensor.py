"""
Binary sensor platform for FusionSolar App HA.

Charger:  connectivity, is_charging, vehicle_connected
Station:  connectivity
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

# Signal 2101519 status values that mean "actively charging"
_CHARGING_STATES = {"3", "11"}   # "3"=Charging, "11"=PV Power Charging

# Signal 2101519 status values that mean a vehicle is present
_CONNECTED_STATES = {"1", "2", "3", "4", "6", "8", "9", "10", "11"}
# Standby, Timed wait, Charging, Complete, Orderly wait, Starting, Alarm, PV wait, PV charging
# Excludes "0" (No car connected), "5" (Faulted), "7" (Upgrading)


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _charger_device_info(coordinator: ChargerCoordinator) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"charger_{coordinator.dn_id}")},
        name=coordinator.device_name,
        manufacturer="Huawei",
        model="FusionSolar EV Charger",
    )


def _signal_status_value(coordinator: ChargerCoordinator) -> str:
    """Return the raw signal 2101519 value string (e.g. '0', '3', '11')."""
    if not coordinator.data:
        return ""
    # signal_status holds the human label — we need the raw numeric key
    # We store status_code from charge-status as fallback, but for signal-based
    # detection we check the label directly against known charging labels
    return coordinator.data.get("_signal_status_raw", "")


# ---------------------------------------------------------------------------
# Charger binary sensors
# ---------------------------------------------------------------------------

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
    """
    True when the charger is actively delivering power.
    Uses signal_status label (from signal 2101519) for richest detection,
    with charge_power > 0 as a secondary confirmation.
    """
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
        # Primary: check known charging status labels
        if status in ("Charging", "PV power charging"):
            return True
        if status in ("No car connected", "Charging complete", "Standby", "Faulted"):
            return False
        # Secondary fallback: charge_power > 0
        power = self.coordinator.data.get("charge_power")
        if power is not None:
            return float(power) > 0
        # Fallback to numeric status_code: 2 = Charging
        return self.coordinator.data.get("status_code") == 2


class VehicleConnectedSensor(CoordinatorEntity[ChargerCoordinator], BinarySensorEntity):
    """
    True when a vehicle is physically plugged in.
    False only when status is "No car connected".
    """
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
            # Any other known status means a car is present
            return True
        # Fallback to numeric status_code: 1-5 = vehicle present
        code = self.coordinator.data.get("status_code", -1)
        if code == -1:
            return None
        return 1 <= int(code) <= 5


# ---------------------------------------------------------------------------
# Station binary sensor
# ---------------------------------------------------------------------------

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
