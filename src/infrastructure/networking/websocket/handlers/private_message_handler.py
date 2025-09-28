"""
PrivateMessageHandler - Specialized Handler for Private Trading Messages

Specialized message handler for private WebSocket messages including order updates,
position changes, balance updates, and execution reports. Extends BaseMessageHandler
with private trading operations specific routing and processing.

Key Features:
- Specialized routing for private message types (orders, positions, balances)
- Integration with PrivateWebSocketMixin callback system
- Performance optimized for trading operations
- Authentication-aware message handling
- HFT optimized: <10μs order updates, <10μs position updates, <5μs balance updates

HFT COMPLIANCE: Sub-millisecond processing for all trading operations.
"""

import asyncio
from typing import Any, Dict, List, Optional, Callable, Awaitable

from .base_message_handler import BaseMessageHandler
from infrastructure.networking.websocket.message_types import WebSocketMessageType
from infrastructure.networking.websocket.mixins import PrivateWebSocketMixin
from infrastructure.logging import get_logger


class PrivateMessageHandler(BaseMessageHandler, PrivateWebSocketMixin):
    """
    Specialized handler for private trading messages.
    
    Extends BaseMessageHandler with private-specific message routing and
    integrates with PrivateWebSocketMixin for callback management. Handles
    order updates, position changes, balance updates, and execution reports.
    
    Message Types Handled:
    - ORDER_UPDATE: Order status changes (new, filled, cancelled)
    - POSITION_UPDATE: Position changes (size, entry price, PnL)
    - BALANCE_UPDATE: Account balance changes
    - EXECUTION_REPORT: Trade execution reports
    - AUTH_RESPONSE: Authentication confirmation/rejection
    - ERROR: Error messages specific to private operations
    
    Performance Specifications:
    - Order update routing: <5μs, processing <10μs
    - Position update routing: <5μs, processing <10μs  
    - Balance update routing: <3μs, processing <5μs
    """
    
    def __init__(self, exchange_name: str, logger=None):
        """
        Initialize private message handler.
        
        Args:
            exchange_name: Name of the exchange for logging and metrics
            logger: Optional logger instance for dependency injection
        """
        # Initialize both parent classes
        BaseMessageHandler.__init__(self, exchange_name, logger)
        PrivateWebSocketMixin.__init__(self)
        
        # Private-specific performance targets (in microseconds)
        self.order_routing_target_us = 5
        self.position_routing_target_us = 5
        self.balance_routing_target_us = 3
        self.execution_routing_target_us = 5
        
        # Message-specific metrics
        self.order_update_count = 0
        self.position_update_count = 0
        self.balance_update_count = 0
        self.execution_report_count = 0
        self.auth_response_count = 0
        self.private_error_count = 0
        
        # Authentication state
        self._is_authenticated = False
        
        self.logger.info(f"PrivateMessageHandler initialized for {exchange_name}",
                        exchange=exchange_name,
                        handler_type="private",
                        authentication_required=True,
                        performance_tracking=True)
    
    async def _route_message(self, message_type: WebSocketMessageType, raw_message: Any) -> None:
        """
        Route private messages to appropriate parsers and callbacks.
        
        Performance-optimized routing for private trading data with specialized
        handling for each message type. Integrates with PrivateWebSocketMixin
        callback system for trading event distribution.
        
        Args:
            message_type: Detected message type
            raw_message: Raw message from WebSocket
            
        Raises:
            ValueError: If message type is not supported for private handler
        """
        if message_type == WebSocketMessageType.ORDER_UPDATE:
            await self._handle_order_update_message(raw_message)
            
        elif message_type == WebSocketMessageType.POSITION_UPDATE:
            await self._handle_position_update_message(raw_message)
            
        elif message_type == WebSocketMessageType.BALANCE_UPDATE:
            await self._handle_balance_update_message(raw_message)
            
        elif message_type == WebSocketMessageType.EXECUTION_REPORT:
            await self._handle_execution_report_message(raw_message)
            
        elif message_type == WebSocketMessageType.AUTH_RESPONSE:
            await self._handle_auth_response_message(raw_message)
            
        elif message_type == WebSocketMessageType.ERROR:
            await self._handle_private_error_message(raw_message)
            
        elif message_type == WebSocketMessageType.PING:
            # Handle ping messages even in private handler
            await self._handle_ping_message(raw_message)
            
        else:
            # Track unsupported message types
            self.logger.warning("Unsupported message type in private handler",
                              message_type=str(message_type),
                              exchange=self.exchange_name)
            
            self.logger.metric("ws_private_handler_unsupported_message", 1,
                             tags={"exchange": self.exchange_name, 
                                   "message_type": str(message_type)})
            
            raise ValueError(f"Unsupported message type for private handler: {message_type}")
    
    # Message-specific handlers
    
    async def _handle_order_update_message(self, raw_message: Any) -> None:
        """
        Handle order update messages.
        
        Parses order status changes and triggers registered callbacks through
        PrivateWebSocketMixin. Critical for HFT trading operations.
        
        Args:
            raw_message: Raw order update message
        """
        self.order_update_count += 1
        
        try:
            # Parse order update using exchange-specific implementation
            order_update = await self._parse_order_update(raw_message)
            
            if order_update:
                # Trigger callbacks through PrivateWebSocketMixin
                await self._notify_order_callbacks(order_update)
                
                self.logger.debug("Order update processed",
                                exchange=self.exchange_name,
                                order_id=getattr(order_update, 'order_id', 'unknown'),
                                status=getattr(order_update, 'status', 'unknown'),
                                symbol=str(getattr(order_update, 'symbol', 'unknown')))
                
                # Track order status changes for monitoring
                status = getattr(order_update, 'status', 'unknown')
                self.logger.metric("ws_private_handler_order_updates", 1,
                                 tags={"exchange": self.exchange_name, "status": str(status)})
            else:
                self.logger.warning("Order update parsing returned None",
                                  exchange=self.exchange_name)
                
        except Exception as e:
            self.logger.error("Error processing order update message",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            exchange=self.exchange_name)
            
            self.logger.metric("ws_private_handler_order_errors", 1,
                             tags={"exchange": self.exchange_name})
            raise
    
    async def _handle_position_update_message(self, raw_message: Any) -> None:
        """
        Handle position update messages.
        
        Parses position changes and triggers registered callbacks through
        PrivateWebSocketMixin. Important for portfolio tracking and risk management.
        
        Args:
            raw_message: Raw position update message
        """
        self.position_update_count += 1
        
        try:
            # Parse position update using exchange-specific implementation
            position_update = await self._parse_position_update(raw_message)
            
            if position_update:
                # Trigger callbacks through PrivateWebSocketMixin
                await self._notify_position_callbacks(position_update)
                
                self.logger.debug("Position update processed",
                                exchange=self.exchange_name,
                                symbol=str(getattr(position_update, 'symbol', 'unknown')),
                                size=getattr(position_update, 'size', 0),
                                side=getattr(position_update, 'side', 'unknown'))
                
                # Track position changes for monitoring
                self.logger.metric("ws_private_handler_position_updates", 1,
                                 tags={"exchange": self.exchange_name})
            else:
                self.logger.warning("Position update parsing returned None",
                                  exchange=self.exchange_name)
                
        except Exception as e:
            self.logger.error("Error processing position update message",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            exchange=self.exchange_name)
            
            self.logger.metric("ws_private_handler_position_errors", 1,
                             tags={"exchange": self.exchange_name})
            raise
    
    async def _handle_balance_update_message(self, raw_message: Any) -> None:
        """
        Handle balance update messages.
        
        Parses account balance changes and triggers registered callbacks through
        PrivateWebSocketMixin. Critical for margin and risk management.
        
        Args:
            raw_message: Raw balance update message
        """
        self.balance_update_count += 1
        
        try:
            # Parse balance update using exchange-specific implementation
            balance_update = await self._parse_balance_update(raw_message)
            
            if balance_update:
                # Trigger callbacks through PrivateWebSocketMixin
                await self._notify_balance_callbacks(balance_update)
                
                self.logger.debug("Balance update processed",
                                exchange=self.exchange_name,
                                asset=getattr(balance_update, 'asset', 'unknown'),
                                balance=getattr(balance_update, 'balance', 0))
                
                # Track balance changes for monitoring
                self.logger.metric("ws_private_handler_balance_updates", 1,
                                 tags={"exchange": self.exchange_name})
            else:
                self.logger.warning("Balance update parsing returned None",
                                  exchange=self.exchange_name)
                
        except Exception as e:
            self.logger.error("Error processing balance update message",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            exchange=self.exchange_name)
            
            self.logger.metric("ws_private_handler_balance_errors", 1,
                             tags={"exchange": self.exchange_name})
            raise
    
    async def _handle_execution_report_message(self, raw_message: Any) -> None:
        """
        Handle execution report messages.
        
        Parses trade execution reports and triggers registered callbacks through
        PrivateWebSocketMixin. Critical for trade confirmation and settlement.
        
        Args:
            raw_message: Raw execution report message
        """
        self.execution_report_count += 1
        
        try:
            # Parse execution report using exchange-specific implementation
            execution_report = await self._parse_execution_report(raw_message)
            
            if execution_report:
                # Trigger callbacks through PrivateWebSocketMixin
                await self._notify_execution_callbacks(execution_report)
                
                self.logger.debug("Execution report processed",
                                exchange=self.exchange_name,
                                trade_id=getattr(execution_report, 'trade_id', 'unknown'),
                                symbol=str(getattr(execution_report, 'symbol', 'unknown')),
                                quantity=getattr(execution_report, 'quantity', 0))
                
                # Track executions for monitoring
                self.logger.metric("ws_private_handler_executions", 1,
                                 tags={"exchange": self.exchange_name})
            else:
                self.logger.warning("Execution report parsing returned None",
                                  exchange=self.exchange_name)
                
        except Exception as e:
            self.logger.error("Error processing execution report message",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            exchange=self.exchange_name)
            
            self.logger.metric("ws_private_handler_execution_errors", 1,
                             tags={"exchange": self.exchange_name})
            raise
    
    async def _handle_auth_response_message(self, raw_message: Any) -> None:
        """
        Handle authentication response messages.
        
        Processes authentication confirmations/rejections and updates
        authentication state.
        
        Args:
            raw_message: Raw authentication response message
        """
        self.auth_response_count += 1
        
        try:
            # Parse authentication response
            auth_result = await self._parse_auth_response(raw_message)
            
            if auth_result:
                success = auth_result.get('success', False)
                self._is_authenticated = success
                
                if success:
                    self.logger.info("Authentication successful",
                                   exchange=self.exchange_name)
                    self.logger.metric("ws_private_handler_auth_success", 1,
                                     tags={"exchange": self.exchange_name})
                else:
                    error_msg = auth_result.get('error', 'Unknown error')
                    self.logger.error("Authentication failed",
                                    exchange=self.exchange_name,
                                    error=error_msg)
                    self.logger.metric("ws_private_handler_auth_failure", 1,
                                     tags={"exchange": self.exchange_name})
            
        except Exception as e:
            self.logger.error("Error processing authentication response",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            exchange=self.exchange_name)
    
    async def _handle_private_error_message(self, raw_message: Any) -> None:
        """
        Handle error messages specific to private operations.
        
        Processes private operation errors and logs appropriate warnings.
        
        Args:
            raw_message: Raw error message
        """
        self.private_error_count += 1
        
        try:
            # Parse error message
            error_info = await self._parse_private_error_message(raw_message)
            
            self.logger.warning("Private operation error received",
                              exchange=self.exchange_name,
                              error_info=error_info)
            
            self.logger.metric("ws_private_handler_exchange_errors", 1,
                             tags={"exchange": self.exchange_name})
            
        except Exception as e:
            self.logger.error("Error processing private error message",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            exchange=self.exchange_name)
    
    async def _handle_ping_message(self, raw_message: Any) -> None:
        """
        Handle ping messages in private context.
        
        Args:
            raw_message: Raw ping message
        """
        try:
            # Handle ping (implementation depends on exchange)
            self.logger.debug("Ping message handled in private context",
                            exchange=self.exchange_name)
            
        except Exception as e:
            self.logger.error("Error handling ping in private context",
                            error_type=type(e).__name__,
                            error_message=str(e),
                            exchange=self.exchange_name)
    
    # Abstract methods that exchanges must implement
    
    async def _parse_order_update(self, raw_message: Any) -> Optional[Dict[str, Any]]:
        """
        Parse order update from raw message.
        
        Exchange-specific implementation must parse the raw message into
        a structured order update. Performance target: <10μs processing.
        
        Args:
            raw_message: Raw order update message
            
        Returns:
            Order update dict or None if parsing failed
        """
        # Default implementation - exchanges should override
        self.logger.warning("Using default order update parser - should be overridden",
                          exchange=self.exchange_name)
        return None
    
    async def _parse_position_update(self, raw_message: Any) -> Optional[Dict[str, Any]]:
        """
        Parse position update from raw message.
        
        Exchange-specific implementation must parse the raw message into
        a structured position update. Performance target: <10μs processing.
        
        Args:
            raw_message: Raw position update message
            
        Returns:
            Position update dict or None if parsing failed
        """
        # Default implementation - exchanges should override
        self.logger.warning("Using default position update parser - should be overridden",
                          exchange=self.exchange_name)
        return None
    
    async def _parse_balance_update(self, raw_message: Any) -> Optional[Dict[str, Any]]:
        """
        Parse balance update from raw message.
        
        Exchange-specific implementation must parse the raw message into
        a structured balance update. Performance target: <5μs processing.
        
        Args:
            raw_message: Raw balance update message
            
        Returns:
            Balance update dict or None if parsing failed
        """
        # Default implementation - exchanges should override
        self.logger.warning("Using default balance update parser - should be overridden",
                          exchange=self.exchange_name)
        return None
    
    async def _parse_execution_report(self, raw_message: Any) -> Optional[Dict[str, Any]]:
        """
        Parse execution report from raw message.
        
        Exchange-specific implementation must parse the raw message into
        a structured execution report. Performance target: <10μs processing.
        
        Args:
            raw_message: Raw execution report message
            
        Returns:
            Execution report dict or None if parsing failed
        """
        # Default implementation - exchanges should override
        self.logger.warning("Using default execution report parser - should be overridden",
                          exchange=self.exchange_name)
        return None
    
    async def _parse_auth_response(self, raw_message: Any) -> Optional[Dict[str, Any]]:
        """
        Parse authentication response from raw message.
        
        Exchange-specific implementation should parse the raw message into
        a structured auth response.
        
        Args:
            raw_message: Raw authentication response message
            
        Returns:
            Dict with 'success' boolean and optional 'error' message
        """
        # Default implementation
        return {"success": True}
    
    async def _parse_private_error_message(self, raw_message: Any) -> Dict[str, Any]:
        """
        Parse private error message from raw message.
        
        Exchange-specific implementation should parse the raw message into
        a structured error format.
        
        Args:
            raw_message: Raw error message
            
        Returns:
            Dictionary with error information
        """
        # Default implementation
        return {"raw_error": str(raw_message)}
    
    # Callback notification methods (delegated to PrivateWebSocketMixin)
    
    async def _notify_order_callbacks(self, order_update: Dict[str, Any]) -> None:
        """Notify registered order update callbacks."""
        if hasattr(self, 'order_callbacks') and self.order_callbacks:
            await asyncio.gather(*[
                callback(order_update) for callback in self.order_callbacks
            ], return_exceptions=True)
    
    async def _notify_position_callbacks(self, position_update: Dict[str, Any]) -> None:
        """Notify registered position update callbacks."""
        if hasattr(self, 'position_callbacks') and self.position_callbacks:
            await asyncio.gather(*[
                callback(position_update) for callback in self.position_callbacks
            ], return_exceptions=True)
    
    async def _notify_balance_callbacks(self, balance_update: Dict[str, Any]) -> None:
        """Notify registered balance update callbacks."""
        if hasattr(self, 'balance_callbacks') and self.balance_callbacks:
            await asyncio.gather(*[
                callback(balance_update) for callback in self.balance_callbacks
            ], return_exceptions=True)
    
    async def _notify_execution_callbacks(self, execution_report: Dict[str, Any]) -> None:
        """Notify registered execution report callbacks."""
        if hasattr(self, 'execution_callbacks') and self.execution_callbacks:
            await asyncio.gather(*[
                callback(execution_report) for callback in self.execution_callbacks
            ], return_exceptions=True)
    
    # Authentication state management
    
    def is_authenticated(self) -> bool:
        """
        Check if handler is authenticated for private operations.
        
        Returns:
            True if authenticated
        """
        return self._is_authenticated
    
    def set_authenticated(self, authenticated: bool) -> None:
        """
        Set authentication state.
        
        Args:
            authenticated: New authentication state
        """
        self._is_authenticated = authenticated
        self.logger.info("Authentication state changed",
                        exchange=self.exchange_name,
                        authenticated=authenticated)
    
    # Performance metrics override
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics including private-specific statistics.
        
        Returns:
            Dictionary with performance and message statistics
        """
        base_metrics = super().get_performance_metrics()
        
        # Add private-specific metrics
        base_metrics.update({
            'handler_type': 'private',
            'authentication_status': self._is_authenticated,
            'message_breakdown': {
                'order_update_count': self.order_update_count,
                'position_update_count': self.position_update_count,
                'balance_update_count': self.balance_update_count,
                'execution_report_count': self.execution_report_count,
                'auth_response_count': self.auth_response_count,
                'private_error_count': self.private_error_count
            },
            'callback_counts': {
                'order_callbacks': len(self.order_callbacks) if hasattr(self, 'order_callbacks') else 0,
                'position_callbacks': len(self.position_callbacks) if hasattr(self, 'position_callbacks') else 0,
                'balance_callbacks': len(self.balance_callbacks) if hasattr(self, 'balance_callbacks') else 0,
                'execution_callbacks': len(self.execution_callbacks) if hasattr(self, 'execution_callbacks') else 0
            }
        })
        
        return base_metrics