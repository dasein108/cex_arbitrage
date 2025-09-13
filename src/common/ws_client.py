from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union, Awaitable
import asyncio
import time
import logging
from contextlib import asynccontextmanager
from collections import deque
from websockets import connect #, State
import msgspec
import json

from common.exceptions import ExchangeAPIError


class ConnectionState(Enum):
    """WebSocket connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    CLOSING = "closing"
    CLOSED = "closed"


class SubscriptionAction(Enum):
    """WebSocket subscription actions"""
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"


class WebSocketConfig(msgspec.Struct):
    """Configuration for WebSocket connections optimized for trading"""
    # Connection settings
    name: str
    url: Optional[str] = None
    timeout: float = 30.0
    ping_interval: float = 20.0
    ping_timeout: float = 10.0
    close_timeout: float = 5.0
    
    # Reconnection settings
    max_reconnect_attempts: int = 10
    reconnect_delay: float = 1.0
    reconnect_backoff: float = 2.0
    max_reconnect_delay: float = 60.0
    
    # Performance settings
    max_message_size: int = 1024 * 1024  # 1MB
    max_queue_size: int = 1000
    heartbeat_interval: float = 30.0
    
    # Compression and encoding
    enable_compression: bool = True
    text_encoding: str = "utf-8"


class WebsocketClient:
    """
    Abstract base class for high-performance WebSocket connections.
    
    This interface is completely data format agnostic and provides:
    - High-performance async WebSocket management
    - Automatic reconnection with exponential backoff
    - Subscription management
    - Error handling and recovery
    - Connection lifecycle management
    """

    __slots__ = (
        'exchange', 'config', 'message_handler', 'error_handler',
        '_state', '_ws', '_loop', '_connection_task', '_reader_task',
        '_subscriptions', '_pending_subscriptions', '_reconnect_attempts',
        '_should_reconnect', '_last_pong', 'logger',
        '_cached_backoff_delays', '_message_count', '_time_cache', 'get_connect_url'
    )
    
    def __init__(
        self,
        config: WebSocketConfig,
        message_handler: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        error_handler: Optional[Callable[[Exception], Awaitable[None]]] = None,
        get_connect_url: Optional[Callable[[], Awaitable[str]]] = None
    ):
        self.config = config
        self.message_handler = message_handler
        self.error_handler = error_handler
        self.get_connect_url = get_connect_url
        
        # Connection state
        self._state = ConnectionState.DISCONNECTED
        self._ws = None
        self._loop = None
        self._connection_task = None
        self._reader_task = None
        
        # Subscription management - optimized data structures
        self._subscriptions: Dict[str, Dict[str, Any]] = {}
        self._pending_subscriptions = deque()  # O(1) append/popleft instead of O(n) clear
        
        # Reconnection control
        self._reconnect_attempts = 0
        self._should_reconnect = True
        self._last_pong = 0.0
        
        # Pre-computed backoff delays for performance (avoid power calculations)
        self._cached_backoff_delays = self._precompute_backoff_delays()
        
        # Performance optimizations
        self._message_count = 0  # Local counter to reduce time() calls
        self._time_cache = time.time()  # Cache time for batched updates
        
        self.logger = logging.getLogger(f"{__name__}.{self.config.name}")
    
    def _precompute_backoff_delays(self) -> List[float]:
        """Pre-compute exponential backoff delays to avoid power calculations in hot path"""
        delays = []
        for attempt in range(self.config.max_reconnect_attempts):
            delay = min(
                self.config.reconnect_delay * (self.config.reconnect_backoff ** attempt),
                self.config.max_reconnect_delay
            )
            delays.append(delay)
        return delays
    
    @property
    def state(self) -> ConnectionState:
        """Current connection state"""
        return self._state
    
    @property
    def is_connected(self) -> bool:
        """True if WebSocket is connected and ready"""
        return self._state == ConnectionState.CONNECTED and self._ws is not None
    
    @property
    def subscriptions(self) -> Dict[str, Dict[str, Any]]:
        """Current active subscriptions - returns view to avoid copying"""
        return dict(self._subscriptions)  # Only copy when actually needed
    
    # Abstract methods that must be implemented by exchange-specific classes

    async def _send_subscription_message(
            self,
            streams: List[str],
            action: SubscriptionAction
    ) -> None:
        """
        Send subscription message to MEXC WebSocket.

        MEXC uses exact format: {"method": "SUBSCRIPTION", "params": [streams]}
        Based on working legacy implementation in raw/mexc_api/websocket/mexc_ws.py
        """
        if not self._ws: # TODO: ????  or self._ws.state != State.OPEN:
            raise ExchangeAPIError(500, "WebSocket not connected")

        try:
            # MEXC subscription message format - exact match from legacy working code
            method = "SUBSCRIPTION" if action == SubscriptionAction.SUBSCRIBE else "UNSUBSCRIPTION"
            message = {
                "method": method,
                "params": streams
                # No "id" field - legacy working code doesn't include it
            }
            
            # Send as JSON bytes using msgspec for HFT performance
            message_bytes = msgspec.json.encode(message)
            await self._ws.send(message_bytes)

            action_str = "Subscribed to" if action == SubscriptionAction.SUBSCRIBE else "Unsubscribed from"
            self.logger.info(f"{action_str} {len(streams)} streams")

        except Exception as e:
            self.logger.error(f"Failed to send subscription message: {e}")
            raise ExchangeAPIError(500, f"Subscription failed: {str(e)}")

    async def _connect(self) -> None:
        """
        Establish WebSocket connection with MEXC-optimized settings.

        Uses minimal headers to avoid blocking by MEXC.
        The working implementation shows that browser-like headers cause blocking.
        """
        try:
            # Close existing connection if any
            if self._ws: # TODO: ??? and self._ws.state != State.CLOSED:
                await self._ws.close()

            self.logger.info(f"Connecting to WebSocket: {self.config.url}")

            # Minimal connection - no extra headers to avoid blocking
            # The working simple_websocket.py shows this approach works
            url = self.config.url
            if self.get_connect_url:
                url = await self.get_connect_url()
                self.logger.info(f"Using dynamic WebSocket URL: {url}")

            self._ws = await connect(
                url,
                # NO extra headers - they cause blocking
                # NO origin header - causes blocking
                # Performance optimizations
                ping_interval=self.config.ping_interval,
                ping_timeout=self.config.ping_timeout,
                max_queue=self.config.max_queue_size,
                # Disable compression for CPU optimization in HFT
                compression=None,
                max_size=self.config.max_message_size,
                # Additional performance settings
                write_limit=2 ** 20,  # 1MB write buffer
                # read_limit parameter not supported in websockets 15.0.1
            )

            self.logger.info("WebSocket connected successfully")

        except Exception as e:
            self.logger.error(f"Failed to connect to WebSocket: {e}")
            raise ExchangeAPIError(500, f"WebSocket connection failed: {str(e)}")



    # Connection lifecycle management
    
    async def start(self) -> None:
        """Start the WebSocket connection - optimized"""
        if self._connection_task is not None:
            return
        
        self._loop = asyncio.get_running_loop()
        self._should_reconnect = True
        # Use direct asyncio.create_task for better performance
        self._connection_task = asyncio.create_task(self._connection_loop())
        
        if self.logger.isEnabledFor(logging.INFO):
            self.logger.info("Started WebSocket connection for %s", self.config.name)
    
    async def stop(self) -> None:
        """Stop the WebSocket connection gracefully - optimized"""
        self._should_reconnect = False
        self._state = ConnectionState.CLOSING
        
        # Cancel running tasks efficiently
        tasks_to_cancel = []
        if self._reader_task and not self._reader_task.done():
            tasks_to_cancel.append(self._reader_task)
        if self._connection_task and not self._connection_task.done():
            tasks_to_cancel.append(self._connection_task)
        
        for task in tasks_to_cancel:
            task.cancel()
        
        # Close WebSocket connection with optimized error handling
        if self._ws:
            try:
                await asyncio.wait_for(self._ws.close(), timeout=self.config.close_timeout)
            except asyncio.TimeoutError:
                if self.logger.isEnabledFor(logging.WARNING):
                    self.logger.warning("WebSocket close timeout")
            except Exception as e:
                if self.logger.isEnabledFor(logging.ERROR):
                    self.logger.error("Error closing WebSocket: %s", e)
        
        self._state = ConnectionState.CLOSED
        if self.logger.isEnabledFor(logging.INFO):
            self.logger.info("Stopped WebSocket connection for %s", self.config.name)
    
    async def restart(self) -> None:
        """Restart the WebSocket connection - optimized restart sequence"""
        await self.stop()
        self._message_count = 0
        self._time_cache = time.time()
        self._reconnect_attempts = 0
        await asyncio.sleep(1.0)
        await self.start()
    
    # Subscription management
    
    async def subscribe(self, streams: List[str] ) -> None:
        """
        Subscribe to streams - optimized for memory efficiency.
        
        Args:
            streams: List of stream identifiers
            stream_params: Optional parameters for subscription
        """
        if not streams:
            return
        
        if self.is_connected:
            await self._send_subscription_message(streams, SubscriptionAction.SUBSCRIBE)
        else:
            # Queue for when connection is established - use efficient deque
            self._pending_subscriptions.append((streams, SubscriptionAction.SUBSCRIBE))
        
        # Lazy logging to avoid string formatting overhead
        if self.logger.isEnabledFor(logging.INFO):
            self.logger.info("Subscribing to %d streams", len(streams))
    
    async def unsubscribe(self, streams: List[str]) -> None:
        """
        Unsubscribe from streams - optimized for performance.
        
        Args:
            streams: List of stream identifiers to unsubscribe from
        """
        if not streams:
            return
        
        # Optimized removal - batch operation
        subscriptions = self._subscriptions
        for stream in streams:
            subscriptions.pop(stream, None)
        
        if self.is_connected:
            await self._send_subscription_message(streams, SubscriptionAction.UNSUBSCRIBE)
        
        # Lazy logging to avoid string formatting overhead
        if self.logger.isEnabledFor(logging.INFO):
            self.logger.info("Unsubscribing from %d streams", len(streams))
    
    # Message handling
    
    async def send_message(self, message: Dict[str, Any]) -> None:
        """
        Send a message through the WebSocket.
        Message will be serialized appropriately for the connection.
        """
        if not self.is_connected:
            raise ExchangeAPIError(500, "WebSocket not connected")
        
        try:
            # Optimized serialization - avoid decode step for bytes
            serialized_bytes = msgspec.json.encode(message)
            await self._ws.send(serialized_bytes)
        except Exception as e:
            raise ExchangeAPIError(500, f"Failed to send message: {str(e)}")
    
    # Internal connection management
    
    async def _connection_loop(self) -> None:
        """Main connection loop with automatic reconnection - optimized"""
        connect_time = time.time()
        
        while self._should_reconnect:
            try:
                self._state = ConnectionState.CONNECTING
                await self._connect()
                
                if self._ws is None:
                    raise ExchangeAPIError(500, "Connection failed - no WebSocket created")
                
                self._state = ConnectionState.CONNECTED
                self._reconnect_attempts = 0
                current_time = time.time()
                self._time_cache = current_time
                
                # Process pending subscriptions
                await self._process_pending_subscriptions()
                
                # Start message reader with optimized task creation
                self._reader_task = asyncio.create_task(self._message_reader())
                
                if self.logger.isEnabledFor(logging.INFO):
                    self.logger.info("WebSocket connected to %s", self.config.name)
                
                # Wait for connection to close
                await self._reader_task
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                await self._handle_connection_error(e)
        
        self._state = ConnectionState.DISCONNECTED
    
    async def _message_reader(self) -> None:
        """Read and process messages from WebSocket - optimized for high throughput"""
        # Performance optimizations: cache frequently accessed values
        message_handler = self.message_handler
        error_handler = self.error_handler
        
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("Starting message reader loop")
        
        try:
            while self.is_connected:
                # This is the correct pattern from the working implementation
                try:
                    raw_message = await self._ws.recv()

                    # Handle message - direct call to avoid lookup overhead
                    if message_handler:
                        await message_handler(raw_message)
                    
                except Exception as e:
                    # Avoid string formatting in hot path - use lazy logging
                    if self.logger.isEnabledFor(logging.ERROR):
                        self.logger.error("Error processing message: %s", e)
                    
                    if error_handler:
                        await error_handler(e)
                
        except asyncio.CancelledError:
            if self.logger.isEnabledFor(logging.INFO):
                self.logger.info("Message reader cancelled")
        except Exception as e:
            if self.logger.isEnabledFor(logging.ERROR):
                self.logger.error("Message reader error: %s", e)
            if error_handler:
                await error_handler(e)
    
    async def _process_pending_subscriptions(self) -> None:
        """Process queued subscriptions after connection - optimized with deque"""
        pending = self._pending_subscriptions
        
        # Process all pending subscriptions efficiently
        while pending:
            try:
                streams, action = pending.popleft()
                await self._send_subscription_message(streams, action)
            except Exception as e:
                if self.logger.isEnabledFor(logging.ERROR):
                    self.logger.error("Failed to process pending subscription: %s", e)
                break  # Stop processing on first error to avoid cascade failures
    
    async def _handle_connection_error(self, error: Exception) -> None:
        """Handle connection errors with pre-computed exponential backoff"""
        self._state = ConnectionState.ERROR

        if self._reconnect_attempts >= self.config.max_reconnect_attempts:
            if self.logger.isEnabledFor(logging.ERROR):
                self.logger.error("Max reconnection attempts reached for %s", self.config.name)
            self._should_reconnect = False
            return
        
        # Use pre-computed backoff delay - no power calculation needed
        delay = self._cached_backoff_delays[self._reconnect_attempts]
        
        self._reconnect_attempts += 1

        # Lazy logging with optimized formatting
        if self.logger.isEnabledFor(logging.WARNING):
            self.logger.warning(
                "Connection error for %s (attempt %d): %s. Reconnecting in %.1fs",
                self.config.name, self._reconnect_attempts, error, delay
            )
        
        self._state = ConnectionState.RECONNECTING
        await asyncio.sleep(delay)
    
    # Context manager support
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.stop()


