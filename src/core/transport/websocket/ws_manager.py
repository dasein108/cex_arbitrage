"""
WebSocket Manager V2 - Refactored Architecture

Clean, strategy-driven WebSocket manager with no exchange-specific assumptions.
Focuses on core responsibilities: connection lifecycle, message flow, and strategy delegation.

HFT COMPLIANCE: Sub-millisecond message processing, zero-copy patterns.
"""

import logging
import asyncio
import time
from typing import List, Dict, Optional, Callable, Any, Awaitable, Set

from structs.common import Symbol
from core.transport.websocket.structs import SubscriptionAction
from core.transport.websocket.strategies.strategy_set import WebSocketStrategySet
from .structs import ParsedMessage, WebSocketManagerConfig, PerformanceMetrics
from core.config.structs import WebSocketConfig
from core.transport.websocket.ws_client import WebsocketClient
from core.transport.websocket.structs import ConnectionState
from core.exceptions.exchange import BaseExchangeError


class WebSocketManager:
    """
    Clean WebSocket manager focused on core responsibilities.
    
    Responsibilities:
    - Connection lifecycle management
    - Message queuing and processing
    - Strategy delegation
    - Performance metrics
    
    NOT responsible for:
    - Channel/subscription format (handled by strategy)
    - Message format assumptions (handled by strategy)
    - Symbol tracking (handled by implementation)
    
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
        Initialize WebSocket manager with clean architecture.
        
        Args:
            config: WebSocket connection configuration
            strategies: Complete strategy set for exchange-specific logic
            message_handler: Async callback for parsed messages
            state_change_handler: Optional callback for connection state changes
            manager_config: Manager-specific configuration
        """
        self.config = config
        self.strategies = strategies
        self.message_handler = message_handler
        self.state_change_handler = state_change_handler
        self.manager_config = manager_config or WebSocketManagerConfig()
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Connection management
        self.ws_client: Optional[WebsocketClient] = None
        self.connection_state = ConnectionState.DISCONNECTED
        self._auth_required = False
        
        # Performance tracking
        self.metrics = PerformanceMetrics()
        self.start_time = 0.0
        self._active_symbols: Set[Symbol] = set()
        # Message processing
        self._message_queue: asyncio.Queue = asyncio.Queue(
            maxsize=self.manager_config.max_pending_messages
        )
        self._processing_task: Optional[asyncio.Task] = None
        

        self.logger.info("WebSocket manager initialized with clean architecture")
    
    async def initialize(self, symbols: Optional[List[Symbol]] = None) -> None:
        """
        Initialize WebSocket connection with optional initial symbols.
        
        Args:
            symbols: Optional list of symbols for initial subscription
        """
        self.start_time = time.perf_counter()
        self._active_symbols.update(symbols)
        try:
            # Get connection context from strategy
            connection_context = await self.strategies.connection_strategy.create_connection_context()
            self._auth_required = connection_context.auth_required
            
            # Initialize WebSocket client
            self.ws_client = WebsocketClient(
                config=self.config.with_url(connection_context.url),
                message_handler=self._on_raw_message,
                error_handler=self._on_error,
                connection_handler=self._on_state_change
            )
            
            # Store initial symbols for when connection is established
            if symbols:
                self.logger.info(f"Stored initial subscription for {len(symbols)} symbols")
            
            # Start connection
            await self.ws_client.start()
            
            # Start message processing
            self._processing_task = asyncio.create_task(self._process_messages())
            
            self.logger.info("WebSocket manager initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize WebSocket manager: {e}")
            await self.close()
            raise BaseExchangeError(500, f"WebSocket initialization failed: {e}")
    
    async def subscribe(self, symbols: List[Symbol]) -> None:
        """
        Create and send subscription messages using strategy.
        
        Simplified flow: symbols → create_messages → send dict objects
        
        Args:
            symbols: List of symbols to subscribe to
        """
        if not self.is_connected():
            raise BaseExchangeError(503, "WebSocket not connected")


        try:
            # Get complete message objects from strategy
            messages = await self.strategies.subscription_strategy.create_subscription_messages(
                action=SubscriptionAction.SUBSCRIBE,
                symbols=symbols
            )
            
            if not messages:
                self.logger.warning("No subscription messages created")
                return
            
            self.logger.info(f"Sending {len(messages)} subscription messages for {len(symbols)} symbols")
            
            # Send each complete message dict
            for message in messages:
                await self.send_message(message)
                # Log first 200 chars of message for debugging
                msg_preview = str(message)[:200] + "..." if len(str(message)) > 200 else str(message)
                self.logger.debug(f"Sent subscription: {msg_preview}")
            
            # TODO: update active symbols only on successful subscription ack
            self._active_symbols.update(symbols)
            
        except Exception as e:
            self.logger.error(f"Subscription failed: {e}")
            raise BaseExchangeError(400, f"Subscription failed: {e}")
    
    async def unsubscribe(self, symbols: List[Symbol]) -> None:
        """
        Create and send unsubscription messages using strategy.
        
        Args:
            symbols: List of symbols to unsubscribe from
        """
        if not self.is_connected():
            return  # Silently ignore if not connected
        
        try:
            # Get complete unsubscription message objects from strategy
            messages = await self.strategies.subscription_strategy.create_subscription_messages(
                action=SubscriptionAction.UNSUBSCRIBE,
                symbols=symbols
            )
            
            if not messages:
                return
            
            self.logger.info(f"Sending {len(messages)} unsubscription messages for {len(symbols)} symbols")
            
            # Send each complete message dict
            for message in messages:
                await self.send_message(message)
            
            self._active_symbols.difference_update(symbols)

        except Exception as e:
            self.logger.error(f"Unsubscription failed: {e}")
    
    async def send_message(self, message: Dict[str, Any]) -> None:
        """
        Send complete message dict object through WebSocket connection.
        
        Args:
            message: Complete message dictionary ready for WebSocket sending
        """
        if not self.ws_client or self.connection_state != ConnectionState.CONNECTED:
            raise BaseExchangeError(503, "WebSocket not connected")
        
        try:
            # Send dict object directly - WebSocket client handles JSON encoding
            await self.ws_client.send_message(message)
            
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            raise BaseExchangeError(400, f"Message send failed: {e}")
    
    async def _on_raw_message(self, raw_message: Any) -> None:
        """
        Handle raw WebSocket message.
        
        Args:
            raw_message: Raw message from WebSocket (string or bytes)
        """
        start_time = time.perf_counter()
        
        try:
            # Queue message for async processing
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
        """
        Process queued messages asynchronously.
        
        HFT COMPLIANT: Optimized for sub-millisecond processing.
        """
        while True:
            try:
                # Get message from queue
                raw_message, queue_time = await self._message_queue.get()
                processing_start = time.perf_counter()
                
                try:
                    # Parse message using strategy
                    parsed_message = await self.strategies.message_parser.parse_message(raw_message)
                    
                    if parsed_message:
                        # Route to handler
                        await self.message_handler(parsed_message)
                        
                        # Update metrics
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
    
    async def _on_state_change(self, state: ConnectionState) -> None:
        """
        Handle WebSocket connection state changes.
        
        Args:
            state: New connection state
        """
        previous_state = self.connection_state
        self.connection_state = state
        
        self.logger.info(f"Connection state: {previous_state.name} → {state.name}")
        
        # Handle connection established
        if state == ConnectionState.CONNECTED and previous_state != ConnectionState.CONNECTED:
            
            # Perform authentication if required
            if self._auth_required:
                try:
                    success = await self.strategies.connection_strategy.authenticate(self.ws_client)
                    if not success:
                        self.logger.error("Authentication failed")
                        await self.ws_client.stop()
                        return

                    self.logger.info("Authentication successful")
                except Exception as e:
                    self.logger.error(f"Authentication error: {e}")
                    await self.ws_client.stop()
                    return
                except Exception as e:
                    self.logger.error(f"Initial subscription failed: {e}")
            
            # Handle reconnection subscriptions
            await self.subscribe(list(self._active_symbols))

        # Notify external handler
        if self.state_change_handler:
            try:
                await self.state_change_handler(state)
            except Exception as e:
                self.logger.error(f"Error in state change handler: {e}")
    
    async def _on_error(self, error: Exception) -> None:
        """Handle WebSocket errors."""
        self.metrics.error_count += 1
        self.logger.error(f"WebSocket error: {error}")
        
        # Let strategy decide on reconnection
        if self.strategies.connection_strategy.should_reconnect(error):
            self.metrics.reconnection_count += 1
            self.logger.info("Will attempt reconnection")
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self.connection_state == ConnectionState.CONNECTED


    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics.
        
        Returns:
            Dictionary with performance metrics
        """
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
            
            # Strategy cleanup
            if self.strategies and self.strategies.connection_strategy:
                await self.strategies.connection_strategy.cleanup()
            
            self.connection_state = ConnectionState.DISCONNECTED
            self.logger.info("WebSocket manager closed")
            
        except Exception as e:
            self.logger.error(f"Error closing WebSocket manager: {e}")