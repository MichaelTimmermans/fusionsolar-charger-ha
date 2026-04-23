"""
Config flow for FusionSolar Charger.

Setup flow:
  Step 1 — user: username + password (validated by a real auth attempt)
            → on success: auto-detect regional server from auth response
            → if auto-detect fails: show server picker (step: server)
  Step 2 — server (only if needed): choose from known regional servers
  Step 3 — pick_device (only if multiple chargers found): choose which one

The happy path for most users is just Step 1 (enter credentials, done).
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import FusionSolarApi, FusionSolarAuthError
from .const import (
    CONF_API_BASE,
    CONF_DEVICE_DN_ID,
    CONF_DEVICE_NAME,
    DEFAULT_API_BASE,
    DOMAIN,
    REGION_SERVERS,
)

_LOGGER = logging.getLogger(__name__)


class FusionSolarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for FusionSolar Charger."""

    VERSION = 1

    def __init__(self) -> None:
        self._username: str = ""
        self._password: str = ""
        self._api_base: str = ""
        self._devices: list[dict] = []

    # ------------------------------------------------------------------
    # Step 1: credentials
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """
        Ask for FusionSolar username + password.
        Attempts auth immediately and auto-detects the regional server.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            session = async_get_clientsession(self.hass, verify_ssl=False)
            # No api_base yet — auth will auto-detect it from regionFloatIp
            api = FusionSolarApi(username, password, session)

            try:
                await api.authenticate()
            except FusionSolarAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during credential validation")
                errors["base"] = "cannot_connect"
            else:
                self._username = username
                self._password = password
                self._api_base = api.api_base  # auto-detected or fallback default

                # Try to fetch devices with the resolved server
                try:
                    devices = await api.get_device_list()
                except Exception:
                    _LOGGER.warning(
                        "Could not fetch devices from auto-detected server %s, "
                        "falling back to server picker",
                        self._api_base,
                    )
                    return await self.async_step_server()

                if not devices:
                    # Server responded but no chargers found — might be wrong region
                    _LOGGER.debug("No devices on %s, showing server picker", self._api_base)
                    return await self.async_step_server()

                return await self._proceed_with_devices(devices)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
                    ),
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(
                            type=TextSelectorType.PASSWORD, autocomplete="current-password"
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "portal_url": "https://eu5.fusionsolar.huawei.com"
            },
        )

    # ------------------------------------------------------------------
    # Step 2 (optional): regional server picker
    # ------------------------------------------------------------------

    async def async_step_server(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """
        Let the user pick which regional server to use.
        Only shown when auto-detection fails or finds no chargers.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            chosen = user_input[CONF_API_BASE]
            api_base = REGION_SERVERS.get(chosen, chosen) or DEFAULT_API_BASE

            session = async_get_clientsession(self.hass, verify_ssl=False)
            api = FusionSolarApi(self._username, self._password, session, api_base=api_base)

            try:
                await api.authenticate()
                devices = await api.get_device_list()
            except FusionSolarAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Error connecting to %s", api_base)
                errors["base"] = "cannot_connect"
            else:
                self._api_base = api_base
                if not devices:
                    errors["base"] = "no_devices"
                else:
                    return await self._proceed_with_devices(devices)

        options = [
            SelectOptionDict(value=label, label=f"{label}  ({url})" if url else label)
            for label, url in REGION_SERVERS.items()
            if label != "Auto-detect (recommended)"
        ]

        return self.async_show_form(
            step_id="server",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_API_BASE,
                        default="Europe 5 (eu5) — default",
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "hint": (
                    "Check which server you use by looking at the URL when you log in to "
                    "the FusionSolar web portal (e.g. eu5.fusionsolar.huawei.com → Europe 5)."
                )
            },
        )

    # ------------------------------------------------------------------
    # Step 3 (optional): pick one charger if account has multiple
    # ------------------------------------------------------------------

    async def async_step_pick_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Let the user choose which EV charger to monitor."""
        if user_input is not None:
            dn_id = int(user_input[CONF_DEVICE_DN_ID])
            name = next(
                (d["name"] for d in self._devices if d["dn_id"] == dn_id),
                f"Charger {dn_id}",
            )
            return self._create_entry(dn_id, name)

        options = [
            SelectOptionDict(value=str(d["dn_id"]), label=d["name"])
            for d in self._devices
        ]

        return self.async_show_form(
            step_id="pick_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_DN_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _proceed_with_devices(self, devices: list) -> FlowResult:
        """Route to device picker or straight to entry creation."""
        if len(devices) == 1:
            d = devices[0]
            return self._create_entry(d.dn_id, d.name)

        self._devices = [{"dn_id": d.dn_id, "name": d.name} for d in devices]
        return await self.async_step_pick_device()

    def _create_entry(self, dn_id: int, name: str) -> FlowResult:
        """Create the final config entry."""
        return self.async_create_entry(
            title=name,
            data={
                CONF_USERNAME: self._username,
                CONF_PASSWORD: self._password,
                CONF_API_BASE: self._api_base,
                CONF_DEVICE_DN_ID: dn_id,
                CONF_DEVICE_NAME: name,
            },
        )
