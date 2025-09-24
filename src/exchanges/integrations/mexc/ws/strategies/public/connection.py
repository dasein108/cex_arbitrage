from websockets import connect
from websockets.client import WebSocketClientProtocol

from exchanges.interfaces.ws import ConnectionStrategy, ConnectionContext
from infrastructure.networking.websocket.strategies.connection import ReconnectionPolicy
from config.structs import ExchangeConfig
from infrastructure.exceptions.exchange import BaseExchangeError
from infrastructure.data_structures.connection import WebSocketConnectionSettings, ReconnectionSettings

# HFT Logger Integration
from infrastructure.logging import get_strategy_logger, LoggingTimer


class MexcPublicConnectionStrategy(ConnectionStrategy):
    """MEXC public WebSocket connection strategy with direct connection handling."""

    def __init__(self, config: ExchangeConfig, logger=None):
        super().__init__(config)  # Initialize parent with _websocket = None
        
        # Initialize HFT logger with hierarchical tags
        if logger is None:
            tags = ['mexc', 'public', 'ws', 'connection']
            logger = get_strategy_logger('ws.connection.mexc.public', tags)
        
        self.logger = logger
        
        # MEXC-specific connection settings
        self.websocket_url = config.websocket_url
        ws_settings = WebSocketConnectionSettings(
            ping_interval=30,  # MEXC uses 30s ping interval
            ping_timeout=15,   # Increased timeout for better stability
            max_queue_size=512,
            max_message_size=1024 * 1024,  # 1MB
            write_limit=2 ** 20  # 1MB write buffer
        )
        self.ping_interval = ws_settings.ping_interval
        self.ping_timeout = ws_settings.ping_timeout
        self.max_queue_size = ws_settings.max_queue_size
        self.max_message_size = ws_settings.max_message_size
        self.write_limit = ws_settings.write_limit
        
        # Log strategy initialization
        self.logger.info("MEXC public connection strategy initialized",
                        websocket_url=self.websocket_url,
                        ping_interval=self.ping_interval,
                        ping_timeout=self.ping_timeout,
                        max_queue_size=self.max_queue_size)
        
        self.logger.metric("ws_connection_strategies_created", 1,
                          tags={"exchange": "mexc", "type": "public"})

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
            with LoggingTimer(self.logger, "mexc_ws_connection") as timer:
                self.logger.info("Connecting to MEXC WebSocket",
                               websocket_url=self.websocket_url)
                
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
                    write_limit=self.write_limit
                )
            
            # Track successful connection
            self.logger.info("MEXC WebSocket connected successfully",
                           connection_time_ms=timer.elapsed_ms)
            
            self.logger.metric("ws_connections_established", 1,
                              tags={"exchange": "mexc", "type": "public"})
            
            self.logger.metric("ws_connection_time_ms", timer.elapsed_ms,
                              tags={"exchange": "mexc", "type": "public"})
            
            return self._websocket
            
        except Exception as e:
            self.logger.error("Failed to connect to MEXC WebSocket",
                            websocket_url=self.websocket_url,
                            error_type=type(e).__name__,
                            error_message=str(e))
            
            # Track connection failure
            self.logger.metric("ws_connection_failures", 1,
                              tags={"exchange": "mexc", "type": "public", "error_type": type(e).__name__})
            
            raise BaseExchangeError(500, f"MEXC WebSocket connection failed: {str(e)}")
    
    def get_reconnection_policy(self) -> ReconnectionPolicy:
        """Get MEXC-specific reconnection policy."""
        settings = ReconnectionSettings(
            max_attempts=10,
            initial_delay=1.0,
            backoff_factor=2.0,
            max_delay=60.0,
            reset_on_1005=True  # MEXC often has 1005 errors
        )
        return ReconnectionPolicy(
            max_attempts=settings.max_attempts,
            initial_delay=settings.initial_delay,
            backoff_factor=settings.backoff_factor,
            max_delay=settings.max_delay,
            reset_on_1005=settings.reset_on_1005
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
        should_reconnect = False
        
        # Always reconnect for WebSocket 1005 errors (very common with MEXC)
        if error_type == "abnormal_closure":
            self.logger.info("MEXC 1005 error detected - will reconnect (common network issue)")
            should_reconnect = True
        
        # Reconnect on network and timeout errors
        elif error_type in ["connection_refused", "timeout"]:
            self.logger.warning("MEXC network error - will reconnect",
                              error_type=error_type)
            should_reconnect = True
        
        # Don't reconnect on authentication failures (shouldn't happen for public)
        elif error_type == "authentication_failure":
            self.logger.error("MEXC authentication failure - won't reconnect")
            should_reconnect = False
        
        # For unknown errors, try reconnecting (MEXC can be unstable)
        else:
            self.logger.warning("MEXC unknown error - will attempt reconnect",
                              error_type=error_type,
                              error_message=str(error))
            should_reconnect = True
        
        # Track reconnection decision metrics
        self.logger.metric("ws_reconnection_decisions", 1,
                          tags={"exchange": "mexc", "type": "public", 
                                "error_type": error_type, "should_reconnect": str(should_reconnect)})
        
        return should_reconnect

    async def cleanup(self) -> None:
        """Clean up MEXC public WebSocket resources."""
        self.logger.debug("MEXC public WebSocket cleanup - no specific resources to clean")
        pass
