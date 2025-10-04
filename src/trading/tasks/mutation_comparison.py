"""
Comparison of dict mutation approaches for DeltaNeutralTask refactoring.

Shows the old problematic way vs. the two new clean approaches.
"""

from exchanges.structs.common import Side

# ========================================
# ORIGINAL PROBLEMATIC PATTERN (DON'T USE)
# ========================================
def old_problematic_pattern(self, order):
    """The original problematic pattern that violates immutability."""
    # ❌ PROBLEMS:
    # 1. Direct mutation breaks immutability
    # 2. Verbose and repetitive
    # 3. Wasteful - creates new dicts after mutation
    # 4. Error-prone - easy to forget to call evolve_context
    
    self.context.filled_quantity[order.side] = (
        self.context.filled_quantity[order.side] + order.filled_quantity
    )
    self.context.order_id[order.side] = None
    
    # Then redundantly pass the whole mutated dict
    self.evolve_context(
        order_id=self.context.order_id, 
        filled_quantity=self.context.filled_quantity
    )


# ========================================
# APPROACH 1: DJANGO-LIKE SYNTAX
# ========================================
def django_like_approach(self, order):
    """Django-like double underscore syntax."""
    # ✅ PROS:
    # - Familiar syntax (Django QuerySet style)
    # - Single method call
    # - Mix dict and regular updates
    # - Can use dynamic key construction
    
    # Static keys
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
    
    # Or with dynamic keys (more DRY)
    side_key = 'buy' if order.side == Side.BUY else 'sell'
    self.evolve_context(**{
        f'filled_quantity__{side_key}': (
            self.context.filled_quantity[order.side] + order.filled_quantity
        ),
        f'order_id__{side_key}': None
    })


# ========================================
# APPROACH 2: EXPLICIT TUPLE SYNTAX (NEW)
# ========================================
def explicit_tuple_approach(self, order):
    """Explicit tuple-based syntax - most straightforward."""
    # ✅ PROS:
    # - Crystal clear what's being updated
    # - Type-safe (no string manipulation)
    # - IDE autocomplete works perfectly
    # - No magic syntax to remember
    # - Works naturally with enums
    
    # Single update
    self.update_dict_field('filled_quantity', order.side, 
                          self.context.filled_quantity[order.side] + order.filled_quantity)
    self.update_dict_field('order_id', order.side, None)
    
    # Or atomic multiple updates (preferred)
    self.update_dict_fields(
        ('filled_quantity', order.side, 
         self.context.filled_quantity[order.side] + order.filled_quantity),
        ('order_id', order.side, None)
    )


# ========================================
# REAL WORLD EXAMPLES
# ========================================

class DeltaNeutralTaskRefactored:
    """Examples of both approaches for common patterns."""
    
    # DJANGO-LIKE EXAMPLES
    def process_order_django_style(self, order):
        """Process order execution with Django-like syntax."""
        # Calculate new values
        old_filled = self.context.filled_quantity[order.side]
        new_filled = old_filled + order.filled_quantity
        old_avg = self.context.avg_price[order.side]
        new_avg = ((old_avg * old_filled) + (order.price * order.filled_quantity)) / new_filled
        
        # Update with Django-like syntax
        side_key = 'buy' if order.side == Side.BUY else 'sell'
        self.evolve_context(**{
            f'filled_quantity__{side_key}': new_filled,
            f'avg_price__{side_key}': new_avg,
            f'order_id__{side_key}': None,
            'state': TradingStrategyState.EXECUTING  # Mix with regular fields
        })
    
    def clear_all_orders_django(self):
        """Clear all orders with Django syntax."""
        self.evolve_context(
            order_id__buy=None,
            order_id__sell=None
        )
    
    # EXPLICIT TUPLE EXAMPLES  
    def process_order_explicit_style(self, order):
        """Process order execution with explicit tuple syntax."""
        # Calculate new values
        old_filled = self.context.filled_quantity[order.side]
        new_filled = old_filled + order.filled_quantity
        old_avg = self.context.avg_price[order.side]
        new_avg = ((old_avg * old_filled) + (order.price * order.filled_quantity)) / new_filled
        
        # Update with explicit syntax - VERY clear what's happening
        self.update_dict_fields(
            ('filled_quantity', order.side, new_filled),
            ('avg_price', order.side, new_avg),
            ('order_id', order.side, None)
        )
        
        # Separate call for regular fields (or could mix with evolve_context)
        self.evolve_context(state=TradingStrategyState.EXECUTING)
    
    def clear_all_orders_explicit(self):
        """Clear all orders with explicit syntax."""
        self.update_dict_fields(
            ('order_id', Side.BUY, None),
            ('order_id', Side.SELL, None)
        )
    
    def update_both_sides_explicit(self, buy_order, sell_order):
        """Update both sides atomically."""
        self.update_dict_fields(
            # Buy side
            ('filled_quantity', Side.BUY, 
             self.context.filled_quantity[Side.BUY] + buy_order.filled_quantity),
            ('order_id', Side.BUY, buy_order.order_id),
            ('avg_price', Side.BUY, buy_order.price),
            
            # Sell side
            ('filled_quantity', Side.SELL,
             self.context.filled_quantity[Side.SELL] + sell_order.filled_quantity),
            ('order_id', Side.SELL, sell_order.order_id),
            ('avg_price', Side.SELL, sell_order.price)
        )


# ========================================
# PERFORMANCE COMPARISON
# ========================================

def performance_notes():
    """
    Performance characteristics of each approach:
    
    OLD PROBLEMATIC:
    - Multiple dict mutations + evolve_context call
    - Creates dicts twice (mutation + copy)
    - ~3 operations per update
    
    DJANGO-LIKE:
    - Single evolve_context call
    - String parsing overhead for keys
    - ~1.5 operations per update
    
    EXPLICIT TUPLE:
    - Single update_dict_fields call  
    - No string parsing
    - Direct tuple unpacking
    - ~1 operation per update (fastest)
    """


# ========================================
# RECOMMENDATION
# ========================================

def recommendation():
    """
    RECOMMENDED USAGE:
    
    1. EXPLICIT TUPLE SYNTAX for new code:
       - Clearest intent
       - Best performance
       - Type-safe
       - IDE-friendly
    
    2. DJANGO-LIKE for quick migrations:
       - Familiar syntax
       - Easy to convert from old code
       - Good for mixed updates
    
    3. Choose based on team preference:
       - Explicit = more verbose but clearer
       - Django-like = more compact but requires string knowledge
    
    BOTH are infinitely better than the old mutation pattern!
    """