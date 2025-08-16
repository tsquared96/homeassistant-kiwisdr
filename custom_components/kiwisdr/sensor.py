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
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, SENSOR_TYPES, DEFAULT_SCAN_INTERVAL, CONF_HOST, CONF_PORT, CONF_NAME

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
            
            # Ensure we have values for all sensor types
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
                "users_max": status.get("users_max", 4),
            }
            
            _LOGGER.debug("Updated data: %s", data)
            return data
            
        except Exception as err:
            _LOGGER.error("Error fetching KiwiSDR data: %s", err)
            # Return offline status on error
            return {
                "status": "Offline",
                "users": 0,
                "frequency": 0,
                "mode": "Unknown",
                "bandwidth": 0,
                "signal_strength": 0,
                "uptime": 0,
                "gps_status": "Unknown",
                "antenna": "Unknown",
                "adc_overload": False,
                "users_max": 0,
            }

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
        
        # Create unique entity ID
        self._attr_unique_id = f"{entry.entry_id}_{sensor_type}"
        
        # Set name
        name_prefix = entry.data.get(CONF_NAME, 'KiwiSDR')
        self._attr_name = f"{name_prefix} {sensor_config['name']}"
        
        # Set other attributes
        self._attr_icon = sensor_config.get("icon")
        self._attr_unit_of_measurement = sensor_config.get("unit")
        
        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=name_prefix,
            manufacturer="KiwiSDR",
            model="Software Defined Radio",
            configuration_url=f"http://{entry.data.get(CONF_HOST)}:{entry.data.get(CONF_PORT, 8073)}"
        )
        
        _LOGGER.debug("Created sensor: %s", self._attr_name)
    
    @property
    def state(self):
        """Return the state of the sensor."""
        value = self.coordinator.data.get(self._sensor_type)
        
        # Format specific sensor types
        if self._sensor_type == "uptime" and value:
            # Convert uptime to hours if it's in seconds
            if value > 3600:
                value = round(value / 3600, 1)
            
        _LOGGER.debug("Sensor %s state: %s", self._sensor_type, value)
        return value
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.coordinator.data.get("status") == "Online"
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "host": self._entry.data.get(CONF_HOST),
            "port": self._entry.data.get(CONF_PORT, 8073),
        }
        
        # Add max users for users sensor
        if self._sensor_type == "users":
            attrs["max_users"] = self.coordinator.data.get("users_max", 4)
            attrs["slots_available"] = self.coordinator.data.get("users_max", 4) - self.coordinator.data.get("users", 0)
        
        # Add connection URL
        if self._sensor_type == "status":
            attrs["url"] = f"http://{self._entry.data.get(CONF_HOST)}:{self._entry.data.get(CONF_PORT, 8073)}"
        
        return attrs
