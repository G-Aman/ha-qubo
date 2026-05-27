"""Qubo hub integration helper for Home Assistant."""

from datetime import timedelta
import json
import logging
import ssl
import time

import aiohttp
import paho.mqtt.client as mqtt

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    BASE_URL,
    CAMERA_MODELS,
    DEVICE_TYPE_BULBS,
    DEVICE_TYPE_PLUG,
    LOGIN_DEVICE_NAME,
    MQTT_HOST,
    MQTT_PORT,
)

_LOGGER = logging.getLogger(__name__)


class QuboHub:
    """Qubo hub - one per device, handles MQTT and state tracking."""

    def __init__(
        self,
        hass: HomeAssistant,
        session,
        access_token: str,
        refresh_token: str,
        user_uuid: str,
        device_uuid: str,
        unit_uuid: str,
        expires_at: float,
        initial_state: bool,
        device_name: str,
        handle_name: str,
        client_id: str,
        device_model: str,
    ) -> None:
        """Initialize the Qubo hub."""
        self.hass = hass
        self.session = session
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._expires_at = expires_at

        self._user_uuid = user_uuid
        self.device_uuid = device_uuid
        self._unit_uuid = unit_uuid
        self.device_name = device_name
        self._handle_name = handle_name
        self._client_id = client_id
        self.device_model = device_model

        # Common state
        self.state = initial_state
        # Detect plug: exact model match OR keyword in name/model
        self.is_plug = (
            device_model == DEVICE_TYPE_PLUG
            or any(
                kw in (device_model + device_name).lower()
                for kw in ("plug", "socket", "smartplug")
            )
        )

        # Detect camera
        combined = (device_model + device_name).lower()
        self.is_camera = (
            device_model in CAMERA_MODELS
            or any(kw in combined for kw in ("camera", "doorbell", "cam", "ptz"))
        )

        # Detect bulb: exact model match OR keyword (only if not camera)
        self.is_bulb = (
            not self.is_plug
            and not self.is_camera
            and (
                device_model in DEVICE_TYPE_BULBS
                or any(kw in combined for kw in ("bulb", "light", "lamp", "hlb"))
            )
        )

        # Bulb state
        self.color_mode_str: str = "cw"
        self.brightness: int | None = None
        self.rgb_color: tuple[int, int, int] | None = None
        self.color_temp_kelvin: int | None = None

        # Plug metering
        self.metrics: dict[str, float | None] = {
            "power": None,
            "current": None,
            "voltage": None,
            "consumption": None,
            "duration": None,
        }

        # Camera state
        self.camera_motion_tracking: bool = False
        self.camera_continuous_recording: bool = False
        self.camera_image_analytics: bool = False
        self.camera_night_mode: str = "auto"
        self.camera_motion_sensitivity: str = "HIGH_SENSITIVITY"
        self.camera_volume: int = 50
        self.camera_ptz_position: str = ""
        self.camera_cloud_dvr: bool = False
        self.camera_sd_info: dict[str, str | None] = {
            "total": None,
            "available": None,
            "status": None,
        }

        # WiFi info (all devices)
        self.wifi_info: dict[str, str | None] = {
            "ssid": None,
            "ip": None,
            "signal": None,
        }

        # Online status and firmware (all devices)
        self.online: bool = True
        self.firmware_update_available: bool = False
        self.firmware_version: str | None = None

        # Timer (bulb only)
        self.timer_duration: int = 0  # minutes, 0 = off

        self._callbacks: set = set()
        self._unsub_refresh = None

        # MQTT topics
        self._topic_control_switch = (
            f"/control/{unit_uuid}/{device_uuid}/lcSwitchControl"
        )
        self._topic_monitor_switch = (
            f"/monitor/{unit_uuid}/{device_uuid}/lcSwitchControl"
        )
        self._topic_control_meter = (
            f"/control/{unit_uuid}/{device_uuid}/meteringRefresh"
        )
        self._topic_monitor_meter = (
            f"/monitor/{unit_uuid}/{device_uuid}/plugMetering"
        )

        # MQTT client
        self._mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self._mqtt_client.username_pw_set(
            username=self._user_uuid, password=self._access_token
        )
        self._mqtt_client.on_connect = self._on_connect
        self._mqtt_client.on_message = self._on_message

    def register_callback(self, callback) -> None:
        """Register a callback to be called when the state updates."""
        self._callbacks.add(callback)

    def unregister_callback(self, callback) -> None:
        """Unregister a callback."""
        self._callbacks.discard(callback)

    def _publish_update(self) -> None:
        """Notify all registered callbacks of a state change."""
        for callback in self._callbacks:
            callback()

    def _on_connect(self, client, userdata, flags, rc) -> None:
        """Handle MQTT connection."""
        if rc == 0:
            unit = self._unit_uuid
            dev = self.device_uuid
            topics = [
                (self._topic_monitor_switch, 0),
                # Common services for all device types
                (f"/monitor/{unit}/{dev}/wifiSettings", 0),
                (f"/monitor/{unit}/{dev}/upgradeAvailable", 0),
                (f"/monitor/{unit}/{dev}/heartbeat", 0),
            ]
            if self.is_plug:
                topics.append((self._topic_monitor_meter, 0))
            elif self.is_bulb:
                topics.extend([
                    (f"/monitor/{unit}/{dev}/colorModeControl", 0),
                    (f"/monitor/{unit}/{dev}/colorRGBControl", 0),
                    (f"/monitor/{unit}/{dev}/colorWarmthControl", 0),
                ])
            elif self.is_camera:
                topics.extend([
                    (f"/monitor/{unit}/{dev}/motionTracking", 0),
                    (f"/monitor/{unit}/{dev}/continuousRecording", 0),
                    (f"/monitor/{unit}/{dev}/aisetting", 0),
                    (f"/monitor/{unit}/{dev}/nightModeControl", 0),
                    (f"/monitor/{unit}/{dev}/recordingConfig", 0),
                    (f"/monitor/{unit}/{dev}/volumeControl", 0),
                    (f"/monitor/{unit}/{dev}/panTiltControl", 0),
                    (f"/monitor/{unit}/{dev}/panTiltPreset", 0),
                    (f"/monitor/{unit}/{dev}/systemDiagnosis", 0),
                    (f"/monitor/{unit}/{dev}/cloudDvrControl", 0),
                    (f"/monitor/{unit}/{dev}/streamControl", 0),
                ])
            client.subscribe(topics)
            _LOGGER.debug("MQTT connected and subscribed for %s", self.device_name)
            self.online = True
            self.hass.loop.call_soon_threadsafe(self._publish_update)

    def _on_message(self, client, userdata, msg) -> None:
        """Handle incoming MQTT messages."""
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            topic = msg.topic

            if topic == self._topic_monitor_switch:
                self._handle_switch_update(payload)
            elif self.is_plug and topic == self._topic_monitor_meter:
                self._handle_metering_update(payload)
            elif topic.endswith("/wifiSettings"):
                self._handle_wifi_update(payload)
            elif topic.endswith("/upgradeAvailable"):
                self._handle_upgrade_update(payload)
            elif topic.endswith("/heartbeat"):
                self.online = True
                self.hass.loop.call_soon_threadsafe(self._publish_update)
            elif self.is_bulb:
                if topic.endswith("/colorModeControl"):
                    self._handle_color_mode_update(payload)
                elif topic.endswith("/colorRGBControl"):
                    self._handle_rgb_update(payload)
                elif topic.endswith("/colorWarmthControl"):
                    self._handle_warmth_update(payload)
            elif self.is_camera:
                self._handle_camera_update(topic, payload)

        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as err:
            _LOGGER.debug("Error parsing MQTT message: %s", err)

    def _handle_switch_update(self, payload: dict) -> None:
        """Parse switch state from MQTT payload."""
        state_data = (
            payload.get("devices", {})
            .get("services", {})
            .get("lcSwitchControl", {})
            .get("events", {})
            .get("stateChanged", {})
        )
        if "power" in state_data:
            self.state = state_data["power"] == "on"
            self.hass.loop.call_soon_threadsafe(self._publish_update)

    def _handle_metering_update(self, payload: dict) -> None:
        """Parse plug metering data from MQTT payload."""
        metrics_data = (
            payload.get("devices", {})
            .get("services", {})
            .get("plugMetering", {})
            .get("events", {})
            .get("stateChanged", {})
        )
        if metrics_data:
            self.metrics["power"] = float(metrics_data.get("power", 0))
            self.metrics["current"] = float(metrics_data.get("current", 0))
            self.metrics["consumption"] = float(
                metrics_data.get("consumption", 0)
            )
            self.metrics["duration"] = int(metrics_data.get("duration", 0))
            new_voltage = float(metrics_data.get("voltage", 0))
            if new_voltage > 50:
                self.metrics["voltage"] = new_voltage
            self.hass.loop.call_soon_threadsafe(self._publish_update)

    def _handle_color_mode_update(self, payload: dict) -> None:
        """Parse color mode change from MQTT payload."""
        mode_data = (
            payload.get("devices", {})
            .get("services", {})
            .get("colorModeControl", {})
            .get("events", {})
            .get("stateChanged", {})
        )
        if "mode" in mode_data:
            self.color_mode_str = mode_data["mode"]
            self.hass.loop.call_soon_threadsafe(self._publish_update)

    def _handle_rgb_update(self, payload: dict) -> None:
        """Parse RGB color change from MQTT payload."""
        rgb_data = (
            payload.get("devices", {})
            .get("services", {})
            .get("colorRGBControl", {})
            .get("events", {})
            .get("stateChanged", {})
        )
        if "color" in rgb_data:
            self._parse_rgb(rgb_data["color"])
            self.hass.loop.call_soon_threadsafe(self._publish_update)

    def _handle_warmth_update(self, payload: dict) -> None:
        """Parse warmth/color-temp change from MQTT payload."""
        warmth_data = (
            payload.get("devices", {})
            .get("services", {})
            .get("colorWarmthControl", {})
            .get("events", {})
            .get("stateChanged", {})
        )
        if "color" in warmth_data:
            self._parse_warmth(warmth_data["color"])
            self.hass.loop.call_soon_threadsafe(self._publish_update)

    def _handle_wifi_update(self, payload: dict) -> None:
        """Parse wifiSettings from MQTT payload."""
        wifi_data = (
            payload.get("devices", {})
            .get("services", {})
            .get("wifiSettings", {})
            .get("events", {})
            .get("stateChanged", {})
        )
        if wifi_data:
            if "ssid" in wifi_data:
                self.wifi_info["ssid"] = wifi_data["ssid"]
            if "ip" in wifi_data:
                self.wifi_info["ip"] = wifi_data["ip"]
            if "signalStrength" in wifi_data:
                self.wifi_info["signal"] = wifi_data["signalStrength"]
            _LOGGER.debug("WiFi updated: %s", self.wifi_info)
            self.hass.loop.call_soon_threadsafe(self._publish_update)

    def _handle_upgrade_update(self, payload: dict) -> None:
        """Parse upgradeAvailable from MQTT payload."""
        upgrade_data = (
            payload.get("devices", {})
            .get("services", {})
            .get("upgradeAvailable", {})
            .get("events", {})
            .get("stateChanged", {})
        )
        if upgrade_data:
            available = str(upgrade_data.get("available", "false")).lower()
            self.firmware_update_available = available in ("true", "1", "yes")
            _LOGGER.debug(
                "Firmware update available: %s", self.firmware_update_available
            )
            self.hass.loop.call_soon_threadsafe(self._publish_update)

    def _parse_rgb(self, color_str: str) -> None:
        """Parse Qubo RGB color string 'R,G,B,W,CW,CT' to HA rgb_color."""
        if not color_str:
            return
        parts = color_str.split(",")
        if len(parts) >= 3:
            r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
            self.rgb_color = (r, g, b)
        if len(parts) >= 6:
            ct = int(parts[5])
            self.brightness = int(ct * 2.55)

    def _parse_warmth(self, color_str: str) -> None:
        """Parse Qubo warmth string 'R,G,B,W,CW,CT,brightness,warmth'."""
        if not color_str:
            return
        parts = color_str.split(",")
        if len(parts) >= 8:
            brightness_pct = int(float(parts[6]))
            self.brightness = int(brightness_pct * 2.55)
            ct = int(parts[5])
            self.color_temp_kelvin = _qubo_ct_to_kelvin(ct)
        elif len(parts) >= 6:
            ct = int(parts[5])
            self.color_temp_kelvin = _qubo_ct_to_kelvin(ct)

    def _handle_camera_update(self, topic: str, payload: dict) -> None:
        """Parse camera MQTT messages and update state."""
        svc_data = (
            payload.get("devices", {})
            .get("services", {})
        )
        # Extract the service name from topic
        svc_name = topic.rsplit("/", 1)[-1] if "/" in topic else ""
        state = svc_data.get(svc_name, {}).get("events", {}).get("stateChanged", {})
        if not state:
            return

        if svc_name == "motionTracking":
            self.camera_motion_tracking = str(state.get("enabled", "")).lower() == "true"
        elif svc_name == "continuousRecording":
            self.camera_continuous_recording = str(state.get("enabled", "")).lower() == "true"
        elif svc_name == "aisetting":
            self.camera_image_analytics = str(state.get("state", "")).lower() == "enable"
        elif svc_name == "nightModeControl":
            self.camera_night_mode = state.get("mpc_nightMode", state.get("nightModeView", state.get("nightMode", self.camera_night_mode)))
        elif svc_name == "recordingConfig":
            self.camera_motion_sensitivity = state.get("motionSensitivity", self.camera_motion_sensitivity)
        elif svc_name == "volumeControl":
            try:
                self.camera_volume = int(state.get("level", self.camera_volume))
            except (ValueError, TypeError):
                pass
        elif svc_name == "panTiltControl":
            self.camera_ptz_position = state.get("horizontalVerticalPostion", self.camera_ptz_position)
        elif svc_name == "cloudDvrControl":
            self.camera_cloud_dvr = str(state.get("state", "")).lower() == "enable"
        elif svc_name == "systemDiagnosis":
            if "totalExternalStorage" in state:
                self.camera_sd_info["total"] = state["totalExternalStorage"]
            if "availableExternalStorage" in state:
                self.camera_sd_info["available"] = state["availableExternalStorage"]
            if "SdCardAvailability" in state:
                self.camera_sd_info["status"] = state["SdCardAvailability"]
            if "sdCardStatus" in state:
                # Append detailed card health if available (e.g. statusOK, noSpaceAvailable)
                self.camera_sd_info["sdcard_status"] = state["sdCardStatus"]

        self.hass.loop.call_soon_threadsafe(self._publish_update)

    # ── Camera control methods ─────────────────────────────────────

    async def camera_set_motion_tracking(self, enabled: bool) -> None:
        """Enable/disable motion tracking."""
        await self._async_refresh_token_if_needed()
        self._publish_service("motionTracking", {"enabled": str(enabled).lower()})

    async def camera_set_continuous_recording(self, enabled: bool) -> None:
        """Enable/disable continuous recording."""
        await self._async_refresh_token_if_needed()
        self._publish_service("continuousRecording", {"enabled": str(enabled).lower()})

    async def camera_set_image_analytics(self, enabled: bool) -> None:
        """Enable/disable AI image analytics."""
        await self._async_refresh_token_if_needed()
        self._publish_service("aisetting", {"state": "enable" if enabled else "disable"})

    async def camera_set_night_mode(self, mode: str) -> None:
        """Set night mode: 'auto', 'on', 'off'."""
        await self._async_refresh_token_if_needed()
        self._publish_service("nightModeControl", {"mpc_nightMode": mode})

    async def camera_set_motion_sensitivity(self, level: str) -> None:
        """Set motion sensitivity: HIGH_SENSITIVITY, MEDIUM_SENSITIVITY, LOW_SENSITIVITY."""
        await self._async_refresh_token_if_needed()
        self._publish_service("recordingConfig", {"motionSensitivity": level})

    async def camera_set_volume(self, level: int) -> None:
        """Set camera volume 0-100."""
        await self._async_refresh_token_if_needed()
        self._publish_service("volumeControl", {"level": str(level)})

    async def camera_ptz_move(self, h: int, v: int) -> None:
        """Move PTZ. h: -100 to 100 (left/right), v: -100 to 100 (up/down)."""
        await self._async_refresh_token_if_needed()
        self._publish_service("panTiltControl", {"horizontalVerticalPostion": f"{h},{v}"})

    async def camera_ptz_start_pan(self, direction: str) -> None:
        """Start continuous PTZ movement. direction: UP, DOWN, LEFT, RIGHT."""
        await self._async_refresh_token_if_needed()
        self._publish_command("panTiltControl", "startPan", {"direction": direction})

    async def camera_ptz_stop_pan(self) -> None:
        """Stop continuous PTZ movement."""
        await self._async_refresh_token_if_needed()
        self._publish_command("panTiltControl", "stopPan")

    async def camera_set_cloud_dvr(self, enabled: bool) -> None:
        """Enable/disable cloud DVR."""
        await self._async_refresh_token_if_needed()
        self._publish_service("cloudDvrControl", {"state": "enable" if enabled else "disable"})

    async def camera_reboot(self) -> None:
        """Reboot the camera."""
        await self._async_refresh_token_if_needed()
        self._publish_service("deviceReboot", {"commands": "reboot"})

    async def _send_sdcard_refresh(self, now=None) -> None:
        """Request SD card storage status from a camera (systemDiagnosis)."""
        await self._async_refresh_token_if_needed()
        topic = f"/control/{self._unit_uuid}/{self.device_uuid}/systemDiagnosis"
        payload = {
            "devices": {
                "deviceUUID": self.device_uuid,
                "services": {
                    "systemDiagnosis": {
                        "commands": {
                            "getExternalStorageStatus": {
                                "instanceId": "0",
                                "parameters": {},
                            }
                        }
                    }
                },
            },
        }
        self._mqtt_client.publish(topic, json.dumps(payload))
        _LOGGER.debug("Sent getExternalStorageStatus for %s", self.device_name)

    # ── MQTT connection lifecycle ────────────────────────────────────

    async def start(self) -> None:
        """Start the MQTT connection."""
        def connect_mqtt():
            self._mqtt_client.tls_set(cert_reqs=ssl.CERT_NONE)
            self._mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
            self._mqtt_client.loop_start()

        await self.hass.async_add_executor_job(connect_mqtt)

        if self.is_plug:
            await self._send_meter_refresh()
            self._unsub_refresh = async_track_time_interval(
                self.hass, self._send_meter_refresh, timedelta(seconds=60)
            )

        if self.is_camera:
            await self._send_sdcard_refresh()
            self._unsub_refresh = async_track_time_interval(
                self.hass, self._send_sdcard_refresh, timedelta(seconds=60)
            )

    async def stop(self) -> None:
        """Stop the MQTT connection."""
        if self._unsub_refresh:
            self._unsub_refresh()
        self._mqtt_client.loop_stop()
        self._mqtt_client.disconnect()

    # ── Token refresh ────────────────────────────────────────────────

    async def _async_refresh_token_if_needed(self) -> None:
        """Refresh the access token if it has expired."""
        if time.time() < self._expires_at:
            return

        _LOGGER.info("Qubo access token expired. Refreshing")
        refresh_url = (
            f"{BASE_URL}/sms/api/v1/sp/"
            f"d10e4bfb0153496e8e8bb955f7ebe413/"
            f"users/{self._user_uuid}/auth/refresh"
        )
        payload = {
            "accessToken": self._access_token,
            "refreshToken": self._refresh_token,
        }
        headers = {
            "Host": "srvcapp.platform.quboworld.com",
            "User-Agent": "libcurl-agent restclient-cpp/2:1:1",
            "Accept": "*/*",
            "Login-Device-Name": LOGIN_DEVICE_NAME,
            "Source-Device-Id": self._client_id,
            "Token-Type": "USER",
        }

        try:
            async with self.session.post(
                refresh_url, json=payload, headers=headers
            ) as response:
                response.raise_for_status()
                data = await response.json()

                self._access_token = data.get("accessToken", self._access_token)
                self._refresh_token = data.get("refreshToken", self._refresh_token)
                expires_in = data.get("expires_in", 3600)
                self._expires_at = time.time() + expires_in - 60

                _LOGGER.debug("Token refreshed successfully")

                def restart_mqtt():
                    _LOGGER.debug("Rebooting MQTT client with new token")
                    self._mqtt_client.loop_stop()
                    self._mqtt_client.disconnect()
                    self._mqtt_client.username_pw_set(
                        username=self._user_uuid,
                        password=self._access_token,
                    )
                    self._mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
                    self._mqtt_client.loop_start()
                    _LOGGER.info("MQTT connection successfully restored")

                await self.hass.async_add_executor_job(restart_mqtt)

        except (aiohttp.ClientError, Exception) as err:
            _LOGGER.error("Failed to refresh Qubo token: %s", err)

    # ── Command helpers ──────────────────────────────────────────────

    def _build_command(self, service: str, attributes: dict) -> str:
        """Build an MQTT command payload for a service."""
        payload = {
            "command": {
                "devices": {
                    "deviceUUID": self.device_uuid,
                    "handleName": self._handle_name,
                    "services": {
                        service: {
                            "attributes": attributes,
                            "instanceId": 0,
                        }
                    },
                }
            },
            "deviceUUID": self.device_uuid,
            "msgSequenceId": int(time.time() * 1000),
            "srcDeviceId": self._client_id,
            "timestamp": int(time.time() * 1000),
        }
        return json.dumps(payload)

    def _publish_service(self, service: str, attributes: dict) -> None:
        """Publish a command to a service topic."""
        topic = f"/control/{self._unit_uuid}/{self.device_uuid}/{service}"
        payload = self._build_command(service, attributes)
        self._mqtt_client.publish(topic, payload)

    def _publish_command(self, service: str, command_name: str, parameters: dict = None) -> None:
        """Publish a commands-based (not attributes-based) MQTT payload."""
        topic = f"/control/{self._unit_uuid}/{self.device_uuid}/{service}"
        payload = {
            "command": {
                "devices": {
                    "deviceUUID": self.device_uuid,
                    "handleName": self._handle_name,
                    "services": {
                        service: {
                            "commands": {
                                command_name: {
                                    "parameters": parameters or {},
                                    "instanceId": 0,
                                }
                            }
                        }
                    },
                }
            },
            "deviceUUID": self.device_uuid,
            "msgSequenceId": int(time.time() * 1000),
            "srcDeviceId": self._client_id,
            "timestamp": int(time.time() * 1000),
        }
        self._mqtt_client.publish(topic, json.dumps(payload))

    # ── Public control methods ───────────────────────────────────────

    async def turn_on(self) -> None:
        """Turn the device on."""
        await self._async_refresh_token_if_needed()
        self._publish_service("lcSwitchControl", {"power": "on"})

    async def turn_off(self) -> None:
        """Turn the device off."""
        await self._async_refresh_token_if_needed()
        self._publish_service("lcSwitchControl", {"power": "off"})

    async def set_color_mode(self, mode: str) -> None:
        """Set color mode: 'cw' (white) or 'rgb' (color)."""
        await self._async_refresh_token_if_needed()
        self.color_mode_str = mode
        self._publish_service("colorModeControl", {"mode": mode})

    async def set_color_rgb(self, color_str: str) -> None:
        """Set RGB color. Format: 'R,G,B,W,CW,CT'."""
        await self._async_refresh_token_if_needed()
        self._publish_service("colorRGBControl", {"color": color_str})

    async def set_color_warmth(self, color_str: str) -> None:
        """Set white mode color. Format: 'R,G,B,W,CW,CT,brightness,warmth'."""
        await self._async_refresh_token_if_needed()
        self._publish_service("colorWarmthControl", {"color": color_str})

    async def set_timer(self, minutes: int) -> None:
        """Set auto-off timer (0-1440 min). 0 = cancel."""
        await self._async_refresh_token_if_needed()
        self.timer_duration = minutes
        self._publish_service(
            "countdownTimerControl", {"duration": str(minutes)}
        )
        self.hass.loop.call_soon_threadsafe(self._publish_update)

    async def refresh_metering(self) -> None:
        """Manually trigger a metering refresh (plug)."""
        await self._send_meter_refresh()

    async def activate_scene(self, scene_name: str) -> None:
        """Activate a preset scene by name."""
        await self._async_refresh_token_if_needed()
        from .const import PRESET_COLORS, PRESET_WHITES

        if scene_name in PRESET_COLORS:
            await self.set_color_mode("rgb")
            await self.set_color_rgb(PRESET_COLORS[scene_name])
        elif scene_name in PRESET_WHITES:
            await self.set_color_mode("cw")
            await self.set_color_warmth(PRESET_WHITES[scene_name])

    async def _send_meter_refresh(self, now=None) -> None:
        """Request metering data from a smart plug."""
        await self._async_refresh_token_if_needed()
        self._publish_service("meteringRefresh", {"duration": "60"})


# ── Color conversion helpers ──────────────────────────────────────────


def _qubo_ct_to_kelvin(ct: int) -> int:
    """Convert Qubo CT (0=warm, 100=cool) to HA color_temp_kelvin."""
    from .const import QUBO_COLOR_TEMP_MIN_KELVIN, QUBO_COLOR_TEMP_MAX_KELVIN
    kelvin = QUBO_COLOR_TEMP_MIN_KELVIN + (ct / 100.0) * (
        QUBO_COLOR_TEMP_MAX_KELVIN - QUBO_COLOR_TEMP_MIN_KELVIN
    )
    return int(kelvin)


def kelvin_to_qubo_ct(kelvin: int) -> int:
    """Convert HA color_temp_kelvin to Qubo CT (0=warm, 100=cool)."""
    from .const import QUBO_COLOR_TEMP_MIN_KELVIN, QUBO_COLOR_TEMP_MAX_KELVIN
    ct = (kelvin - QUBO_COLOR_TEMP_MIN_KELVIN) / (
        QUBO_COLOR_TEMP_MAX_KELVIN - QUBO_COLOR_TEMP_MIN_KELVIN
    ) * 100
    return max(0, min(100, int(ct)))
