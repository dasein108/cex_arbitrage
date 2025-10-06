"""
Order Generator for Trading Task Tests

Specialized helper for generating orders with various states, fill patterns,
and scenarios commonly encountered in trading task testing.
"""

import time
from typing import List, Dict, Optional, Tuple
from enum import Enum

from exchanges.structs import Order, Symbol, Side, OrderType, OrderStatus
from exchanges.structs.common import TimeInForce
from .test_data_factory import TestDataFactory


class FillPattern(Enum):
    """Common fill patterns for testing."""
    NO_FILL = "no_fill"
    PARTIAL_FILL = "partial_fill"
    FULL_FILL = "full_fill"
    PROGRESSIVE_FILL = "progressive_fill"  # Fills over multiple updates
    INSTANT_FILL = "instant_fill"  # Market orders


class OrderGenerator:
    """Generator for creating orders with specific fill patterns and behaviors."""
    
    def __init__(self):
        self._order_counter = 1
    
    def generate_order_sequence(self, symbol: Symbol, side: Side,
                               quantities: List[float],
                               fill_pattern: FillPattern = FillPattern.NO_FILL,
                               base_price: float = 50000.0) -> List[Order]:
        """Generate a sequence of orders with specified fill pattern."""
        orders = []
        
        for quantity in quantities:
            order = self._create_order_with_pattern(
                symbol, side, quantity, fill_pattern, base_price
            )
            orders.append(order)
        
        return orders
    
    def generate_dual_side_orders(self, symbol: Symbol,
                                 quantity: float = 0.1,
                                 buy_fill_pattern: FillPattern = FillPattern.NO_FILL,
                                 sell_fill_pattern: FillPattern = FillPattern.NO_FILL,
                                 price_spread: float = 100.0) -> Dict[Side, Order]:
        """Generate orders for both buy and sell sides."""
        base_price = 50000.0
        
        buy_order = self._create_order_with_pattern(
            symbol, Side.BUY, quantity, buy_fill_pattern, base_price - price_spread/2
        )
        
        sell_order = self._create_order_with_pattern(
            symbol, Side.SELL, quantity, sell_fill_pattern, base_price + price_spread/2
        )
        
        return {
            Side.BUY: buy_order,
            Side.SELL: sell_order
        }
    
    def generate_imbalanced_scenario(self, symbol: Symbol,
                                   total_quantity: float = 1.0,
                                   buy_fill_ratio: float = 0.7,
                                   sell_fill_ratio: float = 0.3) -> Dict[str, Order]:
        """Generate orders that create an imbalanced fill scenario."""
        buy_filled = total_quantity * buy_fill_ratio
        sell_filled = total_quantity * sell_fill_ratio
        
        buy_order = TestDataFactory.create_partial_filled_order(
            symbol=symbol,
            side=Side.BUY,
            quantity=total_quantity,
            fill_ratio=buy_fill_ratio,
            order_id=self._get_next_order_id()
        )
        
        sell_order = TestDataFactory.create_partial_filled_order(
            symbol=symbol,
            side=Side.SELL,
            quantity=total_quantity,
            fill_ratio=sell_fill_ratio,
            order_id=self._get_next_order_id()
        )
        
        return {
            'buy_order': buy_order,
            'sell_order': sell_order,
            'imbalance_quantity': buy_filled - sell_filled
        }
    
    def generate_progressive_fill_sequence(self, symbol: Symbol, side: Side,
                                         total_quantity: float = 1.0,
                                         fill_steps: List[float] = None) -> List[Order]:
        """Generate a sequence showing progressive order fills."""
        if fill_steps is None:
            fill_steps = [0.0, 0.2, 0.5, 0.8, 1.0]  # 0%, 20%, 50%, 80%, 100%
        
        order_id = self._get_next_order_id()
        base_order = TestDataFactory.create_order(
            symbol=symbol,
            side=side,
            quantity=total_quantity,
            order_id=order_id
        )
        
        fill_sequence = []
        for i, fill_ratio in enumerate(fill_steps):
            filled_quantity = total_quantity * fill_ratio
            
            if fill_ratio == 0.0:
                status = OrderStatus.NEW
            elif fill_ratio < 1.0:
                status = OrderStatus.PARTIALLY_FILLED
            else:
                status = OrderStatus.FILLED
            
            updated_order = Order(
                symbol=base_order.symbol,
                order_id=base_order.order_id,
                side=base_order.side,
                order_type=base_order.order_type,
                quantity=base_order.quantity,
                price=base_order.price,
                filled_quantity=filled_quantity,
                status=status,
                timestamp=base_order.timestamp + i * 1000,  # 1 second between updates
                time_in_force=base_order.time_in_force
            )
            
            fill_sequence.append(updated_order)
        
        return fill_sequence
    
    def generate_cancellation_scenario(self, symbol: Symbol, side: Side,
                                     quantity: float = 0.1,
                                     partial_fill_before_cancel: float = 0.3) -> Tuple[Order, Order]:
        """Generate scenario where order is partially filled then cancelled."""
        order_id = self._get_next_order_id()
        
        # Initial order with partial fill
        partial_order = TestDataFactory.create_partial_filled_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            fill_ratio=partial_fill_before_cancel,
            order_id=order_id
        )
        
        # Cancelled order (preserves fill amount)
        cancelled_order = Order(
            symbol=partial_order.symbol,
            order_id=partial_order.order_id,
            side=partial_order.side,
            order_type=partial_order.order_type,
            quantity=partial_order.quantity,
            price=partial_order.price,
            filled_quantity=partial_order.filled_quantity,
            status=OrderStatus.CANCELLED,
            timestamp=partial_order.timestamp + 5000,  # 5 seconds later
            time_in_force=partial_order.time_in_force
        )
        
        return partial_order, cancelled_order
    
    def generate_market_order_scenario(self, symbol: Symbol, side: Side,
                                     quote_quantity: float = 1000.0,
                                     execution_price: float = 50000.0) -> Order:
        """Generate market order that executes immediately."""
        base_quantity = quote_quantity / execution_price
        
        return TestDataFactory.create_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=base_quantity,
            price=execution_price,
            filled_quantity=base_quantity,
            status=OrderStatus.FILLED,
            time_in_force=TimeInForce.IOC,
            order_id=self._get_next_order_id()
        )
    
    def generate_rebalancing_orders(self, symbol: Symbol,
                                  imbalance_quantity: float = 0.2,
                                  rebalance_side: Side = Side.BUY) -> Dict[str, Order]:
        """Generate orders that would be created during rebalancing."""
        # Original imbalanced state
        if rebalance_side == Side.BUY:
            # Sell side is ahead, need to buy more
            buy_filled = 0.3
            sell_filled = 0.5
        else:
            # Buy side is ahead, need to sell more
            buy_filled = 0.5
            sell_filled = 0.3
        
        # Market order to rebalance
        rebalance_order = self.generate_market_order_scenario(
            symbol=symbol,
            side=rebalance_side,
            quote_quantity=abs(imbalance_quantity) * 50000.0  # Approximate quote value
        )
        
        return {
            'imbalanced_buy_filled': buy_filled,
            'imbalanced_sell_filled': sell_filled,
            'rebalance_order': rebalance_order,
            'target_balance': max(buy_filled, sell_filled)
        }
    
    def _create_order_with_pattern(self, symbol: Symbol, side: Side,
                                  quantity: float, pattern: FillPattern,
                                  price: float) -> Order:
        """Create order with specific fill pattern."""
        order_id = self._get_next_order_id()
        
        if pattern == FillPattern.NO_FILL:
            return TestDataFactory.create_order(
                symbol=symbol, side=side, quantity=quantity, 
                price=price, order_id=order_id
            )
        elif pattern == FillPattern.PARTIAL_FILL:
            return TestDataFactory.create_partial_filled_order(
                symbol=symbol, side=side, quantity=quantity,
                fill_ratio=0.5, price=price, order_id=order_id
            )
        elif pattern == FillPattern.FULL_FILL:
            return TestDataFactory.create_filled_order(
                symbol=symbol, side=side, quantity=quantity,
                price=price, order_id=order_id
            )
        elif pattern == FillPattern.INSTANT_FILL:
            return TestDataFactory.create_order(
                symbol=symbol, side=side, quantity=quantity,
                price=price, order_id=order_id,
                order_type=OrderType.MARKET,
                filled_quantity=quantity,
                status=OrderStatus.FILLED,
                time_in_force=TimeInForce.IOC
            )
        else:
            # Default to no fill
            return TestDataFactory.create_order(
                symbol=symbol, side=side, quantity=quantity,
                price=price, order_id=order_id
            )
    
    def _get_next_order_id(self) -> str:
        """Generate unique order ID for testing."""
        order_id = f"test_order_{self._order_counter}"
        self._order_counter += 1
        return order_id
    
    def reset_counter(self):
        """Reset order counter for new test."""
        self._order_counter = 1