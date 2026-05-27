"""The Qubo integration."""

import logging
import time

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv

from .const import (
    APP_ID,
    BASE_URL,
    CAMERA_MODELS,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEVICE_ATTRIBUTE,
    DEVICE_TYPE_BULBS,
    DEVICE_TYPE_PLUG,
    DOMAIN,
    LOGIN_DEVICE_NAME,
    PLATFORMS_BULB,
    PLATFORMS_CAMERA,
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

    # Camera models from decompiled APK
    if device_model in CAMERA_MODELS:
        return PLATFORMS_CAMERA

    # Keyword fallback when model code is missing/unknown
    combined = (device_model + device_name).lower()
    if any(kw in combined for kw in ("plug", "socket", "smartplug")):
        return PLATFORMS_PLUG
    if any(kw in combined for kw in ("bulb", "light", "lamp", "hlb")):
        return PLATFORMS_BULB
    if any(kw in combined for kw in ("camera", "doorbell", "cam", "ptz")):
        return PLATFORMS_CAMERA

    # Unknown - no platforms, log warning
    _LOGGER.warning(
        "Unknown Qubo device model: %s (name: %s)", device_model, device_name
    )
    return []


async def _login_and_get_token(hass, username, password, client_id):
    """Login to Qubo and return auth tokens."""
    session = async_get_clientsession(hass)
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

    async with session.post(
        login_url, json=payload, headers=headers, params={"system": "CS"}
    ) as response:
        if response.status >= 400:
            raise CannotConnect(f"Qubo login failed: {response.status}")
        data = await response.json()
        return {
            "access_token": data.get("accessToken"),
            "refresh_token": data.get("refreshToken"),
            "user_uuid": data.get("uuid"),
            "expires_at": time.time() + data.get("expires_in", 3600) - 60,
        }


async def _fetch_device_state(hass, access_token, user_uuid, client_id, device_uuid):
    """Fetch initial state for a single device from sync API."""
    session = async_get_clientsession(hass)
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

    initial_state = False
    firmware_version = None
    wifi_info = {"ssid": None, "ip": None, "signal": None}
    initial_color_mode = None
    initial_rgb_color = None
    initial_warmth_color = None
    hub_online = True
    # Camera initial state
    camera_night_mode = None
    camera_motion_sensitivity = None
    camera_volume = None
    camera_sd_info: dict[str, str | None] = {}

    try:
        async with session.post(
            sync_url, headers=sync_headers, json={"syncType": 1}
        ) as sync_response:
            if sync_response.status < 400:
                sync_data = await sync_response.json()

                for dev in sync_data.get("devices", []):
                    if dev.get("deviceUUID") == device_uuid:
                        initial_state = dev.get("state", 0) == 1
                        firmware_version = dev.get("firmwareVersion")
                        break

                for shadow_dev in sync_data.get("deviceshadow", []):
                    if shadow_dev.get("deviceUUID") != device_uuid:
                        continue
                    for svc in shadow_dev.get("services", []):
                        svc_name = svc.get("service", "")
                        attrs = svc.get("attributes", {})
                        if svc_name == "wifiSettings":
                            wifi_info["ssid"] = (attrs.get("SSIDName") or {}).get("value")
                            wifi_info["ip"] = (attrs.get("ipAddress") or {}).get("value")
                            wifi_info["signal"] = (attrs.get("signalStrength") or {}).get("value")
                        elif svc_name == "colorModeControl":
                            initial_color_mode = (attrs.get("mode") or {}).get("value")
                        elif svc_name == "colorRGBControl":
                            initial_rgb_color = (attrs.get("color") or {}).get("value")
                        elif svc_name == "colorWarmthControl":
                            initial_warmth_color = (attrs.get("color") or {}).get("value")
                        elif svc_name == "nightModeControl":
                            camera_night_mode = attrs.get("mpc_nightMode") or attrs.get("nightModeView") or attrs.get("nightMode")
                            if isinstance(camera_night_mode, dict):
                                camera_night_mode = camera_night_mode.get("value")
                        elif svc_name == "recordingConfig":
                            sens = attrs.get("motionSensitivity")
                            if isinstance(sens, dict):
                                sens = sens.get("value")
                            if sens:
                                camera_motion_sensitivity = sens
                        elif svc_name == "volumeControl":
                            vol = attrs.get("level")
                            if isinstance(vol, dict):
                                vol = vol.get("value")
                            if vol is not None:
                                camera_volume = int(vol)
                        elif svc_name == "systemDiagnosis":
                            for key, api_key in [("total", "totalExternalStorage"), ("available", "availableExternalStorage"), ("status", "SdCardAvailability")]:
                                val = attrs.get(api_key)
                                if isinstance(val, dict):
                                    val = val.get("value")
                                if val is not None:
                                    camera_sd_info[key] = str(val)
                            sd_status = attrs.get("sdCardStatus")
                            if isinstance(sd_status, dict):
                                sd_status = sd_status.get("value")
                            if sd_status is not None:
                                camera_sd_info["sdcard_status"] = str(sd_status)
                    op_state = shadow_dev.get("operationState", {})
                    hub_online = op_state.get("value") != "offline"
                    break
    except aiohttp.ClientError as err:
        _LOGGER.warning("Could not fetch initial state for %s: %s", device_uuid, err)

    return {
        "initial_state": initial_state,
        "firmware_version": firmware_version,
        "wifi_info": wifi_info,
        "initial_color_mode": initial_color_mode,
        "initial_rgb_color": initial_rgb_color,
        "initial_warmth_color": initial_warmth_color,
        "hub_online": hub_online,
        "camera_night_mode": camera_night_mode,
        "camera_motion_sensitivity": camera_motion_sensitivity,
        "camera_volume": camera_volume,
        "camera_sd_info": camera_sd_info,
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Qubo from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    client_id = entry.data["client_id"]

    # Support both old format (single device) and new format (devices list)
    if "devices" in entry.data:
        devices = entry.data["devices"]
    else:
        # Legacy single-device entry
        devices = [{
            "device_uuid": entry.data.get("device_uuid"),
            "unit_uuid": entry.data.get("unit_uuid"),
            "device_name": entry.data.get("device_name", "Qubo Device"),
            "handle_name": entry.data.get("handle_name"),
            "device_model": entry.data.get("device_model", ""),
        }]

    # Login once for all devices
    try:
        auth = await _login_and_get_token(hass, username, password, client_id)
    except Exception as err:
        _LOGGER.error("Failed to login to Qubo: %s", err)
        return False

    access_token = auth["access_token"]
    refresh_token = auth["refresh_token"]
    user_uuid = auth["user_uuid"]
    expires_at = auth["expires_at"]

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"hubs": {}}

    all_platforms: set[str] = set()

    for dev_info in devices:
        device_uuid = dev_info.get("device_uuid")
        unit_uuid = dev_info.get("unit_uuid")
        device_name = dev_info.get("device_name", "Qubo Device")
        handle_name = dev_info.get("handle_name")
        device_model = dev_info.get("device_model", "")

        if not device_uuid or not unit_uuid:
            _LOGGER.warning("Skipping device with missing UUID: %s", dev_info)
            continue

        # Fetch initial state for this device
        state_info = await _fetch_device_state(
            hass, access_token, user_uuid, client_id, device_uuid
        )

        # Create hub for this device
        hub = QuboHub(
            hass=hass,
            session=async_get_clientsession(hass),
            access_token=access_token,
            refresh_token=refresh_token,
            user_uuid=user_uuid,
            device_uuid=device_uuid,
            unit_uuid=unit_uuid,
            expires_at=expires_at,
            initial_state=state_info["initial_state"],
            device_name=device_name,
            handle_name=handle_name or "",
            client_id=client_id,
            device_model=device_model,
        )

        hub.firmware_version = state_info["firmware_version"]
        hub.online = state_info["hub_online"]

        if any(state_info["wifi_info"].values()):
            hub.wifi_info.update(state_info["wifi_info"])
        if state_info["initial_color_mode"]:
            hub.color_mode_str = state_info["initial_color_mode"]
        if state_info["initial_rgb_color"]:
            hub._parse_rgb(state_info["initial_rgb_color"])
        if state_info["initial_warmth_color"]:
            hub._parse_warmth(state_info["initial_warmth_color"])

        # Apply camera initial state from sync
        if hub.is_camera:
            if state_info["camera_night_mode"] is not None:
                hub.camera_night_mode = state_info["camera_night_mode"]
            if state_info["camera_motion_sensitivity"] is not None:
                hub.camera_motion_sensitivity = state_info["camera_motion_sensitivity"]
            if state_info["camera_volume"] is not None:
                hub.camera_volume = state_info["camera_volume"]
            if state_info["camera_sd_info"]:
                hub.camera_sd_info.update(state_info["camera_sd_info"])

        await hub.start()

        hass.data[DOMAIN][entry.entry_id]["hubs"][device_uuid] = hub

        platforms = _get_device_platforms(device_model, device_name)
        _LOGGER.info(
            "Qubo: device '%s' model=%s, platforms=%s",
            device_name, device_model, platforms,
        )
        all_platforms.update(platforms)

    # Clean up stale entities from wrong device types
    ent_reg = er.async_get(hass)
    for hub in hass.data[DOMAIN][entry.entry_id]["hubs"].values():
        if hub.is_camera:
            # Remove bulb-only entities that were incorrectly registered to camera
            for suffix in ("timer", "color_mode"):
                unique_id = f"{hub.device_uuid}_{suffix}"
                entity_id = ent_reg.async_get_entity_id(
                    "number" if suffix == "timer" else "select",
                    DOMAIN,
                    unique_id,
                )
                if entity_id:
                    ent_reg.async_remove(entity_id)
                    _LOGGER.info("Removed stale entity %s from camera device", entity_id)

    # Register custom PTZ services
    _register_ptz_services(hass, hass.data[DOMAIN][entry.entry_id]["hubs"])

    if all_platforms:
        await hass.config_entries.async_forward_entry_setups(entry, list(all_platforms))

    return True


def _register_ptz_services(hass, hubs):
    """Register Qubo PTZ start_pan/stop_pan services."""
    from homeassistant.exceptions import ServiceValidationError

    async def _find_hub_by_device_id(device_id: str):
        """Find hub by device UUID."""
        for hub in hubs.values():
            if hub.device_uuid == device_id:
                return hub
        raise ServiceValidationError(
            f"Qubo device not found: {device_id}"
        )

    SERVICE_PTZ_START = "qubo_ptz_start_pan"
    SERVICE_PTZ_STOP = "qubo_ptz_stop_pan"

    # Only register once
    if hass.services.has_service(DOMAIN, SERVICE_PTZ_START):
        return

    async def handle_ptz_start(call):
        hub = await _find_hub_by_device_id(call.data["device_id"])
        direction = call.data["direction"].upper()
        if direction not in ("UP", "DOWN", "LEFT", "RIGHT"):
            raise ServiceValidationError(
                f"Invalid direction: {direction}. Use UP, DOWN, LEFT, or RIGHT."
            )
        await hub.camera_ptz_start_pan(direction)

    async def handle_ptz_stop(call):
        hub = await _find_hub_by_device_id(call.data["device_id"])
        await hub.camera_ptz_stop_pan()

    hass.services.async_register(
        DOMAIN,
        SERVICE_PTZ_START,
        handle_ptz_start,
        schema=vol.Schema({
            vol.Required("device_id"): cv.string,
            vol.Required("direction"): vol.In(["UP", "DOWN", "LEFT", "RIGHT",
                                                 "up", "down", "left", "right"]),
        }),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PTZ_STOP,
        handle_ptz_stop,
        schema=vol.Schema({
            vol.Required("device_id"): cv.string,
        }),
    )
    _LOGGER.info("Qubo PTZ services registered: %s, %s", SERVICE_PTZ_START, SERVICE_PTZ_STOP)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hubs = hass.data[DOMAIN][entry.entry_id]["hubs"]

    all_platforms: set[str] = set()
    for hub in hubs.values():
        await hub.stop()
        platforms = _get_device_platforms(hub.device_model, hub.device_name)
        all_platforms.update(platforms)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, list(all_platforms))
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""
