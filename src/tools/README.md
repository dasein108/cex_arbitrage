# CEX Arbitrage Tools

High-performance toolset for cryptocurrency arbitrage analysis across multiple exchanges. **Refactored to follow CLAUDE.md SOLID principles** with unified architecture and ~65% code reduction.

## Overview

**NEW: Unified Tool Architecture (v3.0)**

The tools have been refactored from 3 separate scripts (~1,400 lines) into a single unified tool (~500 lines) following CLAUDE.md standards:

- **SOLID Compliance**: Single responsibility components with proper interfaces
- **DRY Elimination**: Removed ~305 lines of duplicate code
- **Factory Pattern**: Uses proper ExchangeFactory instead of manual creation
- **Interface Usage**: Clean src-only architecture with BasePublicExchangeInterface
- **Performance**: HFT-compliant with <50ms latency targets

**Usage**:
```bash
python unified_arbitrage_tool.py discover [options]  # Symbol discovery
python unified_arbitrage_tool.py fetch [options]     # Data collection  
python unified_arbitrage_tool.py analyze [options]   # Spread analysis
```

### Quick Start (Unified Tool)

```bash
# Complete workflow using unified tool
python unified_arbitrage_tool.py discover --format detailed
python unified_arbitrage_tool.py fetch --days 3 --max-symbols 20
python unified_arbitrage_tool.py analyze --min-profit-score 30

# Get help for any operation
python unified_arbitrage_tool.py discover --help
python unified_arbitrage_tool.py fetch --help  
python unified_arbitrage_tool.py analyze --help
```

### Architecture Benefits

**SOLID Principles Implementation**:
- `ArbitrageToolController`: Single responsibility orchestration (SRP)
- `SymbolDiscoveryService`: Focused on symbol discovery only (SRP)
- `DataCollectionService`: Focused on data fetching only (SRP)  
- `AnalysisService`: Focused on spread analysis only (SRP)
- Interface-based dependencies (DIP)

**Code Reduction Achieved**:
- CLI parsing: ~150 lines → shared `CLIManager`
- Logging setup: ~25 lines → shared `LoggingConfigurator`
- Path resolution: ~30 lines → shared `PathResolver`
- Error handling: ~40 lines → shared `ErrorHandler`
- Main function patterns: ~60 lines → unified controller

## Legacy Tools (Deprecated but Available)

The original 3-script workflow is deprecated but still available for backward compatibility:

1. **[Symbol Discovery](#1-symbol-discovery)** - `cross_exchange_symbol_discovery.py`
2. **[Data Fetcher](#2-data-fetcher)** - `arbitrage_data_fetcher.py`
3. **[Spread Analyzer](#3-spread-analyzer)** - `arbitrage_analyzer.py`

### Key Improvements in v2.0

- **Modular Workflow**: Independent execution of each phase for better control
- **Rate Limiting**: Centralized `ExchangeRateLimiter` prevents API throttling
- **Fixed "Thundering Herd"**: Coordinated batch downloads prevent concurrent API conflicts
- **Optimized Data Period**: 3 days default (vs. months) for faster analysis
- **Enhanced Metrics**: 15 comprehensive CSV columns with profit scoring
- **HFT Compliance**: No real-time data caching, fresh API calls only

---

## 1. Symbol Discovery

**File**: `cross_exchange_symbol_discovery.py`

High-performance tool for analyzing symbol availability across multiple exchanges to identify arbitrage opportunities.

### Features

- **Multi-Exchange Analysis**: MEXC Spot, MEXC Futures, Gate.io Spot, Gate.io Futures
- **Stablecoin Equivalence**: USDT/USDC treated as unified USD_STABLE pairs
- **3-Tier Focus**: Filter major coins to focus on altcoin opportunities
- **Multiple Output Formats**: Matrix, detailed, summary, and filtered outputs
- **HFT Compliant**: No real-time data caching, fresh API calls only
- **Parallel Processing**: Async fetching from all exchanges simultaneously

### Quick Start

```bash
# Run discovery with default settings (detailed output, filter major coins)
python cross_exchange_symbol_discovery.py

# Generate arbitrage-ready matrix format
python cross_exchange_symbol_discovery.py --format matrix

# Include major coins in analysis
python cross_exchange_symbol_discovery.py --no-filter-major

# Generate summary only without saving
python cross_exchange_symbol_discovery.py --format summary --no-save
```

### Output Files

The discovery tool generates two key output files:

**1. JSON Results** (`symbol_discovery_detailed_YYYYMMDD_HHMMSS.json`)
```json
{
  "availability_matrix": {
    "ADA/USD_STABLE": {
      "mexc_spot": true,
      "mexc_futures": true, 
      "gateio_spot": true,
      "gateio_futures": true
    }
  },
  "statistics": {
    "four_way_opportunities": 45,
    "three_way_opportunities": 123,
    "total_symbols": 1247
  }
}
```

**2. Markdown Report** (`arbitrage_opportunities.md`)
- Four-way arbitrage opportunities (highest priority)
- Three-way arbitrage opportunities  
- Comprehensive statistics and insights

### Command Line Options

```bash
usage: cross_exchange_symbol_discovery.py [-h] [--format {summary,detailed,filtered,matrix}] 
                                         [--no-filter-major] [--no-save]

optional arguments:
  -h, --help            show this help message and exit
  --format {summary,detailed,filtered,matrix}
                        Output format (default: detailed)
  --no-filter-major     Include major coins (BTC, ETH, etc.) in analysis
  --no-save             Do not save output to file
```

### Performance Characteristics

- **Sub-30s Execution**: Complete 4-exchange analysis in <30 seconds
- **Parallel API Calls**: All exchanges queried simultaneously  
- **msgspec Processing**: Zero-copy JSON parsing for maximum speed
- **Connection Pooling**: Reuses existing RestClient connections
- **HFT Compliance**: No caching of real-time data per architectural rules

---

## 2. Data Fetcher

**File**: `arbitrage_data_fetcher.py`

Downloads historical 1-minute candles for symbols identified in discovery phase. Features intelligent rate limiting and coordinated batch processing.

### Features

- **Integrated Workflow**: Uses discovery results as input automatically
- **Rate Limiting**: Centralized `ExchangeRateLimiter` prevents API throttling  
- **Batch Coordination**: Eliminates "thundering herd" problem with controlled concurrency
- **Data Validation**: Comprehensive validation of collected data
- **Memory Efficient**: Streaming CSV writes with bounded memory usage
- **Progress Tracking**: Real-time progress indicators for large datasets

### Quick Start

```bash
# Fetch 3 days of data (default, optimized for speed)
python arbitrage_data_fetcher.py

# Fetch 7 days with custom symbol limit for testing
python arbitrage_data_fetcher.py --days 7 --max-symbols 10

# Use custom discovery file and data directory
python arbitrage_data_fetcher.py --discovery-file my_symbols.json --data-dir ./my_data

# Validate existing data without downloading new data
python arbitrage_data_fetcher.py --validate-only
```

### Rate Limiting Architecture

The data fetcher implements centralized rate limiting to prevent API throttling:

- **Gate.io**: Max 2 concurrent requests, 300ms delays  
- **MEXC**: Max 5 concurrent requests, 100ms delays
- **Coordination**: Global semaphores prevent concurrent API conflicts
- **Auto-Recovery**: Intelligent backoff with exponential delays

### Command Line Options

```bash
usage: arbitrage_data_fetcher.py [-h] [--discovery-file FILE] [--data-dir DIR] 
                                [--days N] [--max-symbols N] [--validate-only] [--verbose]

optional arguments:
  -h, --help            show this help message and exit
  --discovery-file FILE Path to symbol discovery results JSON file
  --data-dir DIR        Output directory for collected data (default: ../../data/arbitrage)  
  --days N              Number of days of historical data to collect (default: 3)
  --max-symbols N       Maximum number of symbols to process (useful for testing)
  --validate-only       Only validate existing data without collecting new data
  --verbose, -v         Enable verbose logging
```

### Output Structure

Data is saved in a structured directory format:

```
data/arbitrage/
├── MEXC/
│   ├── BTC_USDT_1m_20250910_20250913.csv
│   ├── ETH_USDT_1m_20250910_20250913.csv
│   └── ...
├── GATEIO/
│   ├── BTC_USDT_1m_20250910_20250913.csv  
│   ├── ETH_USDT_1m_20250910_20250913.csv
│   └── ...
└── collection_metadata.json
```

### Data Validation

Built-in validation ensures data quality:

- **Completeness Check**: Verifies all required symbols have data
- **Time Range Validation**: Ensures data covers requested period
- **Data Integrity**: Validates CSV format and required columns
- **Exchange Coverage**: Confirms data from all required exchanges

---

## 3. Spread Analyzer  

**File**: `arbitrage_analyzer.py`

Analyzes collected data to identify and rank profitable arbitrage opportunities with comprehensive metrics calculation.

### Features

- **Comprehensive Metrics**: 15 detailed columns in CSV report
- **Profit Scoring**: 0-100 composite score based on multiple factors
- **Statistical Analysis**: Spread frequency, duration, and volatility metrics
- **Risk Assessment**: Liquidity scoring and execution difficulty analysis
- **Ranking System**: Automated opportunity prioritization

### Quick Start

```bash
# Analyze all available data with default settings
python arbitrage_analyzer.py

# Limit analysis scope for testing
python arbitrage_analyzer.py --max-symbols 20

# Filter by minimum profit score threshold
python arbitrage_analyzer.py --min-profit-score 30

# Generate detailed analysis with custom output
python arbitrage_analyzer.py --output my_analysis.csv --details
```

### Report Columns

The analyzer generates CSV reports with 15 comprehensive columns:

| Column | Description | Range |
|--------|-------------|-------|
| pair | Trading pair symbol | - |
| max_spread | Maximum spread observed (%) | 0-100+ |
| avg_spread | Average spread (%) | 0-100+ |
| med_spread | Median spread (%) | 0-100+ |
| spread_>0.3% | % time spread >0.3% | 0-100 |
| spread_>0.5% | % time spread >0.5% | 0-100 |  
| count_gt_0.3% | Count of opportunities >0.3% | 0+ |
| count_gt_0.5% | Count of opportunities >0.5% | 0+ |
| opportunity_minutes_per_day | Minutes/day with profitable spreads | 0-1440 |
| avg_duration_seconds | Average opportunity duration | 0+ |
| volatility_score | Price volatility indicator | 0-100 |
| liquidity_score | Liquidity assessment | 0-100 |
| execution_score | Execution difficulty | 0-100 |
| risk_score | Risk assessment | 0-100 |
| profit_score | Final composite score | 0-100 |

### Profit Scoring Algorithm

The profit score (0-100) combines multiple factors:

- **Spread Frequency** (40%): How often profitable spreads occur
- **Spread Magnitude** (30%): Size of spreads when they occur  
- **Duration** (15%): How long opportunities persist
- **Liquidity** (10%): Market depth and execution feasibility
- **Risk Factors** (5%): Volatility and execution complexity

### Command Line Options

```bash
usage: arbitrage_analyzer.py [-h] [--data-dir DIR] [--output FILE] [--max-symbols N] 
                            [--min-profit-score N] [--details] [--verbose]

optional arguments:
  -h, --help            show this help message and exit
  --data-dir DIR        Directory containing collected candles data
  --output FILE         Output CSV report filename  
  --max-symbols N       Maximum number of symbols to analyze
  --min-profit-score N  Minimum profit score threshold for reporting
  --details             Show detailed analysis for each symbol
  --verbose, -v         Enable verbose logging
```

---

## Complete Workflow Example

Here's the complete 3-step arbitrage analysis workflow:

```bash
# Step 1: Discover symbols available on multiple cex
python cross_exchange_symbol_discovery.py
# Output: symbol_discovery_detailed_YYYYMMDD_HHMMSS.json
#         arbitrage_opportunities.md

# Step 2: Fetch historical data for identified symbols  
python arbitrage_data_fetcher.py --days 3
# Output: ../../data/arbitrage/ (structured CSV data)

# Step 3: Analyze spreads and rank opportunities
python arbitrage_analyzer.py
# Output: arbitrage_analysis_report.csv

# Review top opportunities
head -20 output/arbitrage_analysis_report.csv
```

### Legacy Script (Deprecated)

**File**: `run_arbitrage_analysis.py` 

The legacy script combines all steps into one execution but is deprecated in favor of the modular workflow. It remains available for backward compatibility.

---

## Rate Limiting System

**File**: `../common/rate_limiter.py`

The tools use a centralized rate limiting system to prevent API throttling while maintaining optimal performance.

### Key Features

- **Per-Exchange Control**: Different limits for each exchange based on testing
- **Semaphore Coordination**: Thread-safe concurrency control
- **Intelligent Delays**: Optimal timing between requests
- **Global Coordination**: Prevents conflicts between concurrent tools

### Exchange Configurations

| Exchange | Max Concurrent | Delay (ms) | Based On |
|----------|---------------|------------|----------|
| Gate.io | 2 | 300 | Conservative API testing |
| MEXC | 5 | 100 | Higher throughput capacity |
| Binance* | 10 | 50 | Future implementation |
| OKX* | 8 | 80 | Future implementation |

*Future exchanges

### Usage in Tools

The rate limiter is automatically integrated into all data fetching operations:

```python
from common.rate_limiter import get_rate_limiter

rate_limiter = get_rate_limiter()

async with rate_limiter.coordinate_request('mexc'):
    response = await mexc_client.get('/api/endpoint')
```

---

## Performance Characteristics

### Symbol Discovery
- **Execution Time**: <30 seconds for 4-exchange analysis
- **Memory Usage**: O(1) per request with connection pooling  
- **API Calls**: 4 parallel requests (one per exchange)
- **Output Size**: ~1MB JSON file for ~1000 symbols

### Data Fetcher  
- **Throughput**: ~50 symbols/minute with rate limiting
- **Data Volume**: ~100MB per 1000 symbols (3 days, 1m candles)
- **Memory Usage**: Bounded at ~50MB regardless of dataset size
- **Success Rate**: >95% under optimal network conditions

### Spread Analyzer
- **Processing Speed**: ~100 symbols/minute  
- **Memory Usage**: O(n) where n = data size per symbol
- **Output Size**: ~50KB CSV per 100 symbols
- **Analysis Accuracy**: Sub-second timestamp precision

---

## Troubleshooting

### Common Issues

**1. API Rate Limiting Errors**
```bash
# Solution: Reduce concurrency or increase delays
python arbitrage_data_fetcher.py --max-symbols 10  # Test with fewer symbols
```

**2. Data Collection Failures**
```bash
# Check connectivity and retry
python arbitrage_data_fetcher.py --validate-only  # Check existing data
```

**3. No Analysis Results**
```bash
# Verify data exists
ls ../../data/arbitrage/
python arbitrage_analyzer.py --verbose  # Enable detailed logging
```

**4. Memory Issues with Large Datasets**
```bash
# Process in batches
python arbitrage_analyzer.py --max-symbols 50
```

### API Debugging

Enable verbose logging to debug API issues:

```bash
# Enable debug logging for any tool
python cross_exchange_symbol_discovery.py --verbose
python arbitrage_data_fetcher.py --verbose  
python arbitrage_analyzer.py --verbose
```

### Data Validation

Validate data integrity before analysis:

```bash
# Check if data collection was successful
python arbitrage_data_fetcher.py --validate-only

# Verify data structure
find ../../data/arbitrage -name "*.csv" | head -5
```

---

## HFT Compliance

All tools strictly adhere to HFT architectural principles:

### No Real-Time Data Caching
- ✅ **Symbol configurations** (static data) can be cached
- ❌ **Price data, order books, balances** are never cached
- ❌ **Real-time market data** always fetched fresh

### Performance Targets
- **API Response Time**: <50ms per request
- **JSON Parsing**: <1ms per message (msgspec only)
- **Memory Management**: O(1) per request with connection pooling
- **Uptime**: >99.9% availability with automatic recovery

### Error Handling
- **Fail-fast**: All exceptions propagate to application level
- **No Silent Failures**: Every error is logged and surfaced
- **Unified Exceptions**: Consistent error hierarchy across all tools
- **Audit Trail**: Complete logging for all trading operations

---

## Integration Notes

### Dependencies
- Python 3.8+
- aiohttp for async HTTP requests
- msgspec for high-performance JSON parsing
- pandas for data analysis (analyzer only)
- Standard library modules (pathlib, logging, etc.)

### File Structure
```
tools/
├── cross_exchange_symbol_discovery.py    # Step 1: Symbol discovery
├── arbitrage_data_fetcher.py              # Step 2: Data collection  
├── arbitrage_analyzer.py                  # Step 3: Spread analysis
├── run_arbitrage_analysis.py              # Legacy combined workflow
├── output/                                # Generated reports
│   ├── symbol_discovery_detailed_*.json
│   ├── arbitrage_opportunities.md
│   └── arbitrage_analysis_report.csv
└── README.md                              # This documentation
```

### API Integration
All tools integrate with the existing exchange abstraction layer:
- `src/exchanges/mexc/` - MEXC implementation
- `src/exchanges/gateio/` - Gate.io implementation  
- `src/common/rate_limiter.py` - Centralized rate limiting
- `src/analysis/` - Data processing pipelines

This modular design ensures the tools can easily adapt to new exchanges and trading strategies while maintaining HFT performance requirements.