"""
WebSocket Manager V3 - Strategy-Driven Architecture

Clean WebSocket manager that uses strategy.connect() directly without ws_client dependency.
Implements true strategy-driven connection handling with encapsulated policies.

HFT COMPLIANCE: Sub-millisecond message processing, <100ms reconnection.
"""

import logging
import asyncio
import time
from typing import List, Dict, Optional, Callable, Any, Awaitable, Set
from websockets.client import WebSocketClientProtocol
from websockets.protocol import State as WsState

from structs.common import Symbol
from core.transport.websocket.structs import SubscriptionAction, WebsocketChannelType
from core.transport.websocket.strategies.strategy_set import WebSocketStrategySet
from .structs import ParsedMessage, WebSocketManagerConfig, PerformanceMetrics
from core.config.structs import WebSocketConfig
from core.transport.websocket.structs import ConnectionState
from core.exceptions.exchange import BaseExchangeError
import msgspec


class WebSocketManager:
    """
    Strategy-driven WebSocket manager with direct connection handling.
    
    This version eliminates the ws_client dependency and uses strategies
    for all connection-specific logic including establishment, reconnection,
    and heartbeat handling.
    
    Key improvements:
    - Direct strategy.connect() usage
    - Strategy-encapsulated reconnection policies
    - Exchange-specific error handling
    - Cleaner separation of concerns
    """
    
    def __init__(
        self,
        config: WebSocketConfig,
        strategies: WebSocketStrategySet,
        message_handler: Callable[[ParsedMessage], Awaitable[None]],
        state_change_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None,
        manager_config: Optional[WebSocketManagerConfig] = None
    ):
        self.config = config
        self.strategies = strategies
        self.message_handler = message_handler
        self.state_change_handler = state_change_handler
        self.manager_config = manager_config or WebSocketManagerConfig()
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
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
        self._active_symbols: Set[Symbol] = set()
        self._ws_channels: List[WebsocketChannelType] = []
        
        # Performance tracking
        self.metrics = PerformanceMetrics()
        self.start_time = 0.0
        
        # Message processing
        self._message_queue: asyncio.Queue = asyncio.Queue(
            maxsize=self.manager_config.max_pending_messages
        )
        
        self.logger.info("WebSocket manager V2 initialized with strategy-driven architecture")
    
    async def initialize(self, symbols: Optional[List[Symbol]] = None,
                         channels: Optional[List[WebsocketChannelType]] = None) -> None:
        """
        Initialize WebSocket connection using strategy.connect() directly.
        
        Args:
            symbols: Optional list of symbols for initial subscription
        """
        self.start_time = time.perf_counter()
        if symbols:
            self._active_symbols.update(symbols)

        if channels:
            self._ws_channels = channels

        try:
            self.logger.info("Initializing WebSocket manager with direct strategy connection")
            
            # Start connection loop (handles reconnection with strategy policies)
            self._should_reconnect = True
            self._connection_task = asyncio.create_task(self._connection_loop())
            
            # Start message processing
            self._processing_task = asyncio.create_task(self._process_messages())
            
            # Start strategy-managed heartbeat if needed
            # Note: This heartbeat supplements built-in ping/pong for exchanges requiring custom ping
            if self.config.heartbeat_interval and self.config.heartbeat_interval > 0:
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                self.logger.info(f"Started custom heartbeat with {self.config.heartbeat_interval}s interval (supplements built-in ping/pong)")
            
            self.logger.info("WebSocket manager V2 initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize WebSocket manager V2: {e}")
            await self.close()
            raise BaseExchangeError(500, f"WebSocket initialization failed: {e}")
    
    async def subscribe(self, symbols: List[Symbol]) -> None:
        """Subscribe to symbols using strategy."""
        if not self.is_connected():
            raise BaseExchangeError(503, "WebSocket not connected")

        try:
            messages = await self.strategies.subscription_strategy.create_subscription_messages(
                action=SubscriptionAction.SUBSCRIBE, symbols=symbols, channels=self._ws_channels)
            
            if not messages:
                self.logger.warning("No subscription messages created")
                return
            
            self.logger.info(f"Sending {len(messages)} subscription messages for {len(symbols)} symbols")
            
            for message in messages:
                await self.send_message(message)
            
            self._active_symbols.update(symbols)
            
        except Exception as e:
            self.logger.error(f"Subscription failed: {e}")
            raise BaseExchangeError(400, f"Subscription failed: {e}")
    
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
            raise BaseExchangeError(503, "WebSocket not connected")
        
        try:
            msg_str = msgspec.json.encode(message).decode("utf-8")
            await self._websocket.send(msg_str)
            
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            raise BaseExchangeError(400, f"Message send failed: {e}")
    
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
                    raise BaseExchangeError(500, "Strategy returned no WebSocket connection")
                
                await self._update_state(ConnectionState.CONNECTED)
                
                # Reset reconnection attempts on successful connection
                reconnect_attempts = 0
                
                # Authenticate if required
                auth_success = await self.strategies.connection_strategy.authenticate()
                if not auth_success:
                    self.logger.error("Authentication failed")
                    await self._websocket.close()
                    continue
                
                # Subscribe to active symbols
                # if self._active_symbols:
                await self.subscribe(list(self._active_symbols))
                
                # Start message reader
                self._reader_task = asyncio.create_task(self._message_reader())
                
                self.logger.info("Strategy-driven WebSocket connection established successfully")
                
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
            while self.is_connected():
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
        
        self.logger.warning(f"Connection error ({error_type}, attempt {attempt + 1}): {error}. Reconnecting in {delay:.1f}s")
        
        await self._update_state(ConnectionState.RECONNECTING)
        await asyncio.sleep(delay)
    
    async def _update_state(self, state: ConnectionState) -> None:
        """Update connection state and notify handlers."""
        previous_state = self.connection_state
        self.connection_state = state
        
        if previous_state != state:
            self.logger.info(f"Connection state: {previous_state.name} → {state.name}")
            
            # Notify external handler
            if self.state_change_handler:
                try:
                    await self.state_change_handler(state)
                except Exception as e:
                    self.logger.error(f"Error in state change handler: {e}")
    
    async def _on_raw_message(self, raw_message: Any) -> None:
        """Queue raw message for processing."""
        start_time = time.perf_counter()
        
        try:
            if self._message_queue.full():
                self.logger.warning("Message queue full, dropping oldest")
                try:
                    self._message_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            
            await self._message_queue.put((raw_message, start_time))
            
        except Exception as e:
            self.metrics.error_count += 1
            self.logger.error(f"Error queuing message: {e}")
    
    async def _process_messages(self) -> None:
        """Process queued messages asynchronously."""
        while True:
            try:
                raw_message, queue_time = await self._message_queue.get()
                processing_start = time.perf_counter()
                
                try:
                    parsed_message = await self.strategies.message_parser.parse_message(raw_message)
                    
                    if parsed_message:
                        await self.message_handler(parsed_message)
                        
                        processing_time_ms = (time.perf_counter() - processing_start) * 1000
                        self.metrics.update_processing_time(processing_time_ms)
                        self.metrics.messages_processed += 1
                
                except Exception as e:
                    self.metrics.error_count += 1
                    self.logger.error(f"Error processing message: {e}")
                
                finally:
                    self._message_queue.task_done()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in message processing loop: {e}")
                await asyncio.sleep(0.1)
    
    async def _on_error(self, error: Exception) -> None:
        """Handle WebSocket errors using strategy classification."""
        self.metrics.error_count += 1
        
        error_type = self.strategies.connection_strategy.classify_error(error)
        
        if error_type == "abnormal_closure":
            self.logger.warning(f"WebSocket {error_type}: {error}")
        else:
            self.logger.error(f"WebSocket {error_type}: {error}")
        
        # Strategy decides on reconnection in _connection_loop
    
    async def _heartbeat_loop(self) -> None:
        """Strategy-managed heartbeat loop."""
        consecutive_failures = 0
        max_failures = 3
        
        try:
            while self.is_connected():
                await asyncio.sleep(self.config.heartbeat_interval)
                
                # Use strategy for heartbeat (custom ping messages for exchanges that need them)
                if self.config.has_heartbeat:
                    try:
                        await self.strategies.connection_strategy.handle_heartbeat()
                        consecutive_failures = 0  # Reset on success
                        self.logger.debug("Strategy heartbeat sent successfully")
                    except Exception as e:
                        consecutive_failures += 1
                        self.logger.warning(f"Strategy heartbeat failed ({consecutive_failures}/{max_failures}): {e}")
                        
                        # If too many consecutive failures, stop heartbeat (built-in ping/pong will handle)
                        if consecutive_failures >= max_failures:
                            self.logger.error(f"Too many consecutive heartbeat failures ({max_failures}), stopping custom heartbeat")
                            break
                        
        except asyncio.CancelledError:
            self.logger.debug("Strategy heartbeat loop cancelled")
        except Exception as e:
            self.logger.error(f"Strategy heartbeat loop error: {e}")
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        if self.connection_state != ConnectionState.CONNECTED or self._websocket is None:
            return False
        try:
            return self._websocket.state == WsState.OPEN
        except AttributeError:
            self.logger.error(f"WebSocket object {type(self._websocket)} has no 'closed' attribute")
            return False
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        uptime = time.perf_counter() - self.start_time if self.start_time > 0 else 0
        
        return {
            'messages_processed': self.metrics.messages_processed,
            'messages_per_second': self.metrics.messages_processed / uptime if uptime > 0 else 0,
            'avg_processing_time_ms': self.metrics.avg_processing_time_ms,
            'max_processing_time_ms': self.metrics.max_processing_time_ms,
            'connection_uptime_seconds': uptime,
            'reconnection_count': self.metrics.reconnection_count,
            'error_count': self.metrics.error_count,
            'connection_state': self.connection_state.name
        }
    
    async def close(self) -> None:
        """Close WebSocket manager and cleanup resources."""
        self.logger.info("Closing WebSocket manager V2...")
        
        try:
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
                    self.logger.error(f"Error closing WebSocket: {e}")
                self._websocket = None
            
            # Strategy cleanup
            if self.strategies and self.strategies.connection_strategy:
                await self.strategies.connection_strategy.cleanup()
            
            self.connection_state = ConnectionState.DISCONNECTED
            self.logger.info("WebSocket manager V2 closed")
            
        except Exception as e:
            self.logger.error(f"Error closing WebSocket manager V2: {e}")