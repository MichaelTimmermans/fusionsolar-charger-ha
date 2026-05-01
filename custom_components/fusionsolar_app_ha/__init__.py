"""FusionSolar App HA — integration setup."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FusionSolarApi, FusionSolarApiError, FusionSolarAuthError
from .const import (
    CONF_API_BASE,
    CONF_DEVICE_DN_ID,
    CONF_DEVICE_NAME,
    CONF_STATION_DN_ID,
    CONF_STATION_NAME,
    DOMAIN,
)
from .coordinator import ChargerCoordinator, DiagnosticsCoordinator, StationCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

# 'charger_signal_status' is hier verwijderd uit VALID_CHARGER_KEYS
VALID_CHARGER_KEYS = {
    "charger_charge_power",
    "charger_session_energy",
    "charger_max_current",
    "charger_working_mode",
    "charger_max_grid_power",
    "charger_surplus_power_start",
    "charger_phase_switch",
    "charger_locking_mode",
    "charger_wifi_signal",
    "charger_connectivity",
    "charger_is_charging",
    "charger_vehicle_connected",
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up FusionSolar from a config entry."""
    session = async_get_clientsession(hass, verify_ssl=False)

    api = FusionSolarApi(
        session=session,
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        api_base=entry.data.get(CONF_API_BASE, ""),
    )

    try:
        await api.authenticate()
    except FusionSolarAuthError as exc:
        _LOGGER.error("Authentication failed for %s: %s", entry.title, exc)
        return False

    dn_id: int | None = entry.data.get(CONF_DEVICE_DN_ID)

    if dn_id is None:
        try:
            raw_devices = await api.get_management_devices()
            if not raw_devices: return False
            first = raw_devices[0]
            dn_id = int(first.get("dnId", 0))
            device_name = first.get("name", f"Charger {dn_id}")
            hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_DEVICE_DN_ID: dn_id, CONF_DEVICE_NAME: device_name})
        except Exception: return False
    else:
        dn_id = int(dn_id)

    device_name: str = entry.data.get(CONF_DEVICE_NAME, f"Charger {dn_id}")
    _remove_stale_entities(hass, entry, dn_id)
    gun_dn_id = await _discover_gun_dn_id(api, dn_id)

    charger_coordinator = ChargerCoordinator(hass=hass, api=api, dn_id=dn_id, gun_dn_id=gun_dn_id, device_name=device_name)
    await charger_coordinator.async_config_entry_first_refresh()

    diag_coordinator = DiagnosticsCoordinator(hass=hass, api=api, dn_id=dn_id, gun_dn_id=gun_dn_id, device_name=device_name)
    await diag_coordinator.async_refresh()

    station_dn_id: int | None = entry.data.get(CONF_STATION_DN_ID)
    station_coordinator: StationCoordinator | None = None
    if station_dn_id:
        station_coordinator = StationCoordinator(hass=hass, api=api, station_dn_id=int(station_dn_id), station_name=entry.data.get(CONF_STATION_NAME, "Solar Plant"))
        await station_coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"charger": charger_coordinator, "station": station_coordinator, "diag": diag_coordinator}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok: hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

def _remove_stale_entities(hass: HomeAssistant, entry: ConfigEntry, dn_id: int) -> None:
    ent_reg = er.async_get(hass)
    entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    for entity_entry in entries:
        uid = entity_entry.unique_id or ""
        if not uid.startswith(str(dn_id)): continue
        suffix = uid.replace(f"{dn_id}_", "", 1)
        if suffix not in VALID_CHARGER_KEYS:
            ent_reg.async_remove(entity_entry.entity_id)

async def _discover_gun_dn_id(api: FusionSolarApi, charger_dn_id: int) -> int:
    try:
        company_dn = await api.get_company_dn()
        raw_devices = await api.get_management_devices_raw(company_dn)
        our_device = next((d for d in raw_devices if int(d.get("dnId", 0)) == charger_dn_id), None)
        if our_device:
            parent_dn = our_device.get("dn", "")
            if parent_dn:
                children = await api.get_children_list(parent_dn)
                if children: return int(children[0].get("dnId", 0))
    except: pass
    return charger_dn_id