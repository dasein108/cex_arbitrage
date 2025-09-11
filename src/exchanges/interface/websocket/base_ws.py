from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union, Awaitable
import asyncio
import time
import logging
from contextlib import asynccontextmanager
from collections import deque
import msgspec

from common.exceptions import ExchangeAPIError
from structs.exchange import ExchangeName, StreamType


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
    url: str
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


class _PerformanceMetrics:
    """High-performance metrics collection with __slots__ for memory efficiency"""
    __slots__ = (
        'messages_received', 'messages_sent', 'connections', 'reconnections',
        'errors', 'last_message_time', 'connection_uptime', '_start_time'
    )
    
    def __init__(self):
        self.messages_received = 0
        self.messages_sent = 0
        self.connections = 0
        self.reconnections = 0
        self.errors = 0
        self.last_message_time = 0.0
        self.connection_uptime = 0.0
        self._start_time = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary - only called when needed for external access"""
        return {
            'messages_received': self.messages_received,
            'messages_sent': self.messages_sent,
            'connections': self.connections,
            'reconnections': self.reconnections,
            'errors': self.errors,
            'last_message_time': self.last_message_time,
            'connection_uptime': self.connection_uptime
        }


class BaseWebSocketInterface(ABC):
    """
    Abstract base class for high-performance WebSocket connections.
    
    This interface is completely data format agnostic and provides:
    - High-performance async WebSocket management
    - Automatic reconnection with exponential backoff
    - Subscription management
    - Error handling and recovery
    - Metrics collection
    - Connection lifecycle management
    """
    
    __slots__ = (
        'exchange', 'config', 'message_handler', 'error_handler',
        '_state', '_ws', '_loop', '_connection_task', '_reader_task',
        '_subscriptions', '_pending_subscriptions', '_reconnect_attempts',
        '_should_reconnect', '_last_pong', '_metrics', 'logger',
        '_cached_backoff_delays', '_message_count', '_time_cache'
    )
    
    def __init__(
        self,
        config: WebSocketConfig,
        message_handler: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        error_handler: Optional[Callable[[Exception], Awaitable[None]]] = None
    ):
        self.config = config
        self.message_handler = message_handler
        self.error_handler = error_handler
        
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
        
        # Performance metrics - using optimized slots-based class
        self._metrics = _PerformanceMetrics()
        
        # Performance optimizations
        self._message_count = 0  # Local counter to reduce time() calls
        self._time_cache = time.time()  # Cache time for batched updates
        
        self.logger = logging.getLogger(f"{__name__}.{self.exchange}")
    
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
    
    @property
    def metrics(self) -> Dict[str, Any]:
        """Performance metrics - optimized to avoid unnecessary copying"""
        return self._metrics.to_dict()
    
    # Abstract methods that must be implemented by exchange-specific classes
    
    @abstractmethod
    async def _connect(self) -> None:
        """
        Establish WebSocket connection to the exchange.
        Implementation should set self._ws to the connected WebSocket.
        """
        pass
    
    @abstractmethod
    async def _send_subscription_message(
        self, 
        streams: List[str], 
        action: SubscriptionAction
    ) -> None:
        """
        Send subscription/unsubscription message to the exchange.
        Format is completely exchange-specific and data format agnostic.
        """
        pass
    
    @abstractmethod
    async def _parse_message(self, raw_message: Union[str, bytes]) -> Optional[Dict[str, Any]]:
        """
        Parse raw WebSocket message into a standardized dictionary.
        This method handles all data format specifics (JSON, protobuf, etc.).
        
        Returns None if message should be ignored (heartbeat, etc.).
        """
        pass
    
    @abstractmethod
    def _extract_stream_info(self, message: Dict[str, Any]) -> Optional[tuple[str, StreamType]]:
        """
        Extract stream identifier and type from parsed message.
        Returns (stream_id, stream_type) or None if not applicable.
        """
        pass
    
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
            self.logger.info("Started WebSocket connection for %s", self.exchange)
    
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
            self.logger.info("Stopped WebSocket connection for %s", self.exchange)
    
    async def restart(self) -> None:
        """Restart the WebSocket connection - optimized restart sequence"""
        await self.stop()
        # Reset metrics for clean restart
        self._message_count = 0
        self._time_cache = time.time()
        self._reconnect_attempts = 0
        await asyncio.sleep(1.0)
        await self.start()
    
    # Subscription management
    
    async def subscribe(
        self, 
        streams: List[str], 
        stream_params: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Subscribe to streams - optimized for memory efficiency.
        
        Args:
            streams: List of stream identifiers
            stream_params: Optional parameters for subscription
        """
        if not streams:
            return
        
        # Optimize memory - reuse empty dict singleton for None params
        params = stream_params or {}
        
        # Store subscription info - batch update for efficiency
        subscriptions = self._subscriptions
        for stream in streams:
            subscriptions[stream] = params
        
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
            self._metrics.messages_sent += 1
        except Exception as e:
            self._metrics.errors += 1
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
                self._metrics.connections += 1
                current_time = time.time()
                self._metrics.connection_uptime = current_time - connect_time
                self._time_cache = current_time
                
                # Process pending subscriptions
                await self._process_pending_subscriptions()
                
                # Start message reader with optimized task creation
                self._reader_task = asyncio.create_task(self._message_reader())
                
                if self.logger.isEnabledFor(logging.INFO):
                    self.logger.info("WebSocket connected to %s", self.exchange)
                
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
        metrics = self._metrics
        
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("Starting message reader loop")
        
        try:
            message = await self._ws.recv()
            print(message)
            async for raw_message in self._ws:
                try:
                    # DEBUG: Log raw message reception
                    if self.logger.isEnabledFor(logging.DEBUG):
                        msg_type = type(raw_message).__name__
                        msg_size = len(raw_message) if raw_message else 0
                        self.logger.debug(f"Received raw message: {msg_type}, size={msg_size}")
                    
                    # Parse message (exchange-specific) - minimize await overhead
                    parsed = await self._parse_message(raw_message)
                    if parsed is None:
                        if self.logger.isEnabledFor(logging.DEBUG):
                            self.logger.debug("Parsed message is None, skipping")
                        continue  # Skip heartbeat/ping messages
                    
                    # Optimized metrics update - batch time updates
                    metrics.messages_received += 1
                    self._message_count += 1
                    
                    # Update time cache every 100 messages instead of every message
                    if self._message_count % 100 == 0:
                        self._time_cache = time.time()
                        metrics.last_message_time = self._time_cache
                    
                    if self.logger.isEnabledFor(logging.DEBUG):
                        self.logger.debug(f"Calling message handler with parsed message: {parsed}")
                    
                    # Handle message - direct call to avoid lookup overhead
                    if message_handler:
                        await message_handler(parsed)
                    
                except Exception as e:
                    metrics.errors += 1
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
        self._metrics.errors += 1
        
        if self._reconnect_attempts >= self.config.max_reconnect_attempts:
            if self.logger.isEnabledFor(logging.ERROR):
                self.logger.error("Max reconnection attempts reached for %s", self.exchange)
            self._should_reconnect = False
            return
        
        # Use pre-computed backoff delay - no power calculation needed
        delay = self._cached_backoff_delays[self._reconnect_attempts]
        
        self._reconnect_attempts += 1
        self._metrics.reconnections += 1
        
        # Lazy logging with optimized formatting
        if self.logger.isEnabledFor(logging.WARNING):
            self.logger.warning(
                "Connection error for %s (attempt %d): %s. Reconnecting in %.1fs",
                self.exchange, self._reconnect_attempts, error, delay
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
    
    # Health check and monitoring
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on WebSocket connection - optimized"""
        current_time = time.time()
        last_msg_time = self._metrics.last_message_time
        
        return {
            'exchange': self.exchange,
            'state': self._state.value,
            'is_connected': self.is_connected,
            'subscriptions': len(self._subscriptions),
            'reconnect_attempts': self._reconnect_attempts,
            'metrics': self._metrics.to_dict(),
            'last_message_age': current_time - last_msg_time if last_msg_time else float('inf'),
            'message_rate': self._message_count / (current_time - self._metrics._start_time) if current_time > self._metrics._start_time else 0.0
        }


# High-performance utility functions for WebSocket operations

class WebSocketConnectionPool:
    """
    High-performance WebSocket connection pool for managing multiple exchanges.
    Optimized for cryptocurrency arbitrage trading with minimal overhead.
    """
    
    __slots__ = ('_connections', '_max_connections', '_loop')
    
    def __init__(self, max_connections: int = 50):
        self._connections: Dict[str, BaseWebSocketInterface] = {}
        self._max_connections = max_connections
        self._loop = None
    
    async def get_connection(
        self,
        exchange: ExchangeName,
        config: WebSocketConfig,
        connection_factory: Callable[[], BaseWebSocketInterface]
    ) -> BaseWebSocketInterface:
        """Get or create a WebSocket connection with connection reuse"""
        key = f"{exchange}_{config.url}"
        
        if key in self._connections:
            conn = self._connections[key]
            if conn.is_connected:
                return conn
        
        # Create new connection if pool has capacity
        if len(self._connections) >= self._max_connections:
            # Remove oldest disconnected connection
            for k, conn in list(self._connections.items()):
                if not conn.is_connected:
                    del self._connections[k]
                    break
        
        # Create and store new connection
        connection = connection_factory()
        self._connections[key] = connection
        await connection.start()
        
        return connection
    
    async def close_all(self):
        """Close all connections in the pool"""
        tasks = []
        for conn in self._connections.values():
            if conn.is_connected:
                tasks.append(conn.stop())
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self._connections.clear()

@asynccontextmanager
async def websocket_connection(
    exchange: ExchangeName,
    config: WebSocketConfig,
    message_handler: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    error_handler: Optional[Callable[[Exception], Awaitable[None]]] = None
):
    """
    Optimized context manager for WebSocket connections with automatic cleanup.
    
    Note: This requires a concrete implementation of BaseWebSocketInterface.
    """
    # This would need to be implemented by specific exchange classes
    raise NotImplementedError("Use exchange-specific WebSocket implementations")


def create_websocket_config(
    url: str,
    **overrides
) -> WebSocketConfig:
    """
    Create WebSocket configuration with high-frequency trading optimized defaults.
    
    Args:
        url: WebSocket URL
        **overrides: Configuration overrides
    """
    # Optimized defaults for cryptocurrency arbitrage trading
    defaults = {
        'timeout': 5.0,  # More aggressive for HFT
        'ping_interval': 15.0,  # Shorter intervals for faster disconnect detection
        'ping_timeout': 5.0,  # Quick timeout detection
        'close_timeout': 3.0,  # Faster cleanup
        'reconnect_delay': 0.5,  # Faster reconnection
        'max_reconnect_attempts': 15,  # More attempts for stability
        'reconnect_backoff': 1.5,  # Less aggressive backoff
        'max_reconnect_delay': 30.0,  # Lower max delay
        'max_message_size': 2 * 1024 * 1024,  # 2MB for larger market data
        'max_queue_size': 2000,  # Larger queue for high throughput
        'heartbeat_interval': 20.0,  # Faster heartbeat
        'enable_compression': True,  # Keep compression for bandwidth
    }
    
    defaults.update(overrides)
    return WebSocketConfig(url=url, **defaults)


# Performance monitoring and benchmarking utilities
def calculate_performance_metrics(connection: BaseWebSocketInterface) -> Dict[str, float]:
    """Calculate advanced performance metrics for a WebSocket connection"""
    metrics = connection.metrics
    uptime = metrics.get('connection_uptime', 0.0)
    
    if uptime <= 0:
        return {}
    
    messages_received = metrics.get('messages_received', 0)
    messages_sent = metrics.get('messages_sent', 0)
    errors = metrics.get('errors', 0)
    
    return {
        'message_throughput_per_second': messages_received / uptime,
        'error_rate_percentage': (errors / max(messages_received, 1)) * 100,
        'total_message_rate': (messages_received + messages_sent) / uptime,
        'connection_stability': max(0.0, 1.0 - (errors / max(messages_received, 1))),
        'average_latency_estimate': 1.0 / max(messages_received / max(uptime, 1), 1.0)  # Rough estimate
    }