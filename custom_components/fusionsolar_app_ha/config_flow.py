"""
Config flow for FusionSolar App HA.

Step 1: username + password + server → authenticate → auto-discover everything
Step 2 (optional): pick_device if multiple EV chargers found
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
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

from .api import FusionSolarApi, FusionSolarAuthError, FusionSolarApiError
from .const import (
    CONF_API_BASE,
    CONF_DEVICE_DN_ID,
    CONF_DEVICE_NAME,
    CONF_STATION_DN_ID,
    CONF_STATION_NAME,
    DOMAIN,
    REGION_SERVERS,
)

_LOGGER = logging.getLogger(__name__)


class FusionSolarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for FusionSolar App HA."""

    VERSION = 1

    def __init__(self) -> None:
        self._username: str = ""
        self._password: str = ""
        self._api_base: str = ""
        self._devices: list[dict] = []
        self._station_dn_id: int | None = None
        self._station_name: str = ""

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            server_url = REGION_SERVERS.get(
                user_input[CONF_API_BASE], user_input[CONF_API_BASE]
            )
            session = async_get_clientsession(self.hass, verify_ssl=False)
            api = FusionSolarApi(
                session=session,
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                api_base=server_url,
            )

            try:
                await api.authenticate()
            except FusionSolarAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected auth error")
                errors["base"] = "cannot_connect"

            if not errors:
                try:
                    raw_devices = await api.get_management_devices()
                except (FusionSolarApiError, Exception):
                    _LOGGER.exception("Device discovery error")
                    errors["base"] = "cannot_connect"
                else:
                    if not raw_devices:
                        errors["base"] = "no_devices"
                    else:
                        self._username = user_input[CONF_USERNAME]
                        self._password = user_input[CONF_PASSWORD]
                        self._api_base = api.api_base
                        self._devices = [
                            {
                                "dn_id": int(d.get("dnId", 0)),
                                "name": d.get("name", f"Charger {d.get('dnId')}"),
                            }
                            for d in raw_devices
                        ]
                        await self._discover_station(api)

                        if len(self._devices) == 1:
                            d = self._devices[0]
                            return self._create_entry(d["dn_id"], d["name"])
                        return await self.async_step_pick_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
                ),
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
                ),
                vol.Required(CONF_API_BASE, default="Auto-detect (recommended)"): SelectSelector(
                    SelectSelectorConfig(
                        options=[SelectOptionDict(value=k, label=k) for k in REGION_SERVERS],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
            errors=errors,
        )

    async def async_step_pick_device(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            dn_id = int(user_input[CONF_DEVICE_DN_ID])
            name = next((d["name"] for d in self._devices if d["dn_id"] == dn_id), f"Charger {dn_id}")
            return self._create_entry(dn_id, name)

        return self.async_show_form(
            step_id="pick_device",
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE_DN_ID): SelectSelector(
                    SelectSelectorConfig(
                        options=[SelectOptionDict(value=str(d["dn_id"]), label=d["name"]) for d in self._devices],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    async def _discover_station(self, api: FusionSolarApi) -> None:
        try:
            stations = await api.get_station_list()
            if stations:
                first = stations[0]
                self._station_dn_id = int(first.get("dnId", 0)) or None
                self._station_name = first.get("name", "Solar Plant")
        except Exception as exc:
            _LOGGER.warning("Station discovery failed (non-fatal): %s", exc)

    def _create_entry(self, dn_id: int, name: str):
        data: dict = {
            CONF_USERNAME: self._username,
            CONF_PASSWORD: self._password,
            CONF_API_BASE: self._api_base,
            CONF_DEVICE_DN_ID: dn_id,
            CONF_DEVICE_NAME: name,
        }
        if self._station_dn_id:
            data[CONF_STATION_DN_ID] = self._station_dn_id
            data[CONF_STATION_NAME] = self._station_name
        return self.async_create_entry(title=name, data=data)
