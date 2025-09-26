import time
import hashlib
import hmac
import asyncio
import msgspec
from typing import Dict, Any, Optional
from websockets import connect
from websockets.client import WebSocketClientProtocol

from exchanges.interfaces.ws import ConnectionStrategy, ConnectionContext
from infrastructure.networking.websocket.strategies.connection import ReconnectionPolicy
from config.structs import ExchangeConfig

# HFT Logger Integration
from infrastructure.logging import HFTLoggerInterface, get_strategy_logger, LoggingTimer


class GateioPrivateFuturesConnectionStrategy(ConnectionStrategy):
    """Gate.io private futures WebSocket connection strategy with authentication."""

    def __init__(self, config: ExchangeConfig, logger: Optional[HFTLoggerInterface] = None):
        super().__init__(config, logger)  # Initialize parent with _websocket = None
        
        # Initialize HFT logger with hierarchical tags
        if logger is None:
            tags = ['gateio', 'private', 'ws', 'connection']
            logger = get_strategy_logger('ws.connection.gateio.private', tags)
        
        self.logger = logger

        if not config.credentials.has_private_api:
            raise ValueError("Gate.io credentials not configured for private futures WebSocket")
        
        self.api_key = config.credentials.api_key
        self.secret_key = config.credentials.secret_key
        
        # Gate.io private futures-specific connection settings
        self.websocket_url = self._get_futures_websocket_url(config)
        self.ping_interval = 20  # Gate.io uses 20s ping interval
        self.ping_timeout = 10
        self.max_queue_size = 512
        self.max_message_size = 1024 * 1024  # 1MB
        
        # Log strategy initialization
        self.logger.info("Gate.io private futures connection strategy initialized",
                        websocket_url=self.websocket_url,
                        ping_interval=self.ping_interval,
                        ping_timeout=self.ping_timeout,
                        max_queue_size=self.max_queue_size)
        
        self.logger.metric("ws_connection_strategies_created", 1,
                          tags={"exchange": "gateio", "type": "private_futures"})

    def _get_futures_websocket_url(self, config: ExchangeConfig) -> str:
        """Get appropriate futures WebSocket URL from config or default."""
        # Try to get futures URL from config first
        if hasattr(config, 'futures_websocket_url') and config.futures_websocket_url:
            return config.futures_websocket_url
        
        # Default to USDT futures endpoint (most common)
        return "wss://fx-ws.gateio.ws/v4/ws/usdt/"

    async def connect(self) -> WebSocketClientProtocol:
        """
        Establish Gate.io private futures WebSocket connection with authentication.
        
        Gate.io private futures requires HMAC SHA512 authentication after connection.
        
        Returns:
            Raw WebSocket ClientProtocol
            
        Raises:
            BaseExchangeError: If connection fails
        """
        try:
            with LoggingTimer(self.logger, "gateio_private_futures_ws_connection") as timer:
                self.logger.info("Connecting to Gate.io private futures WebSocket",
                               websocket_url=self.websocket_url)
            
            # Gate.io private futures connection with same optimizations as spot
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
            self.logger.info("Gate.io private futures WebSocket connected, authenticating...",
                           connection_time_ms=timer.elapsed_ms)
            
            # Authenticate after connection
            auth_success = await self.authenticate()
            if not auth_success:
                await self._websocket.close()
                raise BaseExchangeError(401, "Gate.io private futures authentication failed")
            
            self.logger.info("Gate.io private futures WebSocket authenticated successfully")
            
            self.logger.metric("ws_connections_established", 1,
                              tags={"exchange": "gateio", "type": "private_futures"})
            
            self.logger.metric("ws_connection_time_ms", timer.elapsed_ms,
                              tags={"exchange": "gateio", "type": "private_futures"})
            
            return self._websocket
            
        except Exception as e:
            self.logger.error("Failed to connect to Gate.io private futures WebSocket",
                            websocket_url=self.websocket_url,
                            error_type=type(e).__name__,
                            error_message=str(e))
            
            # Track connection failure
            self.logger.metric("ws_connection_failures", 1,
                              tags={"exchange": "gateio", "type": "private_futures", "error_type": type(e).__name__})
            
            raise BaseExchangeError(500, f"Gate.io private futures WebSocket connection failed: {str(e)}")

    def _create_signature(self, channel: str, event: str, timestamp: str) -> str:
        """
        Create HMAC SHA512 signature for Gate.io futures authentication.
        
        Futures authentication uses format: channel=<channel>&event=<event>&time=<time>
        """
        try:
            # Create the message string according to futures API spec
            message = f"channel={channel}&event={event}&time={timestamp}"
            
            # Create HMAC SHA512 signature
            signature = hmac.new(
                self.secret_key.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha512
            ).hexdigest()
            
            self.logger.debug(f"Created signature for message: {message}")
            return signature
            
        except Exception as e:
            self.logger.error(f"Failed to create Gate.io futures signature: {e}")
            raise

    async def authenticate(self) -> bool:
        """
        Authenticate Gate.io private futures WebSocket connection.
        
        Gate.io futures authentication is done via subscription messages with auth info.
        We test authentication by attempting to subscribe to a private channel.
        """
        try:
            timestamp = str(int(time.time()))
            
            # Test authentication with futures.orders channel subscription
            channel = "futures.orders"
            event = "subscribe"
            
            # Create signature using futures format
            signature = self._create_signature(channel, event, timestamp)
            
            # Create authenticated subscription message
            auth_message = {
                "time": int(timestamp),
                "channel": channel,
                "event": event,
                "payload": ["!all"],  # Subscribe to all order updates
                "auth": {
                    "method": "api_key",
                    "KEY": self.api_key,
                    "SIGN": signature
                }
            }
            
            # Send authentication test message
            auth_json = msgspec.json.encode(auth_message).decode()
            await self._websocket.send(auth_json)
            self.logger.debug(f"Sent Gate.io private futures auth test: {channel}")
            
            # Wait for authentication response with timeout
            try:
                response = await asyncio.wait_for(self._websocket.recv(), timeout=10.0)
                auth_response = msgspec.json.decode(response)
                
                self.logger.debug(f"Received auth response: {auth_response}")
                
                # Check authentication result
                error = auth_response.get("error")
                if error is None:
                    # Success if no error is returned
                    self.logger.info("Gate.io private futures authentication successful")
                    return True
                else:
                    error_code = error.get("code", "unknown")
                    error_msg = error.get("message", str(error))
                    
                    # Check if it's an authentication error specifically
                    if error_code in ["INVALID_KEY", "INVALID_SIGN", "PERMISSION_DENIED", "AUTH_FAILED"]:
                        self.logger.error(f"Gate.io private futures authentication failed: {error_msg} (code: {error_code})")
                        return False
                    else:
                        # Other errors might not be authentication related
                        self.logger.warning(f"Gate.io private futures received error but may be authenticated: {error_msg} (code: {error_code})")
                        return True
                    
            except asyncio.TimeoutError:
                self.logger.error("Gate.io private futures authentication timeout")
                return False
                
        except Exception as e:
            self.logger.error(f"Gate.io private futures authentication error: {e}")
            return False

    def create_authenticated_message(self, channel: str, event: str, payload: list = None) -> Dict[str, Any]:
        """
        Create an authenticated message for Gate.io futures private channels.
        
        Args:
            channel: The futures channel (e.g., "futures.orders")
            event: The event type (e.g., "subscribe", "unsubscribe")
            payload: Optional payload for the message
            
        Returns:
            Authenticated message dict ready to send
        """
        timestamp = str(int(time.time()))
        signature = self._create_signature(channel, event, timestamp)
        
        message = {
            "time": int(timestamp),
            "channel": channel,
            "event": event,
            "auth": {
                "method": "api_key",
                "KEY": self.api_key,
                "SIGN": signature
            }
        }
        
        if payload is not None:
            message["payload"] = payload
            
        return message
    
    def get_reconnection_policy(self) -> ReconnectionPolicy:
        """Get Gate.io private futures-specific reconnection policy."""
        return ReconnectionPolicy(
            max_attempts=10,  # Private futures needs fewer attempts due to auth
            initial_delay=3.0,  # Longer initial delay for auth
            backoff_factor=2.0,  # Standard backoff
            max_delay=60.0,  # Higher max delay for auth
            reset_on_1005=True  # Reset on abnormal closure for auth
        )

    def get_ping_message(self) -> str:
        """Get ping message for Gate.io private futures."""
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
        """Create Gate.io private futures WebSocket connection context (legacy support)."""
        return ConnectionContext(
            url=self.websocket_url,
            headers={"User-Agent": "HFTArbitrageEngine-Gateio-PrivateFutures/1.0"},
            auth_required=True,
            ping_interval=self.ping_interval,
            ping_timeout=self.ping_timeout,
            max_reconnect_attempts=10,
            reconnect_delay=3.0
        )

    async def handle_heartbeat(self) -> None:
        """Handle Gate.io private futures heartbeat using internal WebSocket."""
        if not self.is_connected:
            raise RuntimeError("No WebSocket connection available for heartbeat")
            
        try:
            # Send custom ping message through regular WebSocket message channel
            ping_message = self.get_ping_message()
            await self._websocket.send(ping_message)
            self.logger.debug("Sent custom ping message to Gate.io private futures")
        except Exception as e:
            self.logger.warning("Gate.io private futures custom ping failed",
                              error_type=type(e).__name__,
                              error_message=str(e))
            # Continue - built-in ping/pong will handle connection health

    def should_reconnect(self, error: Exception) -> bool:
        """Determine if reconnection should be attempted for Gate.io private futures errors."""
        # Classify error first
        error_type = self.classify_error(error)
        
        should_reconnect = False
        
        # Authentication failures should not reconnect automatically
        if error_type == "authentication_failure":
            self.logger.error("Gate.io private futures authentication failure - won't reconnect")
            should_reconnect = False
        
        # Gate.io private futures 1005 errors need re-authentication
        elif error_type == "abnormal_closure":
            self.logger.info("Gate.io private futures 1005 error detected - will reconnect with re-auth")
            should_reconnect = True
        
        # Reconnect on network and timeout errors
        elif error_type in ["connection_refused", "timeout"]:
            self.logger.warning("Gate.io private futures network error - will reconnect",
                              error_type=error_type)
            should_reconnect = True
        
        # For unknown errors, try reconnecting with re-authentication
        else:
            self.logger.warning("Gate.io private futures unknown error - will attempt reconnect",
                              error_type=error_type,
                              error_message=str(error))
            should_reconnect = True
        
        # Track reconnection decision metrics
        self.logger.metric("ws_reconnection_decisions", 1,
                          tags={"exchange": "gateio", "type": "private_futures", 
                                "error_type": error_type, "should_reconnect": str(should_reconnect)})
        
        return should_reconnect
    
    async def cleanup(self) -> None:
        """Clean up Gate.io private futures WebSocket resources."""
        self.logger.debug("Gate.io private futures WebSocket cleanup - no specific resources to clean")
        pass