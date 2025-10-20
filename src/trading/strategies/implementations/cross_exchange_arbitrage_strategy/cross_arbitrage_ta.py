#!/usr/bin/env python3
"""
Cross-Exchange Arbitrage Technical Analysis

Minimal solution for real-time arbitrage signal generation using historical
thresholds and live order book data from source, dest, and hedge exchanges.
"""

import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Literal, Tuple
from dataclasses import dataclass

from exchanges.structs import Symbol, BookTicker, AssetName, ExchangeEnum
from trading.analysis.data_loader import get_cached_book_ticker_data


@dataclass
class ArbitrageThresholds:
    """Arbitrage entry/exit thresholds calculated from historical data."""
    entry_spread: float  # Minimum profitable spread to enter (90th percentile)
    exit_spread: float   # Exit when spread falls below this
    mean_spread: float   # Average historical spread
    std_spread: float    # Standard deviation for risk assessment
    last_update: datetime
    data_points: int


class CrossArbitrageTA:
    """
    Minimal technical analysis for cross-exchange arbitrage.
    
    Manages historical data, calculates thresholds, and generates
    real-time signals based on current order book prices.
    """
    
    def __init__(
        self,
        symbol: Symbol,
        lookback_hours: int = 24,
        refresh_minutes: int = 15,
        entry_percentile: int = 10,  # Top 10% of spreads
        exit_threshold: float = 0.05,  # Exit at 0.05% spread
        total_fees: float = 0.2  # Total round-trip fees
    ):
        """Initialize with configuration parameters."""
        self.symbol = symbol
        self.lookback_hours = lookback_hours
        self.refresh_minutes = refresh_minutes
        self.entry_percentile = entry_percentile
        self.exit_threshold = exit_threshold
        self.total_fees = total_fees
        
        # Data storage
        self.historical_df: Optional[pd.DataFrame] = None
        self.thresholds: Optional[ArbitrageThresholds] = None
        self.last_refresh: Optional[datetime] = None
        
    async def initialize(self) -> None:
        """Load initial historical data and calculate thresholds."""
        await self.refresh_historical_data()
        
    async def refresh_historical_data(self) -> None:
        """
        Load historical data from DB and recalculate thresholds.
        Called on initialization and every refresh_minutes.
        """
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=self.lookback_hours)
        
        print(f"=� Loading {self.lookback_hours}h data for {self.symbol.base}/{self.symbol.quote}")
        
        # Load data for all 3 exchanges in parallel
        tasks = [
            self._load_exchange_data(ExchangeEnum.MEXC, start_time, end_time),
            self._load_exchange_data(ExchangeEnum.GATEIO, start_time, end_time),
            self._load_exchange_data(ExchangeEnum.GATEIO_FUTURES, start_time, end_time)
        ]
        
        dfs = await asyncio.gather(*tasks)
        dfs = [df for df in dfs if not df.empty]
        
        if not dfs:
            print("L No historical data available")
            return
            
        # Merge all dataframes
        self.historical_df = pd.concat(dfs, axis=1).fillna(method='ffill').dropna()
        
        # Calculate arbitrage spreads
        self._calculate_historical_spreads()
        
        # Update thresholds
        self._update_thresholds()
        
        self.last_refresh = datetime.now(timezone.utc)
        print(f" Loaded {len(self.historical_df)} historical records")
        
    async def _load_exchange_data(
        self, 
        exchange: ExchangeEnum,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """Load and format data for a single exchange."""
        try:
            df = await get_cached_book_ticker_data(
                exchange=exchange.value,
                symbol_base=self.symbol.base,
                symbol_quote=self.symbol.quote,
                start_time=start_time,
                end_time=end_time
            )
            
            if df.empty:
                return pd.DataFrame()
                
            # Set timestamp as index
            df = df.set_index('timestamp')

            prefix = exchange.value.lower()

            # Rename columns with exchange prefix
            rename_cols = {}
            for col in ['bid_price', 'ask_price', 'bid_qty', 'ask_qty']:
                if col in df.columns:
                    rename_cols[col] = f'{prefix}_{col}'
            
            df = df.rename(columns=rename_cols)
            
            # Keep only prefixed columns
            return df[[c for c in df.columns if c.startswith(prefix)]]
            
        except Exception as e:
            print(f"� Failed to load {exchange.value} data: {e}")
            return pd.DataFrame()
    
    def _calculate_historical_spreads(self) -> None:
        """Calculate arbitrage spreads from historical data."""
        if self.historical_df is None or self.historical_df.empty:
            return
            
        df = self.historical_df
        
        # Source�Hedge arbitrage (buy MEXC, sell Gate.io futures)
        if 'mexc_spot_ask_price' in df and 'gateio_futures_bid_price' in df:
            df['source_hedge_arb'] = (
                (df['gateio_futures_bid_price'] - df['mexc_spot_ask_price']) / 
                df['gateio_futures_bid_price'] * 100
            )
        
        # Dest�Hedge arbitrage (buy Gate.io spot, sell Gate.io futures)  
        if 'gateio_spot_bid_price' in df and 'gateio_futures_ask_price' in df:
            df['dest_hedge_arb'] = (
                (df['gateio_spot_bid_price'] - df['gateio_futures_ask_price']) /
                df['gateio_spot_bid_price'] * 100
            )
        
        # Total arbitrage opportunity
        if 'source_hedge_arb' in df and 'dest_hedge_arb' in df:
            df['total_spread'] = df['source_hedge_arb'] + df['dest_hedge_arb']
            df['spread_after_fees'] = df['total_spread'] - self.total_fees
        
    def _update_thresholds(self) -> None:
        """Calculate entry/exit thresholds from historical spreads."""
        if self.historical_df is None or 'spread_after_fees' not in self.historical_df:
            return
            
        spreads = self.historical_df['spread_after_fees'].dropna()
        
        if len(spreads) < 100:  # Need minimum data
            print(f"� Only {len(spreads)} data points, need at least 100")
            return
            
        # Calculate thresholds
        self.thresholds = ArbitrageThresholds(
            entry_spread=float(np.percentile(spreads, 100 - self.entry_percentile)),
            exit_spread=self.exit_threshold,
            mean_spread=float(spreads.mean()),
            std_spread=float(spreads.std()),
            last_update=datetime.now(timezone.utc),
            data_points=len(spreads)
        )
        
        print(f"=� Thresholds updated: Entry>{self.thresholds.entry_spread:.3f}%, Exit<{self.thresholds.exit_spread:.3f}%")
    
    def should_refresh(self) -> bool:
        """Check if historical data needs refreshing."""
        if self.last_refresh is None:
            return True
            
        elapsed = (datetime.now(timezone.utc) - self.last_refresh).total_seconds() / 60
        return elapsed >= self.refresh_minutes
    
    def calculate_realtime_spread(
        self,
        source_book: BookTicker,  # MEXC spot
        dest_book: BookTicker,    # Gate.io spot  
        hedge_book: BookTicker    # Gate.io futures
    ) -> Dict[str, float]:
        """
        Calculate current arbitrage spread from live order book data.
        
        Returns:
            Dict with current spread components and total
        """
        # Source�Hedge: Buy MEXC ask, sell futures bid
        source_hedge_arb = (
            (hedge_book.bid_price - source_book.ask_price) /
            hedge_book.bid_price * 100
        )
        
        # Dest�Hedge: Buy Gate.io spot bid, sell futures ask
        dest_hedge_arb = (
            (dest_book.bid_price - hedge_book.ask_price) /
            dest_book.bid_price * 100
        )
        
        total_spread = source_hedge_arb + dest_hedge_arb
        spread_after_fees = total_spread - self.total_fees
        
        return {
            'source_hedge_arb': source_hedge_arb,
            'dest_hedge_arb': dest_hedge_arb,
            'total_spread': total_spread,
            'spread_after_fees': spread_after_fees,
            'timestamp': datetime.now(timezone.utc)
        }
    
    def generate_signal(
        self,
        source_book: BookTicker,
        dest_book: BookTicker,
        hedge_book: BookTicker,
        position_open: bool = False,
        position_duration_minutes: float = 0
    ) -> Tuple[Literal['enter', 'exit', 'none'], Dict[str, float]]:
        """
        Generate trading signal based on current market conditions.
        
        Args:
            source_book: MEXC spot order book
            dest_book: Gate.io spot order book  
            hedge_book: Gate.io futures order book
            position_open: Whether a position is currently open
            position_duration_minutes: How long position has been open
            
        Returns:
            Tuple of (signal, spread_data)
        """
        # Calculate current spread
        current = self.calculate_realtime_spread(source_book, dest_book, hedge_book)
        current_spread = current['spread_after_fees']
        
        # Default signal
        signal: Literal['enter', 'exit', 'none'] = 'none'
        
        if self.thresholds is None:
            return signal, current
            
        # Generate signal based on position state
        if position_open:
            # Exit conditions
            if (current_spread < self.thresholds.exit_spread or
                position_duration_minutes > 120):  # Max 2 hours
                signal = 'exit'
        else:
            # Entry conditions
            if (current_spread > self.thresholds.entry_spread and
                current_spread > 0.1):  # Minimum 0.1% profit after fees
                signal = 'enter'
        
        # Add threshold info to output
        current['entry_threshold'] = self.thresholds.entry_spread
        current['exit_threshold'] = self.thresholds.exit_spread
        current['signal'] = signal
        
        return signal, current


# Integration helper for cross_exchange_arbitrage_task.py
async def create_ta_for_task(symbol: Symbol) -> CrossArbitrageTA:
    """Helper to create and initialize TA for the arbitrage task."""
    ta = CrossArbitrageTA(
        symbol=symbol,
        lookback_hours=24,
        refresh_minutes=15,
        entry_percentile=10,
        exit_threshold=0.05,
        total_fees=0.2
    )
    
    await ta.initialize()
    return ta