import logging
import time
import hashlib
import hmac
import asyncio
from typing import Dict, Any, Optional

from core.cex.websocket import ConnectionStrategy, ConnectionContext
from core.config.structs import ExchangeConfig


class GateioPrivateConnectionStrategy(ConnectionStrategy):
    """Gate.io private WebSocket connection strategy with authentication."""

    def __init__(self, config: ExchangeConfig):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.config = config
        
        if not config.credentials.is_configured():
            raise ValueError("Gate.io credentials not configured for private WebSocket")
        
        self.api_key = config.credentials.api_key
        self.secret_key = config.credentials.secret_key

    async def handle_connection_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle Gate.io connection-specific messages."""
        # Handle authentication responses and other connection messages using new event format
        if message.get("channel") == "spot.login" and message.get("event") == "api":
            # Authentication response
            result = message.get("result", {})
            if result.get("status") == "success":
                self.logger.info("Gate.io WebSocket authentication successful")
            elif "error" in message:
                self.logger.error(f"Gate.io WebSocket authentication error: {message['error']}")
            elif result.get("status") == "fail":
                self.logger.error("Gate.io WebSocket authentication failed")
        elif message.get("event") in ["ping", "pong"]:
            # Handle ping/pong messages
            self.logger.debug(f"Gate.io {message.get('event')} message received")
        elif message.get("method") == "RESULT" and "id" in message:
            # Fallback: Handle legacy format if still used
            if message.get("result", {}).get("status") == "success":
                self.logger.info("Gate.io WebSocket operation successful")
            elif "error" in message:
                self.logger.error(f"Gate.io WebSocket error: {message['error']}")
        
        return message

    def requires_authentication(self) -> bool:
        """Private WebSocket requires authentication."""
        return True

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
        """Create connection configuration for Gate.io private WebSocket."""
        return ConnectionContext(
            url=self.config.websocket_url,
            headers={"User-Agent": "HFTArbitrageEngine-Gateio/1.0"},
            ping_interval=self.config.websocket.ping_interval,
            ping_message=self.get_ping_message(),
            auth_required=True
        )

    async def authenticate(self, websocket: Any) -> bool:
        """Perform authentication for Gate.io private WebSocket."""
        try:
            auth_message = await self._generate_auth_message()
            if auth_message:
                # Parse JSON string back to dict for send_message
                import msgspec
                auth_dict = msgspec.json.decode(auth_message)
                await websocket.send_message(auth_dict)
                await asyncio.sleep(1)  # Wait a moment for auth to process *MANDATORY*
                self.logger.debug("Sent authentication message to Gate.io")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}")
            return False

    async def handle_keep_alive(self, websocket: Any) -> None:
        """Handle keep-alive operations for Gate.io."""
        try:
            ping_message = self.get_ping_message()
            # Parse JSON string back to dict for send_message
            import msgspec
            ping_dict = msgspec.json.decode(ping_message)
            await websocket.send_message(ping_dict)
            self.logger.debug("Sent ping message to Gate.io")
        except Exception as e:
            self.logger.warning(f"Failed to send ping: {e}")

    def should_reconnect(self, error: Exception) -> bool:
        """Determine if should reconnect based on error type."""
        return self.should_reconnect_on_error(error)