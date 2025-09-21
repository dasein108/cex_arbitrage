# CEX Arbitrage Tools - Unified Architecture

**High-performance cryptocurrency arbitrage analysis toolset** following SOLID principles and CLAUDE.md architectural standards.

## Architecture Overview

**Unified Tool Design (v4.0)** - Complete refactoring from legacy 3-script workflow into a single, SOLID-compliant tool:

- **Single Entry Point**: `unified_arbitrage_tool.py` replaces 3 separate scripts
- **SOLID Compliance**: Proper separation of concerns with focused service classes
- **ExchangeEnum Integration**: Uses predefined exchanges from `src/cex/consts.py`
- **Factory Pattern**: Leverages `ExchangeFactory` for proper dependency injection
- **Interface-Driven**: Clean separation between public/private exchange operations
- **HFT Performance**: Sub-50ms latency targets with O(1) symbol resolution

### Key Benefits

- **~65% Code Reduction**: From ~1,400 lines across 3 files to ~500 lines unified
- **DRY Compliance**: Eliminated duplicate CLI, logging, and error handling code
- **Maintainability**: Single tool to update vs. 3 separate scripts
- **Type Safety**: Comprehensive use of ExchangeEnum and structured data types
- **Performance**: Parallel operations with intelligent rate limiting

---

## Unified Arbitrage Tool

**File**: `unified_arbitrage_tool.py`

### Quick Start

```bash
# Complete arbitrage analysis workflow
python unified_arbitrage_tool.py discover --format detailed
python unified_arbitrage_tool.py fetch --days 3 --max-symbols 20
python unified_arbitrage_tool.py analyze --min-profit-score 30

# Get help for any operation
python unified_arbitrage_tool.py discover --help
python unified_arbitrage_tool.py fetch --help
python unified_arbitrage_tool.py analyze --help
```

### Available Operations

The unified tool provides three main operations:

1. **`discover`** - Symbol discovery across exchanges
2. **`fetch`** - Historical data collection
3. **`analyze`** - Spread analysis and opportunity ranking

---

## 1. Symbol Discovery (`discover`)

**Purpose**: Identify trading symbols available across multiple exchanges for arbitrage opportunities.

### Supported Exchanges

The tool automatically discovers symbols from predefined exchanges using `ExchangeEnum`:

- **MEXC Spot** (`ExchangeEnum.MEXC`)
- **Gate.io Spot** (`ExchangeEnum.GATEIO`)  
- **Gate.io Futures** (`ExchangeEnum.GATEIO_FUTURES`)

### Basic Usage

```bash
# Run discovery with default settings
python unified_arbitrage_tool.py discover

# Detailed discovery with major coin filtering
python unified_arbitrage_tool.py discover --format detailed --filter-major-coins

# Include all symbols (no filtering)
python unified_arbitrage_tool.py discover --no-filter-major-coins

# Generate matrix format for analysis tools
python unified_arbitrage_tool.py discover --format matrix --save
```

### Command Line Options

```bash
python unified_arbitrage_tool.py discover [OPTIONS]

Discovery Options:
  --format {summary,detailed,matrix}
                        Output format (default: detailed)
                        - summary: High-level statistics only
                        - detailed: Complete symbol breakdown  
                        - matrix: Arbitrage-ready format for analysis
  
  --filter-major-coins  Filter out major coins (BTC, ETH, BNB, etc.) for focused analysis
  --no-filter-major-coins
                        Include all symbols in discovery
  
  --save                Save discovery results to JSON file
  --no-save             Display results only, don't save
  
  --output-dir DIR      Directory for output files (default: output/)
  
Common Options:
  --verbose, -v         Enable verbose logging
  --help, -h            Show detailed help
```

### Output Structure

**Console Output**:
```
===========================================================
SYMBOL DISCOVERY RESULTS
===========================================================
Total Symbols: 1,247
Arbitrage Candidates: 342
Two-Way Opportunities: 198
Three-Way Opportunities: 144
Four-Way Opportunities: 23

TOP OPPORTUNITIES:
    • WAI/USDT
    • HIFI/USDT
    • GIGA/USDT
    • AI16Z/USDT
    • MYRIA/USDT
===========================================================
```

**JSON Output** (`symbol_discovery_detailed_YYYYMMDD_HHMMSS.json`):
```json
{
  "timestamp": "2025-01-21T10:30:45.123456",
  "total_symbols": 1247,
  "arbitrage_candidates": 342,
  "availability_matrix": {
    "WAI/USDT": {
      "mexc_spot": true,
      "gateio_spot": true,
      "gateio_futures": false
    },
    "HIFI/USDT": {
      "mexc_spot": true,
      "gateio_spot": true,
      "gateio_futures": true
    }
  },
  "statistics": {
    "arbitrage_candidates": 342,
    "two_way_opportunities": 198,
    "three_way_opportunities": 144,
    "four_way_opportunities": 23,
    "best_opportunities": [
      "WAI/USDT", "HIFI/USDT", "GIGA/USDT"
    ]
  }
}
```

### Performance Characteristics

- **Execution Time**: <30 seconds for complete multi-exchange analysis
- **Parallel Processing**: All exchanges queried simultaneously using `asyncio.gather()`
- **Memory Efficiency**: O(1) per request with connection pooling
- **HFT Compliance**: No caching of real-time symbol data per architectural rules

---

## 2. Data Collection (`fetch`)

**Purpose**: Download historical klines (candlestick) data for symbols identified in discovery phase.

### Features

- **Integrated Workflow**: Automatically uses discovery results as input
- **Rate Limiting**: Respects exchange-specific API limits
- **Batch Processing**: Intelligent chunking for large date ranges
- **Data Validation**: Comprehensive validation of collected data
- **Progress Tracking**: Real-time progress indicators

### Basic Usage

```bash
# Fetch 3 days of data (optimized default)
python unified_arbitrage_tool.py fetch

# Fetch custom time period with symbol limit
python unified_arbitrage_tool.py fetch --days 7 --max-symbols 25

# Use custom discovery file and output directory
python unified_arbitrage_tool.py fetch --discovery-file my_symbols.json --data-dir ./my_data

# Validate existing data without fetching new data
python unified_arbitrage_tool.py fetch --validate-only
```

### Command Line Options

```bash
python unified_arbitrage_tool.py fetch [OPTIONS]

Data Collection Options:
  --discovery-file FILE Path to symbol discovery JSON file
                        (default: auto-detects latest in output/)
  
  --data-dir DIR        Output directory for collected data
                        (default: ../../data/arbitrage)
  
  --days N              Number of days of historical data to collect
                        (default: 3, range: 1-30)
  
  --max-symbols N       Maximum number of symbols to process
                        (useful for testing, default: unlimited)
  
  --validate-only       Only validate existing data without collecting new data
  
  --interval {1m,5m,15m,30m,1h,4h,12h,1d}
                        Klines interval (default: 1m)

Common Options:
  --verbose, -v         Enable verbose logging
  --help, -h            Show detailed help
```

### Output Structure

Data is organized in a structured directory format:

```
data/arbitrage/
├── MEXC/
│   ├── WAI_USDT_1m_20250118_20250121.csv
│   ├── HIFI_USDT_1m_20250118_20250121.csv
│   └── GIGA_USDT_1m_20250118_20250121.csv
├── GATEIO/
│   ├── WAI_USDT_1m_20250118_20250121.csv
│   ├── HIFI_USDT_1m_20250118_20250121.csv
│   └── GIGA_USDT_1m_20250118_20250121.csv
└── collection_metadata.json
```

**CSV Format** (standardized across all exchanges):
```csv
timestamp,open,high,low,close,volume,quote_volume
1705651200000,0.0234,0.0238,0.0232,0.0235,1234567.89,28956.34
1705651260000,0.0235,0.0237,0.0233,0.0236,1098765.43,25897.12
```

### Rate Limiting Configuration

The tool implements intelligent rate limiting per exchange:

| Exchange | Max Concurrent | Delay (ms) | API Limit |
|----------|---------------|------------|-----------|
| MEXC | 5 | 100 | 20 req/sec |
| Gate.io | 2 | 300 | 20 req/10sec |

### Data Validation

Built-in validation ensures data quality:

- **Completeness Check**: Verifies all symbols have data for requested period
- **Time Range Validation**: Ensures data covers requested date range
- **Format Validation**: Validates CSV structure and required columns
- **Exchange Coverage**: Confirms data from all required exchanges
- **Duplicate Detection**: Identifies and reports any duplicate records

### Console Output

```bash
📊 Starting data collection...
📡 Initializing exchange connections...
✅ MEXC connection established
✅ GATEIO connection established

📊 Processing 25 symbols over 3 days...
[████████████████████████████████] 100% | 25/25 symbols completed

📈 Collection Summary:
  • Total Symbols: 25
  • Success Rate: 96.0% (24/25 successful)
  • Failed Symbols: 1 (SYMBOL_USDT - API timeout)
  • Data Files: 48 CSV files created
  • Total Size: 145.7 MB

✅ Data collection completed successfully!
📄 Metadata saved to: collection_metadata.json
```

---

## 3. Spread Analysis (`analyze`)

**Purpose**: Analyze collected klines data to identify and rank profitable arbitrage opportunities.

### Features

- **Comprehensive Metrics**: 15 detailed analysis columns
- **Profit Scoring**: 0-100 composite score based on multiple factors
- **Statistical Analysis**: Spread frequency, duration, and volatility metrics
- **Risk Assessment**: Liquidity and execution difficulty analysis
- **Incremental Output**: Real-time CSV generation for large datasets

### Basic Usage

```bash
# Analyze all available data with default settings
python unified_arbitrage_tool.py analyze

# Limit analysis scope for faster testing
python unified_arbitrage_tool.py analyze --max-symbols 20

# Filter by minimum profit threshold
python unified_arbitrage_tool.py analyze --min-profit-score 40

# Custom output file with incremental updates
python unified_arbitrage_tool.py analyze --output my_analysis.csv --incremental
```

### Command Line Options

```bash
python unified_arbitrage_tool.py analyze [OPTIONS]

Analysis Options:
  --data-dir DIR        Directory containing collected klines data
                        (default: ../../data/arbitrage)
  
  --output FILE         Output CSV report filename
                        (default: output/arbitrage_analysis_report.csv)
  
  --max-symbols N       Maximum number of symbols to analyze
                        (default: unlimited)
  
  --min-profit-score N  Minimum profit score threshold for reporting
                        (default: 0, range: 0-100)
  
  --incremental         Enable incremental CSV output during analysis
                        (useful for large datasets)

Common Options:
  --verbose, -v         Enable verbose logging
  --help, -h            Show detailed help
```

### Analysis Report Columns

The analyzer generates comprehensive CSV reports with 15 metrics:

| Column | Description | Range | Weight |
|--------|-------------|-------|--------|
| **pair** | Trading pair symbol | - | - |
| **max_spread** | Maximum spread observed (%) | 0-100+ | High |
| **avg_spread** | Average spread (%) | 0-100+ | Medium |
| **med_spread** | Median spread (%) | 0-100+ | Medium |
| **spread_>0.3%** | % time spread >0.3% | 0-100 | High |
| **spread_>0.5%** | % time spread >0.5% | 0-100 | High |
| **count_gt_0.3%** | Count of opportunities >0.3% | 0+ | Medium |
| **count_gt_0.5%** | Count of opportunities >0.5% | 0+ | Medium |
| **opportunity_minutes_per_day** | Minutes/day with profitable spreads | 0-1440 | High |
| **avg_duration_seconds** | Average opportunity duration | 0+ | Medium |
| **volatility_score** | Price volatility indicator | 0-100 | Low |
| **liquidity_score** | Liquidity assessment | 0-100 | Medium |
| **execution_score** | Execution difficulty | 0-100 | Medium |
| **risk_score** | Risk assessment | 0-100 | Low |
| **profit_score** | **Final composite score** | **0-100** | **Final** |

### Profit Scoring Algorithm

The profit score (0-100) is calculated using weighted factors:

- **Spread Frequency** (40%): How often profitable spreads occur
- **Spread Magnitude** (30%): Size of spreads when they occur
- **Duration** (15%): How long opportunities persist
- **Liquidity** (10%): Market depth and execution feasibility
- **Risk Factors** (5%): Volatility and execution complexity

### Console Output

```bash
📈 Starting spread analysis...
📊 Found data for 24 symbols
⚡ Analyzing spreads across 3 days of 1-minute data...

[████████████████████████████████] 100% | 24/24 symbols analyzed

============================================================
ARBITRAGE ANALYSIS COMPLETED
============================================================
📊 Total opportunities: 24
💰 Average profit score: 42.3
📄 Report saved to: output/arbitrage_analysis_report.csv

🎯 TOP 5 OPPORTUNITIES:
  1. WAI/USDT        - Profit:  78.5, Max Spread:  2.456%
  2. HIFI/USDT       - Profit:  71.2, Max Spread:  1.934%
  3. GIGA/USDT       - Profit:  65.8, Max Spread:  1.721%
  4. AI16Z/USDT      - Profit:  58.7, Max Spread:  1.543%
  5. MYRIA/USDT      - Profit:  52.1, Max Spread:  1.287%
============================================================
```

### Sample Analysis Report

**CSV Output** (`arbitrage_analysis_report.csv`):
```csv
pair,max_spread,avg_spread,med_spread,spread_>0.3%,spread_>0.5%,count_gt_0.3%,count_gt_0.5%,opportunity_minutes_per_day,avg_duration_seconds,volatility_score,liquidity_score,execution_score,risk_score,profit_score
WAI/USDT,2.456,0.834,0.623,34.2,18.7,493,269,492.48,145.3,68.4,72.1,81.5,23.7,78.5
HIFI/USDT,1.934,0.712,0.534,28.6,14.3,412,206,411.84,128.7,58.2,68.9,78.2,28.4,71.2
GIGA/USDT,1.721,0.645,0.487,25.1,12.1,361,174,360.24,118.9,52.7,65.3,74.8,31.2,65.8
AI16Z/USDT,1.543,0.587,0.423,21.8,9.7,314,140,313.92,108.4,48.3,61.7,71.4,33.9,58.7
MYRIA/USDT,1.287,0.521,0.378,18.4,7.2,265,104,264.96,95.8,44.1,58.2,67.9,36.5,52.1
```

---

## Complete Workflow Examples

### Basic Workflow

```bash
# Step 1: Discover arbitrage-ready symbols
python unified_arbitrage_tool.py discover --format detailed --save

# Step 2: Collect 3 days of 1-minute data
python unified_arbitrage_tool.py fetch --days 3

# Step 3: Analyze and rank opportunities
python unified_arbitrage_tool.py analyze --min-profit-score 30

# Review results
head -10 output/arbitrage_analysis_report.csv
```

### Advanced Testing Workflow

```bash
# Quick testing with limited scope
python unified_arbitrage_tool.py discover --max-symbols 10 --save
python unified_arbitrage_tool.py fetch --days 1 --max-symbols 10
python unified_arbitrage_tool.py analyze --max-symbols 10 --min-profit-score 20

# Validation-only run (no new data collection)
python unified_arbitrage_tool.py fetch --validate-only

# Incremental analysis for large datasets
python unified_arbitrage_tool.py analyze --incremental --verbose
```

### Production Workflow

```bash
# Comprehensive discovery (include all symbols)
python unified_arbitrage_tool.py discover --no-filter-major-coins --save

# Collect week of data for thorough analysis
python unified_arbitrage_tool.py fetch --days 7

# High-threshold analysis for best opportunities only
python unified_arbitrage_tool.py analyze --min-profit-score 50 --output production_opportunities.csv
```

---

## Architecture & Performance

### SOLID Principles Implementation

**Single Responsibility Principle (SRP)**:
- `ArbitrageToolController`: Orchestrates operations, no business logic
- `SymbolDiscoveryService`: Only handles symbol discovery across exchanges
- `DataCollectionService`: Only handles historical data fetching
- `AnalysisService`: Only handles spread analysis and ranking

**Open/Closed Principle (OCP)**:
- New exchanges added via ExchangeEnum without modifying existing code
- Analysis algorithms can be extended without changing core service logic

**Liskov Substitution Principle (LSP)**:
- All exchange implementations fully interchangeable via common interfaces
- Service classes can be substituted for testing or different implementations

**Interface Segregation Principle (ISP)**:
- `BasePublicExchangeInterface` used for market data (no authentication needed)
- `BasePrivateExchangeInterface` used only when trading operations required
- Services depend only on interfaces they actually use

**Dependency Inversion Principle (DIP)**:
- Controller receives configured services via dependency injection
- Services depend on abstractions (ExchangeFactory) not concrete implementations

### Performance Characteristics

#### Symbol Discovery
- **Execution Time**: <30 seconds for multi-exchange analysis
- **Memory Usage**: O(1) with connection pooling
- **API Calls**: Parallel requests to all exchanges simultaneously
- **Throughput**: ~1000+ symbols analyzed per run

#### Data Collection  
- **Processing Speed**: ~50-100 symbols/minute (rate-limited)
- **Memory Usage**: Bounded at ~50MB regardless of dataset size
- **Data Volume**: ~100MB per 1000 symbols (3 days, 1-minute klines)
- **Success Rate**: >95% under optimal network conditions

#### Spread Analysis
- **Analysis Speed**: ~100 symbols/minute
- **Memory Usage**: O(n) where n = klines per symbol
- **Processing Accuracy**: Microsecond timestamp precision
- **Report Generation**: <1 second for 100 symbols

### HFT Compliance

**No Real-Time Data Caching**:
- ✅ Symbol configurations and static data can be cached
- ❌ Price data, klines, and market data never cached
- ❌ Real-time market information always fetched fresh

**Performance Targets**:
- **API Response Time**: <50ms per request
- **JSON Parsing**: <1ms per message (msgspec-exclusive)
- **Symbol Resolution**: O(1) lookup using ExchangeFactory
- **Memory Management**: Bounded memory usage with streaming processing

**Error Handling**:
- **Fail-Fast**: All exceptions propagate to application level
- **Unified Exceptions**: Consistent error hierarchy across all operations
- **Audit Trail**: Complete logging of all operations and failures
- **No Silent Failures**: Every error logged and surfaced to user

---

## Configuration & Dependencies

### Environment Setup

**Required Environment Variables** (for live data collection):
```bash
# Exchange API credentials (optional for public data)
export MEXC_API_KEY="your_mexc_api_key"
export MEXC_SECRET_KEY="your_mexc_secret_key"
export GATEIO_API_KEY="your_gateio_api_key"  
export GATEIO_SECRET_KEY="your_gateio_secret_key"
```

### Dependencies

**Core Dependencies**:
- Python 3.8+
- aiohttp (async HTTP requests)
- msgspec (high-performance JSON parsing)
- pandas (data analysis)
- pathlib (path handling)

**Project Dependencies**:
- `src/cex/consts.py` (ExchangeEnum definitions)
- `src/cex/factories/exchange_factory.py` (Exchange creation)
- `src/core/config/config_manager.py` (Configuration management)
- `src/analysis/` (Data processing pipelines)

### File Structure

```
tools/
├── unified_arbitrage_tool.py          # Main unified tool
├── shared_utils.py                    # Shared utility classes
├── output/                            # Generated reports and data
│   ├── symbol_discovery_*.json
│   ├── arbitrage_analysis_report.csv
│   └── collection_metadata.json
└── README.md                          # This documentation

Legacy (Deprecated):
├── cross_exchange_symbol_discovery.py # Legacy: Symbol discovery
├── arbitrage_data_fetcher.py          # Legacy: Data collection
├── arbitrage_analyzer.py              # Legacy: Spread analysis
└── run_arbitrage_analysis.py          # Legacy: Combined workflow
```

---

## Troubleshooting

### Common Issues & Solutions

**1. API Rate Limiting Errors**
```bash
# Error: HTTP 429 Too Many Requests
# Solution: Reduce concurrency or use smaller symbol sets
python unified_arbitrage_tool.py fetch --max-symbols 10
```

**2. Data Collection Failures**
```bash
# Error: Failed to fetch data for multiple symbols
# Solution: Check network connectivity and validate existing data
python unified_arbitrage_tool.py fetch --validate-only
```

**3. No Analysis Results**
```bash
# Error: No arbitrage opportunities found
# Solution: Verify data exists and lower profit threshold
ls ../../data/arbitrage/
python unified_arbitrage_tool.py analyze --min-profit-score 0 --verbose
```

**4. Memory Issues with Large Datasets**
```bash
# Error: Out of memory during analysis
# Solution: Process in smaller batches
python unified_arbitrage_tool.py analyze --max-symbols 25
```

**5. ExchangeFactory Import Errors**
```bash
# Error: Cannot import ExchangeEnum or ExchangeFactory
# Solution: Ensure PYTHONPATH includes src directory
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
python unified_arbitrage_tool.py discover
```

### Debug Mode

Enable verbose logging for detailed troubleshooting:

```bash
# Enable debug logging for any operation
python unified_arbitrage_tool.py discover --verbose
python unified_arbitrage_tool.py fetch --verbose
python unified_arbitrage_tool.py analyze --verbose
```

### Data Validation Commands

```bash
# Validate discovery output
python -m json.tool output/symbol_discovery_detailed_*.json

# Check data collection completeness
python unified_arbitrage_tool.py fetch --validate-only

# Verify analysis data structure
find ../../data/arbitrage -name "*.csv" | head -5
head -5 ../../data/arbitrage/MEXC/WAI_USDT_1m_*.csv
```

---

## Migration from Legacy Tools

### Legacy to Unified Command Mapping

**Symbol Discovery**:
```bash
# Legacy
python cross_exchange_symbol_discovery.py --format detailed

# Unified
python unified_arbitrage_tool.py discover --format detailed
```

**Data Collection**:
```bash
# Legacy  
python arbitrage_data_fetcher.py --days 3 --max-symbols 20

# Unified
python unified_arbitrage_tool.py fetch --days 3 --max-symbols 20
```

**Analysis**:
```bash
# Legacy
python arbitrage_analyzer.py --min-profit-score 30

# Unified
python unified_arbitrage_tool.py analyze --min-profit-score 30
```

### Migration Benefits

- **Single Tool**: No need to manage 3 separate scripts
- **Consistent CLI**: Unified argument parsing and help system  
- **Better Error Handling**: Consistent error messages across all operations
- **Improved Performance**: Shared connection pooling and optimizations
- **Easier Maintenance**: Single codebase to update and test

### Backward Compatibility

Legacy tools remain available but are deprecated:
- `cross_exchange_symbol_discovery.py` → Use `unified_arbitrage_tool.py discover`
- `arbitrage_data_fetcher.py` → Use `unified_arbitrage_tool.py fetch`
- `arbitrage_analyzer.py` → Use `unified_arbitrage_tool.py analyze`

---

## Integration with Trading System

### Data Pipeline Integration

The unified tool generates data in formats compatible with the main trading system:

**Discovery Output** → **Symbol Configuration** for arbitrage engine
**Klines Data** → **Backtesting Framework** for strategy validation
**Analysis Report** → **Opportunity Prioritization** for live trading

### Real-Time Integration

While the tool focuses on historical analysis, outputs can inform real-time trading:

- **Symbol Selection**: Use discovery results to configure active trading pairs
- **Profit Thresholds**: Use analysis report profit scores to set minimum thresholds
- **Risk Assessment**: Use volatility and liquidity scores for position sizing

### API Compatibility

All data structures use the same types as the main trading system:
- `Symbol` and `SymbolInfo` from `src/structs/common.py`
- `Kline` structures from `src/cex/interfaces/structs.py`
- Exchange configurations from `config.yaml`

This ensures seamless integration between analysis tools and live trading components.