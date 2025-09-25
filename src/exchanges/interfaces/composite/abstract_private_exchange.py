"""
Abstract Private Exchange Implementation

Template method pattern implementation that eliminates code duplication
between exchange implementations by centralizing common trading patterns,
error handling, and performance tracking.

This abstract class provides unified trading operations while allowing
exchange-specific customization through template methods.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any, Protocol, runtime_checkable
import asyncio

from exchanges.interfaces.composite.base_private_exchange import CompositePrivateExchange
from exchanges.structs.common import (
    Symbol, OrderType, TimeInForce, Order, AssetBalance, Position
)
from exchanges.structs import Side
from exchanges.structs.types import OrderId
from config.structs import ExchangeConfig
from infrastructure.logging import HFTLoggerInterface
from exchanges.interfaces.utils.trading_performance_tracker import TradingPerformanceTracker


@runtime_checkable
class OrderValidatorProtocol(Protocol):
    """Protocol for order validators."""
    def validate_order(self, symbol: Symbol, side: Side, quantity: float, price: Optional[float], order_type: OrderType) -> None:
        """Validate order parameters."""
        ...


class AbstractPrivateExchange(CompositePrivateExchange, ABC):
    """
    Abstract base class for private exchange implementations.
    
    Provides common patterns for trading operations, error handling,
    performance tracking, and validation while allowing exchange-specific
    customization through template methods.
    
    Eliminates ~80% of code duplication between exchange implementations
    by centralizing common patterns and utilities.
    
    Architecture:
    - Template methods provide common flow (validation, timing, error handling)
    - Abstract implementation methods handle exchange-specific logic
    - Performance tracking is centralized and consistent
    - Error handling and logging patterns are unified
    """
    
    def __init__(self, 
                 config: ExchangeConfig, 
                 symbols: List[Symbol], 
                 logger: Optional[HFTLoggerInterface] = None):
        """Initialize abstract private exchange."""
        super().__init__(config)
        
        # Performance tracking
        self._performance_tracker = TradingPerformanceTracker(
            logger=self.logger,
            exchange_name=config.name
        )
        
        # Order validation
        self._order_validator = self._create_order_validator()
        
        # Initialize exchange-specific components
        self._initialize_exchange_components()
        
        self.logger.info("AbstractPrivateExchange initialized",
                        exchange=config.name,
                        symbol_count=len(symbols) if symbols else 0)
    
    # ========================================
    # Abstract Methods - Must be implemented by subclasses
    # ========================================
    
    @abstractmethod
    def _initialize_exchange_components(self) -> None:
        """Initialize exchange-specific components (REST clients, etc.)."""
        pass
    
    @abstractmethod
    async def _place_limit_order_impl(self, 
                                    symbol: Symbol, 
                                    side: Side, 
                                    quantity: float, 
                                    price: float, 
                                    **kwargs) -> Order:
        """Exchange-specific limit order implementation."""
        pass
    
    @abstractmethod
    async def _place_market_order_impl(self, 
                                     symbol: Symbol, 
                                     side: Side, 
                                     quantity: float, 
                                     **kwargs) -> Order:
        """Exchange-specific market order implementation."""
        pass
    
    @abstractmethod
    async def _cancel_order_impl(self, symbol: Symbol, order_id: OrderId) -> bool:
        """Exchange-specific order cancellation implementation."""
        pass
    
    @abstractmethod
    async def _get_order_impl(self, order_id: OrderId, symbol: Symbol) -> Optional[Order]:
        """Exchange-specific order retrieval implementation.""" 
        pass
    
    @abstractmethod
    async def _get_balances_impl(self) -> Dict[str, AssetBalance]:
        """Exchange-specific balance retrieval implementation."""
        pass
    
    @abstractmethod
    async def _get_open_orders_impl(self, symbol: Optional[Symbol] = None) -> List[Order]:
        """Exchange-specific open orders retrieval implementation."""
        pass
    
    @abstractmethod
    def _create_order_validator(self) -> Optional[OrderValidatorProtocol]:
        """Create exchange-specific order validator (can return None if not needed)."""
        pass
    
    # ========================================
    # Template Methods - Common implementations using performance tracking
    # ========================================
    
    async def place_limit_order(self, 
                              symbol: Symbol, 
                              side: Side, 
                              quantity: float, 
                              price: float, 
                              time_in_force: TimeInForce = TimeInForce.GTC,
                              **kwargs) -> Order:
        """
        Place a limit order with common validation and performance tracking.
        
        Template method that provides:
        - Input validation
        - Performance timing
        - Error handling and logging
        - Metrics collection
        """
        # Pre-execution validation
        self._validate_order_params(symbol, side, quantity, price, OrderType.LIMIT)
        
        # Execute with performance tracking
        async def _execute():
            return await self._place_limit_order_impl(
                symbol=symbol,
                side=side, 
                quantity=quantity,
                price=price,
                time_in_force=time_in_force,
                **kwargs
            )
        
        return await self._performance_tracker.track_operation(
            operation_name="place_limit_order",
            operation_func=_execute
        )
    
    async def place_market_order(self, 
                               symbol: Symbol, 
                               side: Side, 
                               quantity: float,
                               **kwargs) -> Order:
        """
        Place a market order with common validation and performance tracking.
        """
        # Pre-execution validation
        self._validate_order_params(symbol, side, quantity, None, OrderType.MARKET)
        
        # Execute with performance tracking
        async def _execute():
            return await self._place_market_order_impl(
                symbol=symbol,
                side=side,
                quantity=quantity,
                **kwargs
            )
        
        return await self._performance_tracker.track_operation(
            operation_name="place_market_order",
            operation_func=_execute
        )
    
    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> bool:
        """
        Cancel an order with performance tracking and validation.
        """
        # Validate inputs
        if not order_id:
            raise ValueError("Order ID is required for cancellation")
        if not symbol:
            raise ValueError("Symbol is required for order cancellation")
        
        # Execute with performance tracking
        async def _execute():
            return await self._cancel_order_impl(symbol, order_id)
        
        return await self._performance_tracker.track_operation(
            operation_name="cancel_order",
            operation_func=_execute
        )
    
    async def get_order(self, order_id: OrderId, symbol: Symbol) -> Optional[Order]:
        """
        Retrieve order details with performance tracking.
        """
        # Validate inputs
        if not order_id:
            raise ValueError("Order ID is required")
        if not symbol:
            raise ValueError("Symbol is required for order retrieval")
        
        # Execute with performance tracking
        async def _execute():
            return await self._get_order_impl(order_id, symbol)
        
        return await self._performance_tracker.track_operation(
            operation_name="get_order",
            operation_func=_execute,
            log_success=False  # Don't log every order query
        )
    
    async def get_balances(self) -> Dict[str, AssetBalance]:
        """
        Get account balances with performance tracking.
        """
        async def _execute():
            return await self._get_balances_impl()
        
        return await self._performance_tracker.track_operation(
            operation_name="get_balances", 
            operation_func=_execute,
            log_success=False  # Don't log every balance query
        )
    
    async def get_open_orders(self, symbol: Optional[Symbol] = None) -> List[Order]:
        """
        Get open orders with performance tracking.
        """
        async def _execute():
            return await self._get_open_orders_impl(symbol)
        
        return await self._performance_tracker.track_operation(
            operation_name="get_open_orders",
            operation_func=_execute,
            log_success=False  # Don't log every order query
        )
    
    # ========================================
    # Batch Operations - Common implementations
    # ========================================
    
    async def place_multiple_orders(self, orders: List[Dict[str, Any]]) -> List[Order]:
        """
        Place multiple orders with optimized performance tracking.
        
        Processes orders concurrently where possible while respecting
        exchange rate limits and error isolation.
        """
        if not orders:
            return []
        
        self.logger.info(f"Placing {len(orders)} orders",
                        exchange=self.config.name,
                        order_count=len(orders))
        
        results = []
        errors = []
        
        # Process orders with controlled concurrency
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent orders
        
        async def _place_single_order(order_data: Dict[str, Any]) -> Optional[Order]:
            async with semaphore:
                try:
                    order_type = order_data.get('type', 'limit')
                    
                    if order_type.lower() == 'limit':
                        return await self.place_limit_order(
                            symbol=order_data['symbol'],
                            side=order_data['side'],
                            quantity=order_data['quantity'],
                            price=order_data['price'],
                            **order_data.get('kwargs', {})
                        )
                    elif order_type.lower() == 'market':
                        return await self.place_market_order(
                            symbol=order_data['symbol'],
                            side=order_data['side'],
                            quantity=order_data['quantity'],
                            **order_data.get('kwargs', {})
                        )
                    else:
                        raise ValueError(f"Unsupported order type: {order_type}")
                        
                except Exception as e:
                    errors.append({"order": order_data, "error": str(e)})
                    return None
        
        # Execute all orders concurrently
        order_tasks = [_place_single_order(order_data) for order_data in orders]
        results = await asyncio.gather(*order_tasks, return_exceptions=True)
        
        # Filter out None results and exceptions
        successful_orders = [r for r in results if isinstance(r, Order)]
        
        self.logger.info(f"Batch order placement completed",
                        exchange=self.config.name,
                        total_orders=len(orders),
                        successful_orders=len(successful_orders),
                        failed_orders=len(errors))
        
        if errors:
            self.logger.warning("Some orders failed in batch placement",
                              exchange=self.config.name,
                              errors=errors[:5])  # Log first 5 errors
        
        return successful_orders
    
    async def cancel_multiple_orders(self, order_cancellations: List[Dict[str, Any]]) -> List[bool]:
        """Cancel multiple orders with controlled concurrency."""
        if not order_cancellations:
            return []
        
        self.logger.info(f"Cancelling {len(order_cancellations)} orders",
                        exchange=self.config.name,
                        cancellation_count=len(order_cancellations))
        
        # Process cancellations with controlled concurrency
        semaphore = asyncio.Semaphore(10)  # Higher concurrency for cancellations
        
        async def _cancel_single_order(cancellation_data: Dict[str, Any]) -> bool:
            async with semaphore:
                try:
                    return await self.cancel_order(
                        symbol=cancellation_data['symbol'],
                        order_id=cancellation_data['order_id']
                    )
                except Exception as e:
                    self.logger.error(f"Failed to cancel order: {e}",
                                    order_id=cancellation_data['order_id'],
                                    symbol=str(cancellation_data['symbol']))
                    return False
        
        # Execute all cancellations concurrently  
        cancellation_tasks = [_cancel_single_order(data) for data in order_cancellations]
        results = await asyncio.gather(*cancellation_tasks, return_exceptions=True)
        
        # Convert exceptions to False
        cancellation_results = [
            r if isinstance(r, bool) else False 
            for r in results
        ]
        
        successful_cancellations = sum(cancellation_results)
        
        self.logger.info(f"Batch order cancellation completed",
                        exchange=self.config.name,
                        total_cancellations=len(order_cancellations),
                        successful_cancellations=successful_cancellations,
                        failed_cancellations=len(order_cancellations) - successful_cancellations)
        
        return cancellation_results
    
    # ========================================
    # Validation and Utilities
    # ========================================
    
    def _validate_order_params(self, 
                             symbol: Symbol, 
                             side: Side, 
                             quantity: float, 
                             price: Optional[float],
                             order_type: OrderType) -> None:
        """Validate common order parameters."""
        if not symbol:
            raise ValueError("Symbol is required")
        
        if not side:
            raise ValueError("Side is required") 
        
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        
        if order_type == OrderType.LIMIT and (not price or price <= 0):
            raise ValueError("Price must be positive for limit orders")
        
        # Validate symbol is in active symbols
        if hasattr(self, 'active_symbols') and symbol not in self.active_symbols:
            raise ValueError(f"Symbol {symbol} is not in active symbols list")
        
        # Use exchange-specific validator if available
        if self._order_validator:
            self._order_validator.validate_order(symbol, side, quantity, price, order_type)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        return {
            "exchange": self.config.name,
            "overall_stats": self._performance_tracker.get_overall_stats(),
            "operation_stats": {
                "place_limit_order": self._performance_tracker.get_operation_stats("place_limit_order"),
                "place_market_order": self._performance_tracker.get_operation_stats("place_market_order"),
                "cancel_order": self._performance_tracker.get_operation_stats("cancel_order"),
                "get_order": self._performance_tracker.get_operation_stats("get_order"),
                "get_balances": self._performance_tracker.get_operation_stats("get_balances"),
                "get_open_orders": self._performance_tracker.get_operation_stats("get_open_orders")
            }
        }
    
    @property
    def trading_operations_count(self) -> int:
        """Get total trading operations count."""
        return self._performance_tracker.trading_operations_count