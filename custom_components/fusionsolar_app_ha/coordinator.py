"""
FusionSolar App HA — DataUpdateCoordinators.

Signal routing (confirmed from queryAll DIAG):

  PARENT dnId — config-info:
    20001   Dynamic Charging Power limit (kW)
    20014   Networking Mode (FE/WIFI)
    20015   Alias (user-set name)
    2101518 WiFi Signal Strength (dBm)
    2101519 Rich charger status enum

  GUN dnId — config-info (queryAll=True for live session data):
    20002   Working Mode
    20003   Maximum Charge Current (A)
    20004   Phase Switch
    20005   Connector Locking Mode
    20006   Max Charging Power from Grid (kW)
    20007   Surplus Power to Start Charging (kW)
    10030   Expected Charged Energy (kWh) — session target
    10035   Charging Duration — live session
    10036   Energy Charged (Wh) — lifetime total (8901 Wh = 8.9 kWh confirmed)
    + live charging power signal TBD (will appear during active session)

  PARENT dnId — charge-status:
    chargeStatus  int (0-11)
"""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FusionSolarApi, FusionSolarApiError, FusionSolarAuthError
from .const import (
    CHARGER_SIGNAL_STATUS_MAP,
    CHARGER_STATUS_MAP,
    DOMAIN,
    GUN_CONFIG_SIGNAL_IDS,
    PARENT_CONFIG_SIGNAL_IDS,
    PARENT_REALTIME_SIGNAL_IDS,
    SCAN_INTERVAL,
    SCAN_INTERVAL_STATION,
)

_LOGGER = logging.getLogger(__name__)

# GUN signals that represent live session data (only meaningful during charging)
_SESSION_SIGNAL_IDS = {10027, 10030, 10035}


class ChargerCoordinator(DataUpdateCoordinator):
    """
    Polls the EV charger every 30s.

    data dict keys:
      status_code             int
      status_label            str   — basic (Available/Charging/etc.)
      signal_status           str   — rich from signal 2101519
      max_power_limit         float — kW, signal 20001
      networking_mode         str   — FE/WIFI, signal 20014
      charger_alias           str   — user-set name, signal 20015
      wifi_signal             float — dBm, signal 2101518
      working_mode            str   — Normal/PV Preferred, signal 20002
      max_current             float — A, signal 20003
      phase_switch            str   — Enable/Disable, signal 20004
      locking_mode            str   — signal 20005
      max_grid_power          float — kW, signal 20006
      surplus_power_start     float — kW, signal 20007
      session_target_energy   float — kWh, signal 10030
      charging_duration       float — signal 10035 (unit TBD)
      total_energy_wh         float — Wh lifetime, signal 10036
      total_energy_kwh        float — kWh lifetime (10036 / 1000)
      charge_power            float — W (live, TBD signal ID)
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: FusionSolarApi,
        dn_id: int,
        gun_dn_id: int,
        device_name: str,
    ) -> None:
        super().__init__(
            hass, _LOGGER,
            name=f"{DOMAIN}_charger_{dn_id}",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.api = api
        self.dn_id = dn_id
        self.gun_dn_id = gun_dn_id
        self.device_name = device_name
        # Cache of all gun signal IDs discovered via queryAll
        # Will be populated on first run and used for targeted polling
        self._gun_signal_ids: list[int] | None = None

    async def _async_update_data(self) -> dict:
        try:
            # ── 1. Rich status (fastest — realtime on parent) ─────────
            rt = await self.api.get_realtime_signals(
                self.dn_id, PARENT_REALTIME_SIGNAL_IDS
            )
            status_sig = rt.get(2101519, {})
            raw_val = status_sig.get("value", "")
            signal_status = (
                status_sig.get("realValue")
                or CHARGER_SIGNAL_STATUS_MAP.get(raw_val, "")
            )

            # ── 2. Charge-status (basic status integer) ───────────────
            cs = await self.api.get_charger_status(self.dn_id)
            status_code = _to_int(cs.get("chargeStatus"), -1)

            # ── 3. Parent config-info (semi-static settings) ──────────
            parent_cfg = await self.api.get_config_signals(
                self.dn_id, PARENT_CONFIG_SIGNAL_IDS
            )
            max_power_limit = _sig_float(parent_cfg, 20001)
            networking_mode = parent_cfg.get(20014, {}).get("realValue", "")
            charger_alias   = parent_cfg.get(20015, {}).get("realValue", "")
            wifi_signal     = _sig_float(parent_cfg, 2101518)

            # ── 4. Gun config-info queryAll (live session + settings) ─
            # First run: discover all available signal IDs
            if self._gun_signal_ids is None:
                gun_all = await self.api.get_config_signals(
                    self.gun_dn_id, [], query_all=True
                )
                self._gun_signal_ids = list(gun_all.keys())
                _LOGGER.info(
                    "Discovered %d gun signal IDs: %s",
                    len(self._gun_signal_ids), self._gun_signal_ids,
                )
                gun_cfg = gun_all
            else:
                gun_cfg = await self.api.get_config_signals(
                    self.gun_dn_id, self._gun_signal_ids
                )

            working_mode        = gun_cfg.get(20002, {}).get("realValue", "")
            max_current         = _sig_float(gun_cfg, 20003)
            phase_switch        = gun_cfg.get(20004, {}).get("realValue", "")
            locking_mode        = gun_cfg.get(20005, {}).get("realValue", "")
            max_grid_power      = _sig_float(gun_cfg, 20006)
            surplus_power_start = _sig_float(gun_cfg, 20007)
            session_target      = _sig_float(gun_cfg, 10030)
            charging_duration   = _sig_float(gun_cfg, 10035)
            total_energy_wh     = _sig_float(gun_cfg, 10036)
            total_energy_kwh    = (
                total_energy_wh / 1000.0 if total_energy_wh is not None else None
            )

            # Live charging power — scan all gun signals for likely power signal
            # (signal ID TBD, will be non-zero during active charging)
            charge_power = _find_charging_power(gun_cfg, status_code)

            # Log any unknown non-zero signals during charging for power discovery
            if status_code in (2, 3, 8, 11) and _LOGGER.isEnabledFor(logging.DEBUG):
                for sid, s in gun_cfg.items():
                    if sid not in GUN_CONFIG_SIGNAL_IDS and s.get("realValue") not in (
                        None, "", "0", "0.0",
                    ):
                        _LOGGER.debug(
                            "Gun signal during charging — id=%s name=%r "
                            "realValue=%r unit=%r",
                            sid, s.get("name"), s.get("realValue"), s.get("unit"),
                        )

            return {
                "status_code":          status_code,
                "status_label":         CHARGER_STATUS_MAP.get(status_code, "Unknown"),
                "signal_status":        signal_status or CHARGER_STATUS_MAP.get(status_code, "Unknown"),
                "max_power_limit":      max_power_limit,
                "networking_mode":      networking_mode,
                "charger_alias":        charger_alias,
                "wifi_signal":          wifi_signal,
                "working_mode":         working_mode,
                "max_current":          max_current,
                "phase_switch":         phase_switch,
                "locking_mode":         locking_mode,
                "max_grid_power":       max_grid_power,
                "surplus_power_start":  surplus_power_start,
                "session_target_energy": session_target,
                "charging_duration":    charging_duration,
                "total_energy_kwh":     total_energy_kwh,
                "charge_power":         charge_power,
            }

        except FusionSolarAuthError as exc:
            raise UpdateFailed(f"Auth error: {exc}") from exc
        except FusionSolarApiError as exc:
            raise UpdateFailed(f"API error: {exc}") from exc


class StationCoordinator(DataUpdateCoordinator):
    """Polls the solar plant every 5 minutes via station-list."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: FusionSolarApi,
        station_dn_id: int,
        station_name: str,
    ) -> None:
        super().__init__(
            hass, _LOGGER,
            name=f"{DOMAIN}_station_{station_dn_id}",
            update_interval=timedelta(seconds=SCAN_INTERVAL_STATION),
        )
        self.api = api
        self.station_dn_id = station_dn_id
        self.station_name = station_name

    async def _async_update_data(self) -> dict:
        try:
            stations = await self.api.get_station_list()
        except FusionSolarAuthError as exc:
            raise UpdateFailed(f"Auth error: {exc}") from exc
        except FusionSolarApiError as exc:
            raise UpdateFailed(f"API error: {exc}") from exc

        station: dict = {}
        for s in stations:
            if int(s.get("dnId", -1)) == self.station_dn_id:
                station = s
                break

        if not station:
            _LOGGER.warning("Station %s not in station-list", self.station_dn_id)
            return {}

        return {
            "current_power":      _to_float(station.get("currentPower")),
            "daily_energy":       _to_float(station.get("dailyEnergy")),
            "daily_on_grid":      _to_float(station.get("dailyOnGridEnergy")),
            "daily_buy":          _to_float(station.get("dailyBuyEnergy")),
            "daily_use":          _to_float(station.get("dailyUseEnergy")),
            "daily_self_use":     _to_float(station.get("dailySelfUseEnergy")),
            "month_energy":       _to_float(station.get("monthEnergy")),
            "year_energy":        _to_float(station.get("yearEnergy")),
            "cumulative_energy":  _to_float(station.get("cumulativeEnergy")),
            "battery_capacity":   _to_float(station.get("batteryCapacity")),
            "battery_power":      _to_float(station.get("energyStoragePower")),
            "plant_status":       station.get("plantStatus"),
            "installed_capacity": _to_float(station.get("installedCapacity")),
            "eq_power_hours":     _to_float(station.get("eqPowerHours")),
        }


class DiagnosticsCoordinator(DataUpdateCoordinator):
    """
    Fires once at startup. Logs all gun signals during charging to
    identify the live power signal ID. Remove after debugging is complete.
    """

    def __init__(self, hass, api, dn_id, gun_dn_id, device_name):
        super().__init__(
            hass, _LOGGER,
            name=f"{DOMAIN}_diag_{dn_id}",
            update_interval=timedelta(seconds=30),
        )
        self.api = api
        self.dn_id = dn_id
        self.gun_dn_id = gun_dn_id
        self.device_name = device_name

    async def _async_update_data(self) -> dict:
        try:
            cs = await self.api.get_charger_status(self.dn_id)
            status = cs.get("chargeStatus", 0)
            _LOGGER.warning("[DIAG] charge-status: %s", cs)

            # Only log all gun signals when actively charging
            if status in (2, 3, 8, 11):
                gun_all = await self.api.get_config_signals(
                    self.gun_dn_id, [], query_all=True
                )
                _LOGGER.warning(
                    "[DIAG] CHARGING — gun queryAll returned %d signals:", len(gun_all)
                )
                for sid, s in gun_all.items():
                    _LOGGER.warning(
                        "[DIAG] CHARGING gun %s: name=%r realValue=%r unit=%r",
                        sid, s.get("name"), s.get("realValue"), s.get("unit"),
                    )
            else:
                _LOGGER.warning(
                    "[DIAG] Not charging (status=%s) — skipping gun dump", status
                )
        except Exception as exc:
            _LOGGER.warning("[DIAG] Error: %s", exc)
        return {}


FusionSolarCoordinator = ChargerCoordinator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_float(value: object) -> float | None:
    if value is None or value == "" or value == "--":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _sig_float(signals: dict, signal_id: int) -> float | None:
    s = signals.get(signal_id, {})
    return _to_float(s.get("realValue") or s.get("value"))


def _find_charging_power(gun_cfg: dict, status_code: int) -> float | None:
    """
    Attempt to find the live charging power signal from all gun signals.
    The signal ID is not yet known — this scans for numeric kW/W signals
    with non-zero values during active charging.
    Known non-power signals are excluded.
    Returns power in Watts (converted from kW if needed).
    """
    if status_code not in (2, 3, 8, 11):
        return None

    _EXCLUDE = {
        20002, 20003, 20004, 20005, 20006, 20007, 20009,
        10036,  # lifetime energy Wh
    }

    candidates = []
    for sid, s in gun_cfg.items():
        if sid in _EXCLUDE:
            continue
        unit = (s.get("unit") or "").lower()
        name = (s.get("name") or "").lower()
        val = _to_float(s.get("realValue"))
        if val is None or val <= 0:
            continue
        if "power" in name or unit in ("w", "kw"):
            candidates.append((sid, val, unit, name))
            _LOGGER.debug(
                "Power candidate: signal %s name=%r val=%s unit=%s",
                sid, name, val, unit,
            )

    if not candidates:
        return None

    # Return the first kW candidate converted to W, or W candidate directly
    for sid, val, unit, name in candidates:
        if unit == "kw":
            return val * 1000
        if unit == "w":
            return val
    return None
