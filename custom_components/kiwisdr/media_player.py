"""Media player platform for KiwiSDR audio streaming."""
import logging
import asyncio
import numpy as np
from typing import Any, Optional

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_ENABLE_AUDIO

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up KiwiSDR media player."""
    
    if not entry.data.get(CONF_ENABLE_AUDIO, True):
        return
    
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    
    media_player = KiwiSDRMediaPlayer(entry, api)
    async_add_entities([media_player], True)

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
        
        # Register audio callback
        self._api.websocket.register_callback('audio', self._handle_audio)
    
    async def _handle_audio(self, audio_data: np.ndarray):
        """Handle incoming audio data."""
        # Process audio data
        # In a real implementation, you'd send this to a streaming endpoint
        self._audio_buffer.append(audio_data)
        
        # Keep buffer size manageable
        if len(self._audio_buffer) > 100:
            self._audio_buffer.pop(0)
    
    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"{self._entry.entry_id}_media_player"
    
    @property
    def name(self) -> str:
        """Return the name."""
        return f"{self._entry.data.get('name', 'KiwiSDR')} Radio"
    
    @property
    def state(self) -> MediaPlayerState:
        """Return the state."""
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
    def supported_features(self) -> int:
        """Return supported features."""
        return (
            MediaPlayerEntityFeature.PLAY
            | MediaPlayerEntityFeature.STOP
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_MUTE
        )
    
    async def async_play_media(self, media_type: str, media_id: str) -> None:
        """Play a specific frequency."""
        # Parse media_id as frequency
        try:
            frequency = float(media_id)
            await self._api.tune(frequency, self._mode)
            self._frequency = frequency
            self._state = MediaPlayerState.PLAYING
        except ValueError:
            _LOGGER.error(f"Invalid frequency: {media_id}")
    
    async def async_media_play(self) -> None:
        """Start playback."""
        self._state = MediaPlayerState.PLAYING
        # Start audio streaming
        await self._api.websocket.send_command("SET run=1")
    
    async def async_media_stop(self) -> None:
        """Stop playback."""
        self._state = MediaPlayerState.IDLE
        # Stop audio streaming
        await self._api.websocket.send_command("SET run=0")
    
    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level."""
        self._volume = volume
        # Send volume command
        vol_db = int((volume - 0.5) * 60)  # Convert to dB
        await self._api.websocket.send_command(f"SET vol={vol_db}")
    
    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        self._muted = mute
        if mute:
            await self._api.websocket.send_command("SET mute=1")
        else:
            await self._api.websocket.send_command("SET mute=0")
