"""
Trading capability interface for exchange operations.

Universal capability available for both spot and futures exchanges.
Provides core order management functionality.

HFT COMPLIANT: Sub-50ms order execution requirements.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from exchanges.structs.common import Symbol, Order
from exchanges.structs.enums import OrderSide


class TradingCapability(ABC):
    """
    Core trading operations capability.
    
    Available for both spot and futures exchanges.
    Provides order placement, cancellation, and status tracking.
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
    async def get_order_status(self, symbol: Symbol, order_id: str) -> Order:
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
    
    @abstractmethod
    async def get_order_history(
        self,
        symbol: Optional[Symbol] = None,
        limit: int = 100
    ) -> List[Order]:
        """
        Get order history.

        Args:
            symbol: Optional symbol filter
            limit: Maximum number of orders to return

        Returns:
            List of historical orders
        """
        pass