"""Qubo button entities — metering refresh."""

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
    hub: QuboHub = hass.data[DOMAIN][entry.entry_id]["hub"]

    if hub.is_plug:
        async_add_entities([QuboRefreshMeteringButton(hub)])
    # Bulb: no buttons needed — colors/effects are in the light entity


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
