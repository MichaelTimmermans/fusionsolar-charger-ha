"""
Number platform for FusionSolar App HA.

Exposes adjustable charger settings as HA number entities:
  - Max charging current (A)           → signal 20003, gun dnId
  - Max power from grid (kW)           → signal 20006, gun dnId
  - PV surplus to start charging (kW)  → signal 20007, gun dnId
  - Dynamic charging power limit (kW)  → signal 20001, parent dnId

Writing uses POST /rest/neteco/web/homemgr/v1/device/set-config-info
Payload: {conditions: [{dnId, signals: [{id, value}]}]}
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ChargerCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ChargerNumberDescription(NumberEntityDescription):
    signal_id: int = 0
    use_gun_dn: bool = True      # True = gun dnId, False = parent dnId
    data_key: str = ""           # coordinator data key for current value


CHARGER_NUMBERS: tuple[ChargerNumberDescription, ...] = (
    ChargerNumberDescription(
        key="max_current",
        name="Max charging current",
        icon="mdi:current-ac",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        native_min_value=6.0,
        native_max_value=32.0,
        native_step=1.0,
        mode=NumberMode.SLIDER,
        signal_id=20003,
        use_gun_dn=True,
        data_key="max_current",
    ),
    ChargerNumberDescription(
        key="max_grid_power",
        name="Max power from grid",
        icon="mdi:transmission-tower-import",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        native_min_value=0.0,
        native_max_value=22.0,
        native_step=0.1,
        mode=NumberMode.BOX,
        signal_id=20006,
        use_gun_dn=True,
        data_key="max_grid_power",
    ),
    ChargerNumberDescription(
        key="surplus_power_start",
        name="PV surplus to start charging",
        icon="mdi:solar-power-variant",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        native_min_value=0.5,
        native_max_value=22.0,
        native_step=0.1,
        mode=NumberMode.BOX,
        signal_id=20007,
        use_gun_dn=True,
        data_key="surplus_power_start",
    ),
    ChargerNumberDescription(
        key="max_power_limit",
        name="Dynamic charging power limit",
        icon="mdi:lightning-bolt-circle",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        native_min_value=4.1,
        native_max_value=17.0,
        native_step=0.1,
        mode=NumberMode.SLIDER,
        signal_id=20001,
        use_gun_dn=False,    # parent dnId, confirmed from DIAG
        data_key="max_power_limit",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    charger: ChargerCoordinator = data["charger"]

    async_add_entities(
        ChargerNumber(charger, desc) for desc in CHARGER_NUMBERS
    )


class ChargerNumber(CoordinatorEntity[ChargerCoordinator], NumberEntity):
    """Adjustable number entity for a charger config signal."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChargerCoordinator,
        description: ChargerNumberDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.dn_id}_charger_num_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"charger_{self.coordinator.dn_id}")},
            name=self.coordinator.device_name,
            manufacturer="Huawei",
            model="FusionSolar EV Charger",
        )

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.data:
            return None
        val = self.coordinator.data.get(self.entity_description.data_key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        desc = self.entity_description
        dn_id = (
            self.coordinator.gun_dn_id
            if desc.use_gun_dn
            else self.coordinator.dn_id
        )

        _LOGGER.info(
            "Setting signal %s to %s on dnId %s (%s)",
            desc.signal_id, value, dn_id,
            "gun" if desc.use_gun_dn else "parent",
        )

        success = await self.coordinator.api.set_config_signal(
            dn_id=dn_id,
            signal_id=desc.signal_id,
            value=value,
        )

        if success:
            _LOGGER.info("Signal %s set to %s successfully", desc.signal_id, value)
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set signal %s to %s", desc.signal_id, value)
