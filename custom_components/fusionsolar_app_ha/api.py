"""
FusionSolar API client — confirmed from APK decompilation.

Endpoints used:
  Auth:          POST intl.fusionsolar.huawei.com/rest/neteco/appauthen/v1/smapp/app/token
  Company DN:    GET  /rest/neteco/phoneapp/v2/fusionsolarbusiness/company/getorganizationcompanybyuser
  Device list:   GET  /rest/neteco/web/config/device/v1/device-list   (all mocTypes)
  Children list: GET  /rest/neteco/web/config/device/v1/children-list
  Charger status:POST /rest/neteco/web/homemgr/v1/charger/status/charge-status
  Process data:  POST /rest/neteco/web/homemgr/v1/charger/device/query-process-data
  Config info:   POST /rest/neteco/web/homemgr/v1/device/get-config-info
  Realtime info: POST /rest/neteco/web/homemgr/v1/device/get-realtime-info
  Set config:    POST /rest/neteco/web/homemgr/v1/device/set-config-info
  Start charge:  POST /rest/neteco/web/homemgr/v1/charger/charge/start-charge
  Stop charge:   POST /rest/neteco/web/homemgr/v1/charger/charge/stop-charge
  Device KPI:    GET  /rest/pvms/web/device/v1/device-real-kpi          (inverter/battery/meter)
  Station KPI:   GET  /rest/pvms/web/station/v1/overview/station-real-kpi
  Station list:  POST /rest/pvms/web/station/v1/station/station-list
  User info:     GET  /rest/neteco/phoneapp/v1/datacenter/getuserdetailinfo
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import AUTH_URL, APP_CLIENT_ID, DEFAULT_API_BASE, TOKEN_RENEWAL_MARGIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class AuthData:
    access_token: str
    roa_rand: str
    region_float_ip: str
    expiry_epoch: float


class FusionSolarAuthError(Exception):
    pass


class FusionSolarApiError(Exception):
    pass


class FusionSolarApi:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        api_base: str = "",
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._auth: AuthData | None = None
        self._auth_lock = asyncio.Lock()

        if api_base:
            base = api_base.rstrip("/")
            if ":32800" not in base and ":443" not in base:
                base = f"{base}:32800"
            self._api_base = base
            self._api_base_locked = True
        else:
            self._api_base = DEFAULT_API_BASE
            self._api_base_locked = False

    @property
    def api_base(self) -> str:
        return self._api_base

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def authenticate(self) -> None:
        payload = {
            "userName": self._username,
            "value": self._password,
            "grantType": "password",
            "verifyCode": "",
            "appClientId": APP_CLIENT_ID,
        }
        try:
            async with self._session.post(
                AUTH_URL, json=payload, ssl=False,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                body = await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            raise FusionSolarAuthError(f"Network error: {exc}") from exc

        data = (body or {}).get("data")
        if not data or not data.get("accessToken"):
            raise FusionSolarAuthError(
                f"Auth rejected: {(body or {}).get('description', 'unknown')}"
            )

        expires_in = int(data.get("expires", 3600))
        region_ip = data.get("regionFloatIp", "")
        self._auth = AuthData(
            access_token=data["accessToken"],
            roa_rand=data["roaRand"],
            region_float_ip=region_ip,
            expiry_epoch=time.time() + expires_in - TOKEN_RENEWAL_MARGIN,
        )
        if not self._api_base_locked and region_ip:
            host = region_ip.strip()
            self._api_base = f"https://{host}:32800" if not host.startswith("http") else host
            _LOGGER.debug("Auto-detected API base: %s", self._api_base)

    async def _ensure_auth(self) -> AuthData:
        async with self._auth_lock:
            if self._auth is None or time.time() >= self._auth.expiry_epoch:
                await self.authenticate()
        return self._auth  # type: ignore[return-value]

    def _headers(self, auth: AuthData) -> dict[str, str]:
        return {
            "roaRand": auth.roa_rand,
            "Cookie": (
                f"locale=en-us;"
                f"bspsession={auth.access_token};"
                f"dp-session={auth.access_token}; Secure; HttpOnly"
            ),
        }

    async def _get(self, path: str, params: dict | None = None) -> Any:
        auth = await self._ensure_auth()
        try:
            async with self._session.get(
                f"{self._api_base}{path}", params=params,
                headers=self._headers(auth), ssl=False,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            raise FusionSolarApiError(f"GET {path} failed: {exc}") from exc

    async def _post(self, path: str, payload: dict) -> Any:
        auth = await self._ensure_auth()
        try:
            async with self._session.post(
                f"{self._api_base}{path}", json=payload,
                headers=self._headers(auth), ssl=False,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            raise FusionSolarApiError(f"POST {path} failed: {exc}") from exc

    # ------------------------------------------------------------------
    # User info (provides accountId for start-charge)
    # ------------------------------------------------------------------

    async def get_user_info(self) -> dict:
        """GET getuserdetailinfo → {userId, username, ...}"""
        body = await self._get(
            "/rest/neteco/phoneapp/v1/datacenter/getuserdetailinfo"
        )
        return (body or {}).get("data") or body or {}

    # ------------------------------------------------------------------
    # Device discovery
    # ------------------------------------------------------------------

    async def get_company_dn(self) -> str:
        body = await self._get(
            "/rest/neteco/phoneapp/v2/fusionsolarbusiness/company"
            "/getorganizationcompanybyuser"
        )
        return (body or {}).get("data", {}).get("dn", "")

    async def get_all_devices(self, company_dn: str) -> list[dict]:
        """
        GET all devices under the company — no mocTypes filter.
        Returns every device type: inverter, battery, meter, charger, dongle etc.
        """
        body = await self._get(
            "/rest/neteco/web/config/device/v1/device-list",
            params={
                "conditionParams.parentDn": company_dn,
                "conditionParams.curPage": 0,
                "conditionParams.recordperpage": 500,
            },
        )
        return (body or {}).get("data") or []

    async def get_devices_by_type(self, company_dn: str, moc_type: int) -> list[dict]:
        """GET devices filtered to a specific mocType."""
        body = await self._get(
            "/rest/neteco/web/config/device/v1/device-list",
            params={
                "conditionParams.parentDn": company_dn,
                "conditionParams.curPage": 0,
                "conditionParams.recordperpage": 500,
                "conditionParams.mocTypes": moc_type,
            },
        )
        return (body or {}).get("data") or []

    async def get_management_devices(self) -> list[dict]:
        """EV charger devices only (mocType 60080) — kept for config flow compat."""
        company_dn = await self.get_company_dn()
        if not company_dn:
            return []
        return await self.get_management_devices_raw(company_dn)

    async def get_management_devices_raw(self, company_dn: str) -> list[dict]:
        return await self.get_devices_by_type(company_dn, 60080)

    async def get_children_list(self, parent_dn: str, moc_type: int = 60081) -> list[dict]:
        body = await self._get(
            "/rest/neteco/web/config/device/v1/children-list",
            params={
                "conditionParams.parentDn": parent_dn,
                "conditionParams.recordperpage": 100,
                "conditionParams.curPage": 0,
                "conditionParams.mocTypes": moc_type,
            },
        )
        return (body or {}).get("data") or []

    # ------------------------------------------------------------------
    # EV Charger — read
    # ------------------------------------------------------------------

    async def get_charger_status(self, dn_id: int) -> dict:
        """POST charge-status → {chargeStatus: int} only."""
        body = await self._post(
            "/rest/neteco/web/homemgr/v1/charger/status/charge-status",
            {"dnId": dn_id, "needRealTimeStatus": True, "gunNumber": 1},
        )
        return body or {}

    async def get_charging_process_data(self, dn_id: int, gun_number: int = 1) -> dict:
        """
        POST query-process-data — live session data.
        Response: {chargingPower: {value, unit}, chargingVoltage, chargingCurrent,
                   chargedEnergy, chargedTime, chargeState, orderNumber, serialNumber, accountId}
        From APK ChargingData.java — all numeric fields are nested {value, unit} objects.
        """
        body = await self._post(
            "/rest/neteco/web/homemgr/v1/charger/device/query-process-data",
            {"devices": [{"dnId": dn_id, "gunNumber": gun_number}]},
        )
        if isinstance(body, list):
            return body[0] if body else {}
        if isinstance(body, dict):
            data = body.get("data")
            if isinstance(data, list):
                return data[0] if data else {}
            if isinstance(data, dict):
                return data.get(str(dn_id), data)
            return body
        return {}

    async def get_config_signals(
        self, dn_id: int, signal_ids: list[int], query_all: bool = False
    ) -> dict[int, dict]:
        body = await self._post(
            "/rest/neteco/web/homemgr/v1/device/get-config-info",
            {
                "conditions": [
                    {"dnId": dn_id, "queryAll": query_all, "signals": signal_ids}
                ],
                "verbose": True,
            },
        )
        signals_raw: list[dict] = (body or {}).get(str(dn_id), [])
        return {s.get("id", 0): s for s in signals_raw}

    async def get_realtime_signals(
        self, dn_id: int, signal_ids: list[int]
    ) -> dict[int, dict]:
        body = await self._post(
            "/rest/neteco/web/homemgr/v1/device/get-realtime-info",
            {"conditions": [{"dnId": dn_id, "queryAll": False, "signals": signal_ids}]},
        )
        signals_raw: list[dict] = (body or {}).get(str(dn_id), [])
        return {s.get("id", 0): s for s in signals_raw}

    # ------------------------------------------------------------------
    # EV Charger — control (from APK fc2.java + StartChargeParamsRequest)
    # ------------------------------------------------------------------

    async def start_charge(
        self, dn_id: int, account_id: str, gun_number: int = 1
    ) -> bool:
        """
        POST start-charge.
        accountId comes from get_user_info()["userId"] (as string).
        Returns True on success.
        """
        try:
            await self._post(
                "/rest/neteco/web/homemgr/v1/charger/charge/start-charge",
                {"dnId": dn_id, "gunNumber": gun_number, "accountId": str(account_id)},
            )
            return True
        except FusionSolarApiError as exc:
            _LOGGER.error("start-charge failed: %s", exc)
            return False

    async def stop_charge(
        self,
        dn_id: int,
        order_number: str = "",
        serial_number: str = "",
        gun_number: int = 1,
    ) -> bool:
        """
        POST stop-charge.
        orderNumber and serialNumber come from get_charging_process_data().
        """
        try:
            await self._post(
                "/rest/neteco/web/homemgr/v1/charger/charge/stop-charge",
                {
                    "dnId": dn_id,
                    "gunNumber": gun_number,
                    "orderNumber": order_number,
                    "serialNumber": serial_number,
                },
            )
            return True
        except FusionSolarApiError as exc:
            _LOGGER.error("stop-charge failed: %s", exc)
            return False

    async def set_config_signal(
        self, dn_id: int, signal_id: int, value: Any
    ) -> bool:
        """
        POST set-config-info for a single signal.
        Payload from APK SignalSettingParam: {conditions: [{dnId, signals: [{id, value}]}]}
        Used for: max current (20003), working mode (20002), max grid power (20006),
                  surplus power threshold (20007), dynamic power limit (20001).
        """
        try:
            body = await self._post(
                "/rest/neteco/web/homemgr/v1/device/set-config-info",
                {
                    "conditions": [
                        {
                            "dnId": dn_id,
                            "signals": [{"id": signal_id, "value": str(value)}],
                        }
                    ]
                },
            )
            code = (body or {}).get("code", 0)
            if code != 0:
                _LOGGER.warning(
                    "set-config-info signal %s=%s returned code %s: %s",
                    signal_id, value, code, (body or {}).get("message", ""),
                )
            return code == 0
        except FusionSolarApiError as exc:
            _LOGGER.error("set-config-info failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Inverter / battery / meter — live KPI via pvms
    # ------------------------------------------------------------------

    async def get_device_real_kpi(self, device_dn: str, signal_ids: list[int]) -> dict:
        """
        GET device-real-kpi.
        deviceDn is the device DN string (e.g. "NE=12345,DEV=1").
        signalIds is a comma-separated string.
        Returns {signalId: {value, unit, ...}, ...}.
        """
        body = await self._get(
            "/rest/pvms/web/device/v1/device-real-kpi",
            params={
                "deviceDn": device_dn,
                "signalIds": ",".join(str(s) for s in signal_ids),
            },
        )
        data = (body or {}).get("data") or body or {}
        # Response is keyed by signal ID as string
        if isinstance(data, dict):
            return data
        return {}

    # ------------------------------------------------------------------
    # Station KPI
    # ------------------------------------------------------------------

    async def get_station_real_kpi(self, station_dn: str, timezone: str = "2.0") -> dict:
        body = await self._get(
            "/rest/pvms/web/station/v1/overview/station-real-kpi",
            params={
                "queryTime": int(time.time() * 1000),
                "stationDn": station_dn,
                "timeZone": timezone,
            },
        )
        return (body or {}).get("data") or {}

    async def get_station_list(self, timezone: str = "Europe/Brussels") -> list[dict]:
        body = await self._post(
            "/rest/pvms/web/station/v1/station/station-list",
            {
                "locale": timezone,
                "sortId": "createTime",
                "timeZone": "2.00",
                "pageSize": "11",
                "supportMDevice": "1",
                "sortDir": "DESC",
                "curPage": 1,
            },
        )
        data = (body or {}).get("data") or {}
        return data.get("list") or data.get("stations") or []

    async def get_station_dn(self, station_dn_id: int) -> str | None:
        stations = await self.get_station_list()
        for s in stations:
            if int(s.get("dnId", -1)) == station_dn_id:
                return s.get("dn") or s.get("stationDn")
        return None
