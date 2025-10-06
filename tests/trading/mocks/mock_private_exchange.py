"""
Mock Private Exchange for Testing Delta Neutral Tasks

Provides a realistic but controllable mock implementation of BasePrivateComposite
for testing trading operations without actual exchange connections.
"""

import asyncio
from typing import Dict, List, Optional, Set
from unittest.mock import AsyncMock
import time

from exchanges.interfaces.composite.base_private_composite import BasePrivateComposite
from exchanges.structs import Symbol, Order, ExchangeEnum, OrderStatus
from exchanges.structs.common import Side, OrderType, TimeInForce, AssetName
from infrastructure.networking.websocket.structs import PrivateWebsocketChannelType


class MockPrivateExchange(BasePrivateComposite):
    """Mock private exchange for testing trading tasks.
    
    Simulates real trading operations with controllable behavior for testing
    state machine logic, order lifecycle management, and error scenarios.
    """
    
    def __init__(self, exchange_enum: ExchangeEnum):
        # Initialize without calling super().__init__ to avoid real exchange setup
        self.exchange = exchange_enum
        self._orders: Dict[str, Order] = {}
        self._order_counter = 1
        self._is_connected = False
        self.is_futures = False
        
        # Tracking for test verification
        self._initialize_called = False
        self._close_called = False
        self._placed_orders: List[Order] = []
        self._cancelled_orders: List[str] = []
        
        # Behavior control for testing scenarios
        self._should_fail_orders = False
        self._should_fail_cancellation = False
        self._order_fill_behavior: Dict[str, float] = {}  # order_id -> fill_quantity
        
    async def initialize(self, symbols: List[Symbol], 
                        private_channels: Optional[List[PrivateWebsocketChannelType]] = None):
        """Initialize mock private exchange."""
        self._initialize_called = True
        self._is_connected = True
    
    async def close(self):
        """Close mock exchange."""
        self._close_called = True
        self._is_connected = False
    
    def is_connected(self) -> bool:
        """Check if mock exchange is connected."""
        return self._is_connected
    
    async def place_limit_order(self, symbol: Symbol, side: Side, 
                               quantity: float, price: float) -> Order:
        """Place a mock limit order."""
        if self._should_fail_orders:
            raise Exception("Mock order placement failure")
        
        order_id = f"mock_order_{self._order_counter}"
        self._order_counter += 1
        
        order = Order(
            symbol=symbol,
            order_id=order_id,
            side=side,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=price,
            filled_quantity=0.0,
            status=OrderStatus.NEW,
            timestamp=int(time.time() * 1000),
            time_in_force=TimeInForce.GTC
        )
        
        self._orders[order_id] = order
        self._placed_orders.append(order)
        
        # Auto-fill behavior for testing
        if order_id in self._order_fill_behavior:
            fill_quantity = self._order_fill_behavior[order_id]
            import msgspec.structs
            filled_order = msgspec.structs.replace(
                order,
                filled_quantity=fill_quantity,
                status=OrderStatus.FILLED if fill_quantity >= quantity else OrderStatus.PARTIALLY_FILLED
            )
            self._orders[order_id] = filled_order
            order = filled_order  # Update the returned order
        
        return order
    
    async def place_market_order(self, symbol: Symbol, side: Side, 
                                price: float, quote_quantity: float) -> Order:
        """Place a mock market order."""
        if self._should_fail_orders:
            raise Exception("Mock market order placement failure")
        
        order_id = f"mock_market_{self._order_counter}"
        self._order_counter += 1
        
        base_quantity = quote_quantity / price
        
        order = Order(
            symbol=symbol,
            order_id=order_id,
            side=side,
            order_type=OrderType.MARKET,
            quantity=base_quantity,
            price=price,
            filled_quantity=base_quantity,  # Market orders fill immediately
            status=OrderStatus.FILLED,
            timestamp=int(time.time() * 1000),
            time_in_force=TimeInForce.IOC
        )
        
        self._orders[order_id] = order
        self._placed_orders.append(order)
        
        return order
    
    async def cancel_order(self, symbol: Symbol, order_id: str) -> Order:
        """Cancel a mock order."""
        if self._should_fail_cancellation:
            raise Exception("Mock order cancellation failure")
        
        if order_id not in self._orders:
            raise Exception(f"Order {order_id} not found")
        
        order = self._orders[order_id]
        import msgspec.structs
        cancelled_order = msgspec.structs.replace(
            order,
            status=OrderStatus.CANCELLED
        )
        
        self._orders[order_id] = cancelled_order
        self._cancelled_orders.append(order_id)
        
        return cancelled_order
    
    async def fetch_order(self, symbol: Symbol, order_id: str) -> Order:
        """Fetch order status."""
        if order_id not in self._orders:
            raise Exception(f"Order {order_id} not found")
        return self._orders[order_id]
    
    async def get_active_order(self, symbol: Symbol, order_id: str) -> Order:
        """Get active order status (alias for fetch_order)."""
        return await self.fetch_order(symbol, order_id)
    
    def round_base_to_contracts(self, symbol: Symbol, quantity: float) -> float:
        """Round quantity to contract size (for futures testing)."""
        if self.is_futures:
            # Simple rounding for testing
            return round(quantity, 3)
        return quantity
    
    # Test control methods
    def set_order_fill_behavior(self, order_id: str, fill_quantity: float):
        """Set how much an order should be filled (for testing partial fills)."""
        self._order_fill_behavior[order_id] = fill_quantity
    
    def set_should_fail_orders(self, should_fail: bool):
        """Control whether order placement should fail (for error testing)."""
        self._should_fail_orders = should_fail
    
    def set_should_fail_cancellation(self, should_fail: bool):
        """Control whether order cancellation should fail (for error testing)."""
        self._should_fail_cancellation = should_fail
    
    def simulate_order_fill(self, order_id: str, fill_quantity: float):
        """Simulate an order getting filled during execution."""
        if order_id in self._orders:
            order = self._orders[order_id]
            new_status = OrderStatus.FILLED if fill_quantity >= order.quantity else OrderStatus.PARTIALLY_FILLED
            
            # Use msgspec.structs.replace for msgspec.Struct objects
            import msgspec.structs
            filled_order = msgspec.structs.replace(
                order,
                filled_quantity=fill_quantity,
                status=new_status
            )
            self._orders[order_id] = filled_order
    
    def set_futures_mode(self, is_futures: bool):
        """Set whether this exchange operates in futures mode."""
        self.is_futures = is_futures
    
    # Verification methods for tests
    def was_initialized(self) -> bool:
        """Check if initialize was called."""
        return self._initialize_called
    
    def was_closed(self) -> bool:
        """Check if close was called."""
        return self._close_called
    
    def get_placed_orders(self) -> List[Order]:
        """Get all orders that were placed."""
        return self._placed_orders.copy()
    
    def get_cancelled_orders(self) -> List[str]:
        """Get all order IDs that were cancelled."""
        return self._cancelled_orders.copy()
    
    def get_order_count(self) -> int:
        """Get total number of orders placed."""
        return len(self._placed_orders)
    
    def get_order_by_id(self, order_id: str) -> Optional[Order]:
        """Get order by ID."""
        return self._orders.get(order_id)
    
    def reset_tracking(self):
        """Reset tracking for new test."""
        self._placed_orders.clear()
        self._cancelled_orders.clear()
        self._orders.clear()
        self._order_counter = 1
        self._order_fill_behavior.clear()