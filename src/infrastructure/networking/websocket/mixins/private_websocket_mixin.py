"""
Private WebSocket Mixin

Provides common functionality for private WebSocket handlers that process
authenticated trading operations (orders, balances, positions) requiring credentials.

This mixin replaces the inheritance-based PrivateWebSocketHandler with a
composition-based approach for cleaner, more testable code.

Design Principles:
- Requires authentication/API keys
- Handles sensitive trading data (balances, orders, positions)
- High-frequency optimized for sub-millisecond processing
- Complete separation from public market data operations
- Implements trading safety and validation
- Composition over inheritance
"""

from typing import Any, Dict, List, Optional
from abc import ABC, abstractmethod

from infrastructure.logging import get_logger
from exchanges.structs.common import Symbol, Order, AssetBalance, Trade
from exchanges.structs.enums import OrderStatus

# Import WebSocketMessageType from the base module
from infrastructure.networking.websocket.message_types import WebSocketMessageType


class PrivateWebSocketMixin:
    """
    Mixin providing common private WebSocket functionality.
    
    Handles authenticated trading streams including:
    - Order updates (fills, cancellations, rejections)
    - Balance changes (deposits, withdrawals, trading impact)
    - Position updates (futures trading, margin changes)
    - Trade executions (user-specific trade events)
    
    Performance Requirements:
    - <30μs per order update for HFT compliance
    - <40μs per balance update processing
    - <50μs per position update handling
    - Zero allocation in hot paths where possible
    
    Security Requirements:
    - Validate all incoming authenticated messages
    - Ensure data integrity for trading operations
    - Implement proper error handling for failed operations
    
    Usage:
        class ExchangePrivateHandler(PrivateWebSocketMixin):
            def __init__(self, user_id=None):
                self.exchange_name = "exchange_name"
                self.setup_private_websocket(user_id)
                
            # Implement abstract methods...
    """
    
    def setup_private_websocket(self, user_id: Optional[str] = None):
        """
        Initialize private WebSocket mixin functionality.
        
        Args:
            user_id: User/account identifier for validation
            
        Call this from your handler's __init__ method.
        """
        # Initialize logger
        if not hasattr(self, 'logger'):
            self.logger = get_logger(f"websocket.private.{getattr(self, 'exchange_name', 'unknown')}")
        
        # Initialize state
        self.user_id = user_id
        self._order_callbacks: List[callable] = []
        self._balance_callbacks: List[callable] = []
        self._position_callbacks: List[callable] = []
        self._trade_callbacks: List[callable] = []
        self._authentication_status = False
        
        # Performance tracking
        self.message_count = 0
        self.is_connected = False
        
        self.logger.info("Private WebSocket mixin initialized",
                        exchange=getattr(self, 'exchange_name', 'unknown'),
                        user_id=user_id)
    
    # Abstract methods that implementing classes must provide
    async def _parse_order_update(self, raw_message: Any) -> Optional[Order]:
        """
        Parse order update message from exchange-specific format.
        
        Args:
            raw_message: Raw WebSocket message
            
        Returns:
            Order object or None if parsing failed
            
        Performance: Must complete in <30μs
        Security: Must validate order belongs to authenticated user
        """
        raise NotImplementedError("Subclass must implement _parse_order_update")
    
    async def _parse_balance_update(self, raw_message: Any) -> Optional[AssetBalance]:
        """
        Parse balance update message from exchange-specific format.
        
        Args:
            raw_message: Raw WebSocket message
            
        Returns:
            AssetBalance object or None if parsing failed
            
        Performance: Must complete in <40μs
        Security: Must validate balance belongs to authenticated user
        """
        raise NotImplementedError("Subclass must implement _parse_balance_update")
    
    async def _parse_position_update(self, raw_message: Any) -> Optional[Any]:
        """
        Parse position update message from exchange-specific format.
        
        Args:
            raw_message: Raw WebSocket message
            
        Returns:
            Position object or None if parsing failed
            
        Performance: Must complete in <50μs
        Security: Must validate position belongs to authenticated user
        """
        raise NotImplementedError("Subclass must implement _parse_position_update")
    
    async def _parse_trade_execution(self, raw_message: Any) -> Optional[Trade]:
        """
        Parse trade execution message from exchange-specific format.
        
        Args:
            raw_message: Raw WebSocket message
            
        Returns:
            Trade object or None if parsing failed
            
        Performance: Must complete in <35μs
        Security: Must validate trade belongs to authenticated user
        """
        # Default implementation - some exchanges may not have separate trade executions
        return None
    
    async def _detect_message_type(self, raw_message: Any) -> WebSocketMessageType:
        """
        Detect the type of incoming private message.
        
        Args:
            raw_message: Raw WebSocket message
            
        Returns:
            WebSocketMessageType enum value
            
        Performance: Must complete in <10μs
        """
        raise NotImplementedError("Subclass must implement _detect_message_type")
    
    async def _validate_authentication(self, raw_message: Any) -> bool:
        """
        Validate that the message is properly authenticated.
        
        Args:
            raw_message: Raw WebSocket message
            
        Returns:
            True if message is authenticated and valid
            
        Security: Critical for preventing unauthorized data access
        """
        raise NotImplementedError("Subclass must implement _validate_authentication")
    
    # Template method implementation
    async def _handle_message(self, raw_message: Any) -> None:
        """
        Handle incoming private WebSocket message.
        
        This method implements the template pattern by:
        1. Validating authentication
        2. Detecting message type
        3. Routing to appropriate parser
        4. Calling registered callbacks
        5. Updating internal state
        
        Args:
            raw_message: Raw WebSocket message
        """
        try:
            self.message_count += 1
            
            # Critical: Validate authentication first
            if not await self._validate_authentication(raw_message):
                self.logger.warning("Received unauthenticated message, ignoring")
                return
            
            # Fast message type detection
            message_type = await self._detect_message_type(raw_message)
            
            # Route to appropriate handler based on type
            if message_type == WebSocketMessageType.ORDER_UPDATE:
                order = await self._parse_order_update(raw_message)
                if order:
                    await self._on_order_update(order)
                    await self._notify_order_callbacks(order)
            
            elif message_type == WebSocketMessageType.BALANCE_UPDATE:
                balance = await self._parse_balance_update(raw_message)
                if balance:
                    await self._on_balance_update(balance)
                    await self._notify_balance_callbacks(balance)
            
            elif message_type == WebSocketMessageType.POSITION_UPDATE:
                position = await self._parse_position_update(raw_message)
                if position:
                    await self._on_position_update(position)
                    await self._notify_position_callbacks(position)
            
            elif message_type == WebSocketMessageType.TRADE:
                trade = await self._parse_trade_execution(raw_message)
                if trade:
                    await self._on_trade_execution(trade)
                    await self._notify_trade_callbacks(trade)
            
            elif message_type == WebSocketMessageType.PING:
                await self._handle_ping(raw_message)
            
            elif message_type == WebSocketMessageType.SUBSCRIBE:
                await self._handle_subscription(raw_message)
            
            elif message_type == WebSocketMessageType.ERROR:
                await self._handle_exchange_error(raw_message)
            
            else:
                self.logger.warning(f"Unknown private message type: {message_type}")
                
        except Exception as e:
            await self._handle_error(raw_message, e)
    
    # Trading operation handlers
    async def _on_order_update(self, order: Order) -> None:
        """
        Handle order update with trading safety validation.
        
        Args:
            order: Updated order object
        """
        # Validate order data integrity
        if not self._validate_order_data(order):
            self.logger.error(f"Invalid order data received: {order}")
            return
        
        # Log critical order events
        if order.status == OrderStatus.FILLED:
            self.logger.info(f"Order filled: {order.order_id} - {order.quantity} @ {order.price}")
        elif order.status == OrderStatus.CANCELED:
            self.logger.info(f"Order cancelled: {order.order_id}")
        elif order.status == OrderStatus.REJECTED:
            self.logger.warning(f"Order rejected: {order.order_id}")
    
    async def _on_balance_update(self, balance: AssetBalance) -> None:
        """
        Handle balance update with validation.
        
        Args:
            balance: Updated balance object
        """
        # Validate balance data
        if not self._validate_balance_data(balance):
            self.logger.error(f"Invalid balance data received: {balance}")
            return
        
        self.logger.debug(f"Balance updated: {balance.asset} = {balance.available}")
    
    async def _on_position_update(self, position: Any) -> None:
        """
        Handle position update with validation.
        
        Args:
            position: Updated position object
        """
        # Validate position data
        if not self._validate_position_data(position):
            self.logger.error(f"Invalid position data received: {position}")
            return
        
        self.logger.debug(f"Position updated: {position}")
    
    async def _on_trade_execution(self, trade: Trade) -> None:
        """
        Handle trade execution event.
        
        Args:
            trade: Executed trade object
        """
        self.logger.debug(f"Trade executed: {trade.symbol} - {trade.quantity} @ {trade.price}")
    
    # Data validation methods
    def _validate_order_data(self, order: Order) -> bool:
        """
        Validate order data integrity.
        
        Args:
            order: Order object to validate
            
        Returns:
            True if order data is valid
        """
        if not order.order_id:
            return False
        if order.quantity and order.quantity <= 0:
            return False
        if order.price and order.price <= 0:
            return False
        return True
    
    def _validate_balance_data(self, balance: AssetBalance) -> bool:
        """
        Validate balance data integrity.
        
        Args:
            balance: AssetBalance object to validate
            
        Returns:
            True if balance data is valid
        """
        if not balance.asset:
            return False
        if balance.available < 0:
            return False
        if balance.locked < 0:
            return False
        return True
    
    def _validate_position_data(self, position: Any) -> bool:
        """
        Validate position data integrity.
        
        Args:
            position: Position object to validate
            
        Returns:
            True if position data is valid
        """
        if not position:
            return False
        # Position validation depends on exchange-specific structure
        # Default implementation accepts any non-None position
        return True
    
    # Callback management for external consumers
    def add_order_callback(self, callback: callable) -> None:
        """Add callback for order updates."""
        self._order_callbacks.append(callback)
    
    def add_balance_callback(self, callback: callable) -> None:
        """Add callback for balance updates."""
        self._balance_callbacks.append(callback)
    
    def add_position_callback(self, callback: callable) -> None:
        """Add callback for position updates."""
        self._position_callbacks.append(callback)
    
    def add_trade_callback(self, callback: callable) -> None:
        """Add callback for trade executions."""
        self._trade_callbacks.append(callback)
    
    # Internal callback notification
    async def _notify_order_callbacks(self, order: Order) -> None:
        """Notify all registered order callbacks."""
        for callback in self._order_callbacks:
            try:
                await callback(order)
            except Exception as e:
                self.logger.error(f"Error in order callback: {e}")
    
    async def _notify_balance_callbacks(self, balance: AssetBalance) -> None:
        """Notify all registered balance callbacks."""
        for callback in self._balance_callbacks:
            try:
                await callback(balance)
            except Exception as e:
                self.logger.error(f"Error in balance callback: {e}")
    
    async def _notify_position_callbacks(self, position: Any) -> None:
        """Notify all registered position callbacks."""
        for callback in self._position_callbacks:
            try:
                await callback(position)
            except Exception as e:
                self.logger.error(f"Error in position callback: {e}")
    
    async def _notify_trade_callbacks(self, trade: Trade) -> None:
        """Notify all registered trade callbacks."""
        for callback in self._trade_callbacks:
            try:
                await callback(trade)
            except Exception as e:
                self.logger.error(f"Error in trade callback: {e}")
    
    # Protocol-specific handlers (can be overridden)
    async def _handle_ping(self, raw_message: Any) -> None:
        """Handle ping messages (exchange-specific implementation)."""
        pass
    
    async def _handle_subscription(self, raw_message: Any) -> None:
        """Handle subscription confirmation messages."""
        pass
    
    async def _handle_exchange_error(self, raw_message: Any) -> None:
        """Handle exchange error messages."""
        self.logger.error(f"Exchange error received: {raw_message}")
    
    async def _handle_error(self, raw_message: Any, error: Exception) -> None:
        """Handle processing errors."""
        self.logger.error(f"Error processing private message: {error}",
                         message_preview=str(raw_message)[:100])
    
    # Authentication management
    def set_authentication_status(self, status: bool) -> None:
        """Set authentication status."""
        self._authentication_status = status
        exchange_name = getattr(self, 'exchange_name', 'unknown')
        if status:
            self.logger.info(f"Authentication established for {exchange_name}")
        else:
            self.logger.warning(f"Authentication lost for {exchange_name}")
    
    @property
    def is_authenticated(self) -> bool:
        """Check if handler is authenticated."""
        return getattr(self, '_authentication_status', False)
    
    # Health monitoring
    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status of the private handler."""
        return {
            "is_connected": getattr(self, 'is_connected', False),
            "is_authenticated": self.is_authenticated,
            "message_count": getattr(self, 'message_count', 0),
            "user_id": getattr(self, 'user_id', None),
            "active_callbacks": {
                "order": len(getattr(self, '_order_callbacks', [])),
                "balance": len(getattr(self, '_balance_callbacks', [])),
                "position": len(getattr(self, '_position_callbacks', [])),
                "trade": len(getattr(self, '_trade_callbacks', []))
            },
            "type": "private",
            "mixin_version": "1.0.0"
        }