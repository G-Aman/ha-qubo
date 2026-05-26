"""Qubo binary sensor entities — online status + firmware update."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .hub import QuboHub


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up Qubo binary sensor entities."""
    hubs: dict[str, QuboHub] = hass.data[DOMAIN][entry.entry_id]["hubs"]
    entities = []
    for hub in hubs.values():
        entities.extend([
            QuboOnlineSensor(hub),
            QuboFirmwareUpdateSensor(hub),
        ])
    async_add_entities(entities)


class QuboOnlineSensor(BinarySensorEntity):
    """Binary sensor indicating if the Qubo device is online."""

    _attr_has_entity_name = True
    _attr_name = "Online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_should_poll = False

    def __init__(self, hub: QuboHub) -> None:
        """Initialize the online sensor."""
        self._hub = hub
        self._attr_unique_id = f"{hub.device_uuid}_online"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        model = self._hub.device_model or ("Smart Plug" if self._hub.is_plug else "Smart Bulb")
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.device_uuid)},
            name=self._hub.device_name,
            manufacturer="Qubo",
            model=model,
        )

    @property
    def is_on(self) -> bool:
        """Return True if the device is online."""
        return self._hub.online

    async def async_added_to_hass(self) -> None:
        """Register callback."""
        self._hub.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callback."""
        self._hub.unregister_callback(self.async_write_ha_state)


class QuboFirmwareUpdateSensor(BinarySensorEntity):
    """Binary sensor indicating if a firmware update is available."""

    _attr_has_entity_name = True
    _attr_name = "Firmware Update"
    _attr_device_class = BinarySensorDeviceClass.UPDATE
    _attr_should_poll = False

    def __init__(self, hub: QuboHub) -> None:
        """Initialize the firmware update sensor."""
        self._hub = hub
        self._attr_unique_id = f"{hub.device_uuid}_firmware_update"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        model = self._hub.device_model or ("Smart Plug" if self._hub.is_plug else "Smart Bulb")
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.device_uuid)},
            name=self._hub.device_name,
            manufacturer="Qubo",
            model=model,
        )

    @property
    def is_on(self) -> bool:
        """Return True if a firmware update is available."""
        return self._hub.firmware_update_available

    @property
    def extra_state_attributes(self) -> dict:
        """Return firmware version info."""
        return {"installed_version": self._hub.firmware_version}

    async def async_added_to_hass(self) -> None:
        """Register callback."""
        self._hub.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callback."""
        self._hub.unregister_callback(self.async_write_ha_state)
