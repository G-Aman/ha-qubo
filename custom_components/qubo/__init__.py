"""The Qubo integration."""

import logging
import time

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    APP_ID,
    BASE_URL,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEVICE_ATTRIBUTE,
    DEVICE_TYPE_BULBS,
    DEVICE_TYPE_PLUG,
    DOMAIN,
    LOGIN_DEVICE_NAME,
    PLATFORMS_BULB,
    PLATFORMS_PLUG,
)
from .hub import QuboHub

_LOGGER = logging.getLogger(__name__)


def _get_device_platforms(device_model: str, device_name: str = "") -> list[str]:
    """Return the HA platforms to load for a given device model."""
    # Exact model match first
    if device_model == DEVICE_TYPE_PLUG:
        return PLATFORMS_PLUG
    if device_model in DEVICE_TYPE_BULBS:
        return PLATFORMS_BULB

    # Keyword fallback when model code is missing/unknown
    combined = (device_model + device_name).lower()
    if any(kw in combined for kw in ("plug", "socket", "smartplug")):
        return PLATFORMS_PLUG
    if any(kw in combined for kw in ("bulb", "light", "lamp", "hlb")):
        return PLATFORMS_BULB

    # Camera or unknown - no platforms, log warning
    if "camera" in combined:
        _LOGGER.warning(
            "Qubo camera devices are not yet supported: %s", device_model
        )
        return []
    _LOGGER.warning(
        "Unknown Qubo device model: %s (name: %s)", device_model, device_name
    )
    return []


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Qubo from a config entry."""
    session = async_get_clientsession(hass)
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    client_id = entry.data["client_id"]

    # Login
    login_url = (
        f"{BASE_URL}/sms/api/v4/sp/"
        f"d10e4bfb0153496e8e8bb955f7ebe413/user/login"
    )
    payload = {
        "accessToken": "",
        "deviceAttribute": DEVICE_ATTRIBUTE,
        "username": username,
        "password": password,
    }
    headers = {
        "Host": "srvcapp.platform.quboworld.com",
        "User-Agent": "libcurl-agent restclient-cpp/2:1:1",
        "Accept": "*/*",
        "App-Id": APP_ID,
        "Login-Device-Name": LOGIN_DEVICE_NAME,
        "Source": "ANDROID",
        "Source-Device-Id": client_id,
        "Token-Type": "USER",
    }

    try:
        async with session.post(
            login_url, json=payload, headers=headers, params={"system": "CS"}
        ) as response:
            if response.status >= 400:
                _LOGGER.error("Qubo login failed: %s", response.status)
                return False
            data = await response.json()
            access_token = data.get("accessToken")
            refresh_token = data.get("refreshToken")
            user_uuid = data.get("uuid")
            expires_in = data.get("expires_in", 3600)
            expires_at = time.time() + expires_in - 60
    except aiohttp.ClientError as err:
        _LOGGER.error("Failed to connect to Qubo: %s", err)
        return False

    # Device info from config entry
    device_uuid = entry.data.get("device_uuid")
    unit_uuid = entry.data.get("unit_uuid")
    device_name = entry.data.get("device_name", "Qubo Device")
    handle_name = entry.data.get("handle_name")
    device_model = entry.data.get("device_model", "")

    if not device_uuid or not unit_uuid:
        _LOGGER.error("Missing device/unit UUID in config entry")
        return False

    # Fetch initial state via sync API
    initial_state = False
    firmware_version: str | None = None
    shadow_data: dict = {}
    try:
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
        async with session.post(
            sync_url, headers=sync_headers, json={"syncType": 1}
        ) as sync_response:
            if sync_response.status < 400:
                sync_data = await sync_response.json()
                for dev in sync_data.get("devices", []):
                    if dev.get("deviceUUID") == device_uuid:
                        # Initial state from device-level "state" field
                        initial_state = dev.get("state", 0) == 1

                        # Collect available service names from nested structure
                        model_key = dev.get("deviceType", "")
                        model_devices = dev.get("devices", {}).get(model_key, [])
                        for model_dev in model_devices:
                            for svc in model_dev.get("services", []):
                                svc_name = svc.get("service", "")
                                shadow_data[svc_name] = True
                        # Firmware version from device-level data
                        firmware_version = dev.get("firmwareVersion")
                        _LOGGER.info(
                            "Qubo sync: device=%s, state=%s, firmware=%s, services=%s",
                            dev.get("deviceName"),
                            "on" if initial_state else "off",
                            firmware_version,
                            list(shadow_data.keys()),
                        )
                        break
    except aiohttp.ClientError as err:
        _LOGGER.warning("Could not fetch initial state: %s", err)

    # Create hub
    hub = QuboHub(
        hass=hass,
        session=session,
        access_token=access_token,
        refresh_token=refresh_token,
        user_uuid=user_uuid,
        device_uuid=device_uuid,
        unit_uuid=unit_uuid,
        expires_at=expires_at,
        initial_state=initial_state,
        device_name=device_name,
        handle_name=handle_name,
        client_id=client_id,
        device_model=device_model,
    )

    # Apply firmware version from sync
    hub.firmware_version = firmware_version

    # Online — sync succeeded, device is reachable
    hub.online = True

    await hub.start()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"hub": hub}

    # Determine platforms from device model (with keyword fallback)
    platforms = _get_device_platforms(device_model, device_name)
    _LOGGER.info(
        "Qubo device model: %s, loading platforms: %s",
        device_model, platforms,
    )
    if platforms:
        await hass.config_entries.async_forward_entry_setups(entry, platforms)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hub: QuboHub = hass.data[DOMAIN][entry.entry_id]["hub"]
    await hub.stop()
    platforms = _get_device_platforms(hub.device_model, hub.device_name)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
