# API Interfaces & Data Contracts

## Core Data Structures

### **Optimization Results**

```python
@dataclass
class OptimizationResult:
    """Result from parameter optimization analysis"""
    entry_threshold_pct: float      # Optimized entry threshold (e.g., 0.5 for 0.5%)
    exit_threshold_pct: float       # Optimized exit threshold (e.g., 0.1 for 0.1%)
    confidence_score: float         # Confidence in optimization (0.0-1.0)
    analysis_period_hours: int      # Hours of data analyzed
    mean_reversion_speed: float     # Half-life of spread convergence (hours)
    spread_volatility: float        # Standard deviation of spreads
    optimization_timestamp: float   # When optimization was performed
```

```python
@dataclass  
class SpreadAnalysis:
    """Detailed spread distribution analysis"""
    mean_spread: float              # Average spread in percentage
    std_spread: float              # Standard deviation of spreads
    percentiles: Dict[int, float]  # Percentile distribution {25: -0.1, 50: 0.05, ...}
    autocorrelation: List[float]   # Autocorrelation at different lags
    half_life_hours: float         # Mean reversion half-life
    regime_changes: int            # Number of detected regime changes
```

```python
@dataclass
class MeanReversionMetrics:
    """Mean reversion characteristics of spreads"""
    half_life: float               # Time for 50% reversion (hours)
    reversion_speed: float         # Speed coefficient  
    long_term_mean: float          # Long-term spread equilibrium
    volatility_clustering: bool    # Whether volatility clusters
    adf_statistic: float          # Augmented Dickey-Fuller test result
    p_value: float                # P-value for stationarity test
```

## Core Interfaces

### **1. Parameter Optimizer Interface**

```python
class DeltaArbitrageOptimizer:
    """Main optimization engine for delta arbitrage parameters"""
    
    def __init__(self, 
                 target_hit_rate: float = 0.7,
                 min_trades_per_day: int = 5,
                 max_drawdown_tolerance: float = 0.02):
        """Initialize optimizer with target constraints"""
        
    async def optimize_parameters(self, 
                                df: pd.DataFrame,
                                lookback_hours: int = 24) -> OptimizationResult:
        """
        Optimize entry/exit thresholds based on historical data
        
        Args:
            df: Historical book ticker data with columns:
                ['timestamp', 'spot_ask_price', 'spot_bid_price', 
                 'fut_ask_price', 'fut_bid_price']
            lookback_hours: Hours of historical data to analyze
            
        Returns:
            OptimizationResult with optimized parameters
        """
        
    def analyze_spread_distribution(self, df: pd.DataFrame) -> SpreadAnalysis:
        """Analyze spread characteristics for optimization"""
        
    def validate_parameters(self, 
                          entry_threshold: float, 
                          exit_threshold: float) -> bool:
        """Validate that parameters meet safety constraints"""
```

### **2. Live Strategy Interface**

```python
class SimpleDeltaArbitrageStrategy(BaseArbitrageStrategy):
    """Simplified delta arbitrage strategy with dynamic parameters"""
    
    def __init__(self,
                 symbol: Symbol,
                 optimizer: DeltaArbitrageOptimizer,
                 base_position_size: float = 100.0,
                 parameter_update_interval: int = 300):  # 5 minutes
        """Initialize strategy with optimizer integration"""
        
    async def update_parameters(self) -> bool:
        """Update strategy parameters using optimizer"""
        
    async def get_current_parameters(self) -> Dict[str, float]:
        """Get current entry/exit thresholds"""
        
    def get_optimization_status(self) -> Dict:
        """Get status of parameter optimization"""
```

### **3. Optimizer Bridge Interface**

```python
class OptimizerBridge:
    """Bridge between optimization engine and live strategy"""
    
    def __init__(self, 
                 optimizer: DeltaArbitrageOptimizer,
                 strategy: SimpleDeltaArbitrageStrategy):
        """Initialize bridge with optimizer and strategy"""
        
    async def update_strategy_parameters(self) -> bool:
        """Fetch new data, optimize, and update strategy"""
        
    async def get_recent_market_data(self, hours: int = 24) -> pd.DataFrame:
        """Fetch recent market data for optimization"""
        
    def should_update_parameters(self) -> bool:
        """Check if parameters need updating based on schedule"""
        
    def get_last_optimization_result(self) -> Optional[OptimizationResult]:
        """Get result of most recent optimization"""
```

## Data Flow Interfaces

### **Market Data Interface**

```python
# Input data format for optimization (from existing backtesting)
MarketDataFrame = pd.DataFrame[{
    'timestamp': pd.Timestamp,
    'spot_ask_price': float,
    'spot_bid_price': float, 
    'spot_ask_quantity': float,
    'spot_bid_quantity': float,
    'fut_ask_price': float,
    'fut_bid_price': float,
    'fut_ask_quantity': float,
    'fut_bid_quantity': float
}]
```

### **Strategy Configuration Interface**

```python
@dataclass
class DeltaArbitrageConfig:
    """Configuration for delta arbitrage strategy"""
    # Symbol configuration
    symbol: Symbol
    
    # Position sizing
    base_position_size: float = 100.0
    max_position_multiplier: float = 2.0
    
    # Optimization settings
    optimization_lookback_hours: int = 24
    parameter_update_interval_minutes: int = 5
    min_spread_data_points: int = 100
    
    # Safety constraints
    max_entry_threshold: float = 1.0  # Never enter above 1%
    min_exit_threshold: float = 0.05  # Never exit below 0.05%
    max_position_hold_minutes: int = 360  # 6 hours max hold
    
    # Performance targets
    target_hit_rate: float = 0.7
    min_daily_trades: int = 5
    max_drawdown_tolerance: float = 0.02
```

## Event Interfaces

### **Parameter Update Events**

```python
@dataclass
class ParameterUpdateEvent:
    """Event fired when parameters are updated"""
    timestamp: float
    old_entry_threshold: float
    new_entry_threshold: float
    old_exit_threshold: float
    new_exit_threshold: float
    confidence_score: float
    optimization_duration_ms: float
```

### **Optimization Status Events**

```python
@dataclass
class OptimizationStatusEvent:
    """Event for optimization process status"""
    timestamp: float
    status: str  # 'started', 'completed', 'failed'
    data_points_analyzed: int
    error_message: Optional[str] = None
    duration_ms: Optional[float] = None
```

## Integration with Existing Codebase

### **Compatibility with Existing Backtesting**

```python
# Existing function signature (from backtesting_direct_arbitrage.py)
def delta_neutral_backtest(
    df: pd.DataFrame,
    max_entry_cost_pct: float = 0.5,
    min_profit_pct: float = 0.1,
    max_hours: float = 6,
    spot_fee: float = 0.0005,
    fut_fee: float = 0.0005
) -> list:

# Enhanced version with optimization
async def optimized_delta_neutral_backtest(
    df: pd.DataFrame,
    optimizer: DeltaArbitrageOptimizer,
    optimization_window_hours: int = 24,
    static_params: Optional[Dict] = None
) -> Tuple[list, List[OptimizationResult]]:
    """
    Run backtest with dynamic parameter optimization
    
    Returns:
        (trades, optimization_history)
    """
```

### **Integration with MexcGateioFuturesStrategy**

```python
# Reuse these components from existing strategy:
# - ExchangeManager for order execution
# - BaseArbitrageStrategy for state management  
# - ArbitrageTaskContext for position tracking
# - Event-driven architecture with WebSocket feeds

# Simplifications in new strategy:
# - Remove complex rebalancing logic
# - Remove detailed balance validation
# - Remove advanced position tracking
# - Add optimizer integration
# - Add parameter update scheduling
```

## Error Handling Interfaces

### **Optimization Errors**

```python
class OptimizationError(Exception):
    """Base class for optimization errors"""
    pass

class InsufficientDataError(OptimizationError):
    """Raised when not enough data for reliable optimization"""
    pass

class ParameterValidationError(OptimizationError):
    """Raised when optimized parameters fail validation"""
    pass

class OptimizationTimeoutError(OptimizationError):
    """Raised when optimization takes too long"""
    pass
```

### **Strategy Update Errors**

```python
class ParameterUpdateError(Exception):
    """Raised when parameter update fails"""
    pass

class DataFetchError(Exception):
    """Raised when market data fetch fails"""
    pass
```

## Performance Interfaces

### **Performance Monitoring**

```python
@dataclass
class OptimizationPerformance:
    """Performance metrics for optimization process"""
    optimization_duration_ms: float
    data_points_processed: int
    memory_usage_mb: float
    cache_hit_ratio: float
    
@dataclass  
class StrategyPerformance:
    """Performance metrics for strategy execution"""
    avg_trade_execution_ms: float
    parameter_update_duration_ms: float
    memory_usage_mb: float
    uptime_percentage: float
```

## Testing Interfaces

### **Mock Data Generation**

```python
def generate_mock_market_data(
    hours: int = 24,
    spread_volatility: float = 0.002,
    trend_strength: float = 0.0
) -> pd.DataFrame:
    """Generate realistic mock market data for testing"""
    
def generate_mock_spread_regime(
    regime_type: str = 'mean_reverting',  # 'trending', 'volatile'
    duration_hours: int = 6
) -> pd.DataFrame:
    """Generate specific spread regime patterns for testing"""
```