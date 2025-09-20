import logging
import time
from typing import Any
from websockets import connect
from websockets.client import WebSocketClientProtocol

from core.cex.websocket import ConnectionStrategy, ConnectionContext
from core.transport.websocket.strategies.connection import ReconnectionPolicy
from core.config.structs import ExchangeConfig
from core.exceptions.exchange import BaseExchangeError


class MexcPublicConnectionStrategy(ConnectionStrategy):
    """MEXC public WebSocket connection strategy with direct connection handling."""

    def __init__(self, config: ExchangeConfig):
        super().__init__()  # Initialize parent with _websocket = None
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # MEXC-specific connection settings
        self.websocket_url = config.websocket_url
        self.ping_interval = 30  # MEXC uses 30s ping interval (built-in only)
        self.ping_timeout = 15   # Increased timeout for better stability
        self.max_queue_size = 512
        self.max_message_size = 1024 * 1024  # 1MB

    async def connect(self) -> WebSocketClientProtocol:
        """
        Establish MEXC public WebSocket connection with MEXC-specific optimizations.
        
        MEXC requires minimal headers to avoid blocking. The working implementation
        shows that browser-like headers cause blocking.
        
        Returns:
            Raw WebSocket ClientProtocol
            
        Raises:
            BaseExchangeError: If connection fails
        """
        try:
            self.logger.info(f"Connecting to MEXC WebSocket: {self.websocket_url}")
            
            # MEXC-specific connection with minimal headers to avoid blocking
            # NO extra headers - they cause blocking
            # NO origin header - causes blocking
            self._websocket = await connect(
                self.websocket_url,
                # Performance optimizations for MEXC
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout,
                max_queue=self.max_queue_size,
                # Disable compression for CPU optimization in HFT
                compression=None,
                max_size=self.max_message_size,
                # Additional performance settings
                write_limit=2 ** 20,  # 1MB write buffer
            )
            
            self.logger.info("MEXC WebSocket connected successfully")
            return self._websocket
            
        except Exception as e:
            self.logger.error(f"Failed to connect to MEXC WebSocket: {e}")
            raise BaseExchangeError(500, f"MEXC WebSocket connection failed: {str(e)}")
    
    def get_reconnection_policy(self) -> ReconnectionPolicy:
        """Get MEXC-specific reconnection policy."""
        return ReconnectionPolicy(
            max_attempts=10,
            initial_delay=1.0,
            backoff_factor=2.0,
            max_delay=60.0,
            reset_on_1005=True  # MEXC often has 1005 errors, treat as network issues
        )
    
    async def create_connection_context(self) -> ConnectionContext:
        """Create MEXC public WebSocket connection context (legacy support)."""
        return ConnectionContext(
            url=self.websocket_url,
            headers={},
            auth_required=False,
            ping_interval=self.ping_interval,
            ping_timeout=self.ping_timeout,
            max_reconnect_attempts=10,
            reconnect_delay=1.0
        )

    async def authenticate(self) -> bool:
        """Public WebSocket requires no authentication."""
        return True

    async def handle_heartbeat(self) -> None:
        """Handle MEXC heartbeat (ping/pong) using internal WebSocket."""
        if not self.is_connected:
            raise RuntimeError("No WebSocket connection available for heartbeat")
            
        # MEXC uses WebSocket built-in ping/pong mechanism ONLY
        # The websockets library handles this automatically with ping_interval/ping_timeout
        # No custom ping messages needed for MEXC public WebSocket
        # This method is called by WebSocket manager but we don't send additional pings
        self.logger.debug("MEXC heartbeat: relying on built-in ping/pong mechanism (no custom ping)")
        pass

    def should_reconnect(self, error: Exception) -> bool:
        """Determine if reconnection should be attempted for MEXC errors."""
        # Classify error first
        error_type = self.classify_error(error)
        
        # Always reconnect for WebSocket 1005 errors (very common with MEXC)
        if error_type == "abnormal_closure":
            self.logger.info("MEXC 1005 error detected - will reconnect (common network issue)")
            return True
        
        # Reconnect on network and timeout errors
        if error_type in ["connection_refused", "timeout"]:
            self.logger.warning(f"MEXC {error_type} error - will reconnect")
            return True
        
        # Don't reconnect on authentication failures (shouldn't happen for public)
        if error_type == "authentication_failure":
            self.logger.error("MEXC authentication failure - won't reconnect")
            return False
        
        # For unknown errors, try reconnecting (MEXC can be unstable)
        self.logger.warning(f"MEXC unknown error ({error}) - will attempt reconnect")
        return True

    async def cleanup(self) -> None:
        """Clean up MEXC public WebSocket resources."""
        self.logger.debug("MEXC public WebSocket cleanup - no specific resources to clean")
        pass
