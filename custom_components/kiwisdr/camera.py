"""Camera platform for KiwiSDR waterfall display."""
import logging
import asyncio
import io
from datetime import datetime
from typing import Optional
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    DOMAIN, CONF_ENABLE_WATERFALL, CONF_HOST, CONF_PORT, CONF_NAME,
    WATERFALL_WIDTH, WATERFALL_HEIGHT
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up KiwiSDR camera."""
    
    if not entry.data.get(CONF_ENABLE_WATERFALL, True):
        _LOGGER.debug("Waterfall display disabled for %s", entry.data.get(CONF_HOST))
        return
    
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    
    camera = KiwiSDRWaterfallCamera(entry, api)
    async_add_entities([camera], True)
    
    _LOGGER.info("Added KiwiSDR waterfall camera for %s", entry.data.get(CONF_HOST))

class KiwiSDRWaterfallCamera(Camera):
    """Representation of KiwiSDR waterfall display."""
    
    def __init__(self, entry: ConfigEntry, api):
        """Initialize the camera."""
        super().__init__()
        self._entry = entry
        self._api = api
        self._waterfall_data = np.zeros((WATERFALL_HEIGHT, WATERFALL_WIDTH, 3), dtype=np.uint8)
        self._last_update = None
        self._frequency = 7000.0
        self._span = 10.0
        self._mode = "AM"
        
        # Set entity attributes
        self._attr_unique_id = f"{entry.entry_id}_waterfall"
        self._attr_name = f"{entry.data.get(CONF_NAME, 'KiwiSDR')} Waterfall"
        
        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, 'KiwiSDR'),
            manufacturer="KiwiSDR",
            model="Software Defined Radio",
            configuration_url=f"http://{entry.data.get(CONF_HOST)}:{entry.data.get(CONF_PORT, 8073)}"
        )
        
        # Register waterfall callback if WebSocket is available
        if self._api.websocket:
            self._api.websocket.register_callback('waterfall', self._handle_waterfall)
            self._api.websocket.register_callback('status', self._handle_status)
    
    async def _handle_status(self, data: dict):
        """Handle status updates."""
        if 'freq' in data:
            try:
                self._frequency = float(data['freq'])
            except:
                pass
        
        if 'mode' in data:
            self._mode = data['mode'].upper()
        
        if 'zoom' in data:
            try:
                zoom = int(data['zoom'])
                # Calculate span based on zoom level
                self._span = 30.0 / (2 ** zoom)
            except:
                pass
    
    async def _handle_waterfall(self, data: bytes):
        """Handle incoming waterfall data."""
        try:
            # KiwiSDR waterfall data format
            if len(data) < WATERFALL_WIDTH:
                _LOGGER.debug("Waterfall data too short: %d bytes", len(data))
                return
            
            # Parse waterfall line
            waterfall_line = np.frombuffer(data[:WATERFALL_WIDTH], dtype=np.uint8)
            
            # Shift existing data down
            self._waterfall_data[1:, :, :] = self._waterfall_data[:-1, :, :]
            
            # Add new line at top with color mapping
            for i in range(min(len(waterfall_line), WATERFALL_WIDTH)):
                color = self._value_to_color(waterfall_line[i])
                self._waterfall_data[0, i, :] = color
            
            self._last_update = datetime.now()
            _LOGGER.debug("Updated waterfall display")
            
        except Exception as e:
            _LOGGER.error(f"Error processing waterfall data: {e}")
    
    def _value_to_color(self, value: int) -> tuple:
        """Convert signal strength to RGB color."""
        # Enhanced color mapping for better visibility
        value = min(255, max(0, value))
        
        if value < 32:
            # Black to dark blue
            return (0, 0, value * 2)
        elif value < 64:
            # Dark blue to blue
            v = (value - 32) * 4
            return (0, 0, 64 + v)
        elif value < 96:
            # Blue to cyan
            v = (value - 64) * 4
            return (0, v, 255)
        elif value < 128:
            # Cyan to green
            v = (value - 96) * 8
            return (0, 255, 255 - v)
        elif value < 160:
            # Green to yellow
            v = (value - 128) * 8
            return (v, 255, 0)
        elif value < 192:
            # Yellow to orange
            v = (value - 160) * 4
            return (255, 255 - v, 0)
        elif value < 224:
            # Orange to red
            v = (value - 192) * 2
            return (255, 128 - v, 0)
        else:
            # Red to white
            v = (value - 224) * 4
            return (255, min(255, v), min(255, v))
    
    async def async_camera_image(
        self, width: Optional[int] = None, height: Optional[int] = None
    ) -> bytes:
        """Return current waterfall image."""
        # Create image from waterfall data
        img = Image.fromarray(self._waterfall_data, 'RGB')
        
        # Add overlay with frequency scale
        draw = ImageDraw.Draw(img)
        
        # Draw frequency scale at top
        if self._frequency > 0:
            # Calculate frequency range
            start_freq = self._frequency - (self._span / 2)
            end_freq = self._frequency + (self._span / 2)
            
            # Draw frequency markers
            for i in range(0, WATERFALL_WIDTH + 1, WATERFALL_WIDTH // 10):
                freq = start_freq + (i / WATERFALL_WIDTH) * self._span
                
                # Draw tick mark
                draw.line([(i, 0), (i, 5)], fill=(255, 255, 255), width=1)
                
                # Draw frequency label
                if i < WATERFALL_WIDTH - 30:  # Avoid text cutoff
                    freq_text = f"{freq:.1f}"
                    draw.text((i + 2, 5), freq_text, fill=(255, 255, 255))
        
        # Add center frequency and mode
        center_text = f"{self._frequency:.2f} kHz {self._mode}"
        draw.text((WATERFALL_WIDTH // 2 - 40, WATERFALL_HEIGHT - 25), 
                 center_text, fill=(255, 255, 255))
        
        # Add timestamp
        if self._last_update:
            timestamp = self._last_update.strftime("%H:%M:%S")
            draw.text((10, WATERFALL_HEIGHT - 15), timestamp, fill=(255, 255, 255))
        
        # Add grid lines
        for y in range(0, WATERFALL_HEIGHT, 30):
            draw.line([(0, y), (WATERFALL_WIDTH, y)], 
                     fill=(64, 64, 64, 128), width=1)
        
        # Convert to JPEG
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85)
        return buffer.getvalue()
    
    @property
    def frame_interval(self) -> float:
        """Return the interval between frames."""
        return 1.0  # Update every second
    
    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        attrs = {
            "frequency": self._frequency,
            "mode": self._mode,
            "span": self._span,
            "websocket_connected": bool(self._api.websocket and self._api.websocket.ws),
        }
        
        if self._last_update:
            attrs["last_update"] = self._last_update.isoformat()
        
        return attrs
