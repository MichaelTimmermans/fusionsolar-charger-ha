"""
FusionSolar App HA — DataUpdateCoordinators.

ChargerCoordinator   — EV charger, 30s
InverterCoordinator  — Solar inverter, 30s (device-real-kpi via pvms)
BatteryCoordinator   — Battery / LUNA2000, 30s (device-real-kpi via pvms)
MeterCoordinator     — Grid meter, 30s (device-real-kpi via pvms)
StationCoordinator   — Plant KPIs, 5min (station-real-kpi)
"""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FusionSolarApi, FusionSolarApiError, FusionSolarAuthError
from .const import (
    BATTERY_SIGNAL_IDS,
    BATTERY_STATUS_MAP,
    CHARGER_SIGNAL_STATUS_MAP,
    CHARGER_STATUS_MAP,
    DOMAIN,
    GUN_CONFIG_SIGNAL_IDS,
    INVERTER_SIGNAL_IDS,
    INVERTER_STATUS_MAP,
    METER_SIGNAL_IDS,
    PARENT_CONFIG_SIGNAL_IDS,
    PARENT_REALTIME_SIGNAL_IDS,
    SCAN_INTERVAL,
    SCAN_INTERVAL_STATION,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EV Charger Coordinator
# ---------------------------------------------------------------------------

class ChargerCoordinator(DataUpdateCoordinator):
    """
    Polls the EV charger every 30s.

    data keys:
      status_code, signal_status
      charging_power (W), charging_voltage (V), charging_current (A)
      session_energy (kWh), session_duration_s (str), session_duration_min (float)
      total_energy_kwh (kWh lifetime)
      order_number, serial_number (needed for stop-charge)
      account_id (from process data, needed for start-charge)
      max_current (A), working_mode, max_grid_power (kW)
      surplus_power_start (kW), phase_switch, locking_mode
      max_power_limit (kW), networking_mode, charger_alias, wifi_signal (dBm)
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
            # 1. Rich status (realtime-info on parent)
            rt = await self.api.get_realtime_signals(self.dn_id, PARENT_REALTIME_SIGNAL_IDS)
            status_sig = rt.get(2101519, {})
            signal_status = (
                status_sig.get("realValue")
                or CHARGER_SIGNAL_STATUS_MAP.get(status_sig.get("value", ""), "")
            )

            # 2. Basic status integer
            cs = await self.api.get_charger_status(self.dn_id)
            status_code = _to_int(cs.get("chargeStatus"), -1)
            if not signal_status:
                signal_status = CHARGER_STATUS_MAP.get(status_code, "Unknown")

            # 3. Live session data (query-process-data)
            # ChargingData fields are nested {value, unit} objects per APK
            process = await self.api.get_charging_process_data(self.dn_id)
            charging_power   = _nested_float(process, "chargingPower")
            charging_voltage = _nested_float(process, "chargingVoltage")
            charging_current = _nested_float(process, "chargingCurrent")
            session_energy   = _nested_float(process, "chargedEnergy")
            session_duration = _nested_float(process, "chargedTime")  # seconds or minutes

            # Format duration as string and keep raw value
            session_duration_str = _format_duration(session_duration)

            order_number  = process.get("orderNumber", "")
            serial_number = process.get("serialNumber", "")
            process_account_id = str(process.get("accountId", ""))

            # 4. Gun config-info (settings + lifetime energy)
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
            total_energy_kwh    = total_energy_wh / 1000.0 if total_energy_wh is not None else None

            # 5. Parent config-info (semi-static settings)
            parent_cfg = await self.api.get_config_signals(
                self.dn_id, PARENT_CONFIG_SIGNAL_IDS
            )
            max_power_limit = _sig_float(parent_cfg, 20001)
            networking_mode = parent_cfg.get(20014, {}).get("realValue", "")
            charger_alias   = parent_cfg.get(20015, {}).get("realValue", "")
            wifi_signal     = _sig_float(parent_cfg, 2101518)

            return {
                "status_code":          status_code,
                "signal_status":        signal_status,
                "charging_power":       charging_power,
                "charging_voltage":     charging_voltage,
                "charging_current":     charging_current,
                "session_energy":       session_energy,
                "session_duration_s":   session_duration_str,
                "session_duration_min": session_duration,
                "total_energy_kwh":     total_energy_kwh,
                "order_number":         order_number,
                "serial_number":        serial_number,
                "account_id":           process_account_id,
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


# ---------------------------------------------------------------------------
# Inverter Coordinator
# ---------------------------------------------------------------------------

class InverterCoordinator(DataUpdateCoordinator):
    """
    Polls an inverter every 30s via pvms device-real-kpi.

    data keys:
      active_power (W), running_status (str)
      daily_energy (kWh), month_energy (kWh), year_energy (kWh)
      grid_voltage_a/b/c (V), grid_current_a/b/c (A)
      temperature (°C)
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: FusionSolarApi,
        dn_id: int,
        device_dn: str,
        device_name: str,
    ) -> None:
        super().__init__(
            hass, _LOGGER,
            name=f"{DOMAIN}_inverter_{dn_id}",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.api = api
        self.dn_id = dn_id
        self.device_dn = device_dn
        self.device_name = device_name

    async def _async_update_data(self) -> dict:
        try:
            raw = await self.api.get_device_real_kpi(self.device_dn, INVERTER_SIGNAL_IDS)
            _LOGGER.debug("Inverter %s KPI: %s", self.dn_id, raw)

            status_code = _to_int(_kpi_val(raw, 10025), -1)

            return {
                "active_power":    _kpi_float(raw, 10018),
                "running_status":  INVERTER_STATUS_MAP.get(status_code, f"Unknown ({status_code})"),
                "running_status_code": status_code,
                "daily_energy":    _kpi_float(raw, 10032),
                "month_energy":    _kpi_float(raw, 10033),
                "year_energy":     _kpi_float(raw, 10034),
                "grid_voltage_a":  _kpi_float(raw, 10011),
                "grid_voltage_b":  _kpi_float(raw, 10012),
                "grid_voltage_c":  _kpi_float(raw, 10013),
                "grid_current_a":  _kpi_float(raw, 10014),
                "grid_current_b":  _kpi_float(raw, 10015),
                "grid_current_c":  _kpi_float(raw, 10016),
                "temperature":     _kpi_float(raw, 10029),
            }
        except FusionSolarAuthError as exc:
            raise UpdateFailed(f"Auth error: {exc}") from exc
        except FusionSolarApiError as exc:
            raise UpdateFailed(f"API error: {exc}") from exc


# ---------------------------------------------------------------------------
# Battery Coordinator
# ---------------------------------------------------------------------------

class BatteryCoordinator(DataUpdateCoordinator):
    """
    Polls a LUNA2000 battery every 30s.

    data keys:
      battery_power (W, positive=charging, negative=discharging)
      voltage (V), running_status (str)
      charge_capacity (kWh), discharge_capacity (kWh)
      charge_mode (str)
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: FusionSolarApi,
        dn_id: int,
        device_dn: str,
        device_name: str,
    ) -> None:
        super().__init__(
            hass, _LOGGER,
            name=f"{DOMAIN}_battery_{dn_id}",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.api = api
        self.dn_id = dn_id
        self.device_dn = device_dn
        self.device_name = device_name

    async def _async_update_data(self) -> dict:
        try:
            raw = await self.api.get_device_real_kpi(self.device_dn, BATTERY_SIGNAL_IDS)
            _LOGGER.debug("Battery %s KPI: %s", self.dn_id, raw)

            status_code = _to_int(_kpi_val(raw, 10003), -1)
            charge_mode_code = _to_int(_kpi_val(raw, 10008), -1)
            charge_mode_map = {0: "None", 1: "Forced charge", 2: "Forced discharge"}

            return {
                "battery_power":      _kpi_float(raw, 10004),
                "voltage":            _kpi_float(raw, 10005),
                "running_status":     BATTERY_STATUS_MAP.get(status_code, f"Unknown ({status_code})"),
                "running_status_code": status_code,
                "charge_capacity":    _kpi_float(raw, 10001),
                "discharge_capacity": _kpi_float(raw, 10002),
                "charge_mode":        charge_mode_map.get(charge_mode_code, str(charge_mode_code)),
            }
        except FusionSolarAuthError as exc:
            raise UpdateFailed(f"Auth error: {exc}") from exc
        except FusionSolarApiError as exc:
            raise UpdateFailed(f"API error: {exc}") from exc


# ---------------------------------------------------------------------------
# Grid Meter Coordinator
# ---------------------------------------------------------------------------

class MeterCoordinator(DataUpdateCoordinator):
    """
    Polls a grid meter every 30s.

    data keys:
      active_power (W), active_energy (kWh), reverse_energy (kWh)
      voltage_a (V), current_a (A), status (str)
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: FusionSolarApi,
        dn_id: int,
        device_dn: str,
        device_name: str,
    ) -> None:
        super().__init__(
            hass, _LOGGER,
            name=f"{DOMAIN}_meter_{dn_id}",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.api = api
        self.dn_id = dn_id
        self.device_dn = device_dn
        self.device_name = device_name

    async def _async_update_data(self) -> dict:
        try:
            raw = await self.api.get_device_real_kpi(self.device_dn, METER_SIGNAL_IDS)
            _LOGGER.debug("Meter %s KPI: %s", self.dn_id, raw)

            return {
                "active_power":    _kpi_float(raw, 10004),
                "active_energy":   _kpi_float(raw, 10008),
                "reverse_energy":  _kpi_float(raw, 10009),
                "voltage_a":       _kpi_float(raw, 10002),
                "current_a":       _kpi_float(raw, 10003),
                "status":          _kpi_val(raw, 10001),
            }
        except FusionSolarAuthError as exc:
            raise UpdateFailed(f"Auth error: {exc}") from exc
        except FusionSolarApiError as exc:
            raise UpdateFailed(f"API error: {exc}") from exc


# ---------------------------------------------------------------------------
# Station Coordinator
# ---------------------------------------------------------------------------

class StationCoordinator(DataUpdateCoordinator):
    """Polls the solar plant every 5 minutes."""

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
                    }

            # Fallback to station-list
            stations = await self.api.get_station_list()
            for s in stations:
                if int(s.get("dnId", -1)) == self.station_dn_id:
                    return {
                        "current_power":     _to_float(s.get("currentPower")),
                        "daily_energy":      _to_float(s.get("dailyEnergy")),
                        "cumulative_energy": _to_float(s.get("cumulativeEnergy")),
                        "month_energy":      _to_float(s.get("monthEnergy")),
                        "year_energy":       _to_float(s.get("yearEnergy")),
                        "daily_self_use":    _to_float(s.get("dailySelfUseEnergy")),
                        "daily_use":         _to_float(s.get("dailyUseEnergy")),
                    }
            return {}

        except FusionSolarAuthError as exc:
            raise UpdateFailed(f"Auth error: {exc}") from exc
        except FusionSolarApiError as exc:
            raise UpdateFailed(f"API error: {exc}") from exc


# Backwards-compat alias
FusionSolarCoordinator = ChargerCoordinator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_float(value: object) -> float | None:
    if value in (None, "", "--"):
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


def _nested_float(data: dict, key: str) -> float | None:
    """
    Extract float from nested {value, unit} structure used in ChargingData.
    Falls back to plain value if not nested.
    """
    val = data.get(key)
    if isinstance(val, dict):
        return _to_float(val.get("value"))
    return _to_float(val)


def _kpi_val(raw: dict, signal_id: int) -> Any:
    """Get raw value from device-real-kpi response (keyed by signal ID string)."""
    entry = raw.get(str(signal_id)) or raw.get(signal_id, {})
    if isinstance(entry, dict):
        return entry.get("value") or entry.get("realValue")
    return entry


def _kpi_float(raw: dict, signal_id: int) -> float | None:
    return _to_float(_kpi_val(raw, signal_id))


def _format_duration(seconds: float | None) -> str:
    """Format seconds into human-readable duration string."""
    if seconds is None:
        return ""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    hours = s // 3600
    minutes = (s % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes:02d}min"
    return f"{minutes}min"
