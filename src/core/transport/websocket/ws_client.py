from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Awaitable
import asyncio
import time
import logging
from collections import deque
from websockets import connect #, State
import msgspec

from core.exceptions.exchange import BaseExchangeError
from core.transport.websocket.structs import ConnectionState
from core.config.structs import WebSocketConfig


class WebsocketClient:
    """
    Abstract cex class for high-performance WebSocket connections.
    
    This cex is completely data format agnostic and provides:
    - High-performance async WebSocket management
    - Automatic reconnection with exponential backoff
    - Subscription management
    - Error handling and recovery
    - Connection lifecycle management
    """

    __slots__ = (
        'config', '_message_handler', '_error_handler',
        '_state', '_ws', '_loop', '_connection_task', '_reader_task',
        '_reconnect_attempts', '_should_reconnect', '_last_pong', 
        'logger', 'url_name', '_cached_backoff_delays', '_message_count', 
        '_time_cache', '_connection_handler'
    )
    
    def __init__(
        self,
        config: WebSocketConfig,
        message_handler: Optional[Callable[[Any], Awaitable[None]]] = None,
        error_handler: Optional[Callable[[Exception], Awaitable[None]]] = None,
        connection_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None,
    ):
        self.config = config
        self._message_handler = message_handler
        self._error_handler = error_handler
        self._connection_handler = connection_handler

        # Connection state
        self._state = ConnectionState.DISCONNECTED
        self._ws = None
        self._loop = None
        self._connection_task = None
        self._reader_task = None
        
        # Reconnection control
        self._reconnect_attempts = 0
        self._should_reconnect = True
        self._last_pong = 0.0
        
        # Pre-computed backoff delays for performance (avoid power calculations)
        self._cached_backoff_delays = self._precompute_backoff_delays()
        
        # Performance optimizations
        self._message_count = 0  # Local counter to reduce time() calls
        self._time_cache = time.time()  # Cache time for batched updates
        
        # Extract name from URL for logging (fallback to class name)
        self.url_name = self.config.url.split('/')[-1] if self.config.url else "websocket"
        self.logger = logging.getLogger(f"{__name__}.{self.url_name}")
    
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
            raise BaseExchangeError(500, f"WebSocket connection failed: {str(e)}")


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
            self.logger.info("Started WebSocket connection for %s", self.url_name)
    
    async def stop(self) -> None:
        """Stop the WebSocket connection gracefully - optimized"""
        self._should_reconnect = False
        await self._update_state(self._state)
        
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
        
        await self._update_state(ConnectionState.CLOSED)

        if self.logger.isEnabledFor(logging.INFO):
            self.logger.info("Stopped WebSocket connection for %s", self.url_name)
    
    async def restart(self) -> None:
        """Restart the WebSocket connection - optimized restart sequence"""
        await self.stop()
        self._message_count = 0
        self._time_cache = time.time()
        self._reconnect_attempts = 0
        await asyncio.sleep(1.0)
        await self.start()
    

    async def send_message(self, message: Dict[str, Any]) -> None:
        """
        Send a message through the WebSocket.
        Message will be serialized appropriately for the connection.
        """
        if not self.is_connected:
            raise BaseExchangeError(500, "WebSocket not connected")
        
        try:
            # Optimized serialization - avoid decode step for bytes
            msg_str = msgspec.json.encode(message).decode("utf-8")
            await self._ws.send(msg_str)
        except Exception as e:
            raise BaseExchangeError(500, f"Failed to send message: {str(e)}")
    
    # Internal connection management
    
    async def _connection_loop(self) -> None:
        """Main connection loop with automatic reconnection - optimized"""
        connect_time = time.time()
        
        while self._should_reconnect:
            try:
                await self._update_state(ConnectionState.CONNECTING)
                await self._connect()
                
                if self._ws is None:
                    raise BaseExchangeError(500, "Connection failed - no WebSocket created")

                await self._update_state(ConnectionState.CONNECTED)

                self._reconnect_attempts = 0
                current_time = time.time()
                self._time_cache = current_time
                
                # Start message reader with optimized task creation
                self._reader_task = asyncio.create_task(self._message_reader())
                
                if self.logger.isEnabledFor(logging.INFO):
                    self.logger.info("WebSocket connected to %s", self.url_name)
                
                # Wait for connection to close
                await self._reader_task
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                await self._handle_connection_error(e)

        await self._update_state(ConnectionState.DISCONNECTED)

    async def _update_state(self, state: ConnectionState) -> None:
        self._state = state
        if self._connection_handler:
            await self._connection_handler(self._state)
    
    async def _message_reader(self) -> None:
        """Read and process messages from WebSocket - optimized for high throughput"""
        # Performance optimizations: cache frequently accessed values
        message_handler = self._message_handler
        error_handler = self._error_handler
        
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("Starting message reader loop")
        
        try:
            while self.is_connected:
                # This is the correct pattern from the working implementation
                try:
                    raw_message = await self._ws.recv()
                    
                    # Debug: Log message reception
                    if self.logger.isEnabledFor(logging.DEBUG):
                        message_preview = str(raw_message)[:100] + "..." if len(str(raw_message)) > 100 else str(raw_message)
                        self.logger.debug(f"Received WebSocket message: {message_preview}")

                    # Handle message - direct call to avoid lookup overhead
                    if message_handler:
                        await message_handler(raw_message)
                    else:
                        self.logger.warning("No message handler configured - message dropped")
                    
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
    
    async def _handle_connection_error(self, error: Exception) -> None:
        """Handle connection errors with pre-computed exponential backoff"""
        await self._update_state(ConnectionState.ERROR)

        if self._reconnect_attempts >= self.config.max_reconnect_attempts:
            if self.logger.isEnabledFor(logging.ERROR):
                self.logger.error("Max reconnection attempts reached for %s", self.url_name)
            self._should_reconnect = False
            return
        
        # Use pre-computed backoff delay - no power calculation needed
        delay = self._cached_backoff_delays[self._reconnect_attempts]
        
        self._reconnect_attempts += 1

        # Lazy logging with optimized formatting
        if self.logger.isEnabledFor(logging.WARNING):
            self.logger.warning(
                "Connection error for %s (attempt %d): %s. Reconnecting in %.1fs",
                self.url_name, self._reconnect_attempts, error, delay
            )
        
        await self._update_state(ConnectionState.RECONNECTING)
        await asyncio.sleep(delay)
    
    # Context manager support
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""

        await self.stop()



