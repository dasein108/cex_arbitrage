import logging
import time
import hashlib
import hmac
import asyncio
from typing import Dict, Any, Optional
from websockets import connect
from websockets.client import WebSocketClientProtocol

from exchanges.interfaces.ws import ConnectionStrategy, ConnectionContext
from infrastructure.networking.websocket.strategies.connection import ReconnectionPolicy
from config.structs import ExchangeConfig
from infrastructure.exceptions.exchange import BaseExchangeError


class GateioPrivateConnectionStrategy(ConnectionStrategy):
    """Gate.io private WebSocket connection strategy with direct connection and authentication."""

    def __init__(self, config: ExchangeConfig):
        super().__init__(config)  # Initialize parent with _websocket = None
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        if not config.credentials.is_configured():
            raise ValueError("Gate.io credentials not configured for private WebSocket")
        
        self.api_key = config.credentials.api_key
        self.secret_key = config.credentials.secret_key
        
        # Gate.io private-specific connection settings
        self.websocket_url = config.websocket_url
        self.ping_interval = 20  # Gate.io uses 20s ping interval
        self.ping_timeout = 10
        self.max_queue_size = 512
        self.max_message_size = 1024 * 1024  # 1MB

    async def connect(self) -> WebSocketClientProtocol:
        """
        Establish Gate.io private WebSocket connection with authentication.
        
        Gate.io private requires HMAC SHA512 authentication after connection.
        
        Returns:
            Raw WebSocket ClientProtocol
            
        Raises:
            BaseExchangeError: If connection fails
        """
        try:
            self.logger.info(f"Connecting to Gate.io private WebSocket: {self.websocket_url}")
            
            # Gate.io private connection (similar to public but for private endpoint)
            # IMPORTANT: Disable built-in ping since we use custom ping messages
            # This prevents conflict between built-in ping/pong and custom ping
            self._websocket = await connect(
                self.websocket_url,
                # # Gate.io-specific optimizations
                # extra_headers={
                #     "User-Agent": "HFTArbitrageEngine-Gateio/1.0"
                # },
                ping_interval=None,  # DISABLE built-in ping - we use custom ping messages
                ping_timeout=None,   # DISABLE built-in ping timeout
                max_queue=self.max_queue_size,
                # Gate.io works well with compression
                compression="deflate",
                max_size=self.max_message_size,
                write_limit=2 ** 20,  # 1MB write buffer
            )
            
            self.logger.info("Gate.io private WebSocket connected successfully")
            return self._websocket
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Gate.io private WebSocket: {e}")
            raise BaseExchangeError(500, f"Gate.io private WebSocket connection failed: {str(e)}")
    
    def get_reconnection_policy(self) -> ReconnectionPolicy:
        """Get Gate.io private-specific reconnection policy."""
        return ReconnectionPolicy(
            max_attempts=10,  # Fewer attempts for private due to auth complexity
            initial_delay=3.0,  # Longer delay for auth setup
            backoff_factor=2.0,  # Standard backoff
            max_delay=60.0,  # Higher max delay for auth issues
            reset_on_1005=False  # Gate.io private 1005 errors may indicate auth issues
        )

    async def _generate_auth_message(self, **kwargs) -> Optional[str]:
        """Generate Gate.io WebSocket authentication message."""
        timestamp = int(time.time())
        timestamp_ms = int(time.time() * 1000)
        req_id = f"{timestamp_ms}-1"
        
        # Gate.io WebSocket authentication signature format (from official example)
        # String to sign: "api\n{channel}\n{request_param_bytes}\n{timestamp}"
        channel = "spot.login"
        request_param_bytes = b""  # Empty for login request
        
        key = f"api\n{channel}\n{request_param_bytes.decode()}\n{timestamp}"
        
        # Create HMAC SHA512 signature
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            key.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
        
        auth_message = {
            "time": timestamp,
            "channel": channel,
            "event": "api",
            "payload": {
                "api_key": self.api_key,
                "signature": signature,
                "timestamp": str(timestamp),
                "req_id": req_id
            }
        }
        
        import msgspec
        return msgspec.json.encode(auth_message).decode()

    def get_ping_message(self) -> str:
        """Get ping message for Gate.io."""
        import msgspec
        
        ping_msg = {
            "time": int(time.time()),
            "channel": "spot.ping",
            "event": "ping"
        }
        return msgspec.json.encode(ping_msg).decode()

    def is_pong_message(self, message: Dict[str, Any]) -> bool:
        """Check if message is a pong response."""
        return message.get("event") == "pong"

    def should_reconnect_on_error(self, error: Exception) -> bool:
        """Determine if should reconnect on error."""
        # Don't reconnect on authentication failures
        error_str = str(error).lower()
        if "auth" in error_str or "unauthorized" in error_str:
            return False
        return True

    async def create_connection_context(self) -> ConnectionContext:
        """Create Gate.io private WebSocket connection context (legacy support)."""
        return ConnectionContext(
            url=self.websocket_url,
            headers={"User-Agent": "HFTArbitrageEngine-Gateio/1.0"},
            auth_required=True,
            ping_interval=self.ping_interval,
            ping_timeout=self.ping_timeout,
            max_reconnect_attempts=10,
            reconnect_delay=3.0
        )

    async def authenticate(self) -> bool:
        """Perform authentication for Gate.io private WebSocket using internal connection."""
        if not self.is_connected:
            raise RuntimeError("No WebSocket connection available for authentication")
            
        try:
            auth_message = await self._generate_auth_message()
            if auth_message:
                # Send authentication message directly to WebSocket
                await self._websocket.send(auth_message)
                await asyncio.sleep(1)  # Wait a moment for auth to process *MANDATORY*
                self.logger.info("Sent authentication message to Gate.io private WebSocket")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Gate.io private authentication failed: {e}")
            return False

    async def handle_heartbeat(self) -> None:
        """Handle Gate.io private heartbeat (ping/pong with custom messages) using internal WebSocket."""
        if not self.is_connected:
            raise RuntimeError("No WebSocket connection available for heartbeat")
            
        try:
            ping_message = self.get_ping_message()
            # Send ping message directly to WebSocket
            await self._websocket.send(ping_message)
            self.logger.debug("Sent custom ping message to Gate.io private")
        except Exception as e:
            self.logger.warning(f"Gate.io private ping failed: {e}")
            # Continue - built-in ping/pong will handle connection health

    def should_reconnect(self, error: Exception) -> bool:
        """Determine if reconnection should be attempted for Gate.io private errors."""
        # Classify error first
        error_type = self.classify_error(error)
        
        # Don't reconnect on authentication failures
        if error_type == "authentication_failure":
            self.logger.error("Gate.io private authentication failure - won't reconnect")
            return False
        
        # Gate.io private 1005 errors might indicate auth session expired
        if error_type == "abnormal_closure":
            self.logger.warning("Gate.io private 1005 error - may need reauthentication, will reconnect")
            return True
        
        # Reconnect on network and timeout errors
        if error_type in ["connection_refused", "timeout"]:
            self.logger.warning(f"Gate.io private {error_type} error - will reconnect")
            return True
        
        # For unknown errors, try reconnecting (but auth might fail)
        self.logger.warning(f"Gate.io private unknown error ({error}) - will attempt reconnect")
        return True
    
    async def cleanup(self) -> None:
        """Clean up Gate.io private WebSocket resources."""
        self.logger.debug("Gate.io private WebSocket cleanup - authentication session ended")
        pass