"""Number platform for KiwiSDR frequency tuning."""
import logging
from typing import Optional

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import UnitOfFrequency

from .const import DOMAIN, CONF_HOST, CONF_PORT, CONF_NAME

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up KiwiSDR number entities."""

    api = hass.data[DOMAIN][entry.entry_id]["api"]

    numbers = [
        KiwiSDRFrequencyNumber(hass, entry, api),
    ]

    async_add_entities(numbers, True)

    _LOGGER.info("Added KiwiSDR number entities for %s", entry.data.get(CONF_HOST))

class KiwiSDRFrequencyNumber(NumberEntity):
    """Representation of KiwiSDR frequency control."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api):
        """Initialize the number entity."""
        self.hass = hass
        self._entry = entry
        self._api = api
        self._value = 7074.0  # Default FT8 frequency
        self._mode = "USB"

        # Set entity attributes
        self._attr_unique_id = f"{entry.entry_id}_frequency"
        self._attr_name = f"{entry.data.get(CONF_NAME, 'KiwiSDR')} Frequency"
        self._attr_native_min_value = 0.0
        self._attr_native_max_value = 30000.0
        self._attr_native_step = 0.1
        self._attr_mode = NumberMode.BOX
        self._attr_native_unit_of_measurement = "kHz"
        self._attr_icon = "mdi:radio-tower"

        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, 'KiwiSDR'),
            manufacturer="KiwiSDR",
            model="Software Defined Radio",
            configuration_url=f"http://{entry.data.get(CONF_HOST)}:{entry.data.get(CONF_PORT, 8073)}"
        )

        # Store reference for media player sync
        hass.data[DOMAIN][entry.entry_id]['frequency_number'] = self

    @property
    def native_value(self) -> float:
        """Return the current frequency."""
        # Sync with API status if available
        if hasattr(self._api, 'current_status') and self._api.current_status.get('frequency', 0) > 0:
            self._value = self._api.current_status['frequency']
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        """Set new frequency value."""
        try:
            # Get current mode from media player if available
            media_player = self.hass.data[DOMAIN][self._entry.entry_id].get('media_player')
            if media_player:
                self._mode = media_player._mode

            # Tune to new frequency
            success = await self._api.tune(value, self._mode)

            if success:
                self._value = value

                # Update media player if available
                if media_player:
                    media_player._frequency = value
                    media_player.async_write_ha_state()

                self.async_write_ha_state()
                _LOGGER.info("Frequency tuned to %s kHz", value)
            else:
                _LOGGER.error("Failed to tune to %s kHz", value)

        except Exception as e:
            _LOGGER.error("Error setting frequency: %s", e)

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        return {
            "mode": self._mode,
            "websocket_connected": bool(self._api.websocket and self._api.websocket.ws),
        }
