import logging
import time
import hashlib
import hmac
from typing import Dict, Any, Optional

from core.cex.websocket import ConnectionStrategy
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

    async def get_connection_url(self) -> str:
        """Get Gate.io private WebSocket URL."""
        return "wss://api.gateio.ws/ws/v4/"

    async def get_connection_headers(self) -> Dict[str, str]:
        """Get connection headers for Gate.io private WebSocket."""
        return {
            "User-Agent": "HFTArbitrageEngine-Gateio/1.0"
        }

    async def handle_connection_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle Gate.io connection-specific messages."""
        # Handle authentication responses and other connection messages
        if message.get("method") == "RESULT" and "id" in message:
            # Authentication response or subscription response
            if message.get("result", {}).get("status") == "success":
                self.logger.info("Gate.io WebSocket authentication successful")
            elif "error" in message:
                self.logger.error(f"Gate.io WebSocket error: {message['error']}")
        
        return message

    def requires_authentication(self) -> bool:
        """Private WebSocket requires authentication."""
        return True

    async def authenticate(self, **kwargs) -> Optional[str]:
        """Generate Gate.io WebSocket authentication message."""
        timestamp = str(int(time.time()))
        
        # Gate.io WebSocket authentication format
        # method=websocket&timestamp={timestamp}
        string_to_sign = f"channel=spot.login&timestamp={timestamp}"
        
        # Create HMAC SHA512 signature
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
        
        auth_message = {
            "method": "SUBSCRIBE",
            "params": ["spot.login"],
            "id": int(timestamp),
            "auth": {
                "method": "api_key",
                "KEY": self.api_key,
                "SIGN": signature,
                "timestamp": timestamp
            }
        }
        
        import msgspec
        return msgspec.json.encode(auth_message).decode()

    def get_ping_interval(self) -> float:
        """Get ping interval for Gate.io (30 seconds recommended)."""
        return 30.0

    def get_ping_message(self) -> str:
        """Get ping message for Gate.io."""
        import msgspec
        
        ping_msg = {
            "method": "PING",
            "params": [],
            "id": int(time.time())
        }
        return msgspec.json.encode(ping_msg).decode()

    def is_pong_message(self, message: Dict[str, Any]) -> bool:
        """Check if message is a pong response."""
        return message.get("method") == "PONG"

    def should_reconnect_on_error(self, error: Exception) -> bool:
        """Determine if should reconnect on error."""
        # Don't reconnect on authentication failures
        error_str = str(error).lower()
        if "auth" in error_str or "unauthorized" in error_str:
            return False
        return True