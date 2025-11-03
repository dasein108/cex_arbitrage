"""
Dual-Mode Arbitrage Data Provider

High-performance data provider supporting both backtesting and live trading modes.
Automatically optimizes data structures and operations based on mode.

Key Features:
- Backtesting: Full DataFrame operations with vectorized processing
- Live Trading: Rolling buffer with incremental updates
- Automatic mode detection and optimization
- Memory-efficient data management
"""

import asyncio
import pandas as pd
from datetime import datetime, UTC
from collections import deque
from typing import Optional, Dict, Any, Union
from dataclasses import dataclass

from exchanges.structs import Symbol, ExchangeEnum
from exchanges.structs.enums import KlineInterval
from trading.research.cross_arbitrage.book_ticker_source import BookTickerSourceProtocol


@dataclass
class DataProviderConfig:
    """Configuration for data provider behavior."""
    mode: str = 'backtest'  # 'backtest' or 'live'
    live_buffer_size: int = 1000  # Rolling buffer size for live mode
    cache_ttl_minutes: int = 30  # Cache TTL for backtesting
    context_window_size: int = 100  # Context window for live indicator calculations


class ArbitrageDataProvider:
    """
    Dual-mode data provider optimized for both backtesting and live trading.
    
    Backtesting Mode:
    - Loads full historical DataFrames for vectorized operations
    - Caches data to avoid repeated downloads
    - Optimized for batch processing
    
    Live Trading Mode:
    - Maintains rolling buffer of recent data
    - Incremental updates with minimal memory allocation
    - Sub-millisecond update performance
    """
    
    def __init__(self, source: BookTickerSourceProtocol, config: DataProviderConfig = None):
        self.source = source
        self.config = config or DataProviderConfig()
        
        # Backtesting data cache
        self._historical_cache: Dict[str, pd.DataFrame] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        
        # Live trading rolling buffer
        self._live_buffer: deque = deque(maxlen=self.config.live_buffer_size)
        self._live_columns: Optional[list] = None
        
        # Performance metrics
        self._metrics = {
            'cache_hits': 0,
            'cache_misses': 0,
            'live_updates': 0,
            'avg_update_time_ms': 0.0
        }
    
    @property
    def mode(self) -> str:
        """Current operation mode."""
        return self.config.mode
    
    @mode.setter
    def mode(self, value: str):
        """Switch operation mode and optimize accordingly."""
        if value not in ['backtest', 'live']:
            raise ValueError("Mode must be 'backtest' or 'live'")
        self.config.mode = value
        
        if value == 'live' and not self._live_buffer:
            print(f"🔄 Switched to live mode - buffer initialized (size: {self.config.live_buffer_size})")
    
    async def get_historical_data(self, symbol: Symbol, days: int, 
                                exchanges: list[ExchangeEnum] = None) -> pd.DataFrame:
        """
        Get historical data optimized for current mode.
        
        Backtesting Mode: Returns full historical DataFrame with caching
        Live Mode: Returns current buffer as DataFrame for initial context
        """
        if self.mode == 'backtest':
            return await self._get_historical_backtest(symbol, days, exchanges)
        else:
            return await self._get_historical_live(symbol, days, exchanges)
    
    async def _get_historical_backtest(self, symbol: Symbol, days: int,
                                     exchanges: list[ExchangeEnum] = None) -> pd.DataFrame:
        """Optimized historical data loading for backtesting."""
        cache_key = f"{symbol.base}_{symbol.quote}_{days}"
        
        # Check cache first
        if cache_key in self._historical_cache:
            cache_time = self._cache_timestamps[cache_key]
            if (datetime.now(UTC) - cache_time).total_seconds() < self.config.cache_ttl_minutes * 60:
                self._metrics['cache_hits'] += 1
                print(f"📊 Cache hit for {cache_key}")
                return self._historical_cache[cache_key].copy()
        
        # Cache miss - load fresh data
        self._metrics['cache_misses'] += 1
        print(f"📥 Loading historical data for {symbol} ({days} days)")
        
        exchanges = exchanges or [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]
        df = await self.source.get_multi_exchange_data(
            exchanges=exchanges,
            symbol=symbol,
            hours=days * 24,
            timeframe=KlineInterval.MINUTE_5
        )
        
        # Cache the result
        self._historical_cache[cache_key] = df.copy()
        self._cache_timestamps[cache_key] = datetime.now(UTC)
        
        print(f"💾 Cached {len(df)} rows for {cache_key}")
        return df
    
    async def _get_historical_live(self, symbol: Symbol, days: int,
                                 exchanges: list[ExchangeEnum] = None) -> pd.DataFrame:
        """Initialize live buffer with recent historical data."""
        if not self._live_buffer:
            # First time initialization - load recent data to bootstrap buffer
            print(f"🚀 Initializing live buffer with recent data...")
            exchanges = exchanges or [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]
            df = await self.source.get_multi_exchange_data(
                exchanges=exchanges,
                symbol=symbol,
                hours=min(days * 24, 24),  # Max 24 hours for initial load
                timeframe=KlineInterval.MINUTE_5
            )
            
            # Populate buffer with recent data
            if not df.empty:
                self._live_columns = list(df.columns)
                for idx, row in df.tail(self.config.live_buffer_size).iterrows():
                    row_dict = row.to_dict()
                    row_dict['timestamp'] = idx
                    self._live_buffer.append(row_dict)
                print(f"📊 Initialized live buffer with {len(self._live_buffer)} rows")
        
        # Return current buffer as DataFrame
        return self._buffer_to_dataframe()
    
    async def update_realtime(self, new_data: Dict[str, Any]) -> pd.DataFrame:
        """
        Add real-time data update and return context window for indicator calculation.
        
        Optimized for sub-millisecond performance in live trading.
        """
        if self.mode != 'live':
            raise ValueError("update_realtime only available in live mode")
        
        import time
        start_time = time.perf_counter()
        
        # Ensure timestamp is included
        if 'timestamp' not in new_data:
            new_data['timestamp'] = datetime.now(UTC)
        
        # Add to rolling buffer (automatically removes oldest when full)
        self._live_buffer.append(new_data)
        self._metrics['live_updates'] += 1
        
        # Update column tracking
        if self._live_columns is None:
            self._live_columns = list(new_data.keys())
        
        # Return context window for indicator calculations
        context_df = self._buffer_to_dataframe(last_n=self.config.context_window_size)
        
        # Update performance metrics
        update_time = (time.perf_counter() - start_time) * 1000  # Convert to ms
        self._update_avg_time(update_time)
        
        return context_df
    
    def _buffer_to_dataframe(self, last_n: Optional[int] = None) -> pd.DataFrame:
        """Convert rolling buffer to DataFrame efficiently."""
        if not self._live_buffer:
            return pd.DataFrame()
        
        # Get last N rows or all if None
        if last_n is not None:
            data = list(self._live_buffer)[-last_n:]
        else:
            data = list(self._live_buffer)
        
        if not data:
            return pd.DataFrame()
        
        # Create DataFrame with timestamp index
        df = pd.DataFrame(data)
        if 'timestamp' in df.columns:
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)
        
        return df
    
    def _update_avg_time(self, new_time_ms: float):
        """Update rolling average of update times."""
        current_avg = self._metrics['avg_update_time_ms']
        update_count = self._metrics['live_updates']
        
        # Simple rolling average
        self._metrics['avg_update_time_ms'] = (
            (current_avg * (update_count - 1) + new_time_ms) / update_count
        )
    
    def get_buffer_status(self) -> Dict[str, Any]:
        """Get current buffer status and performance metrics."""
        return {
            'mode': self.mode,
            'buffer_size': len(self._live_buffer),
            'buffer_capacity': self.config.live_buffer_size,
            'cache_hits': self._metrics['cache_hits'],
            'cache_misses': self._metrics['cache_misses'],
            'live_updates': self._metrics['live_updates'],
            'avg_update_time_ms': round(self._metrics['avg_update_time_ms'], 3),
            'cache_hit_ratio': (
                self._metrics['cache_hits'] / 
                max(1, self._metrics['cache_hits'] + self._metrics['cache_misses'])
            )
        }
    
    def clear_cache(self):
        """Clear historical data cache."""
        self._historical_cache.clear()
        self._cache_timestamps.clear()
        print("🗑️ Historical data cache cleared")
    
    def reset_live_buffer(self):
        """Reset live trading buffer."""
        self._live_buffer.clear()
        self._live_columns = None
        print("🔄 Live buffer reset")