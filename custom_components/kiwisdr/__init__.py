"""The KiwiSDR integration."""
import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_extract_entity_ids

from .const import (
    DOMAIN, CONF_HOST, CONF_PORT, CONF_PASSWORD, CONF_ADMIN_PASSWORD,
    CONF_NAME, CONF_ENABLE_AUDIO, CONF_ENABLE_WATERFALL, MODES
)
from .kiwisdr_api import KiwiSDRAPI
from .stream_view import KiwiSDRAudioStreamView

_LOGGER = logging.getLogger(__name__)

# Preset stations
PRESET_STATIONS = {
    "WWV 2.5 MHz": {"frequency": 2500.0, "mode": "AM"},
    "WWV 5 MHz": {"frequency": 5000.0, "mode": "AM"},
    "WWV 10 MHz": {"frequency": 10000.0, "mode": "AM"},
    "WWV 15 MHz": {"frequency": 15000.0, "mode": "AM"},
    "CHU 3.33 MHz": {"frequency": 3330.0, "mode": "AM"},
    "CHU 7.85 MHz": {"frequency": 7850.0, "mode": "AM"},
    "BBC 5.875 MHz": {"frequency": 5875.0, "mode": "AM"},
    "FT8 3.573 MHz": {"frequency": 3573.0, "mode": "USB"},
    "FT8 7.074 MHz": {"frequency": 7074.0, "mode": "USB"},
    "FT8 14.074 MHz": {"frequency": 14074.0, "mode": "USB"},
    "WSPR 7.0386 MHz": {"frequency": 7038.6, "mode": "USB"},
    "WSPR 14.0956 MHz": {"frequency": 14095.6, "mode": "USB"},
    "CB Channel 19": {"frequency": 27185.0, "mode": "AM"},
    "Air Band": {"frequency": 121500.0, "mode": "AM"},
    "Marine VHF": {"frequency": 156800.0, "mode": "FM"},
}

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.MEDIA_PLAYER,
    Platform.CAMERA,
    Platform.NUMBER,
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up KiwiSDR from a config entry."""
    
    _LOGGER.info("Setting up KiwiSDR integration for %s", entry.data.get(CONF_HOST))
    
    # Create API instance
    api = KiwiSDRAPI(
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, 8073),
        password=entry.data.get(CONF_PASSWORD),
        admin_password=entry.data.get(CONF_ADMIN_PASSWORD)
    )
    
    # Test connection
    if not await api.test_connection():
        _LOGGER.error("Failed to connect to KiwiSDR at %s:%s", 
                     entry.data[CONF_HOST], entry.data.get(CONF_PORT, 8073))
        return False
    
    # Connect WebSocket
    websocket_connected = await api.connect_websocket()
    if not websocket_connected:
        _LOGGER.warning("WebSocket connection failed, some features will be limited")
    
    # Store the API instance
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "entry": entry,
    }

    # Register audio stream view (once for all instances)
    if 'stream_view_registered' not in hass.data[DOMAIN]:
        stream_view = KiwiSDRAudioStreamView(hass)
        hass.http.register_view(stream_view)
        hass.data[DOMAIN]['stream_view_registered'] = True
        _LOGGER.info("Registered KiwiSDR audio stream view")

    # Setup platforms
    platforms_to_setup = [Platform.SENSOR, Platform.NUMBER]

    if entry.data.get(CONF_ENABLE_AUDIO, True):
        platforms_to_setup.append(Platform.MEDIA_PLAYER)

    if entry.data.get(CONF_ENABLE_WATERFALL, True):
        platforms_to_setup.append(Platform.CAMERA)

    await hass.config_entries.async_forward_entry_setups(entry, platforms_to_setup)
    
    # Register services
    await _register_services(hass)
    
    # Set initial frequency to a known station (7074 kHz FT8)
    await api.tune(7074.0, "USB")
    _LOGGER.info("Initial tune to 7074.0 kHz USB (FT8)")
    
    return True

async def _register_services(hass: HomeAssistant):
    """Register KiwiSDR services."""
    
    async def get_api_for_entity(entity_id: str):
        """Get API instance for a specific entity."""
        for entry_id, data in hass.data[DOMAIN].items():
            # Check if this entity belongs to this entry
            if entity_id and entry_id in entity_id:
                return data["api"]
        # Return first available API if no specific entity
        if hass.data[DOMAIN]:
            return next(iter(hass.data[DOMAIN].values()))["api"]
        return None
    
    async def handle_tune(call: ServiceCall):
        """Handle tune service."""
        frequency = call.data.get("frequency")
        mode = call.data.get("mode", "AM").upper()
        
        # Get target entities
        entity_ids = await async_extract_entity_ids(hass, call)
        
        if entity_ids:
            for entity_id in entity_ids:
                api = await get_api_for_entity(entity_id)
                if api:
                    success = await api.tune(frequency, mode)
                    if success:
                        _LOGGER.info("Tuned %s to %s kHz %s", entity_id, frequency, mode)
                    else:
                        _LOGGER.error("Failed to tune %s", entity_id)
        else:
            # Apply to all KiwiSDRs
            for data in hass.data[DOMAIN].values():
                api = data["api"]
                await api.tune(frequency, mode)
    
    async def handle_set_mode(call: ServiceCall):
        """Handle set mode service."""
        mode = call.data.get("mode").upper()
        
        entity_ids = await async_extract_entity_ids(hass, call)
        for entity_id in entity_ids:
            api = await get_api_for_entity(entity_id)
            if api and api.websocket:
                await api.websocket.send_command(f"SET mode={mode.lower()}")
                _LOGGER.info("Set mode to %s", mode)
    
    async def handle_set_bandwidth(call: ServiceCall):
        """Handle bandwidth setting."""
        low_cut = call.data.get("low_cut")
        high_cut = call.data.get("high_cut")
        
        for data in hass.data[DOMAIN].values():
            api = data["api"]
            if api.websocket:
                await api.websocket.send_command(f"SET low_cut={low_cut} high_cut={high_cut}")
                _LOGGER.info("Set bandwidth: %d to %d Hz", low_cut, high_cut)
    
    async def handle_set_agc(call: ServiceCall):
        """Handle AGC settings."""
        enabled = call.data.get("enabled")
        hang = call.data.get("hang", False)
        threshold = call.data.get("threshold", -100)
        
        for data in hass.data[DOMAIN].values():
            api = data["api"]
            await api.set_agc(enabled, hang)
            if api.websocket:
                await api.websocket.send_command(f"SET agc_thresh={threshold}")
            _LOGGER.info("Set AGC: enabled=%s, hang=%s, threshold=%d", enabled, hang, threshold)
    
    async def handle_set_squelch(call: ServiceCall):
        """Handle squelch setting."""
        level = call.data.get("level")
        
        for data in hass.data[DOMAIN].values():
            api = data["api"]
            await api.set_squelch(level)
            _LOGGER.info("Set squelch to %d", level)
    
    async def handle_waterfall_settings(call: ServiceCall):
        """Handle waterfall settings."""
        for data in hass.data[DOMAIN].values():
            api = data["api"]
            
            if "zoom" in call.data:
                await api.set_zoom(call.data["zoom"])
            
            if "speed" in call.data:
                await api.set_waterfall_speed(call.data["speed"])
            
            if "colormap" in call.data and api.websocket:
                await api.websocket.send_command(f"SET colormap={call.data['colormap']}")
    
    async def handle_tune_preset(call: ServiceCall):
        """Handle tuning to preset stations."""
        preset_name = call.data.get("preset")

        if preset_name in PRESET_STATIONS:
            preset = PRESET_STATIONS[preset_name]
            for data in hass.data[DOMAIN].values():
                api = data["api"]
                await api.tune(preset["frequency"], preset["mode"])
                _LOGGER.info("Tuned to preset: %s (%s kHz %s)",
                           preset_name, preset["frequency"], preset["mode"])

    async def handle_step_frequency_up(call: ServiceCall):
        """Handle stepping frequency up."""
        step = call.data.get("step", 1.0)

        entity_ids = await async_extract_entity_ids(hass, call)
        for entity_id in entity_ids:
            api = await get_api_for_entity(entity_id)
            if api:
                # Get current frequency
                current_freq = api.current_status.get("frequency", 7074.0)
                new_freq = min(current_freq + step, 30000.0)

                # Get current mode
                current_mode = api.current_status.get("mode", "USB")

                success = await api.tune(new_freq, current_mode)
                if success:
                    _LOGGER.info("Stepped frequency up to %s kHz", new_freq)

                    # Update number entity if available
                    entry_data = next((data for entry_id, data in hass.data[DOMAIN].items()
                                     if entry_id in entity_id and isinstance(data, dict)), None)
                    if entry_data and 'frequency_number' in entry_data:
                        entry_data['frequency_number']._value = new_freq
                        entry_data['frequency_number'].async_write_ha_state()

    async def handle_step_frequency_down(call: ServiceCall):
        """Handle stepping frequency down."""
        step = call.data.get("step", 1.0)

        entity_ids = await async_extract_entity_ids(hass, call)
        for entity_id in entity_ids:
            api = await get_api_for_entity(entity_id)
            if api:
                # Get current frequency
                current_freq = api.current_status.get("frequency", 7074.0)
                new_freq = max(current_freq - step, 0.0)

                # Get current mode
                current_mode = api.current_status.get("mode", "USB")

                success = await api.tune(new_freq, current_mode)
                if success:
                    _LOGGER.info("Stepped frequency down to %s kHz", new_freq)

                    # Update number entity if available
                    entry_data = next((data for entry_id, data in hass.data[DOMAIN].items()
                                     if entry_id in entity_id and isinstance(data, dict)), None)
                    if entry_data and 'frequency_number' in entry_data:
                        entry_data['frequency_number']._value = new_freq
                        entry_data['frequency_number'].async_write_ha_state()

    # Register all services - check each individually to ensure they all get registered
    if not hass.services.has_service(DOMAIN, "tune"):
        hass.services.async_register(DOMAIN, "tune", handle_tune)

    if not hass.services.has_service(DOMAIN, "set_mode"):
        hass.services.async_register(DOMAIN, "set_mode", handle_set_mode)

    if not hass.services.has_service(DOMAIN, "set_bandwidth"):
        hass.services.async_register(DOMAIN, "set_bandwidth", handle_set_bandwidth)

    if not hass.services.has_service(DOMAIN, "set_agc"):
        hass.services.async_register(DOMAIN, "set_agc", handle_set_agc)

    if not hass.services.has_service(DOMAIN, "set_squelch"):
        hass.services.async_register(DOMAIN, "set_squelch", handle_set_squelch)

    if not hass.services.has_service(DOMAIN, "waterfall_settings"):
        hass.services.async_register(DOMAIN, "waterfall_settings", handle_waterfall_settings)

    if not hass.services.has_service(DOMAIN, "tune_preset"):
        hass.services.async_register(DOMAIN, "tune_preset", handle_tune_preset)

    if not hass.services.has_service(DOMAIN, "step_frequency_up"):
        hass.services.async_register(DOMAIN, "step_frequency_up", handle_step_frequency_up)

    if not hass.services.has_service(DOMAIN, "step_frequency_down"):
        hass.services.async_register(DOMAIN, "step_frequency_down", handle_step_frequency_down)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    
    # Disconnect WebSocket
    if entry.entry_id in hass.data[DOMAIN]:
        api = hass.data[DOMAIN][entry.entry_id]["api"]
        await api.disconnect()
    
    # Unload platforms
    platforms_to_unload = [Platform.SENSOR, Platform.NUMBER]

    if entry.data.get(CONF_ENABLE_AUDIO, True):
        platforms_to_unload.append(Platform.MEDIA_PLAYER)

    if entry.data.get(CONF_ENABLE_WATERFALL, True):
        platforms_to_unload.append(Platform.CAMERA)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms_to_unload)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok
