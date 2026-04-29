"""Constants for the FusionSolar App HA integration."""

DOMAIN = "fusionsolar_app_ha"

AUTH_URL = "https://intl.fusionsolar.huawei.com:32800/rest/neteco/appauthen/v1/smapp/app/token"
APP_CLIENT_ID = "86366133-B8B5-41FA-8EB9-E5A64229E3E1"

CONF_API_BASE = "api_base"
CONF_STATION_DN_ID = "station_dn_id"
CONF_STATION_NAME = "station_name"

REGION_SERVERS = {
    "Auto-detect (recommended)": "https://uni001eu5.fusionsolar.huawei.com",
    "Europe 1 (eu1)": "https://region01eu5.fusionsolar.huawei.com",
    "Europe 2 (eu2)": "https://region02eu5.fusionsolar.huawei.com",
    "Europe 3 (eu3)": "https://region03eu5.fusionsolar.huawei.com",
    "Europe 4 (eu4)": "https://region04eu5.fusionsolar.huawei.com",
    "Europe 5 (eu5) — default": "https://uni001eu5.fusionsolar.huawei.com",
    "International (intl)": "https://intl.fusionsolar.huawei.com",
    "China (cn)": "https://intl.fusionsolar.huawei.com",
}
DEFAULT_API_BASE = "https://uni001eu5.fusionsolar.huawei.com:32800"

SCAN_INTERVAL = 30
SCAN_INTERVAL_STATION = 300
TOKEN_RENEWAL_MARGIN = 300

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_DEVICE_DN_ID = "device_dn_id"
CONF_DEVICE_NAME = "device_name"

# ── Signal map (confirmed from queryAll DIAG output) ──────────────────────────
#
# PARENT dnId — config-info (queryAll):
#   20001   Dynamic Charging Power        FLOAT  kW   (user-set limit)
#   20009   (rated power)                 FLOAT  kW
#   20010   AC Mode                       ENUM   (1-Phase / 3-Phase 4-Wire)
#   20011   System Category               STRING (ChargeONE)
#   20012   Rated Current Main Breaker    FLOAT  A
#   20013   Earthing System               ENUM   (TN/TT / IT)
#   20014   Networking Mode               ENUM   (FE / WIFI)
#   20015   Alias                         STRING (user-set name)
#   20016   AC Charger Type               ENUM
#   20017   LED Status                    UINT
#   2101518 WiFi Signal Strength          INT    dBm
#   2101519 Charger Status (rich)         ENUM   (No Car / Charging / PV Power / etc.)
#   538976533 TCP-Modbus Server IP        IPV4
#   538976534 TCP-Modbus Server Port      UINT
#   538976800 Expired Cert Communication  ENUM
#
# GUN dnId — config-info (queryAll, 44 signals):
#   20002   Working Mode                  ENUM   (Normal charge / PV Power Preferred)
#   20003   Maximum Charge Current        FLOAT  A
#   20004   Single/Three Phase Switch     ENUM   (Enable / Disable)
#   20005   Connector Locking Mode        ENUM
#   20006   Max Charging Power from Grid  FLOAT  kW
#   20007   Surplus Power to Start        FLOAT  kW
#   10027   Charging Mode                 (live session)
#   10030   Expected Charged Energy       FLOAT  kWh  (session target)
#   10035   Charging Duration             FLOAT  unit TBD (live session)
#   10036   Energy Charged                UINT   Wh   (lifetime total — 8901 = 8.9 kWh)
#   2101774 (internal)
#   + ~33 more TBD signals
#
# PARENT dnId — realtime-info:
#   2101518 WiFi Signal Strength          INT    dBm
#   2101519 Charger Status (rich)         ENUM
#   2101524 (internal)
#   2101525 (internal)
#   10100   (internal)
#
# NOTE: Live charging power signal ID not yet identified — will appear in
#       GUN queryAll during an active charging session.

# Signal IDs used in normal polling (not DIAG)
# Parent dnId — config-info (static/semi-static settings)
PARENT_CONFIG_SIGNAL_IDS = [
    20001,    # Dynamic Charging Power limit (kW)
    20010,    # AC Mode
    20012,    # Rated Current Main Breaker (A)
    20014,    # Networking Mode
    20015,    # Alias
    2101518,  # WiFi Signal Strength (dBm)
    2101519,  # Rich charger status
]

# Gun dnId — config-info (settings + live session data)
GUN_CONFIG_SIGNAL_IDS = [
    20002,  # Working Mode
    20003,  # Maximum Charge Current (A)
    20004,  # Phase Switch
    20005,  # Connector Locking Mode
    20006,  # Max Charging Power from Grid (kW)
    20007,  # Surplus Power to Start Charging (kW)
    10030,  # Expected Charged Energy (kWh) — session
    10035,  # Charging Duration — session
    10036,  # Energy Charged (Wh) — lifetime total
]

# Parent dnId — realtime-info (fastest-changing status)
PARENT_REALTIME_SIGNAL_IDS = [2101519]  # Rich status — all we need from realtime

# ── Status maps ───────────────────────────────────────────────────────────────
CHARGER_STATUS_MAP = {
    0: "Available", 1: "Preparing", 2: "Charging",
    3: "Suspended EV", 4: "Suspended EVSE", 5: "Finishing",
    6: "Reserved", 7: "Unavailable", 8: "Faulted", 10: "PV power — waiting",
}

CHARGER_SIGNAL_STATUS_MAP = {
    "0": "No car connected", "1": "Standby",
    "2": "Timed charging — waiting", "3": "Charging",
    "4": "Charging complete", "5": "Faulted",
    "6": "Orderly charging — waiting", "7": "Upgrading",
    "8": "Starting charging", "9": "Alarm",
    "10": "PV power — waiting", "11": "PV power charging",
}

CHARGE_MODE_MAP = {
    0: "Immediate", 1: "Scheduled", 2: "Eco mode",
    3: "Fast mode", 4: "PV only", 5: "Grid only", 6: "Mixed mode",
}
START_REASON_MAP = {
    0: "Plug-in", 1: "Remote start", 2: "Scheduled",
    3: "Manual start", 4: "RFID scan", 5: "Vehicle start",
}
STOP_REASON_MAP = {
    0: "Manual stop", 1: "Scheduled end", 2: "By vehicle",
    3: "By charger", 4: "Emergency stop", 5: "Power failure",
    6: "Auth failure", 7: "Overcurrent", 8: "Unplugged", 9: "Charger fault",
}
