"""Constants for KiwiSDR integration."""
DOMAIN = "kiwisdr"

# Configuration
CONF_HOST = "host"
CONF_PORT = "port"
CONF_PASSWORD = "password"
CONF_ADMIN_PASSWORD = "admin_password"
CONF_NAME = "name"
CONF_ENABLE_AUDIO = "enable_audio"
CONF_ENABLE_WATERFALL = "enable_waterfall"

# Defaults
DEFAULT_PORT = 8073
DEFAULT_NAME = "KiwiSDR"
DEFAULT_SCAN_INTERVAL = 30

# WebSocket commands
WS_CMD_SET_FREQ = "SET freq={:.3f}"
WS_CMD_SET_MODE = "SET mod={}"
WS_CMD_SET_ZOOM = "SET zoom={}"
WS_CMD_SET_WF_SPEED = "SET wf_speed={}"
WS_CMD_GET_STATUS = "GET status"
WS_CMD_ADMIN_AUTH = "SET auth t=admin p={}"

# Audio parameters
AUDIO_SAMPLE_RATE = 12000
AUDIO_BUFFER_SIZE = 512

# Waterfall parameters
WATERFALL_WIDTH = 1024
WATERFALL_HEIGHT = 200
WATERFALL_UPDATE_INTERVAL = 1.0

# Sensor types
SENSOR_TYPES = {
    "status": {"name": "Status", "icon": "mdi:radio"},
    "users": {"name": "Active Users", "icon": "mdi:account-multiple"},
    "frequency": {"name": "Frequency", "unit": "kHz", "icon": "mdi:sine-wave"},
    "mode": {"name": "Mode", "icon": "mdi:access-point"},
    "bandwidth": {"name": "Bandwidth", "unit": "Hz", "icon": "mdi:speedometer"},
    "signal_strength": {"name": "Signal Strength", "unit": "dBm", "icon": "mdi:signal"},
    "uptime": {"name": "Uptime", "unit": "hours", "icon": "mdi:clock-outline"},
    "gps_status": {"name": "GPS Status", "icon": "mdi:satellite-variant"},
    "antenna": {"name": "Antenna", "icon": "mdi:antenna"},
    "adc_overload": {"name": "ADC Overload", "icon": "mdi:alert"},
}

# Modes
MODES = ["AM", "AMN", "USB", "LSB", "CW", "CWN", "FM", "IQ"]
