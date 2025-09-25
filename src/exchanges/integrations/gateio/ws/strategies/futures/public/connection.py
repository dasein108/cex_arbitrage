from typing import Dict, Any, Optional
from websockets import connect
from websockets.client import WebSocketClientProtocol

from exchanges.interfaces.ws import ConnectionStrategy, ConnectionContext
from infrastructure.networking.websocket.strategies.connection import ReconnectionPolicy
from config.structs import ExchangeConfig
from infrastructure.exceptions.exchange import BaseExchangeError

# HFT Logger Integration
from infrastructure.logging import HFTLoggerInterface, get_strategy_logger, LoggingTimer


class GateioPublicFuturesConnectionStrategy(ConnectionStrategy):
    """Gate.io futures WebSocket connection strategy with futures-specific endpoints."""

    def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None):
        super().__init__(config, logger)  # Initialize parent with _websocket = None
        
        # Initialize HFT logger with hierarchical tags
        if logger is None:
            tags = ['gateio', 'public', 'ws', 'connection']
            logger = get_strategy_logger('ws.connection.gateio.public', tags)
        
        self.logger = logger
        
        # Gate.io futures-specific connection settings
        self.websocket_url = self._get_futures_websocket_url(config)
        self.ping_interval = 20  # Gate.io uses 20s ping interval
        self.ping_timeout = 10
        self.max_queue_size = 512
        self.max_message_size = 1024 * 1024  # 1MB
        
        # Log strategy initialization
        self.logger.info("Gate.io futures public connection strategy initialized",
                        websocket_url=self.websocket_url,
                        ping_interval=self.ping_interval,
                        ping_timeout=self.ping_timeout,
                        max_queue_size=self.max_queue_size)
        
        self.logger.metric("ws_connection_strategies_created", 1,
                          tags={"exchange": "gateio", "type": "public_futures"})

    def _get_futures_websocket_url(self, config: ExchangeConfig) -> str:
        """Get appropriate futures WebSocket URL from config or default."""
        # Try to get futures URL from config first
        if hasattr(config, 'futures_websocket_url') and config.futures_websocket_url:
            return config.futures_websocket_url
        
        # Default to USDT futures endpoint (most common)
        return "wss://fx-ws.gateio.ws/v4/ws/usdt/"

    async def connect(self) -> WebSocketClientProtocol:
        """
        Establish Gate.io futures WebSocket connection.
        
        Similar to spot connection but uses futures-specific endpoint.
        
        Returns:
            Raw WebSocket ClientProtocol
            
        Raises:
            BaseExchangeError: If connection fails
        """
        try:
            with LoggingTimer(self.logger, "gateio_futures_ws_connection") as timer:
                self.logger.info("Connecting to Gate.io Futures WebSocket",
                               websocket_url=self.websocket_url)
            
            # Gate.io futures connection with same optimizations as spot
            self._websocket = await connect(
                self.websocket_url,
                ping_interval=None,  # DISABLE built-in ping - we use custom ping messages
                ping_timeout=None,   # DISABLE built-in ping timeout
                max_queue=self.max_queue_size,
                compression="deflate",
                max_size=self.max_message_size,
                write_limit=2 ** 20,  # 1MB write buffer
            )
            
            # Track successful connection
            self.logger.info("Gate.io Futures WebSocket connected successfully",
                           connection_time_ms=timer.elapsed_ms)
            
            self.logger.metric("ws_connections_established", 1,
                              tags={"exchange": "gateio", "type": "public_futures"})
            
            self.logger.metric("ws_connection_time_ms", timer.elapsed_ms,
                              tags={"exchange": "gateio", "type": "public_futures"})
            
            return self._websocket
            
        except Exception as e:
            self.logger.error("Failed to connect to Gate.io Futures WebSocket",
                            websocket_url=self.websocket_url,
                            error_type=type(e).__name__,
                            error_message=str(e))
            
            # Track connection failure
            self.logger.metric("ws_connection_failures", 1,
                              tags={"exchange": "gateio", "type": "public_futures", "error_type": type(e).__name__})
            
            raise BaseExchangeError(500, f"Gate.io Futures WebSocket connection failed: {str(e)}")
    
    def get_reconnection_policy(self) -> ReconnectionPolicy:
        """Get Gate.io futures-specific reconnection policy."""
        return ReconnectionPolicy(
            max_attempts=15,  # Gate.io futures is stable, allow more attempts
            initial_delay=2.0,  # Longer initial delay
            backoff_factor=1.5,  # Gentler backoff
            max_delay=30.0,  # Lower max delay
            reset_on_1005=False  # Gate.io 1005 errors are less common
        )

    def get_ping_message(self) -> str:
        """Get ping message for Gate.io futures."""
        import time
        import msgspec
        
        ping_msg = {
            "time": int(time.time()),
            "channel": "futures.ping",  # Futures-specific ping channel
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
        """Create Gate.io futures WebSocket connection context (legacy support)."""
        return ConnectionContext(
            url=self.websocket_url,
            headers={"User-Agent": "HFTArbitrageEngine-Gateio-Futures/1.0"},
            auth_required=False,
            ping_interval=self.ping_interval,
            ping_timeout=self.ping_timeout,
            max_reconnect_attempts=15,
            reconnect_delay=2.0
        )
    
    async def authenticate(self) -> bool:
        """Public futures WebSocket requires no authentication."""
        return True

    async def handle_heartbeat(self) -> None:
        """Handle Gate.io futures heartbeat using internal WebSocket."""
        if not self.is_connected:
            raise RuntimeError("No WebSocket connection available for heartbeat")
            
        try:
            # Send custom ping message through regular WebSocket message channel
            ping_message = self.get_ping_message()
            await self._websocket.send(ping_message)
            self.logger.debug("Sent custom ping message to Gate.io Futures")
        except Exception as e:
            self.logger.warning("Gate.io Futures custom ping failed",
                              error_type=type(e).__name__,
                              error_message=str(e))
            # Continue - built-in ping/pong will handle connection health

    def should_reconnect(self, error: Exception) -> bool:
        """Determine if reconnection should be attempted for Gate.io futures errors."""
        # Classify error first
        error_type = self.classify_error(error)
        
        should_reconnect = False
        
        # Gate.io futures 1005 errors are less common but still reconnectable
        if error_type == "abnormal_closure":
            self.logger.info("Gate.io Futures 1005 error detected - will reconnect")
            should_reconnect = True
        
        # Reconnect on network and timeout errors
        elif error_type in ["connection_refused", "timeout"]:
            self.logger.warning("Gate.io Futures network error - will reconnect",
                              error_type=error_type)
            should_reconnect = True
        
        # Don't reconnect on authentication failures (shouldn't happen for public)
        elif error_type == "authentication_failure":
            self.logger.error("Gate.io Futures authentication failure - won't reconnect")
            should_reconnect = False
        
        # For unknown errors, try reconnecting (Gate.io futures is generally stable)
        else:
            self.logger.warning("Gate.io Futures unknown error - will attempt reconnect",
                              error_type=error_type,
                              error_message=str(error))
            should_reconnect = True
        
        # Track reconnection decision metrics
        self.logger.metric("ws_reconnection_decisions", 1,
                          tags={"exchange": "gateio", "type": "public_futures", 
                                "error_type": error_type, "should_reconnect": str(should_reconnect)})
        
        return should_reconnect
    
    async def cleanup(self) -> None:
        """Clean up Gate.io futures WebSocket resources."""
        self.logger.debug("Gate.io futures WebSocket cleanup - no specific resources to clean")
        pass