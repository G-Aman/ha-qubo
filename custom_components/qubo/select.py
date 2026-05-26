"""Qubo select entity — color mode selector (bulb only)."""

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .hub import QuboHub

COLOR_MODES = {"cw": "White", "rgb": "Color"}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up Qubo select entities."""
    hubs: dict[str, QuboHub] = hass.data[DOMAIN][entry.entry_id]["hubs"]
    async_add_entities([
        QuboColorModeSelect(hub) for hub in hubs.values() if hub.is_bulb
    ])


class QuboColorModeSelect(SelectEntity):
    """Select entity for bulb color mode (White / Color)."""

    _attr_has_entity_name = True
    _attr_name = "Color Mode"
    _attr_icon = "mdi:palette-swatch"
    _attr_options = list(COLOR_MODES.values())
    _attr_should_poll = False

    def __init__(self, hub: QuboHub) -> None:
        """Initialize the color mode select."""
        self._hub = hub
        self._attr_unique_id = f"{hub.device_uuid}_color_mode"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.device_uuid)},
            name=self._hub.device_name,
            manufacturer="Qubo",
            model="Smart Bulb",
        )

    @property
    def current_option(self) -> str:
        """Return the current color mode."""
        return COLOR_MODES.get(self._hub.color_mode_str, "White")

    async def async_select_option(self, option: str) -> None:
        """Set the color mode."""
        mode = next(
            (k for k, v in COLOR_MODES.items() if v == option), "cw"
        )
        await self._hub.set_color_mode(mode)

    async def async_added_to_hass(self) -> None:
        """Register callback."""
        self._hub.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callback."""
        self._hub.unregister_callback(self.async_write_ha_state)
