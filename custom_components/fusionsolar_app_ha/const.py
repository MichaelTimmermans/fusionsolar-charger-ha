"""Constants for the FusionSolar App HA integration."""

DOMAIN = "fusionsolar_app_ha"

AUTH_URL = "https://intl.fusionsolar.huawei.com:32800/rest/neteco/appauthen/v1/smapp/app/token"
APP_CLIENT_ID = "86366133-B8B5-41FA-8EB9-E5A64229E3E1"

CONF_API_BASE = "api_base"
CONF_STATION_DN_ID = "station_dn_id"
CONF_STATION_NAME = "station_name"

DEFAULT_API_BASE = "https://uni001eu5.fusionsolar.huawei.com:32800"

# Regio servers teruggezet om import-fouten in config_flow te voorkomen
REGION_SERVERS = {
    "Europe (uni001eu5)": "https://uni001eu5.fusionsolar.huawei.com:32800",
    "Germany (region01eu5)": "https://region01eu5.fusionsolar.huawei.com:32800",
    "North America (region01na5)": "https://region01na5.fusionsolar.huawei.com:32800",
    "China (region01cn5)": "https://region01cn5.fusionsolar.huawei.com:32800",
    "Asia Pacific (region01ap5)": "https://region01ap5.fusionsolar.huawei.com:32800",
    "Other": "https://intl.fusionsolar.huawei.com:32800",
}

SCAN_INTERVAL = 30
SCAN_INTERVAL_STATION = 300
TOKEN_RENEWAL_MARGIN = 300

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_DEVICE_DN_ID = "device_dn_id"
CONF_DEVICE_NAME = "device_name"

PARENT_CONFIG_SIGNAL_IDS = [20001, 20010, 20012, 20014, 20015, 2101518, 2101519]
GUN_CONFIG_SIGNAL_IDS = [20002, 20003, 20004, 20005, 20006, 20007, 10030, 10035, 10036]
PARENT_REALTIME_SIGNAL_IDS = [2101519]

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