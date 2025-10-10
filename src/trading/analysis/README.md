# Trading Analysis Scripts Documentation

This directory contains HFT-optimized trading analysis tools for the CEX arbitrage engine. All scripts are designed for high-frequency trading environments with sub-millisecond performance targets.

## 📊 Available Analysis Tools

### 1. Strategy Backtester (`strategy_backtester.py`)

**Purpose**: HFT-optimized backtesting engine for delta-neutral spot-futures arbitrage strategies.

**Key Features**:
- Compatible with MexcGateioFuturesStrategy for real strategy testing
- Uses existing database infrastructure with normalized schema
- msgspec.Struct models for maximum performance
- Parallel database queries for HFT requirements
- Realistic execution modeling with slippage and fees

**Usage Example**:
```python
from src.trading.analysis.strategy_backtester import HFTStrategyBacktester
from exchanges.structs.common import Symbol, AssetName
from db.cache import initialize_symbol_cache
from config.config_manager import HftConfig
from db.connection import initialize_database

async def run_backtest():
    # Initialize infrastructure
    config_manager = HftConfig()
    db_config = config_manager.get_database_config()
    await initialize_database(db_config)
    await initialize_symbol_cache()
    
    # Create symbol
    symbol = Symbol(base=AssetName('NEIROETH'), quote=AssetName('USDT'))
    
    # Create and run backtester
    backtester = HFTStrategyBacktester()
    results = await backtester.run_backtest(
        symbol=symbol,
        spot_exchange='MEXC_SPOT',
        futures_exchange='GATEIO_FUTURES',
        start_date='2025-10-05T12:10:00',
        end_date='2025-10-05T12:30:00'
    )
    
    print(f"Total Return: {results.total_return:.2%}")
    print(f"Total Trades: {results.total_trades}")
    print(f"Sharpe Ratio: {results.sharpe_ratio:.3f}")
```

**Performance Targets**:
- Database queries: <10ms for up to 10,000 records
- Backtest execution: <100ms per 1,000 data points
- Memory usage: <500MB for full day backtests

### 2. Delta Neutral Analyzer (`delta_neutral_analyzer.py`)

**Purpose**: Advanced analytics for delta-neutral arbitrage strategies with real-time risk monitoring.

**Key Features**:
- Real-time delta exposure calculation
- Position rebalancing recommendations
- Hedge ratio optimization
- Greeks calculation for risk management
- Performance attribution analysis

**Usage Example**:
```python
from src.trading.analysis.delta_neutral_analyzer import DeltaNeutralAnalyzer
from src.applications.hedged_arbitrage.strategy.mexc_gateio_futures_strategy import MexcGateioFuturesStrategy

# Initialize with strategy
analyzer = DeltaNeutralAnalyzer(strategy_instance)

# Analyze current delta exposure
delta_metrics = await analyzer.calculate_delta_metrics()
print(f"Current Delta: {delta_metrics.current_delta:.4f}")
print(f"Delta Drift: {delta_metrics.delta_drift:.4f}")

# Get rebalancing recommendations
rebalance_recs = await analyzer.get_rebalancing_recommendations()
for rec in rebalance_recs:
    print(f"Exchange: {rec.exchange}, Action: {rec.action}, Size: {rec.size}")
```

### 3. Risk Monitor (`risk_monitor.py`)

**Purpose**: Real-time risk monitoring and alerting system for HFT arbitrage operations.

**Key Features**:
- Position limit monitoring
- Drawdown tracking and alerts
- Correlation risk analysis
- Liquidity risk assessment
- Real-time P&L tracking

**Usage Example**:
```python
from src.trading.analysis.risk_monitor import RiskMonitor

# Initialize risk monitor
risk_monitor = RiskMonitor()

# Set up position limits
await risk_monitor.set_position_limits({
    'MEXC': {'max_position': 1000.0, 'max_leverage': 3.0},
    'GATEIO_FUTURES': {'max_position': 1000.0, 'max_leverage': 10.0}
})

# Start real-time monitoring
await risk_monitor.start_monitoring()

# Check current risk metrics
risk_summary = await risk_monitor.get_risk_summary()
print(f"Current Drawdown: {risk_summary.current_drawdown:.2%}")
print(f"VaR (95%): {risk_summary.var_95:.2f}")
```

### 4. Microstructure Analyzer (`microstructure_analyzer.py`)

**Purpose**: Market microstructure analysis for order book dynamics and execution optimization.

**Key Features**:
- Order flow imbalance (OFI) calculation
- Microprice estimation
- Volume imbalance analysis
- Optimal execution timing
- Market impact modeling

**Usage Example**:
```python
from src.trading.analysis.microstructure_analyzer import MicrostructureAnalyzer

# Initialize analyzer
analyzer = MicrostructureAnalyzer()

# Analyze order book microstructure
symbol = Symbol(base=AssetName('NEIROETH'), quote=AssetName('USDT'))
microstructure_data = await analyzer.analyze_symbol(
    symbol=symbol,
    exchange='MEXC_SPOT',
    lookback_minutes=60
)

print(f"OFI Score: {microstructure_data.ofi_score:.4f}")
print(f"Microprice: {microstructure_data.microprice:.6f}")
print(f"Volume Imbalance: {microstructure_data.volume_imbalance:.4f}")
```

## 🚀 Getting Started

### Prerequisites

1. **Database Setup**: Ensure the arbitrage database is running and accessible
2. **Environment Variables**: Set up database connection parameters
3. **Dependencies**: Install required packages

### Basic Setup

```bash
# Set database environment variables
export POSTGRES_PASSWORD=dev_password_2024
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=arbitrage_data
export POSTGRES_USER=arbitrage_user

# Run analysis with proper PYTHONPATH
PYTHONPATH=src python src/trading/analysis/strategy_backtester.py
```

### Configuration

All analysis tools use the centralized configuration system:

```python
from config.config_manager import HftConfig

config_manager = HftConfig()
db_config = config_manager.get_database_config()
```

## 📋 Analysis Workflow

### Typical Analysis Session

1. **Initialize Infrastructure**:
   ```python
   await initialize_database(db_config)
   await initialize_symbol_cache()
   ```

2. **Run Strategy Backtest**:
   ```python
   backtester = HFTStrategyBacktester()
   results = await backtester.run_backtest(...)
   ```

3. **Analyze Performance**:
   ```python
   analyzer = DeltaNeutralAnalyzer()
   metrics = await analyzer.analyze_backtest_results(results)
   ```

4. **Monitor Risk**:
   ```python
   risk_monitor = RiskMonitor()
   risk_summary = await risk_monitor.assess_strategy_risk(results)
   ```

### Performance Optimization

- **Database Queries**: All tools use parallel queries for HFT performance
- **Memory Management**: msgspec.Struct models minimize allocation overhead
- **Caching**: Symbol cache provides sub-microsecond lookups
- **Async Operations**: Full async/await support for non-blocking operations

## 🔧 Integration with Strategy Framework

### MexcGateioFuturesStrategy Integration

The analysis tools are specifically designed to work with the MexcGateioFuturesStrategy:

```python
from src.applications.hedged_arbitrage.strategy.mexc_gateio_futures_strategy import (
    MexcGateioFuturesStrategy,
    MexcGateioFuturesContext
)

# Create strategy context for backtesting
strategy_context = MexcGateioFuturesContext(
    symbol=symbol,
    base_position_size=100.0,
    entry_threshold_pct=0.5
)

# Run comprehensive analysis
backtester = HFTStrategyBacktester()
results = await backtester.run_backtest(...)

# Analyze with strategy-specific tools
analyzer = DeltaNeutralAnalyzer()
performance = await analyzer.analyze_results(results, strategy_context)
```

## 📊 Output and Results

### Backtest Results Structure

```python
class BacktestResults(msgspec.Struct):
    total_return: float          # Overall return percentage
    total_trades: int           # Number of completed trades
    final_capital: float        # Final capital amount
    max_drawdown: float         # Maximum drawdown percentage
    sharpe_ratio: float         # Risk-adjusted return
    win_rate: float            # Percentage of profitable trades
    avg_trade_pnl: float       # Average profit per trade
    trades: List[Trade]        # Individual trade details
```

### Performance Metrics

All analysis tools provide comprehensive performance metrics:
- Execution latency (target: <1ms)
- Database query performance (target: <10ms)
- Memory usage monitoring
- Error rates and recovery statistics

## 🎯 Best Practices

1. **Always initialize database and cache before running analysis**
2. **Use appropriate date ranges with available data**
3. **Monitor memory usage for large backtests**
4. **Validate results with multiple time periods**
5. **Use realistic execution parameters (slippage, fees)**
6. **Implement proper error handling for production use**

## ⚠️ Important Notes

- **Database Schema**: Tools are compatible with both normalized and legacy schemas
- **Performance**: All tools target HFT performance requirements (<1ms latency)
- **Error Handling**: Comprehensive error handling with detailed logging
- **Production Ready**: All components tested for high-frequency trading environments

For specific usage examples and advanced configuration, refer to the individual script documentation and the examples in the `/examples` directory.