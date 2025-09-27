"""
Trading capability interface for high-frequency exchange operations.

This module defines the core trading capability that provides order management
functionality for both spot and futures exchanges. All implementations must
meet strict HFT performance requirements for professional trading operations.

## Performance Requirements

- **Order Placement**: <50ms end-to-end execution
- **Order Cancellation**: <30ms confirmation
- **Status Queries**: <20ms response time
- **WebSocket Priority**: Real-time updates for order status changes

## Design Principles

1. **Async-First**: All operations are async for non-blocking execution
2. **Error Recovery**: Automatic retry with exponential backoff
3. **Precision Handling**: Decimal precision for all price/quantity values
4. **State Tracking**: Local order state synchronized with WebSocket updates

## Integration Notes

This capability is typically composed with BalanceCapability for complete
trading functionality. For futures exchanges, it's also composed with
PositionCapability and LeverageCapability.

See also:
- capabilities-architecture.md for complete protocol design
- hft-requirements-compliance.md for performance specifications
- separated-domain-pattern.md for architectural context
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from exchanges.structs.common import Symbol, Order
from exchanges.structs.enums import OrderSide


class TradingCapability(ABC):
    """
    Core trading operations capability for HFT systems.
    
    Provides high-performance order management operations that are universal
    across both spot and futures exchanges. All methods follow strict latency
    requirements for professional trading operations.
    
    ## Capability Scope
    
    This capability provides:
    - Limit and market order placement
    - Order cancellation and modification
    - Order status tracking and history
    - Real-time order updates via WebSocket
    
    ## Implementation Requirements
    
    1. **Latency Targets**: All operations must meet HFT latency requirements
    2. **Error Handling**: Comprehensive error handling with typed exceptions
    3. **State Management**: Maintain local order cache synchronized with exchange
    4. **Logging**: Performance metrics logging for all operations
    
    ## Business Context
    
    In HFT arbitrage systems, order execution speed is critical:
    - Arbitrage opportunities exist for milliseconds
    - Slower execution means missed profits
    - Order cancellation speed prevents adverse selection
    - Status tracking enables risk management
    
    Example:
        ```python
        class MyExchange(CompositePrivateExchange, TradingCapability):
            async def place_limit_order(self, symbol, side, quantity, price, **kwargs):
                # Implementation with <50ms execution
                with LoggingTimer(self.logger, "place_limit_order"):
                    return await self._rest_client.create_order(...)
        ```
    """
    
    @abstractmethod
    async def place_limit_order(
        self, 
        symbol: Symbol, 
        side: OrderSide, 
        quantity: float, 
        price: float, 
        **kwargs
    ) -> Order:
        """
        Place a limit order.
        
        Args:
            symbol: Trading symbol
            side: Order side (BUY or SELL)
            quantity: Order quantity
            price: Limit price
            **kwargs: Exchange-specific parameters
            
        Returns:
            Order object with order details
            
        Raises:
            ExchangeError: If order placement fails
        """
        pass
    
    @abstractmethod
    async def place_market_order(
        self, 
        symbol: Symbol, 
        side: OrderSide, 
        quantity: float, 
        **kwargs
    ) -> Order:
        """
        Place a market order.
        
        Args:
            symbol: Trading symbol
            side: Order side (BUY or SELL)
            quantity: Order quantity
            **kwargs: Exchange-specific parameters
            
        Returns:
            Order object with order details
            
        Raises:
            ExchangeError: If order placement fails
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, symbol: Symbol, order_id: str) -> bool:
        """
        Cancel an existing order.
        
        Args:
            symbol: Trading symbol
            order_id: Exchange order ID to cancel
            
        Returns:
            True if cancellation successful, False otherwise
            
        Raises:
            ExchangeError: If cancellation fails
        """
        pass
    
    @abstractmethod
    async def get_order(self, symbol: Symbol, order_id: str) -> Order:
        """
        Get current status of an order.
        
        Args:
            symbol: Trading symbol
            order_id: Exchange order ID
            
        Returns:
            Order object with current status
            
        Raises:
            ExchangeError: If order not found or query fails
        """
        pass
    
    # @abstractmethod
    # async def get_order_history(
    #     self,
    #     symbol: Optional[Symbol] = None,
    #     limit: int = 100
    # ) -> List[Order]:
    #     """
    #     Get order history.
    #
    #     Args:
    #         symbol: Optional symbol filter
    #         limit: Maximum number of orders to return
    #
    #     Returns:
    #         List of historical orders
    #     """
    #     pass