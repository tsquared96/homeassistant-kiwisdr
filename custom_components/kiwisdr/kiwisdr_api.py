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
        self.rx_chan = 0
        
    async def connect(self):
        """Connect to KiwiSDR WebSocket."""
        try:
            # KiwiSDR WebSocket URL
            ws_url = f"ws://{self.host}:{self.port}/{self.port}/SND"
            
            _LOGGER.info("Connecting to KiwiSDR WebSocket at %s", ws_url)
            
            self.ws = await websockets.connect(
                ws_url,
                compression=None,
                max_size=None,
                close_timeout=10,
                ping_interval=20,
                ping_timeout=10
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
        """Perform KiwiSDR handshake with proper initialization."""
        try:
            # Send authentication
            if self.password:
                await self.ws.send(f"SET auth t=kiwi p={self.password}")
            else:
                await self.ws.send("SET auth t=kiwi p=")
            
            await asyncio.sleep(0.1)
            
            # Initialize receiver with proper sequence
            init_commands = [
                "SET AR OK in=12000 out=44100",
                "SET agc=1 hang=0",
                "SET squelch=0 max=0",
                "SET genattn=0",
                "SET wf_comp=0",
                "SET wf_speed=1",
                "SET zoom=0",
                "SET start",
                "SET gen=0 mix=-1",
                "SET ident_user=HomeAssistant",
                "SET browser=HA",
                "SET OVERRIDE inactivity_timeout=0",
            ]
            
            for cmd in init_commands:
                await self.ws.send(cmd)
                await asyncio.sleep(0.05)
            
            _LOGGER.info("KiwiSDR handshake complete")
            
        except Exception as e:
            _LOGGER.error(f"Handshake failed: {e}")
    
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
                message = await asyncio.wait_for(self.ws.recv(), timeout=30)
                
                if isinstance(message, bytes):
                    await self._handle_binary_message(message)
                else:
                    await self._handle_text_message(message)
                    
            except asyncio.TimeoutError:
                _LOGGER.debug("WebSocket receive timeout, connection still alive")
                continue
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
        
        # Check for KiwiSDR message types
        if data.startswith(b'AUD'):
            await self._handle_audio_data(data[3:])
        elif data.startswith(b'W/F'):
            await self._handle_waterfall_data(data[3:])
        elif data.startswith(b'MSG'):
            msg_data = data[3:].decode('utf-8', errors='ignore')
            await self._handle_text_message(msg_data)
    
    async def _handle_audio_data(self, data: bytes):
        """Handle audio data."""
        try:
            audio_data = np.frombuffer(data, dtype=np.int16)
            
            for callback in self.callbacks['audio']:
                await callback(audio_data)
                
        except Exception as e:
            _LOGGER.error(f"Error handling audio data: {e}")
    
    async def _handle_waterfall_data(self, data: bytes):
        """Handle waterfall data."""
        try:
            for callback in self.callbacks['waterfall']:
                await callback(data)
                
        except Exception as e:
            _LOGGER.error(f"Error handling waterfall data: {e}")
    
    async def _handle_text_message(self, message: str):
        """Handle text WebSocket message."""
        try:
            _LOGGER.debug(f"Received message: {message[:100]}")
            
            data = {}
            
            # Parse different message formats
            if message.startswith("MSG"):
                parts = message.split()
                for part in parts[1:]:
                    if '=' in part:
                        key, value = part.split('=', 1)
                        data[key] = value
                        
            elif "users=" in message:
                parts = message.split()
                for part in parts:
                    if '=' in part:
                        key, value = part.split('=', 1)
                        if key == 'users':
                            users_parts = value.split('/')
                            data['users'] = int(users_parts[0]) if users_parts[0].isdigit() else 0
                            if len(users_parts) > 1 and users_parts[1].isdigit():
                                data['users_max'] = int(users_parts[1])
                                
            elif "freq=" in message:
                parts = message.split()
                for part in parts:
                    if '=' in part:
                        key, value = part.split('=', 1)
                        data[key] = value
            
            if data:
                for callback in self.callbacks['status']:
                    await callback(data)
                    
        except Exception as e:
            _LOGGER.debug(f"Failed to parse message: {e}")
    
    def register_callback(self, callback_type: str, callback: Callable):
        """Register a callback for message type."""
        if callback_type in self.callbacks:
            self.callbacks[callback_type].append(callback)
    
    async def disconnect(self):
        """Disconnect WebSocket."""
        self.running = False
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
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
        if 'freq' in data:
            try:
                self.current_status["frequency"] = float(data['freq'])
            except:
                pass
        
        if 'mode' in data:
            self.current_status["mode"] = data['mode'].upper()
        
        if 'users' in data:
            self.current_status["users"] = data['users']
        
        if 'users_max' in data:
            self.current_status["users_max"] = data['users_max']
            
        self.current_status["online"] = True
    
    async def test_connection(self) -> bool:
        """Test if we can connect to the KiwiSDR."""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = self.base_url
                async with session.get(url) as response:
                    if response.status == 200:
                        text = await response.text()
                        if 'kiwi' in text.lower() or 'OpenWebRX' in text:
                            _LOGGER.info("Successfully connected to KiwiSDR at %s", url)
                            return True
                        
        except Exception as e:
            _LOGGER.error(f"Failed to connect to KiwiSDR: {e}")
        
        return False
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current KiwiSDR status."""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.base_url) as response:
                    if response.status == 200:
                        html_text = await response.text()
                        
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
                        
                        self.current_status["online"] = True
                        
        except Exception as e:
            _LOGGER.error(f"Error getting KiwiSDR status: {e}")
            self.current_status["online"] = False
        
        return self.current_status
    
    async def tune(self, frequency: float, mode: str = "AM") -> bool:
        """Tune to a specific frequency with proper command sequence."""
        try:
            if not self.websocket or not self.websocket.ws:
                _LOGGER.error("WebSocket not connected for tuning")
                return False
            
            # Ensure mode is lowercase for KiwiSDR
            mode_lower = mode.lower()
            
            # Calculate passband based on mode
            passband = self._get_passband_for_mode(mode_lower)
            
            # Send tuning commands in proper sequence
            commands = [
                f"SET mod={mode_lower}",
                f"SET freq={frequency:.3f}",
                f"SET low_cut={passband['low']}",
                f"SET high_cut={passband['high']}",
                "SET GET freq",
            ]
            
            for cmd in commands:
                await self.websocket.send_command(cmd)
                await asyncio.sleep(0.1)
            
            # Update internal status
            self.current_status["frequency"] = frequency
            self.current_status["mode"] = mode.upper()
            
            _LOGGER.info("Tuned to %s kHz %s", frequency, mode)
            return True
            
        except Exception as e:
            _LOGGER.error(f"Failed to tune: {e}")
            return False
    
    def _get_passband_for_mode(self, mode: str) -> dict:
        """Get appropriate passband settings for mode."""
        passbands = {
            "am": {"low": -4200, "high": 4200},
            "amn": {"low": -2400, "high": 2400},
            "lsb": {"low": -2400, "high": -300},
            "usb": {"low": 300, "high": 2700},
            "cw": {"low": 300, "high": 700},
            "cwn": {"low": 470, "high": 530},
            "fm": {"low": -8000, "high": 8000},
            "iq": {"low": -5000, "high": 5000},
        }
        return passbands.get(mode, {"low": -2400, "high": 2400})
    
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
