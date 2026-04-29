"""
FusionSolar API client — faithful Python port of HuaweiInterface.cs.

KEY POINTS:
  - Auth always POSTs to AUTH_URL (intl.fusionsolar.huawei.com) — never the regional server
  - All data calls use api_base (the regional server)
  - regionFloatIp in the auth response gives us the correct regional server automatically
  - All requests use: roaRand header + Cookie with bspsession + dp-session
  - Signal data uses the GUN dnId (child, mocType 60081), not the charger parent dnId
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
    """Bad credentials or auth rejected."""

class FusionSolarApiError(Exception):
    """A data API call failed."""


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
    # Auth — always hits AUTH_URL, never api_base
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
                AUTH_URL,
                json=payload,
                ssl=False,
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
            _LOGGER.debug("Auto-detected API base: %s", self._api_base)

        _LOGGER.debug("Authenticated, token expires in %ds", expires_in)

    async def _ensure_auth(self) -> AuthData:
        async with self._auth_lock:
            if self._auth is None or time.time() >= self._auth.expiry_epoch:
                await self.authenticate()
        return self._auth  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Request helpers
    # ------------------------------------------------------------------

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
        url = f"{self._api_base}{path}"
        try:
            async with self._session.get(
                url, params=params, headers=self._headers(auth),
                ssl=False, timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            raise FusionSolarApiError(f"GET {path} failed: {exc}") from exc

    async def _post(self, path: str, payload: dict) -> Any:
        auth = await self._ensure_auth()
        url = f"{self._api_base}{path}"
        try:
            async with self._session.post(
                url, json=payload, headers=self._headers(auth),
                ssl=False, timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            raise FusionSolarApiError(f"POST {path} failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Company DN discovery
    # ------------------------------------------------------------------

    async def get_company_dn(self) -> str:
        body = await self._get(
            "/rest/neteco/phoneapp/v2/fusionsolarbusiness/company"
            "/getorganizationcompanybyuser"
        )
        dn = (body or {}).get("data", {}).get("dn", "")
        if not dn:
            _LOGGER.warning("getorganizationcompanybyuser returned no dn. Response: %s", body)
        return dn

    # ------------------------------------------------------------------
    # Device discovery
    # ------------------------------------------------------------------

    async def get_management_devices(self) -> list[dict]:
        """Discover company DN then return EV charger devices (mocTypes=60080)."""
        company_dn = await self.get_company_dn()
        if not company_dn:
            return []
        return await self.get_management_devices_raw(company_dn)

    async def get_management_devices_raw(self, company_dn: str) -> list[dict]:
        """Fetch EV charger devices with a known company_dn. Returns raw dicts including 'dn'."""
        body = await self._get(
            "/rest/neteco/web/config/device/v1/device-list",
            params={
                "conditionParams.parentDn": company_dn,
                "conditionParams.curPage": 0,
                "conditionParams.recordperpage": 500,
                "conditionParams.mocTypes": 60080,
            },
        )
        devices = (body or {}).get("data") or []
        _LOGGER.debug("Found %d charger device(s)", len(devices))
        return devices

    async def get_children_list(self, parent_dn: str) -> list[dict]:
        """
        GET gun/connector children of a charger (mocTypes=60081).
        These child dnIds are needed for config-info and realtime-info calls.
        Mirrors GetChildrenListAsync() in HuaweiInterface.cs.
        """
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

    # ------------------------------------------------------------------
    # Charger status
    # Response is a flat dict: chargeStatus (int), chargePower (W), chargeEnergy (kWh)
    # ------------------------------------------------------------------

    async def get_charger_status(self, dn_id: int) -> dict:
        """
        POST charge-status. Uses the PARENT charger dnId.
        Response fields are at the top level (not nested under 'data').
        Mirrors GetChargerStatusAsync(dnId, needRealTimeStatus=true, gunNumber=1).
        """
        body = await self._post(
            "/rest/neteco/web/homemgr/v1/charger/status/charge-status",
            {"dnId": dn_id, "needRealTimeStatus": True, "gunNumber": 1},
        )
        return body or {}

    # ------------------------------------------------------------------
    # Config signals (confirmed working — use GUN dnId)
    # Returns dict keyed by signal_id for easy lookup
    # ------------------------------------------------------------------

    async def get_config_signals(
        self, dn_id: int, signal_ids: list[int], query_all: bool = False
    ) -> dict[int, dict]:
        """
        POST get-config-info.
        Use query_all=True to request every available signal without ID filtering.
        """
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
        _LOGGER.debug("get-config-info for %s returned %d signals", dn_id, len(signals_raw))
        return {s.get("id", 0): s for s in signals_raw}

    async def get_realtime_signals(
        self, dn_id: int, signal_ids: list[int]
    ) -> dict[int, dict]:
        """
        POST get-realtime-info. Use the GUN dnId.
        Returns signals indexed by signal_id.
        """
        body = await self._post(
            "/rest/neteco/web/homemgr/v1/device/get-realtime-info",
            {
                "conditions": [
                    {"dnId": dn_id, "queryAll": False, "signals": signal_ids}
                ]
            },
        )
        signals_raw: list[dict] = (body or {}).get(str(dn_id), [])
        return {s.get("id", 0): s for s in signals_raw}

    # ------------------------------------------------------------------
    # Station list
    # ------------------------------------------------------------------

    async def get_station_list(self, timezone: str = "Europe/Brussels") -> list[dict]:
        """POST station-list. Mirrors GetStationListAsync() in HuaweiInterface.cs."""
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
