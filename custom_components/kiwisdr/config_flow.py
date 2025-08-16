"""Config flow for KiwiSDR integration."""
import voluptuous as vol
import logging

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN, CONF_HOST, CONF_PORT, CONF_PASSWORD, CONF_ADMIN_PASSWORD,
    CONF_NAME, CONF_ENABLE_AUDIO, CONF_ENABLE_WATERFALL,
    DEFAULT_PORT, DEFAULT_NAME
)
from .kiwisdr_api import KiwiSDRAPI

_LOGGER = logging.getLogger(__name__)

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""

async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect."""
    
    api = KiwiSDRAPI(
        host=data[CONF_HOST],
        port=data.get(CONF_PORT, DEFAULT_PORT),
        password=data.get(CONF_PASSWORD),
        admin_password=data.get(CONF_ADMIN_PASSWORD)
    )
    
    # Test the connection
    if not await api.test_connection():
        raise CannotConnect
    
    # Get status
    status = await api.get_status()
    
    return {
        "title": data.get(CONF_NAME, f"KiwiSDR {data[CONF_HOST]}"),
        "users_max": status.get("users_max", 4),
        "has_admin": bool(data.get(CONF_ADMIN_PASSWORD))
    }

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for KiwiSDR."""
    
    VERSION = 1
    
    def __init__(self):
        """Initialize."""
        self.data = {}
    
    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            self.data = user_input
            return await self.async_step_features()
        
        data_schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
            vol.Optional(CONF_PASSWORD): str,
            vol.Optional(CONF_ADMIN_PASSWORD): str,
            vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
        })
        
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors
        )
    
    async def async_step_features(self, user_input=None) -> FlowResult:
        """Configure features to enable."""
        errors = {}
        
        if user_input is not None:
            self.data.update(user_input)
            
            try:
                info = await validate_input(self.hass, self.data)
                
                # Create unique ID
                unique_id = f"{self.data[CONF_HOST]}:{self.data.get(CONF_PORT, DEFAULT_PORT)}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=info["title"],
                    data=self.data,
                    options={
                        "has_admin": info["has_admin"]
                    }
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
        
        # Show features form
        data_schema = vol.Schema({
            vol.Optional(CONF_ENABLE_AUDIO, default=True): bool,
            vol.Optional(CONF_ENABLE_WATERFALL, default=True): bool,
        })
        
        return self.async_show_form(
            step_id="features",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "host": self.data[CONF_HOST]
            }
        )
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get options flow."""
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow."""
    
    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
    
    async def async_step_init(self, user_input=None):
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        
        options_schema = {}
        
        # Add admin options if admin password is configured
        if self.config_entry.options.get("has_admin"):
            options_schema.update({
                vol.Optional("max_users", default=4): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=8)
                ),
                vol.Optional("kick_idle_users", default=False): bool,
                vol.Optional("idle_timeout", default=30): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=120)
                ),
            })
        
        # General options
        options_schema.update({
            vol.Optional("waterfall_speed", default="normal"): vol.In(
                ["slow", "normal", "fast"]
            ),
            vol.Optional("auto_squelch", default=False): bool,
            vol.Optional("noise_reduction", default=False): bool,
        })
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(options_schema)
        )
