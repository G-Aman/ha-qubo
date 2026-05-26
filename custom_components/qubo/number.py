"""Qubo number entities — timer (bulb) + volume (camera)."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .hub import QuboHub


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up Qubo number entities."""
    hubs: dict[str, QuboHub] = hass.data[DOMAIN][entry.entry_id]["hubs"]
    entities = []
    for hub in hubs.values():
        if hub.is_bulb:
            entities.append(QuboTimerNumber(hub))
        elif hub.is_camera:
            entities.append(QuboCameraVolumeNumber(hub))
    async_add_entities(entities)


class QuboTimerNumber(NumberEntity):
    """Number entity for auto-off timer (0-1440 minutes)."""

    _attr_has_entity_name = True
    _attr_name = "Auto-Off Timer"
    _attr_icon = "mdi:timer-outline"
    _attr_native_min_value = 0
    _attr_native_max_value = 1440
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.SLIDER

    def __init__(self, hub: QuboHub) -> None:
        """Initialize the timer number entity."""
        self._hub = hub
        self._attr_unique_id = f"{hub.device_uuid}_timer"

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
    def native_value(self) -> float:
        """Return the current timer duration in minutes."""
        return float(self._hub.timer_duration)

    async def async_set_native_value(self, value: float) -> None:
        """Set the auto-off timer duration."""
        await self._hub.set_timer(int(value))

    async def async_added_to_hass(self) -> None:
        """Register callback."""
        self._hub.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callback."""
        self._hub.unregister_callback(self.async_write_ha_state)


class QuboCameraVolumeNumber(NumberEntity):
    """Number entity for camera speaker volume (0-100)."""

    _attr_has_entity_name = True
    _attr_name = "Volume"
    _attr_icon = "mdi:volume-high"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 5
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, hub: QuboHub) -> None:
        """Initialize."""
        self._hub = hub
        self._attr_unique_id = f"{hub.device_uuid}_cam_volume"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.device_uuid)},
            name=self._hub.device_name,
            manufacturer="Qubo",
            model=self._hub.device_model,
        )

    @property
    def native_value(self) -> float:
        """Return current volume."""
        return float(self._hub.camera_volume)

    async def async_set_native_value(self, value: float) -> None:
        """Set volume."""
        await self._hub.camera_set_volume(int(value))

    async def async_added_to_hass(self) -> None:
        """Register callback."""
        self._hub.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callback."""
        self._hub.unregister_callback(self.async_write_ha_state)
