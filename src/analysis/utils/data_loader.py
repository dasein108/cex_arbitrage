#!/usr/bin/env python3
"""
Data Loader Utilities

Memory-efficient CSV data loading for arbitrage analysis.
Optimized for streaming processing of large historical datasets.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Iterator, Tuple
import pandas as pd
from msgspec import Struct

# Add parent directories to path for imports
import sys
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class CandleData(Struct):
    """Single candle data point optimized for memory efficiency"""
    timestamp: int              # Unix timestamp in milliseconds
    open_price: float
    high_price: float  
    low_price: float
    close_price: float
    volume: float
    quote_volume: float


class DataLoader:
    """
    Memory-efficient data loader for historical candle data.
    
    Features:
    - Streaming CSV processing to minimize memory usage
    - Timestamp synchronization between exchanges
    - Data validation and integrity checks
    - Support for chunked processing
    """
    
    def __init__(self, data_dir: str):
        """Initialize data loader with data directory"""
        self.data_dir = Path(data_dir)
        self.logger = logging.getLogger(__name__)
        
        if not self.data_dir.exists():
            raise ValueError(f"Data directory does not exist: {data_dir}")
    
    def find_symbol_files(self, symbol: str) -> Dict[str, Optional[Path]]:
        """
        Find CSV files for a symbol across the 3 supported exchanges.
        
        Args:
            symbol: Trading symbol (e.g., "BTC_USDT")
            
        Returns:
            Dictionary mapping exchange types to file paths
        """
        symbol_files = {}
        
        # Look for files from the 3 supported exchange types
        exchange_patterns = {
            'mexc_spot': f"mexc_{symbol}_1m_*.csv",
            'gateio_spot': f"gateio_{symbol}_1m_*.csv", 
            'gateio_futures': f"gateio_futures_{symbol}_1m_*.csv"
        }
        
        for exchange_type, pattern in exchange_patterns.items():
            matching_files = list(self.data_dir.glob(pattern))
            
            if matching_files:
                # Use the most recent file if multiple exist
                symbol_files[exchange_type] = max(matching_files, key=lambda p: p.stat().st_mtime)
            else:
                symbol_files[exchange_type] = None
                self.logger.debug(f"No data file found for {exchange_type} {symbol}")
        
        # Also check for generic gateio files (without futures in name) as spot files
        if not symbol_files.get('gateio_spot'):
            generic_pattern = f"gateio_{symbol}_1m_*.csv"
            matching_files = [f for f in self.data_dir.glob(generic_pattern) if 'futures' not in f.name]
            if matching_files:
                symbol_files['gateio_spot'] = max(matching_files, key=lambda p: p.stat().st_mtime)
        
        return symbol_files
    
    def load_candle_data(self, file_path: Path, chunk_size: int = 10000) -> Iterator[List[CandleData]]:
        """
        Load candle data from CSV file in chunks for memory efficiency.
        
        Args:
            file_path: Path to CSV file
            chunk_size: Number of rows per chunk
            
        Yields:
            Lists of CandleData objects
        """
        if not file_path.exists():
            self.logger.error(f"File does not exist: {file_path}")
            return
        
        try:
            # Use pandas for efficient CSV reading with chunks
            csv_reader = pd.read_csv(
                file_path, 
                chunksize=chunk_size,
                dtype={
                    'timestamp': 'int64',
                    'open': 'float64',
                    'high': 'float64', 
                    'low': 'float64',
                    'close': 'float64',
                    'volume': 'float64',
                    'quote_volume': 'float64'
                }
            )
            
            for chunk_df in csv_reader:
                chunk_data = []
                
                for _, row in chunk_df.iterrows():
                    try:
                        candle = CandleData(
                            timestamp=int(row['timestamp']),
                            open_price=float(row['open']),
                            high_price=float(row['high']),
                            low_price=float(row['low']),
                            close_price=float(row['close']),
                            volume=float(row['volume']),
                            quote_volume=float(row['quote_volume'])
                        )
                        chunk_data.append(candle)
                    except (ValueError, KeyError) as e:
                        self.logger.warning(f"Skipping invalid row in {file_path}: {e}")
                        continue
                
                if chunk_data:
                    yield chunk_data
                    
        except Exception as e:
            self.logger.error(f"Error loading data from {file_path}: {e}")
            raise
    
    def synchronize_timestamps(self, 
                             exchange1_data: List[CandleData], 
                             exchange2_data: List[CandleData]) -> List[Tuple[CandleData, CandleData]]:
        """
        Synchronize candle data by timestamps for spread calculation.
        
        Args:
            exchange1_data: First exchange candle data
            exchange2_data: Second exchange candle data
            
        Returns:
            List of synchronized (exchange1, exchange2) candle pairs
        """
        # Convert to dictionaries for O(1) lookup
        exchange1_dict = {candle.timestamp: candle for candle in exchange1_data}
        exchange2_dict = {candle.timestamp: candle for candle in exchange2_data}
        
        # Find common timestamps
        common_timestamps = set(exchange1_dict.keys()) & set(exchange2_dict.keys())
        
        if not common_timestamps:
            self.logger.warning("No common timestamps found between exchanges")
            return []
        
        # Create synchronized pairs
        synchronized_pairs = [
            (exchange1_dict[ts], exchange2_dict[ts]) 
            for ts in sorted(common_timestamps)
        ]
        
        sync_rate = len(synchronized_pairs) / max(len(exchange1_data), len(exchange2_data)) * 100
        self.logger.debug(f"Synchronized {len(synchronized_pairs)} data points ({sync_rate:.1f}% sync rate)")
        
        return synchronized_pairs
    
    def validate_data_quality(self, candles: List[CandleData]) -> Dict[str, any]:
        """
        Validate data quality and return statistics.
        
        Args:
            candles: List of candle data
            
        Returns:
            Dictionary with quality metrics
        """
        if not candles:
            return {'valid': False, 'reason': 'No data'}
        
        # Check for missing or invalid prices
        invalid_count = 0
        zero_volume_count = 0
        
        for candle in candles:
            if (candle.open_price <= 0 or candle.high_price <= 0 or 
                candle.low_price <= 0 or candle.close_price <= 0):
                invalid_count += 1
            
            if candle.volume == 0:
                zero_volume_count += 1
        
        # Check timestamp continuity (should be 1-minute intervals)
        timestamp_gaps = 0
        if len(candles) > 1:
            for i in range(1, len(candles)):
                expected_ts = candles[i-1].timestamp + 60000  # 1 minute in ms
                if candles[i].timestamp != expected_ts:
                    timestamp_gaps += 1
        
        quality_metrics = {
            'valid': True,
            'total_candles': len(candles),
            'invalid_prices': invalid_count,
            'zero_volume': zero_volume_count,
            'timestamp_gaps': timestamp_gaps,
            'invalid_price_rate': invalid_count / len(candles) * 100,
            'zero_volume_rate': zero_volume_count / len(candles) * 100,
            'gap_rate': timestamp_gaps / max(1, len(candles) - 1) * 100
        }
        
        # Mark as invalid if too many issues
        if (quality_metrics['invalid_price_rate'] > 5 or 
            quality_metrics['gap_rate'] > 10):
            quality_metrics['valid'] = False
            quality_metrics['reason'] = 'Poor data quality'
        
        return quality_metrics
    
    def get_data_summary(self, symbol: str) -> Dict[str, any]:
        """
        Get summary information about available data for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Summary statistics
        """
        files = self.find_symbol_files(symbol)
        summary = {
            'symbol': symbol,
            'mexc_file': str(files.get('mexc')) if files.get('mexc') else None,
            'gateio_file': str(files.get('gateio')) if files.get('gateio') else None,
            'has_both_exchanges': all(files.values()),
            'file_sizes': {}
        }
        
        for exchange, file_path in files.items():
            if file_path and file_path.exists():
                size_mb = file_path.stat().st_size / (1024 * 1024)
                summary['file_sizes'][exchange] = f"{size_mb:.1f} MB"
        
        return summary