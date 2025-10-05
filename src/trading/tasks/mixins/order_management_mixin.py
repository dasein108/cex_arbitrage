"""Order Management Mixin for Trading Tasks.

Provides reusable order management operations that eliminate code duplication
across trading tasks while maintaining HFT performance requirements.
"""
from typing import Optional
from abc import ABC

from exchanges.dual_exchange import DualExchange
from exchanges.structs import Order, Symbol, SymbolInfo
from exchanges.structs.common import Side, TimeInForce
from infrastructure.logging import HFTLoggerInterface


class OrderManagementMixin(ABC):
    """Reusable order management operations for trading tasks.
    
    This mixin provides common order operations that are used across multiple
    trading task implementations. It follows HFT performance requirements and
    maintains proper error handling patterns.
    
    Required Attributes (must be provided by inheriting class):
        logger: HFTLoggerInterface - Logger instance for task operations
        _tag: str - Task identification tag for logging
    """
    
    # These attributes must be provided by the inheriting class
    logger: HFTLoggerInterface
    _tag: str
    
    async def cancel_order_safely(
        self, 
        exchange: DualExchange, 
        symbol: Symbol, 
        order_id: str,
        tag: str = ""
    ) -> Optional[Order]:
        """Safely cancel order with consistent error handling.
        
        Args:
            exchange: Exchange instance to cancel order on
            symbol: Trading symbol
            order_id: ID of order to cancel
            tag: Additional tag for logging (optional)
            
        Returns:
            Cancelled order if successful, None if failed
            
        Note:
            Follows HFT error handling pattern - logs errors but doesn't raise exceptions
            to prevent trading task interruption.
        """
        try:
            tag = tag or exchange.name
            order = await exchange.private.cancel_order(symbol, order_id)
            tag_str = f"{self._tag} {tag}".strip()
            self.logger.info(f"🛑 Cancelled order {tag_str}", order_id=order.order_id)
            return order
        except Exception as e:
            tag_str = f"{self._tag} {tag}".strip()
            self.logger.error(f"🚫 Failed to cancel order {tag_str}", error=str(e))
            return None
    
    def validate_order_size(self, symbol_info: SymbolInfo, quantity: float, price: float) -> float:
        """Validate and adjust order size to meet exchange minimums.
        
        Args:
            symbol_info: Symbol information with minimum requirements
            quantity: Requested order quantity
            price: Order price
            
        Returns:
            Adjusted quantity that meets exchange minimums
            
        Note:
            Adds small buffer (0.01) to ensure minimum is met due to floating point precision.
        """
        min_quote_qty = symbol_info.min_quote_quantity
        if quantity * price < min_quote_qty:
            return min_quote_qty / price + 0.01
        return quantity
    
    async def place_limit_order_safely(
        self,
        exchange: DualExchange,
        symbol: Symbol,
        side: Side,
        quantity: float,
        price: float,
        tag: str = ""
    ) -> Optional[Order]:
        """Place limit order with validation and error handling.
        
        Args:
            exchange: Exchange instance to place order on
            symbol: Trading symbol
            side: Order side (BUY/SELL)
            quantity: Order quantity
            price: Order price
            tag: Additional tag for logging (optional)
            
        Returns:
            Placed order if successful, None if failed
            
        Note:
            Automatically validates and adjusts quantity to meet exchange minimums.
            Uses GTC (Good Till Cancelled) time in force for HFT requirements.
        """
        try:
            symbol_info = exchange.public.symbols_info[symbol]
            adjusted_quantity = self.validate_order_size(symbol_info, quantity, price)
            
            order = await exchange.private.place_limit_order(
                symbol=symbol,
                side=side,
                quantity=adjusted_quantity,
                price=price,
            )
            
            tag_str = f"{self._tag} {tag}".strip()
            self.logger.info(f"📈 Placed {side.name} order {tag_str}", 
                           order_id=order.order_id, 
                           quantity=adjusted_quantity, 
                           price=price)
            return order
            
        except Exception as e:
            tag_str = f"{self._tag} {tag}".strip()
            self.logger.error(f"🚫 Failed to place order {tag_str}", error=str(e))
            return None
    
    def get_minimum_order_quantity(self, symbol_info: SymbolInfo, current_price: float) -> float:
        """Get minimum order quantity based on exchange requirements.
        
        Args:
            symbol_info: Symbol information with minimum requirements
            current_price: Current market price
            
        Returns:
            Minimum order quantity in base currency
        """
        return symbol_info.min_quote_quantity / current_price