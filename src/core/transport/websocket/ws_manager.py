"""
WebSocket Manager

HFT-compliant WebSocket orchestrator using strategy pattern composition.
Manages connection lifecycle, subscriptions, and message routing.

HFT COMPLIANCE: Sub-millisecond message processing, zero-copy patterns.
"""

import logging
import asyncio
import time
from typing import List, Dict, Optional, Set, Callable, Any, Awaitable

from structs.exchange import Symbol
from core.transport.websocket.strategies.strategy_set import WebSocketStrategySet
from .structs import MessageType, SubscriptionAction, ParsedMessage, WebSocketManagerConfig, \
    PerformanceMetrics
from core.config.structs import WebSocketConfig
from core.transport.websocket.ws_client import WebsocketClient
from core.transport.websocket.structs import ConnectionState
from core.exceptions.exchange import BaseExchangeError


class WebSocketManager:
    """
    Strategy-based WebSocket manager for HFT trading systems.
    
    Orchestrates connection, subscription, and message processing strategies
    while maintaining sub-millisecond performance requirements.
    
    HFT COMPLIANCE: <1ms message processing, <100ms reconnection.
    """
    
    def __init__(
        self,
        config: WebSocketConfig,
        strategies: WebSocketStrategySet,
        message_handler: Callable[[ParsedMessage], Awaitable[None]],
        state_change_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None,
        manager_config: Optional[WebSocketManagerConfig] = None
    ):
        """
        Initialize WebSocket manager with strategy composition.
        
        Args:
            config: WebSocket connection configuration
            strategies: Complete strategy set (connection, subscription, parser)
            message_handler: Async callback for processed messages
            manager_config: Manager-specific configuration
        """
        self.config = config
        self.strategies = strategies
        self.message_handler = message_handler
        self.state_change_handler = state_change_handler
        self.manager_config = manager_config or WebSocketManagerConfig()
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Connection management (stateless - no symbol tracking)
        self.ws_client: Optional[WebsocketClient] = None
        self.connection_state = ConnectionState.DISCONNECTED
        self._is_initial_connection = True  # Flag for initial connection handling
        
        # Store initial subscription parameters for first connection
        self._initial_subscription_kwargs: Optional[Dict[str, Any]] = None
        
        # Performance tracking
        self.metrics = PerformanceMetrics()
        self.start_time = 0.0
        
        # Message processing
        self._message_queue: asyncio.Queue = asyncio.Queue(
            maxsize=self.manager_config.max_pending_messages
        )
        self._processing_task: Optional[asyncio.Task] = None
        self._connection_task: Optional[asyncio.Task] = None
        
        # Channel-based subscription management (symbol agnostic)
        self._active_channels: Set[str] = set()
        
        # HFT Optimizations (caching removed - handled by implementations)
        # Note: Symbol state management moved to WebSocket implementations
        
        self.logger.info("WebSocket manager initialized with strategy composition")
    
    async def initialize(self, symbols: List[Symbol] = None) -> None:
        """
        Initialize WebSocket connection and subscriptions.
        
        Args:
            symbols: Initial symbols to subscribe to
        """
        self.start_time = time.perf_counter()
        
        try:
            # Get connection context from strategy
            connection_context = await self.strategies.connection_strategy.create_connection_context()
            
            # Update WebSocket config with strategy context
            # self.config.url = connection_context.url
            
            # Initialize WebSocket client
            self.ws_client = WebsocketClient(
                config=self.config.with_url(connection_context.url),
                message_handler=self._on_raw_message,
                error_handler=self._on_error,
                connection_handler=self._on_state_change
            )
            
            # Start connection
            await self.ws_client.start()
            
            # Authenticate if required
            if connection_context.auth_required:
                auth_success = await self.strategies.connection_strategy.authenticate(self.ws_client)
                if not auth_success:
                    raise BaseExchangeError(401, "WebSocket authentication failed")
            
            # Start message processing
            self._processing_task = asyncio.create_task(self._process_messages())
            
            # Store initial subscription parameters for when connection is established
            if symbols:
                self._initial_subscription_kwargs = {'symbols': symbols}
                self.logger.info(f"Stored initial subscription for {len(symbols)} symbols")
            else:
                self._initial_subscription_kwargs = {}
                self.logger.info("Stored initial subscription for private channels")
            
            self.logger.info("WebSocket manager initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize WebSocket manager: {e}")
            await self.close()
            raise BaseExchangeError(500, f"WebSocket initialization failed: {e}")
    
    async def send_message(self, message: Any) -> None:
        """
        Send message through WebSocket connection.
        
        Stateless message sending - no subscription state management.
        
        Args:
            message: Message to send (dict or string)
        """
        if not self.ws_client or self.connection_state != ConnectionState.CONNECTED:
            raise BaseExchangeError(503, "WebSocket not connected")
        
        try:
            if isinstance(message, str):
                # JSON string - parse to dict for WebSocket client
                import msgspec
                message_dict = msgspec.json.decode(message)
                await self.ws_client.send_message(message_dict)
            else:
                # Dict or other object
                await self.ws_client.send_message(message)
                
            self.logger.debug(f"Sent WebSocket message: {message}")
            
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            raise BaseExchangeError(400, f"Message send failed: {e}")
    
    
    async def _on_raw_message(self, raw_message: str) -> None:
        """
        Handle raw WebSocket message.
        
        HFT COMPLIANT: Fast message queuing with minimal processing.
        """
        start_time = time.perf_counter()
        
        try:
            # Queue message for processing to avoid blocking WebSocket
            if self._message_queue.full():
                self.logger.warning("Message queue full, dropping oldest message")
                try:
                    self._message_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            
            await self._message_queue.put((raw_message, start_time))
            
        except Exception as e:
            self.metrics.error_count += 1
            self.logger.error(f"Error queuing message: {e}")
    
    async def _process_messages(self) -> None:
        """
        Process queued messages asynchronously.
        
        HFT COMPLIANT: Batch processing with sub-millisecond targets.
        """
        while True:
            try:
                # Batch processing optimization
                if (self.manager_config.batch_processing_enabled and 
                    self.strategies.message_parser.supports_batch_parsing()):
                    
                    await self._process_message_batch()
                else:
                    await self._process_single_message()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.metrics.error_count += 1
                self.logger.error(f"Error in message processing: {e}")
                await asyncio.sleep(0.1)  # Brief pause on error
    
    async def _process_single_message(self) -> None:
        """Process a single queued message."""
        raw_message, queue_time = await self._message_queue.get()
        processing_start = time.perf_counter()
        
        try:
            # Parse message using strategy
            parsed_message = await self.strategies.message_parser.parse_message(raw_message)
            
            if parsed_message:
                # Route to handler
                await self.message_handler(parsed_message)
                
                # Update performance metrics
                processing_time_ms = (time.perf_counter() - processing_start) * 1000
                self.metrics.update_processing_time(processing_time_ms)
                
                # Track orderbook updates specifically
                if parsed_message.message_type == MessageType.ORDERBOOK:
                    self.metrics.orderbook_updates += 1
            
        except Exception as e:
            self.metrics.error_count += 1
            self.logger.error(f"Error processing message: {e}")
        
        finally:
            self._message_queue.task_done()
    
    async def _process_message_batch(self) -> None:
        """Process multiple messages in batch for efficiency."""
        messages = []
        batch_start = time.perf_counter()
        
        # Collect batch
        for _ in range(min(self.manager_config.batch_size, self._message_queue.qsize())):
            try:
                raw_message, queue_time = self._message_queue.get_nowait()
                messages.append(raw_message)
            except asyncio.QueueEmpty:
                break
        
        if not messages:
            await asyncio.sleep(0.001)  # Brief wait if no messages
            return
        
        try:
            # Batch parse using strategy
            async for parsed_message in self.strategies.message_parser.parse_batch_messages(messages):
                await self.message_handler(parsed_message)
                
                # Track orderbook updates
                if parsed_message.message_type == MessageType.ORDERBOOK:
                    self.metrics.orderbook_updates += 1
            
            # Update batch metrics
            batch_time_ms = (time.perf_counter() - batch_start) * 1000
            avg_time_per_message = batch_time_ms / len(messages)
            
            for _ in messages:
                self.metrics.update_processing_time(avg_time_per_message)
                self._message_queue.task_done()
            
        except Exception as e:
            self.metrics.error_count += 1
            self.logger.error(f"Error processing message batch: {e}")
            
            # Mark tasks as done even on error
            for _ in messages:
                self._message_queue.task_done()
    
    async def _on_error(self, error: Exception) -> None:
        """Handle WebSocket errors."""
        self.metrics.error_count += 1
        self.logger.error(f"WebSocket error: {error}")
        
        # Check if reconnection should be attempted
        if self.strategies.connection_strategy.should_reconnect(error):
            self.metrics.reconnection_count += 1
            self.logger.info("Attempting WebSocket reconnection...")
    
    async def _on_state_change(self, state: ConnectionState) -> None:
        """Handle WebSocket connection state changes."""
        previous_state = self.connection_state
        self.connection_state = state
        self.logger.debug(f"WebSocket state changed from {previous_state.name} to {state.name} (active_channels: {len(self._active_channels)})")
        
        # Only process on transition to CONNECTED, not repeated CONNECTED events
        if state == ConnectionState.CONNECTED and previous_state != ConnectionState.CONNECTED:
            if self._is_initial_connection:
                # First connection - handle initial subscriptions
                if self._initial_subscription_kwargs is not None:
                    self.logger.info("Creating initial subscriptions on first connection")
                    await self.add_subscription(**self._initial_subscription_kwargs)
                self._is_initial_connection = False
            else:
                # Reconnection - restore all active channels
                if (self.strategies.subscription_strategy.should_resubscribe_on_reconnect() and
                    self._active_channels):
                    
                    self.logger.info(f"Restoring {len(self._active_channels)} channel subscriptions after reconnect")
                    await self.restore_all_subscriptions()

        if self.state_change_handler:
            await self.state_change_handler(state)

    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get current performance metrics.
        
        Returns:
            Dictionary with HFT performance metrics
        """
        current_time = time.perf_counter()
        uptime = current_time - self.start_time if self.start_time > 0 else 0
        
        # Calculate messages per second
        if uptime > 0:
            self.metrics.messages_per_second = self.metrics.messages_processed / uptime
        
        self.metrics.connection_uptime = uptime
        
        # HFT compliance percentage
        hft_compliance_rate = 0.0
        if self.metrics.messages_processed > 0:
            hft_compliance_rate = (self.metrics.sub_1ms_messages / self.metrics.messages_processed) * 100
        
        return {
            'messages_processed': self.metrics.messages_processed,
            'messages_per_second': round(self.metrics.messages_per_second, 2),
            'avg_processing_time_ms': round(self.metrics.avg_processing_time_ms, 3),
            'max_processing_time_ms': round(self.metrics.max_processing_time_ms, 3),
            'connection_uptime_seconds': round(uptime, 1),
            'reconnection_count': self.metrics.reconnection_count,
            'error_count': self.metrics.error_count,
            'orderbook_updates': self.metrics.orderbook_updates,
            'hft_compliance_rate_percent': round(hft_compliance_rate, 1),
            'latency_violations': self.metrics.latency_violations,
            'active_channels_count': len(self._active_channels),
            'connection_state': self.connection_state.name
        }
    
    async def close(self) -> None:
        """Close WebSocket manager and cleanup resources."""
        self.logger.info("Closing WebSocket manager...")
        
        try:
            # Cancel processing task
            if self._processing_task and not self._processing_task.done():
                self._processing_task.cancel()
                try:
                    await self._processing_task
                except asyncio.CancelledError:
                    pass
            
            # Close WebSocket client
            if self.ws_client:
                await self.ws_client.stop()
                self.ws_client = None
            
            # Call strategy cleanup (for listen key management, etc.)
            if self.strategies and self.strategies.connection_strategy:
                try:
                    await self.strategies.connection_strategy.cleanup()
                except Exception as e:
                    self.logger.error(f"Error during strategy cleanup: {e}")
            
            # Clear state
            self._active_channels.clear()
            self._initial_subscription_kwargs = None
            self._is_initial_connection = True
            self.connection_state = ConnectionState.DISCONNECTED
            
            self.logger.info("WebSocket manager closed successfully")
            
        except Exception as e:
            self.logger.error(f"Error closing WebSocket manager: {e}")
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self.connection_state == ConnectionState.CONNECTED
    
    def get_active_channels(self) -> List[str]:
        """Get list of active channels."""
        return list(self._active_channels)
    
    async def add_channels(self, channels: List[str]) -> None:
        """
        Add channels to subscription and store for restoration.
        
        Args:
            channels: List of channel names to subscribe to
        """
        if not channels:
            return
        
        # Store channels for restoration
        self._active_channels.update(channels)
        
        # Create subscription messages using strategy
        messages = self.strategies.subscription_strategy.format_subscription_messages({
            'action': 'subscribe',
            'channels': channels
        })
        
        # Send subscription messages
        for message in messages:
            await self.send_message(message)
            
        self.logger.debug(f"Added {len(channels)} channels")
    
    async def remove_channels(self, channels: List[str]) -> None:
        """
        Remove channels from subscription.
        
        Args:
            channels: List of channel names to unsubscribe from
        """
        if not channels:
            return
        
        # Filter to only remove channels we actually have
        channels_to_remove = [c for c in channels if c in self._active_channels]
        if not channels_to_remove:
            return
        
        # Remove from active channels
        self._active_channels.difference_update(channels_to_remove)
        
        # Create unsubscription messages using strategy
        messages = self.strategies.subscription_strategy.format_subscription_messages({
            'action': 'unsubscribe',
            'channels': channels_to_remove
        })
        
        # Send unsubscription messages
        for message in messages:
            await self.send_message(message)
            
        self.logger.debug(f"Removed {len(channels_to_remove)} channels")
    
    async def restore_all_subscriptions(self) -> None:
        """
        Restore all active channel subscriptions after reconnection.
        
        Uses stored channel names to restore subscriptions without symbol knowledge.
        """
        if not self._active_channels:
            self.logger.debug("No active channels to restore")
            return
        
        # Create restoration messages using strategy
        messages = self.strategies.subscription_strategy.format_subscription_messages({
            'action': 'subscribe',
            'channels': list(self._active_channels)
        })
        
        # Send all restoration messages
        for message in messages:
            await self.send_message(message)
            
        self.logger.info(f"Restored {len(self._active_channels)} channel subscriptions")
    
    async def add_subscription(self, **kwargs) -> None:
        """
        Add subscription using strategy-generated channels.
        
        Unified method that generates channels via strategy and subscribes.
        
        Args:
            **kwargs: Strategy-specific subscription parameters:
                - For public: symbols=[Symbol, ...]
                - For private: (no params needed - uses fixed channels)
        """
        # Generate channels using unified strategy method
        channels = self.strategies.subscription_strategy.generate_channels(**kwargs)
        
        if not channels:
            return
            
        # Subscribe to generated channels
        await self.add_channels(channels)
        
        self.logger.debug(f"Added subscription with {len(channels)} channels")
    
    async def remove_subscription(self, **kwargs) -> None:
        """
        Remove subscription using strategy-generated channels.
        
        Unified method that generates channels via strategy and unsubscribes.
        
        Args:
            **kwargs: Strategy-specific subscription parameters:
                - For public: symbols=[Symbol, ...]
                - For private: (no params needed - uses fixed channels)
        """
        # Generate channels using unified strategy method
        channels = self.strategies.subscription_strategy.generate_channels(**kwargs)
        
        if not channels:
            return
            
        # Unsubscribe from generated channels
        await self.remove_channels(channels)
        
        self.logger.debug(f"Removed subscription with {len(channels)} channels")