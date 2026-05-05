"""Qubo button entities — metering refresh + scene activation."""

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, EFFECT_LIST
from .hub import QuboHub


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up Qubo button entities."""
    hub: QuboHub = hass.data[DOMAIN][entry.entry_id]["hub"]

    entities = []

    if hub.is_plug:
        entities.append(QuboRefreshMeteringButton(hub))
    else:
        # Bulb: one button per preset scene
        for scene_name in EFFECT_LIST:
            entities.append(QuboSceneButton(hub, scene_name))

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


class QuboSceneButton(ButtonEntity):
    """Button to activate a preset scene on a Qubo bulb."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:palette"

    def __init__(self, hub: QuboHub, scene_name: str) -> None:
        """Initialize the scene button."""
        self._hub = hub
        self._scene_name = scene_name
        self._attr_name = scene_name
        self._attr_unique_id = f"{hub.device_uuid}_scene_{scene_name.lower().replace(' ', '_')}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.device_uuid)},
            name=self._hub.device_name,
            manufacturer="Qubo",
            model="Smart Bulb",
        )

    async def async_press(self) -> None:
        """Activate the preset scene."""
        await self._hub.activate_scene(self._scene_name)
