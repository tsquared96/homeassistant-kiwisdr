from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up sensor platform."""
    sensors = [YourSensor(entry)]
    async_add_entities(sensors)

class YourSensor(SensorEntity):
    """Representation of a sensor."""
    
    def __init__(self, entry):
        """Initialize the sensor."""
        self._attr_name = "Your Sensor"
        self._attr_unique_id = "your_sensor_unique_id"
        self._state = None
    
    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state
    
    async def async_update(self):
        """Fetch new state data."""
        # Update self._state with your logic
        self._state = "some_value"
