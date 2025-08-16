"""The KiwiSDR integration."""
import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN, CONF_HOST, CONF_PORT, CONF_PASSWORD, CONF_ADMIN_PASSWORD,
    CONF_ENABLE_AUDIO, CONF_ENABLE_WATERFALL, MODES
)
from .kiwisdr_api import KiwiSDRAPI

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.MEDIA_PLAYER,
    Platform.CAMERA,
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up KiwiSDR from a config entry."""
    
    # Create API instance
    api = KiwiSDRAPI(
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, 8073),
        password=entry.data.get(CONF_PASSWORD),
        admin_password=entry.data.get(CONF_ADMIN_PASSWORD)
    )
    
    # Connect WebSocket
    await api.connect_websocket()
    
    # Store the API instance
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "entry": entry,
    }
    
    # Forward setup to platforms
    platforms_to_setup = [Platform.SENSOR]
    
    if entry.data.get(CONF_ENABLE_AUDIO, True):
        platforms_to_setup.append(Platform.MEDIA_PLAYER)
    
    if entry.data.get(CONF_ENABLE_WATERFALL, True):
        platforms_to_setup.append(Platform.CAMERA)
    
    await hass.config_entries.async_forward_entry_setups(entry, platforms_to_setup)
    
    # Register services
    await _register_services(hass, entry.entry_id)
    
    return True

async def _register_services(hass: HomeAssistant, entry_id: str):
    """Register KiwiSDR services."""
    
    async def handle_tune(call: ServiceCall):
        """Handle tune service."""
        api = hass.data[DOMAIN][entry_id]["api"]
        frequency = call.data.get("frequency")
        mode = call.data.get("mode", "AM")
        await api.tune(frequency, mode)
    
    async def handle_set_agc(call: ServiceCall):
        """Handle AGC settings."""
        api = hass.data[DOMAIN][entry_id]["api"]
        enabled = call.data.get("enabled")
        hang = call.data.get("hang", False)
        await api.set_agc(enabled, hang)
    
    async def handle_set_squelch(call: ServiceCall):
        """Handle squelch setting."""
        api = hass.data[DOMAIN][entry_id]["api"]
        level = call.data.get("level")
        await api.set_squelch(level)
    
    async def handle_waterfall_settings(call: ServiceCall):
        """Handle waterfall settings."""
        api = hass.data[DOMAIN][entry_id]["api"]
        
        if "zoom" in call.data:
            await api.set_zoom(call.data["zoom"])
        
        if "speed" in call.data:
            await api.set_waterfall_speed(call.data["speed"])
    
    # Admin services
    async def handle_kick_user(call: ServiceCall):
        """Handle kick user (admin)."""
        api = hass.data[DOMAIN][entry_id]["api"]
        if api.websocket.is_admin:
            user_ip = call.data.get("user_ip")
            await api.kick_user(user_ip)
    
    async def handle_restart_server(call: ServiceCall):
        """Handle server restart (admin)."""
        api = hass.data[DOMAIN][entry_id]["api"]
        if api.websocket.is_admin:
            await api.restart_server()
    
    # Register services
    hass.services.async_register(
        DOMAIN, "tune",
        handle_tune,
        schema=vol.Schema({
            vol.Required("frequency"): cv.positive_float,
            vol.Optional("mode"): vol.In(MODES),
        })
    )
    
    hass.services.async_register(
        DOMAIN, "set_agc",
        handle_set_agc,
        schema=vol.Schema({
            vol.Required("enabled"): cv.boolean,
            vol.Optional("hang"): cv.boolean,
        })
    )
    
    hass.services.async_register(
        DOMAIN, "set_squelch",
        handle_set_squelch,
        schema=vol.Schema({
            vol.Required("level"): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=99)
            ),
        })
    )
    
    hass.services.async_register(
        DOMAIN, "waterfall_settings",
        handle_waterfall_settings,
        schema=vol.Schema({
            vol.Optional("zoom"): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=14)
            ),
            vol.Optional("speed"): vol.In(["slow", "normal", "fast"]),
        })
    )
    
    # Admin services (only if admin password provided)
    entry = hass.data[DOMAIN][entry_id]["entry"]
    if entry.data.get(CONF_ADMIN_PASSWORD):
        hass.services.async_register(
            DOMAIN, "kick_user",
            handle_kick_user,
            schema=vol.Schema({
                vol.Required("user_ip"): cv.string,
            })
        )
        
        hass.services.async_register(
            DOMAIN, "restart_server",
            handle_restart_server,
            schema=vol.Schema({})
        )

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    
    # Disconnect WebSocket
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    await api.disconnect()
    
    # Unload platforms
    platforms_to_unload = [Platform.SENSOR]
    
    if entry.data.get(CONF_ENABLE_AUDIO, True):
        platforms_to_unload.append(Platform.MEDIA_PLAYER)
    
    if entry.data.get(CONF_ENABLE_WATERFALL, True):
        platforms_to_unload.append(Platform.CAMERA)
    
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, platforms_to_unload
    )
    
    if unload_ok:
        # Unregister services
        for service in ["tune", "set_agc", "set_squelch", "waterfall_settings",
                       "kick_user", "restart_server"]:
            if hass.services.has_service(DOMAIN, service):
                hass.services.async_remove(DOMAIN, service)
        
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok
