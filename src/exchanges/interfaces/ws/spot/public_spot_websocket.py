"""
PublicSpotWebsocket - Concrete Implementation for Spot Public Market Data

Concrete implementation of BasePublicWebsocket for spot trading markets.
Handles orderbook updates, trades, tickers, and other market data streams.

Architecture compliance:
- Inherits from BasePublicWebsocket for domain separation
- Implements all abstract methods with spot-specific logic
- Uses WebSocket manager for connection handling
- Provides message routing to handlers
- Maintains HFT performance requirements
"""

import time
from typing import List, Dict, Set, Optional, Callable, Awaitable, Union

from exchanges.structs.common import Symbol
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, ConnectionState, MessageType, ParsedMessage
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers
from infrastructure.networking.websocket.utils import create_websocket_manager
from config.structs import ExchangeConfig
from infrastructure.logging import HFTLoggerInterface, LoggingTimer
from infrastructure.exceptions.unified import UnifiedConnectionError, UnifiedSubscriptionError

from ..base_public_websocket import BasePublicWebsocket
from ..performance_tracker import PublicWebSocketPerformanceTracker
from ..constants import PerformanceConstants


class PublicSpotWebsocket(BasePublicWebsocket):
    """
    Concrete implementation of public WebSocket for spot trading markets.
    
    Provides complete market data functionality including:
    - Orderbook streaming and management
    - Trade feed processing
    - Ticker updates
    - Symbol subscription management
    
    HFT Optimized:
    - Sub-millisecond message processing
    - Zero-copy message routing
    - Efficient symbol state management
    - Performance metrics tracking
    """
    
    def __init__(
        self,
        config: ExchangeConfig,
        handlers: PublicWebsocketHandlers,
        logger: HFTLoggerInterface,
        connection_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None
    ) -> None:
        """
        Initialize concrete public spot WebSocket implementation.
        
        Args:
            config: Exchange configuration with connection settings
            handlers: Public WebSocket message handlers for market data
            logger: HFT logger for sub-millisecond performance tracking
            connection_handler: Optional callback for connection state changes
        """
        # Initialize base class
        super().__init__(config, handlers, logger, connection_handler)
        
        # Create WebSocket manager using dependency injection
        self._ws_manager = create_websocket_manager(
            exchange_config=config,
            is_private=False,
            message_handler=self._handle_parsed_message,
            state_change_handler=self._handle_state_change,
            logger=logger
        )
        
        # Performance tracking using shared utility
        self._performance_tracker = PublicWebSocketPerformanceTracker(
            exchange_name=self.exchange_name,
            logger=logger,
            ring_buffer_size=PerformanceConstants.DEFAULT_RING_BUFFER_SIZE
        )
        
        self.logger.info(
            "Initialized public spot WebSocket",
            exchange=self.exchange_name,
            implementation="concrete_spot"
        )
    
    async def initialize(
        self,
        symbols: List[Symbol],
        channels: List[PublicWebsocketChannelType]
    ) -> None:
        """
        Initialize WebSocket connection with required symbols.
        
        Args:
            symbols: List of symbols to subscribe to (REQUIRED)
            channels: WebSocket channels to subscribe to
            
        Raises:
            UnifiedConnectionError: If connection fails
            UnifiedSubscriptionError: If symbol subscription fails
            ValueError: If symbols list is empty
        """
        # Validate symbols using base class method
        self._validate_symbols_list(symbols, "initialization")
        
        try:
            with LoggingTimer(self.logger, "public_ws_initialization") as timer:
                # Track connection start time
                self._performance_tracker.start_connection_tracking()
                
                # Initialize WebSocket manager with symbols and channels
                await self._ws_manager.initialize(symbols=symbols, default_channels=channels)
                
                # Add symbols to active set
                self._add_symbols_to_active(symbols)
            
            self.logger.info(
                "Public WebSocket initialized successfully",
                exchange=self.exchange_name,
                symbols_count=len(symbols),
                channels=len(channels),
                initialization_time_ms=timer.elapsed_ms
            )
            
        except Exception as e:
            error_msg = f"Failed to initialize public WebSocket: {str(e)}"
            self.logger.error(
                error_msg,
                exchange=self.exchange_name,
                symbols_count=len(symbols),
                error_type=type(e).__name__
            )
            
            if "connection" in str(e).lower():
                raise UnifiedConnectionError(self.exchange_name, error_msg)
            elif "subscription" in str(e).lower():
                raise UnifiedSubscriptionError(self.exchange_name, error_msg)
            else:
                raise UnifiedConnectionError(self.exchange_name, error_msg)
    
    async def subscribe(self, symbols: List[Symbol]) -> None:
        """
        Add symbols to existing subscription.
        
        Args:
            symbols: Additional symbols to subscribe to
            
        Raises:
            UnifiedSubscriptionError: If subscription fails
            ValueError: If symbols list is empty
        """
        self._validate_symbols_list(symbols, "subscription")
        
        try:
            with LoggingTimer(self.logger, "public_ws_subscribe") as timer:
                await self._ws_manager.subscribe(symbols=symbols)
                self._add_symbols_to_active(symbols)
            
            self.logger.info(
                "Successfully subscribed to additional symbols",
                exchange=self.exchange_name,
                new_symbols=[str(s) for s in symbols],
                total_active=len(self._active_symbols),
                subscribe_time_ms=timer.elapsed_ms
            )
            
        except Exception as e:
            error_msg = f"Failed to subscribe to symbols: {str(e)}"
            self.logger.error(
                error_msg,
                exchange=self.exchange_name,
                failed_symbols=[str(s) for s in symbols],
                error_type=type(e).__name__
            )
            raise UnifiedSubscriptionError(self.exchange_name, error_msg)
    
    async def unsubscribe(self, symbols: List[Symbol]) -> None:
        """
        Remove symbols from current subscription.
        
        Args:
            symbols: Symbols to remove from subscription
            
        Raises:
            UnifiedSubscriptionError: If unsubscription fails
            ValueError: If symbols list is empty
        """
        self._validate_symbols_list(symbols, "unsubscription")
        
        # Filter to only remove symbols we actually have
        symbols_to_remove = [s for s in symbols if s in self._active_symbols]
        if not symbols_to_remove:
            self.logger.warning(
                "No active symbols to unsubscribe",
                exchange=self.exchange_name,
                requested_symbols=[str(s) for s in symbols]
            )
            return
        
        try:
            with LoggingTimer(self.logger, "public_ws_unsubscribe") as timer:
                await self._ws_manager.unsubscribe(symbols=symbols_to_remove)
                self._remove_symbols_from_active(symbols_to_remove)
            
            self.logger.info(
                "Successfully unsubscribed from symbols",
                exchange=self.exchange_name,
                removed_symbols=[str(s) for s in symbols_to_remove],
                remaining_active=len(self._active_symbols),
                unsubscribe_time_ms=timer.elapsed_ms
            )
            
        except Exception as e:
            error_msg = f"Failed to unsubscribe from symbols: {str(e)}"
            self.logger.error(
                error_msg,
                exchange=self.exchange_name,
                failed_symbols=[str(s) for s in symbols_to_remove],
                error_type=type(e).__name__
            )
            raise UnifiedSubscriptionError(self.exchange_name, error_msg)
    
    def get_active_symbols(self) -> Set[Symbol]:
        """
        Get currently subscribed symbols.
        
        Returns:
            Set of symbols currently subscribed to
        """
        return self._active_symbols.copy()
    
    async def close(self) -> None:
        """
        Close WebSocket connection and clean up resources.
        
        Raises:
            ConnectionError: If close operation fails
        """
        try:
            with LoggingTimer(self.logger, "public_ws_close") as timer:
                await self._ws_manager.close()
                self._active_symbols.clear()
            
            self.logger.info(
                "Public WebSocket closed successfully",
                exchange=self.exchange_name,
                close_time_ms=timer.elapsed_ms
            )
            
        except Exception as e:
            error_msg = f"Error closing public WebSocket: {str(e)}"
            self.logger.error(
                error_msg,
                exchange=self.exchange_name,
                error_type=type(e).__name__
            )
            raise ConnectionError(error_msg)
    
    def is_connected(self) -> bool:
        """
        Check connection status.
        
        Returns:
            True if WebSocket is connected, False otherwise
        """
        return self._ws_manager.is_connected()
    
    def get_performance_metrics(self) -> Dict[str, Union[int, float, str]]:
        """
        Get HFT performance metrics for monitoring.
        
        Returns:
            Dictionary containing performance metrics
        """
        base_metrics = self._ws_manager.get_performance_metrics()
        
        # Get metrics from performance tracker with additional context
        additional_metrics = {
            "active_symbols_count": len(self._active_symbols),
            "domain": "market_data"
        }
        
        return self._performance_tracker.get_performance_metrics(
            additional_metrics={**base_metrics, **additional_metrics}
        )
    
    async def _handle_parsed_message(self, message: ParsedMessage) -> None:
        """
        Route parsed messages to appropriate handlers with performance tracking.
        
        Args:
            message: Parsed message from WebSocket
        """
        start_time = time.perf_counter()
        
        try:
            # Route based on message type with performance tracking
            if message.message_type == MessageType.ORDERBOOK:
                if message.data:
                    await self.handlers.handle_orderbook(message.data)
                    
            elif message.message_type == MessageType.TRADES:
                if message.data:
                    # Handle both single trade and list of trades
                    if isinstance(message.data, list):
                        for trade in message.data:
                            await self.handlers.handle_trade(trade)
                    else:
                        await self.handlers.handle_trade(message.data)
                        
            elif message.message_type == MessageType.BOOK_TICKER:
                if message.data:
                    await self.handlers.handle_book_ticker(message.data)
                    
            elif message.message_type == MessageType.TICKER:
                if message.data:
                    await self.handlers.handle_ticker(message.data)
                    
            elif message.message_type == MessageType.SUBSCRIPTION_CONFIRM:
                self.logger.debug(
                    "Subscription confirmed",
                    exchange=self.exchange_name,
                    channel=message.channel,
                    symbol=str(message.symbol) if message.symbol else None
                )
                
            elif message.message_type == MessageType.ERROR:
                self.logger.error(
                    "WebSocket error message received",
                    exchange=self.exchange_name,
                    channel=message.channel,
                    error_data=message.raw_data
                )
                
            else:
                self.logger.debug(
                    "Unhandled message type",
                    exchange=self.exchange_name,
                    message_type=message.message_type,
                    channel=message.channel
                )
                
        except Exception as e:
            self.logger.error(
                "Error handling parsed message",
                exchange=self.exchange_name,
                message_type=message.message_type,
                error_type=type(e).__name__,
                error_message=str(e)
            )
        finally:
            # Track processing time using shared performance tracker
            processing_time = time.perf_counter() - start_time
            
            # Record processing time with message type-specific tracking
            if message.message_type == MessageType.ORDERBOOK:
                self._performance_tracker.record_orderbook_update(processing_time)
            elif message.message_type == MessageType.TRADES:
                self._performance_tracker.record_trade_update(processing_time)
            elif message.message_type == MessageType.BOOK_TICKER:
                self._performance_tracker.record_book_ticker_update(processing_time)
            elif message.message_type == MessageType.TICKER:
                self._performance_tracker.record_ticker_update(processing_time)
            else:
                self._performance_tracker.record_message_processing_time(processing_time)
    
    async def _handle_state_change(self, state: ConnectionState) -> None:
        """
        Handle connection state changes.
        
        Args:
            state: New connection state
        """
        self.logger.info(
            "Public WebSocket state changed",
            exchange=self.exchange_name,
            new_state=state.value,
            active_symbols_count=len(self._active_symbols)
        )
        
        # Call external handler if provided
        if self.connection_handler:
            try:
                await self.connection_handler(state)
            except Exception as e:
                self.logger.error(
                    "Error in external connection handler",
                    exchange=self.exchange_name,
                    state=state.value,
                    error_type=type(e).__name__,
                    error_message=str(e)
                )