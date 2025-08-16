"""KiwiSDR API Client with WebSocket support."""
import aiohttp
import asyncio
import websockets
import json
import logging
import numpy as np
from typing import Optional, Dict, Any, Callable
from datetime import datetime
import base64

_LOGGER = logging.getLogger(__name__)

class KiwiSDRWebSocket:
    """WebSocket connection handler for KiwiSDR."""
    
    def __init__(self, host: str, port: int, password: Optional[str] = None):
        """Initialize WebSocket handler."""
        self.host = host
        self.port = port
        self.password = password
        self.ws_url = f"ws://{host}:{port}/kiwi/{port}/W/F"
        self.ws = None
        self.running = False
        self.callbacks = {
            'audio': [],
            'waterfall': [],
            'status': []
        }
        self.is_admin = False
        
    async def connect(self):
        """Connect to KiwiSDR WebSocket."""
        try:
            self.ws = await websockets.connect(
                self.ws_url,
                subprotocols=["kiwi-protocol"]
            )
            self.running = True
            _LOGGER.info("Connected to KiwiSDR WebSocket")
            
            # Send initial configuration
            await self._initialize_connection()
            
            # Start message handler
            asyncio.create_task(self._message_handler())
            
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to connect WebSocket: {e}")
            return False
    
    async def _initialize_connection(self):
        """Initialize the WebSocket connection."""
        # Send initial commands
        init_commands = [
            "SET auth t=kiwi p=",  # Basic auth (no password)
            "SET AR OK in=12000 out=44100",  # Audio rate
            "SET squelch=0 max=0",
            "SET genattn=0",
            "SET gen=0 mix=-1",
            "SET ident_user=HomeAssistant",
            "SET geo=geo",
        ]
        
        for cmd in init_commands:
            await self.send_command(cmd)
            await asyncio.sleep(0.1)
    
    async def authenticate_admin(self, admin_password: str):
        """Authenticate as admin."""
        if admin_password:
            await self.send_command(f"SET auth t=admin p={admin_password}")
            self.is_admin = True
            _LOGGER.info("Authenticated as admin")
    
    async def send_command(self, command: str):
        """Send command to KiwiSDR."""
        if self.ws:
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
        # Parse message type from header
        if len(data) < 4:
            return
        
        msg_type = data[0]
        
        if msg_type == 0x04:  # Audio data
            await self._handle_audio_data(data[4:])
        elif msg_type == 0x08:  # Waterfall data
            await self._handle_waterfall_data(data[4:])
    
    async def _handle_audio_data(self, data: bytes):
        """Handle audio data."""
        # Convert to numpy array
        audio_data = np.frombuffer(data, dtype=np.int16)
        
        # Notify callbacks
        for callback in self.callbacks['audio']:
            await callback(audio_data)
    
    async def _handle_waterfall_data(self, data: bytes):
        """Handle waterfall data."""
        # Parse waterfall data (simplified)
        for callback in self.callbacks['waterfall']:
            await callback(data)
    
    async def _handle_text_message(self, message: str):
        """Handle text WebSocket message."""
        try:
            # Parse JSON or key-value pairs
            if message.startswith('{'):
                data = json.loads(message)
            else:
                # Parse key=value format
                data = {}
                for item in message.split():
                    if '=' in item:
                        key, value = item.split('=', 1)
                        data[key] = value
            
            # Notify status callbacks
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
        self.websocket = KiwiSDRWebSocket(host, port, password)
        self._session: Optional[aiohttp.ClientSession] = None
        self.current_status = {}
        
    async def connect_websocket(self):
        """Connect WebSocket for real-time data."""
        success = await self.websocket.connect()
        
        if success and self.admin_password:
            await self.websocket.authenticate_admin(self.admin_password)
        
        # Register status callback
        self.websocket.register_callback('status', self._update_status)
        
        return success
    
    async def _update_status(self, data: Dict[str, Any]):
        """Update current status from WebSocket."""
        self.current_status.update(data)
    
    async def test_connection(self) -> bool:
        """Test if we can connect to the KiwiSDR."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/status"
                async with session.get(url, timeout=10) as response:
                    return response.status == 200
        except Exception as e:
            _LOGGER.error(f"Failed to connect to KiwiSDR: {e}")
            return False
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current KiwiSDR status."""
        try:
            async with aiohttp.ClientSession() as session:
                # Get status from HTTP endpoint
                status_url = f"{self.base_url}/status"
                async with session.get(status_url, timeout=10) as response:
                    if response.status == 200:
                        status_text = await response.text()
                        status_data = self._parse_status(status_text)
                        
                        # Merge with WebSocket status
                        status_data.update(self.current_status)
                        
                        return status_data
        except Exception as e:
            _LOGGER.error(f"Error getting KiwiSDR status: {e}")
            return self.current_status
    
    def _parse_status(self, status_text: str) -> Dict[str, Any]:
        """Parse KiwiSDR status response."""
        status = {
            "online": True,
            "users": 0,
            "users_max": 4,
            "gps_status": "Unknown",
            "uptime": 0,
            "frequency": 7000.0,
            "mode": "AM",
            "antenna": "Unknown",
            "adc_overload": False,
        }
        
        # Parse actual response
        import re
        lines = status_text.split('\n')
        
        for line in lines:
            # Parse users
            if 'users=' in line:
                match = re.search(r'users=(\d+)/(\d+)', line)
                if match:
                    status["users"] = int(match.group(1))
                    status["users_max"] = int(match.group(2))
            
            # Parse GPS
            elif 'gps=' in line:
                if 'yes' in line.lower():
                    status["gps_status"] = "Locked"
                else:
                    status["gps_status"] = "Unlocked"
            
            # Parse uptime
            elif 'up=' in line:
                match = re.search(r'(\d+):(\d+)', line)
                if match:
                    hours = int(match.group(1))
                    minutes = int(match.group(2))
                    status["uptime"] = hours + (minutes / 60)
        
        return status
    
    async def tune(self, frequency: float, mode: str = "AM") -> bool:
        """Tune to a specific frequency."""
        try:
            await self.websocket.send_command(f"SET freq={frequency:.3f}")
            await self.websocket.send_command(f"SET mode={mode}")
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to tune: {e}")
            return False
    
    async def set_agc(self, enabled: bool, hang: bool = False):
        """Set AGC settings."""
        agc_val = 1 if enabled else 0
        hang_val = 1 if hang else 0
        await self.websocket.send_command(f"SET agc={agc_val} hang={hang_val}")
    
    async def set_squelch(self, level: int):
        """Set squelch level (0-99)."""
        level = max(0, min(99, level))
        await self.websocket.send_command(f"SET squelch={level}")
    
    async def set_zoom(self, level: int):
        """Set waterfall zoom level."""
        await self.websocket.send_command(f"SET zoom={level}")
    
    async def set_waterfall_speed(self, speed: str):
        """Set waterfall speed (slow/normal/fast)."""
        speed_map = {"slow": 1, "normal": 2, "fast": 3}
        if speed in speed_map:
            await self.websocket.send_command(f"SET wf_speed={speed_map[speed]}")
    
    # Admin functions
    async def kick_user(self, user_ip: str):
        """Kick a user (admin only)."""
        if self.websocket.is_admin:
            await self.websocket.send_command(f"ADM kick={user_ip}")
    
    async def ban_user(self, user_ip: str, hours: int = 24):
        """Ban a user (admin only)."""
        if self.websocket.is_admin:
            await self.websocket.send_command(f"ADM ban={user_ip} time={hours}")
    
    async def set_user_limit(self, limit: int):
        """Set maximum number of users (admin only)."""
        if self.websocket.is_admin:
            await self.websocket.send_command(f"ADM user_limit={limit}")
    
    async def restart_server(self):
        """Restart KiwiSDR server (admin only)."""
        if self.websocket.is_admin:
            await self.websocket.send_command("ADM restart")
    
    async def disconnect(self):
        """Disconnect all connections."""
        await self.websocket.disconnect()
