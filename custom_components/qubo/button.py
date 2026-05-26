"""Qubo button entities — metering refresh (plug) + camera controls."""

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .hub import QuboHub

# PTZ direction presets: (horizontal, vertical)
PTZ_DIRECTIONS = {
    "ptz_up": ("PTZ Up", "mdi:arrow-up", 0, 50),
    "ptz_down": ("PTZ Down", "mdi:arrow-down", 0, -50),
    "ptz_left": ("PTZ Left", "mdi:arrow-left", -50, 0),
    "ptz_right": ("PTZ Right", "mdi:arrow-right", 50, 0),
    "ptz_home": ("PTZ Home", "mdi:home", 0, 0),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up Qubo button entities."""
    hubs: dict[str, QuboHub] = hass.data[DOMAIN][entry.entry_id]["hubs"]
    entities = []
    for hub in hubs.values():
        if hub.is_plug:
            entities.append(QuboRefreshMeteringButton(hub))
        elif hub.is_camera:
            entities.append(QuboCameraRebootButton(hub))
            for key, (label, icon, h, v) in PTZ_DIRECTIONS.items():
                entities.append(QuboCameraPTZButton(hub, key, label, icon, h, v))
    async_add_entities(entities)


class QuboRefreshMeteringButton(ButtonEntity):
    """Button to manually refresh plug metering data."""

    _attr_has_entity_name = True
    _attr_name = "Refresh Metering"
    _attr_icon = "mdi:refresh"
    _attr_device_class = ButtonDeviceClass.UPDATE

    def __init__(self, hub: QuboHub) -> None:
        """Initialize the button."""
        self._hub = hub
        self._attr_unique_id = f"{hub.device_uuid}_refresh_metering"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.device_uuid)},
            name=self._hub.device_name,
            manufacturer="Qubo",
            model="Smart Plug",
        )

    async def async_press(self) -> None:
        """Trigger a metering refresh."""
        await self._hub.refresh_metering()


class QuboCameraRebootButton(ButtonEntity):
    """Button to reboot the camera."""

    _attr_has_entity_name = True
    _attr_name = "Reboot"
    _attr_icon = "mdi:restart"
    _attr_device_class = ButtonDeviceClass.RESTART

    def __init__(self, hub: QuboHub) -> None:
        """Initialize the button."""
        self._hub = hub
        self._attr_unique_id = f"{hub.device_uuid}_cam_reboot"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.device_uuid)},
            name=self._hub.device_name,
            manufacturer="Qubo",
            model=self._hub.device_model,
        )

    async def async_press(self) -> None:
        """Reboot the camera."""
        await self._hub.camera_reboot()


class QuboCameraPTZButton(ButtonEntity):
    """Button to move camera PTZ in a direction."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        hub: QuboHub,
        key: str,
        label: str,
        icon: str,
        h: int,
        v: int,
    ) -> None:
        """Initialize the PTZ button."""
        self._hub = hub
        self._h = h
        self._v = v
        self._attr_name = label
        self._attr_unique_id = f"{hub.device_uuid}_{key}"
        self._attr_icon = icon

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.device_uuid)},
            name=self._hub.device_name,
            manufacturer="Qubo",
            model=self._hub.device_model,
        )

    async def async_press(self) -> None:
        """Move PTZ in the configured direction."""
        await self._hub.camera_ptz_move(self._h, self._v)
