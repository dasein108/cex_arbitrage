# Simple Arbitrage Analysis Tasks

## Task Overview

Create an arbitrage analysis system that:
1. Uses existing symbol discovery results to identify trading pairs
2. Downloads 3 months of 1-minute candles for those pairs
3. Analyzes spreads and generates a performance report table

## Task 1: Data Collection Pipeline

### Input
- Discovery result from: `src/tools/output/symbol_discovery_detailed_20250913_102849.json`
- Target: Symbols with 4-way coverage (MEXC spot/futures + Gate.io spot/futures)

### Implementation
```python
# File: src/analysis/collect_arbitrage_data.py

class ArbitrageDataPipeline:
    def __init__(self):
        self.discovery_file = "src/tools/output/symbol_discovery_detailed_20250913_102849.json"
        self.candles_downloader = CandlesDownloader(output_dir="./data/arbitrage")
    
    async def collect_data_for_analysis(self):
        # 1. Load discovery results
        symbols = self.load_four_way_symbols()
        
        # 2. Generate download configs for each symbol/exchange combination
        configs = self.generate_download_configs(symbols, months=3, timeframe="1m")
        
        # 3. Bulk download using existing candles downloader
        results = await self.candles_downloader.download_multiple(configs)
        
        return results
```

### Output
```
data/arbitrage/
├── mexc_BTC_USDT_1m_20240613_20240913.csv
├── gateio_BTC_USDT_1m_20240613_20240913.csv
├── mexc_ETH_USDT_1m_20240613_20240913.csv
├── gateio_ETH_USDT_1m_20240613_20240913.csv
└── ...
```

## Task 2: Spread Analysis & Report Generation

### Input
- CSV files from Task 1 (historical candle data)
- Analysis period: 3 months of 1-minute data

### Implementation
```python
# File: src/analysis/spread_analyzer.py

class SpreadAnalyzer:
    def analyze_pair(self, symbol: str) -> ArbitrageMetrics:
        # 1. Load MEXC and Gate.io data for symbol
        mexc_data = self.load_candles(f"mexc_{symbol}_1m_*.csv")
        gateio_data = self.load_candles(f"gateio_{symbol}_1m_*.csv")
        
        # 2. Synchronize timestamps and calculate spreads
        spreads = self.calculate_spreads(mexc_data, gateio_data)
        
        # 3. Calculate all required metrics
        return ArbitrageMetrics(
            pair=symbol,
            max_spread=max(spreads),
            avg_spread=mean(spreads),
            med_spread=median(spreads),
            spread_gt_0_3_percent=percent_above_threshold(spreads, 0.003),
            count_gt_0_3_percent=count_above_threshold(spreads, 0.003),
            # ... other metrics
        )
```

### Required Report Table Columns
```csv
pair,max_spread,avg_spread,med_spread,spread_>0.3%,count_>0.3%,spread_>0.5%,count_>0.5%,opportunity_minutes_per_day,avg_duration_seconds,liquidity_score,execution_score,risk_score,profit_score,composite_rank
```

### Metric Definitions

| Column | Definition | Calculation |
|--------|------------|-------------|
| `pair` | Trading pair symbol | e.g., "BTC/USD_STABLE" |
| `max_spread` | Maximum spread % observed | `max((gateio_price - mexc_price) / mexc_price * 100)` |
| `avg_spread` | Average spread % | `mean(all_spreads)` |
| `med_spread` | Median spread % | `median(all_spreads)` |
| `spread_>0.3%` | % of time spread > 0.3% | `count(spreads > 0.3) / total_count * 100` |
| `count_>0.3%` | Number of 1-min periods > 0.3% | `count(spreads > 0.3)` |
| `spread_>0.5%` | % of time spread > 0.5% | `count(spreads > 0.5) / total_count * 100` |
| `count_>0.5%` | Number of 1-min periods > 0.5% | `count(spreads > 0.5)` |
| `opportunity_minutes_per_day` | Avg profitable minutes/day | `(count_>0.3% / days) / (24*60) * 100` |
| `avg_duration_seconds` | Avg continuous opportunity duration | Time-series analysis of consecutive profitable periods |
| `liquidity_score` | Order book depth score (0-100) | Based on volume data in candles |
| `execution_score` | Execution feasibility (0-100) | Based on spread stability and volume |
| `risk_score` | Risk assessment (0-100) | Based on volatility during spread periods |
| `profit_score` | Risk-adjusted profit (0-100) | Combination of spread size, frequency, and risk |
| `composite_rank` | Overall ranking (1=best) | Ranked by profit_score |

### Integration Points

#### From Symbol Discovery Tool
```python
def load_four_way_symbols(discovery_file: str) -> List[str]:
    """Extract symbols with 4-way coverage from discovery results"""
    with open(discovery_file) as f:
        data = json.load(f)
    
    four_way_symbols = []
    for symbol, availability in data['availability'].items():
        if all([
            availability['mexc_spot'],
            availability['mexc_futures'], 
            availability['gateio_spot'],
            availability['gateio_futures']
        ]):
            four_way_symbols.append(symbol)
    
    return four_way_symbols
```

#### With Candles Downloader
```python
def generate_download_configs(symbols: List[str], months: int = 3) -> List[Dict]:
    """Generate download configs for candles downloader"""
    configs = []
    end_date = datetime.now()
    start_date = end_date - timedelta(days=months * 30)
    
    for symbol in symbols:
        for exchange in ['mexc', 'gateio']:
            configs.append({
                'exchange': exchange,
                'symbol': symbol.replace('/USD_STABLE', '/USDT'),  # Convert back to USDT
                'timeframe': '1m',
                'start_date': start_date,
                'end_date': end_date
            })
    
    return configs
```

## Expected Deliverables

### Task 1 Deliverables:
1. `ArbitrageDataPipeline` class that integrates with existing tools
2. Symbol filtering from discovery results (4-way opportunities)
3. Bulk data collection using `CandlesDownloader.download_multiple()`
4. Organized file structure for analysis

### Task 2 Deliverables:
1. `SpreadAnalyzer` class with statistical analysis
2. CSV report with exact columns specified:
   ```
   pair,max_spread,avg_spread,med_spread,spread_>0.3%,count_>0.3%,spread_>0.5%,count_>0.5%,opportunity_minutes_per_day,avg_duration_seconds,liquidity_score,execution_score,risk_score,profit_score,composite_rank
   ```
3. Memory-efficient processing for large datasets
4. Comprehensive metrics calculation

## Usage Example

```bash
# Step 1: Collect data
python -m analysis.collect_arbitrage_data \
    --discovery-file src/tools/output/symbol_discovery_detailed_20250913_102849.json \
    --months 3 \
    --output ./data/arbitrage/

# Step 2: Analyze and generate report
python -m analysis.spread_analyzer \
    --data-dir ./data/arbitrage/ \
    --output arbitrage_analysis_report.csv
```

## Success Criteria

### Task 1:
- ✅ Successfully load 4-way symbols from discovery results
- ✅ Download 3 months of 1-minute data for all symbol/exchange combinations
- ✅ Organized file structure ready for analysis

### Task 2:
- ✅ Generate CSV report with exact specified columns
- ✅ Calculate all 15 required metrics accurately
- ✅ Process entire dataset efficiently (memory < 2GB)
- ✅ Rank opportunities by composite score

## File Structure
```
src/analysis/
├── __init__.py
├── collect_arbitrage_data.py    # Task 1: Data collection pipeline
├── spread_analyzer.py           # Task 2: Analysis and reporting
└── utils/
    ├── __init__.py
    ├── data_loader.py           # CSV data loading utilities
    ├── spread_calculator.py     # Spread calculation functions
    └── metrics.py               # Statistical metrics calculation
```

This simplified approach focuses on the core requirements while leveraging existing tools for maximum efficiency and integration.