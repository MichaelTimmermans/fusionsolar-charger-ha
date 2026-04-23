"""Constants for the FusionSolar Charger integration."""

DOMAIN = "fusionsolar_charger"

# Auth endpoint — universal international endpoint, same for all regions
AUTH_URL = "https://intl.fusionsolar.huawei.com:32800/rest/neteco/appauthen/v1/smapp/app/token"
APP_CLIENT_ID = "86366133-B8B5-41FA-8EB9-E5A64229E3E1"

# Config entry key for the resolved API base URL
CONF_API_BASE = "api_base"

# Known regional API servers.
# Format: {display label: base URL}
# The auth response contains a regionFloatIp that usually resolves this
# automatically. This list is the fallback picker shown only if auto-detect fails.
REGION_SERVERS: dict[str, str] = {
    "Auto-detect (recommended)": "",
    "Europe 1 (eu1)": "https://uni001eu1.fusionsolar.huawei.com:32800",
    "Europe 2 (eu2)": "https://uni001eu2.fusionsolar.huawei.com:32800",
    "Europe 3 (eu3)": "https://uni001eu3.fusionsolar.huawei.com:32800",
    "Europe 4 (eu4)": "https://uni001eu4.fusionsolar.huawei.com:32800",
    "Europe 5 (eu5) — default": "https://uni001eu5.fusionsolar.huawei.com:32800",
    "International (intl)": "https://intl.fusionsolar.huawei.com:32800",
    "China (cn)": "https://uni001cn1.fusionsolar.huawei.com:32800",
}

# Fallback if auto-detect produces nothing
DEFAULT_API_BASE = "https://uni001eu5.fusionsolar.huawei.com:32800"

# Polling interval in seconds
SCAN_INTERVAL = 30

# Token renewal margin (seconds before expiry to refresh)
TOKEN_RENEWAL_MARGIN = 300

# Config entry keys
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_DEVICE_DN_ID = "device_dn_id"
CONF_DEVICE_NAME = "device_name"

# Charger status codes → human-readable
CHARGER_STATUS_MAP = {
    0: "Available",
    1: "Preparing",
    2: "Charging",
    3: "Suspended EV",
    4: "Suspended EVSE",
    5: "Finishing",
    6: "Reserved",
    7: "Unavailable",
    8: "Faulted",
}

# Start reason codes
START_REASON_MAP = {
    0: "Plug-in",
    1: "Remote start",
    2: "Scheduled",
    3: "Manual start",
    4: "RFID scan",
    5: "Vehicle start",
}

# Stop reason codes
STOP_REASON_MAP = {
    0: "Manual stop",
    1: "Scheduled end",
    2: "By vehicle",
    3: "By charger",
    4: "Emergency stop",
    5: "Power failure",
    6: "Auth failure",
    7: "Overcurrent",
    8: "Unplugged",
    9: "Charger fault",
}

# Charge mode codes
CHARGE_MODE_MAP = {
    0: "Immediate",
    1: "Scheduled",
    2: "Eco mode",
    3: "Fast mode",
    4: "PV only",
    5: "Grid only",
    6: "Mixed mode",
}

# Signal IDs used for real-time device info (charger power, status etc.)
# These match the signal IDs your C# code queries
REALTIME_SIGNAL_IDS = [20001, 20002, 20004, 20005, 20006, 20010, 20011, 20013, 20015, 20016, 20017]

# Signal IDs for config (charging current limit etc.)
CONFIG_SIGNAL_IDS = [20014, 2101518, 2101525, 10100, 20006, 20001, 2101519, 20017]
