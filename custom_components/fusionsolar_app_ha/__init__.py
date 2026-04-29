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

# Keys that the current ChargerCoordinator actually produces.
# Any entity whose unique_id suffix is NOT in this set is a stale
# leftover from a previous version and will be removed automatically.
VALID_CHARGER_KEYS = {
    "charger_signal_status",
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

    # ── Resolve charger dn_id ─────────────────────────────────────────
    dn_id: int | None = entry.data.get(CONF_DEVICE_DN_ID)

    if dn_id is None:
        _LOGGER.warning("Config entry missing device_dn_id — re-discovering")
        try:
            raw_devices = await api.get_management_devices()
        except (FusionSolarAuthError, FusionSolarApiError) as exc:
            _LOGGER.error("Could not re-discover devices: %s", exc)
            return False

        if not raw_devices:
            _LOGGER.error("No EV charger devices found for %s", entry.title)
            return False

        first = raw_devices[0]
        dn_id = int(first.get("dnId", 0))
        device_name = first.get("name", f"Charger {dn_id}")
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_DEVICE_DN_ID: dn_id, CONF_DEVICE_NAME: device_name},
        )
    else:
        dn_id = int(dn_id)

    device_name: str = entry.data.get(CONF_DEVICE_NAME, f"Charger {dn_id}")

    # ── Remove stale entities from previous integration versions ──────
    _remove_stale_entities(hass, entry, dn_id)

    # ── Discover gun dnId ─────────────────────────────────────────────
    gun_dn_id = await _discover_gun_dn_id(api, dn_id)
    _LOGGER.info("Charger %s: gun dnId = %s", dn_id, gun_dn_id)

    # ── Charger coordinator ───────────────────────────────────────────
    charger_coordinator = ChargerCoordinator(
        hass=hass,
        api=api,
        dn_id=dn_id,
        gun_dn_id=gun_dn_id,
        device_name=device_name,
    )
    await charger_coordinator.async_config_entry_first_refresh()

    # ── Diagnostics coordinator (fires once at startup) ───────────────
    diag_coordinator = DiagnosticsCoordinator(
        hass=hass,
        api=api,
        dn_id=dn_id,
        gun_dn_id=gun_dn_id,
        device_name=device_name,
    )
    await diag_coordinator.async_refresh()

    # ── Station coordinator ───────────────────────────────────────────
    station_coordinator: StationCoordinator | None = None
    station_dn_id: int | None = entry.data.get(CONF_STATION_DN_ID)

    if station_dn_id is None:
        try:
            stations = await api.get_station_list()
            if stations:
                first_station = stations[0]
                station_dn_id = int(first_station.get("dnId", 0)) or None
                station_name = first_station.get("name", "Solar Plant")
                if station_dn_id:
                    hass.config_entries.async_update_entry(
                        entry,
                        data={
                            **entry.data,
                            CONF_STATION_DN_ID: station_dn_id,
                            CONF_STATION_NAME: station_name,
                        },
                    )
                    _LOGGER.info("Discovered station: %s (dnId=%s)", station_name, station_dn_id)
        except Exception as exc:
            _LOGGER.warning("Station discovery failed (non-fatal): %s", exc)

    if station_dn_id:
        station_coordinator = StationCoordinator(
            hass=hass,
            api=api,
            station_dn_id=int(station_dn_id),
            station_name=entry.data.get(CONF_STATION_NAME, "Solar Plant"),
        )
        await station_coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "charger": charger_coordinator,
        "station": station_coordinator,
        "diag": diag_coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


def _remove_stale_entities(
    hass: HomeAssistant, entry: ConfigEntry, dn_id: int
) -> None:
    """
    Remove entity registry entries that belonged to previous versions
    of this integration but are no longer created by the current code.
    This prevents 'Unavailable' ghost entities from old installs.
    """
    ent_reg = er.async_get(hass)
    entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)

    for entity_entry in entries:
        uid = entity_entry.unique_id or ""
        # Only touch charger entities (station entities have a different prefix)
        if not uid.startswith(str(dn_id)):
            continue
        # Extract the key suffix — unique_id format is "{dn_id}_charger_{key}"
        suffix = uid.replace(f"{dn_id}_", "", 1)  # e.g. "charger_signal_status"
        if suffix not in VALID_CHARGER_KEYS:
            _LOGGER.info(
                "Removing stale entity %s (unique_id=%s) from previous version",
                entity_entry.entity_id, uid,
            )
            ent_reg.async_remove(entity_entry.entity_id)


async def _discover_gun_dn_id(api: FusionSolarApi, charger_dn_id: int) -> int:
    """Find the gun/connector child dnId. Falls back to parent dnId."""
    try:
        company_dn = await api.get_company_dn()
        raw_devices = await api.get_management_devices_raw(company_dn)
        our_device = next(
            (d for d in raw_devices if int(d.get("dnId", 0)) == charger_dn_id), None
        )
        if our_device:
            parent_dn = our_device.get("dn", "")
            if parent_dn:
                children = await api.get_children_list(parent_dn)
                if children:
                    gun_dn_id = int(children[0].get("dnId", 0))
                    if gun_dn_id:
                        return gun_dn_id
    except Exception as exc:
        _LOGGER.warning("Gun dnId discovery failed for %s: %s", charger_dn_id, exc)
    return charger_dn_id
