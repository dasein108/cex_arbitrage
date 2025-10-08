# Symbol Analysis Tools

Comprehensive analytics tools for arbitrage strategy analysis across cryptocurrency trading symbols. These tools provide historical spread analysis, performance metrics, and quantitative insights for informed trading decisions.

## Overview

The Symbol Analysis Tools suite provides:

- **Historical Spread Analysis**: Analyze past arbitrage opportunities and market patterns
- **Performance Metrics**: Statistical analysis including volatility, trends, and percentiles  
- **Cross-Exchange Analysis**: Compare spreads between Gate.io, MEXC, and other exchanges
- **Quantitative Insights**: Data-driven recommendations for trading strategies
- **Real-time Data Integration**: Direct database connection to production trading data

## Quick Start

### Basic Historical Analysis

Analyze NEIROETH historical spreads from the project root:

```bash
cd /Users/dasein/dev/cex_arbitrage/
python -m src.applications.tools.analyze_symbol_simplified --symbol NEIROETH --quote USDT
```

### Extended Analysis with Custom Parameters

```bash
# Analyze BTC with 48-hour historical data
python -m src.applications.tools.analyze_symbol_simplified --symbol BTC --quote USDT --hours 48

# Analyze ETH with specific exchanges
python -m src.applications.tools.analyze_symbol_simplified --symbol ETH --quote USDT --exchanges GATEIO_SPOT,MEXC_SPOT

# Save results to JSON file
python -m src.applications.tools.analyze_symbol_simplified --symbol NEIROETH --quote USDT --output json --save analysis_results.json
```

## Core Tools

### 1. analyze_symbol_simplified.py

**Purpose**: Streamlined historical spread analysis for quantitative trading insights

**Features**:
- Historical arbitrage opportunity analysis
- Statistical spread metrics (mean, median, percentiles)
- Volatility regime classification
- Trading recommendations based on patterns
- Auto-detection of best spread type

**Usage**:
```bash
python -m src.applications.tools.analyze_symbol_simplified [OPTIONS]
```

**Required Arguments**:
- `--symbol`: Base symbol to analyze (e.g., NEIROETH, BTC, ETH)
- `--quote`: Quote currency (default: USDT)

**Optional Arguments**:
- `--hours`: Hours of historical data to analyze (default: 24)
- `--exchanges`: Comma-separated exchange list (default: GATEIO_SPOT,GATEIO_FUTURES,MEXC_SPOT)
- `--spread-type`: Spread analysis type (default: auto)
- `--output`: Output format (pretty/json, default: pretty)
- `--save`: Save results to file

**Expected Results**:
```
HISTORICAL PERFORMANCE ANALYSIS
==================================================
Symbol: NEIROETH/USDT
Timestamp: 2025-10-08T12:34:56.789Z
Period: 24 hours
Samples: 1,425

SPREAD STATISTICS
Mean Spread: 0.1245%
Median Spread: 0.0987%
Range: 0.0123% - 0.8765%
Std Deviation: 0.0876%

PERCENTILES
25th: 0.0654%
75th: 0.1543%
90th: 0.2345%
95th: 0.3456%
99th: 0.6789%

MARKET ANALYSIS
Trend: expanding
Volatility Regime: medium
Opportunities per Hour: 2.35
Profitable Opportunities: 56

RECOMMENDATIONS
• HIGH ACTIVITY: Strong arbitrage potential with frequent opportunities
• EXPANDING SPREADS: Increasing arbitrage opportunities expected
• WIDE SPREADS: Excellent profit potential with proper execution
```

### 2. data_fetcher.py

**Purpose**: High-performance data retrieval from TimescaleDB for any trading symbol

**Features**:
- Multi-exchange data aggregation (Gate.io Spot/Futures, MEXC Spot)
- Optimized database queries with symbol ID caching
- HFT-compliant (no real-time data caching)
- Unified snapshot format for cross-exchange analysis

**Key Classes**:
- `MultiSymbolDataFetcher`: Main data retrieval interface
- `UnifiedSnapshot`: Cross-exchange data structure

### 3. spread_analyzer_simplified.py

**Purpose**: Statistical analysis engine for spread patterns

**Features**:
- Auto-detection of best spread type (cross-exchange vs internal futures)
- Comprehensive statistical analysis (volatility, trends, percentiles)
- Opportunity identification and rate calculation
- Performance optimized for large datasets

**Key Classes**:
- `SpreadAnalyzer`: Main analysis engine
- `SpreadStatistics`: Statistical results container

## Database Requirements

The tools require connection to a TimescaleDB instance with:

**Required Tables**:
- `book_ticker_snapshots`: Real-time orderbook data
- `symbols`: Symbol configuration and mapping
- `exchanges`: Exchange metadata

**Environment Variables**:
```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=arbitrage_data
POSTGRES_USER=arbitrage_user
POSTGRES_PASSWORD=your_password
```

## Python API Usage

### Programmatic Access

```python
import asyncio
from src.applications.tools import MultiSymbolDataFetcher, SpreadAnalyzer
from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName

async def analyze_symbol():
    # Create symbol
    symbol = Symbol(base=AssetName("NEIROETH"), quote=AssetName("USDT"))
    
    # Initialize components
    data_fetcher = MultiSymbolDataFetcher(symbol)
    analyzer = SpreadAnalyzer(data_fetcher)
    
    # Initialize database connection
    await data_fetcher.initialize()
    
    # Get historical statistics
    stats = await analyzer.get_historical_statistics(hours_back=24)
    print(f"Mean spread: {stats.mean_spread:.4f}%")
    print(f"Opportunities: {stats.profitable_opportunities}")
    
    # Get volatility metrics
    volatility = await analyzer.get_volatility_metrics()
    print(f"Volatility regime: {volatility['volatility_regime']}")

# Run analysis
asyncio.run(analyze_symbol())
```

### Custom Exchange Configuration

```python
# Analyze with specific exchanges
exchanges = {
    'EXCHANGE_1': 'GATEIO_SPOT',
    'EXCHANGE_2': 'MEXC_SPOT'
}

data_fetcher = MultiSymbolDataFetcher(symbol, exchanges)
```

## Performance Characteristics

### Expected Performance Metrics

- **Database Query Latency**: <10ms for 24-hour historical data
- **Analysis Processing**: <50ms for 1,000+ samples
- **Memory Usage**: <100MB for typical analysis workloads
- **Throughput**: 10+ symbols/minute for batch analysis

### Optimization Features

- **Symbol ID Caching**: Eliminates repeated database lookups
- **Bulk Data Retrieval**: Minimizes database round trips  
- **msgspec Serialization**: Zero-copy data structures
- **Vectorized Calculations**: NumPy-optimized statistical analysis

## Output Formats

### Pretty Format (Default)

Human-readable text output with formatted tables and recommendations.

### JSON Format

Structured data output for programmatic consumption:

```json
{
  "timestamp": "2025-10-08T12:34:56.789Z",
  "symbol": "NEIROETH/USDT",
  "analysis_period": {
    "hours_back": 24,
    "spread_type": "gateio_mexc",
    "sample_count": 1425
  },
  "historical_statistics": {
    "mean_spread_pct": 0.1245,
    "median_spread_pct": 0.0987,
    "std_deviation": 0.0876,
    "percentiles": {
      "p25": 0.0654,
      "p75": 0.1543,
      "p95": 0.3456
    }
  },
  "market_analysis": {
    "trend_direction": "expanding",
    "volatility_regime": "medium",
    "opportunity_rate_per_hour": 2.35
  },
  "recommendations": [
    "HIGH ACTIVITY: Strong arbitrage potential with frequent opportunities",
    "EXPANDING SPREADS: Increasing arbitrage opportunities expected"
  ]
}
```

## Trading Insights

### Spread Analysis Types

1. **Cross-Exchange Arbitrage** (`gateio_mexc`):
   - Gate.io vs MEXC price differences
   - Best for high-frequency arbitrage strategies
   - Requires fast execution and risk management

2. **Internal Futures Spread** (`internal_futures`):
   - Gate.io spot vs futures price differences  
   - Best for delta-neutral strategies
   - Lower execution risk, funding rate considerations

3. **Auto-Detection** (`auto`):
   - Automatically selects best available spread type
   - Recommended for initial analysis

### Recommendation Categories

- **HIGH/LOW ACTIVITY**: Opportunity frequency assessment
- **VOLATILITY REGIME**: Risk management guidance
- **TREND DIRECTION**: Market pattern identification  
- **SPREAD WIDTH**: Profitability potential

### Risk Considerations

- **High Volatility**: Use smaller position sizes and tighter risk management
- **Low Volatility**: Stable conditions, suitable for larger positions
- **Expanding Spreads**: Increasing opportunities but higher risk
- **Contracting Spreads**: Decreasing profitability potential

## Troubleshooting

### Common Issues

1. **Database Connection Errors**:
   ```bash
   # Verify environment variables
   echo $POSTGRES_HOST $POSTGRES_PORT $POSTGRES_DB
   
   # Test database connectivity
   psql -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER -d $POSTGRES_DB -c "\dt"
   ```

2. **Import Errors**:
   ```bash
   # Ensure you're running from project root
   cd /Users/dasein/dev/cex_arbitrage/
   
   # Verify Python path
   python -c "import sys; print('\n'.join(sys.path))"
   ```

3. **No Historical Data**:
   - Check if symbol exists in database
   - Verify data collection is running  
   - Try different time periods (--hours parameter)

### Debug Mode

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Integration Examples

### Batch Symbol Analysis

```bash
#!/bin/bash
# Analyze multiple symbols
symbols=("BTC" "ETH" "NEIROETH" "SOL" "DOGE")

for symbol in "${symbols[@]}"; do
    echo "Analyzing $symbol..."
    python -m src.applications.tools.analyze_symbol_simplified \
        --symbol "$symbol" \
        --quote USDT \
        --hours 24 \
        --output json \
        --save "analysis_${symbol}.json"
done
```

### Strategy Development Pipeline

```python
# 1. Historical Analysis
stats = await analyzer.get_historical_statistics(hours_back=168)  # 1 week

# 2. Strategy Parameters
entry_threshold = stats.p75  # 75th percentile as entry trigger
exit_threshold = stats.p25   # 25th percentile as exit trigger

# 3. Risk Assessment
volatility = await analyzer.get_volatility_metrics()
position_size = base_size * (1.0 / volatility['coefficient_of_variation'])

# 4. Implementation
if stats.opportunity_rate > 2.0:  # At least 2 opportunities per hour
    deploy_strategy(symbol, entry_threshold, exit_threshold, position_size)
```

---

## Support

For technical issues or feature requests:
1. Check the [PROJECT_GUIDES.md](../../../PROJECT_GUIDES.md) for development patterns
2. Review the [HFT Requirements Compliance](../../../specs/performance/hft-requirements-compliance.md)
3. Contact the HFT development team

**Last Updated**: October 2025
**Version**: 1.0.0