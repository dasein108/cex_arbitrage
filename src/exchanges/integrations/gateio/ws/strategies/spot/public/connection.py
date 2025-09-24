import logging
from typing import Dict, Any
from websockets import connect
from websockets.client import WebSocketClientProtocol

from exchanges.interfaces.ws import ConnectionStrategy, ConnectionContext
from infrastructure.networking.websocket.strategies.connection import ReconnectionPolicy
from infrastructure.config.structs import ExchangeConfig
from infrastructure.exceptions.exchange import BaseExchangeError
from infrastructure.data_structures.connection import WebSocketConnectionSettings, ReconnectionSettings


class GateioPublicConnectionStrategy(ConnectionStrategy):
    """Gate.io public WebSocket connection strategy with direct connection handling."""

    def __init__(self, config: ExchangeConfig):
        super().__init__(config)  # Initialize parent with _websocket = None
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Gate.io-specific connection settings
        self.websocket_url = config.websocket_url
        ws_settings = WebSocketConnectionSettings(
            ping_interval=20,  # Gate.io uses 20s ping interval
            ping_timeout=10,
            max_queue_size=512,
            max_message_size=1024 * 1024,  # 1MB
            write_limit=2 ** 20  # 1MB write buffer
        )
        self.ping_interval = ws_settings.ping_interval
        self.ping_timeout = ws_settings.ping_timeout
        self.max_queue_size = ws_settings.max_queue_size
        self.max_message_size = ws_settings.max_message_size
        self.write_limit = ws_settings.write_limit

    async def connect(self) -> WebSocketClientProtocol:
        """
        Establish Gate.io public WebSocket connection with Gate.io-specific optimizations.
        
        Gate.io requires custom ping messages and has different connection characteristics
        compared to MEXC.
        
        Returns:
            Raw WebSocket ClientProtocol
            
        Raises:
            BaseExchangeError: If connection fails
        """
        try:
            self.logger.info(f"Connecting to Gate.io WebSocket: {self.websocket_url}")
            
            # Gate.io-specific connection with custom headers
            # IMPORTANT: Disable built-in ping since we use custom ping messages
            # This prevents conflict between built-in ping/pong and custom ping
            self._websocket = await connect(
                self.websocket_url,
                # Gate.io-specific optimizations
                # extra_headers={
                #     "User-Agent": "HFTArbitrageEngine-Gateio/1.0"
                # },
                ping_interval=None,  # DISABLE built-in ping - we use custom ping messages
                ping_timeout=None,   # DISABLE built-in ping timeout
                max_queue=self.max_queue_size,
                # Gate.io works well with compression
                compression="deflate",
                max_size=self.max_message_size,
                write_limit=self.write_limit
            )
            
            self.logger.info("Gate.io WebSocket connected successfully")
            return self._websocket
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Gate.io WebSocket: {e}")
            raise BaseExchangeError(500, f"Gate.io WebSocket connection failed: {str(e)}")
    
    def get_reconnection_policy(self) -> ReconnectionPolicy:
        """Get Gate.io-specific reconnection policy."""
        settings = ReconnectionSettings(
            max_attempts=15,  # Gate.io is more stable
            initial_delay=2.0,
            backoff_factor=1.5,
            max_delay=30.0,
            reset_on_1005=False  # Gate.io 1005 errors are less common
        )
        return ReconnectionPolicy(
            max_attempts=settings.max_attempts,
            initial_delay=settings.initial_delay,
            backoff_factor=settings.backoff_factor,
            max_delay=settings.max_delay,
            reset_on_1005=settings.reset_on_1005
        )

    def get_ping_message(self) -> str:
        """Get ping message for Gate.io."""
        import time
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
        # Reconnect on most errors except authentication failures
        return True

    async def create_connection_context(self) -> ConnectionContext:
        """Create Gate.io public WebSocket connection context (legacy support)."""
        return ConnectionContext(
            url=self.websocket_url,
            headers={"User-Agent": "HFTArbitrageEngine-Gateio/1.0"},
            auth_required=False,
            ping_interval=self.ping_interval,
            ping_timeout=self.ping_timeout,
            max_reconnect_attempts=15,
            reconnect_delay=2.0
        )
    
    async def authenticate(self) -> bool:
        """Public WebSocket requires no authentication."""
        return True

    async def handle_heartbeat(self) -> None:
        """Handle Gate.io heartbeat (ping/pong with custom messages) using internal WebSocket."""
        if not self.is_connected:
            raise RuntimeError("No WebSocket connection available for heartbeat")
            
        # Gate.io uses both built-in WebSocket ping/pong AND custom ping messages
        # The built-in mechanism is handled by websockets library
        # Custom ping is sent through regular message channel
        try:
            # Send custom ping message through regular WebSocket message channel
            ping_message = self.get_ping_message()
            await self._websocket.send(ping_message)
            self.logger.debug("Sent custom ping message to Gate.io")
        except Exception as e:
            self.logger.warning(f"Gate.io custom ping failed: {e}")
            # Continue - built-in ping/pong will handle connection health

    def should_reconnect(self, error: Exception) -> bool:
        """Determine if reconnection should be attempted for Gate.io errors."""
        # Classify error first
        error_type = self.classify_error(error)
        
        # Gate.io 1005 errors are less common but still reconnectable
        if error_type == "abnormal_closure":
            self.logger.info("Gate.io 1005 error detected - will reconnect (less common than MEXC)")
            return True
        
        # Reconnect on network and timeout errors
        if error_type in ["connection_refused", "timeout"]:
            self.logger.warning(f"Gate.io {error_type} error - will reconnect")
            return True
        
        # Don't reconnect on authentication failures (shouldn't happen for public)
        if error_type == "authentication_failure":
            self.logger.error("Gate.io authentication failure - won't reconnect")
            return False
        
        # For unknown errors, try reconnecting (Gate.io is generally stable)
        self.logger.warning(f"Gate.io unknown error ({error}) - will attempt reconnect")
        return True
    
    async def cleanup(self) -> None:
        """Clean up Gate.io public WebSocket resources."""
        self.logger.debug("Gate.io public WebSocket cleanup - no specific resources to clean")
        pass