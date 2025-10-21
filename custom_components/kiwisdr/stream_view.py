"""Audio stream view for KiwiSDR."""
import logging
import asyncio
import io
import wave
import numpy as np
from aiohttp import web
from homeassistant.components.http import HomeAssistantView

_LOGGER = logging.getLogger(__name__)

class KiwiSDRAudioStreamView(HomeAssistantView):
    """View to stream KiwiSDR audio."""

    url = "/api/kiwisdr/{entry_id}/audio.wav"
    name = "api:kiwisdr:audio_stream"
    requires_auth = False  # Allow local playback without auth

    def __init__(self, hass):
        """Initialize the stream view."""
        self.hass = hass
        self._streams = {}

    async def get(self, request, entry_id):
        """Stream audio data."""
        from .const import DOMAIN

        # Get the media player entity for this entry
        if entry_id not in self.hass.data.get(DOMAIN, {}):
            return web.Response(status=404, text="KiwiSDR instance not found")

        # Find the media player entity
        media_player = None
        entity_registry = self.hass.helpers.entity_registry.async_get(self.hass)
        for entity in entity_registry.entities.values():
            if entity.config_entry_id == entry_id and entity.domain == "media_player":
                # Get the actual entity object
                state_machine = self.hass.states
                entity_id = entity.entity_id
                # Get media player from platform
                if hasattr(self.hass.data[DOMAIN][entry_id], 'media_player'):
                    media_player = self.hass.data[DOMAIN][entry_id]['media_player']
                    break

        if not media_player:
            # Try to get from stored reference
            if 'media_player' in self.hass.data[DOMAIN][entry_id]:
                media_player = self.hass.data[DOMAIN][entry_id]['media_player']
            else:
                _LOGGER.error("Media player not found for entry %s", entry_id)
                return web.Response(status=404, text="Media player not found")

        _LOGGER.info("Starting audio stream for entry %s", entry_id)

        # Create WAV stream
        response = web.StreamResponse(
            status=200,
            reason='OK',
            headers={
                'Content-Type': 'audio/wav',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
            }
        )

        await response.prepare(request)

        try:
            # Send WAV header for 12kHz, 16-bit, mono
            sample_rate = 12000
            channels = 1
            sample_width = 2  # 16-bit

            # Create WAV header (44 bytes)
            wav_header = self._create_wav_header(sample_rate, channels, sample_width)
            await response.write(wav_header)

            # Stream audio data
            last_buffer_size = 0
            no_data_count = 0

            while True:
                # Check if client disconnected
                if request.transport is None or request.transport.is_closing():
                    _LOGGER.debug("Client disconnected from audio stream")
                    break

                # Get audio data from media player buffer
                if hasattr(media_player, '_audio_buffer') and media_player._audio_buffer:
                    # Get all buffered audio
                    audio_data = media_player._audio_buffer.copy()

                    if audio_data:
                        # Only send new data
                        if len(audio_data) > last_buffer_size:
                            new_data = audio_data[last_buffer_size:]
                            last_buffer_size = len(audio_data)

                            # Convert to bytes and send
                            for chunk in new_data:
                                if isinstance(chunk, np.ndarray):
                                    audio_bytes = chunk.astype(np.int16).tobytes()
                                    await response.write(audio_bytes)

                            no_data_count = 0
                        else:
                            no_data_count += 1
                    else:
                        no_data_count += 1

                    # Reset buffer position if buffer was cleared
                    if len(audio_data) < last_buffer_size:
                        last_buffer_size = 0
                else:
                    no_data_count += 1

                # If no new data for a while, send silence to keep stream alive
                if no_data_count > 20:  # ~1 second with 50ms sleep
                    # Send small silence chunk
                    silence = np.zeros(512, dtype=np.int16)
                    await response.write(silence.tobytes())
                    no_data_count = 0

                # Small delay to prevent CPU spinning
                await asyncio.sleep(0.05)

        except asyncio.CancelledError:
            _LOGGER.debug("Audio stream cancelled")
        except Exception as e:
            _LOGGER.error("Error streaming audio: %s", e)
        finally:
            await response.write_eof()

        return response

    def _create_wav_header(self, sample_rate, channels, sample_width):
        """Create WAV file header."""
        # We don't know the final size, so use maximum
        data_size = 0xFFFFFFFF - 44

        header = io.BytesIO()
        header.write(b'RIFF')
        header.write((data_size + 36).to_bytes(4, 'little'))
        header.write(b'WAVE')

        # fmt chunk
        header.write(b'fmt ')
        header.write((16).to_bytes(4, 'little'))  # chunk size
        header.write((1).to_bytes(2, 'little'))   # audio format (PCM)
        header.write(channels.to_bytes(2, 'little'))
        header.write(sample_rate.to_bytes(4, 'little'))
        header.write((sample_rate * channels * sample_width).to_bytes(4, 'little'))  # byte rate
        header.write((channels * sample_width).to_bytes(2, 'little'))  # block align
        header.write((sample_width * 8).to_bytes(2, 'little'))  # bits per sample

        # data chunk
        header.write(b'data')
        header.write(data_size.to_bytes(4, 'little'))

        return header.getvalue()
