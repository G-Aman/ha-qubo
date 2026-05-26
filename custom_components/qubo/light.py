"""Qubo Smart Bulb Light Entity."""

import logging

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DOMAIN,
    EFFECT_LIST,
    QUBO_COLOR_TEMP_MAX_KELVIN,
    QUBO_COLOR_TEMP_MIN_KELVIN,
    PRESET_COLORS,
    PRESET_WHITES,
)
from .hub import QuboHub, kelvin_to_qubo_ct

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Qubo light platform."""
    hubs: dict[str, QuboHub] = hass.data[DOMAIN][entry.entry_id]["hubs"]
    async_add_entities([
        QuboLight(hub) for hub in hubs.values() if not hub.is_plug and not hub.is_camera
    ])


class QuboLight(LightEntity):
    """Representation of a Qubo smart bulb with full color support."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_icon = "mdi:lightbulb"

    # Color modes: RGB for full color, COLOR_TEMP for white/warmth
    _attr_supported_color_modes = {ColorMode.RGB, ColorMode.COLOR_TEMP}
    _attr_color_mode = ColorMode.COLOR_TEMP  # default
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = EFFECT_LIST

    # Qubo CT range mapped to kelvin
    _attr_min_color_temp_kelvin = QUBO_COLOR_TEMP_MIN_KELVIN
    _attr_max_color_temp_kelvin = QUBO_COLOR_TEMP_MAX_KELVIN

    def __init__(self, hub: QuboHub) -> None:
        """Initialize the light entity."""
        self._hub = hub
        self._attr_unique_id = f"{hub.device_uuid}_light"
        self._attr_brightness = 255
        self._attr_rgb_color = (255, 255, 255)
        self._attr_color_temp_kelvin = 4000
        self._attr_effect = None

        # Apply initial state from hub
        if hub.brightness is not None:
            self._attr_brightness = hub.brightness
        if hub.rgb_color is not None:
            self._attr_rgb_color = hub.rgb_color
        if hub.color_temp_kelvin is not None:
            self._attr_color_temp_kelvin = hub.color_temp_kelvin
        self._update_color_mode(hub.color_mode_str)

    def _update_color_mode(self, mode_str: str) -> None:
        """Update the HA color mode based on Qubo mode string."""
        if mode_str == "rgb":
            self._attr_color_mode = ColorMode.RGB
        else:
            self._attr_color_mode = ColorMode.COLOR_TEMP

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
    def is_on(self) -> bool:
        """Return True if the light is on."""
        return self._hub.state

    @property
    def should_poll(self) -> bool:
        """Return False - updates come via MQTT."""
        return False

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on with optional attributes."""
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._attr_brightness)
        brightness_pct = int(brightness / 2.55)

        if ATTR_EFFECT in kwargs:
            effect_name = kwargs[ATTR_EFFECT]
            await self._apply_effect(effect_name, brightness_pct)
            return

        if ATTR_RGB_COLOR in kwargs:
            r, g, b = kwargs[ATTR_RGB_COLOR]
            self._attr_rgb_color = (r, g, b)
            self._attr_color_mode = ColorMode.RGB
            # Switch to RGB mode, then set color
            await self._hub.set_color_mode("rgb")
            color_str = f"{r},{g},{b},0,0,{brightness_pct}"
            await self._hub.set_color_rgb(color_str)
            self._hub.brightness = brightness
            return

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            self._attr_color_temp_kelvin = kelvin
            self._attr_color_mode = ColorMode.COLOR_TEMP
            # Switch to CW mode, then set warmth
            await self._hub.set_color_mode("cw")
            ct = kelvin_to_qubo_ct(kelvin)
            warmth = ct / 100.0
            color_str = (
                f"255,224,165,255,0,{ct},{brightness_pct},{warmth}"
            )
            await self._hub.set_color_warmth(color_str)
            self._hub.brightness = brightness
            return

        if ATTR_BRIGHTNESS in kwargs:
            # Brightness-only change - send in current mode
            if self._attr_color_mode == ColorMode.RGB and self._attr_rgb_color:
                r, g, b = self._attr_rgb_color
                await self._hub.set_color_mode("rgb")
                color_str = f"{r},{g},{b},0,0,{brightness_pct}"
                await self._hub.set_color_rgb(color_str)
            else:
                kelvin = self._attr_color_temp_kelvin
                ct = kelvin_to_qubo_ct(kelvin)
                warmth = ct / 100.0
                await self._hub.set_color_mode("cw")
                color_str = (
                    f"255,224,165,255,0,{ct},{brightness_pct},{warmth}"
                )
                await self._hub.set_color_warmth(color_str)
            self._hub.brightness = brightness
            return

        # No color/brightness attrs - just turn on
        await self._hub.turn_on()

    async def _apply_effect(self, effect_name: str, brightness_pct: int) -> None:
        """Apply a preset effect."""
        if effect_name in PRESET_COLORS:
            await self._hub.set_color_mode("rgb")
            # Use the preset but override brightness
            parts = PRESET_COLORS[effect_name].split(",")
            r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
            self._attr_rgb_color = (r, g, b)
            self._attr_color_mode = ColorMode.RGB
            color_str = f"{r},{g},{b},0,0,{brightness_pct}"
            await self._hub.set_color_rgb(color_str)
        elif effect_name in PRESET_WHITES:
            await self._hub.set_color_mode("cw")
            self._attr_color_mode = ColorMode.COLOR_TEMP
            # Build a warmth string with the requested brightness
            parts = PRESET_WHITES[effect_name].split(",")
            ct = int(parts[5])
            warmth = parts[7]
            self._attr_color_temp_kelvin = _qubo_ct_to_kelvin(ct)
            color_str = (
                f"{parts[0]},{parts[1]},{parts[2]},{parts[3]},{parts[4]},"
                f"{ct},{brightness_pct},{warmth}"
            )
            await self._hub.set_color_warmth(color_str)
        self._attr_effect = effect_name
        self._hub.brightness = int(brightness_pct * 2.55)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        await self._hub.turn_off()

    async def async_added_to_hass(self) -> None:
        """Register callback for state updates."""
        self._hub.register_callback(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callback."""
        self._hub.unregister_callback(self._handle_update)

    def _handle_update(self) -> None:
        """Handle state updates from hub via MQTT."""
        if self._hub.brightness is not None:
            self._attr_brightness = self._hub.brightness
        if self._hub.rgb_color is not None:
            self._attr_rgb_color = self._hub.rgb_color
        if self._hub.color_temp_kelvin is not None:
            self._attr_color_temp_kelvin = self._hub.color_temp_kelvin
        self._update_color_mode(self._hub.color_mode_str)
        self.async_write_ha_state()


def _qubo_ct_to_kelvin(ct: int) -> int:
    """Convert Qubo CT (0-100) to kelvin."""
    return int(
        QUBO_COLOR_TEMP_MIN_KELVIN
        + (ct / 100.0)
        * (QUBO_COLOR_TEMP_MAX_KELVIN - QUBO_COLOR_TEMP_MIN_KELVIN)
    )
