import logging
from typing import Any

from core.cex.websocket import ConnectionStrategy, ConnectionContext
from core.config.structs import ExchangeConfig


class MexcPublicConnectionStrategy(ConnectionStrategy):
    """MEXC public WebSocket connection strategy."""

    def __init__(self, config: ExchangeConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def create_connection_context(self) -> ConnectionContext:
        """Create MEXC public WebSocket connection context."""
        # Use the correct MEXC WebSocket URL from documentation
        websocket_url = self.config.websocket_url
        return ConnectionContext(
            url=websocket_url,
            headers={},
            auth_required=False,
            ping_interval=30,
            ping_timeout=10,
            max_reconnect_attempts=10,
            reconnect_delay=1.0
        )

    async def authenticate(self, websocket: Any) -> bool:
        """Public WebSocket requires no authentication."""
        return True

    async def handle_keep_alive(self, websocket: Any) -> None:
        """Handle MEXC keep-alive (ping/pong)."""
        # MEXC uses WebSocket built-in ping/pong mechanism
        # The websocket library handles this automatically with ping_interval/ping_timeout
        # No custom ping messages needed
        pass

    def should_reconnect(self, error: Exception) -> bool:
        """Determine if reconnection should be attempted."""
        # Always reconnect for WebSocket 1005 errors (abnormal closure)
        error_str = str(error)
        if "1005" in error_str or "no status received" in error_str:
            return True
        
        # Reconnect on most errors except authentication failures
        return not isinstance(error, (PermissionError, ValueError))

    async def cleanup(self) -> None:
        """Clean up resources - no specific cleanup needed for public WebSocket."""
        pass
