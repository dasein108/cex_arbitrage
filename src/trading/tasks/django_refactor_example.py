"""
Example of how Django-like syntax simplifies DeltaNeutralTask code.

This file demonstrates the before/after refactoring patterns.
"""

from exchanges.structs.common import Side

# ========================================
# BEFORE: Problematic mutation pattern
# ========================================
def old_process_order_execution(self, order):
    """Old problematic pattern with mutation."""
    # Direct mutation of dict fields (BAD!)
    self.context.filled_quantity[order.side] = (
        self.context.filled_quantity[order.side] + order.filled_quantity
    )
    self.context.order_id[order.side] = None
    
    # Then passing the whole mutated dict (REDUNDANT!)
    self.evolve_context(
        order_id=self.context.order_id, 
        filled_quantity=self.context.filled_quantity
    )
    
    # Problems:
    # 1. Mutates context directly (breaks immutability)
    # 2. Creates new dicts after mutation (wasteful)
    # 3. Verbose and error-prone
    # 4. Hard to track what changed


# ========================================
# AFTER: Clean Django-like pattern
# ========================================
def new_process_order_execution(self, order):
    """New clean pattern with Django-like syntax."""
    # Single atomic update with clear intent
    if order.side == Side.BUY:
        self.evolve_context(
            filled_quantity__buy=self.context.filled_quantity[Side.BUY] + order.filled_quantity,
            order_id__buy=None
        )
    else:
        self.evolve_context(
            filled_quantity__sell=self.context.filled_quantity[Side.SELL] + order.filled_quantity,
            order_id__sell=None
        )
    
    # Benefits:
    # 1. No direct mutations
    # 2. Single context update
    # 3. Clear and readable
    # 4. Immutable and safe


# ========================================
# DYNAMIC KEY CONSTRUCTION
# ========================================
def dynamic_update_pattern(self, order):
    """Using dynamic keys for more DRY code."""
    # Convert Side enum to string key
    side_key = 'buy' if order.side == Side.BUY else 'sell'
    
    # Single update with dynamic keys
    self.evolve_context(**{
        f'filled_quantity__{side_key}': (
            self.context.filled_quantity[order.side] + order.filled_quantity
        ),
        f'order_id__{side_key}': None,
        f'avg_price__{side_key}': calculate_weighted_avg(
            self.context.avg_price[order.side],
            order.price,
            order.filled_quantity
        )
    })


# ========================================
# MULTIPLE DICT UPDATES
# ========================================
def complex_update_example(self, buy_order, sell_order):
    """Update multiple sides in one call."""
    self.evolve_context(
        # Buy side updates
        filled_quantity__buy=self.context.filled_quantity[Side.BUY] + buy_order.filled_quantity,
        order_id__buy=buy_order.order_id,
        avg_price__buy=buy_order.price,
        
        # Sell side updates  
        filled_quantity__sell=self.context.filled_quantity[Side.SELL] + sell_order.filled_quantity,
        order_id__sell=sell_order.order_id,
        avg_price__sell=sell_order.price,
        
        # Regular field updates
        state=TradingStrategyState.EXECUTING,
        metadata={'last_update': time.time()}
    )


# ========================================
# HELPER METHOD PATTERN
# ========================================
class DeltaNeutralTaskImproved:
    """Helper methods for common update patterns."""
    
    def update_side_execution(self, side: Side, filled: float, order_id: str = None):
        """Helper for updating single side execution."""
        side_key = 'buy' if side == Side.BUY else 'sell'
        
        updates = {
            f'filled_quantity__{side_key}': filled,
            f'order_id__{side_key}': order_id
        }
        
        self.evolve_context(**updates)
    
    def clear_all_orders(self):
        """Clear all order IDs."""
        self.evolve_context(
            order_id__buy=None,
            order_id__sell=None
        )
    
    def update_fills_and_prices(self, buy_fill: float, sell_fill: float, 
                                buy_price: float, sell_price: float):
        """Update both sides atomically."""
        self.evolve_context(
            filled_quantity__buy=buy_fill,
            filled_quantity__sell=sell_fill,
            avg_price__buy=buy_price,
            avg_price__sell=sell_price
        )


# ========================================
# REAL REFACTORING EXAMPLE
# ========================================
def refactored_cancel_current_order(self, exchange_side: Side):
    """Refactored cancel order with Django-like syntax."""
    if self._curr_order[exchange_side]:
        try:
            order = await self._exchange[exchange_side].private.cancel_order(
                self.context.symbol,
                self._curr_order[exchange_side].order_id
            )
            self.logger.info(f"🛑 Cancelled current order", order_id=order.order_id)
            
            # OLD WAY (lines 129-131 in original):
            # self._curr_order = None
            # # TODO: update both of dict
            # self.evolve_context(order_id=None)
            
            # NEW WAY - Clear specific side's order:
            side_key = 'buy' if exchange_side == Side.BUY else 'sell'
            self.evolve_context(**{f'order_id__{side_key}': None})
            
            # Or if you want to clear both:
            # self.evolve_context(order_id__buy=None, order_id__sell=None)
            
        except Exception as e:
            self.logger.error(f"🚫 Failed to cancel current order", error=str(e))
            self._curr_order[exchange_side] = None
            
            # Clear the specific side's order ID
            side_key = 'buy' if exchange_side == Side.BUY else 'sell'
            self.evolve_context(**{f'order_id__{side_key}': None})