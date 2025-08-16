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

from .const import DOMAIN, CONF_ENABLE_WATERFALL, WATERFALL_WIDTH, WATERFALL_HEIGHT

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up KiwiSDR camera."""
    
    if not entry.data.get(CONF_ENABLE_WATERFALL, True):
        return
    
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    
    camera = KiwiSDRWaterfallCamera(entry, api)
    async_add_entities([camera], True)

class KiwiSDRWaterfallCamera(Camera):
    """Representation of KiwiSDR waterfall display."""
    
    def __init__(self, entry: ConfigEntry, api):
        """Initialize the camera."""
        super().__init__()
        self._entry = entry
        self._api = api
        self._waterfall_data = np.zeros((WATERFALL_HEIGHT, WATERFALL_WIDTH, 3), dtype=np.uint8)
        self._last_update = None
        
        # Register waterfall callback
        self._api.websocket.register_callback('waterfall', self._handle_waterfall)
    
    async def _handle_waterfall(self, data: bytes):
        """Handle incoming waterfall data."""
        try:
            # Parse waterfall data (simplified)
            # In reality, you'd need to decode the KiwiSDR waterfall format
            
            # Create a gradient based on signal strength
            waterfall_line = np.frombuffer(data[:WATERFALL_WIDTH], dtype=np.uint8)
            
            # Shift existing data down
            self._waterfall_data[1:, :, :] = self._waterfall_data[:-1, :, :]
            
            # Add new line at top with color mapping
            for i, value in enumerate(waterfall_line):
                if i < WATERFALL_WIDTH:
                    # Map signal strength to color (blue -> green -> yellow -> red)
                    color = self._value_to_color(value)
                    self._waterfall_data[0, i, :] = color
            
            self._last_update = datetime.now()
            
        except Exception as e:
            _LOGGER.error(f"Error processing waterfall data: {e}")
    
    def _value_to_color(self, value: int) -> tuple:
        """Convert signal strength to RGB color."""
        # Simple color mapping
        if value < 64:
            # Blue to cyan
            return (0, value * 4, 255)
        elif value < 128:
            # Cyan to green
            v = (value - 64) * 4
            return (0, 255, 255 - v)
        elif value < 192:
            # Green to yellow
            v = (value - 128) * 4
            return (v, 255, 0)
        else:
            # Yellow to red
            v = (value - 192) * 4
            return (255, 255 - v, 0)
    
    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"{self._entry.entry_id}_waterfall"
    
    @property
    def name(self) -> str:
        """Return the name."""
        return f"{self._entry.data.get('name', 'KiwiSDR')} Waterfall"
    
    async def async_camera_image(
        self, width: Optional[int] = None, height: Optional[int] = None
    ) -> bytes:
        """Return current waterfall image."""
        # Create image with overlay
        img = Image.fromarray(self._waterfall_data, 'RGB')
        
        # Add frequency scale and grid
        draw = ImageDraw.Draw(img)
        
        # Add frequency markers
        if self._api.current_status.get('frequency'):
            freq = self._api.current_status['frequency']
            span = self._api.current_status.get('span', 10)
            
            # Draw frequency scale
            for i in range(0, WATERFALL_WIDTH, 100):
                f = freq - span/2 + (i/WATERFALL_WIDTH) * span
                draw.text((i, 10), f"{f:.1f}", fill=(255, 255, 255))
        
        # Add timestamp
        if self._last_update:
            timestamp = self._last_update.strftime("%H:%M:%S")
            draw.text((10, WATERFALL_HEIGHT - 20), timestamp, fill=(255, 255, 255))
        
        # Convert to JPEG
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=80)
        return buffer.getvalue()
    
    @property
    def frame_interval(self) -> float:
        """Return the interval between frames."""
        return 1.0  # Update every second
