"""KiwiSDR API Client with WebSocket support."""
import aiohttp
import asyncio
import websockets
import json
import logging
import struct
import numpy as np
from typing import Optional, Dict, Any, Callable
from datetime import datetime

_LOGGER = logging.getLogger(__name__)

class KiwiSDRWebSocket:
    """WebSocket connection handler for KiwiSDR."""
    
    def __init__(self, host: str, port: int, password: Optional[str] = None):
        """Initialize WebSocket handler."""
        self.host = host
        self.port = port
        self.password = password
        self.ws = None
        self.running = False
        self.callbacks = {
            'audio': [],
            'waterfall': [],
            'status': [],
            'users': []
        }
        self.is_admin = False
        self.rx_chan = 0  # Receiver channel
        
    async def connect(self):
        """Connect to KiwiSDR WebSocket."""
        try:
            # KiwiSDR WebSocket URL format
            ws_url = f"ws://{self.host}:{self.port}/{self.port}/SND"
            
            _LOGGER.info("Connecting to KiwiSDR WebSocket at %s", ws_url)
            
            self.ws = await websockets.connect(
                ws_url,
                compression=None,
                max_size=None
            )
            
            self.running = True
            _LOGGER.info("Connected to KiwiSDR WebSocket")
            
            # Send initial handshake
            await self._handshake()
            
            # Start message handler
            asyncio.create_task(self._message_handler())
            
            return True
            
        except Exception as e:
            _LOGGER.error(f"Failed to connect WebSocket: {e}")
            return False
    
    async def _handshake(self):
        """Perform KiwiSDR handshake."""
        # Initial connection string for KiwiSDR
        handshake = {
            "type": "SND",
            "gen": 0,
            "wf": 0,
            "ag": 1,
            "nb": 0,
            "nr": 0,
            "an": 0,
            "sq": 0,
            "lp": 0,
            "hp": 0,
            "de": 1,
            "lo": -500,
            "hi": 500,
            "freq": 7000.00,
            "mode": "am",
            "zoom": 0,
            "audio_rate": 12000,
            "comp": 0
        }
        
        # Send as string command
        cmd = "SET auth t=kiwi p="
        if self.password:
            cmd += self.password
        await self.ws.send(cmd)
        
        # Send receiver settings
        await self.ws.send(f"SET AR OK in=12000 out=44100")
        await self.ws.send(f"SET squelch=0 max=0")
        await self.ws.send(f"SET genattn=0")
        await self.ws.send(f"SET gen=0 mix=-1")
        await self.ws.send(f"SET freq={handshake['freq']}")
        await self.ws.send(f"SET mode={handshake['mode']}")
        await self.ws.send(f"SET compression=0")
        await self.ws.send(f"SET ident_user=HomeAssistant")
        await self.ws.send(f"SET agc=1 hang=0")
        await self.ws.send(f"SET SET browser=HA")
    
    async def authenticate_admin(self, admin_password: str):
        """Authenticate as admin."""
        if admin_password and self.ws:
            await self.ws.send(f"SET auth t=admin p={admin_password}")
            self.is_admin = True
            _LOGGER.info("Authenticated as admin")
    
    async def send_command(self, command: str):
        """Send command to KiwiSDR."""
        if self.ws and self.running:
            try:
                await self.ws.send(command)
                _LOGGER.debug(f"Sent command: {command}")
            except Exception as e:
                _LOGGER.error(f"Failed to send command: {e}")
    
    async def _message_handler(self):
        """Handle incoming WebSocket messages."""
        while self.running and self.ws:
            try:
                message = await self.ws.recv()
                
                if isinstance(message, bytes):
                    # Binary message (audio or waterfall data)
                    await self._handle_binary_message(message)
                else:
                    # Text message (status or control)
                    await self._handle_text_message(message)
                    
            except websockets.exceptions.ConnectionClosed:
                _LOGGER.warning("WebSocket connection closed")
                self.running = False
                break
            except Exception as e:
                _LOGGER.error(f"Error in message handler: {e}")
    
    async def _handle_binary_message(self, data: bytes):
        """Handle binary WebSocket message."""
        if len(data) < 1:
            return
        
        # KiwiSDR binary message format
        cmd = data[0:3].decode('ascii', errors='ignore')
        
        if cmd == 'AUD':
            # Audio data packet
            await self._handle_audio_data(data[3:])
        elif cmd == 'W/F':
            # Waterfall data packet
            await self._handle_waterfall_data(data[3:])
        elif cmd == 'MSG':
            # Message packet
            msg_data = data[3:].decode('utf-8', errors='ignore')
            await self._handle_text_message(msg_data)
    
    async def _handle_audio_data(self, data: bytes):
        """Handle audio data."""
        try:
            # KiwiSDR sends 16-bit signed PCM audio
            audio_data = np.frombuffer(data, dtype=np.int16)
            
            # Notify callbacks
            for callback in self.callbacks['audio']:
                await callback(audio_data)
                
        except Exception as e:
            _LOGGER.error(f"Error handling audio data: {e}")
    
    async def _handle_waterfall_data(self, data: bytes):
        """Handle waterfall data."""
        try:
            # Notify callbacks with raw data
            for callback in self.callbacks['waterfall']:
                await callback(data)
                
        except Exception as e:
            _LOGGER.error(f"Error handling waterfall data: {e}")
    
    async def _handle_text_message(self, message: str):
        """Handle text WebSocket message."""
        try:
            _LOGGER.debug(f"Received message: {message}")
            
            # Parse KiwiSDR status messages
            data = {}
            
            if message.startswith("MSG"):
                # Parse MSG format
                parts = message.split()
                for part in parts[1:]:
                    if '=' in part:
                        key, value = part.split('=', 1)
                        data[key] = value
                        
            elif message.startswith("users="):
                # User count update
                parts = message.split()
                for part in parts:
                    if '=' in part:
                        key, value = part.split('=', 1)
                        if key == 'users':
                            users_parts = value.split('/')
                            data['users'] = int(users_parts[0])
                            if len(users_parts) > 1:
                                data['users_max'] = int(users_parts[1])
                                
            elif "freq=" in message:
                # Frequency update
                parts = message.split()
                for part in parts:
                    if '=' in part:
                        key, value = part.split('=', 1)
                        data[key] = value
            
            # Notify status callbacks
            if data:
                for callback in self.callbacks['status']:
                    await callback(data)
                    
        except Exception as e:
            _LOGGER.debug(f"Failed to parse message: {message}, error: {e}")
    
    def register_callback(self, callback_type: str, callback: Callable):
        """Register a callback for message type."""
        if callback_type in self.callbacks:
            self.callbacks[callback_type].append(callback)
    
    async def disconnect(self):
        """Disconnect WebSocket."""
        self.running = False
        if self.ws:
            await self.ws.close()
            self.ws = None

class KiwiSDRAPI:
    """Enhanced KiwiSDR API Client."""
    
    def __init__(self, host: str, port: int, 
                 password: Optional[str] = None,
                 admin_password: Optional[str] = None):
        """Initialize the API client."""
        self.host = host
        self.port = port
        self.password = password
        self.admin_password = admin_password
        self.base_url = f"http://{host}:{port}"
        self.websocket = None
        self._session: Optional[aiohttp.ClientSession] = None
        self.current_status = {
            "online": False,
            "users": 0,
            "users_max": 4,
            "frequency": 0.0,
            "mode": "Unknown",
            "gps_status": "Unknown",
            "uptime": 0,
            "antenna": "Unknown",
            "adc_overload": False,
            "bandwidth": 0,
            "signal_strength": 0,
        }
    
    async def connect_websocket(self):
        """Connect WebSocket for real-time data."""
        self.websocket = KiwiSDRWebSocket(self.host, self.port, self.password)
        success = await self.websocket.connect()
        
        if success:
            if self.admin_password:
                await self.websocket.authenticate_admin(self.admin_password)
            
            # Register status callback
            self.websocket.register_callback('status', self._update_status)
            
        return success
    
    async def _update_status(self, data: Dict[str, Any]):
        """Update current status from WebSocket."""
        self.current_status.update(data)
        self.current_status["online"] = True
    
    async def test_connection(self) -> bool:
        """Test if we can connect to the KiwiSDR."""
        try:
            async with aiohttp.ClientSession() as session:
                # Try the main page first
                url = self.base_url
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        # Check if it's actually a KiwiSDR
                        text = await response.text()
                        if 'kiwi' in text.lower() or 'OpenWebRX' in text:
                            _LOGGER.info("Successfully connected to KiwiSDR at %s", url)
                            return True
                
                # Try status endpoint
                url = f"{self.base_url}/status"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        return True
                        
        except Exception as e:
            _LOGGER.error(f"Failed to connect to KiwiSDR: {e}")
        
        return False
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current KiwiSDR status."""
        try:
            async with aiohttp.ClientSession() as session:
                # Get main page for parsing
                async with session.get(self.base_url, timeout=10) as response:
                    if response.status == 200:
                        html_text = await response.text()
                        
                        # Parse HTML for status info
                        import re
                        
                        # Extract users info
                        users_match = re.search(r'(\d+)\s*(?:\/|of)\s*(\d+)\s*user', html_text, re.IGNORECASE)
                        if users_match:
                            self.current_status["users"] = int(users_match.group(1))
                            self.current_status["users_max"] = int(users_match.group(2))
                        
                        # Extract GPS status
                        if re.search(r'gps.*(?:yes|locked|enabled)', html_text, re.IGNORECASE):
                            self.current_status["gps_status"] = "Locked"
                        elif re.search(r'gps.*(?:no|unlocked|disabled)', html_text, re.IGNORECASE):
                            self.current_status["gps_status"] = "Unlocked"
                        
                        # Extract frequency if in URL parameters
                        freq_match = re.search(r'freq[=:]\s*(\d+\.?\d*)', html_text, re.IGNORECASE)
                        if freq_match:
                            self.current_status["frequency"] = float(freq_match.group(1))
                        
                        # Extract mode
                        mode_match = re.search(r'mode[=:]\s*["\']?(\w+)', html_text, re.IGNORECASE)
                        if mode_match:
                            self.current_status["mode"] = mode_match.group(1).upper()
                        
                        # Check if online
                        self.current_status["online"] = True
                        
                # Try the status endpoint too
                try:
                    async with session.get(f"{self.base_url}/status", timeout=5) as response:
                        if response.status == 200:
                            status_text = await response.text()
                            # Parse additional status info
                            lines = status_text.split('\n')
                            for line in lines:
                                if 'users=' in line:
                                    match = re.search(r'users=(\d+)/(\d+)', line)
                                    if match:
                                        self.current_status["users"] = int(match.group(1))
                                        self.current_status["users_max"] = int(match.group(2))
                except:
                    pass
                        
        except Exception as e:
            _LOGGER.error(f"Error getting KiwiSDR status: {e}")
            self.current_status["online"] = False
        
        return self.current_status
    
    async def tune(self, frequency: float, mode: str = "AM") -> bool:
        """Tune to a specific frequency."""
        try:
            if self.websocket and self.websocket.ws:
                await self.websocket.send_command(f"SET freq={frequency:.3f}")
                await self.websocket.send_command(f"SET mode={mode.lower()}")
                self.current_status["frequency"] = frequency
                self.current_status["mode"] = mode
                return True
            else:
                _LOGGER.warning("WebSocket not connected for tuning")
                return False
        except Exception as e:
            _LOGGER.error(f"Failed to tune: {e}")
            return False
    
    async def set_agc(self, enabled: bool, hang: bool = False):
        """Set AGC settings."""
        if self.websocket:
            agc_val = 1 if enabled else 0
            hang_val = 1 if hang else 0
            await self.websocket.send_command(f"SET agc={agc_val} hang={hang_val}")
    
    async def set_squelch(self, level: int):
        """Set squelch level (0-99)."""
        if self.websocket:
            level = max(0, min(99, level))
            await self.websocket.send_command(f"SET squelch={level}")
    
    async def set_zoom(self, level: int):
        """Set waterfall zoom level."""
        if self.websocket:
            await self.websocket.send_command(f"SET zoom={level}")
    
    async def set_waterfall_speed(self, speed: str):
        """Set waterfall speed (slow/normal/fast)."""
        if self.websocket:
            speed_map = {"slow": 1, "normal": 2, "fast": 3}
            if speed in speed_map:
                await self.websocket.send_command(f"SET wf_speed={speed_map[speed]}")
    
    # Admin functions
    async def kick_user(self, user_ip: str):
        """Kick a user (admin only)."""
        if self.websocket and self.websocket.is_admin:
            await self.websocket.send_command(f"ADM kick={user_ip}")
    
    async def ban_user(self, user_ip: str, hours: int = 24):
        """Ban a user (admin only)."""
        if self.websocket and self.websocket.is_admin:
            await self.websocket.send_command(f"ADM ban={user_ip} time={hours}")
    
    async def set_user_limit(self, limit: int):
        """Set maximum number of users (admin only)."""
        if self.websocket and self.websocket.is_admin:
            await self.websocket.send_command(f"ADM user_limit={limit}")
    
    async def restart_server(self):
        """Restart KiwiSDR server (admin only)."""
        if self.websocket and self.websocket.is_admin:
            await self.websocket.send_command("ADM restart")
    
    async def disconnect(self):
        """Disconnect all connections."""
        if self.websocket:
            await self.websocket.disconnect()
            self.websocket = None
