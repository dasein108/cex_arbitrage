"""
HFT Arbitrage Framework - Data Structures

msgspec.Struct-based data structures for ultra-high-performance arbitrage operations.
All structures are frozen and hashable for optimal performance in HFT scenarios.

Design Principles:
- Zero-copy data structures using msgspec.Struct
- Frozen structures for thread safety and immutability
- Type safety with comprehensive validation
- Memory-efficient with pre-compiled constants
- HFT-optimized for sub-millisecond processing
"""

from __future__ import annotations

from enum import IntEnum
from typing import Dict, List, Optional, Any
from msgspec import Struct

from core.structs.common import Symbol, OrderSide, ExchangeName


class OpportunityType(IntEnum):
    """
    Arbitrage opportunity classification for strategic execution.
    
    HFT Performance: IntEnum provides O(1) comparisons and minimal memory overhead.
    """
    SPOT_SPOT = 1           # Cross-exchange spot arbitrage
    SPOT_FUTURES_HEDGE = 2  # Spot purchase + futures hedge for risk-free profit
    TRIANGULAR = 3          # Single exchange triangular arbitrage
    FUNDING_RATE = 4        # Futures funding rate arbitrage
    OPTIONS_PARITY = 5      # Options-futures parity arbitrage


class ArbitrageState(IntEnum):
    """
    Finite state machine states for atomic arbitrage operations.
    
    State Transitions:
    IDLE → DETECTING → OPPORTUNITY_FOUND → EXECUTING → COMPLETED/FAILED
    Any state can transition to RECOVERING for partial execution handling.
    """
    IDLE = 1                # Engine idle, monitoring markets
    DETECTING = 2           # Actively scanning for opportunities
    OPPORTUNITY_FOUND = 3   # Valid opportunity identified, preparing execution
    EXECUTING = 4           # Orders being placed atomically
    POSITION_OPEN = 5       # Partial execution, position needs completion
    RECOVERING = 6          # Handling partial execution or errors
    COMPLETED = 7           # Arbitrage cycle completed successfully
    FAILED = 8              # Operation failed, positions closed


class ExecutionStage(IntEnum):
    """
    Granular execution stages for atomic spot + futures operations.
    
    Critical for recovery from partial executions where spot succeeds
    but futures hedge fails, requiring precise state tracking.
    """
    PREPARING = 1           # Validating balances and positions
    SPOT_ORDERING = 2       # Placing spot market order
    SPOT_FILLED = 3         # Spot order filled, hedge required
    FUTURES_ORDERING = 4    # Placing futures hedge order
    FUTURES_FILLED = 5      # Futures hedge filled, arbitrage complete
    CLOSING_POSITION = 6    # Closing position due to error/timeout


class ArbitrageOpportunity(Struct, frozen=True):
    """
    Immutable arbitrage opportunity with complete execution parameters.
    
    HFT Design:
    - Frozen struct for thread safety and caching efficiency
    - Pre-calculated execution parameters to minimize computation
    - Decimal precision for exact price matching between exchanges
    - Comprehensive validation data for risk management
    """
    opportunity_id: str                    # Unique identifier for tracking
    opportunity_type: OpportunityType     # Strategy classification
    
    # Market Data (HFT CRITICAL: This data is NEVER cached - always fresh)
    symbol: Symbol                        # Trading pair symbol
    buy_exchange: ExchangeName           # Exchange to buy from
    sell_exchange: ExchangeName          # Exchange to sell to
    buy_price: float                     # Buy price (float for HFT performance)
    sell_price: float                    # Sell price (float for HFT performance)
    
    # Execution Parameters
    max_quantity: float                  # Maximum tradeable quantity
    profit_per_unit: float               # Profit per unit before fees
    total_profit_estimate: float         # Estimated total profit after fees
    profit_margin_bps: int               # Profit margin in basis points
    
    # Risk Metrics
    price_impact_estimate: float         # Estimated slippage impact
    execution_time_window_ms: int        # Maximum execution window (HFT target: <50ms)
    required_balance_buy: float          # Required balance on buy exchange
    required_balance_sell: float         # Required balance on sell exchange
    
    # Validation Data
    timestamp_detected: int              # Detection timestamp (milliseconds)
    market_depth_validated: bool         # Order book depth validated
    balance_validated: bool              # Sufficient balances confirmed
    risk_approved: bool                  # Risk management approval
    
    # Futures Hedge Parameters (for SPOT_FUTURES_HEDGE)
    futures_symbol: Optional[Symbol] = None      # Futures contract symbol
    hedge_ratio: Optional[float] = None          # Hedge ratio (typically 1.0)
    futures_price: Optional[float] = None        # Futures entry price
    
    def calculate_minimum_profit_threshold(self, min_profit_bps: int = 10) -> bool:
        """
        TODO: Implement minimum profit threshold validation.
        
        Logic Requirements:
        - Compare profit_margin_bps against minimum threshold
        - Account for gas fees, network congestion, execution risk
        - Consider time decay of opportunity vs execution speed
        - Include slippage estimates in profit calculations
        
        Questions:
        - Should threshold be dynamic based on market volatility?
        - How to handle different fee structures across exchanges?
        - Should we factor in inventory carrying costs?
        
        Performance: O(1) comparison, <1ms execution target
        """
        return self.profit_margin_bps >= min_profit_bps
    
    def is_execution_window_valid(self) -> bool:
        """
        TODO: Validate if opportunity is still within execution window.
        
        Logic Requirements:
        - Check current time against detection timestamp
        - Account for network latency and order placement time
        - Consider market volatility impact on execution window
        - Return False if window expired to prevent stale executions
        
        HFT Critical: This prevents execution on stale opportunities
        Target: Sub-millisecond validation
        """
        # TODO: Implement timestamp validation logic
        return True


class PositionEntry(Struct, frozen=True):
    """
    Immutable position record for atomic arbitrage operations.
    
    Tracks individual legs of multi-exchange arbitrage positions with
    precise decimal quantities and execution metadata for recovery.
    """
    position_id: str                     # Unique position identifier
    opportunity_id: str                  # Parent opportunity reference
    exchange: ExchangeName              # Exchange where position exists
    symbol: Symbol                      # Trading pair
    side: OrderSide                     # BUY or SELL
    quantity: float                     # Position size (float for HFT performance)
    entry_price: float                  # Average entry price
    
    # Execution Metadata
    order_id: str                       # Exchange order ID
    execution_timestamp: int            # Fill timestamp (milliseconds)
    execution_stage: ExecutionStage     # Stage when position created
    fees_paid: float                    # Total fees paid in quote currency
    
    # Position Management
    is_hedge: bool = False              # True if futures hedge position
    hedge_ratio: Optional[float] = None      # Hedge ratio if applicable
    requires_closing: bool = False      # True if position needs manual close
    
    # Recovery Information
    partial_fill: bool = False          # True if partially filled
    remaining_quantity: float = 0.0     # Unfilled quantity
    recovery_attempts: int = 0          # Number of recovery attempts
    
    def calculate_unrealized_pnl(self, current_price: float) -> float:
        """
        Calculate unrealized P&L for position monitoring.
        
        Logic Requirements:
        - Calculate P&L based on current market price
        - Account for position side (BUY vs SELL)
        - Include fees in P&L calculation
        - Handle different quote currencies between exchanges
        
        Performance: O(1) calculation, sub-millisecond target (optimized with float)
        """
        if self.side == OrderSide.BUY:
            # Long position: profit when price goes up
            pnl = (current_price - self.entry_price) * self.quantity
        else:
            # Short position: profit when price goes down
            pnl = (self.entry_price - current_price) * self.quantity
        
        # Subtract fees
        return pnl - self.fees_paid
    
    def is_position_stale(self, max_age_seconds: int = 300) -> bool:
        """
        TODO: Check if position is stale and needs attention.
        
        Logic Requirements:
        - Compare execution timestamp against current time
        - Consider position type (hedge vs directional)
        - Account for market hours and liquidity cycles
        - Flag positions requiring manual intervention
        
        HFT Critical: Stale positions increase risk exposure
        """
        # TODO: Implement staleness check
        return False


class ExecutionResult(Struct, frozen=True):
    """
    Immutable execution result for arbitrage operations.
    
    Comprehensive execution record with performance metrics
    and error handling information for system optimization.
    """
    execution_id: str                   # Unique execution identifier
    opportunity_id: str                 # Source opportunity reference
    final_state: ArbitrageState         # Final state after execution
    
    # Execution Performance
    total_execution_time_ms: int        # End-to-end execution time
    detection_to_execution_ms: int      # Time from detection to first order
    order_placement_time_ms: int       # Time to place all orders
    fill_confirmation_time_ms: int      # Time to confirm all fills
    
    # Financial Results
    positions_created: List[PositionEntry]  # All positions created
    realized_profit: float              # Actual profit realized (post-fees)
    total_fees_paid: float             # Sum of all exchange fees
    slippage_cost: float               # Total slippage vs expected prices
    
    # Execution Quality Metrics
    orders_placed: int                  # Total orders attempted
    orders_filled: int                  # Total orders successfully filled
    partial_fills: int                  # Number of partial fills
    execution_success_rate: float       # Fill rate percentage
    
    # Error Information
    errors_encountered: List[str]       # Any errors during execution
    recovery_actions_taken: List[str]   # Recovery steps performed
    requires_manual_review: bool        # Flags for manual intervention
    
    # Market Impact Analysis
    market_impact_bps: Optional[int] = None     # Measured market impact
    timing_analysis: Optional[Dict[str, Any]] = None  # Detailed timing breakdown
    
    def calculate_execution_efficiency(self) -> float:
        """
        Calculate overall execution efficiency score.
        
        Logic Requirements:
        - Combine execution time, slippage, and success rate
        - Weight factors based on HFT performance priorities
        - Normalize score to 0-100 scale for comparison
        - Consider market conditions impact on efficiency
        
        Performance: Ultra-fast float calculations for real-time monitoring
        """
        if self.orders_placed == 0:
            return 0.0
        
        # Efficiency factors (0-1 scale)
        time_efficiency = max(0.0, 1.0 - (self.total_execution_time_ms / 50.0))  # Target: <50ms
        fill_efficiency = self.execution_success_rate / 100.0  # Convert from percentage
        cost_efficiency = max(0.0, 1.0 - (abs(self.slippage_cost) / max(abs(self.realized_profit), 1.0)))
        
        # Weighted combination
        efficiency = (0.4 * time_efficiency + 0.4 * fill_efficiency + 0.2 * cost_efficiency) * 100.0
        return min(100.0, max(0.0, efficiency))
    
    def identify_performance_bottlenecks(self) -> List[str]:
        """
        TODO: Analyze execution for performance improvement opportunities.
        
        Logic Requirements:
        - Identify slowest components in execution pipeline
        - Compare against HFT performance targets (<50ms)
        - Detect network latency vs processing time issues
        - Flag suboptimal order routing decisions
        
        Performance Target: Sub-millisecond analysis
        Output: Actionable recommendations for optimization
        """
        # TODO: Implement bottleneck analysis
        return []


class RiskLimits(Struct, frozen=True):
    """
    Immutable risk management parameters for HFT arbitrage.
    
    Comprehensive risk controls with real-time validation
    and circuit breaker functionality for position protection.
    """
    # Position Size Limits
    max_position_size_usd: float        # Maximum position size in USD
    max_total_exposure_usd: float       # Maximum total exposure across all positions
    max_exchange_exposure_usd: float    # Maximum exposure per exchange
    max_symbol_exposure_usd: float      # Maximum exposure per trading pair
    
    # Profit and Loss Controls  
    max_daily_loss_usd: float           # Maximum daily loss threshold
    max_single_loss_usd: float          # Maximum loss per single arbitrage
    min_profit_margin_bps: int          # Minimum profit margin in basis points
    stop_loss_threshold_bps: int        # Stop loss threshold in basis points
    
    # Execution Risk Controls
    max_execution_time_ms: int          # Maximum allowed execution time
    max_slippage_bps: int              # Maximum acceptable slippage
    max_partial_fill_ratio: float       # Maximum partial fill ratio (0.1 = 10%)
    max_concurrent_operations: int      # Maximum concurrent arbitrage operations
    
    # Market Risk Parameters
    max_price_deviation_bps: int        # Maximum price deviation from fair value
    min_market_depth_usd: float        # Minimum order book depth required
    max_spread_bps: int                # Maximum bid-ask spread tolerance
    volatility_circuit_breaker_bps: int # Volatility circuit breaker threshold
    
    # Recovery and Error Handling
    max_recovery_attempts: int          # Maximum position recovery attempts
    recovery_timeout_seconds: int       # Timeout for recovery operations
    emergency_close_threshold_bps: int  # Emergency position close threshold
    
    def validate_opportunity_risk(self, opportunity: ArbitrageOpportunity) -> bool:
        """
        TODO: Validate opportunity against risk parameters.
        
        Logic Requirements:
        - Check profit margin against minimum threshold
        - Validate position size against exposure limits
        - Verify execution window against time limits
        - Assess market depth and liquidity requirements
        
        Questions:
        - Should validation be strict or allow risk manager override?
        - How to handle dynamic risk adjustment during volatile markets?
        - Should correlation risk be considered for multi-symbol positions?
        
        Performance: <1ms validation, critical path optimization
        """
        # TODO: Implement comprehensive risk validation
        return True
    
    def check_circuit_breakers(self, current_positions: List[PositionEntry]) -> List[str]:
        """
        TODO: Check all circuit breaker conditions.
        
        Logic Requirements:
        - Evaluate current exposure against all limits
        - Check P&L against daily and single operation limits
        - Assess market conditions against volatility thresholds
        - Identify which circuit breakers are triggered
        
        Return: List of triggered circuit breaker names
        HFT Critical: Must complete in <1ms for real-time protection
        """
        # TODO: Implement circuit breaker logic
        return []


class ArbitrageConfig(Struct, frozen=True):
    """
    Immutable configuration for arbitrage engine operation.
    
    Comprehensive configuration with HFT performance parameters,
    exchange-specific settings, and operational controls.
    """
    # Engine Configuration
    engine_name: str                    # Engine instance identifier
    enabled_opportunity_types: List[OpportunityType]  # Active arbitrage strategies
    enabled_exchanges: List[ExchangeName]  # Active exchange connections
    
    # Performance Parameters
    target_execution_time_ms: int       # Target execution time (HFT: <50ms)
    opportunity_scan_interval_ms: int   # Market scanning frequency
    position_monitor_interval_ms: int   # Position monitoring frequency
    balance_refresh_interval_ms: int    # Balance refresh frequency
    
    # Risk Management
    risk_limits: RiskLimits            # Comprehensive risk parameters
    enable_risk_checks: bool = True    # Enable real-time risk validation
    enable_circuit_breakers: bool = True  # Enable automated circuit breakers
    
    # Market Data Configuration
    enable_websocket_feeds: bool = True     # Use WebSocket for real-time data
    websocket_fallback_to_rest: bool = True  # Fallback to REST if WebSocket fails
    market_data_staleness_ms: int = 100     # Maximum data age before refresh
    
    # Exchange-Specific Settings
    exchange_specific_configs: Dict[ExchangeName, Dict[str, Any]] = {}
    
    # Operational Controls
    enable_dry_run: bool = False       # Paper trading mode
    enable_detailed_logging: bool = True  # Comprehensive operation logging
    enable_performance_metrics: bool = True  # Detailed performance tracking
    enable_recovery_mode: bool = True  # Automatic position recovery
    
    def validate_configuration(self) -> List[str]:
        """
        TODO: Validate complete configuration for consistency and safety.
        
        Logic Requirements:
        - Verify enabled exchanges have required configurations
        - Check performance parameters against HFT requirements
        - Validate risk limits for mathematical consistency
        - Ensure opportunity types match exchange capabilities
        
        Questions:
        - Should validation prevent startup or just warn?
        - How to handle configuration updates during operation?
        - Should validation include exchange connectivity tests?
        
        Return: List of configuration issues found
        """
        # TODO: Implement configuration validation
        return []
    
    def get_exchange_config(self, exchange: ExchangeName) -> Dict[str, Any]:
        """
        TODO: Get exchange-specific configuration parameters.
        
        Logic Requirements:
        - Return exchange-specific settings or defaults
        - Handle missing configurations gracefully
        - Merge with global defaults where applicable
        - Support dynamic configuration updates
        
        Performance: O(1) lookup, <1ms execution
        """
        # TODO: Implement exchange config lookup
        return self.exchange_specific_configs.get(exchange, {})