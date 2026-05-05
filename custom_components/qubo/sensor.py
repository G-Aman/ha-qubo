"""Qubo sensor entities — plug metrics + WiFi info."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .hub import QuboHub


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up Qubo sensor entities."""
    hub: QuboHub = hass.data[DOMAIN][entry.entry_id]["hub"]

    entities = []

    if hub.is_plug:
        # Plug metering sensors
        entities.extend([
            QuboSensor(hub, "power", "Power", UnitOfPower.WATT,
                       SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
            QuboSensor(hub, "current", "Current", UnitOfElectricCurrent.AMPERE,
                       SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
            QuboSensor(hub, "voltage", "Voltage", UnitOfElectricPotential.VOLT,
                       SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
            QuboSensor(hub, "consumption", "Energy", UnitOfEnergy.KILO_WATT_HOUR,
                       SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING),
            QuboSensor(hub, "duration", "On Duration", UnitOfTime.SECONDS,
                       SensorDeviceClass.DURATION, SensorStateClass.MEASUREMENT),
        ])

    # WiFi info sensors (all device types)
    entities.extend([
        QuboWiFiSensor(hub, "ssid", "WiFi SSID", "mdi:wifi"),
        QuboWiFiSensor(hub, "ip", "IP Address", "mdi:ip-network"),
        QuboWiFiSensor(hub, "signal", "WiFi Signal", "mdi:wifi-strength-2",
                       SensorDeviceClass.SIGNAL_STRENGTH),
    ])

    async_add_entities(entities)


class QuboSensor(SensorEntity):
    """Representation of a Qubo plug metering sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        hub: QuboHub,
        metric_key: str,
        label: str,
        unit: str,
        device_class: str,
        state_class: str,
    ) -> None:
        """Initialize the sensor."""
        self._hub = hub
        self._metric_key = metric_key
        self._attr_name = label
        self._attr_unique_id = f"{hub.device_uuid}_{metric_key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.device_uuid)},
            name=self._hub.device_name,
            manufacturer="Qubo",
            model="Smart Plug",
        )

    @property
    def native_value(self):
        """Return the current sensor value."""
        return self._hub.metrics.get(self._metric_key)

    async def async_added_to_hass(self) -> None:
        """Register callback."""
        self._hub.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callback."""
        self._hub.unregister_callback(self.async_write_ha_state)


class QuboWiFiSensor(SensorEntity):
    """Representation of a Qubo WiFi info sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        hub: QuboHub,
        info_key: str,
        label: str,
        icon: str,
        device_class: str | None = None,
    ) -> None:
        """Initialize the WiFi sensor."""
        self._hub = hub
        self._info_key = info_key
        self._attr_name = label
        self._attr_unique_id = f"{hub.device_uuid}_wifi_{info_key}"
        self._attr_icon = icon
        if device_class:
            self._attr_device_class = device_class

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        model = "Smart Plug" if self._hub.is_plug else "Smart Bulb"
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.device_uuid)},
            name=self._hub.device_name,
            manufacturer="Qubo",
            model=model,
        )

    @property
    def native_value(self):
        """Return the WiFi info value."""
        return self._hub.wifi_info.get(self._info_key)

    async def async_added_to_hass(self) -> None:
        """Register callback."""
        self._hub.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callback."""
        self._hub.unregister_callback(self.async_write_ha_state)
