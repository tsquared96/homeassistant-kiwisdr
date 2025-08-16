"""Sensor platform for KiwiSDR."""
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN, SENSOR_TYPES, DEFAULT_SCAN_INTERVAL, CONF_HOST

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up KiwiSDR sensor based on a config entry."""
    
    _LOGGER.debug("Setting up KiwiSDR sensors for %s", entry.data.get(CONF_HOST))
    
    # Get the API instance
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    
    # Create update coordinator
    coordinator = KiwiSDRCoordinator(hass, api, entry)
    
    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()
    
    # Create sensors
    sensors = []
    for sensor_type, sensor_config in SENSOR_TYPES.items():
        _LOGGER.debug("Creating sensor: %s", sensor_type)
        sensors.append(KiwiSDRSensor(coordinator, entry, sensor_type, sensor_config))
    
    async_add_entities(sensors, True)
    _LOGGER.info("Added %d KiwiSDR sensors", len(sensors))

class KiwiSDRCoordinator(DataUpdateCoordinator):
    """Class to manage fetching KiwiSDR data."""
    
    def __init__(self, hass: HomeAssistant, api, entry: ConfigEntry):
        """Initialize."""
        self.api = api
        self.entry = entry
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"KiwiSDR {entry.data.get(CONF_HOST)}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
    
    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from KiwiSDR."""
        try:
            _LOGGER.debug("Fetching KiwiSDR data")
            status = await self.api.get_status()
            
            # Ensure we have default values for all sensor types
            data = {
                "status": "Online" if status.get("online", False) else "Offline",
                "users": status.get("users", 0),
                "frequency": status.get("frequency", 0),
                "mode": status.get("mode", "Unknown"),
                "bandwidth": status.get("bandwidth", 0),
                "signal_strength": status.get("signal_strength", 0),
                "uptime": status.get("uptime", 0),
                "gps_status": status.get("gps_status", "Unknown"),
                "antenna": status.get("antenna", "Unknown"),
                "adc_overload": status.get("adc_overload", False),
            }
            
            _LOGGER.debug("Updated data: %s", data)
            return data
            
        except Exception as err:
            _LOGGER.error("Error fetching KiwiSDR data: %s", err)
            raise UpdateFailed(f"Error communicating with KiwiSDR: {err}")

class KiwiSDRSensor(CoordinatorEntity, SensorEntity):
    """Representation of a KiwiSDR sensor."""
    
    def __init__(
        self,
        coordinator: KiwiSDRCoordinator,
        entry: ConfigEntry,
        sensor_type: str,
        sensor_config: Dict[str, Any],
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._sensor_type = sensor_type
        self._sensor_config = sensor_config
        
        # Create unique entity ID and name
        name_prefix = entry.data.get('name', 'KiwiSDR')
        self._attr_unique_id = f"kiwisdr_{entry.entry_id}_{sensor_type}"
        self._attr_name = f"{name_prefix} {sensor_config['name']}"
        
        # Set entity ID explicitly (this is what you'll see in HA)
        self.entity_id = f"sensor.kiwisdr_{sensor_type}"
        
        self._attr_icon = sensor_config.get("icon")
        self._attr_unit_of_measurement = sensor_config.get("unit")
        
        _LOGGER.debug("Created sensor: %s with entity_id: %s", 
                     self._attr_name, self.entity_id)
    
    @property
    def state(self):
        """Return the state of the sensor."""
        value = self.coordinator.data.get(self._sensor_type)
        _LOGGER.debug("Sensor %s state: %s", self._sensor_type, value)
        return value
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "host": self._entry.data.get(CONF_HOST),
            "port": self._entry.data.get("port", 8073),
        }
        
        # Add user list if this is the users sensor
        if self._sensor_type == "users" and "users_list" in self.coordinator.data:
            attrs["users_list"] = self.coordinator.data["users_list"]
        
        return attrs
