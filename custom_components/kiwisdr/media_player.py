"""Media player platform for KiwiSDR audio streaming."""
import logging
import asyncio
import numpy as np
from typing import Any, Optional
from datetime import datetime

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, CONF_ENABLE_AUDIO, CONF_HOST, CONF_PORT, CONF_NAME, MODES

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up KiwiSDR media player."""
    
    if not entry.data.get(CONF_ENABLE_AUDIO, True):
        _LOGGER.debug("Audio streaming disabled for %s", entry.data.get(CONF_HOST))
        return
    
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    
    media_player = KiwiSDRMediaPlayer(entry, api)
    async_add_entities([media_player], True)
    
    _LOGGER.info("Added KiwiSDR media player for %s", entry.data.get(CONF_HOST))

class KiwiSDRMediaPlayer(MediaPlayerEntity):
    """Representation of KiwiSDR audio stream."""
    
    def __init__(self, entry: ConfigEntry, api):
        """Initialize the media player."""
        self._entry = entry
        self._api = api
        self._state = MediaPlayerState.IDLE
        self._volume = 0.5
        self._muted = False
        self._frequency = 7000.0
        self._mode = "AM"
        self._audio_buffer = []
        self._last_audio_time = None
        self._is_playing = False
        
        # Set entity attributes
        self._attr_unique_id = f"{entry.entry_id}_media_player"
        self._attr_name = f"{entry.data.get(CONF_NAME, 'KiwiSDR')} Radio"
        
        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, 'KiwiSDR'),
            manufacturer="KiwiSDR",
            model="Software Defined Radio",
            configuration_url=f"http://{entry.data.get(CONF_HOST)}:{entry.data.get(CONF_PORT, 8073)}"
        )
        
        # Register audio callback if WebSocket is available
        if self._api.websocket:
            self._api.websocket.register_callback('audio', self._handle_audio)
    
    async def _handle_audio(self, audio_data: np.ndarray):
        """Handle incoming audio data."""
        # Update state to playing when receiving audio
        if not self._is_playing:
            self._is_playing = True
            self._state = MediaPlayerState.PLAYING
        
        self._last_audio_time = datetime.now()
        
        # Store audio data (limited buffer)
        self._audio_buffer.append(audio_data)
        if len(self._audio_buffer) > 100:
            self._audio_buffer.pop(0)
        
        _LOGGER.debug("Received audio data: %d samples", len(audio_data))
    
    @property
    def state(self) -> MediaPlayerState:
        """Return the state."""
        # Check if we're still receiving audio
        if self._last_audio_time:
            time_since_audio = (datetime.now() - self._last_audio_time).total_seconds()
            if time_since_audio > 5 and self._state == MediaPlayerState.PLAYING:
                self._state = MediaPlayerState.IDLE
                self._is_playing = False
        
        return self._state
    
    @property
    def volume_level(self) -> float:
        """Return the volume level."""
        return self._volume
    
    @property
    def is_volume_muted(self) -> bool:
        """Return mute status."""
        return self._muted
    
    @property
    def media_content_type(self) -> MediaType:
        """Return the media type."""
        return MediaType.MUSIC
    
    @property
    def media_title(self) -> str:
        """Return the media title."""
        return f"{self._frequency} kHz {self._mode}"
    
    @property
    def media_artist(self) -> str:
        """Return the media artist."""
        return f"KiwiSDR {self._entry.data.get(CONF_HOST)}"
    
    @property
    def supported_features(self) -> int:
        """Return supported features."""
        return (
            MediaPlayerEntityFeature.PLAY
            | MediaPlayerEntityFeature.STOP
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.PLAY_MEDIA
        )
    
    async def async_play_media(self, media_type: str, media_id: str) -> None:
        """Play a specific frequency."""
        try:
            # Parse media_id for frequency and optionally mode
            # Format: "7000" or "7000:AM"
            parts = media_id.split(':')
            frequency = float(parts[0])
            
            if len(parts) > 1 and parts[1].upper() in MODES:
                mode = parts[1].upper()
            else:
                mode = self._mode
            
            # Tune to frequency
            success = await self._api.tune(frequency, mode)
            
            if success:
                self._frequency = frequency
                self._mode = mode
                await self.async_media_play()
                _LOGGER.info("Tuned to %s kHz %s", frequency, mode)
            else:
                _LOGGER.error("Failed to tune to %s kHz", frequency)
                
        except ValueError:
            _LOGGER.error("Invalid frequency format: %s", media_id)
    
    async def async_media_play(self) -> None:
        """Start playback."""
        if self._api.websocket:
            self._state = MediaPlayerState.PLAYING
            self._is_playing = True
            await self._api.websocket.send_command("SET run=1")
            _LOGGER.info("Started audio streaming")
        else:
            _LOGGER.warning("WebSocket not connected, cannot start audio")
            self._state = MediaPlayerState.IDLE
    
    async def async_media_stop(self) -> None:
        """Stop playback."""
        self._state = MediaPlayerState.IDLE
        self._is_playing = False
        
        if self._api.websocket:
            await self._api.websocket.send_command("SET run=0")
            _LOGGER.info("Stopped audio streaming")
        
        # Clear audio buffer
        self._audio_buffer.clear()
        self._last_audio_time = None
    
    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level."""
        self._volume = volume
        
        if self._api.websocket:
            # Convert to dB (-60 to 0)
            vol_db = int((volume - 0.5) * 60)
            await self._api.websocket.send_command(f"SET volume={vol_db}")
            _LOGGER.debug("Set volume to %f (%d dB)", volume, vol_db)
    
    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        self._muted = mute
        
        if self._api.websocket:
            if mute:
                await self._api.websocket.send_command("SET mute=1")
            else:
                await self._api.websocket.send_command("SET mute=0")
            _LOGGER.debug("Set mute to %s", mute)
    
    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        attrs = {
            "frequency": self._frequency,
            "mode": self._mode,
            "buffer_size": len(self._audio_buffer),
            "websocket_connected": bool(self._api.websocket and self._api.websocket.ws),
        }
        
        if self._last_audio_time:
            attrs["last_audio_received"] = self._last_audio_time.isoformat()
        
        return attrs
