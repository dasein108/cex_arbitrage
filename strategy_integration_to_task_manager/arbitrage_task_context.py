"""ArbitrageTaskContext - TaskManager compatible context for arbitrage strategy.

This module provides the context structure needed to make the MexcGateioFuturesStrategy
compatible with the TaskManager system while preserving all existing functionality.
"""

import time
import msgspec
from typing import Optional, Dict, Type
from enum import IntEnum

from exchanges.structs import Symbol, Side, Order
from trading.tasks.base_task import TaskContext
from applications.hedged_arbitrage.strategy.mexc_gateio_futures_strategy import (
    TradingParameters, PositionState, ArbitrageOpportunity, ArbitrageState
)


class ArbitrageTaskContext(TaskContext):
    """Arbitrage-specific context extending TaskContext for TaskManager compatibility.
    
    This context preserves all MexcGateioFuturesContext functionality while adding
    TaskManager compatibility and order ID preservation for recovery safety.
    """
    
    # Core arbitrage configuration
    symbol: Symbol
    base_position_size_usdt: float = 20.0
    max_position_multiplier: float = 2.0
    futures_leverage: float = 1.0
    
    # Trading parameters
    params: TradingParameters = msgspec.field(default_factory=TradingParameters)
    
    # Enhanced position tracking (preserved from original)
    positions: PositionState = msgspec.field(default_factory=PositionState)
    
    # CRITICAL: Active order preservation for recovery
    # Using string keys for serialization compatibility
    active_orders: Dict[str, Dict[str, Order]] = msgspec.field(
        default_factory=lambda: {"spot": {}, "futures": {}}
    )
    
    # State and opportunity tracking (preserved from original)
    arbitrage_state: ArbitrageState = ArbitrageState.IDLE
    current_opportunity: Optional[ArbitrageOpportunity] = None
    position_start_time: Optional[float] = None
    
    # Exchange minimum quantities (preserved from original)
    min_quote_quantity: Dict[str, float] = msgspec.field(default_factory=dict)
    
    # Performance tracking (preserved from original)
    arbitrage_cycles: int = 0
    total_volume_usdt: float = 0.0
    total_profit: float = 0.0
    total_fees: float = 0.0
    
    def _convert_dict_key(self, field_name: str, key_str: str):
        """Enhanced key conversion for arbitrage-specific fields.
        
        Handles ArbitrageState and exchange type conversions for proper
        context evolution with Django-like syntax.
        """
        # Handle active_orders and min_quote_quantity exchange types
        if field_name in ['active_orders', 'min_quote_quantity']:
            if key_str in ['spot', 'futures']:
                return key_str
        
        # Handle ArbitrageState enum conversion
        if field_name == 'arbitrage_state' and key_str.isdigit():
            return ArbitrageState(int(key_str))
        
        # Handle Side enum conversion for active_orders nested updates
        if key_str.upper() in ['BUY', 'SELL']:
            try:
                return Side.BUY if key_str.upper() == 'BUY' else Side.SELL
            except:
                pass
        
        # Fall back to base implementation
        return super()._convert_dict_key(field_name, key_str)
    
    def get_active_order_count(self) -> int:
        """Get total number of active orders across all exchanges."""
        return sum(len(orders) for orders in self.active_orders.values())
    
    def has_active_orders(self) -> bool:
        """Check if there are any active orders."""
        return self.get_active_order_count() > 0
    
    def get_exchange_active_orders(self, exchange_type: str) -> Dict[str, Order]:
        """Get active orders for a specific exchange type.
        
        Args:
            exchange_type: 'spot' or 'futures'
            
        Returns:
            Dictionary of order_id -> Order for the exchange
        """
        return self.active_orders.get(exchange_type, {})
    
    def add_active_order(self, exchange_type: str, order: Order) -> 'ArbitrageTaskContext':
        """Add an active order to context tracking.
        
        Args:
            exchange_type: 'spot' or 'futures'
            order: Order object to track
            
        Returns:
            Updated context with new order
        """
        # Use Django-like evolution syntax
        update_key = f'active_orders__{exchange_type}__{order.order_id}'
        return self.evolve(**{update_key: order})
    
    def remove_active_order(self, exchange_type: str, order_id: str) -> 'ArbitrageTaskContext':
        """Remove an active order from context tracking.
        
        Args:
            exchange_type: 'spot' or 'futures'  
            order_id: Order ID to remove
            
        Returns:
            Updated context with order removed
        """
        # Use Django-like evolution syntax with None to remove
        update_key = f'active_orders__{exchange_type}__{order_id}'
        return self.evolve(**{update_key: None})
    
    def update_active_order(self, exchange_type: str, updated_order: Order) -> 'ArbitrageTaskContext':
        """Update an existing active order in context tracking.
        
        Args:
            exchange_type: 'spot' or 'futures'
            updated_order: Updated order object
            
        Returns:
            Updated context with order updated
        """
        # Use Django-like evolution syntax
        update_key = f'active_orders__{exchange_type}__{updated_order.order_id}'
        return self.evolve(**{update_key: updated_order})


def create_arbitrage_context(
    symbol: Symbol,
    base_position_size_usdt: float = 20.0,
    max_entry_cost_pct: float = 0.5,
    min_profit_pct: float = 0.1,
    max_hours: float = 6.0,
    futures_leverage: float = 1.0,
    task_id: Optional[str] = None
) -> ArbitrageTaskContext:
    """Factory function to create ArbitrageTaskContext with proper defaults.
    
    Args:
        symbol: Trading symbol
        base_position_size_usdt: Base position size in USDT
        max_entry_cost_pct: Maximum entry cost percentage
        min_profit_pct: Minimum profit percentage for exit
        max_hours: Maximum hours to hold position
        futures_leverage: Leverage for futures trading
        task_id: Optional task ID (auto-generated if None)
        
    Returns:
        Configured ArbitrageTaskContext ready for TaskManager
    """
    # Create trading parameters
    params = TradingParameters(
        max_entry_cost_pct=max_entry_cost_pct,
        min_profit_pct=min_profit_pct,
        max_hours=max_hours
    )
    
    # Generate task_id if not provided
    if task_id is None:
        timestamp = int(time.time() * 1000)
        task_id = f"arbitrage_{symbol.base}_{symbol.quote}_{timestamp}"
    
    # Create context with all required fields
    return ArbitrageTaskContext(
        task_id=task_id,
        symbol=symbol,
        base_position_size_usdt=base_position_size_usdt,
        max_position_multiplier=2.0,
        futures_leverage=futures_leverage,
        params=params,
        positions=PositionState(),
        arbitrage_state=ArbitrageState.IDLE,
        should_save_flag=True  # Mark for initial persistence
    )


# Convenience function for backward compatibility
def convert_mexc_gateio_context_to_task_context(
    original_context,
    task_id: Optional[str] = None
) -> ArbitrageTaskContext:
    """Convert existing MexcGateioFuturesContext to ArbitrageTaskContext.
    
    This function helps migrate existing strategy instances to TaskManager
    compatibility without losing state.
    
    Args:
        original_context: MexcGateioFuturesContext instance
        task_id: Optional task ID (auto-generated if None)
        
    Returns:
        ArbitrageTaskContext with preserved state
    """
    # Generate task_id if not provided
    if task_id is None:
        timestamp = int(time.time() * 1000)
        task_id = f"arbitrage_{original_context.symbol.base}_{original_context.symbol.quote}_{timestamp}"
    
    # Create new context with all original fields
    return ArbitrageTaskContext(
        task_id=task_id,
        symbol=original_context.symbol,
        base_position_size_usdt=original_context.base_position_size_usdt,
        max_position_multiplier=original_context.max_position_multiplier,
        futures_leverage=original_context.futures_leverage,
        params=original_context.params,
        positions=original_context.positions,
        arbitrage_state=original_context.state,  # Note: field name mapping
        current_opportunity=original_context.current_opportunity,
        position_start_time=original_context.position_start_time,
        min_quote_quantity=original_context.min_quote_quantity,
        arbitrage_cycles=original_context.arbitrage_cycles,
        total_volume_usdt=original_context.total_volume_usdt,
        total_profit=original_context.total_profit,
        total_fees=original_context.total_fees,
        should_save_flag=True  # Mark for persistence
    )