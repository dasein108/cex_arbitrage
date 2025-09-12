# Tools Directory

This directory contains utility tools for the CEX Arbitrage Engine.

## Candles Downloader

A comprehensive tool for downloading historical candlestick data from multiple cryptocurrency exchanges.

### Features

- **Multi-Exchange Support**: Currently supports MEXC and Gate.io
- **Unified CSV Format**: Consistent output format across all exchanges
- **Batch Processing**: Handles large time ranges efficiently
- **Concurrent Downloads**: Download from multiple sources simultaneously
- **CLI & Class Interface**: Use as command-line tool or Python class
- **Data Validation**: Comprehensive error handling and validation
- **Progress Tracking**: Real-time progress updates for large downloads

### Quick Start

#### Command Line Usage

```bash
# Download 30 days of BTC/USDT 1h candles from MEXC
python candles_downloader.py --exchange mexc --symbol BTC_USDT --timeframe 1h --days 30

# Download specific date range from Gate.io
python candles_downloader.py --exchange gateio --symbol BTC_USDT --timeframe 1d --start 2024-01-01 --end 2024-02-01

# Download with custom output directory
python candles_downloader.py --exchange mexc --symbol ETH_USDT --timeframe 5m --days 7 --output ./my_data
```

#### Python Class Usage

```python
import asyncio
from candles_downloader import CandlesDownloader

async def download_data():
    downloader = CandlesDownloader(output_dir="./data")
    
    # Single download
    csv_path = await downloader.download_candles(
        exchange='mexc',
        symbol='BTC_USDT',
        timeframe='1h',
        days=30
    )
    
    # Multiple concurrent downloads
    configs = [
        {'exchange': 'mexc', 'symbol': 'BTC_USDT', 'timeframe': '1h', 'days': 7},
        {'exchange': 'gateio', 'symbol': 'ETH_USDT', 'timeframe': '1d', 'days': 30}
    ]
    paths = await downloader.download_multiple(configs)

asyncio.run(download_data())
```

### CSV Output Format

All data is saved in a unified CSV format:

| Column       | Description                    | Type    |
|--------------|--------------------------------|---------|
| timestamp    | Unix timestamp (milliseconds)  | int     |
| datetime     | Human readable datetime (UTC)  | string  |
| exchange     | Exchange name (MEXC, GATEIO)   | string  |
| symbol       | Symbol in BASE_QUOTE format   | string  |
| timeframe    | Timeframe (1m, 5m, 1h, 1d)    | string  |
| open         | Open price                     | float   |
| high         | High price                     | float   |
| low          | Low price                      | float   |
| close        | Close price                    | float   |
| volume       | Base asset volume              | float   |
| quote_volume | Quote asset volume             | float   |
| trades_count | Number of trades               | int     |

### Supported Exchanges

- **MEXC**: Full klines API support with batch processing
- **Gate.io**: Complete candlesticks API integration
- **Future**: Binance, Kraken, and other major exchanges

### Supported Timeframes

- **Minutes**: 1m, 5m, 15m, 30m
- **Hours**: 1h, 4h, 12h  
- **Days**: 1d
- **Weeks**: 1w
- **Months**: 1M

### Command Line Options

```
usage: candles_downloader.py [-h] --exchange {mexc,gateio} --symbol SYMBOL --timeframe {1m,5m,15m,30m,1h,4h,12h,1d,1w,1M} [--days DAYS | --start START] [--end END] [--output OUTPUT] [--filename FILENAME] [--verbose]

Download historical candlestick data from cryptocurrency exchanges

optional arguments:
  -h, --help            show this help message and exit
  --exchange {mexc,gateio}, -e {mexc,gateio}
                        Exchange to download from
  --symbol SYMBOL, -s SYMBOL
                        Trading symbol (e.g., BTC_USDT, BTCUSDT, BTC/USDT)
  --timeframe {1m,5m,15m,30m,1h,4h,12h,1d,1w,1M}, -t {1m,5m,15m,30m,1h,4h,12h,1d,1w,1M}
                        Candlestick timeframe
  --days DAYS, -d DAYS  Number of days to download (from now backwards)
  --start START         Start date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
  --end END             End date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS), only used with --start
  --output OUTPUT, -o OUTPUT
                        Output directory for CSV files (default: ./data)
  --filename FILENAME, -f FILENAME
                        Custom output filename (auto-generated if not specified)
  --verbose, -v         Enable verbose logging
```

### Examples

See `example_usage.py` for comprehensive usage examples including:
- Single downloads with automatic date ranges
- Specific date range downloads
- Multiple concurrent downloads
- Custom filename usage
- Information about supported options

### Data Directory Structure

```
tools/
├── candles_downloader.py    # Main downloader tool
├── example_usage.py         # Usage examples
├── README.md               # This file
└── data/                   # Default output directory
    ├── mexc_BTC_USDT_1h_20240801_20240831.csv
    ├── gateio_ETH_USDT_1d_20240701_20240801.csv
    └── ...
```

### Performance Characteristics

- **Batch Processing**: Automatically chunks large requests to respect API limits
- **Concurrent Downloads**: Multiple exchanges/symbols downloaded in parallel
- **Memory Efficient**: Streaming writes to CSV, bounded memory usage
- **Rate Limiting**: Built-in respect for exchange API rate limits
- **Error Handling**: Comprehensive retry logic and error recovery

### Requirements

The downloader requires:
- Python 3.8+
- Async/await support
- Exchange implementations (MEXC, Gate.io)
- Standard library modules (csv, argparse, pathlib, etc.)

All dependencies are included in the main project requirements.

### Integration

The downloader integrates seamlessly with:
- **Trading Strategies**: Historical backtesting data
- **Technical Analysis**: Price action and indicator calculation
- **Research Tools**: Market analysis and pattern recognition
- **Data Pipelines**: ETL processes and data warehouse ingestion

### Error Handling

The downloader includes comprehensive error handling for:
- Invalid exchange/symbol/timeframe combinations
- Network connectivity issues
- API rate limiting and errors
- File system permissions and disk space
- Data validation and integrity checks

All errors are logged with detailed information for debugging.