"""The KiwiSDR integration."""
import logging
import voluptuous as vol
import json

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN, CONF_HOST, CONF_PORT, CONF_PASSWORD, CONF_ADMIN_PASSWORD,
    CONF_NAME, CONF_ENABLE_AUDIO, CONF_ENABLE_WATERFALL, MODES
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
    
    _LOGGER.info("Setting up KiwiSDR integration for %s", entry.data.get(CONF_HOST))
    
    # Create API instance
    api = KiwiSDRAPI(
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, 8073),
        password=entry.data.get(CONF_PASSWORD),
        admin_password=entry.data.get(CONF_ADMIN_PASSWORD)
    )
    
    # Test connection first
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
    
    # Setup platforms
    platforms_to_setup = [Platform.SENSOR]  # Always setup sensors
    
    if entry.data.get(CONF_ENABLE_AUDIO, True):
        platforms_to_setup.append(Platform.MEDIA_PLAYER)
    
    if entry.data.get(CONF_ENABLE_WATERFALL, True):
        platforms_to_setup.append(Platform.CAMERA)
    
    await hass.config_entries.async_forward_entry_setups(entry, platforms_to_setup)
    
    # Register services
    await _register_services(hass, entry.entry_id)
    
    _LOGGER.info("KiwiSDR integration setup complete for %s", entry.data.get(CONF_HOST))
    
    return True

async def _register_services(hass: HomeAssistant, entry_id: str):
    """Register KiwiSDR services."""
    
    async def handle_tune(call: ServiceCall):
        """Handle tune service."""
        api = hass.data[DOMAIN][entry_id]["api"]
        frequency = call.data.get("frequency")
        mode = call.data.get("mode", "AM")
        
        success = await api.tune(frequency, mode)
        if success:
            _LOGGER.info("Tuned to %s kHz %s", frequency, mode)
        else:
            _LOGGER.error("Failed to tune to %s kHz", frequency)
    
    async def handle_set_agc(call: ServiceCall):
        """Handle AGC settings."""
        api = hass.data[DOMAIN][entry_id]["api"]
        enabled = call.data.get("enabled")
        hang = call.data.get("hang", False)
        await api.set_agc(enabled, hang)
        _LOGGER.info("Set AGC: enabled=%s, hang=%s", enabled, hang)
    
    async def handle_set_squelch(call: ServiceCall):
        """Handle squelch setting."""
        api = hass.data[DOMAIN][entry_id]["api"]
        level = call.data.get("level")
        await api.set_squelch(level)
        _LOGGER.info("Set squelch to %d", level)
    
    async def handle_waterfall_settings(call: ServiceCall):
        """Handle waterfall settings."""
        api = hass.data[DOMAIN][entry_id]["api"]
        
        if "zoom" in call.data:
            await api.set_zoom(call.data["zoom"])
            _LOGGER.info("Set zoom to %d", call.data["zoom"])
        
        if "speed" in call.data:
            await api.set_waterfall_speed(call.data["speed"])
            _LOGGER.info("Set waterfall speed to %s", call.data["speed"])
    
    # Admin services
    async def handle_kick_user(call: ServiceCall):
        """Handle kick user (admin)."""
        api = hass.data[DOMAIN][entry_id]["api"]
        if api.websocket and api.websocket.is_admin:
            user_ip = call.data.get("user_ip")
            await api.kick_user(user_ip)
            _LOGGER.info("Kicked user: %s", user_ip)
        else:
            _LOGGER.warning("Admin privileges required to kick users")
    
    async def handle_restart_server(call: ServiceCall):
        """Handle server restart (admin)."""
        api = hass.data[DOMAIN][entry_id]["api"]
        if api.websocket and api.websocket.is_admin:
            await api.restart_server()
            _LOGGER.info("Restarting KiwiSDR server")
        else:
            _LOGGER.warning("Admin privileges required to restart server")
    
    # Register services only once
    if not hass.services.has_service(DOMAIN, "tune"):
        hass.services.async_register(
            DOMAIN, "tune",
            handle_tune,
            schema=vol.Schema({
                vol.Required("frequency"): cv.positive_float,
                vol.Optional("mode"): vol.In(MODES),
            })
        )
    
    if not hass.services.has_service(DOMAIN, "set_agc"):
        hass.services.async_register(
            DOMAIN, "set_agc",
            handle_set_agc,
            schema=vol.Schema({
                vol.Required("enabled"): cv.boolean,
                vol.Optional("hang"): cv.boolean,
            })
        )
    
    if not hass.services.has_service(DOMAIN, "set_squelch"):
        hass.services.async_register(
            DOMAIN, "set_squelch",
            handle_set_squelch,
            schema=vol.Schema({
                vol.Required("level"): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=99)
                ),
            })
        )
    
    if not hass.services.has_service(DOMAIN, "waterfall_settings"):
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
        if not hass.services.has_service(DOMAIN, "kick_user"):
            hass.services.async_register(
                DOMAIN, "kick_user",
                handle_kick_user,
                schema=vol.Schema({
                    vol.Required("user_ip"): cv.string,
                })
            )
        
        if not hass.services.has_service(DOMAIN, "restart_server"):
            hass.services.async_register(
                DOMAIN, "restart_server",
                handle_restart_server,
                schema=vol.Schema({})
            )

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    
    _LOGGER.info("Unloading KiwiSDR integration for %s", entry.data.get(CONF_HOST))
    
    # Disconnect WebSocket
    if entry.entry_id in hass.data[DOMAIN]:
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
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
