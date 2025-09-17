import logging
from typing import Dict, Any, Optional

from core.cex.websocket import ConnectionStrategy
from structs.exchange import Symbol


class GateioPublicConnectionStrategy(ConnectionStrategy):
    """Gate.io public WebSocket connection strategy."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def get_connection_url(self) -> str:
        """Get Gate.io public WebSocket URL."""
        return "wss://api.gateio.ws/ws/v4/"

    async def get_connection_headers(self) -> Dict[str, str]:
        """Get connection headers for Gate.io public WebSocket."""
        return {
            "User-Agent": "HFTArbitrageEngine-Gateio/1.0"
        }

    async def handle_connection_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle Gate.io connection-specific messages."""
        # Gate.io doesn't require special connection handling for public channels
        # Just pass through all messages for processing
        return message

    def requires_authentication(self) -> bool:
        """Public WebSocket doesn't require authentication."""
        return False

    async def authenticate(self, **kwargs) -> Optional[str]:
        """Public WebSocket doesn't need authentication."""
        return None

    def get_ping_interval(self) -> float:
        """Get ping interval for Gate.io (30 seconds recommended)."""
        return 30.0

    def get_ping_message(self) -> str:
        """Get ping message for Gate.io."""
        import time
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
        # Reconnect on most errors except authentication failures
        return True