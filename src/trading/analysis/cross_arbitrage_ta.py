#!/usr/bin/env python3
"""
Cross-Exchange Arbitrage Technical Analysis

Minimal solution for real-time arbitrage signal generation using historical
thresholds and live order book data from source, dest, and hedge exchanges.

Domain-aware implementation respecting separated domain architecture:
- Uses public domain interfaces for market data access
- Maintains domain boundaries between data sources
- HFT-optimized with sub-millisecond performance targets
"""

import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Literal, Tuple
from dataclasses import dataclass

from exchanges.structs import Symbol, BookTicker, AssetName, ExchangeEnum
from trading.analysis.data_loader import get_cached_book_ticker_data
from infrastructure.logging import HFTLoggerInterface, get_logger


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
    
    Domain-aware design:
    - Separates public domain data access (market data)
    - Maintains domain boundaries throughout calculation pipeline
    - Uses HFT-optimized data structures and algorithms
    """
    
    def __init__(
        self,
        symbol: Symbol,
        lookback_hours: int = 24,
        refresh_minutes: int = 15,
        entry_percentile: int = 10,  # Top 10% of spreads
        exit_threshold: float = 0.05,  # Exit at 0.05% spread
        total_fees: float = 0.2,  # Total round-trip fees
        logger: Optional[HFTLoggerInterface] = None
    ):
        """Initialize with configuration parameters."""
        self.symbol = symbol
        self.lookback_hours = lookback_hours
        self.refresh_minutes = refresh_minutes
        self.entry_percentile = entry_percentile
        self.exit_threshold = exit_threshold
        self.total_fees = total_fees
        
        # Domain-aware logging
        self.logger = logger or get_logger(f'cross_arbitrage_ta.{symbol}')
        
        # Data storage (HFT-optimized)
        self.historical_df: Optional[pd.DataFrame] = None
        self.thresholds: Optional[ArbitrageThresholds] = None
        self.last_refresh: Optional[datetime] = None
        
        # Performance tracking
        self._calculation_count = 0
        
    async def initialize(self) -> None:
        """Load initial historical data and calculate thresholds."""
        self.logger.info("🔄 Initializing CrossArbitrageTA", 
                        symbol=str(self.symbol),
                        lookback_hours=self.lookback_hours)
        
        await self.refresh_historical_data()
        
        if self.thresholds:
            self.logger.info("✅ CrossArbitrageTA initialized",
                           entry_threshold=f"{self.thresholds.entry_spread:.4f}%",
                           data_points=self.thresholds.data_points)
        else:
            self.logger.warning("⚠️ CrossArbitrageTA initialized with no thresholds")
        
    async def refresh_historical_data(self) -> None:
        """
        Load historical data from DB and recalculate thresholds.
        Called on initialization and every refresh_minutes.
        
        Domain-aware data loading respecting separated domain architecture.
        """
        start_time = datetime.now(timezone.utc)
        end_time = start_time
        start_time = end_time - timedelta(hours=self.lookback_hours)
        
        self.logger.debug("📊 Loading historical data",
                         start_time=start_time.isoformat(),
                         end_time=end_time.isoformat())
        
        try:
            # Load data for all 3 exchanges in parallel (domain-aware)
            tasks = [
                self._load_exchange_data("mexc", ExchangeEnum.MEXC, start_time, end_time),
                self._load_exchange_data("gateio_spot", ExchangeEnum.GATEIO, start_time, end_time),
                self._load_exchange_data("gateio_futures", ExchangeEnum.GATEIO_FUTURES, start_time, end_time)
            ]
            
            dfs = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter successful results and handle exceptions
            valid_dfs = []
            for i, result in enumerate(dfs):
                if isinstance(result, Exception):
                    exchange_names = ["mexc", "gateio_spot", "gateio_futures"]
                    self.logger.warning(f"Failed to load {exchange_names[i]} data: {result}")
                else:
                    valid_dfs.append(result)
            
            if len(valid_dfs) < 3:
                self.logger.error("❌ Insufficient data sources for arbitrage calculation")
                return
            
            # Merge all dataframes (HFT-optimized)
            self.historical_df = pd.concat(valid_dfs, axis=1).fillna(method='ffill').dropna()
            
            if self.historical_df.empty:
                self.logger.warning("⚠️ No overlapping data found across exchanges")
                return
            
            # Calculate arbitrage spreads
            self._calculate_historical_spreads()
            
            # Update thresholds
            self._update_thresholds()
            
            self.last_refresh = datetime.now(timezone.utc)
            
            self.logger.debug("✅ Historical data refreshed",
                             data_points=len(self.historical_df),
                             time_range=f"{self.historical_df.index[0]} to {self.historical_df.index[-1]}")
            
        except Exception as e:
            self.logger.error(f"❌ Error refreshing historical data: {e}")
            
    async def _load_exchange_data(
        self, 
        prefix: str, 
        exchange: ExchangeEnum,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """
        Load and format data for a single exchange.
        
        Domain-aware loading respecting public domain boundaries.
        """
        try:
            # Domain-aware data loading (public domain only)
            df = await get_cached_book_ticker_data(
                exchange=exchange.value,
                symbol_base=self.symbol.base,
                symbol_quote=self.symbol.quote,
                start_time=start_time,
                end_time=end_time
            )
            
            if df.empty:
                self.logger.warning(f"No data available for {exchange.value}")
                return pd.DataFrame()
                
            # Rename columns with exchange prefix (domain-safe)
            df = df.set_index('timestamp')
            for col in ['bid_price', 'ask_price', 'bid_qty', 'ask_qty']:
                if col in df.columns:
                    df[f'{prefix}_{col}'] = df[col]
            
            # Keep only prefixed columns (domain isolation)
            return df[[c for c in df.columns if c.startswith(prefix)]]
            
        except Exception as e:
            self.logger.error(f"Error loading {prefix} data: {e}")
            return pd.DataFrame()
    
    def _calculate_historical_spreads(self) -> None:
        """
        Calculate arbitrage spreads from historical data.
        
        HFT-optimized calculations with domain awareness.
        """
        if self.historical_df is None or self.historical_df.empty:
            return
            
        df = self.historical_df
        
        # Source→Hedge arbitrage (buy MEXC, sell Gate.io futures)
        # Domain: Public market data → calculated trading signal
        df['source_hedge_arb'] = (
            (df['gateio_futures_bid_price'] - df['mexc_ask_price']) / 
            df['gateio_futures_bid_price'] * 100
        )
        
        # Dest→Hedge arbitrage (buy Gate.io spot, sell Gate.io futures)  
        # Domain: Public market data → calculated trading signal
        df['dest_hedge_arb'] = (
            (df['gateio_spot_bid_price'] - df['gateio_futures_ask_price']) /
            df['gateio_spot_bid_price'] * 100
        )
        
        # Total arbitrage opportunity
        df['total_spread'] = df['source_hedge_arb'] + df['dest_hedge_arb']
        
        # Apply fees (domain-aware fee calculation)
        df['spread_after_fees'] = df['total_spread'] - self.total_fees
        
    def _update_thresholds(self) -> None:
        """
        Calculate entry/exit thresholds from historical spreads.
        
        HFT-optimized statistical calculations.
        """
        if self.historical_df is None or 'spread_after_fees' not in self.historical_df:
            return
            
        spreads = self.historical_df['spread_after_fees'].dropna()
        
        if len(spreads) < 100:  # Minimum data requirement
            self.logger.warning(f"Insufficient data for thresholds: {len(spreads)} points")
            return
            
        # HFT-optimized percentile calculation
        self.thresholds = ArbitrageThresholds(
            entry_spread=np.percentile(spreads, 100 - self.entry_percentile),
            exit_spread=self.exit_threshold,
            mean_spread=spreads.mean(),
            std_spread=spreads.std(),
            last_update=datetime.now(timezone.utc),
            data_points=len(spreads)
        )
        
        self.logger.debug("📊 Thresholds updated",
                         entry_spread=f"{self.thresholds.entry_spread:.4f}%",
                         mean_spread=f"{self.thresholds.mean_spread:.4f}%",
                         data_points=self.thresholds.data_points)
    
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
        
        Domain-aware calculation using public domain book ticker data.
        HFT-optimized for sub-millisecond execution.
        
        Returns:
            Dict with current spread components and total
        """
        # HFT-optimized calculation (single pass)
        # Source→Hedge: Buy MEXC ask, sell futures bid
        source_hedge_arb = (
            (hedge_book.bid_price - source_book.ask_price) /
            hedge_book.bid_price * 100
        )
        
        # Dest→Hedge: Buy Gate.io spot bid, sell futures ask
        dest_hedge_arb = (
            (dest_book.bid_price - hedge_book.ask_price) /
            dest_book.bid_price * 100
        )
        
        total_spread = source_hedge_arb + dest_hedge_arb
        spread_after_fees = total_spread - self.total_fees
        
        # Performance tracking
        self._calculation_count += 1
        
        return {
            'source_hedge_arb': source_hedge_arb,
            'dest_hedge_arb': dest_hedge_arb,
            'total_spread': total_spread,
            'spread_after_fees': spread_after_fees,
            'timestamp': datetime.now(timezone.utc),
            'calculation_count': self._calculation_count
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
        
        Domain-aware signal generation using public domain market data.
        HFT-optimized decision logic.
        
        Args:
            source_book: MEXC spot order book
            dest_book: Gate.io spot order book  
            hedge_book: Gate.io futures order book
            position_open: Whether a position is currently open
            position_duration_minutes: How long position has been open
            
        Returns:
            Tuple of (signal, spread_data)
        """
        # Check if we need to refresh historical data (async operation)
        if self.should_refresh():
            self.logger.debug("📊 Historical data refresh needed")
            # Note: In production, trigger async refresh without blocking
            # asyncio.create_task(self.refresh_historical_data())
        
        # Calculate current spread (HFT-optimized)
        current = self.calculate_realtime_spread(source_book, dest_book, hedge_book)
        current_spread = current['spread_after_fees']
        
        # Default signal
        signal: Literal['enter', 'exit', 'none'] = 'none'
        
        if self.thresholds is None:
            self.logger.warning("⚠️ No thresholds available for signal generation")
            return signal, current
            
        # HFT-optimized signal generation logic
        if position_open:
            # Exit conditions (prioritized for speed)
            if (current_spread < self.thresholds.exit_spread or
                position_duration_minutes > 120):  # Max 2 hours
                signal = 'exit'
                self.logger.debug("📉 Exit signal generated",
                                current_spread=f"{current_spread:.4f}%",
                                exit_threshold=f"{self.thresholds.exit_spread:.4f}%",
                                duration_minutes=position_duration_minutes)
        else:
            # Entry conditions
            if (current_spread > self.thresholds.entry_spread and
                current_spread > 0.1):  # Minimum 0.1% profit after fees
                signal = 'enter'
                self.logger.debug("📈 Enter signal generated",
                                current_spread=f"{current_spread:.4f}%",
                                entry_threshold=f"{self.thresholds.entry_spread:.4f}%")
        
        # Add threshold info to output (domain-safe)
        current['entry_threshold'] = self.thresholds.entry_spread
        current['exit_threshold'] = self.thresholds.exit_spread
        current['signal'] = signal
        current['thresholds_age'] = (datetime.now(timezone.utc) - self.thresholds.last_update).total_seconds()
        
        return signal, current
    
    def get_performance_metrics(self) -> Dict[str, any]:
        """Get performance metrics for HFT compliance monitoring."""
        return {
            'calculation_count': self._calculation_count,
            'last_refresh': self.last_refresh.isoformat() if self.last_refresh else None,
            'thresholds_available': self.thresholds is not None,
            'data_points': self.thresholds.data_points if self.thresholds else 0,
            'refresh_interval_minutes': self.refresh_minutes,
            'symbol': str(self.symbol)
        }


# Example usage and testing
async def example_usage():
    """Demonstrate how to use CrossArbitrageTA in a strategy."""
    
    # Initialize TA module with domain-aware configuration
    ta = CrossArbitrageTA(
        symbol=Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
        lookback_hours=24,
        refresh_minutes=15,
        entry_percentile=10,
        exit_threshold=0.05
    )
    
    # Load historical data (domain-aware initialization)
    await ta.initialize()
    
    # Example: In your strategy's step() method
    # Get current order books from domain-separated exchanges
    # (These would come from your separated domain exchange interfaces)
    
    # Mock data for example (in production, get from domain interfaces)
    from decimal import Decimal
    
    source_book = BookTicker(
        symbol=ta.symbol,
        bid_price=50000.0, ask_price=50001.0,
        bid_quantity=10.0, ask_quantity=10.0,
        timestamp=datetime.now(timezone.utc)
    )
    
    dest_book = BookTicker(
        symbol=ta.symbol,
        bid_price=49999.0, ask_price=50000.0,
        bid_quantity=10.0, ask_quantity=10.0,
        timestamp=datetime.now(timezone.utc)
    )
    
    hedge_book = BookTicker(
        symbol=ta.symbol,
        bid_price=50002.0, ask_price=50003.0,
        bid_quantity=10.0, ask_quantity=10.0,
        timestamp=datetime.now(timezone.utc)
    )
    
    # Generate signal (HFT-optimized)
    signal, spread_data = ta.generate_signal(
        source_book=source_book,
        dest_book=dest_book,
        hedge_book=hedge_book,
        position_open=False
    )
    
    if signal == 'enter':
        print(f"📈 Enter signal! Spread: {spread_data['spread_after_fees']:.3f}%")
    elif signal == 'exit':
        print(f"📉 Exit signal! Spread: {spread_data['spread_after_fees']:.3f}%")
    else:
        print(f"⏸️ No action. Current spread: {spread_data['spread_after_fees']:.3f}%")
    
    # Get performance metrics for HFT compliance
    metrics = ta.get_performance_metrics()
    print(f"📊 Performance: {metrics['calculation_count']} calculations, "
          f"{metrics['data_points']} data points")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())