"""Camera platform for Qubo integration."""

import asyncio
import logging
import time
from datetime import timedelta

from homeassistant.components.camera import Camera, CameraEntityFeature, StreamType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    APP_ID,
    BASE_URL,
    CAMERA_MODELS,
    DOMAIN,
    LOGIN_DEVICE_NAME,
    SP_ID,
)

_LOGGER = logging.getLogger(__name__)


def is_camera_device(device_model: str, device_name: str = "") -> bool:
    """Check if a device model is a camera."""
    combined = (device_model + device_name).lower()
    return (
        device_model in CAMERA_MODELS
        or "camera" in combined
        or "doorbell" in combined
        or "cam" in combined
        or "ptz" in combined
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Qubo cameras from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    hubs = data["hubs"]
    cameras = []

    for device_uuid, hub in hubs.items():
        if hub.is_camera:
            cameras.append(
                QuboCamera(
                    hass=hass,
                    hub=hub,
                    entry=entry,
                )
            )

    if cameras:
        async_add_entities(cameras)


class QuboCamera(Camera):
    """Representation of a Qubo camera."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        hass: HomeAssistant,
        hub,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the Qubo camera."""
        super().__init__()
        self.hass = hass
        self._hub = hub
        self._entry = entry

        # Stream state
        self._stream_url: str | None = None
        self._session_id: str | None = None
        self._stream_expires_at: float = 0

        # Tell HA this camera supports HLS streaming
        self._attr_frontend_stream_type = StreamType.HLS
        self._attr_supported_features = CameraEntityFeature.STREAM

        # Snapshot cache (unused — HA stream integration handles snapshots)
        # Stream refresh timer
        self._unsub_stream_refresh = None

        # Retry state
        self._retry_count: int = 0
        self._last_fetch_attempt: float = 0

    @property
    def device_info(self) -> dict:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._hub.device_uuid)},
            "name": self._hub.device_name,
            "manufacturer": "Qubo (Hero Electronix)",
            "model": self._hub.device_model,
        }

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"qubo_camera_{self._hub.device_uuid}"

    @property
    def is_recording(self) -> bool:
        """Return true if the device is recording."""
        return self._hub.camera_continuous_recording

    @property
    def is_streaming(self) -> bool:
        """Return true if the device is streaming."""
        return self._stream_url is not None and time.time() < self._stream_expires_at

    @property
    def brand(self) -> str:
        """Return the brand."""
        return "Qubo"

    @property
    def model(self) -> str:
        """Return the model."""
        return self._hub.device_model

    async def _async_ensure_token(self) -> None:
        """Ensure we have a valid access token."""
        await self._hub._async_refresh_token_if_needed()

    async def _async_get_stream_url(self) -> str:
        """Get a fresh RTSPS stream URL from the Qubo API."""
        await self._async_ensure_token()
        token = self._hub._access_token
        user_uuid = self._hub._user_uuid
        client_id = self._hub._client_id

        session = async_get_clientsession(self.hass)
        url = (
            f"{BASE_URL}/stream-manager/api/v1/sp/{SP_ID}"
            f"/stream/unit/{self._hub._unit_uuid}"
            f"/device/{self._hub.device_uuid}"
            f"?timestamp=NOW&type=high&streamSourceCamera=primary"
            f"&deviceType={self._hub.device_model}"
        )

        headers = {
            "Host": "srvcapp.platform.quboworld.com",
            "User-Agent": "libcurl-agent restclient-cpp/2:1:1",
            "Accept": "*/*",
            "Content-Type": "application/json",
            "App-Id": APP_ID,
            "Login-Device-Name": LOGIN_DEVICE_NAME,
            "Source": "ANDROID",
            "Source-Device-Id": client_id,
            "Subscriber-Key": token,
            "Token-Type": "USER",
            "User-UUID": user_uuid,
        }

        body = {"userAppID": client_id}

        async with session.post(url, json=body, headers=headers) as response:
            if response.status >= 400:
                text = await response.text()
                raise RuntimeError(
                    f"Failed to get stream URL: {response.status} - {text}"
                )
            data = await response.json()

        stream_url = data.get("streamURL")
        session_id = data.get("appSessionId")
        if not stream_url:
            raise RuntimeError(f"API response missing streamURL: {data}")

        self._stream_url = stream_url
        self._session_id = session_id
        # Use API-provided TTL if available, fallback to 15 min
        ttl_seconds = data.get("ttl", data.get("expiresIn", 900))
        self._stream_expires_at = time.time() + ttl_seconds - 60  # 60s safety margin
        self._retry_count = 0

        _LOGGER.warning(
            "Qubo camera stream URL obtained: session=%s url=%s ttl=%ss",
            self._session_id,
            self._stream_url,
            ttl_seconds,
        )
        self.async_write_ha_state()
        return self._stream_url  # type: ignore[return-value]

    async def _async_stop_stream(self) -> None:
        """Stop the current stream session."""
        if not self._session_id:
            return

        await self._async_ensure_token()
        token = self._hub._access_token
        user_uuid = self._hub._user_uuid
        client_id = self._hub._client_id

        session = async_get_clientsession(self.hass)
        url = (
            f"{BASE_URL}/stream-manager/api/v2/sp/{SP_ID}"
            f"/stream/unit/{self._hub._unit_uuid}"
            f"/device/{self._hub.device_uuid}"
        )

        headers = {
            "Host": "srvcapp.platform.quboworld.com",
            "User-Agent": "libcurl-agent restclient-cpp/2:1:1",
            "App-Id": APP_ID,
            "Source": "ANDROID",
            "Source-Device-Id": client_id,
            "Subscriber-Key": token,
            "Token-Type": "USER",
            "User-UUID": user_uuid,
        }

        params = {
            "appSessionId": self._session_id,
            "type": "low",
            "userAppID": client_id,
        }

        try:
            async with session.delete(url, headers=headers, params=params) as resp:
                _LOGGER.debug("Stream stop response: %s", resp.status)
        except Exception as err:
            _LOGGER.debug("Error stopping stream: %s", err)
        finally:
            self._session_id = None
            self._stream_url = None
            self._stream_expires_at = 0
            self.async_write_ha_state()

    async def stream_source(self) -> str | None:
        """Return the stream source URL (RTSPS).

        HA's stream integration takes this URL and transcodes it to HLS
        for the frontend player.
        """
        if self._stream_url and time.time() < self._stream_expires_at:
            return self._stream_url

        # Rate-limit retries: max 1 attempt per 10 seconds
        now = time.time()
        if now - self._last_fetch_attempt < 10 and self._retry_count >= 2:
            return self._stream_url  # Return stale URL as last resort (better than None)
        self._last_fetch_attempt = now

        # Try up to 2 times with brief delay
        for attempt in range(2):
            try:
                url = await self._async_get_stream_url()
                return url
            except Exception as err:
                self._retry_count += 1
                _LOGGER.warning(
                    "Stream URL fetch attempt %d failed: %s", attempt + 1, err
                )
                if attempt == 0:
                    await asyncio.sleep(2)

        # Both attempts failed — return stale URL if available
        if self._stream_url:
            _LOGGER.warning("Using stale stream URL after failed refresh")
            return self._stream_url
        return None

    # async_camera_image is intentionally NOT overridden.
    # HA's built-in stream integration (declared as a dependency) will
    # extract snapshots from the RTSPS URL returned by stream_source().
    # The previous manual ffmpeg approach produced corrupt 0.03kb files.

    async def async_turn_on(self) -> None:
        """Turn on the camera stream."""
        try:
            await self._async_get_stream_url()
        except Exception as err:
            _LOGGER.warning("Failed to start Qubo camera stream: %s", err)

    async def async_turn_off(self) -> None:
        """Turn off the camera stream."""
        await self._async_stop_stream()

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        # Eagerly fetch the stream URL so it's ready when the frontend asks
        try:
            await self._async_get_stream_url()
        except Exception as err:
            _LOGGER.warning("Initial stream fetch failed (will retry on demand): %s", err)

        # Refresh stream URL every 10 minutes (before ~15-min TTL)
        self._unsub_stream_refresh = async_track_time_interval(
            self.hass,
            self._refresh_stream,
            timedelta(minutes=10),
        )

    async def _refresh_stream(self, now=None) -> None:
        """Periodically refresh the stream URL (non-destructive with rollback)."""
        old_url = self._stream_url
        old_session = self._session_id
        old_expires = self._stream_expires_at

        try:
            # Stop old session but keep the URL as fallback
            try:
                await self._async_stop_stream()
            except Exception:
                pass

            await self._async_get_stream_url()
            _LOGGER.debug("Qubo camera stream refreshed")
        except Exception as err:
            _LOGGER.warning("Failed to refresh Qubo camera stream: %s", err)
            # Rollback so stream_source() can still return the old URL
            self._stream_url = old_url
            self._session_id = old_session
            self._stream_expires_at = old_expires

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is removed."""
        if self._unsub_stream_refresh:
            self._unsub_stream_refresh()
        await self._async_stop_stream()
