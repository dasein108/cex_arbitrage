"""
Strategy Context Structures

Flexible context structures for different arbitrage strategy types using msgspec.Struct.
Provides type-safe, serializable contexts that support various exchange combinations
and trading patterns while maintaining compatibility with BaseTradingTask.

Features:
- msgspec.Struct compliance for performance and serialization
- Flexible exchange configuration patterns
- State persistence for task recovery
- HFT-optimized data structures
- Support for N-exchange strategies
"""

from typing import Dict, List, Optional, Any
from enum import Enum
import time

import msgspec

from exchanges.structs import Symbol, Side, ExchangeEnum
from trading.tasks.base_task import TaskContext

from .base_arbitrage_strategy import ExchangeRole


class StrategyType(Enum):
    """Types of arbitrage strategies supported."""
    SPOT_SPOT = "spot_spot"                    # 2 spot exchanges
    SPOT_FUTURES = "spot_futures"              # Spot + futures arbitrage  
    DELTA_NEUTRAL_3X = "delta_neutral_3x"      # 3-exchange delta neutral
    TRIANGULAR = "triangular"                  # Triangular arbitrage
    CROSS_EXCHANGE = "cross_exchange"          # Generic cross-exchange


class RiskParameters(msgspec.Struct):
    """Risk management parameters for arbitrage strategies."""
    max_position_size: float = 1000.0
    max_leverage: float = 3.0
    max_drawdown_pct: float = 5.0
    position_timeout_seconds: int = 300
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    max_slippage_pct: float = 0.1


class SpreadThresholds(msgspec.Struct):
    """Spread thresholds for arbitrage entry/exit."""
    entry_threshold_bps: int = 10      # 0.1% minimum entry spread
    exit_threshold_bps: int = 5        # 0.05% minimum exit spread
    profit_target_bps: int = 8         # 0.08% profit target
    stop_loss_bps: int = 15            # 0.15% stop loss


class PositionInfo(msgspec.Struct):
    """Position information for a specific exchange."""
    exchange_role: str
    exchange_enum: ExchangeEnum
    side: Optional[Side] = None
    quantity: float = 0.0
    avg_price: float = 0.0
    unrealized_pnl: float = 0.0
    last_update: float = msgspec.field(default_factory=time.time)


class PerformanceMetrics(msgspec.Struct):
    """Performance tracking for arbitrage strategies."""
    total_trades: int = 0
    successful_trades: int = 0
    total_volume: float = 0.0
    total_profit: float = 0.0
    total_fees: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0
    win_rate: float = 0.0
    avg_trade_duration_seconds: float = 0.0
    sharpe_ratio: Optional[float] = None
    
    def update_trade_result(self, profit: float, duration: float):
        """Update metrics with new trade result."""
        self.total_trades += 1
        if profit > 0:
            self.successful_trades += 1
            if profit > self.max_profit:
                self.max_profit = profit
        else:
            if profit < self.max_loss:
                self.max_loss = profit
        
        self.total_profit += profit
        self.win_rate = self.successful_trades / self.total_trades if self.total_trades > 0 else 0.0
        
        # Update average duration
        current_avg = self.avg_trade_duration_seconds
        new_avg = ((current_avg * (self.total_trades - 1)) + duration) / self.total_trades
        self.avg_trade_duration_seconds = new_avg


class FlexibleArbitrageContext(TaskContext):
    """
    Flexible context for N-exchange arbitrage strategies.
    
    Supports various strategy types with configurable exchange roles,
    position tracking, and performance metrics.
    """
    
    # Strategy identification
    strategy_type: StrategyType
    symbol: Symbol
    exchange_roles: Dict[str, ExchangeRole] = msgspec.field(default_factory=dict)
    
    # Configuration
    base_position_size: float = 100.0
    risk_params: RiskParameters = msgspec.field(default_factory=RiskParameters)
    spread_thresholds: SpreadThresholds = msgspec.field(default_factory=SpreadThresholds)
    
    # Position tracking (per exchange role)
    positions: Dict[str, PositionInfo] = msgspec.field(default_factory=dict)
    
    # Delta neutrality (for applicable strategies)
    target_delta: float = 0.0
    current_delta: float = 0.0
    delta_tolerance: float = 0.05  # 5% tolerance
    last_rebalance_time: float = 0.0
    
    # Current opportunity
    current_spread_bps: Optional[int] = None
    opportunity_start_time: Optional[float] = None
    expected_profit: Optional[float] = None
    
    # Performance tracking
    performance: PerformanceMetrics = msgspec.field(default_factory=PerformanceMetrics)
    
    # Strategy-specific data (flexible dict for extensions)
    strategy_data: Dict[str, Any] = msgspec.field(default_factory=dict)
    
    def add_exchange_role(self, role_key: str, exchange_enum: ExchangeEnum, 
                         role_name: str, side: Optional[Side] = None,
                         max_position_size: Optional[float] = None):
        """Add an exchange role to the strategy."""
        self.exchange_roles[role_key] = ExchangeRole(
            exchange_enum=exchange_enum,
            role=role_name,
            side=side,
            max_position_size=max_position_size or self.base_position_size
        )
        
        # Initialize position info
        self.positions[role_key] = PositionInfo(
            exchange_role=role_name,
            exchange_enum=exchange_enum,
            side=side
        )
    
    def update_position(self, role_key: str, quantity: float, 
                       avg_price: float, side: Optional[Side] = None):
        """Update position information for an exchange role."""
        if role_key in self.positions:
            self.positions[role_key] = msgspec.structs.replace(
                self.positions[role_key],
                quantity=quantity,
                avg_price=avg_price,
                side=side or self.positions[role_key].side,
                last_update=time.time()
            )
    
    def get_total_position_value(self) -> float:
        """Calculate total position value across all exchanges."""
        total_value = 0.0
        for position in self.positions.values():
            value = position.quantity * position.avg_price
            total_value += value
        return total_value
    
    def get_net_delta(self) -> float:
        """Calculate net delta exposure across all positions."""
        net_delta = 0.0
        for position in self.positions.values():
            if position.side == Side.BUY:
                net_delta += position.quantity
            elif position.side == Side.SELL:
                net_delta -= position.quantity
        return net_delta
    
    def is_delta_neutral(self) -> bool:
        """Check if positions are delta neutral within tolerance."""
        current_delta = abs(self.get_net_delta())
        return current_delta <= self.delta_tolerance
    
    def record_trade_completion(self, profit: float, duration: float):
        """Record completion of an arbitrage trade."""
        self.performance.update_trade_result(profit, duration)


class SpotSpotArbitrageContext(FlexibleArbitrageContext, kw_only=True):
    """Context for spot-to-spot arbitrage between two exchanges."""
    
    strategy_type: StrategyType = StrategyType.SPOT_SPOT
    
    # Spot-specific configuration
    min_volume_threshold: float = 1000.0  # Minimum volume for execution
    price_update_frequency: float = 0.1  # 100ms price update interval
    


class SpotFuturesArbitrageContext(FlexibleArbitrageContext, kw_only=True):
    """Context for spot-futures arbitrage strategies."""
    
    strategy_type: StrategyType = StrategyType.SPOT_FUTURES
    
    # Futures-specific configuration
    futures_leverage: float = 1.0
    funding_rate_threshold: Optional[float] = None
    contract_multiplier: float = 1.0
    margin_requirement: float = 0.1  # 10% margin
    


class DeltaNeutral3ExchangeContext(FlexibleArbitrageContext, kw_only=True):
    """Context for 3-exchange delta neutral arbitrage."""
    
    strategy_type: StrategyType = StrategyType.DELTA_NEUTRAL_3X
    
    # 3-exchange specific configuration
    primary_exchange_role: str = "primary_spot"
    hedge_exchange_role: str = "hedge_futures"
    arbitrage_exchange_role: str = "arbitrage_spot"
    
    # Rebalancing parameters
    rebalance_frequency_seconds: int = 60  # Rebalance every minute
    min_rebalance_amount: float = 10.0
    


class TriangularArbitrageContext(FlexibleArbitrageContext, kw_only=True):
    """Context for triangular arbitrage within a single exchange."""
    
    strategy_type: StrategyType = StrategyType.TRIANGULAR
    
    # Triangular arbitrage configuration
    base_currency: str = "USDT"
    intermediate_currency: str = "BTC"
    target_currency: str = "ETH"
    
    # Trading pairs for triangular path
    pair_1: str = "BTC/USDT"  # Base -> Intermediate
    pair_2: str = "ETH/BTC"   # Intermediate -> Target  
    pair_3: str = "ETH/USDT"  # Target -> Base
    


# Factory functions for creating strategy contexts

def create_spot_spot_context(
    symbol: Symbol,
    exchange1: ExchangeEnum,
    exchange2: ExchangeEnum,
    base_position_size: float = 100.0,
    entry_threshold_bps: int = 10
) -> SpotSpotArbitrageContext:
    """Create context for spot-spot arbitrage strategy."""
    context = SpotSpotArbitrageContext(
        symbol=symbol,
        base_position_size=base_position_size,
        spread_thresholds=SpreadThresholds(entry_threshold_bps=entry_threshold_bps)
    )
    
    context.add_exchange_role("exchange1", exchange1, "primary_spot", Side.BUY)
    context.add_exchange_role("exchange2", exchange2, "target_spot", Side.SELL)
    
    return context


def create_spot_futures_context(
    symbol: Symbol,
    spot_exchange: ExchangeEnum,
    futures_exchange: ExchangeEnum,
    base_position_size: float = 100.0,
    futures_leverage: float = 1.0,
    entry_threshold_bps: int = 10
) -> SpotFuturesArbitrageContext:
    """Create context for spot-futures arbitrage strategy."""
    context = SpotFuturesArbitrageContext(
        symbol=symbol,
        base_position_size=base_position_size,
        futures_leverage=futures_leverage,
        spread_thresholds=SpreadThresholds(entry_threshold_bps=entry_threshold_bps)
    )
    
    context.add_exchange_role("spot", spot_exchange, "spot_trading", Side.BUY)
    context.add_exchange_role("futures", futures_exchange, "futures_hedge", Side.SELL)
    
    return context


def create_delta_neutral_3x_context(
    symbol: Symbol,
    primary_spot: ExchangeEnum,
    hedge_futures: ExchangeEnum,
    arbitrage_spot: ExchangeEnum,
    base_position_size: float = 100.0,
    entry_threshold_bps: int = 10
) -> DeltaNeutral3ExchangeContext:
    """Create context for 3-exchange delta neutral arbitrage strategy."""
    context = DeltaNeutral3ExchangeContext(
        symbol=symbol,
        base_position_size=base_position_size,
        spread_thresholds=SpreadThresholds(entry_threshold_bps=entry_threshold_bps)
    )
    
    context.add_exchange_role("primary_spot", primary_spot, "primary_spot", Side.BUY)
    context.add_exchange_role("hedge_futures", hedge_futures, "hedge_futures", Side.SELL)
    context.add_exchange_role("arbitrage_spot", arbitrage_spot, "arbitrage_target")
    
    return context


def create_triangular_context(
    base_currency: str,
    intermediate_currency: str,
    target_currency: str,
    exchange: ExchangeEnum,
    base_position_size: float = 100.0,
    entry_threshold_bps: int = 5
) -> TriangularArbitrageContext:
    """Create context for triangular arbitrage strategy."""
    # Create symbol from base and target currencies
    from exchanges.structs.types import AssetName
    symbol = Symbol(base=AssetName(target_currency), quote=AssetName(base_currency))
    
    context = TriangularArbitrageContext(
        symbol=symbol,
        base_position_size=base_position_size,
        base_currency=base_currency,
        intermediate_currency=intermediate_currency,
        target_currency=target_currency,
        pair_1=f"{intermediate_currency}/{base_currency}",
        pair_2=f"{target_currency}/{intermediate_currency}",
        pair_3=f"{target_currency}/{base_currency}",
        spread_thresholds=SpreadThresholds(entry_threshold_bps=entry_threshold_bps)
    )
    
    context.add_exchange_role("triangular", exchange, "triangular_arbitrage")
    
    return context


# Utility functions for context management

def serialize_context(context: FlexibleArbitrageContext) -> str:
    """Serialize context to JSON string for persistence."""
    return msgspec.json.encode(context).decode()


def deserialize_context(json_str: str, context_type: type) -> FlexibleArbitrageContext:
    """Deserialize context from JSON string."""
    return msgspec.json.decode(json_str.encode(), type=context_type)


def validate_context(context: FlexibleArbitrageContext) -> List[str]:
    """Validate context configuration and return list of errors."""
    errors = []
    
    # Check required fields
    if not context.symbol:
        errors.append("Symbol is required")
    
    if not context.exchange_roles:
        errors.append("At least one exchange role is required")
    
    if context.base_position_size <= 0:
        errors.append("Base position size must be positive")
    
    # Strategy-specific validation
    if context.strategy_type == StrategyType.SPOT_FUTURES:
        if len(context.exchange_roles) != 2:
            errors.append("Spot-futures arbitrage requires exactly 2 exchanges")
    
    elif context.strategy_type == StrategyType.DELTA_NEUTRAL_3X:
        if len(context.exchange_roles) != 3:
            errors.append("Delta neutral 3x arbitrage requires exactly 3 exchanges")
    
    # Risk parameter validation
    if context.risk_params.max_drawdown_pct <= 0:
        errors.append("Max drawdown percentage must be positive")
    
    if context.risk_params.position_timeout_seconds <= 0:
        errors.append("Position timeout must be positive")
    
    return errors