#!/usr/bin/env python3
"""
Candles Downloader Tool

Multi-exchange candles/klines data downloader with unified CSV output format.
Works both as a Python class and CLI tool for downloading historical candlestick data.

Key Features:
- Multi-exchange support (MEXC, Gate.io)
- Unified CSV format across all cex
- Batch processing for large time ranges
- Data validation and error handling
- Progress tracking for large downloads
- Configurable output directory and format

CLI Usage:
    python candles_downloader.py --exchange mexc --symbol BTC_USDT --timeframe 1h --days 30
    python candles_downloader.py --exchange gateio --symbol BTC_USDT --timeframe 1d --start 2024-01-01 --end 2024-02-01

Class Usage:
    downloader = CandlesDownloader(output_dir="./data")
    await downloader.download_candles("mexc", "BTC_USDT", "1h", days=30)
"""

import asyncio
import argparse
import csv
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

# Import the exchange implementations
from cex.mexc.rest.rest_public import MexcPublicSpotRest
from cex.gateio.rest.gateio_public import GateioPublicExchangeSpotRest
from structs.exchange import Symbol, AssetName, KlineInterval, Kline
# NOTE: rate_limiter functionality replaced by strategy-based transport system
# from common.rate_limiter import get_rate_limiter


class CandlesDownloader:
    """
    Multi-exchange candles downloader with unified CSV output format.
    
    Supports downloading historical candlestick data from multiple cex
    with consistent output format and comprehensive error handling.
    """
    
    # Unified CSV header format
    CSV_HEADER = [
        'timestamp',           # Unix timestamp in milliseconds
        'datetime',           # Human readable datetime (UTC)
        'exchange',           # Exchange name
        'symbol',             # Symbol in BASE_QUOTE format
        'timeframe',          # Timeframe (1m, 5m, 1h, 1d, etc.)
        'open',               # Open price
        'high',               # High price
        'low',                # Low price
        'close',              # Close price
        'volume',             # Base asset volume
        'quote_volume',       # Quote asset volume
        'trades_count'        # Number of trades (0 if not available)
    ]
    
    # Exchange implementations mapping
    EXCHANGES = {
        'mexc': MexcPublicSpotRest,
        'gateio': GateioPublicExchangeSpotRest
    }
    
    # Timeframe mapping to KlineInterval enum
    TIMEFRAME_MAP = {
        '1m': KlineInterval.MINUTE_1,
        '5m': KlineInterval.MINUTE_5,
        '15m': KlineInterval.MINUTE_15,
        '30m': KlineInterval.MINUTE_30,
        '1h': KlineInterval.HOUR_1,
        '4h': KlineInterval.HOUR_4,
        '12h': KlineInterval.HOUR_12,
        '1d': KlineInterval.DAY_1,
        '1w': KlineInterval.WEEK_1,
        '1M': KlineInterval.MONTH_1
    }
    
    def __init__(self, output_dir: str = "data"):
        """
        Initialize the candles downloader.
        
        Args:
            output_dir: Directory to save CSV files (default: data)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # Create console handler if no handlers exist
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        
        self.logger.info(f"CandlesDownloader initialized with output directory: {self.output_dir}")
    
    def _parse_symbol(self, symbol_str: str) -> Symbol:
        """
        Parse symbol string into Symbol struct.
        
        Supports formats: BTC_USDT, BTCUSDT, BTC/USDT
        
        Args:
            symbol_str: Symbol string in various formats
            
        Returns:
            Symbol struct with cex and quote assets
        """
        # Normalize symbol string
        symbol_str = symbol_str.upper().replace('/', '_')
        
        # Handle underscore format (preferred)
        if '_' in symbol_str:
            parts = symbol_str.split('_')
            if len(parts) == 2:
                return Symbol(
                    base=AssetName(parts[0]),
                    quote=AssetName(parts[1]),
                    is_futures=False
                )
        
        # Handle concatenated format (try common quote assets)
        common_quotes = ['USDT', 'USDC', 'BUSD', 'BTC', 'ETH', 'BNB']
        for quote in common_quotes:
            if symbol_str.endswith(quote) and len(symbol_str) > len(quote):
                base = symbol_str[:-len(quote)]
                return Symbol(
                    base=AssetName(base),
                    quote=AssetName(quote), 
                    is_futures=False
                )
        
        raise ValueError(f"Unable to parse symbol: {symbol_str}")
    
    def _get_timeframe(self, timeframe_str: str) -> KlineInterval:
        """
        Convert timeframe string to KlineInterval enum.
        
        Args:
            timeframe_str: Timeframe string (1m, 5m, 1h, 1d, etc.)
            
        Returns:
            KlineInterval enum value
        """
        if timeframe_str not in self.TIMEFRAME_MAP:
            available = ', '.join(self.TIMEFRAME_MAP.keys())
            raise ValueError(f"Unsupported timeframe: {timeframe_str}. Available: {available}")
        
        return self.TIMEFRAME_MAP[timeframe_str]
    
    def _generate_filename(self, exchange: str, symbol: str, timeframe: str, 
                          start_date: datetime, end_date: datetime) -> str:
        """
        Generate CSV filename based on parameters.
        
        Format: {exchange}_{symbol}_{timeframe}_{start}_{end}.csv
        Example: mexc_BTC_USDT_1h_20240101_20240201.csv
        """
        start_str = start_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        symbol_clean = symbol.replace('/', '_').replace('_', '_')
        
        return f"{exchange}_{symbol_clean}_{timeframe}_{start_str}_{end_str}.csv"
    
    def _kline_to_csv_row(self, kline: Kline, exchange: str, timeframe: str) -> List[Any]:
        """
        Convert Kline object to CSV row data.
        
        Args:
            kline: Kline object from exchange
            exchange: Exchange name
            timeframe: Timeframe string
            
        Returns:
            List of values matching CSV_HEADER format
        """
        # Convert timestamp to datetime for human readability
        dt = datetime.fromtimestamp(kline.open_time / 1000)
        
        return [
            kline.open_time,                    # timestamp
            dt.strftime('%Y-%m-%d %H:%M:%S'),  # datetime
            exchange.upper(),                   # exchange
            f"{kline.symbol.base}_{kline.symbol.quote}",  # symbol
            timeframe,                          # timeframe
            kline.open_price,                   # open
            kline.high_price,                   # high
            kline.low_price,                    # low
            kline.close_price,                  # close
            kline.volume,                       # volume
            kline.quote_volume,                 # quote_volume
            kline.trades_count                  # trades_count
        ]
    
    async def download_candles(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        days: Optional[int] = None,
        filename: Optional[str] = None
    ) -> str:
        """
        Download candles data from specified exchange and save to CSV.
        
        Args:
            exchange: Exchange name ('mexc', 'gateio')
            symbol: Symbol string (BTC_USDT, BTCUSDT, etc.)
            timeframe: Timeframe string (1m, 5m, 1h, 1d, etc.)
            start_date: Start date for data download
            end_date: End date for data download
            days: Number of days back from now (alternative to start/end dates)
            filename: Custom filename (optional, auto-generated if None)
            
        Returns:
            Path to saved CSV file
            
        Raises:
            ValueError: If invalid parameters provided
            Exception: If download fails
        """
        # Validate exchange
        if exchange.lower() not in self.EXCHANGES:
            available = ', '.join(self.EXCHANGES.keys())
            raise ValueError(f"Unsupported exchange: {exchange}. Available: {available}")
        
        # Parse parameters
        symbol_obj = self._parse_symbol(symbol)
        timeframe_enum = self._get_timeframe(timeframe)
        
        # Calculate date range
        if days is not None:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
        elif start_date is None or end_date is None:
            # Default to last 7 days
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=7)
            self.logger.info("No date range specified, defaulting to last 7 days")
        
        # Generate filename
        if filename is None:
            filename = self._generate_filename(exchange, symbol, timeframe, start_date, end_date)
        
        csv_path = self.output_dir / filename
        
        self.logger.info(f"Downloading {exchange.upper()} {symbol} {timeframe} candles from {start_date} to {end_date}")
        
        # Initialize exchange client
        exchange_class = self.EXCHANGES[exchange.lower()]
        client = exchange_class()
        
        try:
            # Download data using batch method for large ranges
            klines = await client.get_klines_batch(symbol_obj, timeframe_enum, start_date, end_date)
            
            if not klines:
                self.logger.warning("No data received from exchange")
                return str(csv_path)
            
            self.logger.info(f"Downloaded {len(klines)} candles, writing to CSV...")
            
            # Write to CSV file
            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header
                writer.writerow(self.CSV_HEADER)
                
                # Write data rows
                for kline in klines:
                    row = self._kline_to_csv_row(kline, exchange, timeframe)
                    writer.writerow(row)
            
            self.logger.info(f"Successfully saved {len(klines)} candles to {csv_path}")
            
            # Log file size
            file_size = csv_path.stat().st_size
            self.logger.info(f"File size: {file_size / 1024:.1f} KB")
            
            return str(csv_path)
            
        except Exception as e:
            self.logger.error(f"Failed to download candles: {e}")
            traceback.print_exc()
            raise e
        finally:
            # Clean up exchange client
            if hasattr(client, 'close'):
                await client.close()
    
    async def download_multiple(
        self,
        download_configs: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Download candles from multiple cex/symbols with coordinated rate limiting.
        
        Implements intelligent batching and rate limiting to prevent API throttling
        while maintaining optimal performance through controlled concurrency.
        
        Args:
            download_configs: List of download configuration dictionaries
                Each dict should contain: exchange, symbol, timeframe, and date parameters
        
        Returns:
            List of paths to saved CSV files
        """
        self.logger.info(f"Starting rate-limited batch download of {len(download_configs)} configurations")
        
        # Get global rate limiter for coordination
        rate_limiter = get_rate_limiter()
        
        # Group configurations by exchange for coordinated processing
        exchange_groups = {}
        for config in download_configs:
            exchange = config.get('exchange', '').lower()
            if exchange not in exchange_groups:
                exchange_groups[exchange] = []
            exchange_groups[exchange].append(config)
        
        self.logger.info(f"Grouped downloads: {[(ex, len(configs)) for ex, configs in exchange_groups.items()]}")
        
        # Process each exchange group with proper rate limiting
        all_results = []
        
        for exchange, configs in exchange_groups.items():
            self.logger.info(f"Processing {len(configs)} downloads for {exchange}")
            
            # Create rate-limited tasks for this exchange
            async def download_with_rate_limiting(config):
                """Download with rate limiting coordination."""
                try:
                    # Coordinate request through rate limiter
                    async with rate_limiter.coordinate_request(exchange):
                        result = await self.download_candles(**config)
                        return result
                except Exception as e:
                    self.logger.error(f"Rate-limited download failed for {config}: {e}")
                    return e
            
            # Execute exchange-specific downloads with controlled concurrency
            exchange_tasks = [download_with_rate_limiting(config) for config in configs]
            exchange_results = await asyncio.gather(*exchange_tasks, return_exceptions=True)
            
            all_results.extend(exchange_results)
            
            # Add inter-exchange delay to prevent cross-exchange rate limit conflicts
            if len(exchange_groups) > 1:  # Only delay if multiple cex
                await asyncio.sleep(0.5)  # 500ms between exchange groups
        
        # Process and categorize results
        successful_files = []
        failed_count = 0
        
        for i, result in enumerate(all_results):
            if isinstance(result, Exception):
                self.logger.error(f"Failed download {i+1}: {result}")
                failed_count += 1
            else:
                successful_files.append(result)
        
        # Log rate limiting statistics
        stats = rate_limiter.get_stats()
        for exchange, stat in stats.items():
            if stat['total_requests'] > 0:
                self.logger.info(
                    f"{stat['name']}: {stat['total_requests']} requests, "
                    f"{stat['available_tokens']}/{stat['max_concurrent']} tokens available"
                )
        
        self.logger.info(f"Rate-limited batch download completed: {len(successful_files)} successful, {failed_count} failed")
        
        return successful_files
    
    def list_available_exchanges(self) -> List[str]:
        """Get list of supported cex."""
        return list(self.EXCHANGES.keys())
    
    def list_available_timeframes(self) -> List[str]:
        """Get list of supported timeframes."""
        return list(self.TIMEFRAME_MAP.keys())


def parse_date(date_str: str) -> datetime:
    """Parse date string in various formats."""
    formats = ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d', '%d/%m/%Y']
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    raise ValueError(f"Unable to parse date: {date_str}. Supported formats: YYYY-MM-DD, YYYY-MM-DD HH:MM:SS")


def main():
    """CLI entry point for candles downloader."""
    parser = argparse.ArgumentParser(
        description="Download historical candlestick data from cryptocurrency cex",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download 30 days of BTC/USDT 1h candles from MEXC
  python candles_downloader.py --exchange mexc --symbol BTC_USDT --timeframe 1h --days 30
  
  # Download specific date range from Gate.io
  python candles_downloader.py --exchange gateio --symbol BTC_USDT --timeframe 1d --start 2024-01-01 --end 2024-02-01
  
  # Download with custom output directory
  python candles_downloader.py --exchange mexc --symbol ETH_USDT --timeframe 5m --days 7 --output ./my_data
        """
    )
    
    parser.add_argument(
        '--exchange', '-e',
        required=True,
        choices=['mexc', 'gateio'],
        help='Exchange to download from'
    )
    
    parser.add_argument(
        '--symbol', '-s',
        required=True,
        help='Trading symbol (e.g., BTC_USDT, BTCUSDT, BTC/USDT)'
    )
    
    parser.add_argument(
        '--timeframe', '-t',
        required=True,
        choices=['1m', '5m', '15m', '30m', '1h', '4h', '12h', '1d', '1w', '1M'],
        help='Candlestick timeframe'
    )
    
    # Date range options
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument(
        '--days', '-d',
        type=int,
        help='Number of days to download (from now backwards)'
    )
    
    date_group.add_argument(
        '--start',
        type=str,
        help='Start date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)'
    )
    
    parser.add_argument(
        '--end',
        type=str,
        help='End date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS), only used with --start'
    )
    
    parser.add_argument(
        '--output', '-o',
        default='data',
        help='Output directory for CSV files (default: data)'
    )
    
    parser.add_argument(
        '--filename', '-f',
        help='Custom output filename (auto-generated if not specified)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Setup logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)
    
    # Parse dates if provided
    start_date = None
    end_date = None
    
    if args.start:
        start_date = parse_date(args.start)
        if args.end:
            end_date = parse_date(args.end)
        else:
            end_date = datetime.utcnow()
    
    # Create downloader
    downloader = CandlesDownloader(output_dir=args.output)
    
    async def download_task():
        try:
            csv_path = await downloader.download_candles(
                exchange=args.exchange,
                symbol=args.symbol,
                timeframe=args.timeframe,
                start_date=start_date,
                end_date=end_date,
                days=args.days,
                filename=args.filename
            )
            print(f"✅ Download completed: {csv_path}")
            return csv_path
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return None
    
    # Run the download
    result = asyncio.run(download_task())
    
    if result:
        print(f"\n📄 CSV file saved to: {result}")
        print("✨ Download completed successfully!")
    else:
        print("\n💥 Download failed!")
        exit(1)


if __name__ == "__main__":
    main()