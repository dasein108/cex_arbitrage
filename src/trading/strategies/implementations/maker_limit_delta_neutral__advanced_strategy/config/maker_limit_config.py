"""
Configuration for Maker Limit Order Strategy with Delta-Neutral Hedging

Provides comprehensive configuration structure for the market making strategy
that places limit orders on spot exchange with safe offsets and executes
immediate futures hedges to maintain delta neutrality.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
from exchanges.structs import Symbol, ExchangeEnum


@dataclass
class MakerLimitConfig:
    """Configuration for maker limit order strategy with delta-neutral hedging"""
    
    # Symbol and exchange configuration
    symbol: Symbol
    spot_exchange: ExchangeEnum
    futures_exchange: ExchangeEnum
    
    # Order placement parameters
    base_offset_ticks: int = 2  # Base offset from best bid/ask
    max_offset_ticks: int = 15  # Maximum allowed offset
    position_size_usd: float = 100.0  # Base position size
    
    # Risk management thresholds
    max_volatility_threshold: float = 0.15  # 15% max volatility ratio
    min_correlation: float = 0.7  # Minimum spot-futures correlation
    max_basis_volatility_pct: float = 0.15  # 15% max basis volatility
    
    # Circuit breaker thresholds
    volatility_circuit_breaker: float = 0.20  # 20% volatility spike triggers stop
    correlation_circuit_breaker: float = 0.6   # <60% correlation emergency stop
    volume_circuit_breaker: float = 0.5       # <50% of avg volume triggers stop
    trend_circuit_breaker: float = 0.05       # >5% trend strength triggers caution
    
    # Dynamic adjustment parameters
    volatility_multiplier: float = 1.5  # Offset adjustment during high volatility
    trend_multiplier: float = 0.7       # Offset reduction in mean-reverting markets
    emergency_multiplier: float = 1.3   # +30% offset during price spikes
    
    # Liquidity tier adjustments (from analyzer)
    liquidity_adjustment: Dict[str, float] = field(default_factory=lambda: {
        'ULTRA_LOW': 1.5,  # +50% offset for ultra-low liquidity (<50k/hour)
        'LOW': 1.3,        # +30% offset for low liquidity (50k-100k/hour)
        'MEDIUM': 1.0,     # No adjustment (100k-500k/hour)
        'HIGH': 0.8        # -20% offset for high liquidity (>500k/hour)
    })
    
    # Performance and timing parameters
    loop_interval_ms: int = 100  # Main loop interval in milliseconds
    order_update_threshold: float = 0.001  # Re-quote if price moves >0.1%
    hedge_execution_timeout_ms: int = 100  # 100ms timeout for hedge execution
    max_loop_time_ms: float = 50  # HFT compliance: <50ms loop time
    
    # Position limits and safety
    max_position_size_multiplier: float = 3.0  # Max 3x base position
    delta_tolerance_pct: float = 0.01  # 1% delta tolerance for neutrality
    max_daily_trades: int = 500  # Daily trade limit
    
    # Market regime parameters (from analyzer)
    rsi_oversold: float = 30  # RSI oversold threshold
    rsi_overbought: float = 70  # RSI overbought threshold
    trend_strength_threshold: float = 0.02  # 2% trend detection
    spike_sigma_threshold: float = 2.5  # 2.5 sigma for spike detection
    
    # Circuit breaker cooldown periods
    volatility_cooldown_seconds: int = 300  # 5 minutes
    correlation_cooldown_seconds: int = 600  # 10 minutes
    emergency_cooldown_seconds: int = 180   # 3 minutes
    
    # Performance monitoring
    metrics_log_interval_seconds: int = 10  # Log metrics every 10 seconds
    trade_history_max_size: int = 1000      # Keep last 1000 trades in memory
    
    def __post_init__(self):
        """Validate configuration parameters"""
        # Validate offset parameters
        if self.base_offset_ticks < 1:
            raise ValueError("base_offset_ticks must be >= 1")
        if self.max_offset_ticks < self.base_offset_ticks:
            raise ValueError("max_offset_ticks must be >= base_offset_ticks")
            
        # Validate risk thresholds
        if not 0 < self.min_correlation <= 1:
            raise ValueError("min_correlation must be between 0 and 1")
        if self.max_volatility_threshold <= 0:
            raise ValueError("max_volatility_threshold must be positive")
            
        # Validate circuit breaker thresholds
        if self.correlation_circuit_breaker >= self.min_correlation:
            raise ValueError("correlation_circuit_breaker must be < min_correlation")
            
        # Validate position size
        if self.position_size_usd <= 0:
            raise ValueError("position_size_usd must be positive")
            
        # Validate timing parameters
        if self.hedge_execution_timeout_ms <= 0:
            raise ValueError("hedge_execution_timeout_ms must be positive")
        if self.loop_interval_ms <= 0:
            raise ValueError("loop_interval_ms must be positive")
    
    def get_liquidity_multiplier(self, liquidity_tier: str) -> float:
        """Get liquidity adjustment multiplier for given tier"""
        return self.liquidity_adjustment.get(liquidity_tier, 1.0)
    
    def calculate_max_position_size(self) -> float:
        """Calculate maximum allowed position size"""
        return self.position_size_usd * self.max_position_size_multiplier
    
    def is_within_delta_tolerance(self, net_delta: float, position_size: float) -> bool:
        """Check if net delta is within tolerance for delta neutrality"""
        if position_size == 0:
            return True
        delta_ratio = abs(net_delta / position_size)
        return delta_ratio <= self.delta_tolerance_pct


@dataclass
class MakerLimitRuntimeState:
    """Runtime state tracking for maker limit strategy"""
    
    # Trading state
    is_trading_active: bool = True
    last_order_update_time: float = 0
    last_market_data_time: float = 0
    
    # Circuit breaker state
    circuit_breaker_active: bool = False
    circuit_breaker_reason: str = ""
    circuit_breaker_activation_time: float = 0
    circuit_breaker_cooldown_until: float = 0
    
    # Performance tracking
    total_trades_today: int = 0
    last_metrics_log_time: float = 0
    loop_performance_warnings: int = 0
    
    # Position tracking
    net_spot_position: float = 0.0
    net_futures_position: float = 0.0
    total_spot_volume: float = 0.0
    total_futures_volume: float = 0.0
    
    def calculate_net_delta(self) -> float:
        """Calculate current net delta exposure"""
        return self.net_spot_position + self.net_futures_position
    
    def reset_daily_counters(self):
        """Reset daily trading counters"""
        self.total_trades_today = 0
        self.total_spot_volume = 0.0
        self.total_futures_volume = 0.0
    
    def can_trade_today(self, max_daily_trades: int) -> bool:
        """Check if more trades allowed today"""
        return self.total_trades_today < max_daily_trades