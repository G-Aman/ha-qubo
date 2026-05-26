"""Constants for the Qubo integration."""

DOMAIN = "qubo"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_DEVICE_UUID = "device_uuid"
BASE_URL = "https://srvcapp.platform.quboworld.com"
LOGIN_DEVICE_NAME = "HA-Qubo-Integration"
DEVICE_ATTRIBUTE = "HomeAssistant|Server|Integration"
APP_ID = "934488E68332E88B1E0F9AF552840184955629777525A195949C0BE97DEF6455"

# Device model codes
DEVICE_TYPE_PLUG = "smartPlug10A"
DEVICE_TYPE_BULBS = ("smartBulbWifi9W",)

# Platform lists per device type
PLATFORMS_BULB = ["light", "sensor", "binary_sensor", "number", "select"]
PLATFORMS_PLUG = ["switch", "sensor", "binary_sensor", "button"]

# Qubo color temperature range: CT 0=warm, 100=cool
# Mapped to HA kelvin: 0→2000K, 100→6535K
QUBO_COLOR_TEMP_MIN_KELVIN = 2000
QUBO_COLOR_TEMP_MAX_KELVIN = 6535

# Preset effect colors (Qubo format strings)
PRESET_COLORS = {
    "Green": "0,255,0,0,0,33",
    "Blue": "0,0,255,0,0,33",
    "Red": "255,0,0,0,0,33",
}

# Preset white/warmth scenes (Qubo format strings)
PRESET_WHITES = {
    "Warm White": "255,224,165,255,0,100,0.0,0.5",
    "Natural White": "255,255,255,255,255,100,0.5,0.5",
    "Cool White": "205,233,254,0,255,100,0.997,0.5",
}

# Combined effect list
EFFECT_LIST = list(PRESET_COLORS.keys()) + list(PRESET_WHITES.keys())

# MQTT broker
MQTT_HOST = "mqtt.platform.quboworld.com"
MQTT_PORT = 8883
