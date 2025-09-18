import logging
from typing import Dict, Any, Optional

from core.cex.websocket import ConnectionStrategy, ConnectionContext
from core.config.structs import ExchangeConfig
from structs.common import Symbol


class GateioPublicConnectionStrategy(ConnectionStrategy):
    """Gate.io public WebSocket connection strategy."""

    def __init__(self, config: ExchangeConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

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

    async def create_connection_context(self) -> ConnectionContext:
        """Create connection configuration for Gate.io public WebSocket."""
        return ConnectionContext(
            url=self.config.websocket_url,
            headers={"User-Agent": "HFTArbitrageEngine-Gateio/1.0"},
            ping_interval=self.config.websocket.ping_interval,
            ping_message=self.get_ping_message(),
        )

    async def handle_keep_alive(self, websocket: Any) -> None:
        """Handle keep-alive operations for Gate.io."""
        try:
            ping_message = self.get_ping_message()
            await websocket.send(ping_message)
            self.logger.debug("Sent ping message to Gate.io")
        except Exception as e:
            self.logger.warning(f"Failed to send ping: {e}")

    def should_reconnect(self, error: Exception) -> bool:
        """Determine if should reconnect based on error type."""
        return self.should_reconnect_on_error(error)