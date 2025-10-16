"""
ArbitrageTaskContext for TaskManager Integration

Extends TaskContext with arbitrage-specific fields following PROJECT_GUIDES.md:
- Float-only policy (no Decimal usage)
- Struct-first data modeling with msgspec.Struct  
- HFT performance requirements (<50ms execution)
- Active order preservation for recovery
- Integrated profit tracking with automatic calculation
- Multi-spot position management with profit analytics
"""

import time
from typing import Dict, Optional, Literal, List

import msgspec
from msgspec import Struct

from trading.tasks.base_task import TaskContext
from exchanges.structs import Symbol, Side, Order, ExchangeEnum, BookTicker, OrderId
from trading.task_manager.exchange_manager import (
    ArbitrageExchangeType
)
from utils import calculate_weighted_price

# Arbitrage strategy states using Literal strings for optimal performance
# Includes base states and arbitrage-specific states
ArbitrageState = Literal[
    # Base states
    'idle',
    'paused',
    'error', 
    'completed',
    'cancelled',
    'executing',
    'adjusting',
    
    # Arbitrage-specific states
    'initializing',
    'monitoring',
    'analyzing',
    'error_recovery'
]


class Position(Struct):
    """Individual position information with float-only policy."""
    qty: float = 0.0
    price: float = 0.0
    side: Optional[Side] = None

    @property
    def qty_usdt(self) -> float:
        """Calculate position value in USDT."""
        return self.qty / self.price if self.price > 1e-8 else 0.0

    @property
    def has_position(self):
        return self.qty > 1e-8

    def __str__(self):
        return f"[{self.side.name}: {self.qty} @ {self.price}]" if self.side else "[No Position]"


class PositionState(msgspec.Struct):
    """Unified position tracking for both exchanges with integrated profit tracking.
    
    Features:
    - Dictionary-based position tracking for spot and futures
    - Automatic profit calculation during position updates
    - Real-time profit tracking per exchange and total realized profit
    - HFT-optimized with float-only policy for sub-millisecond performance
    """
    positions: Dict[ArbitrageExchangeType, Position] = msgspec.field(default_factory=lambda: {
        'spot': Position(),
        'futures': Position()
    })
    # Profit tracking
    profit_by_exchange: Dict[ArbitrageExchangeType, float] = msgspec.field(default_factory=lambda: {
        'spot': 0.0,
        'futures': 0.0
    })
    total_realized_profit: float = 0.0

    def __str__(self):
        return f"Positions(spot={self.positions['spot']}, futures={self.positions['futures']}, profit=${self.total_realized_profit:.2f})"
    
    @property
    def has_positions(self) -> bool:
        """Check if strategy has any open positions."""
        return any(pos.qty > 1e-8 for pos in self.positions.values())

    @property
    def delta(self):
        """Calculate delta between spot and futures positions, negative if futures exceed spot."""
        return self.positions['spot'].qty - self.positions['futures'].qty

    @property
    def delta_usdt(self):
        """Calculate delta in USDT negative if futures exceed spot."""
        return self.positions['spot'].qty_usdt - self.positions['futures'].qty_usdt
    
    def update_position(self, exchange_key: ArbitrageExchangeType, quantity: float, price: float, side: Side) -> 'PositionState':
        """Update position for specified exchange with automatic profit calculation.
        
        Args:
            exchange_key: 'spot' or 'futures' exchange identifier
            quantity: Order quantity to update position with
            price: Order price for weighted average calculation
            side: Order side (BUY/SELL) for position direction
            
        Returns:
            New PositionState with updated position and profit tracking
            
        Note:
            - Automatically calculates realized profit when closing/reducing positions
            - Updates profit_by_exchange and total_realized_profit atomically
            - Maintains position weighted average price for accurate P&L calculation
        """
        if quantity <= 0:
            return self
            
        current = self.positions[exchange_key]
        profit = 0.0
        
        # Calculate profit when closing/reducing position
        if current.has_position and current.side != side:
            # Position closing: calculate realized profit
            close_quantity = min(quantity, current.qty)
            side_multiplier = 1 if current.side == Side.BUY else -1
            profit = (price - current.price) * close_quantity * side_multiplier
        
        if not current.has_position:  # No existing position
            new_position = Position(qty=quantity, price=price, side=side)
        elif current.side == side:
            # Same side: add to position with weighted average price
            new_price, new_qty = calculate_weighted_price(current.qty, current.price, quantity, price)
            new_position = Position(qty=new_qty, price=new_price, side=side)
        else:
            new_price, new_qty = calculate_weighted_price(current.qty, current.price, -quantity, price)
            # flip side if FUTURES position reverses
            new_side = side if new_qty < 0 and exchange_key == 'futures' else current.side
            threshold_usdt = 1.0
            new_qty_usdt = abs(new_qty * new_price)
            if new_qty_usdt < threshold_usdt:
                new_position = Position()
            else:
                new_position = Position(qty=abs(new_qty), price=new_price, side=new_side)

        # Update positions and profit
        new_positions = self.positions.copy()
        new_positions[exchange_key] = new_position
        
        new_profit_by_exchange = self.profit_by_exchange.copy()
        new_profit_by_exchange[exchange_key] += profit
        
        return msgspec.structs.replace(self, 
                                     positions=new_positions,
                                     profit_by_exchange=new_profit_by_exchange,
                                     total_realized_profit=self.total_realized_profit + profit)


class MultiSpotPositionState(msgspec.Struct):
    """Enhanced position tracking for multiple spot exchanges with profit tracking.
    
    Features:
    - Multiple spot exchange position management with single active position
    - Single futures exchange for hedging
    - Integrated profit tracking per exchange and total realized profit
    - Delta neutrality calculation and validation
    - HFT-optimized performance with float-only policy
    """
    # Active spot position (only one active at a time)
    active_spot_exchange: Optional[str] = None  # e.g., 'mexc_spot'
    active_spot_position: Optional[Position] = None
    
    # Futures hedge (single futures exchange)
    futures_position: Optional[Position] = None
    
    # All spot positions (for transition periods when switching)
    spot_positions: Dict[str, Position] = msgspec.field(default_factory=dict)
    
    # Profit tracking (same structure as PositionState for consistency)
    profit_by_exchange: Dict[str, float] = msgspec.field(default_factory=dict)  # exchange_key -> profit
    total_realized_profit: float = 0.0
    
    def __str__(self):
        active_spot = f"{self.active_spot_exchange}={self.active_spot_position}" if self.active_spot_exchange else "None"
        return f"MultiSpotPositions(active_spot={active_spot}, futures={self.futures_position}, profit=${self.total_realized_profit:.2f})"
    
    @property
    def has_positions(self) -> bool:
        """Check if strategy has any open positions."""
        return (self.active_spot_position and self.active_spot_position.has_position and 
                self.futures_position and self.futures_position.has_position)
    
    @property
    def total_spot_qty(self) -> float:
        """Calculate total spot quantity across all exchanges."""
        total = 0.0
        if self.active_spot_position:
            total += self.active_spot_position.qty
        # Add any transitional positions
        for pos in self.spot_positions.values():
            if pos.has_position:
                total += pos.qty
        return total
    
    @property
    def delta(self) -> float:
        """Calculate delta between total spot and futures positions."""
        futures_qty = self.futures_position.qty if self.futures_position else 0.0
        return self.total_spot_qty - futures_qty
    
    @property
    def delta_usdt(self) -> float:
        """Calculate delta in USDT between total spot and futures positions."""
        spot_usdt = 0.0
        if self.active_spot_position and self.active_spot_position.has_position:
            spot_usdt += self.active_spot_position.qty_usdt
        for pos in self.spot_positions.values():
            if pos.has_position:
                spot_usdt += pos.qty_usdt
        
        futures_usdt = self.futures_position.qty_usdt if self.futures_position else 0.0
        return spot_usdt - futures_usdt
    
    def update_active_spot_position(self, exchange_key: str, quantity: float, price: float, side: Side) -> 'MultiSpotPositionState':
        """Update the active spot position with automatic profit calculation.
        
        Args:
            exchange_key: Exchange identifier (e.g., 'mexc_spot', 'binance_spot')
            quantity: Order quantity to update position with
            price: Order price for weighted average calculation
            side: Order side (BUY/SELL) for position direction
            
        Returns:
            New MultiSpotPositionState with updated position and profit tracking
            
        Note:
            - Automatically calculates realized profit when closing/reducing positions
            - Updates profit_by_exchange for the specific exchange
            - Updates total_realized_profit atomically
        """
        if quantity <= 0:
            return self
        
        current = self.active_spot_position or Position()
        profit = 0.0
        
        # Calculate profit when closing/reducing position (same logic as PositionState)
        if current.has_position and current.side != side:
            # Position closing: calculate realized profit
            close_quantity = min(quantity, current.qty)
            side_multiplier = 1 if current.side == Side.BUY else -1
            profit = (price - current.price) * close_quantity * side_multiplier
        
        if not current.has_position:
            new_position = Position(qty=quantity, price=price, side=side)
        elif current.side == side:
            new_price, new_qty = calculate_weighted_price(current.qty, current.price, quantity, price)
            new_position = Position(qty=new_qty, price=new_price, side=side)
        else:
            new_price, new_qty = calculate_weighted_price(current.qty, current.price, -quantity, price)
            threshold_usdt = 1.0
            new_qty_usdt = abs(new_qty * new_price)
            if new_qty_usdt < threshold_usdt:
                new_position = Position()
                exchange_key = None
            else:
                new_position = Position(qty=abs(new_qty), price=new_price, side=current.side)
        
        # Update profit tracking
        new_profit_by_exchange = self.profit_by_exchange.copy()
        new_profit_by_exchange[exchange_key] = new_profit_by_exchange.get(exchange_key, 0.0) + profit
        
        return msgspec.structs.replace(self, 
                                     active_spot_exchange=exchange_key,
                                     active_spot_position=new_position,
                                     profit_by_exchange=new_profit_by_exchange,
                                     total_realized_profit=self.total_realized_profit + profit)
    
    def update_futures_position(self, quantity: float, price: float, side: Side) -> 'MultiSpotPositionState':
        """Update the futures position with automatic profit calculation.
        
        Args:
            quantity: Order quantity to update position with
            price: Order price for weighted average calculation
            side: Order side (BUY/SELL) for position direction
            
        Returns:
            New MultiSpotPositionState with updated futures position and profit tracking
            
        Note:
            - Automatically calculates realized profit when closing/reducing positions
            - Updates profit_by_exchange for 'futures' exchange
            - Updates total_realized_profit atomically
        """
        if quantity <= 0:
            return self
        
        current = self.futures_position or Position()
        profit = 0.0
        
        # Calculate profit when closing/reducing position (same logic as PositionState)
        if current.has_position and current.side != side:
            # Position closing: calculate realized profit
            close_quantity = min(quantity, current.qty)
            side_multiplier = 1 if current.side == Side.BUY else -1
            profit = (price - current.price) * close_quantity * side_multiplier
        
        if not current.has_position:
            new_position = Position(qty=quantity, price=price, side=side)
        elif current.side == side:
            new_price, new_qty = calculate_weighted_price(current.qty, current.price, quantity, price)
            new_position = Position(qty=new_qty, price=new_price, side=side)
        else:
            new_price, new_qty = calculate_weighted_price(current.qty, current.price, -quantity, price)
            new_side = side if new_qty < 0 else current.side
            threshold_usdt = 1.0
            new_qty_usdt = abs(new_qty * new_price)
            if new_qty_usdt < threshold_usdt:
                new_position = Position()
            else:
                new_position = Position(qty=abs(new_qty), price=new_price, side=new_side)
        
        # Update profit tracking
        new_profit_by_exchange = self.profit_by_exchange.copy()
        new_profit_by_exchange['futures'] = new_profit_by_exchange.get('futures', 0.0) + profit
        
        return msgspec.structs.replace(self, 
                                     futures_position=new_position,
                                     profit_by_exchange=new_profit_by_exchange,
                                     total_realized_profit=self.total_realized_profit + profit)


class TradingParameters(msgspec.Struct):
    """Trading parameters matching backtesting logic."""
    max_entry_cost_pct: float = 0.5  # Only enter if cost < 0.5%
    min_profit_pct: float = 0.1      # Exit when profit > 0.1%
    max_hours: float = 6.0           # Timeout in hours
    spot_fee: float = 0.0005         # 0.05% spot trading fee
    fut_fee: float = 0.0005          # 0.05% futures trading fee


class ValidationResult(msgspec.Struct):
    """Result of execution validation."""
    valid: bool
    reason: str = ""


class DeltaImbalanceResult(msgspec.Struct):
    """Result of delta imbalance analysis."""
    has_imbalance: bool
    imbalance_direction: Optional[Literal['spot_excess', 'futures_excess']] = None
    imbalance_quantity: float = 0.0
    imbalance_percentage: float = 0.0
    reason: str = ""


class ArbitrageOpportunity(msgspec.Struct):
    """Simplified arbitrage opportunity representation."""
    direction: Literal['enter', 'exit']  # 'spot_to_futures' | 'futures_to_spot'
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


class SpotOpportunity(msgspec.Struct):
    """Multi-spot opportunity representation."""
    exchange_key: str  # e.g., 'mexc_spot', 'binance_spot'
    exchange_enum: ExchangeEnum
    entry_price: float
    cost_pct: float  # Cost percentage vs futures
    max_quantity: float
    timestamp: float = msgspec.field(default_factory=time.time)
    
    def is_fresh(self, max_age_seconds: float = 5.0) -> bool:
        """Check if opportunity is still fresh."""
        return (time.time() - self.timestamp) < max_age_seconds


class SpotSwitchOpportunity(msgspec.Struct):
    """Spot switching opportunity representation."""
    current_exchange_key: str
    target_exchange_key: str
    target_exchange_enum: ExchangeEnum
    current_exit_price: float  # Price to sell current spot
    target_entry_price: float  # Price to buy new spot
    profit_pct: float  # Expected profit from switching
    max_quantity: float
    timestamp: float = msgspec.field(default_factory=time.time)
    
    def is_fresh(self, max_age_seconds: float = 2.0) -> bool:
        """Check if switching opportunity is still fresh (shorter window)."""
        return (time.time() - self.timestamp) < max_age_seconds
    
    @property
    def estimated_profit_per_unit(self) -> float:
        """Calculate estimated profit per unit from switching."""
        return self.current_exit_price - self.target_entry_price


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
    single_order_size_usdt: float = 20.0
    max_executed_orders: int = 3
    futures_leverage: float = 1.0
    
    # Exchange configuration for persistence
    spot_exchange: Optional[ExchangeEnum] = None
    futures_exchange: Optional[ExchangeEnum] = None
    
    # Multi-spot configuration (new)
    spot_exchanges: List[ExchangeEnum] = msgspec.field(default_factory=list)
    active_spot_exchange: Optional[str] = None  # e.g., 'mexc_spot'
    operation_mode: Literal['traditional', 'spot_switching'] = 'traditional'
    
    # Multi-spot parameters
    min_switch_profit_pct: float = 0.05  # Minimum profit to justify switching
    max_spot_transition_time: float = 30.0  # Max time for spot switch
    spot_switch_enabled: bool = True  # Enable/disable spot switching
    
    # Trading parameters
    params: TradingParameters = msgspec.field(default_factory=TradingParameters)
    
    # Position tracking (legacy single spot + futures)
    positions_state: PositionState = msgspec.field(default_factory=PositionState)
    
    # Multi-spot position tracking (new)
    multi_spot_positions: Optional[MultiSpotPositionState] = msgspec.field(default_factory=lambda: MultiSpotPositionState())
    
    # Active orders (preserved across restarts) - using string keys for serialization
    active_orders: Dict[ArbitrageExchangeType, Dict[OrderId, Order]] = msgspec.field(default_factory=lambda: {
        'spot': {},
        'futures': {}
    })

    current_mode: Literal['enter', 'exit'] = 'enter'
    
    # Strategy state and performance
    arbitrage_state: ArbitrageState = 'idle'
    current_opportunity: Optional[ArbitrageOpportunity] = None
    position_start_time: Optional[float] = None
    total_volume_usdt: float = 0.0
    total_profit: float = 0.0
    total_fees: float = 0.0


    def _convert_dict_key(self, field_name: str, key_str: str):
        """Convert string key to appropriate type for arbitrage context.
        
        Handles arbitrage-specific enum conversions for context evolution.
        """
        # Handle ArbitrageState string validation
        if field_name == "arbitrage_state":
            # Convert to lowercase and validate against ArbitrageState
            state_str = key_str.lower()
            # Valid states are defined in the ArbitrageState Literal type
            valid_states = [
                'idle', 'paused', 'error', 'completed', 'cancelled', 'executing', 'adjusting',
                'initializing', 'monitoring', 'analyzing', 'error_recovery'
            ]
            if state_str in valid_states:
                return state_str
        
        # Handle exchange type keys for active_orders
        if field_name in ["active_orders"]:
            if key_str.lower() in ['spot', 'futures']:
                return key_str.lower()
        
        # Call parent for common conversions (Side enum, etc.)
        return super()._convert_dict_key(field_name, key_str)
    
    def get_active_order_count(self, exchange_type: Optional[ArbitrageExchangeType] = None) -> int:
        """Get count of active orders for debugging and monitoring."""
        if exchange_type:
            return len(self.active_orders.get(exchange_type, {}))
        return sum(len(orders) for orders in self.active_orders.values())
    
    def has_active_orders(self) -> bool:
        """Check if strategy has any active orders."""
        return self.get_active_order_count() > 0
    
    def generate_strategy_task_id(self, task_name: str, spot_exchange: ExchangeEnum, futures_exchange: ExchangeEnum) -> str:
        """Generate deterministic task ID for strategy tasks.
        
        Creates a recovery-aware task ID based on strategy components instead of timestamps.
        This prevents duplicate tasks during recovery and makes task identification easier.
        
        Args:
            task_name: Name of the task class (e.g., "SpotFuturesArbitrageTask")
            spot_exchange: Spot exchange enum
            futures_exchange: Futures exchange enum
            
        Returns:
            Deterministic task ID string
            
        Example:
            SpotFuturesArbitrageTask_BTCUSDT_MEXC_GATEIO_FUTURES
        """
        symbol_str = f"{self.symbol.base}{self.symbol.quote}"
        return f"{task_name}_{symbol_str}_{spot_exchange.value}_{futures_exchange.value}"