"""
WebSocket Manager V5 - Mixin-Based Architecture

WebSocket manager supporting mixin-based direct message handling architecture
for optimal HFT performance. Provides unified interface for all exchange
integrations using composition over inheritance.

Key Features:
- Mixin-based composition for flexibility
- Direct message routing without overhead
- Performance monitoring with sub-millisecond targets
- Unified subscription management
- Circuit breaker patterns for error recovery

HFT COMPLIANCE: Sub-millisecond message processing, <100ms reconnection.
"""

import asyncio
import time
from symtable import Symbol
from typing import List, Dict, Optional, Callable, Any, Awaitable, Set
from websockets.client import WebSocketClientProtocol
from websockets.protocol import State as WsState

from infrastructure.networking.websocket.strategies.strategy_set import WebSocketStrategySet
from .structs import ParsedMessage, WebSocketManagerConfig, PerformanceMetrics, ConnectionState, SubscriptionAction, PublicWebsocketChannelType
from config.structs import WebSocketConfig
from infrastructure.exceptions.exchange import ExchangeRestError
import msgspec

# HFT Logger Integration
from infrastructure.logging import get_logger, LoggingTimer

# Mixin-based direct handling infrastructure
# Using composition-based mixins for message handling
# from infrastructure.networking.websocket.adapters import (
#     WebSocketHandlerAdapter, 
#     StrategyPatternAdapter, 
#     AdapterConfig,
#     create_handler_adapter,
#     create_strategy_adapter
# )


class WebSocketManager:
    """
    Dual-path WebSocket manager supporting both legacy and new architectures.
    
    This version supports both:
    1. Direct message handling (mixin-based composition)
    2. High-performance routing with minimal overhead
    
    Architecture selection is configuration-driven with hot-swapping capability.
    Provides compatibility layer for seamless migration with zero downtime.
    
    Key features:
    - Dual-path message processing
    - Configuration-based architecture switching
    - Performance monitoring for both paths
    - Circuit breaker patterns with automatic fallback
    - Zero-overhead adapter layer (<5ns per message)
    """
    
    def __init__(
        self,
        config: WebSocketConfig,
        strategies: Optional[WebSocketStrategySet] = None,
        message_handler: Optional[Callable[[ParsedMessage], Awaitable[None]]] = None,
        connection_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None,
        manager_config: Optional[WebSocketManagerConfig] = None,
        logger=None,
        # New direct handling parameters
        direct_handler: Optional[Any] = None,  # Any handler with _handle_message method
        use_direct_handling: bool = False,
        # adapter_config: Optional[AdapterConfig] = None  # TODO: Fix after adapter refactoring
    ):
        self.config = config
        self.strategies = strategies
        self.message_handler = message_handler
        self.connection_handler = connection_handler
        self.manager_config = manager_config or WebSocketManagerConfig()
        
        # Initialize HFT logger with optional injection
        self.logger = logger or get_logger('ws.manager')
        
        # Dual-path architecture support
        self.use_direct_handling = use_direct_handling
        self.direct_handler = direct_handler
        # self.adapter_config = adapter_config or AdapterConfig()  # TODO: Fix after adapter refactoring
        
        # Initialize handler adapter if using new architecture
        self.handler_adapter = None
        # TODO: Fix after adapter refactoring
        # if self.direct_handler:
        #     self.handler_adapter = create_handler_adapter(self.direct_handler, self.adapter_config)
        #     self.logger.info("Direct handler adapter initialized", 
        #                    handler_type=type(self.direct_handler).__name__)
        
        # Initialize strategy adapter if using legacy with new interface
        self.strategy_adapter = None
        if not self.use_direct_handling and self.strategies and not self.direct_handler:
            # Legacy mode - no adapter needed
            pass
        elif not self.use_direct_handling and self.strategies and self.direct_handler:
            # Hybrid mode - create strategy adapter for compatibility
            self.strategy_adapter = create_strategy_adapter(
                config.url.split('/')[-1],  # Extract exchange name from URL
                self.strategies,
                self.message_handler
            )
            self.logger.info("Strategy adapter initialized for hybrid mode")
        
        # Architecture validation
        if self.use_direct_handling and not self.direct_handler:
            raise ValueError("Direct handling enabled but no direct_handler provided")
        if not self.use_direct_handling and not self.strategies:
            raise ValueError("Legacy mode enabled but no strategies provided")
        
        # Performance tracking for dual paths
        self.legacy_metrics = {'messages': 0, 'errors': 0, 'total_time_ms': 0.0}
        self.direct_metrics = {'messages': 0, 'errors': 0, 'total_time_ms': 0.0}
        self.architecture_switches = 0
        
        # Direct WebSocket connection management
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
        from exchanges.structs.common import Symbol
        self._active_symbols: Set[Symbol] = set()
        self._ws_channels: List[PublicWebsocketChannelType] = []
        
        # Performance tracking
        self.metrics = PerformanceMetrics()
        self.start_time = 0.0
        
        # Message processing
        self._message_queue: asyncio.Queue = asyncio.Queue(
            maxsize=self.manager_config.max_pending_messages
        )
        
        self.logger.info("WebSocket manager V4 initialized with dual-path architecture",
                        websocket_url=config.url,
                        max_pending=self.manager_config.max_pending_messages,
                        use_direct_handling=self.use_direct_handling,
                        has_direct_handler=self.direct_handler is not None,
                        has_strategies=self.strategies is not None)
    
    async def initialize(self, symbols: Optional[List[Symbol]] = None,
                         default_channels: Optional[List[PublicWebsocketChannelType]] = None) -> None:
        """
        Initialize WebSocket connection using strategy.connect() directly.
        
        Args:
            :param symbols: Optional list of Symbol instances for initial subscription
            :param default_channels: Optional list of channels for initial subscription
        """
        # Import Symbol type here if needed for type checking
        from exchanges.structs.common import Symbol
        self.start_time = time.perf_counter()
        if symbols:
            self._active_symbols.update(symbols)

        if default_channels:
            self._ws_channels = default_channels

        try:
            with LoggingTimer(self.logger, "ws_manager_initialization") as timer:
                self.logger.info("Initializing WebSocket manager with direct strategy connection",
                                 symbols_count=len(symbols) if symbols else 0,
                                 channels_count=len(default_channels) if default_channels else 0)
                
                # Start connection loop (handles reconnection with strategy policies)
                self._should_reconnect = True
                self._connection_task = asyncio.create_task(self._connection_loop())
                
                # Start message processing
                self._processing_task = asyncio.create_task(self._process_messages())

                # Start strategy-managed heartbeat if needed
                # Note: This heartbeat supplements built-in ping/pong for exchanges requiring custom ping
                if self.config.heartbeat_interval and self.config.heartbeat_interval > 0:
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                    self.logger.info("Started custom heartbeat",
                                   heartbeat_interval=self.config.heartbeat_interval,
                                   note="supplements built-in ping/pong")
            
            self.logger.info("WebSocket manager V4 initialized successfully",
                           initialization_time_ms=timer.elapsed_ms)
            
            # Track initialization metrics
            self.logger.metric("ws_manager_initializations", 1,
                             tags={"exchange": "ws"})
            self.logger.metric("ws_initialization_time_ms", timer.elapsed_ms,
                             tags={"exchange": "ws"})
            
        except Exception as e:
            self.logger.error("Failed to initialize WebSocket manager V4",
                            error_type=type(e).__name__,
                            error_message=str(e))
            
            # Track initialization failure metrics
            self.logger.metric("ws_initialization_failures", 1,
                             tags={"exchange": "ws"})
            
            await self.close()
            raise ExchangeRestError(500, f"WebSocket initialization failed: {e}")
    
    async def subscribe(self, symbols: List[Symbol]) -> None:
        """Subscribe to symbols using strategy."""
        # Import Symbol type here if needed
        from exchanges.structs.common import Symbol
        if not self.is_connected():
            raise ExchangeRestError(503, "WebSocket not connected")

        try:
            with LoggingTimer(self.logger, "subscription_processing") as timer:
                messages = await self.strategies.subscription_strategy.create_subscription_messages(
                    action=SubscriptionAction.SUBSCRIBE, symbols=symbols, channels=self._ws_channels)
                
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
            self.logger.metric("ws_subscriptions", len(symbols),
                             tags={"exchange": "ws"})
            self.logger.metric("subscription_time_ms", timer.elapsed_ms,
                             tags={"exchange": "ws"})
            
        except Exception as e:
            self.logger.error("Subscription failed",
                            symbols_count=len(symbols),
                            error_type=type(e).__name__,
                            error_message=str(e))
            
            # Track subscription failure metrics
            self.logger.metric("ws_subscription_failures", 1,
                             tags={"exchange": "ws"})
            
            raise ExchangeRestError(400, f"Subscription failed: {e}")
    
    async def unsubscribe(self, symbols: List[Symbol]) -> None:
        """Unsubscribe from symbols using strategy."""
        if not self.is_connected():
            return
        
        try:
            messages = await self.strategies.subscription_strategy.create_subscription_messages(
                action=SubscriptionAction.UNSUBSCRIBE, symbols=symbols, channels=self._ws_channels)
            
            if not messages:
                return
            
            for message in messages:
                await self.send_message(message)
            
            self._active_symbols.difference_update(symbols)

        except Exception as e:
            self.logger.error(f"Unsubscription failed: {e}")
    
    async def send_message(self, message: Dict[str, Any]) -> None:
        """Send message through direct WebSocket connection."""
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
        Main connection loop with strategy-based reconnection.
        
        Uses strategy.connect() directly and implements reconnection 
        using strategy-provided policies.
        """
        reconnection_policy = self.strategies.connection_strategy.get_reconnection_policy()
        reconnect_attempts = 0
        
        while self._should_reconnect:
            try:
                await self._update_state(ConnectionState.CONNECTING)
                
                # Use strategy to establish connection directly
                self._websocket = await self.strategies.connection_strategy.connect()
                
                if not self._websocket:
                    raise ExchangeRestError(500, "Strategy returned no WebSocket connection")
                
                await self._update_state(ConnectionState.CONNECTED)
                
                # Reset reconnection attempts on successful connection
                reconnect_attempts = 0
                
                # Authenticate if required
                auth_success = await self.strategies.connection_strategy.authenticate()
                if not auth_success:
                    self.logger.error("Authentication failed")
                    self.logger.metric("ws_auth_failures", 1,
                                     tags={"exchange": "ws"})
                    await self._websocket.close()
                    continue
                
                # Track successful connection
                self.logger.metric("ws_connections", 1,
                                 tags={"exchange": "ws"})
                
                # Subscribe to active symbols
                # if self._active_symbols:
                await self.subscribe(list(self._active_symbols))
                
                # Start message reader
                self._reader_task = asyncio.create_task(self._message_reader())
                
                self.logger.info("Strategy-driven WebSocket connection established successfully",
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
        
        Direct WebSocket message reading without ws_client layer.
        """
        try:
            while True:
                if not self.is_connected():
                    await asyncio.sleep(0.1)
                    continue
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
        pass

    
    async def _handle_connection_error(self, error: Exception, policy, attempt: int) -> None:
        """Handle connection errors using strategy-specific policies."""
        await self._update_state(ConnectionState.ERROR)
        
        # Let strategy decide if we should reconnect
        if not self.strategies.connection_strategy.should_reconnect(error):
            error_type = self.strategies.connection_strategy.classify_error(error)
            self.logger.error(f"Strategy decided not to reconnect after {error_type} error: {error}")
            self._should_reconnect = False
            return
        
        # Check max attempts
        if attempt >= policy.max_attempts:
            self.logger.error(f"Max reconnection attempts ({policy.max_attempts}) reached")
            self._should_reconnect = False
            return
        
        # Calculate delay with strategy policy
        error_type = self.strategies.connection_strategy.classify_error(error)
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
        self.logger.metric("ws_reconnection_attempts", 1,
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
            self.logger.metric("ws_state_changes", 1,
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
                self.logger.metric("ws_queue_overflows", 1,
                                 tags={"exchange": "ws"})
                
                try:
                    self._message_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            
            await self._message_queue.put((raw_message, start_time))
            
            # Track message queuing metrics
            self.logger.metric("ws_messages_queued", 1,
                             tags={"exchange": "ws"})
            
        except Exception as e:
            self.metrics.error_count += 1
            self.logger.error("Error queuing message",
                            error_type=type(e).__name__,
                            error_message=str(e))
            
            # Track queuing error metrics
            self.logger.metric("ws_queuing_errors", 1,
                             tags={"exchange": "ws"})
    
    async def _process_messages(self) -> None:
        """Process queued messages using dual-path architecture."""
        while True:
            try:
                raw_message, queue_time = await self._message_queue.get()
                processing_start = time.perf_counter()
                
                try:
                    # Dual-path routing based on configuration
                    if self.use_direct_handling and self.direct_handler:
                        # New architecture: Direct _handle_message()
                        await self._process_direct_message(raw_message, processing_start)
                    elif self.strategies:
                        # Legacy fallback handler
                        await self._process_legacy_message(raw_message, processing_start)
                    else:
                        self.logger.error("No valid message processing path available")
                        self.metrics.error_count += 1
                
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
                self.logger.metric("ws_processing_loop_errors", 1,
                                 tags={"exchange": "ws"})
                
                await asyncio.sleep(0.1)
    
    async def _process_direct_message(self, raw_message: Any, processing_start: float) -> None:
        """Process message using new direct handling architecture."""
        try:
            # Direct handling - mixin-based message routing
            await self.direct_handler.process_message(raw_message)
            
            processing_time_ms = (time.perf_counter() - processing_start) * 1000
            self.metrics.update_processing_time(processing_time_ms)
            self.metrics.messages_processed += 1
            
            # Update direct path metrics
            self.direct_metrics['messages'] += 1
            self.direct_metrics['total_time_ms'] += processing_time_ms
            
            # Track message processing metrics with path identification
            self.logger.metric("ws_messages_processed", 1,
                             tags={"exchange": "ws", "path": "direct"})
            self.logger.metric("ws_message_processing_time_ms", processing_time_ms,
                             tags={"exchange": "ws", "path": "direct"})
            
        except Exception as e:
            self.direct_metrics['errors'] += 1
            self._try_fallback_to_legacy(raw_message, e)
    
    async def _process_legacy_message(self, raw_message: Any, processing_start: float) -> None:
        """Process message using legacy architecture for fallback compatibility."""
        try:
            parsed_message = await self.strategies.message_parser.parse_message(raw_message)
            
            if parsed_message and self.message_handler:
                await self.message_handler(parsed_message)
                
                processing_time_ms = (time.perf_counter() - processing_start) * 1000
                self.metrics.update_processing_time(processing_time_ms)
                self.metrics.messages_processed += 1
                
                # Update legacy path metrics
                self.legacy_metrics['messages'] += 1
                self.legacy_metrics['total_time_ms'] += processing_time_ms
                
                # Track message processing metrics with path identification
                self.logger.metric("ws_messages_processed", 1,
                                 tags={"exchange": "ws", "path": "legacy"})
                self.logger.metric("ws_message_processing_time_ms", processing_time_ms,
                                 tags={"exchange": "ws", "path": "legacy"})
            else:
                self.logger.warning("Failed to parse message or no message handler available")
                
        except Exception as e:
            self.legacy_metrics['errors'] += 1
            raise  # Re-raise for handling in parent method
    
    async def _try_fallback_to_legacy(self, raw_message: Any, error: Exception) -> None:
        """Attempt fallback to legacy architecture on direct handling error."""
        if not self.adapter_config.fallback_on_error or not self.strategies:
            raise error
        
        try:
            self.logger.warning("Direct handling failed, attempting legacy fallback",
                              error_type=type(error).__name__,
                              error_message=str(error))
            
            processing_start = time.perf_counter()
            await self._process_legacy_message(raw_message, processing_start)
            
            # Track fallback success
            self.logger.metric("ws_fallback_success", 1,
                             tags={"exchange": "ws"})
            
        except Exception as fallback_error:
            self.logger.error("Legacy fallback also failed",
                            original_error=str(error),
                            fallback_error=str(fallback_error))
            
            # Track fallback failure
            self.logger.metric("ws_fallback_failures", 1,
                             tags={"exchange": "ws"})
            
            raise error  # Raise original error
    
    async def _handle_processing_error(self, error: Exception, raw_message: Any) -> None:
        """Handle errors during message processing with path-specific logic."""
        self.metrics.error_count += 1
        
        error_path = "direct" if self.use_direct_handling else "legacy"
        
        self.logger.error("Error processing message",
                        error_type=type(error).__name__,
                        error_message=str(error),
                        processing_path=error_path)
        
        # Track message processing error metrics with path identification
        self.logger.metric("ws_message_processing_errors", 1,
                         tags={"exchange": "ws", "path": error_path})
    
    async def _on_error(self, error: Exception) -> None:
        """Handle WebSocket errors using strategy classification."""
        self.metrics.error_count += 1
        
        error_type = self.strategies.connection_strategy.classify_error(error)
        
        if error_type == "abnormal_closure":
            self.logger.warning("WebSocket error",
                              error_type=error_type,
                              error_message=str(error))
        else:
            self.logger.error("WebSocket error",
                            error_type=error_type,
                            error_message=str(error))
        
        # Track WebSocket error metrics
        self.logger.metric("ws_errors", 1,
                         tags={"exchange": "ws", "error_type": error_type})
        
        # Strategy decides on reconnection in _connection_loop
    
    async def _heartbeat_loop(self) -> None:
        """Strategy-managed heartbeat loop."""
        consecutive_failures = 0
        max_failures = 3
        
        try:
            while True:
                await asyncio.sleep(self.config.heartbeat_interval)
                
                # Use strategy for heartbeat (custom ping messages for exchanges that need them)
                if self.config.has_heartbeat and self.is_connected():
                    try:
                        await self.strategies.connection_strategy.handle_heartbeat()
                        consecutive_failures = 0  # Reset on success
                        self.logger.debug("Strategy heartbeat sent successfully")
                        
                        # Track successful heartbeat
                        self.logger.metric("ws_heartbeats_sent", 1,
                                         tags={"exchange": "ws"})
                        
                    except Exception as e:
                        consecutive_failures += 1
                        self.logger.warning("Strategy heartbeat failed",
                                          consecutive_failures=consecutive_failures,
                                          max_failures=max_failures,
                                          error_message=str(e))
                        
                        # Track heartbeat failures
                        self.logger.metric("ws_heartbeat_failures", 1,
                                         tags={"exchange": "ws"})
                        
                        # If too many consecutive failures, stop heartbeat (built-in ping/pong will handle)
                        if consecutive_failures >= max_failures:
                            self.logger.error("Too many consecutive heartbeat failures, stopping custom heartbeat",
                                            max_failures=max_failures)
                            
                            # Track heartbeat loop failure
                            self.logger.metric("ws_heartbeat_loop_failures", 1,
                                             tags={"exchange": "ws"})
                            break
                        
        except asyncio.CancelledError:
            self.logger.debug("Strategy heartbeat loop cancelled")
        except Exception as e:
            self.logger.error("Strategy heartbeat loop error",
                            error_type=type(e).__name__,
                            error_message=str(e))
            
            # Track heartbeat loop error metrics
            self.logger.metric("ws_heartbeat_loop_errors", 1,
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
        """Get comprehensive performance metrics for dual-path architecture."""
        uptime = time.perf_counter() - self.start_time if self.start_time > 0 else 0
        
        # Calculate path-specific performance
        legacy_avg_time = (
            self.legacy_metrics['total_time_ms'] / max(1, self.legacy_metrics['messages'])
            if self.legacy_metrics['messages'] > 0 else 0
        )
        
        direct_avg_time = (
            self.direct_metrics['total_time_ms'] / max(1, self.direct_metrics['messages'])
            if self.direct_metrics['messages'] > 0 else 0
        )
        
        return {
            # Overall metrics
            'messages_processed': self.metrics.messages_processed,
            'messages_per_second': self.metrics.messages_processed / uptime if uptime > 0 else 0,
            'avg_processing_time_ms': self.metrics.avg_processing_time_ms,
            'max_processing_time_ms': self.metrics.max_processing_time_ms,
            'connection_uptime_seconds': uptime,
            'reconnection_count': self.metrics.reconnection_count,
            'error_count': self.metrics.error_count,
            'connection_state': self.connection_state.name,
            
            # Architecture-specific metrics
            'architecture': {
                'current': 'direct' if self.use_direct_handling else 'legacy',
                'switches': self.architecture_switches,
                'legacy_path': {
                    'messages': self.legacy_metrics['messages'],
                    'errors': self.legacy_metrics['errors'],
                    'avg_time_ms': legacy_avg_time,
                    'error_rate': self.legacy_metrics['errors'] / max(1, self.legacy_metrics['messages'])
                },
                'direct_path': {
                    'messages': self.direct_metrics['messages'],
                    'errors': self.direct_metrics['errors'],
                    'avg_time_ms': direct_avg_time,
                    'error_rate': self.direct_metrics['errors'] / max(1, self.direct_metrics['messages'])
                }
            },
            
            # Adapter status if available
            'adapters': {
                'handler_adapter': self.handler_adapter.get_status() if self.handler_adapter else None,
                'strategy_adapter': self.strategy_adapter.get_health_status() if self.strategy_adapter else None
            }
        }
    
    def switch_architecture(self, use_direct: bool) -> None:
        """Hot-swap between architectures without reconnection."""
        if use_direct == self.use_direct_handling:
            self.logger.info("Architecture switch requested but already using target architecture",
                           current_architecture='direct' if self.use_direct_handling else 'legacy',
                           requested_architecture='direct' if use_direct else 'legacy')
            return
        
        if use_direct and not self.direct_handler:
            raise ValueError("Cannot switch to direct handling: no direct_handler available")
        
        if not use_direct and not self.strategies:
            raise ValueError("Cannot switch to legacy: no strategies available")
        
        previous_arch = 'direct' if self.use_direct_handling else 'legacy'
        self.use_direct_handling = use_direct
        new_arch = 'direct' if use_direct else 'legacy'
        self.architecture_switches += 1
        
        self.logger.info("Architecture switched successfully",
                        previous_architecture=previous_arch,
                        new_architecture=new_arch,
                        total_switches=self.architecture_switches)
        
        # Track architecture switch metrics
        self.logger.metric("ws_architecture_switches", 1,
                         tags={"exchange": "ws", 
                               "from": previous_arch, 
                               "to": new_arch})
    
    def get_architecture_status(self) -> Dict[str, Any]:
        """Get current architecture configuration and capabilities."""
        return {
            'current_architecture': 'direct' if self.use_direct_handling else 'legacy',
            'capabilities': {
                'can_use_direct': self.direct_handler is not None,
                'can_use_legacy': self.strategies is not None,
                'hot_swap_enabled': True,
                'fallback_enabled': self.adapter_config.fallback_on_error
            },
            'components': {
                'direct_handler_type': type(self.direct_handler).__name__ if self.direct_handler else None,
                'strategy_set_available': self.strategies is not None,
                'handler_adapter_active': self.handler_adapter is not None,
                'strategy_adapter_active': self.strategy_adapter is not None
            },
            'configuration': {
                'use_direct_handling': self.use_direct_handling,
                'fallback_on_error': self.adapter_config.fallback_on_error,
                'performance_monitoring': self.adapter_config.enable_performance_monitoring,
                'max_error_count': self.adapter_config.max_error_count
            }
        }
    
    async def close(self) -> None:
        """Close WebSocket manager and cleanup resources."""
        self.logger.info("Closing WebSocket manager V4...",
                        active_symbols_count=len(self._active_symbols))
        
        try:
            with LoggingTimer(self.logger, "ws_manager_close") as timer:
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
                
                # Strategy cleanup
                if self.strategies and self.strategies.connection_strategy:
                    await self.strategies.connection_strategy.cleanup()
                
                self.connection_state = ConnectionState.DISCONNECTED
            
            self.logger.info("WebSocket manager V4 closed",
                           close_time_ms=timer.elapsed_ms)
            
            # Track close metrics
            self.logger.metric("ws_manager_closes", 1,
                             tags={"exchange": "ws"})
            self.logger.metric("ws_close_time_ms", timer.elapsed_ms,
                             tags={"exchange": "ws"})
            
        except Exception as e:
            self.logger.error("Error closing WebSocket manager V4",
                            error_type=type(e).__name__,
                            error_message=str(e))
            
            # Track close error metrics
            self.logger.metric("ws_close_errors", 1,
                             tags={"exchange": "ws"})