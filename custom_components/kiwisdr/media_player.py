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
    
    media_player = KiwiSDRMediaPlayer(hass, entry, api)
    async_add_entities([media_player], True)
    
    _LOGGER.info("Added KiwiSDR media player for %s", entry.data.get(CONF_HOST))

class KiwiSDRMediaPlayer(MediaPlayerEntity):
    """Representation of KiwiSDR audio stream."""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api):
        """Initialize the media player."""
        self.hass = hass
        self._entry = entry
        self._api = api
        self._state = MediaPlayerState.IDLE
        self._volume = 0.5
        self._muted = False
        self._frequency = 7074.0
        self._mode = "USB"
        self._audio_buffer = []
        self._last_audio_time = None
        self._is_playing = False
        self._audio_initialized = False
        
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
        
        # Build direct KiwiSDR URL with parameters
        host = entry.data.get(CONF_HOST)
        port = entry.data.get(CONF_PORT, 8073)
        # Direct URL to KiwiSDR with autoplay parameters
        self._kiwisdr_url = f"http://{host}:{port}/?f={self._frequency}&m={self._mode.lower()}&pb=300,2700"
        
        # Register audio callback if WebSocket is available
        if self._api.websocket:
            self._api.websocket.register_callback('audio', self._handle_audio)
    
    async def _handle_audio(self, audio_data: np.ndarray):
        """Handle incoming audio data."""
        if not self._is_playing:
            self._is_playing = True
            self._state = MediaPlayerState.PLAYING
        
        self._last_audio_time = datetime.now()
        self._audio_buffer.append(audio_data)
        
        if len(self._audio_buffer) > 100:
            self._audio_buffer.pop(0)
        
        _LOGGER.debug("Received audio data: %d samples", len(audio_data))
    
    @property
    def state(self) -> MediaPlayerState:
        """Return the state."""
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
    def media_content_id(self) -> str:
        """Return the media content ID."""
        return self._kiwisdr_url
    
    @property
    def supported_features(self) -> int:
        """Return supported features."""
        return (
            MediaPlayerEntityFeature.PLAY
            | MediaPlayerEntityFeature.STOP
            | MediaPlayerEntityFeature.PAUSE
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.PLAY_MEDIA
        )
    
    async def async_play_media(self, media_type: str, media_id: str) -> None:
        """Play a specific frequency."""
        try:
            # Parse media_id for frequency and optionally mode
            parts = media_id.replace("kiwisdr://", "").split('/')
            if ':' in parts[0]:
                parts = parts[0].split(':')
            
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
                # Update URL
                host = self._entry.data.get(CONF_HOST)
                port = self._entry.data.get(CONF_PORT, 8073)
                self._kiwisdr_url = f"http://{host}:{port}/?f={frequency}&m={mode.lower()}&pb=300,2700"
                
                await self.async_media_play()
                _LOGGER.info("Tuned to %s kHz %s", frequency, mode)
            else:
                _LOGGER.error("Failed to tune to %s kHz", frequency)
                
        except ValueError:
            _LOGGER.error("Invalid frequency format: %s", media_id)
    
    async def async_media_play(self) -> None:
        """Start playback - this is where user 'clicks play'."""
        if self._api.websocket and self._api.websocket.ws:
            self._state = MediaPlayerState.PLAYING
            self._is_playing = True
            
            # Initialize audio if not done
            if not self._audio_initialized:
                await self._initialize_audio()
            
            # Send play command sequence that mimics clicking play button
            commands = [
                "SET squelch=0",
                "SET agc=1 hang=0",
                "SET run=1",
                "SET audio_start=1",  # This mimics the play button click
                "SET gen=0 mix=-1",
                "SET wf_comp=0",
                "SET mute=0",
            ]
            
            for cmd in commands:
                await self._api.websocket.send_command(cmd)
                await asyncio.sleep(0.05)
            
            _LOGGER.info("Started audio streaming (play button clicked)")
        else:
            _LOGGER.warning("WebSocket not connected, cannot start audio")
            self._state = MediaPlayerState.IDLE
    
    async def _initialize_audio(self):
        """Initialize audio stream - happens once when first playing."""
        if self._api.websocket and self._api.websocket.ws:
            # These commands initialize the audio subsystem
            init_commands = [
                f"SET mod={self._mode.lower()}",
                f"SET freq={self._frequency:.3f}",
                "SET AR OK in=12000 out=44100",
                "SET low_cut=300",
                "SET high_cut=2700",
                "SET audio_init=1",  # Initialize audio subsystem
            ]
            
            for cmd in init_commands:
                await self._api.websocket.send_command(cmd)
                await asyncio.sleep(0.05)
            
            self._audio_initialized = True
            _LOGGER.info("Audio subsystem initialized")
    
    async def async_media_pause(self) -> None:
        """Pause playback."""
        self._state = MediaPlayerState.PAUSED
        self._is_playing = False
        
        if self._api.websocket:
            await self._api.websocket.send_command("SET audio_pause=1")
            await self._api.websocket.send_command("SET run=0")
    
    async def async_media_stop(self) -> None:
        """Stop playback."""
        self._state = MediaPlayerState.IDLE
        self._is_playing = False
        self._audio_initialized = False  # Reset initialization
        
        if self._api.websocket:
            await self._api.websocket.send_command("SET audio_stop=1")
            await self._api.websocket.send_command("SET run=0")
            _LOGGER.info("Stopped audio streaming")
        
        self._audio_buffer.clear()
        self._last_audio_time = None
    
    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level."""
        self._volume = volume
        
        if self._api.websocket:
            # KiwiSDR expects volume in range 0-100
            vol_percent = int(volume * 100)
            await self._api.websocket.send_command(f"SET volume={vol_percent}")
            _LOGGER.debug("Set volume to %d%%", vol_percent)
    
    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        self._muted = mute
        
        if self._api.websocket:
            mute_val = 1 if mute else 0
            await self._api.websocket.send_command(f"SET mute={mute_val}")
            _LOGGER.debug("Set mute to %s", mute)
    
    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        attrs = {
            "frequency": self._frequency,
            "mode": self._mode,
            "buffer_size": len(self._audio_buffer),
            "websocket_connected": bool(self._api.websocket and self._api.websocket.ws),
            "audio_initialized": self._audio_initialized,
            "kiwisdr_url": self._kiwisdr_url,
        }
        
        if self._last_audio_time:
            attrs["last_audio_received"] = self._last_audio_time.isoformat()
        
        return attrs
