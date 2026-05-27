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
    entities = []
    for hub in hubs.values():
        if hub.is_plug:
            entities.append(QuboSwitch(hub))
        elif hub.is_camera:
            entities.extend([
                QuboCameraSwitch(hub, "motion_tracking", "Motion Tracking",
                                 "motionTracking", "mdi:motion-sensor"),
                QuboCameraSwitch(hub, "continuous_recording", "Continuous Recording",
                                 "continuousRecording", "mdi:record-rec"),
                QuboCameraSwitch(hub, "image_analytics", "AI Detection",
                                 "aisetting", "mdi:brain"),
                QuboCameraSwitch(hub, "cloud_dvr", "Cloud DVR",
                                 "cloudDvr", "mdi:cloud-upload"),
            ])
    async_add_entities(entities)


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


class QuboCameraSwitch(SwitchEntity):
    """Representation of a Qubo camera toggle switch."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    # Map attr_key → (hub attribute name, on_value, off_value)
    _SERVICE_MAP = {
        "motion_tracking": ("camera_motion_tracking", True, False),
        "continuous_recording": ("camera_continuous_recording", True, False),
        "image_analytics": ("camera_image_analytics", True, False),
        "cloud_dvr": ("camera_cloud_dvr", True, False),
    }

    def __init__(
        self,
        hub: QuboHub,
        attr_key: str,
        label: str,
        service_name: str,
        icon: str,
    ) -> None:
        """Initialize the camera switch."""
        self._hub = hub
        self._attr_key = attr_key
        self._attr_name = label
        self._service_name = service_name
        self._attr_unique_id = f"{hub.device_uuid}_cam_{attr_key}"
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

    @property
    def is_on(self) -> bool:
        """Return True if the switch is on."""
        hub_attr = self._SERVICE_MAP.get(self._attr_key, (None,))[0]
        if hub_attr:
            return getattr(self._hub, hub_attr, False)
        return False

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on."""
        setter = getattr(self._hub, f"camera_set_{self._attr_key}", None)
        if setter:
            await setter(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off."""
        setter = getattr(self._hub, f"camera_set_{self._attr_key}", None)
        if setter:
            await setter(False)

    async def async_added_to_hass(self) -> None:
        """Register callback."""
        self._hub.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callback."""
        self._hub.unregister_callback(self.async_write_ha_state)
