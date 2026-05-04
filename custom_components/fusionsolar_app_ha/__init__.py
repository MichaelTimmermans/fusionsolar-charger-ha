"""
FusionSolar App HA — integration setup.

Discovers ALL devices on the account automatically:
  - EV charger(s)     → ChargerCoordinator
  - Inverter(s)       → InverterCoordinator
  - Battery/LUNA2000  → BatteryCoordinator
  - Grid meter(s)     → MeterCoordinator
  - Solar plant       → StationCoordinator
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FusionSolarApi, FusionSolarApiError, FusionSolarAuthError
from .const import (
    CONF_API_BASE,
    CONF_DEVICE_DN_ID,
    CONF_DEVICE_NAME,
    CONF_STATION_DN_ID,
    CONF_STATION_NAME,
    DOMAIN,
    MOC_BATTERY,
    MOC_EV_CHARGER,
    MOC_EV_CHARGER_GUN,
    MOC_GRID_METER,
    MOC_INVERTER_RESIDENTIAL,
    MOC_INVERTER_STRING,
    MOC_POWER_SENSOR,
)
from .coordinator import (
    BatteryCoordinator,
    ChargerCoordinator,
    InverterCoordinator,
    MeterCoordinator,
    StationCoordinator,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.NUMBER]


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
        _LOGGER.error("Authentication failed: %s", exc)
        return False

    # ── Discover all devices ──────────────────────────────────────────
    try:
        company_dn = await api.get_company_dn()
        if not company_dn:
            _LOGGER.error("Could not get company DN")
            return False
        all_devices = await api.get_all_devices(company_dn)
    except (FusionSolarAuthError, FusionSolarApiError) as exc:
        _LOGGER.error("Device discovery failed: %s", exc)
        return False

    _LOGGER.info(
        "Discovered %d total devices under company %s",
        len(all_devices), company_dn,
    )

    # Group devices by mocType
    chargers   = [d for d in all_devices if int(d.get("mocType", d.get("typeId", 0))) == MOC_EV_CHARGER]
    inverters  = [d for d in all_devices if int(d.get("mocType", d.get("typeId", 0))) in (MOC_INVERTER_STRING, MOC_INVERTER_RESIDENTIAL)]
    batteries  = [d for d in all_devices if int(d.get("mocType", d.get("typeId", 0))) == MOC_BATTERY]
    meters     = [d for d in all_devices if int(d.get("mocType", d.get("typeId", 0))) in (MOC_GRID_METER, MOC_POWER_SENSOR)]

    _LOGGER.info(
        "Found: %d charger(s), %d inverter(s), %d battery(ies), %d meter(s)",
        len(chargers), len(inverters), len(batteries), len(meters),
    )

    # ── Fallback: if device-list without mocType filter gives empty ───
    # Some accounts return devices only when filtered by specific mocType
    if not chargers:
        chargers = await api.get_management_devices_raw(company_dn)
        _LOGGER.debug("Fallback charger discovery: %d found", len(chargers))

    # ── Resolve the primary charger from config entry ─────────────────
    dn_id: int | None = entry.data.get(CONF_DEVICE_DN_ID)
    if dn_id is None and chargers:
        first = chargers[0]
        dn_id = int(first.get("dnId", 0))
        device_name = first.get("name", f"Charger {dn_id}")
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_DEVICE_DN_ID: dn_id, CONF_DEVICE_NAME: device_name},
        )
    elif dn_id is not None:
        dn_id = int(dn_id)

    device_name: str = entry.data.get(CONF_DEVICE_NAME, f"Charger {dn_id}")

    if dn_id is None:
        _LOGGER.error("No EV charger found — cannot set up integration")
        return False

    # ── Discover gun dnId for the primary charger ─────────────────────
    gun_dn_id = await _discover_gun_dn_id(api, dn_id, all_devices)
    _LOGGER.info("Charger %s → gun dnId %s", dn_id, gun_dn_id)

    coordinators: dict = {}

    # ── Charger coordinator ───────────────────────────────────────────
    charger_coord = ChargerCoordinator(
        hass=hass, api=api,
        dn_id=dn_id, gun_dn_id=gun_dn_id,
        device_name=device_name,
    )
    await charger_coord.async_config_entry_first_refresh()
    coordinators["charger"] = charger_coord

    # ── Inverter coordinators ─────────────────────────────────────────
    inv_coords = []
    for inv in inverters:
        inv_dn_id = int(inv.get("dnId", 0))
        inv_dn    = inv.get("dn", "")
        inv_name  = inv.get("name", f"Inverter {inv_dn_id}")
        if not inv_dn:
            _LOGGER.warning("Inverter %s has no DN string — skipping", inv_dn_id)
            continue
        coord = InverterCoordinator(
            hass=hass, api=api,
            dn_id=inv_dn_id, device_dn=inv_dn,
            device_name=inv_name,
        )
        await coord.async_config_entry_first_refresh()
        inv_coords.append(coord)
        _LOGGER.info("Set up inverter: %s (%s)", inv_name, inv_dn_id)
    coordinators["inverters"] = inv_coords

    # ── Battery coordinators ──────────────────────────────────────────
    bat_coords = []
    for bat in batteries:
        bat_dn_id = int(bat.get("dnId", 0))
        bat_dn    = bat.get("dn", "")
        bat_name  = bat.get("name", f"Battery {bat_dn_id}")
        if not bat_dn:
            _LOGGER.warning("Battery %s has no DN string — skipping", bat_dn_id)
            continue
        coord = BatteryCoordinator(
            hass=hass, api=api,
            dn_id=bat_dn_id, device_dn=bat_dn,
            device_name=bat_name,
        )
        await coord.async_config_entry_first_refresh()
        bat_coords.append(coord)
        _LOGGER.info("Set up battery: %s (%s)", bat_name, bat_dn_id)
    coordinators["batteries"] = bat_coords

    # ── Meter coordinators ────────────────────────────────────────────
    meter_coords = []
    for meter in meters:
        meter_dn_id = int(meter.get("dnId", 0))
        meter_dn    = meter.get("dn", "")
        meter_name  = meter.get("name", f"Grid meter {meter_dn_id}")
        if not meter_dn:
            _LOGGER.warning("Meter %s has no DN string — skipping", meter_dn_id)
            continue
        coord = MeterCoordinator(
            hass=hass, api=api,
            dn_id=meter_dn_id, device_dn=meter_dn,
            device_name=meter_name,
        )
        await coord.async_config_entry_first_refresh()
        meter_coords.append(coord)
        _LOGGER.info("Set up meter: %s (%s)", meter_name, meter_dn_id)
    coordinators["meters"] = meter_coords

    # ── Station coordinator ───────────────────────────────────────────
    station_coord: StationCoordinator | None = None
    station_dn_id: int | None = entry.data.get(CONF_STATION_DN_ID)

    if station_dn_id is None:
        try:
            stations = await api.get_station_list()
            if stations:
                first_station = stations[0]
                station_dn_id = int(first_station.get("dnId", 0)) or None
                station_name  = first_station.get("name", "Solar Plant")
                if station_dn_id:
                    hass.config_entries.async_update_entry(
                        entry,
                        data={
                            **entry.data,
                            CONF_STATION_DN_ID: station_dn_id,
                            CONF_STATION_NAME: station_name,
                        },
                    )
        except Exception as exc:
            _LOGGER.warning("Station discovery failed (non-fatal): %s", exc)

    if station_dn_id:
        station_coord = StationCoordinator(
            hass=hass, api=api,
            station_dn_id=int(station_dn_id),
            station_name=entry.data.get(CONF_STATION_NAME, "Solar Plant"),
        )
        await station_coord.async_config_entry_first_refresh()
    coordinators["station"] = station_coord

    # ── Store user info (for start-charge accountId) ──────────────────
    try:
        user_info = await api.get_user_info()
        coordinators["user_id"] = str(user_info.get("userId", ""))
    except Exception:
        coordinators["user_id"] = ""

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinators

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def _discover_gun_dn_id(
    api: FusionSolarApi, charger_dn_id: int, all_devices: list[dict]
) -> int:
    """Find the gun/connector child dnId. Falls back to parent dnId."""
    try:
        # Find the charger's DN string from the already-fetched device list
        our_device = next(
            (d for d in all_devices if int(d.get("dnId", 0)) == charger_dn_id), None
        )
        if our_device:
            parent_dn = our_device.get("dn", "")
            if parent_dn:
                children = await api.get_children_list(parent_dn, MOC_EV_CHARGER_GUN)
                if children:
                    gun_dn_id = int(children[0].get("dnId", 0))
                    if gun_dn_id:
                        return gun_dn_id
    except Exception as exc:
        _LOGGER.warning("Gun dnId discovery failed for %s: %s", charger_dn_id, exc)
    return charger_dn_id
