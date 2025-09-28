"""
BaseWebSocketInterface - Core WebSocket Infrastructure

Core WebSocket business logic extracted from WebSocketManager to enable clean
mixin-based architecture. Provides connection lifecycle management, message
processing pipeline, and performance monitoring while delegating exchange-specific
behavior to handler mixins.

Key Features:
- Core WebSocket connection state management
- Message queuing and processing pipeline
- Connection lifecycle (connect, disconnect, reconnect)
- Performance metrics and health monitoring
- Task management (connection, reader, processing, heartbeat tasks)
- Delegation to handler mixins for exchange-specific behavior

HFT COMPLIANCE: Sub-millisecond message processing, <100ms reconnection.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Callable, Any, Awaitable, Set
from websockets.client import WebSocketClientProtocol
from websockets.protocol import State as WsState

from .structs import WebSocketManagerConfig, PerformanceMetrics, ConnectionState, SubscriptionAction, PublicWebsocketChannelType
from config.structs import WebSocketConfig
from infrastructure.exceptions.exchange import ExchangeRestError
import msgspec

# HFT Logger Integration
from infrastructure.logging import get_logger, LoggingTimer


class BaseWebSocketInterface(ABC):
    """
    Core WebSocket infrastructure interface with mixin delegation.
    
    Extracted from WebSocketManager to provide clean separation between
    infrastructure concerns and exchange-specific business logic. Manages
    WebSocket connection state and delegates exchange-specific behavior to
    handler mixins.
    
    Key features:
    - Connection lifecycle management with delegated policies
    - Message processing pipeline with handler delegation
    - Performance monitoring with HFT compliance
    - Task management for connection, reading, processing, heartbeat
    - Error handling with exchange-specific classification
    """
    
    def __init__(
        self,
        config: WebSocketConfig,
        connection_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None,
        manager_config: Optional[WebSocketManagerConfig] = None,
        logger=None
    ):
        self.config = config
        self.connection_handler = connection_handler
        self.manager_config = manager_config or WebSocketManagerConfig()
        
        # Initialize HFT logger with optional injection
        self.logger = logger or get_logger('ws.base_interface')
        
        # Core WebSocket connection management
        self._websocket: Optional[WebSocketClientProtocol] = None
        self.connection_state = ConnectionState.DISCONNECTED
        
        # Task management
        self._connection_task: Optional[asyncio.Task] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._processing_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        
        # Control flags
        self._should_reconnect = True
        
        # Delayed import to avoid circular dependency
        try:
            from exchanges.structs.common import Symbol
            self._active_symbols: Set["Symbol"] = set()
        except ImportError as e:
            self.logger.error("Failed to import Symbol type", error=str(e))
            self._active_symbols: Set[Any] = set()  # Fallback to Any type
        
        self._ws_channels: List[PublicWebsocketChannelType] = []
        
        # Performance tracking
        self.metrics = PerformanceMetrics()
        self.start_time = 0.0
        
        # Message processing
        self._message_queue: asyncio.Queue = asyncio.Queue(
            maxsize=self.manager_config.max_pending_messages
        )
        
        self.logger.info("BaseWebSocketInterface initialized",
                        websocket_url=config.url,
                        max_pending=self.manager_config.max_pending_messages)
    
    # Abstract methods that handlers must implement
    
    @abstractmethod
    async def _handle_message(self, raw_message: Any) -> None:
        """
        Process raw WebSocket message.
        
        Handler must implement exchange-specific message processing.
        This is the core message processing entry point that replaces
        the strategy pattern with direct delegation.
        
        Args:
            raw_message: Raw message from WebSocket (bytes, str, or dict)
        """
        pass
    
    @abstractmethod
    async def connect(self) -> WebSocketClientProtocol:
        """
        Establish WebSocket connection using handler's connection configuration.
        
        Handler must implement exchange-specific connection logic using
        ConnectionMixin.
        
        Returns:
            WebSocketClientProtocol instance
        """
        pass
    
    @abstractmethod
    async def authenticate(self) -> bool:
        """
        Perform authentication if required by the exchange.
        
        Handler must implement exchange-specific authentication using
        AuthMixin or return True for no authentication required.
        
        Returns:
            True if authentication successful or not required
        """
        pass
    
    @abstractmethod
    def get_reconnection_policy(self):
        """
        Get exchange-specific reconnection policy.
        
        Handler must provide reconnection configuration for the exchange.
        
        Returns:
            ReconnectionPolicy with exchange-optimized settings
        """
        pass
    
    @abstractmethod
    def should_reconnect(self, error: Exception) -> bool:
        """
        Determine if reconnection should be attempted based on error.
        
        Handler must implement exchange-specific error classification.
        
        Args:
            error: Exception that caused disconnection
            
        Returns:
            True if reconnection should be attempted
        """
        pass
    
    @abstractmethod
    def classify_error(self, error: Exception) -> str:
        """
        Classify error for logging and metrics purposes.
        
        Handler must implement exchange-specific error classification.
        
        Args:
            error: Exception to classify
            
        Returns:
            String classification of error type
        """
        pass
    
    @abstractmethod
    async def subscribe_to_symbols(self, symbols: List["Symbol"], channel_types: List[PublicWebsocketChannelType]) -> List[Dict[str, Any]]:
        """
        Create subscription messages for symbols.
        
        Handler must implement exchange-specific subscription message creation.
        
        Args:
            symbols: List of symbols to subscribe to
            channel_types: List of channel types to subscribe to
            
        Returns:
            List of subscription messages to send
        """
        pass
    
    @abstractmethod
    async def unsubscribe_from_symbols(self, symbols: List["Symbol"]) -> List[Dict[str, Any]]:
        """
        Create unsubscription messages for symbols.
        
        Handler must implement exchange-specific unsubscription message creation.
        
        Args:
            symbols: List of symbols to unsubscribe from
            
        Returns:
            List of unsubscription messages to send
        """
        pass
    
    @abstractmethod
    async def get_resubscription_messages(self) -> List[Dict[str, Any]]:
        """
        Get resubscription messages for active symbols.
        
        Handler must implement exchange-specific resubscription message creation.
        
        Returns:
            List of resubscription messages for current active symbols
        """
        pass
    
    @abstractmethod
    async def handle_heartbeat(self) -> None:
        """
        Handle exchange-specific heartbeat/ping operations.
        
        Handler must implement exchange-specific heartbeat logic or
        do nothing if built-in ping/pong is sufficient.
        """
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """
        Clean up handler-specific resources.
        
        Handler must implement any cleanup required when closing.
        """
        pass
    
    # Core infrastructure methods
    
    async def initialize(self, symbols: Optional[List["Symbol"]] = None,
                        default_channels: Optional[List[PublicWebsocketChannelType]] = None) -> None:
        """
        Initialize WebSocket connection using handler delegation.
        
        Args:
            symbols: Optional list of Symbol instances for initial subscription
            default_channels: Optional list of channels for initial subscription
        """
        try:
            from exchanges.structs.common import Symbol
        except ImportError as e:
            self.logger.error("Failed to import Symbol type in initialize", error=str(e))
        
        self.start_time = time.perf_counter()
        
        if symbols:
            self._active_symbols.update(symbols)
        
        if default_channels:
            self._ws_channels = default_channels
        
        try:
            with LoggingTimer(self.logger, "ws_interface_initialization") as timer:
                self.logger.info("Initializing BaseWebSocketInterface",
                               symbols_count=len(symbols) if symbols else 0,
                               channels_count=len(default_channels) if default_channels else 0)
                
                # Start connection loop (handles reconnection with handler policies)
                self._should_reconnect = True
                self._connection_task = asyncio.create_task(self._connection_loop())
                
                # Start message processing
                self._processing_task = asyncio.create_task(self._process_messages())
                
                # Start handler-managed heartbeat if needed
                if self.config.heartbeat_interval and self.config.heartbeat_interval > 0:
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                    self.logger.info("Started custom heartbeat",
                                   heartbeat_interval=self.config.heartbeat_interval)
            
            self.logger.info("BaseWebSocketInterface initialized successfully",
                           initialization_time_ms=timer.elapsed_ms)
            
            # Track initialization metrics
            self.logger.metric("ws_interface_initializations", 1,
                             tags={"exchange": "ws"})
            self.logger.metric("ws_interface_initialization_time_ms", timer.elapsed_ms,
                             tags={"exchange": "ws"})
            
        except Exception as e:
            self.logger.error("Failed to initialize BaseWebSocketInterface",
                            error_type=type(e).__name__,
                            error_message=str(e))
            
            # Track initialization failure metrics
            self.logger.metric("ws_interface_initialization_failures", 1,
                             tags={"exchange": "ws"})
            
            await self.close()
            raise ExchangeRestError(500, f"WebSocket interface initialization failed: {e}")
    
    async def subscribe(self, symbols: List["Symbol"]) -> None:
        """Subscribe to symbols using handler delegation."""
        try:
            from exchanges.structs.common import Symbol
        except ImportError as e:
            self.logger.error("Failed to import Symbol type in subscribe", error=str(e))
        
        if not self.is_connected():
            raise ExchangeRestError(503, "WebSocket not connected")
        
        try:
            with LoggingTimer(self.logger, "subscription_processing") as timer:
                messages = await self.subscribe_to_symbols(
                    symbols=symbols, channel_types=self._ws_channels)
                
                if not messages:
                    self.logger.warning("No subscription messages created",
                                      symbols_count=len(symbols),
                                      channels_count=len(self._ws_channels))
                    return
                
                self.logger.info("Sending subscription messages",
                               messages_count=len(messages),
                               symbols_count=len(symbols))
                
                for message in messages:
                    await self.send_message(message)
                    self.logger.debug("Sent subscription message", subscription_data=message)
                
                self._active_symbols.update(symbols)
            
            # Track subscription metrics
            self.logger.metric("ws_interface_subscriptions", len(symbols),
                             tags={"exchange": "ws"})
            self.logger.metric("ws_interface_subscription_time_ms", timer.elapsed_ms,
                             tags={"exchange": "ws"})
            
        except Exception as e:
            self.logger.error("Subscription failed",
                            symbols_count=len(symbols),
                            error_type=type(e).__name__,
                            error_message=str(e))
            
            # Track subscription failure metrics
            self.logger.metric("ws_interface_subscription_failures", 1,
                             tags={"exchange": "ws"})
            
            raise ExchangeRestError(400, f"Subscription failed: {e}")
    
    async def unsubscribe(self, symbols: List["Symbol"]) -> None:
        """Unsubscribe from symbols using handler delegation."""
        if not self.is_connected():
            return
        
        try:
            messages = await self.unsubscribe_from_symbols(symbols)
            
            if not messages:
                return
            
            for message in messages:
                await self.send_message(message)
            
            self._active_symbols.difference_update(symbols)
            
        except Exception as e:
            self.logger.error(f"Unsubscription failed: {e}")
    
    async def send_message(self, message: Dict[str, Any]) -> None:
        """Send message through WebSocket connection."""
        if not self._websocket or self.connection_state != ConnectionState.CONNECTED:
            raise ExchangeRestError(503, "WebSocket not connected")
        
        try:
            msg_str = msgspec.json.encode(message).decode("utf-8")
            await self._websocket.send(msg_str)
            
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            raise ExchangeRestError(400, f"Message send failed: {e}")
    
    async def _connection_loop(self) -> None:
        """
        Main connection loop with handler-based reconnection.
        
        Uses handler delegation for connection establishment and reconnection
        policies. Implements the connection lifecycle management.
        """
        reconnection_policy = self.get_reconnection_policy()
        reconnect_attempts = 0
        
        while self._should_reconnect:
            try:
                await self._update_state(ConnectionState.CONNECTING)
                
                # Use handler delegation to establish connection
                self._websocket = await self.connect()
                
                if not self._websocket:
                    raise ExchangeRestError(500, "Handler returned no WebSocket connection")
                
                await self._update_state(ConnectionState.CONNECTED)
                
                # Reset reconnection attempts on successful connection
                reconnect_attempts = 0
                
                # Authenticate using handler delegation
                auth_success = await self.authenticate()
                if not auth_success:
                    self.logger.error("Authentication failed")
                    self.logger.metric("ws_interface_auth_failures", 1,
                                     tags={"exchange": "ws"})
                    await self._websocket.close()
                    continue
                
                # Track successful connection
                self.logger.metric("ws_interface_connections", 1,
                                 tags={"exchange": "ws"})
                
                # Resubscribe to active symbols using handler delegation
                if self._active_symbols:
                    resubscription_messages = await self.get_resubscription_messages()
                    for message in resubscription_messages:
                        await self.send_message(message)
                    self.logger.info(f"Resubscribed to {len(self._active_symbols)} symbols")
                
                # Start message reader
                self._reader_task = asyncio.create_task(self._message_reader())
                
                self.logger.info("WebSocket connection established successfully",
                               active_symbols_count=len(self._active_symbols))
                
                # Wait for connection to close
                await self._reader_task
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                await self._handle_connection_error(e, reconnection_policy, reconnect_attempts)
                reconnect_attempts += 1
        
        await self._update_state(ConnectionState.DISCONNECTED)
    
    async def _message_reader(self) -> None:
        """
        Read messages from WebSocket and queue for processing.
        
        Direct WebSocket message reading with high-performance queuing.
        """
        try:
            while True:
                if not self.is_connected():
                    self.logger.debug("WebSocket disconnected, exiting message reader")
                    break
                try:
                    raw_message = await self._websocket.recv()
                    await self._on_raw_message(raw_message)
                except Exception as e:
                    await self._on_error(e)
                    break
        except asyncio.CancelledError:
            self.logger.debug("Message reader cancelled")
        except Exception as e:
            self.logger.error(f"Message reader error: {e}")
            await self._on_error(e)
    
    async def _handle_connection_error(self, error: Exception, policy, attempt: int) -> None:
        """Handle connection errors using handler-specific policies."""
        await self._update_state(ConnectionState.ERROR)
        
        # Let handler decide if we should reconnect
        if not self.should_reconnect(error):
            error_type = self.classify_error(error)
            self.logger.error(f"Handler decided not to reconnect after {error_type} error: {error}")
            self._should_reconnect = False
            return
        
        # Check max attempts
        if attempt >= policy.max_attempts:
            self.logger.error(f"Max reconnection attempts ({policy.max_attempts}) reached")
            self._should_reconnect = False
            return
        
        # Calculate delay with handler policy
        error_type = self.classify_error(error)
        if policy.reset_on_1005 and error_type == "abnormal_closure":
            delay = policy.initial_delay  # Reset delay for 1005 errors
        else:
            delay = min(
                policy.initial_delay * (policy.backoff_factor ** attempt),
                policy.max_delay
            )
        
        self.logger.warning("Connection error, reconnecting",
                           error_type=error_type,
                           attempt=attempt + 1,
                           delay_seconds=delay,
                           error_message=str(error))
        
        # Track reconnection metrics
        self.logger.metric("ws_interface_reconnection_attempts", 1,
                         tags={"exchange": "ws", "error_type": error_type})
        
        await self._update_state(ConnectionState.RECONNECTING)
        await asyncio.sleep(delay)
    
    async def _update_state(self, state: ConnectionState) -> None:
        """Update connection state and notify handlers."""
        previous_state = self.connection_state
        self.connection_state = state
        
        if previous_state != state:
            self.logger.info("Connection state changed",
                           previous_state=previous_state.name,
                           new_state=state.name)
            
            # Track state change metrics
            self.logger.metric("ws_interface_state_changes", 1,
                             tags={"exchange": "ws",
                                   "from_state": previous_state.name,
                                   "to_state": state.name})
            
            # Notify external handler
            if self.connection_handler:
                try:
                    await self.connection_handler(state)
                except Exception as e:
                    self.logger.error("Error in state change handler",
                                    error_type=type(e).__name__,
                                    error_message=str(e))
    
    async def _on_raw_message(self, raw_message: Any) -> None:
        """Queue raw message for processing."""
        start_time = time.perf_counter()
        try:
            if self._message_queue.full():
                self.logger.warning("Message queue full, dropping oldest",
                                  queue_size=self._message_queue.qsize(),
                                  max_size=self.manager_config.max_pending_messages)
                
                # Track queue overflow metrics
                self.logger.metric("ws_interface_queue_overflows", 1,
                                 tags={"exchange": "ws"})
                
                try:
                    self._message_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            
            await self._message_queue.put((raw_message, start_time))
            
            # Track message queuing metrics
            self.logger.metric("ws_interface_messages_queued", 1,
                             tags={"exchange": "ws"})
            
        except Exception as e:
            self.metrics.error_count += 1
            self.logger.error("Error queuing message",
                            error_type=type(e).__name__,
                            error_message=str(e))
            
            # Track queuing error metrics
            self.logger.metric("ws_interface_queuing_errors", 1,
                             tags={"exchange": "ws"})
    
    async def _process_messages(self) -> None:
        """Process queued messages using handler delegation."""
        while True:
            try:
                raw_message, queue_time = await self._message_queue.get()
                processing_start = time.perf_counter()
                
                try:
                    # Direct handler delegation for message processing
                    await self._handle_message(raw_message)
                    
                    processing_time_ms = (time.perf_counter() - processing_start) * 1000
                    self.metrics.update_processing_time(processing_time_ms)
                    self.metrics.messages_processed += 1
                    
                    # Track message processing metrics
                    self.logger.metric("ws_interface_messages_processed", 1,
                                     tags={"exchange": "ws"})
                    self.logger.metric("ws_interface_message_processing_time_ms", processing_time_ms,
                                     tags={"exchange": "ws"})
                
                except Exception as e:
                    await self._handle_processing_error(e, raw_message)
                
                finally:
                    self._message_queue.task_done()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Error in message processing loop",
                                error_type=type(e).__name__,
                                error_message=str(e))
                
                # Track processing loop error metrics
                self.logger.metric("ws_interface_processing_loop_errors", 1,
                                 tags={"exchange": "ws"})
    
    async def _handle_processing_error(self, error: Exception, raw_message: Any) -> None:
        """Handle errors during message processing."""
        self.metrics.error_count += 1
        
        self.logger.error("Error processing message",
                        error_type=type(error).__name__,
                        error_message=str(error))
        
        # Track message processing error metrics
        self.logger.metric("ws_interface_message_processing_errors", 1,
                         tags={"exchange": "ws"})
    
    async def _on_error(self, error: Exception) -> None:
        """Handle WebSocket errors using handler classification."""
        self.metrics.error_count += 1
        
        error_type = self.classify_error(error)
        
        if error_type == "abnormal_closure":
            self.logger.warning("WebSocket error",
                              error_type=error_type,
                              error_message=str(error))
        else:
            self.logger.error("WebSocket error",
                            error_type=error_type,
                            error_message=str(error))
        
        # Track WebSocket error metrics
        self.logger.metric("ws_interface_errors", 1,
                         tags={"exchange": "ws", "error_type": error_type})
    
    async def _heartbeat_loop(self) -> None:
        """Handler-managed heartbeat loop."""
        consecutive_failures = 0
        max_failures = 3
        
        try:
            while True:
                await asyncio.sleep(self.config.heartbeat_interval)
                
                # Use handler delegation for heartbeat
                if self.config.has_heartbeat and self.is_connected():
                    try:
                        await self.handle_heartbeat()
                        consecutive_failures = 0  # Reset on success
                        self.logger.debug("Handler heartbeat sent successfully")
                        
                        # Track successful heartbeat
                        self.logger.metric("ws_interface_heartbeats_sent", 1,
                                         tags={"exchange": "ws"})
                        
                    except Exception as e:
                        consecutive_failures += 1
                        self.logger.warning("Handler heartbeat failed",
                                          consecutive_failures=consecutive_failures,
                                          max_failures=max_failures,
                                          error_message=str(e))
                        
                        # Track heartbeat failures
                        self.logger.metric("ws_interface_heartbeat_failures", 1,
                                         tags={"exchange": "ws"})
                        
                        if consecutive_failures >= max_failures:
                            self.logger.error("Too many consecutive heartbeat failures",
                                            max_failures=max_failures)
                            
                            # Track heartbeat loop failure
                            self.logger.metric("ws_interface_heartbeat_loop_failures", 1,
                                             tags={"exchange": "ws"})
                            break
                        
        except asyncio.CancelledError:
            self.logger.debug("Heartbeat loop cancelled")
        except Exception as e:
            self.logger.error("Heartbeat loop error",
                            error_type=type(e).__name__,
                            error_message=str(e))
            
            # Track heartbeat loop error metrics
            self.logger.metric("ws_interface_heartbeat_loop_errors", 1,
                             tags={"exchange": "ws"})
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        if self.connection_state != ConnectionState.CONNECTED or self._websocket is None:
            return False
        try:
            return self._websocket.state == WsState.OPEN
        except AttributeError:
            self.logger.error("WebSocket object has no 'state' attribute",
                            websocket_type=type(self._websocket).__name__)
            return False
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for WebSocket interface."""
        uptime = time.perf_counter() - self.start_time if self.start_time > 0 else 0
        
        return {
            'messages_processed': self.metrics.messages_processed,
            'messages_per_second': self.metrics.messages_processed / uptime if uptime > 0 else 0,
            'avg_processing_time_ms': self.metrics.avg_processing_time_ms,
            'max_processing_time_ms': self.metrics.max_processing_time_ms,
            'connection_uptime_seconds': uptime,
            'reconnection_count': self.metrics.reconnection_count,
            'error_count': self.metrics.error_count,
            'connection_state': self.connection_state.name,
            'interface_type': 'BaseWebSocketInterface'
        }
    
    async def close(self) -> None:
        """Close WebSocket interface and cleanup resources."""
        self.logger.info("Closing BaseWebSocketInterface...",
                        active_symbols_count=len(self._active_symbols))
        
        try:
            with LoggingTimer(self.logger, "ws_interface_close") as timer:
                self._should_reconnect = False
                
                # Cancel all tasks
                tasks = [
                    self._processing_task,
                    self._heartbeat_task,
                    self._connection_task,
                    self._reader_task
                ]
                
                for task in tasks:
                    if task and not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                
                # Close WebSocket connection
                if self._websocket:
                    try:
                        await self._websocket.close()
                    except Exception as e:
                        self.logger.error("Error closing WebSocket",
                                        error_type=type(e).__name__,
                                        error_message=str(e))
                    self._websocket = None
                
                # Handler cleanup
                await self.cleanup()
                
                self.connection_state = ConnectionState.DISCONNECTED
            
            self.logger.info("BaseWebSocketInterface closed",
                           close_time_ms=timer.elapsed_ms)
            
            # Track close metrics
            self.logger.metric("ws_interface_closes", 1,
                             tags={"exchange": "ws"})
            self.logger.metric("ws_interface_close_time_ms", timer.elapsed_ms,
                             tags={"exchange": "ws"})
            
        except Exception as e:
            self.logger.error("Error closing BaseWebSocketInterface",
                            error_type=type(e).__name__,
                            error_message=str(e))
            
            # Track close error metrics
            self.logger.metric("ws_interface_close_errors", 1,
                             tags={"exchange": "ws"})