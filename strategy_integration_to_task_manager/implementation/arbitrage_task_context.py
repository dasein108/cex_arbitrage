"""
ArbitrageTaskContext for TaskManager Integration

Extends TaskContext with arbitrage-specific fields following PROJECT_GUIDES.md:
- Float-only policy (no Decimal usage)
- Struct-first data modeling with msgspec.Struct  
- HFT performance requirements (<50ms execution)
- Active order preservation for recovery
"""

import time
from typing import Dict, Optional, Any
from enum import IntEnum

import msgspec
from msgspec import Struct

from trading.tasks.base_task import TaskContext
from trading.struct import TradingStrategyState
from exchanges.structs import Symbol, Side, Order


class ArbitrageState(IntEnum):
    """States for arbitrage strategy execution."""
    IDLE = 0
    INITIALIZING = 1
    MONITORING = 2
    ANALYZING = 3
    EXECUTING = 4
    ERROR_RECOVERY = 5


class Position(Struct):
    """Individual position information with float-only policy."""
    qty: float = 0.0
    price: float = 0.0
    side: Optional[Side] = None

    def __str__(self):
        return f"[{self.side.name}: {self.qty} @ {self.price}]" if self.side else "[No Position]"


class PositionState(msgspec.Struct):
    """Unified position tracking for both exchanges."""
    spot: Position = msgspec.field(default_factory=Position)
    futures: Position = msgspec.field(default_factory=Position)
    
    def __str__(self):
        return f"Positions(spot={self.spot}, futures={self.futures})"
    
    @property
    def has_positions(self) -> bool:
        """Check if strategy has any open positions."""
        return self.spot.qty > 1e-8 or self.futures.qty > 1e-8


class TradingParameters(msgspec.Struct):
    """Trading parameters matching backtesting logic."""
    max_entry_cost_pct: float = 0.5  # Only enter if cost < 0.5%
    min_profit_pct: float = 0.1      # Exit when profit > 0.1%
    max_hours: float = 6.0           # Timeout in hours
    spot_fee: float = 0.0005         # 0.05% spot trading fee
    fut_fee: float = 0.0005          # 0.05% futures trading fee


class ArbitrageOpportunity(msgspec.Struct):
    """Simplified arbitrage opportunity representation."""
    direction: str  # 'spot_to_futures' | 'futures_to_spot'
    spread_pct: float
    buy_price: float
    sell_price: float
    max_quantity: float
    timestamp: float = msgspec.field(default_factory=time.time)
    
    def is_fresh(self, max_age_seconds: float = 5.0) -> bool:
        """Check if opportunity is still fresh."""
        return (time.time() - self.timestamp) < max_age_seconds
    
    @property
    def estimated_profit(self) -> float:
        """Calculate estimated profit per unit."""
        return self.sell_price - self.buy_price


class ArbitrageTaskContext(TaskContext):
    """Context for arbitrage trading tasks with order preservation.
    
    Extends TaskContext with arbitrage-specific fields following PROJECT_GUIDES.md:
    - Float-only policy for all numerical fields
    - Struct-first data modeling 
    - Active order preservation for recovery
    - HFT performance optimized
    """
    
    # Core strategy configuration
    symbol: Symbol
    base_position_size_usdt: float = 20.0
    futures_leverage: float = 1.0
    
    # Trading parameters
    params: TradingParameters = msgspec.field(default_factory=TradingParameters)
    
    # Position tracking
    positions: PositionState = msgspec.field(default_factory=PositionState)
    
    # Active orders (preserved across restarts) - using string keys for serialization
    active_orders: Dict[str, Dict[str, Order]] = msgspec.field(default_factory=lambda: {
        'spot': {},
        'futures': {}
    })
    
    # Strategy state and performance
    arbitrage_state: ArbitrageState = ArbitrageState.IDLE
    current_opportunity: Optional[ArbitrageOpportunity] = None
    position_start_time: Optional[float] = None
    arbitrage_cycles: int = 0
    total_volume_usdt: float = 0.0
    total_profit: float = 0.0
    total_fees: float = 0.0
    
    # Minimum quote quantities per exchange
    min_quote_quantity: Dict[str, float] = msgspec.field(default_factory=dict)
    
    def _convert_dict_key(self, field_name: str, key_str: str):
        """Convert string key to appropriate type for arbitrage context.
        
        Handles arbitrage-specific enum conversions for context evolution.
        """
        # Handle ArbitrageState enum conversion
        if field_name == "arbitrage_state":
            try:
                return ArbitrageState[key_str.upper()]
            except (KeyError, AttributeError):
                pass
        
        # Handle exchange type keys for active_orders and min_quote_quantity
        if field_name in ["active_orders", "min_quote_quantity"]:
            if key_str.lower() in ['spot', 'futures']:
                return key_str.lower()
        
        # Call parent for common conversions (Side enum, etc.)
        return super()._convert_dict_key(field_name, key_str)
    
    def get_active_order_count(self, exchange_type: Optional[str] = None) -> int:
        """Get count of active orders for debugging and monitoring."""
        if exchange_type:
            return len(self.active_orders.get(exchange_type, {}))
        return sum(len(orders) for orders in self.active_orders.values())
    
    def has_active_orders(self) -> bool:
        """Check if strategy has any active orders."""
        return self.get_active_order_count() > 0
    
    def clear_active_orders(self, exchange_type: Optional[str] = None):
        """Clear active orders for an exchange or all exchanges."""
        if exchange_type:
            if exchange_type in self.active_orders:
                self.active_orders[exchange_type].clear()
        else:
            for orders in self.active_orders.values():
                orders.clear()