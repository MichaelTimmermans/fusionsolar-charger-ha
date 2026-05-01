"""
FusionSolar API client — confirmed from APK decompilation.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
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
            raise FusionSolarAuthError(f"Network error during auth: {exc}") from exc

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

    async def get_company_dn(self) -> str:
        body = await self._get(
            "/rest/neteco/phoneapp/v2/fusionsolarbusiness/company"
            "/getorganizationcompanybyuser"
        )
        return (body or {}).get("data", {}).get("dn", "")

    async def get_management_devices(self) -> list[dict]:
        company_dn = await self.get_company_dn()
        if not company_dn:
            return []
        return await self.get_management_devices_raw(company_dn)

    async def get_management_devices_raw(self, company_dn: str) -> list[dict]:
        body = await self._get(
            "/rest/neteco/web/config/device/v1/device-list",
            params={
                "conditionParams.parentDn": company_dn,
                "conditionParams.curPage": 0,
                "conditionParams.recordperpage": 500,
                "conditionParams.mocTypes": 60080,
            },
        )
        return (body or {}).get("data") or []

    async def get_children_list(self, parent_dn: str) -> list[dict]:
        body = await self._get(
            "/rest/neteco/web/config/device/v1/children-list",
            params={
                "conditionParams.parentDn": parent_dn,
                "conditionParams.recordperpage": 100,
                "conditionParams.curPage": 0,
                "conditionParams.mocTypes": 60081,
            },
        )
        return (body or {}).get("data") or []

    async def get_charger_status(self, dn_id: int) -> dict:
        body = await self._post(
            "/rest/neteco/web/homemgr/v1/charger/status/charge-status",
            {"dnId": dn_id, "needRealTimeStatus": True, "gunNumber": 1},
        )
        return body or {}

    async def get_charging_process_data(
        self, dn_id: int, gun_number: int = 1
    ) -> dict:
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
                # Check for the specific dnId key as seen in your logs
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

    async def get_station_real_kpi(
        self, station_dn: str, timezone: str = "2.0"
    ) -> dict:
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