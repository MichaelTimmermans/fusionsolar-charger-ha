"""
Constants for FusionSolar App HA.

All signal IDs and device types confirmed from APK decompilation:
  DevStdSignal.java, InverterSamplingSignal.java, EnergyStoreSamplingSignal.java,
  HemsConfigSignal.java, DeviceLevelThreeMocTypeEnum.java, ChargingData.java
"""

DOMAIN = "fusionsolar_app_ha"

# Auth — always this URL regardless of region
AUTH_URL = (
    "https://intl.fusionsolar.huawei.com:32800"
    "/rest/neteco/appauthen/v1/smapp/app/token"
)
APP_CLIENT_ID = "86366133-B8B5-41FA-8EB9-E5A64229E3E1"

# Config entry keys
CONF_API_BASE = "api_base"
CONF_STATION_DN_ID = "station_dn_id"
CONF_STATION_NAME = "station_name"
CONF_STATION_DN = "station_dn"
CONF_DEVICE_DN_ID = "device_dn_id"
CONF_DEVICE_NAME = "device_name"
CONF_GUN_DN_ID = "gun_dn_id"

# Regional servers
REGION_SERVERS = {
    "Auto-detect (recommended)": "https://uni001eu5.fusionsolar.huawei.com",
    "Europe (uni001eu5)": "https://uni001eu5.fusionsolar.huawei.com",
    "Germany (region01eu5)": "https://region01eu5.fusionsolar.huawei.com",
    "North America (region01na5)": "https://region01na5.fusionsolar.huawei.com",
    "China (region01cn5)": "https://region01cn5.fusionsolar.huawei.com",
    "Asia Pacific (region01ap5)": "https://region01ap5.fusionsolar.huawei.com",
    "International (intl)": "https://intl.fusionsolar.huawei.com",
}
DEFAULT_API_BASE = "https://uni001eu5.fusionsolar.huawei.com:32800"

# Polling intervals (seconds)
SCAN_INTERVAL = 30          # charger, inverter live data
SCAN_INTERVAL_STATION = 300 # station KPIs

TOKEN_RENEWAL_MARGIN = 300

# ── Device mocType IDs (from APK DeviceLevelThreeMocTypeEnum + device-list usage) ──
MOC_INVERTER_STRING      = 1     # String inverter
MOC_SMARTLOGGER          = 2     # SmartLogger
MOC_GRID_METER           = 17    # Grid meter
MOC_INVERTER_RESIDENTIAL = 38    # Residential inverter (SUN2000-L)
MOC_BATTERY              = 39    # Battery / LUNA2000
MOC_BACKUP_BOX           = 40    # Backup box
MOC_POWER_SENSOR         = 47    # Power sensor
MOC_DONGLE               = 62    # Dongle / SmartDongle
MOC_EV_CHARGER           = 60080 # EV charger (ChargeONE parent)
MOC_EV_CHARGER_GUN       = 60081 # EV charger gun/connector (child)

# Device types that use pvms device-real-kpi endpoint
MOC_TYPES_PVMS = {
    MOC_INVERTER_STRING, MOC_INVERTER_RESIDENTIAL,
    MOC_BATTERY, MOC_GRID_METER, MOC_POWER_SENSOR,
}

# ── Charger status maps ───────────────────────────────────────────────────────
CHARGER_STATUS_MAP = {
    0: "Available", 1: "Preparing", 2: "Charging",
    3: "Suspended EV", 4: "Suspended EVSE", 5: "Finishing",
    6: "Reserved", 7: "Unavailable", 8: "Faulted", 10: "PV power — waiting",
}

# Signal 2101519 enum values (confirmed from live DIAG + APK)
CHARGER_SIGNAL_STATUS_MAP = {
    "0": "No car connected", "1": "Standby",
    "2": "Timed charging — waiting", "3": "Charging",
    "4": "Charging complete", "5": "Faulted",
    "6": "Orderly charging — waiting", "7": "Upgrading",
    "8": "Starting charging", "9": "Alarm",
    "10": "PV power — waiting", "11": "PV power charging",
}

# ── Inverter running status (DevStdSignal.InverterSampling signal 10025) ──────
INVERTER_STATUS_MAP = {
    0: "Standby: initialising",
    256: "Starting",
    512: "On-grid",
    513: "Grid connection: power limited",
    514: "Grid connection: self-derating",
    768: "Shutdown: fault",
    769: "Shutdown: command",
    772: "Shutdown: power limited",
    1280: "Spot-check ready",
    1536: "Inspecting",
    2048: "I-V scanning",
    40960: "Standby: no irradiation",
}

# ── Battery running status (DevStdSignal.EnergyStoreSampling signal 10003) ───
BATTERY_STATUS_MAP = {
    0: "Offline", 1: "Standby", 2: "Running", 3: "Fault", 4: "Sleep mode",
}

# ── Charger signal IDs (confirmed from live DIAG output) ─────────────────────
# Parent dnId — get-config-info
PARENT_CONFIG_SIGNAL_IDS = [20001, 20010, 20012, 20014, 20015, 2101518, 2101519]
# Gun dnId — get-config-info (queryAll discovers all, but these are the known ones)
GUN_CONFIG_SIGNAL_IDS = [20002, 20003, 20004, 20005, 20006, 20007, 10030, 10035, 10036]
# Parent dnId — get-realtime-info
PARENT_REALTIME_SIGNAL_IDS = [2101519]

# ── Inverter signal IDs (DevStdSignal.InverterSampling) ──────────────────────
INVERTER_SIGNAL_IDS = [
    10018,  # Active power (W)
    10025,  # Running status
    10032,  # Daily energy (kWh)
    10033,  # Month energy (kWh)
    10034,  # Year energy (kWh)
    10011,  # Grid voltage A (V)
    10012,  # Grid voltage B (V)
    10013,  # Grid voltage C (V)
    10014,  # Grid current A (A)
    10015,  # Grid current B (A)
    10016,  # Grid current C (A)
    10029,  # Temperature (°C)
    10047,  # PV string count
]

# ── Battery signal IDs (DevStdSignal.EnergyStoreSampling) ────────────────────
BATTERY_SIGNAL_IDS = [
    10001,  # Charge capacity (kWh)
    10002,  # Discharge capacity (kWh)
    10003,  # Running status
    10004,  # Battery power (W) — positive=charge, negative=discharge
    10005,  # Voltage (V)
    10008,  # Charge mode
]

# ── Grid meter signal IDs (DevStdSignal.MeterSampling) ───────────────────────
METER_SIGNAL_IDS = [
    10004,  # Active power (W)
    10008,  # Active energy / grid export (kWh)
    10009,  # Reverse active energy / grid import (kWh)
    10001,  # Status
    10002,  # Voltage A (V)
    10003,  # Current A (A)
]

# ── Writable charger signal IDs (for set-config-info) ────────────────────────
# These can be written via POST /rest/neteco/web/homemgr/v1/device/set-config-info
# Payload: {conditions: [{dnId, signals: [{id, value}]}]}
WRITABLE_CHARGER_SIGNALS = {
    20001: "Dynamic Charging Power limit (kW)",     # parent dnId
    20003: "Max Charge Current (A)",                # gun dnId
    20006: "Max Grid Power (kW)",                   # gun dnId
    20007: "Surplus Power to Start Charging (kW)",  # gun dnId
    20002: "Working Mode (0=Normal, 1=PV Preferred)", # gun dnId
}
