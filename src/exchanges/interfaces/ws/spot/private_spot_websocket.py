"""
PrivateSpotWebsocket - Concrete Implementation for Spot Private Trading Operations

Concrete implementation of BasePrivateWebsocket for spot trading operations.
Handles order updates, balance changes, trade executions, and other account data.

Architecture compliance:
- Inherits from BasePrivateWebsocket for domain separation
- Implements all abstract methods with spot-specific logic
- Uses WebSocket manager for connection handling
- Provides message routing to handlers
- Maintains HFT performance requirements
- No symbols parameter - subscribes to account streams
"""

import time
from typing import Dict, Optional, Callable, Awaitable, Union, List

from infrastructure.networking.websocket.structs import ConnectionState, MessageType, ParsedMessage
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
from infrastructure.networking.websocket.utils import create_websocket_manager
from config.structs import ExchangeConfig
from infrastructure.logging import HFTLoggerInterface, LoggingTimer
from infrastructure.exceptions.unified import UnifiedConnectionError, UnifiedValidationError

from ..base_private_websocket import BasePrivateWebsocket
from ..performance_tracker import PrivateWebSocketPerformanceTracker
from ..constants import PerformanceConstants


class PrivateSpotWebsocket(BasePrivateWebsocket):
    """
    Concrete implementation of private WebSocket for spot trading operations.
    
    Provides complete trading functionality including:
    - Order status updates and executions
    - Account balance changes
    - Trade execution notifications
    - Position updates (for margin accounts)
    
    HFT Optimized:
    - Sub-millisecond message processing
    - Zero-copy message routing
    - Efficient authentication handling
    - Performance metrics tracking
    
    Domain Separation:
    - No symbols parameter - account streams only
    - Authentication required for all operations
    - Complete isolation from public market data
    """
    
    def __init__(
        self,
        config: ExchangeConfig,
        handlers: PrivateWebsocketHandlers,
        logger: HFTLoggerInterface,
        connection_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None
    ) -> None:
        """
        Initialize concrete private spot WebSocket implementation.
        
        Args:
            config: Exchange configuration with authentication credentials
            handlers: Private WebSocket message handlers for trading data
            logger: HFT logger for sub-millisecond performance tracking
            connection_handler: Optional callback for connection state changes
        """
        # Initialize base class with validation
        super().__init__(config, handlers, logger, connection_handler)
        
        # Create WebSocket manager using dependency injection for private operations
        self._ws_manager = create_websocket_manager(
            exchange_config=config,
            is_private=True,  # Private operations require authentication
            message_handler=self._handle_parsed_message,
            state_change_handler=self._handle_state_change,
            logger=logger
        )
        
        # Performance tracking using shared utility
        self._performance_tracker = PrivateWebSocketPerformanceTracker(
            exchange_name=self.exchange_name,
            logger=logger,
            ring_buffer_size=PerformanceConstants.DEFAULT_RING_BUFFER_SIZE
        )
        
        self.logger.info(
            "Initialized private spot WebSocket",
            exchange=self.exchange_name,
            implementation="concrete_spot",
            authentication_ready=self._has_authentication_credentials()
        )
    
    async def initialize(self) -> None:
        """
        Initialize private WebSocket connection.
        
        No symbols parameter - subscribes to account streams automatically.
        Handles authentication and establishes trading data streams.
        
        Raises:
            UnifiedConnectionError: If connection fails
            UnifiedValidationError: If authentication fails
        """
        try:
            with LoggingTimer(self.logger, "private_ws_initialization") as timer:
                # Track connection start time
                self._performance_tracker.start_connection_tracking()
                
                # Initialize WebSocket manager without symbols (account streams)
                await self._ws_manager.initialize()
                
                # Mark as authenticated after successful initialization
                self._mark_authenticated()
            
            self.logger.info(
                "Private WebSocket initialized successfully",
                exchange=self.exchange_name,
                authenticated=self._is_authenticated,
                initialization_time_ms=timer.elapsed_ms
            )
            
        except Exception as e:
            error_msg = f"Failed to initialize private WebSocket: {str(e)}"
            self.logger.error(
                error_msg,
                exchange=self.exchange_name,
                error_type=type(e).__name__
            )
            
            # Mark as unauthenticated on failure
            self._mark_unauthenticated()
            
            if "auth" in str(e).lower() or "credential" in str(e).lower():
                raise UnifiedValidationError(self.exchange_name, error_msg)
            else:
                raise UnifiedConnectionError(self.exchange_name, error_msg)
    
    async def close(self) -> None:
        """
        Close WebSocket connection and clean up resources.
        
        Raises:
            ConnectionError: If close operation fails
        """
        try:
            with LoggingTimer(self.logger, "private_ws_close") as timer:
                await self._ws_manager.close()
                self._mark_unauthenticated()
            
            self.logger.info(
                "Private WebSocket closed successfully",
                exchange=self.exchange_name,
                close_time_ms=timer.elapsed_ms
            )
            
        except Exception as e:
            error_msg = f"Error closing private WebSocket: {str(e)}"
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
    
    def is_authenticated(self) -> bool:
        """
        Check authentication status.
        
        Returns:
            True if WebSocket is authenticated for trading operations, False otherwise
        """
        return self._is_authenticated and self.is_connected()
    
    def get_performance_metrics(self) -> Dict[str, Union[int, float, str]]:
        """
        Get HFT performance metrics for monitoring.
        
        Returns:
            Dictionary containing performance metrics
        """
        base_metrics = self._ws_manager.get_performance_metrics()
        
        # Get metrics from performance tracker with additional context
        additional_metrics = {
            "authentication_status": "authenticated" if self.is_authenticated() else "unauthenticated",
            "domain": "trading_operations"
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
            # Route based on message type for trading operations
            if message.message_type == MessageType.ORDER:
                if message.data:
                    await self.handlers.handle_order(message.data)
                    
            elif message.message_type == MessageType.BALANCE:
                if message.data:
                    await self.handlers.handle_balance(message.data)
                    
            elif message.message_type == MessageType.TRADE:
                if message.data:
                    await self.handlers.handle_execution(message.data)
                    
            elif message.message_type == MessageType.SUBSCRIPTION_CONFIRM:
                self.logger.debug(
                    "Private subscription confirmed",
                    exchange=self.exchange_name,
                    channel=message.channel
                )
                
            elif message.message_type == MessageType.HEARTBEAT:
                self.logger.debug(
                    "Private heartbeat received",
                    exchange=self.exchange_name
                )
                
            elif message.message_type == MessageType.ERROR:
                self.logger.error(
                    "Private WebSocket error message received",
                    exchange=self.exchange_name,
                    channel=message.channel,
                    error_data=message.raw_data
                )
                
                # Check if authentication was lost
                if "auth" in str(message.raw_data).lower():
                    self._mark_unauthenticated()
                
            else:
                self.logger.debug(
                    "Unhandled private message type",
                    exchange=self.exchange_name,
                    message_type=message.message_type,
                    channel=message.channel
                )
                
        except Exception as e:
            self.logger.error(
                "Error handling parsed private message",
                exchange=self.exchange_name,
                message_type=message.message_type,
                error_type=type(e).__name__,
                error_message=str(e)
            )
        finally:
            # Track processing time using shared performance tracker
            processing_time = time.perf_counter() - start_time
            
            # Record processing time with message type-specific tracking
            if message.message_type == MessageType.ORDER:
                self._performance_tracker.record_order_update(processing_time)
            elif message.message_type == MessageType.BALANCE:
                self._performance_tracker.record_balance_update(processing_time)
            elif message.message_type == MessageType.TRADE:
                self._performance_tracker.record_execution_update(processing_time)
            else:
                self._performance_tracker.record_message_processing_time(processing_time)
    
    async def _handle_state_change(self, state: ConnectionState) -> None:
        """
        Handle connection state changes.
        
        Args:
            state: New connection state
        """
        self.logger.info(
            "Private WebSocket state changed",
            exchange=self.exchange_name,
            new_state=state.value,
            authenticated=self._is_authenticated
        )
        
        # Update authentication status based on connection state
        if state == ConnectionState.DISCONNECTED or state == ConnectionState.ERROR:
            self._mark_unauthenticated()
        elif state == ConnectionState.CONNECTED and self._has_authentication_credentials():
            # Authentication will be verified during message flow
            pass
        
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