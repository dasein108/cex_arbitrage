#!/usr/bin/env python3
"""
ArbitrageDataPipeline - Historical Data Collection for Arbitrage Analysis

Coordinates data collection from multiple exchanges for arbitrage opportunity analysis.
Handles rate limiting, batch processing, and data validation for reliable collection.

Key Features:
- Rate-limited data collection from multiple exchanges
- Automatic retry logic with exponential backoff
- Data validation and quality checks
- Progress tracking and incremental collection
- Unified CSV output format

Usage:
    from arbitrage_data_pipeline import ArbitrageDataPipeline
    
    pipeline = ArbitrageDataPipeline(output_dir="data/arbitrage")
    await pipeline.collect_data_for_analysis(discovery_file="symbols.json", days=3)
"""

import asyncio
import json
import pandas as pd
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta
import logging
import time

from infrastructure.logging.factory import get_logger
from exchanges.exchange_factory import get_composite_implementation
from config.config_manager import HftConfig
from exchanges.structs.enums import ExchangeEnum
from exchanges.structs.common import Symbol, AssetName
from exchanges.structs.enums import KlineInterval


class ArbitrageDataPipeline:
    """
    Advanced data collection pipeline for arbitrage analysis.
    
    Coordinates data collection from multiple exchanges with rate limiting,
    error handling, and data validation for reliable arbitrage analysis.
    """
    
    def __init__(self, output_dir: str = "data/arbitrage"):
        """
        Initialize the ArbitrageDataPipeline.
        
        Args:
            output_dir: Directory to save collected data files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger = get_logger("ArbitrageDataPipeline")
        self.config_manager = HftConfig()
        
        # Collection configuration
        self.rate_limit_delay = 1.0  # Seconds between requests
        self.max_retries = 3
        self.retry_delay = 2.0
        self.batch_size = 5  # Symbols per batch
        
        # Data validation thresholds
        self.min_data_points = 100
        self.max_price_deviation = 0.5  # 50% price change threshold for outlier detection
        
        # Exchange instances cache
        self._exchange_instances = {}
    
    async def _get_exchange_instance(self, exchange_enum: ExchangeEnum):
        """Get or create exchange instance with caching."""
        if exchange_enum not in self._exchange_instances:
            try:
                exchange_config = self.config_manager.get_exchange_config(exchange_enum.value.lower())
                
                # Use public interface for market data (no authentication needed)
                instance = get_composite_implementation(
                    exchange_config=exchange_config,
                    is_private=False
                )
                
                self._exchange_instances[exchange_enum] = instance
                self.logger.debug(f"Created exchange instance for {exchange_enum.value}")
                
            except Exception as e:
                self.logger.error(f"Failed to create {exchange_enum.value} instance: {e}")
                return None
        
        return self._exchange_instances.get(exchange_enum)
    
    def load_discovery_results(self, discovery_file: str) -> List[Dict[str, Any]]:
        """
        Load symbol discovery results from JSON file.
        
        Args:
            discovery_file: Path to symbol discovery results
            
        Returns:
            List of symbol discovery entries
        """
        discovery_path = Path(discovery_file)
        
        if not discovery_path.exists():
            self.logger.error(f"Discovery file not found: {discovery_file}")
            return []
        
        try:
            with open(discovery_path, 'r') as f:
                data = json.load(f)
            
            # Handle different discovery file formats
            if isinstance(data, dict):
                if 'symbols' in data:
                    symbols = data['symbols']
                elif 'results' in data:
                    symbols = data['results']
                else:
                    # Assume the dict itself contains symbol data
                    symbols = [data] if 'symbol' in data else []
            elif isinstance(data, list):
                symbols = data
            else:
                self.logger.error(f"Unexpected discovery file format: {type(data)}")
                return []
            
            self.logger.info(f"📂 Loaded {len(symbols)} symbols from discovery file")
            return symbols
            
        except Exception as e:
            self.logger.error(f"Failed to load discovery file {discovery_file}: {e}")
            return []
    
    def parse_symbol_from_discovery(self, symbol_entry: Dict[str, Any]) -> Optional[Tuple[str, List[ExchangeEnum]]]:
        """
        Parse symbol and exchanges from discovery entry.
        
        Args:
            symbol_entry: Single entry from discovery results
            
        Returns:
            Tuple of (symbol_pair, list_of_exchanges) or None if parsing failed
        """
        try:
            # Try different field names for symbol
            symbol_pair = None
            for field in ['symbol', 'pair', 'symbol_pair', 'base_quote']:
                if field in symbol_entry:
                    symbol_pair = symbol_entry[field]
                    break
            
            if not symbol_pair:
                # Try to construct from base/quote
                if 'base' in symbol_entry and 'quote' in symbol_entry:
                    symbol_pair = f"{symbol_entry['base']}/{symbol_entry['quote']}"
                else:
                    self.logger.warning(f"Could not extract symbol from entry: {symbol_entry}")
                    return None
            
            # Normalize symbol format (ensure it has /)
            if '/' not in symbol_pair:
                # Try common patterns
                if symbol_pair.endswith('USDT'):
                    base = symbol_pair[:-4]
                    symbol_pair = f"{base}/USDT"
                elif symbol_pair.endswith('USDC'):
                    base = symbol_pair[:-4]
                    symbol_pair = f"{base}/USDC"
                else:
                    self.logger.warning(f"Could not normalize symbol format: {symbol_pair}")
                    return None
            
            # Extract exchanges
            exchanges = []
            for field in ['exchanges', 'available_exchanges', 'supported_exchanges']:
                if field in symbol_entry:
                    exchange_names = symbol_entry[field]
                    if isinstance(exchange_names, str):
                        exchange_names = [exchange_names]
                    
                    for name in exchange_names:
                        try:
                            # Try to map exchange name to enum
                            if name.upper() == 'MEXC' or 'MEXC' in name.upper():
                                exchanges.append(ExchangeEnum.MEXC_SPOT)
                            elif name.upper() == 'GATEIO' or 'GATE' in name.upper():
                                if 'FUTURES' in name.upper():
                                    exchanges.append(ExchangeEnum.GATEIO_FUTURES)
                                else:
                                    exchanges.append(ExchangeEnum.GATEIO_SPOT)
                            # Add more exchange mappings as needed
                        except Exception as e:
                            self.logger.debug(f"Could not map exchange {name}: {e}")
                    break
            
            if not exchanges:
                # Default to common exchanges if not specified
                exchanges = [ExchangeEnum.MEXC_SPOT, ExchangeEnum.GATEIO_SPOT]
            
            return symbol_pair, exchanges
            
        except Exception as e:
            self.logger.warning(f"Failed to parse symbol entry {symbol_entry}: {e}")
            return None
    
    async def fetch_candles_for_symbol(self, symbol_pair: str, exchange_enum: ExchangeEnum, 
                                     days: int = 3) -> Optional[pd.DataFrame]:
        """
        Fetch historical candles for a symbol from a specific exchange.
        
        Args:
            symbol_pair: Trading pair (e.g., "BTC/USDT")
            exchange_enum: Exchange to fetch from
            days: Number of days of historical data
            
        Returns:
            DataFrame with OHLCV data or None if failed
        """
        try:
            # Get exchange instance
            exchange = await self._get_exchange_instance(exchange_enum)
            if not exchange:
                return None
            
            # Parse symbol
            base, quote = symbol_pair.split('/')
            symbol = Symbol(
                base=AssetName(base),
                quote=AssetName(quote),
                is_futures=(exchange_enum == ExchangeEnum.GATEIO_FUTURES)
            )
            
            # Calculate time range
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            
            # Convert to exchange format
            exchange_symbol = await exchange.convert_to_exchange_symbol(symbol)
            
            # Fetch candles data
            self.logger.debug(f"Fetching {days}d candles for {symbol_pair} on {exchange_enum.value}")
            
            candles = await exchange.get_klines(
                symbol=symbol,
                interval=KlineInterval.MINUTE_1,
                start_time=start_time,
                end_time=end_time,
                limit=days * 1440  # 1440 minutes per day
            )
            
            if not candles:
                self.logger.warning(f"No candles data returned for {symbol_pair} on {exchange_enum.value}")
                return None
            
            # Convert to DataFrame
            df_data = []
            for candle in candles:
                df_data.append({
                    'timestamp': candle.timestamp,
                    'open': float(candle.open_price),
                    'high': float(candle.high_price),
                    'low': float(candle.low_price),
                    'close': float(candle.close_price),
                    'volume': float(candle.volume)
                })
            
            df = pd.DataFrame(df_data)
            
            if len(df) < self.min_data_points:
                self.logger.warning(f"Insufficient data for {symbol_pair} on {exchange_enum.value}: {len(df)} points")
                return None
            
            # Basic data validation
            if not self._validate_candles_data(df, symbol_pair, exchange_enum.value):
                return None
            
            self.logger.debug(f"✅ Fetched {len(df)} candles for {symbol_pair} on {exchange_enum.value}")
            return df
            
        except Exception as e:
            self.logger.error(f"Failed to fetch candles for {symbol_pair} on {exchange_enum.value}: {e}")
            return None
    
    def _validate_candles_data(self, df: pd.DataFrame, symbol_pair: str, exchange_name: str) -> bool:
        """
        Validate candles data quality.
        
        Args:
            df: DataFrame with candles data
            symbol_pair: Symbol being validated
            exchange_name: Exchange name
            
        Returns:
            True if data is valid, False otherwise
        """
        try:
            # Check for required columns
            required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            if not all(col in df.columns for col in required_cols):
                self.logger.warning(f"Missing required columns for {symbol_pair} on {exchange_name}")
                return False
            
            # Check for NaN values
            if df[required_cols].isnull().any().any():
                self.logger.warning(f"NaN values found in {symbol_pair} on {exchange_name}")
                return False
            
            # Check for zero or negative prices
            price_cols = ['open', 'high', 'low', 'close']
            if (df[price_cols] <= 0).any().any():
                self.logger.warning(f"Zero or negative prices in {symbol_pair} on {exchange_name}")
                return False
            
            # Check for extreme price movements (potential errors)
            df_sorted = df.sort_values('timestamp')
            price_changes = df_sorted['close'].pct_change().abs()
            if price_changes.max() > self.max_price_deviation:
                self.logger.warning(f"Extreme price movement detected in {symbol_pair} on {exchange_name}")
                return False
            
            # Check OHLC relationships
            invalid_ohlc = (
                (df['high'] < df['low']) |
                (df['high'] < df['open']) |
                (df['high'] < df['close']) |
                (df['low'] > df['open']) |
                (df['low'] > df['close'])
            )
            
            if invalid_ohlc.any():
                self.logger.warning(f"Invalid OHLC relationships in {symbol_pair} on {exchange_name}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.warning(f"Data validation failed for {symbol_pair} on {exchange_name}: {e}")
            return False
    
    def save_candles_to_csv(self, df: pd.DataFrame, symbol_pair: str, 
                          exchange_enum: ExchangeEnum, days: int) -> str:
        """
        Save candles DataFrame to CSV file.
        
        Args:
            df: Candles data
            symbol_pair: Trading pair
            exchange_enum: Exchange enum
            days: Number of days collected
            
        Returns:
            Path to saved CSV file
        """
        # Generate filename
        base, quote = symbol_pair.split('/')
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
        
        filename = f"{exchange_enum.value}_{base}_{quote}_1m_{start_date}_{end_date}.csv"
        file_path = self.output_dir / filename
        
        # Sort by timestamp and save
        df_sorted = df.sort_values('timestamp')
        df_sorted.to_csv(file_path, index=False)
        
        self.logger.debug(f"💾 Saved {len(df)} candles to {file_path}")
        return str(file_path)
    
    async def collect_data_for_analysis(self, discovery_file: str, days: int = 3, 
                                      max_symbols: Optional[int] = None) -> Dict[str, Any]:
        """
        Collect historical candles data for arbitrage analysis.
        
        Args:
            discovery_file: Path to symbol discovery results
            days: Number of days of historical data to collect
            max_symbols: Maximum symbols to process (for testing)
            
        Returns:
            Dictionary with collection results and statistics
        """
        self.logger.info(f"🚀 Starting data collection for arbitrage analysis")
        self.logger.info(f"📅 Collection period: {days} days")
        
        # Load discovery results
        discovery_results = self.load_discovery_results(discovery_file)
        if not discovery_results:
            return {
                'success': False,
                'error': 'No discovery results loaded',
                'total_symbols': 0,
                'successful_downloads': 0,
                'failed_downloads': 0,
                'success_rate': 0.0
            }
        
        # Parse symbols and limit if requested
        symbols_to_process = []
        for entry in discovery_results:
            parsed = self.parse_symbol_from_discovery(entry)
            if parsed:
                symbol_pair, exchanges = parsed
                symbols_to_process.append((symbol_pair, exchanges))
        
        if max_symbols:
            symbols_to_process = symbols_to_process[:max_symbols]
        
        self.logger.info(f"📊 Processing {len(symbols_to_process)} symbols")
        
        # Collection statistics
        total_downloads = 0
        successful_downloads = 0
        failed_downloads = 0
        processed_symbols = []
        
        # Process symbols in batches
        for i in range(0, len(symbols_to_process), self.batch_size):
            batch = symbols_to_process[i:i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            total_batches = (len(symbols_to_process) + self.batch_size - 1) // self.batch_size
            
            self.logger.info(f"📦 Processing batch {batch_num}/{total_batches} ({len(batch)} symbols)")
            
            # Process batch
            batch_tasks = []
            for symbol_pair, exchanges in batch:
                for exchange_enum in exchanges:
                    batch_tasks.append(self._collect_symbol_data(symbol_pair, exchange_enum, days))
                    total_downloads += 1
            
            # Execute batch with rate limiting
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            # Process results
            for j, result in enumerate(batch_results):
                symbol_pair, exchange_enum = batch[j // len(exchanges)][0], batch[j // len(exchanges)][1][j % len(exchanges)]
                
                if isinstance(result, Exception):
                    self.logger.warning(f"❌ {symbol_pair} on {exchange_enum.value}: {result}")
                    failed_downloads += 1
                elif result:
                    self.logger.info(f"✅ {symbol_pair} on {exchange_enum.value}: Collected")
                    successful_downloads += 1
                    if symbol_pair not in processed_symbols:
                        processed_symbols.append(symbol_pair)
                else:
                    failed_downloads += 1
            
            # Rate limiting between batches
            if i + self.batch_size < len(symbols_to_process):
                await asyncio.sleep(self.rate_limit_delay)
        
        # Calculate final statistics
        success_rate = (successful_downloads / total_downloads * 100) if total_downloads > 0 else 0
        
        # Close exchange instances
        for instance in self._exchange_instances.values():
            if hasattr(instance, 'close'):
                try:
                    await instance.close()
                except:
                    pass
        
        results = {
            'success': True,
            'total_symbols': len(symbols_to_process),
            'total_downloads': total_downloads,
            'successful_downloads': successful_downloads,
            'failed_downloads': failed_downloads,
            'success_rate': success_rate,
            'data_directory': str(self.output_dir),
            'symbols_processed': processed_symbols
        }
        
        self.logger.info(f"🎉 Data collection completed: {successful_downloads}/{total_downloads} successful")
        
        return results
    
    async def _collect_symbol_data(self, symbol_pair: str, exchange_enum: ExchangeEnum, 
                                 days: int) -> bool:
        """
        Collect data for a single symbol on a single exchange with retry logic.
        
        Args:
            symbol_pair: Trading pair to collect
            exchange_enum: Exchange to collect from
            days: Number of days to collect
            
        Returns:
            True if successful, False otherwise
        """
        for attempt in range(self.max_retries):
            try:
                # Check if file already exists
                base, quote = symbol_pair.split('/')
                end_date = datetime.now().strftime('%Y%m%d')
                start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
                filename = f"{exchange_enum.value}_{base}_{quote}_1m_{start_date}_{end_date}.csv"
                file_path = self.output_dir / filename
                
                if file_path.exists():
                    self.logger.debug(f"⚡ {symbol_pair} on {exchange_enum.value}: File already exists")
                    return True
                
                # Fetch data
                df = await self.fetch_candles_for_symbol(symbol_pair, exchange_enum, days)
                
                if df is not None:
                    # Save to CSV
                    self.save_candles_to_csv(df, symbol_pair, exchange_enum, days)
                    return True
                
                # If this was the last attempt, fail
                if attempt == self.max_retries - 1:
                    return False
                
                # Wait before retry
                await asyncio.sleep(self.retry_delay * (2 ** attempt))
                
            except Exception as e:
                self.logger.debug(f"Attempt {attempt + 1} failed for {symbol_pair} on {exchange_enum.value}: {e}")
                
                if attempt == self.max_retries - 1:
                    return False
                
                await asyncio.sleep(self.retry_delay * (2 ** attempt))
        
        return False
    
    def validate_collected_data(self) -> Dict[str, Any]:
        """
        Validate the quality and completeness of collected data.
        
        Returns:
            Dictionary with validation results
        """
        self.logger.info(f"🔍 Validating collected data in: {self.output_dir}")
        
        if not self.output_dir.exists():
            return {
                'valid': False,
                'reason': 'Data directory does not exist',
                'complete_symbols': 0,
                'data_completeness': 0.0
            }
        
        # Find all CSV files
        csv_files = list(self.output_dir.glob("*.csv"))
        
        if not csv_files:
            return {
                'valid': False,
                'reason': 'No CSV files found',
                'complete_symbols': 0,
                'data_completeness': 0.0
            }
        
        # Group files by symbol
        symbol_files = {}
        for file_path in csv_files:
            try:
                # Parse filename to extract symbol
                filename = file_path.stem
                parts = filename.split('_')
                
                if len(parts) >= 4:
                    exchange = '_'.join(parts[:2])
                    base = parts[2]
                    quote = parts[3]
                    symbol = f"{base}/{quote}"
                    
                    if symbol not in symbol_files:
                        symbol_files[symbol] = []
                    symbol_files[symbol].append(file_path)
            except:
                continue
        
        # Validate each symbol's data
        complete_symbols = []
        total_symbols = len(symbol_files)
        
        for symbol, files in symbol_files.items():
            if len(files) >= 2:  # Need at least 2 exchanges for arbitrage
                # Check data quality
                valid_files = 0
                for file_path in files:
                    try:
                        df = pd.read_csv(file_path)
                        if len(df) >= self.min_data_points and self._validate_csv_data(df):
                            valid_files += 1
                    except:
                        continue
                
                if valid_files >= 2:
                    complete_symbols.append(symbol)
        
        data_completeness = (len(complete_symbols) / total_symbols * 100) if total_symbols > 0 else 0
        
        return {
            'valid': len(complete_symbols) > 0,
            'complete_symbols': len(complete_symbols),
            'total_symbols': total_symbols,
            'data_completeness': data_completeness,
            'complete_symbol_list': complete_symbols
        }
    
    def _validate_csv_data(self, df: pd.DataFrame) -> bool:
        """Basic validation for CSV data."""
        required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        return (
            all(col in df.columns for col in required_cols) and
            not df[required_cols].isnull().any().any() and
            (df[['open', 'high', 'low', 'close']] > 0).all().all()
        )