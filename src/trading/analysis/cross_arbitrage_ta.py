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
from abc import ABC, abstractmethod
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Literal, Tuple, List
from dataclasses import dataclass

from exchanges.structs import Symbol, BookTicker, AssetName, ExchangeEnum
from trading.analysis.data_loader import get_cached_book_ticker_data
from infrastructure.logging import HFTLoggerInterface, get_logger
from msgspec import Struct


def calculate_realtime_spread(
        source_book: BookTicker,  # MEXC spot
        dest_book: BookTicker,  # Gate.io spot
        hedge_book: BookTicker,  # Gate.io futures
        total_fees: float
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
    spread_after_fees = total_spread - total_fees

    return {
        'source_hedge_arb': source_hedge_arb,
        'dest_hedge_arb': dest_hedge_arb,
        'total_spread': total_spread,
        'spread_after_fees': spread_after_fees,
    }

class CrossArbitrageSignalConfig(Struct):
    """Configuration for CrossArbitrageTA."""
    lookback_hours: int = 24
    refresh_minutes: Optional[int] = None  # Auto-refresh interval in minutes (None = disabled)
    entry_percentile: int = 10  # Top 10% of spreads for dynamic entry threshold
    exit_percentile: int = 85  # 85th percentile for dynamic exit threshold
    total_fees: float = 0.2  # Total round-trip fees percentage

type CrossArbitrageSignalType = Literal['enter', 'exit']

class CrossArbitrageSignal(Struct):
    """Real-time arbitrage signals and spread data."""
    signals: List[CrossArbitrageSignalType] = []
    current_spread: float = 0
    entry_threshold: float = 0
    exit_threshold: float = 0
    thresholds_age: float = 0 # Seconds since last threshold update
    timestamp: Optional[datetime] = None


@dataclass
class ArbitrageThresholds:
    """Arbitrage entry/exit thresholds calculated from historical data."""
    entry_spread: float  # Minimum profitable spread to enter (dynamic percentile)
    exit_spread: float  # Exit when spread falls below this (dynamic percentile)
    mean_spread: float  # Average historical spread
    std_spread: float  # Standard deviation for risk assessment
    last_update: datetime
    data_points: int
    entry_percentile_used: float  # Actual percentile used for entry
    exit_percentile_used: float  # Actual percentile used for exit


class CrossArbitrageSignalGeneratorInterface(ABC):
    """Interface for CrossArbitrageTA signal generation."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the TA module, load historical data."""
        pass

    @abstractmethod
    async def generate_signal(
            self,
            source_book: BookTicker,
            dest_book: BookTicker,
            hedge_book: BookTicker
    ) -> CrossArbitrageSignal:
        """Generate trading signal based on current market conditions."""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Shutdown the TA module and cleanup resources."""
        pass

class CrossArbitrageFixedSignalGenerator(CrossArbitrageSignalGeneratorInterface):

    def __init__(self, entry_threshold: float, exit_threshold: float,
                 total_fees: float,
                 logger: Optional[HFTLoggerInterface] = None):
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.total_fees = total_fees
        self.logger = logger or get_logger('cross_arbitrage_fixed_ta')

    async def initialize(self) -> None:
        pass

    def generate_signal(
            self,
            source_book: BookTicker,
            dest_book: BookTicker,
            hedge_book: BookTicker
    ) -> CrossArbitrageSignal:
        """
        Generate trading signal based on current market conditions.

        Domain-aware signal generation using public domain market data.
        HFT-optimized decision logic.

        Args:
            source_book: MEXC spot order book
            dest_book: Gate.io spot order book
            hedge_book: Gate.io futures order book

        Returns:
            Tuple of (signal, spread_data)
        """
        # Note: Historical data is automatically refreshed by background task if enabled
        # Manual refresh can still be triggered by calling refresh_historical_data() directly

        # Calculate current spread (HFT-optimized)
        current = calculate_realtime_spread(source_book, dest_book, hedge_book, self.total_fees)
        current_spread = current['spread_after_fees']

        # Default signal
        signals: List[CrossArbitrageSignalType] = []

        # HFT-optimized signal generation logic
        # Exit conditions (prioritized for speed)

        # TODO: TEST HARDCODED
        signals.append('exit')
        return CrossArbitrageSignal(
            signals=signals,
            current_spread=current_spread,
            entry_threshold=self.entry_threshold,
            exit_threshold=self.exit_threshold,
            thresholds_age=0,
            timestamp=datetime.now(timezone.utc)
        )

        if current_spread < self.exit_threshold:  # Max 2 hours
            signals.append('exit')
            self.logger.debug("📉 Exit signal generated",
                              current_spread=f"{current_spread:.4f}%",
                              exit_threshold=f"{self.exit_threshold:.4f}% (dynamic)")
        else:
            # Entry conditions
            if (current_spread > self.entry_threshold or
                    current_spread > 0.1):  # Minimum 0.1% profit after fees
                signals.append('enter')
                self.logger.debug("📈 Enter signal generated",
                                  current_spread=f"{current_spread:.4f}%",
                                  entry_threshold=f"{self.entry_threshold:.4f}% (dynamic)")

        return CrossArbitrageSignal(
            signals=signals,
            current_spread=current_spread,
            entry_threshold=self.entry_threshold,
            exit_threshold=self.exit_threshold,
            thresholds_age=0,
            timestamp=datetime.now(timezone.utc)
        )

    async def cleanup(self) -> None:
        pass


class CrossArbitrageDynamicSignalGenerator(CrossArbitrageSignalGeneratorInterface):
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
            config: CrossArbitrageSignalConfig,
            logger: Optional[HFTLoggerInterface] = None
    ):
        """Initialize with configuration parameters."""
        self.symbol = symbol
        self.lookback_hours = config.lookback_hours
        self.refresh_minutes = config.refresh_minutes
        self.entry_percentile = config.entry_percentile
        self.exit_percentile = config.exit_percentile
        self.total_fees = config.total_fees

        # Domain-aware logging
        self.logger = logger or get_logger(f'cross_arbitrage_ta.{symbol}')

        # Data storage (HFT-optimized)
        self.historical_df: Optional[pd.DataFrame] = None
        self.thresholds: Optional[ArbitrageThresholds] = None
        self.last_refresh: Optional[datetime] = None
        
        # Auto-refresh task management
        self._refresh_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._is_running = False

    async def initialize(self) -> None:
        """Load initial historical data and calculate thresholds."""
        if self._is_running:
            self.logger.warning("CrossArbitrageTA already initialized")
            return
            
        self.logger.info("🔄 Initializing CrossArbitrageTA",
                         symbol=str(self.symbol),
                         lookback_hours=self.lookback_hours,
                         auto_refresh=self.refresh_minutes is not None)

        # Load initial data
        await self.refresh_historical_data()
        
        # Start auto-refresh task if enabled
        if self.refresh_minutes is not None:
            self._is_running = True
            self._refresh_task = asyncio.create_task(self._auto_refresh_loop())
            self.logger.info("🔄 Auto-refresh task started",
                           refresh_interval_minutes=self.refresh_minutes)

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
            exchange_enums = [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]
            tasks = [
                self._load_exchange_data(e, start_time, end_time) for e in exchange_enums
            ]

            dfs = await asyncio.gather(*tasks, return_exceptions=True)

            # Filter successful results and handle exceptions
            valid_dfs = []
            for i, result in enumerate(dfs):
                if isinstance(result, Exception):
                    self.logger.warning(f"Failed to load {exchange_enums[i]} data: {result}")
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

    async def _auto_refresh_loop(self) -> None:
        """
        Background task that automatically refreshes historical data every N minutes.
        
        Runs until shutdown is requested.
        """
        if self.refresh_minutes is None:
            return
            
        self.logger.debug("🔄 Auto-refresh loop started")
        
        try:
            while not self._shutdown_event.is_set():
                # Wait for the refresh interval or shutdown
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self.refresh_minutes * 60  # Convert to seconds
                    )
                    # If we reach here, shutdown was requested
                    break
                except asyncio.TimeoutError:
                    # Timeout reached, time to refresh
                    pass
                
                if not self._shutdown_event.is_set():
                    self.logger.debug("🔄 Auto-refresh triggered")
                    try:
                        await self.refresh_historical_data()
                        self.logger.debug("✅ Auto-refresh completed successfully")
                    except Exception as e:
                        self.logger.error(f"❌ Auto-refresh failed: {e}")
                        
        except asyncio.CancelledError:
            self.logger.debug("🔄 Auto-refresh loop cancelled")
            raise
        except Exception as e:
            self.logger.error(f"❌ Auto-refresh loop error: {e}")
        finally:
            self.logger.debug("🔄 Auto-refresh loop stopped")

    async def cleanup(self) -> None:
        """
        Shutdown the TA module and cleanup resources.
        
        Stops the auto-refresh task and cleans up any background tasks.
        """
        if not self._is_running:
            self.logger.debug("CrossArbitrageTA already shutdown")
            return
            
        self.logger.info("🛑 Shutting down CrossArbitrageTA")
        
        # Signal shutdown
        self._shutdown_event.set()
        self._is_running = False
        
        # Cancel and cleanup auto-refresh task
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self.logger.error(f"❌ Error during refresh task cleanup: {e}")
        
        self._refresh_task = None
        self.logger.info("✅ CrossArbitrageTA shutdown complete")

    async def _load_exchange_data(
            self,
            exchange: ExchangeEnum,
            start_time: datetime,
            end_time: datetime
    ) -> pd.DataFrame:
        """
        Load and format data for a single exchange.
        
        Domain-aware loading respecting public domain boundaries.
        """
        prefix = exchange.value.lower()

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
            # df = df.set_index('timestamp')
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
                (df['gateio_futures_bid_price'] - df['mexc_spot_ask_price']) /
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
        Calculate dynamic entry/exit thresholds from historical spreads.
        
        HFT-optimized statistical calculations using percentile-based thresholds.
        """
        if self.historical_df is None or 'spread_after_fees' not in self.historical_df:
            return

        spreads = self.historical_df['spread_after_fees'].dropna()

        if len(spreads) < 100:  # Minimum data requirement
            self.logger.warning(f"Insufficient data for thresholds: {len(spreads)} points")
            return

        # Dynamic entry threshold calculation (percentile-based)
        entry_spread = np.percentile(spreads, 100 - self.entry_percentile)

        # Dynamic exit threshold calculation (percentile-based)
        exit_spread = np.percentile(spreads, self.exit_percentile)

        # HFT-optimized threshold creation
        self.thresholds = ArbitrageThresholds(
            entry_spread=entry_spread,
            exit_spread=exit_spread,
            mean_spread=spreads.mean(),
            std_spread=spreads.std(),
            last_update=datetime.now(timezone.utc),
            data_points=len(spreads),
            entry_percentile_used=100 - self.entry_percentile,
            exit_percentile_used=self.exit_percentile
        )

        self.logger.debug("📊 Dynamic thresholds updated",
                          entry_spread=f"{self.thresholds.entry_spread:.4f}%",
                          exit_spread=f"{self.thresholds.exit_spread:.4f}%",
                          entry_percentile=f"{self.thresholds.entry_percentile_used:.1f}%",
                          exit_percentile=f"{self.thresholds.exit_percentile_used:.1f}%",
                          data_points=self.thresholds.data_points)

    def should_refresh(self) -> bool:
        """
        Check if historical data needs refreshing.
        
        Note: With auto-refresh enabled, this method is mainly for manual refresh checks.
        """
        if self.last_refresh is None:
            return True
        
        # If auto-refresh is disabled, use manual refresh check
        if self.refresh_minutes is None:
            return False
            
        elapsed = (datetime.now(timezone.utc) - self.last_refresh).total_seconds() / 60
        return elapsed >= self.refresh_minutes

    # def calculate_realtime_spread(
    #         self,
    #         source_book: BookTicker,  # MEXC spot
    #         dest_book: BookTicker,  # Gate.io spot
    #         hedge_book: BookTicker  # Gate.io futures
    # ) -> Dict[str, float]:
    #     """
    #     Calculate current arbitrage spread from live order book data.
    #
    #     Domain-aware calculation using public domain book ticker data.
    #     HFT-optimized for sub-millisecond execution.
    #
    #     Returns:
    #         Dict with current spread components and total
    #     """
    #     # HFT-optimized calculation (single pass)
    #     # Source→Hedge: Buy MEXC ask, sell futures bid
    #     source_hedge_arb = (
    #             (hedge_book.bid_price - source_book.ask_price) /
    #             hedge_book.bid_price * 100
    #     )
    #
    #     # Dest→Hedge: Buy Gate.io spot bid, sell futures ask
    #     dest_hedge_arb = (
    #             (dest_book.bid_price - hedge_book.ask_price) /
    #             dest_book.bid_price * 100
    #     )
    #
    #     total_spread = source_hedge_arb + dest_hedge_arb
    #     spread_after_fees = total_spread - self.total_fees
    #
    #
    #     return {
    #         'source_hedge_arb': source_hedge_arb,
    #         'dest_hedge_arb': dest_hedge_arb,
    #         'total_spread': total_spread,
    #         'spread_after_fees': spread_after_fees,
    #     }

    def generate_signal(
            self,
            source_book: BookTicker,
            dest_book: BookTicker,
            hedge_book: BookTicker
    ) -> CrossArbitrageSignal:
        """
        Generate trading signal based on current market conditions.
        
        Domain-aware signal generation using public domain market data.
        HFT-optimized decision logic.
        
        Args:
            source_book: MEXC spot order book
            dest_book: Gate.io spot order book  
            hedge_book: Gate.io futures order book

        Returns:
            Tuple of (signal, spread_data)
        """
        # Note: Historical data is automatically refreshed by background task if enabled
        # Manual refresh can still be triggered by calling refresh_historical_data() directly

        # Calculate current spread (HFT-optimized)
        current = calculate_realtime_spread(source_book, dest_book, hedge_book, self.total_fees)
        current_spread = current['spread_after_fees']

        # Default signal
        signals: List[CrossArbitrageSignalType] = []

        if self.thresholds is None:
            self.logger.warning("⚠️ No thresholds available for signal generation")
            return CrossArbitrageSignal(
                signals=signals,
                current_spread=current_spread,
                entry_threshold=0.0,
                exit_threshold=0.0,
                thresholds_age=float('inf'),
            )

        # HFT-optimized signal generation logic
            # Exit conditions (prioritized for speed)
        if current_spread < self.thresholds.exit_spread:  # Max 2 hours
            signals.append('exit')
            self.logger.debug("📉 Exit signal generated",
                              current_spread=f"{current_spread:.4f}%",
                              exit_threshold=f"{self.thresholds.exit_spread:.4f}% (dynamic)")
        else:
            # Entry conditions
            if (current_spread > self.thresholds.entry_spread or
                    current_spread > 0.1):  # Minimum 0.1% profit after fees
                signals.append('enter')
                self.logger.debug("📈 Enter signal generated",
                                  current_spread=f"{current_spread:.4f}%",
                                  entry_threshold=f"{self.thresholds.entry_spread:.4f}% (dynamic)")

        return CrossArbitrageSignal(
            signals=signals,
            current_spread=current_spread,
            entry_threshold=self.thresholds.entry_spread,
            exit_threshold=self.thresholds.exit_spread,
            thresholds_age=(datetime.now(timezone.utc) - self.thresholds.last_update).total_seconds(),
            timestamp=datetime.now(timezone.utc)
        )

    def get_performance_metrics(self) -> Dict[str, any]:
        """Get performance metrics for HFT compliance monitoring."""
        return {
            'last_refresh': self.last_refresh.isoformat() if self.last_refresh else None,
            'thresholds_available': self.thresholds is not None,
            'data_points': self.thresholds.data_points if self.thresholds else 0,
            'refresh_interval_minutes': self.refresh_minutes,
            'symbol': str(self.symbol)
        }


# Example usage and testing
async def example_usage():
    """Demonstrate how to use CrossArbitrageTA in a strategy."""

    # Initialize TA module with domain-aware configuration and auto-refresh
    ta = CrossArbitrageDynamicSignalGenerator(
        symbol=Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
        config=CrossArbitrageSignalConfig(
            lookback_hours=24,
            refresh_minutes=15,  # Auto-refresh every 15 minutes (set to None to disable)
            entry_percentile=10,  # Top 10% of spreads for dynamic entry
            exit_percentile=85  # 85th percentile for dynamic exit
        )
    )

    # Load historical data (domain-aware initialization)
    await ta.initialize()

    # Example: In your strategy's step() method
    # Get current order books from domain-separated exchanges
    # (These would come from your separated domain exchange interfaces)

    # Mock data for example (in production, get from domain interfaces)
    from decimal import Decimal
    ts = int(datetime.now(timezone.utc).timestamp())
    source_book = BookTicker(
        symbol=ta.symbol,
        bid_price=50000.0, ask_price=50001.0,
        bid_quantity=10.0, ask_quantity=10.0,
        timestamp=ts
    )

    dest_book = BookTicker(
        symbol=ta.symbol,
        bid_price=49999.0, ask_price=50000.0,
        bid_quantity=10.0, ask_quantity=10.0,
        timestamp=ts
    )

    hedge_book = BookTicker(
        symbol=ta.symbol,
        bid_price=50002.0, ask_price=50003.0,
        bid_quantity=10.0, ask_quantity=10.0,
        timestamp=ts
    )

    # Generate signal (HFT-optimized)
    signal = ta.generate_signal(
        source_book=source_book,
        dest_book=dest_book,
        hedge_book=hedge_book
    )

    if not signal.signals:
        print(f"⏸️ No action. Current spread: {signal.current_spread:.3f}%")
    else:
        if 'enter' in signal.signals:
            print(f"📈 Enter signal! Spread: {signal.current_spread:.3f}%")
        if 'exit' in signal.signals:
            print(f"📉 Exit signal! Spread: {signal.current_spread:.3f}%")


    # Get performance metrics for HFT compliance
    metrics = ta.get_performance_metrics()
    print(f"📊 Performance: {metrics['data_points']} data points, "
          f"Auto-refresh: {'enabled' if ta.refresh_minutes else 'disabled'}")
    
    # Simulate running for a while...
    print("⏳ Simulating runtime (auto-refresh running in background)...")
    await asyncio.sleep(2)  # In production, this would be your main strategy loop
    
    # Cleanup when done
    print("🛑 Shutting down...")
    await ta.shutdown()


if __name__ == "__main__":
    import asyncio

    asyncio.run(example_usage())
