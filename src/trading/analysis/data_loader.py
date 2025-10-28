"""
Simple data loader utility with file-based caching for book ticker snapshots.

Rounds timestamps to 5-minute intervals to enable efficient caching and reduce DB calls.
"""

import asyncio
import os
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd

from db.database_manager import get_database_manager


class CachedDataLoader:
    """Simple data loader with file-based caching for book ticker data."""
    
    def __init__(self, cache_dir: str = "cache/snapshots"):
        """Initialize with cache directory."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _round_to_5min(self, dt: datetime) -> datetime:
        """Round datetime to nearest 5-minute interval."""
        # Round down to nearest 5-minute mark
        minutes = (dt.minute // 5) * 5
        return dt.replace(minute=minutes, second=0, microsecond=0)
    
    def _generate_cache_key(self, exchange: str, symbol_base: str, symbol_quote: str, 
                           start_time: datetime, end_time: datetime) -> str:
        """Generate cache key from parameters."""
        start_rounded = self._round_to_5min(start_time)
        end_rounded = self._round_to_5min(end_time)
        
        start_str = start_rounded.strftime("%Y%m%d_%H%M")
        end_str = end_rounded.strftime("%Y%m%d_%H%M")
        
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
                                       start_time: datetime, end_time: datetime, limit: Optional[int] = None) -> pd.DataFrame:
        """
        Get book ticker dataframe with caching.
        
        First checks cache, falls back to DB if not found.
        Rounds timestamps to 5-minute intervals for cache efficiency.
        """
        # Generate cache key
        cache_key = self._generate_cache_key(exchange, symbol_base, symbol_quote, start_time, end_time)
        
        # Try to load from cache
        df = self._load_from_cache(cache_key)
        if df is not None:
            print(f"  📁 Loaded from cache: {cache_key}")
            return df
        
        # Load from database
        print(f"  🗄️  Loading book ticker from database {exchange} {symbol_base} {symbol_quote}...")
        db_manager = await get_database_manager()
        df = await db_manager.get_book_ticker_dataframe(
            exchange=exchange,
            symbol_base=symbol_base,
            symbol_quote=symbol_quote,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        # Save to cache
        if not df.empty:
            self._save_to_cache(df, cache_key)
            print(f"  💾 Cached as: {cache_key}")
        
        return df
    
    async def get_multi_exchange_data(self, exchanges: List[str], symbol_base: str, symbol_quote: str,
                                     start_time: datetime, end_time: datetime) -> Dict[str, pd.DataFrame]:
        """Load data for multiple exchanges simultaneously."""
        tasks = [
            self.get_book_ticker_dataframe(exchange, symbol_base, symbol_quote, start_time, end_time)
            for exchange in exchanges
        ]
        results = await asyncio.gather(*tasks)
        return {exchange: df for exchange, df in zip(exchanges, results)}
    
    def rescale_to_5min(self, df: pd.DataFrame) -> pd.DataFrame:
        """Rescale book ticker data to 5-minute intervals using OHLC logic."""
        return self.rescale_to_window(df, 5)
    
    def rescale_to_window(self, df: pd.DataFrame, window_minutes: int) -> pd.DataFrame:
        """Rescale book ticker data to any window size using OHLC logic."""
        if df.empty:
            return df
        
        # Ensure timestamp is datetime
        if 'timestamp' not in df.columns:
            return df
            
        df = df.copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Round timestamps to window boundaries
        df['timestamp_window'] = df['timestamp'].dt.floor(f'{window_minutes}T')
        
        # Group by window intervals and aggregate
        aggregated = df.groupby('timestamp_window').agg({
            'bid_price': 'last',    # Use closing prices
            'ask_price': 'last',
            'bid_qty': 'mean',      # Average quantities
            'ask_qty': 'mean'
        }).reset_index().rename(columns={'timestamp_window': 'timestamp'})
        
        return aggregated


# Global instance for convenience
cached_loader = CachedDataLoader()


async def get_cached_book_ticker_data(exchange: str, symbol_base: str, symbol_quote: str,
                                     start_time: datetime, end_time: datetime, limit: Optional[int] = None) -> pd.DataFrame:
    """Convenience function for cached book ticker data loading."""
    return await cached_loader.get_book_ticker_dataframe(
        exchange=exchange,
        symbol_base=symbol_base, 
        symbol_quote=symbol_quote,
        start_time=start_time,
        end_time=end_time,
        limit=limit
    )