"""
FusionSolar API client — Python port of HuaweiInterface.cs.

Uses aiohttp (async) as required by Home Assistant.
Auth: POST username/password → accessToken + roaRand
Subsequent requests: Cookie header with bspsession + dp-session, roaRand header.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from .const import (
    APP_CLIENT_ID,
    AUTH_URL,
    DEFAULT_API_BASE,
    TOKEN_RENEWAL_MARGIN,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes (mirrors C# models)
# ---------------------------------------------------------------------------

@dataclass
class AuthData:
    """Mirrors AuthenticationResponseData."""
    access_token: str
    roa_rand: str
    expires: int          # seconds until expiry (relative, from API)
    refresh_token: str
    region_float_ip: str
    expiry_epoch: float   # absolute epoch when token expires (computed here)


@dataclass
class DeviceData:
    """Mirrors DeviceData model."""
    dn_id: int
    dn: str
    name: str
    device_status: str
    station_name: str
    type_id: int
    is_expandable: bool
    raw: dict = field(default_factory=dict)


@dataclass
class ChargerStatus:
    """Mirrors ChargerStatusResponse."""
    charge_status: int
    charge_status_label: str


@dataclass
class ChargeRecord:
    """Mirrors ChargeRecord model."""
    dn_id: int
    gun_number: int
    order_number: str
    serial_number: str
    start_time: int       # unix seconds
    stop_time: int        # unix seconds
    total_time: int       # minutes
    total_power: float    # kWh
    start_reason: int
    stop_reason: int
    charge_mode: int
    account_id: str


@dataclass
class RealTimeSignal:
    """Mirrors RealTimeSignal model."""
    signal_id: int
    name: str
    value: str
    real_value: str
    unit: str
    enum_map: dict[str, str]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class FusionSolarAuthError(Exception):
    """Raised when authentication fails."""


class FusionSolarApiError(Exception):
    """Raised when an API call fails."""


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

class FusionSolarApi:
    """
    Async API client for FusionSolar charger data.

    Mirrors HuaweiInterface.cs — auth is Bearer-like but uses session cookies
    (bspsession + dp-session) and a roaRand header for all requests.
    """

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        api_base: str = "",
    ) -> None:
        self._username = username
        self._password = password
        self._session = session
        self._auth: AuthData | None = None
        self._auth_lock = asyncio.Lock()
        # api_base may be auto-detected from regionFloatIp after first auth
        self._api_base = api_base or DEFAULT_API_BASE
        # If caller explicitly provided a base, don't override it with auto-detect
        self._api_base_overridden = bool(api_base)

    @property
    def api_base(self) -> str:
        """Return the resolved API base URL (useful after auto-detection)."""
        return self._api_base

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def authenticate(self) -> AuthData:
        """
        POST credentials to get accessToken + roaRand.
        Mirrors AuthenticateAsync() in C#.
        """
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
                ssl=False,   # C# also skips cert validation
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                body = await resp.json(content_type=None)

            if body.get("code") != 0 and body.get("data", {}).get("accessToken") is None:
                raise FusionSolarAuthError(
                    f"Auth failed: {body.get('description', 'unknown error')}"
                )

            data = body["data"]
            expires_in = int(data.get("expires", 3600))

            # Auto-detect regional API server from regionFloatIp.
            # The auth response contains the correct regional hostname for this account.
            # Example: "regionFloatIp": "uni001eu5.fusionsolar.huawei.com"
            region_ip = data.get("regionFloatIp", "")
            if region_ip and not self._api_base_overridden:
                # Build the full URL from the region hostname
                host = region_ip.strip()
                if not host.startswith("http"):
                    self._api_base = f"https://{host}:32800"
                    _LOGGER.debug("Auto-detected API base from regionFloatIp: %s", self._api_base)

            auth = AuthData(
                access_token=data["accessToken"],
                roa_rand=data["roaRand"],
                expires=expires_in,
                refresh_token=data.get("refreshToken", ""),
                region_float_ip=data.get("regionFloatIp", ""),
                expiry_epoch=time.time() + expires_in - TOKEN_RENEWAL_MARGIN,
            )
            self._auth = auth
            _LOGGER.debug("FusionSolar authenticated, token expires in %ds", expires_in)
            return auth

        except aiohttp.ClientError as exc:
            raise FusionSolarAuthError(f"HTTP error during auth: {exc}") from exc

    async def ensure_authenticated(self) -> AuthData:
        """
        Return current auth, refreshing if expired.
        Thread-safe via asyncio.Lock.
        """
        async with self._auth_lock:
            if self._auth is None or time.time() >= self._auth.expiry_epoch:
                _LOGGER.debug("Token missing or expired — re-authenticating")
                await self.authenticate()
        return self._auth  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Request helper
    # ------------------------------------------------------------------

    def _auth_headers(self, auth: AuthData) -> dict[str, str]:
        """
        Build headers used for every authenticated request.
        Mirrors the C# request.Headers pattern.
        """
        cookie = (
            f"locale=en-us;"
            f"bspsession={auth.access_token};"
            f"dp-session={auth.access_token}; Secure; HttpOnly"
        )
        return {
            "roaRand": auth.roa_rand,
            "Cookie": cookie,
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, params: dict | None = None) -> Any:
        auth = await self.ensure_authenticated()
        url = f"{self._api_base}{path}"
        try:
            async with self._session.get(
                url,
                params=params,
                headers=self._auth_headers(auth),
                ssl=False,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            raise FusionSolarApiError(f"GET {path} failed: {exc}") from exc

    async def _post(self, path: str, payload: dict) -> Any:
        auth = await self.ensure_authenticated()
        url = f"{self._api_base}{path}"
        try:
            async with self._session.post(
                url,
                json=payload,
                headers=self._auth_headers(auth),
                ssl=False,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            raise FusionSolarApiError(f"POST {path} failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Device discovery
    # ------------------------------------------------------------------

    async def get_device_list(self, parent_dn: str = "NE=140540243") -> list[DeviceData]:
        """
        GET device list filtered to EV chargers (mocType=60080).
        Mirrors GetDeviceListAsync() in C#.
        """
        body = await self._get(
            "/rest/neteco/web/config/device/v1/device-list",
            params={
                "conditionParams.parentDn": parent_dn,
                "conditionParams.curPage": 0,
                "conditionParams.recordperpage": 500,
                "conditionParams.mocTypes": 60080,
            },
        )

        raw_list: list[dict] = (body or {}).get("data") or []
        devices = []
        for d in raw_list:
            devices.append(DeviceData(
                dn_id=d.get("dnId", 0),
                dn=d.get("dn", ""),
                name=d.get("name", "Unknown charger"),
                device_status=d.get("deviceStatus", ""),
                station_name=d.get("stationName", ""),
                type_id=d.get("typeId", 0),
                is_expandable=d.get("isExpandable", False),
                raw=d,
            ))
        return devices

    async def get_children_list(self, parent_dn: str) -> list[dict]:
        """
        GET charger gun/connector children (mocType=60081).
        Mirrors GetChildrenListAsync() in C#.
        """
        from urllib.parse import quote
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
    # ------------------------------------------------------------------

    async def get_charger_status(
        self,
        dn_id: int,
        gun_number: int = 1,
        need_real_time_status: bool = True,
    ) -> ChargerStatus:
        """
        POST to charge-status endpoint.
        Mirrors GetChargerStatusAsync() in C#.
        """
        body = await self._post(
            "/rest/neteco/web/homemgr/v1/charger/status/charge-status",
            {
                "dnId": dn_id,
                "needRealTimeStatus": need_real_time_status,
                "gunNumber": gun_number,
            },
        )

        status_code = int((body or {}).get("chargeStatus", -1))
        from .const import CHARGER_STATUS_MAP
        return ChargerStatus(
            charge_status=status_code,
            charge_status_label=CHARGER_STATUS_MAP.get(status_code, "Unknown"),
        )

    # ------------------------------------------------------------------
    # Real-time signal data (power, current, voltage, etc.)
    # ------------------------------------------------------------------

    async def get_realtime_info(
        self,
        dn_id: int,
        signal_ids: list[int],
    ) -> list[RealTimeSignal]:
        """
        POST to get-realtime-info endpoint.
        Mirrors GetDeviceRealTimeInfoAsync() in C#.
        Response is keyed by device dnId as a string.
        """
        body = await self._post(
            "/rest/neteco/web/homemgr/v1/device/get-realtime-info",
            {
                "conditions": [
                    {
                        "dnId": dn_id,
                        "queryAll": False,
                        "signals": signal_ids,
                    }
                ]
            },
        )

        # Response is {"<dnId>": [{signal}, ...]}
        signals_raw: list[dict] = (body or {}).get(str(dn_id), [])
        signals = []
        for s in signals_raw:
            signals.append(RealTimeSignal(
                signal_id=s.get("id", 0),
                name=s.get("name", ""),
                value=s.get("value", ""),
                real_value=s.get("realValue", ""),
                unit=s.get("unit", ""),
                enum_map=s.get("enumMap") or {},
            ))
        return signals

    # ------------------------------------------------------------------
    # Config info (max current, settings)
    # ------------------------------------------------------------------

    async def get_config_info(
        self,
        dn_id: int,
        signal_ids: list[int],
        verbose: bool = True,
    ) -> list[dict]:
        """
        POST to get-config-info endpoint.
        Mirrors GetDeviceConfigInfoAsync() in C#.
        """
        body = await self._post(
            "/rest/neteco/web/homemgr/v1/device/get-config-info",
            {
                "conditions": [
                    {
                        "dnId": dn_id,
                        "queryAll": False,
                        "signals": signal_ids,
                    }
                ],
                "verbose": verbose,
            },
        )
        return (body or {}).get(str(dn_id), [])

    # ------------------------------------------------------------------
    # Charge sessions history
    # ------------------------------------------------------------------

    async def get_charge_sessions(
        self,
        dn_id: int,
        start_ts: int,
        end_ts: int,
        page: int = 1,
        page_size: int = 50,
        timezone_id: str = "Europe/Brussels",
    ) -> list[ChargeRecord]:
        """
        POST to list-charge-record endpoint.
        Mirrors GetChargeSessionsAsync() in C#.
        """
        body = await self._post(
            "/rest/neteco/web/homemgr/v2/charger/list-charge-record",
            {
                "pageNo": page,
                "pageSize": page_size,
                "timeZoneId": timezone_id,
                "dnId": str(dn_id),
                "startTime": start_ts,
                "endTime": end_ts,
            },
        )

        records_raw: list[dict] = ((body or {}).get("data") or {}).get("records") or []
        records = []
        for r in records_raw:
            records.append(ChargeRecord(
                dn_id=r.get("dnId", 0),
                gun_number=r.get("gunNumber", 1),
                order_number=r.get("orderNumber", ""),
                serial_number=r.get("serialNumber", ""),
                start_time=int(r.get("startTime", 0)),
                stop_time=int(r.get("stopTime", 0)),
                total_time=r.get("totalTime", 0),
                total_power=float(r.get("totalPower", 0.0)),
                start_reason=r.get("startReason", -1),
                stop_reason=r.get("stopReason", -1),
                charge_mode=r.get("chargeMode", -1),
                account_id=r.get("accountId", ""),
            ))
        return records

    # ------------------------------------------------------------------
    # Charge plans / next trip
    # ------------------------------------------------------------------

    async def get_charger_plans(self, dn_id: int) -> dict:
        """Mirrors GetChargerPlansAsync() in C#."""
        body = await self._get(
            "/rest/neteco/web/homemgr/v1/charger/plan/query-plan",
            params={"dnId": dn_id},
        )
        return body or {}

    async def check_next_trip_support(self, dn_id: int) -> bool:
        """Mirrors CheckNextTripSupportAsync() in C#."""
        body = await self._get(
            "/rest/neteco/web/homemgr/v1/charger/plan/next-trip",
            params={"dnId": dn_id},
        )
        return bool((body or {}).get("data", {}).get("isSupportNextTrip", False))

    # ------------------------------------------------------------------
    # User / station helpers
    # ------------------------------------------------------------------

    async def get_user_info(self) -> dict:
        """Mirrors GetUserDetailInfoAsync() in C#."""
        body = await self._get(
            "/rest/neteco/phoneapp/v1/datacenter/getuserdetailinfo"
        )
        return body or {}

    async def get_station_list(self, timezone: str = "Europe/Brussels") -> list[dict]:
        """Mirrors GetStationListAsync() in C#."""
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
        return data.get("stations") or data.get("list") or []
