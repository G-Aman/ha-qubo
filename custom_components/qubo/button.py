"""Qubo button entities — metering refresh (plug) + reboot (camera)."""

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .hub import QuboHub


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
