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


class ChargerCoordinator(DataUpdateCoordinator):
    """
    Polls the EV charger every 30s.

    data dict keys:
      status_code           int   — chargeStatus integer
      signal_status         str   — rich label from signal 2101519
      charging_power        float — kW (from query-process-data)
      charging_voltage      float — V
      charging_current      float — A
      session_energy        float — kWh (current session)
      session_duration_str  str   — formatted duration (e.g. 1u32)
      session_start_time    int   — epoch ms
      total_energy_kwh      float — kWh lifetime (signal 10036 ÷ 1000)
      max_current           float — A (signal 20003)
      working_mode          str   — Normal/PV Preferred (signal 20002)
      max_grid_power        float — kW (signal 20006)
      surplus_power_start   float — kW (signal 20007)
      phase_switch          str   — Enable/Disable (signal 20004)
      locking_mode          str   — (signal 20005)
      max_power_limit       float — kW (signal 20001 from parent)
      networking_mode       str   — FE/WIFI (signal 20014)
      charger_alias         str   — user name (signal 20015)
      wifi_signal           float — dBm (signal 2101518)
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
        self._gun_signal_ids: list[int] | None = None

    async def _async_update_data(self) -> dict:
        try:
            # ── 1. Rich status via realtime-info (parent dnId) ────────
            rt = await self.api.get_realtime_signals(
                self.dn_id, PARENT_REALTIME_SIGNAL_IDS
            )
            status_sig = rt.get(2101519, {})
            signal_status = (
                status_sig.get("realValue")
                or CHARGER_SIGNAL_STATUS_MAP.get(status_sig.get("value", ""), "")
            )
            wifi_signal = _to_float(rt.get(2101518, {}).get("realValue"))

            # ── 2. Basic status (parent dnId) ─────────────────────────
            cs = await self.api.get_charger_status(self.dn_id)
            status_code = _to_int(cs.get("chargeStatus"), -1)

            if not signal_status:
                signal_status = CHARGER_STATUS_MAP.get(status_code, "Unknown")

            # ── 3. Live session data via query-process-data ───────────
            process = await self.api.get_charging_process_data(self.dn_id)
            _LOGGER.debug("query-process-data response: %s", process)

            # Extract nested 'value' from the JSON structure
            charging_power   = _to_float_from_dict(process.get("chargingPower"))
            charging_voltage = _to_float_from_dict(process.get("chargingVoltage"))
            charging_current = _to_float_from_dict(process.get("chargingCurrent"))
            session_energy   = _to_float_from_dict(process.get("chargedEnergy"))
            
            # Duration formatting: 92 -> 1u32
            raw_duration = _to_float_from_dict(process.get("chargedTime"))
            session_duration_str = "Unknown"
            if raw_duration is not None:
                hours = int(raw_duration // 60)
                minutes = int(raw_duration % 60)
                if hours > 0:
                    session_duration_str = f"{hours}u{minutes:02d}"
                else:
                    session_duration_str = f"{minutes}Min"

            session_start = process.get("startTime")

            # ── 4. Gun config-info (settings + lifetime energy) ───────
            if self._gun_signal_ids is None:
                gun_all = await self.api.get_config_signals(
                    self.gun_dn_id, [], query_all=True
                )
                self._gun_signal_ids = list(gun_all.keys())
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
            total_energy_wh     = _sig_float(gun_cfg, 10036)
            total_energy_kwh    = (
                total_energy_wh / 1000.0 if total_energy_wh is not None else None
            )

            # ── 5. Parent config-info (semi-static settings) ──────────
            parent_cfg = await self.api.get_config_signals(
                self.dn_id, PARENT_CONFIG_SIGNAL_IDS
            )
            max_power_limit  = _sig_float(parent_cfg, 20001)
            networking_mode  = parent_cfg.get(20014, {}).get("realValue", "")
            charger_alias    = parent_cfg.get(20015, {}).get("realValue", "")

            return {
                "status_code":          status_code,
                "signal_status":        signal_status,
                "charging_power":       charging_power,
                "charging_voltage":     charging_voltage,
                "charging_current":     charging_current,
                "session_energy":       session_energy,
                "session_duration_s":   session_duration_str, # Gebruikt voor weergave
                "session_start_time":   session_start,
                "total_energy_kwh":     total_energy_kwh,
                "max_current":          max_current,
                "working_mode":         working_mode,
                "max_grid_power":       max_grid_power,
                "surplus_power_start":  surplus_power_start,
                "phase_switch":         phase_switch,
                "locking_mode":         locking_mode,
                "max_power_limit":      max_power_limit,
                "networking_mode":      networking_mode,
                "charger_alias":        charger_alias,
                "wifi_signal":          wifi_signal,
            }

        except FusionSolarAuthError as exc:
            raise UpdateFailed(f"Auth error: {exc}") from exc
        except FusionSolarApiError as exc:
            raise UpdateFailed(f"API error: {exc}") from exc


class StationCoordinator(DataUpdateCoordinator):
    """
    Polls the solar plant every 5 minutes.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: FusionSolarApi,
        station_dn_id: int,
        station_name: str,
        station_dn: str = "",
    ) -> None:
        super().__init__(
            hass, _LOGGER,
            name=f"{DOMAIN}_station_{station_dn_id}",
            update_interval=timedelta(seconds=SCAN_INTERVAL_STATION),
        )
        self.api = api
        self.station_dn_id = station_dn_id
        self.station_name = station_name
        self._station_dn = station_dn

    async def _async_update_data(self) -> dict:
        try:
            if not self._station_dn:
                self._station_dn = await self.api.get_station_dn(self.station_dn_id) or ""

            if self._station_dn:
                kpi = await self.api.get_station_real_kpi(self._station_dn)
                if kpi:
                    return {
                        "current_power":     _to_float(kpi.get("currentPower")),
                        "daily_energy":      _to_float(kpi.get("dailyEnergy")),
                        "cumulative_energy": _to_float(kpi.get("cumulativeEnergy")),
                        "month_energy":      _to_float(kpi.get("monthEnergy")),
                        "year_energy":       _to_float(kpi.get("yearEnergy")),
                        "daily_self_use":    _to_float(kpi.get("dailySelfUseEnergy")),
                        "daily_use":         _to_float(kpi.get("dailyUseEnergy")),
                        "daily_on_grid":     None,
                        "daily_buy":         None,
                        "battery_capacity":  None,
                        "battery_power":     None,
                        "plant_status":      None,
                        "installed_capacity": None,
                        "eq_power_hours":    None,
                    }

            stations = await self.api.get_station_list()
            station: dict = {}
            for s in stations:
                if int(s.get("dnId", -1)) == self.station_dn_id:
                    station = s
                    break

            if not station:
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

        except FusionSolarAuthError as exc:
            raise UpdateFailed(f"Auth error: {exc}") from exc
        except FusionSolarApiError as exc:
            raise UpdateFailed(f"API error: {exc}") from exc


class DiagnosticsCoordinator(DataUpdateCoordinator):
    """Fires at startup to log query-process-data response during charging."""

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
            _LOGGER.warning("[DIAG] charge-status: %s", cs)

            proc = await self.api.get_charging_process_data(self.dn_id)
            _LOGGER.warning("[DIAG] query-process-data: %s", proc)

        except Exception as exc:
            _LOGGER.warning("[DIAG] Error: %s", exc)
        return {}


FusionSolarCoordinator = ChargerCoordinator


def _to_float(value: object) -> float | None:
    if value is None or value == "" or value == "--":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _to_float_from_dict(data: object) -> float | None:
    """Helper to extract 'value' from nested dicts like {'value': 4.891, 'unit': 'kWh'}"""
    if isinstance(data, dict):
        return _to_float(data.get("value"))
    return _to_float(data)

def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _sig_float(signals: dict, signal_id: int) -> float | None:
    s = signals.get(signal_id, {})
    return _to_float(s.get("realValue") or s.get("value"))