"""
Simple data loader utility with file-based caching for book ticker snapshots.

Rounds timestamps to 5-minute intervals to enable efficient caching and reduce DB calls.
"""

import asyncio
import os
import pickle
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd

from db.database_manager import get_database_manager
from config.config_manager import HftConfig
from infrastructure.logging import HFTLoggerInterface, get_logger
from utils.kline_utils import round_datetime_to_interval, get_interval_seconds

class BookTickerSnapshotLoader:
    """Simple data loader with file-based caching for book ticker data."""
    
    def __init__(self, cache_dir: str = "book_tickers",
                 logger: HFTLoggerInterface = None):
        """Initialize with cache directory."""
        self.cache_dir = HftConfig.cache_dir / cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or get_logger(__name__)
    

    def _generate_cache_key(self, exchange: str, symbol_base: str, symbol_quote: str, 
                           start_time: datetime, end_time: datetime, rounding_seconds: int) -> str:
        """Generate cache key from parameters."""
        start_rounded = round_datetime_to_interval(start_time, rounding_seconds)
        end_rounded = round_datetime_to_interval(end_time, rounding_seconds)
        
        start_str = start_rounded.strftime("%Y%m%d_%H%M%S")
        end_str = end_rounded.strftime("%Y%m%d_%H%M%S")
        
        return f"{exchange}_{symbol_base}_{symbol_quote}_{start_str}_{end_str}.pkl"
    
    def _load_from_cache(self, cache_key: str) -> Optional[pd.DataFrame]:
        """Load dataframe from cache file."""
        cache_path = self.cache_dir / cache_key
        if cache_path.exists():
            try:
                with open(cache_path, 'rb') as f:
                    return pickle.load(f)
            except Exception:
                # Remove corrupted cache file
                cache_path.unlink(missing_ok=True)
        return None
    
    def _save_to_cache(self, df: pd.DataFrame, cache_key: str) -> None:
        """Save dataframe to cache file."""
        cache_path = self.cache_dir / cache_key
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(df, f)
        except Exception:
            # Ignore cache save errors
            pass
    
    async def get_book_ticker_dataframe(self, exchange: str, symbol_base: str, symbol_quote: str,
                                       start_time: datetime, end_time: datetime, rounding_seconds: int = 0) -> pd.DataFrame:
        """
        Get book ticker dataframe with caching.
        
        First checks cache, falls back to DB if not found.
        Rounds timestamps to 5-minute intervals for cache efficiency.
        """
        # Generate cache key
        cache_key = self._generate_cache_key(exchange, symbol_base, symbol_quote, start_time, end_time, rounding_seconds)
        
        # Try to load from cache
        df = self._load_from_cache(cache_key)
        if df is not None:
            self.logger.info(f"  📁 Loaded from cache: {cache_key}")
            if rounding_seconds:
                df = self.rescale_to_seconds(df, rounding_seconds)

            return df

        # Load from database
        self.logger.info(f"  🗄️  Loading book ticker from database {exchange} {symbol_base} {symbol_quote}...")
        db_manager = await get_database_manager()
        df = await db_manager.get_book_ticker_dataframe(
            exchange=exchange,
            symbol_base=symbol_base,
            symbol_quote=symbol_quote,
            start_time=start_time,
            end_time=end_time,
        )
        
        # Save to cache
        if not df.empty:
            self._save_to_cache(df, cache_key)
            print(f"  💾 Cached as: {cache_key}")

        if rounding_seconds:
            df = self.rescale_to_seconds(df, rounding_seconds)
        
        return df

    # python
    def rescale_to_seconds(self, df: pd.DataFrame, window_seconds: int = 1) -> pd.DataFrame:
        """Rescale book ticker data using the dataframe index as the timestamp."""
        if df.empty:
            return df

        df = df.copy()

        # Drop rows with invalid timestamps
        df = df[~df.index.isna()]
        if df.empty:
            return df

        # Floor index to window boundaries
        window_str = f"{max(int(window_seconds), 1)}S"
        df["timestamp_window"] = df.index.floor(window_str)

        # Build aggregation map for available columns
        agg_map = {"bid_price": "last", "ask_price": "last"}

        aggregated = (
            df.groupby("timestamp_window", sort=True)
            .agg(agg_map)
            .reset_index()
            .rename(columns={"timestamp_window": "timestamp"})
        )

        aggregated.set_index("timestamp", inplace=True)

        return aggregated
