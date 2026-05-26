"""Qubo Smart Plug Switch Entity."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .hub import QuboHub


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Qubo switch platform from a config entry."""
    hubs: dict[str, QuboHub] = hass.data[DOMAIN][entry.entry_id]["hubs"]
    async_add_entities([
        QuboSwitch(hub) for hub in hubs.values() if hub.is_plug
    ])


class QuboSwitch(SwitchEntity):
    """Representation of a Qubo smart plug switch."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_icon = "mdi:power-plug"

    def __init__(self, hub: QuboHub) -> None:
        """Initialize the Qubo switch entity."""
        self._hub = hub
        self._attr_unique_id = hub.device_uuid

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the switch."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.device_uuid)},
            name=self._hub.device_name,
            manufacturer="Qubo",
            model="Smart Plug",
        )

    @property
    def is_on(self) -> bool:
        """Return True if the switch is on."""
        return self._hub.state

    @property
    def should_poll(self) -> bool:
        """Return False - updates come via MQTT."""
        return False

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        await self._hub.turn_on()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        await self._hub.turn_off()

    async def async_added_to_hass(self) -> None:
        """Register the hub callback when the entity is added."""
        self._hub.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister the hub callback when the entity is removed."""
        self._hub.unregister_callback(self.async_write_ha_state)
