"""Config flow for the Qubo integration."""

import logging
import uuid

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    APP_ID,
    BASE_URL,
    CONF_DEVICE_UUID,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEVICE_ATTRIBUTE,
    DEVICE_TYPE_BULBS,
    DEVICE_TYPE_PLUG,
    DOMAIN,
    LOGIN_DEVICE_NAME,
)

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)
    login_url = (
        f"{BASE_URL}/sms/api/v4/sp/"
        f"d10e4bfb0153496e8e8bb955f7ebe413/user/login"
    )

    payload = {
        "accessToken": "",
        "deviceAttribute": DEVICE_ATTRIBUTE,
        "username": data[CONF_USERNAME],
        "password": data[CONF_PASSWORD],
    }

    client_id = uuid.uuid4().hex[:16]

    headers = {
        "Content-Type": "application/json",
        "Host": "srvcapp.platform.quboworld.com",
        "User-Agent": "libcurl-agent restclient-cpp/2:1:1",
        "App-Id": APP_ID,
        "Login-Device-Name": LOGIN_DEVICE_NAME,
        "Source": "ANDROID",
        "Source-Device-Id": client_id,
        "Token-Type": "USER",
    }
    params = {"system": "CS"}

    async with session.post(
        login_url, json=payload, headers=headers, params=params
    ) as response:
        if response.status in {401, 403}:
            raise InvalidAuth
        if response.status >= 400:
            raise CannotConnect

        result = await response.json()
        access_token = result.get("accessToken")
        user_uuid = result.get("uuid")

    # Fetch devices via sync API
    sync_url = (
        f"{BASE_URL}/unit-entity-management/api/v6/sp/"
        f"d10e4bfb0153496e8e8bb955f7ebe413/units/sync"
    )
    sync_headers = {
        "Host": "srvcapp.platform.quboworld.com",
        "User-Agent": "libcurl-agent restclient-cpp/2:1:1",
        "Accept": "*/*",
        "Login-Device-Name": LOGIN_DEVICE_NAME,
        "Source-Device-Id": client_id,
        "Subscriber-Key": access_token,
        "Token-Type": "USER",
        "User-UUID": user_uuid,
    }
    sync_payload = {"syncType": 1}

    async with session.post(
        sync_url, headers=sync_headers, json=sync_payload
    ) as sync_response:
        if sync_response.status >= 400:
            raise CannotConnect
        sync_data = await sync_response.json()

    devices = sync_data.get("devices", [])
    if not devices:
        raise NoDevices

    return {
        "title": data[CONF_USERNAME],
        "client_id": client_id,
        "devices": devices,
    }


class QuboConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Qubo."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._username = None
        self._password = None
        self._client_id = None
        self._devices = []

    async def async_step_user(self, user_input=None):
        """Handle the initial step - login."""
        errors = {}

        if user_input is not None:
            try:
                self._username = user_input[CONF_USERNAME]
                self._password = user_input[CONF_PASSWORD]

                info = await validate_input(self.hass, user_input)
                self._client_id = info["client_id"]
                self._devices = info["devices"]

                if len(self._devices) == 1:
                    return await self._create_entry(self._devices[0])

                return await self.async_step_device()

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except NoDevices:
                errors["base"] = "no_devices"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_device(self, user_input=None):
        """Handle device selection when multiple devices exist."""
        errors = {}

        if user_input is not None:
            device_uuid = user_input[CONF_DEVICE_UUID]
            selected = next(
                (d for d in self._devices if d["deviceUUID"] == device_uuid),
                self._devices[0],
            )
            return await self._create_entry(selected)

        device_options = {}
        for dev in self._devices:
            name = dev.get("deviceName", dev.get("deviceUUID", "Unknown"))
            model = dev.get("deviceType", "")
            label = f"{name} ({model})" if model else name
            device_options[dev["deviceUUID"]] = label

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICE_UUID): vol.In(device_options)}
            ),
            errors=errors,
        )

    async def _create_entry(self, device):
        """Create the config entry for the selected device."""
        await self.async_set_unique_id(device["deviceUUID"])
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=device.get("deviceName", self._username),
            data={
                CONF_USERNAME: self._username,
                CONF_PASSWORD: self._password,
                "client_id": self._client_id,
                "device_uuid": device["deviceUUID"],
                "unit_uuid": device.get("unitUUID"),
                "device_name": device.get("deviceName"),
                "handle_name": device.get("handleName"),
                "device_model": device.get("deviceType", ""),
            },
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


class NoDevices(Exception):
    """Error to indicate no devices found."""
