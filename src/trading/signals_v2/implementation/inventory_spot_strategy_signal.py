"""
Inventory Spot Strategy Signal V2

High-performance cryptocurrency arbitrage strategy for cross-exchange trading
between MEXC and Gate.io spot markets with realistic cost modeling and risk management.

This strategy implements sophisticated inventory management with transfer delays,
comprehensive cost accounting, and enhanced performance metrics for accurate
backtesting and live trading scenarios.
"""

from typing import Dict, Optional, List, Tuple, Literal, Union
import pandas as pd
from datetime import datetime, timedelta, UTC

from exchanges.structs import BookTicker, Fees
from infrastructure.logging import HFTLoggerInterface, get_logger
from trading.signals.types import Signal
from exchanges.structs.enums import ExchangeEnum, Side
from numbers import Number
from trading.signals_v2.entities import PerformanceMetrics, TradeEntry, PositionEntry, BacktestingParams
from trading.signals_v2.strategy_signal import StrategySignal
from trading.data_sources.column_utils import get_column_key
import numpy as np
from enum import IntEnum
from msgspec import Struct
class InventorySignalEnum(IntEnum):
    MEXC_TO_GATEIO = 1
    GATEIO_TO_MEXC = 2
    HOLD = 0

class InventorySignalWithLimitEnum(IntEnum):
    HOLD = 0
    MARKET_MEXC_SELL_MARKET_GATEIO_BUY = 1
    MARKET_GATEIO_SELL_MARKET_MEXC_BUY = 2
    LIMIT_MEXC_SELL_MARKET_GATEIO_BUY = 3
    MARKET_GATEIO_SELL_LIMIT_MEXC_BUY = 4
    MARKET_MEXC_SELL_LIMIT_GATEIO_BUY = 5
    LIMIT_GATEIO_SELL_MARKET_MEXC_BUY = 6

class InventorySignalType(Struct):
    side: Side
    is_market: bool

type ArbitrageSignalType = Literal['both_market', 'limit_mexc', 'limit_gateio']
type InventorySpreadDirectionType = Literal['mexc_to_gateio', 'gateio_to_mexc']

class InventoryExecutionOpportunity(Struct):
    exchange: ExchangeEnum
    side: Side
    is_market: bool
    spread_bps: float
    pair: InventorySpreadDirectionType


class InventorySpreadStats(Struct):
    min_spread_bps: float
    max_spread_bps: float
    avg_spread_bps: float
    spread_stddev_bps: float
    spread_history: np.ndarray
    
    @classmethod
    def create_empty(cls, max_history_length: int = 100) -> 'InventorySpreadStats':
        """Create an empty stats object with pre-allocated numpy array."""
        return cls(
            min_spread_bps=float('inf'),
            max_spread_bps=float('-inf'),
            avg_spread_bps=0.0,
            spread_stddev_bps=0.0,
            spread_history=np.full(max_history_length, np.nan, dtype=np.float64)
        )
    
    def update_with_spread(self, spread_bps: float) -> 'InventorySpreadStats':
        """Update stats with new spread value using circular buffer."""
        # Copy history array for immutable update
        history = self.spread_history.copy()
        
        # Find first NaN slot or use circular buffer
        nan_indices = np.where(np.isnan(history))[0]
        if len(nan_indices) > 0:
            # Fill first available NaN slot
            history[nan_indices[0]] = spread_bps
        else:
            # Array is full, shift left and add new value (circular buffer)
            history[:-1] = history[1:]
            history[-1] = spread_bps
        
        # Calculate statistics using numpy for performance
        valid_spreads = history[~np.isnan(history)]
        if len(valid_spreads) > 0:
            min_spread = float(np.min(valid_spreads))
            max_spread = float(np.max(valid_spreads))
            avg_spread = float(np.mean(valid_spreads))
            std_spread = float(np.std(valid_spreads)) if len(valid_spreads) > 1 else 0.0
        else:
            min_spread = spread_bps
            max_spread = spread_bps
            avg_spread = spread_bps
            std_spread = 0.0
            
        return InventorySpreadStats(
            min_spread_bps=min_spread,
            max_spread_bps=max_spread,
            avg_spread_bps=avg_spread,
            spread_stddev_bps=std_spread,
            spread_history=history
        )

type InventorySignalPairType = Dict[ExchangeEnum,InventorySignalType]  # (side, is_market_order)

class InventorySpotStrategySignal(StrategySignal):
    """
    Advanced Inventory Spot Arbitrage Strategy V2
    
    This strategy implements sophisticated cross-exchange arbitrage with realistic
    cost modeling, transfer delays, and enhanced risk management.
    
    Strategy Logic:
    1. Initial Setup: Buy initial inventory on the exchange with lower prices
    2. Continuous Monitoring: Track spreads between MEXC and Gate.io spot markets  
    3. Arbitrage Execution: Execute trades when spread exceeds profitable thresholds
    4. Transfer Management: Handle asset transfers between exchanges with realistic delays
    5. Cost Accounting: Include trading fees, slippage, and transfer costs
    
    Key Features:
    - Realistic cost modeling with fees, slippage, and transfer costs
    - Enhanced performance metrics with proper risk adjustment
    - Transfer delay simulation with configurable timing
    - Position sizing based on available balances and market conditions
    - Comprehensive profit/loss calculation using net cash flow analysis
    """
    
    name: str = "inventory_spot_signal"
    
    def __init__(self,
                 params: Dict[str, float],
                 update_interval_seconds: int = 60,
                 max_history_length: int = 100,
                 backtesting_params: BacktestingParams = None,
                 fees: Dict[ExchangeEnum, Fees] = {},
                 logger: HFTLoggerInterface=None
                 ):
        """
        Initialize advanced inventory spot arbitrage strategy.
        
        Args:
            update_interval_seconds: Price history update frequency
            max_history_length: Maximum price history to maintain
            backtesting_params: Enhanced backtesting configuration with realistic costs
        """
        self.logger = logger or get_logger(__name__)
        self.params = params
        self.fees = fees
        self._backtesting_params = backtesting_params or BacktestingParams()

        self.col_mexc_bid = get_column_key(ExchangeEnum.MEXC, 'bid_price')
        self.col_mexc_ask = get_column_key(ExchangeEnum.MEXC, 'ask_price')
        self.col_gateio_bid = get_column_key(ExchangeEnum.GATEIO, 'bid_price')
        self.col_gateio_ask = get_column_key(ExchangeEnum.GATEIO, 'ask_price')

        self.col_mexc_balance = get_column_key(ExchangeEnum.MEXC, 'balance')
        self.col_gateio_balance = get_column_key(ExchangeEnum.GATEIO, 'balance')
        
        # Initialize stats with proper typing and numpy arrays
        self.stats: Dict[ArbitrageSignalType, Dict[InventorySpreadDirectionType, InventorySpreadStats]] = {
            'both_market': {
                'mexc_to_gateio': InventorySpreadStats.create_empty(max_history_length),
                'gateio_to_mexc': InventorySpreadStats.create_empty(max_history_length)
            },
            'limit_mexc': {
                'mexc_to_gateio': InventorySpreadStats.create_empty(max_history_length),
                'gateio_to_mexc': InventorySpreadStats.create_empty(max_history_length)
            },
            'limit_gateio': {
                'mexc_to_gateio': InventorySpreadStats.create_empty(max_history_length),
                'gateio_to_mexc': InventorySpreadStats.create_empty(max_history_length)
            }
        }
        
        # Initialize price history with numpy arrays for better performance
        self.price_history = {
            self.col_mexc_bid: np.full(max_history_length, np.nan, dtype=np.float64),
            self.col_mexc_ask: np.full(max_history_length, np.nan, dtype=np.float64),
            self.col_gateio_bid: np.full(max_history_length, np.nan, dtype=np.float64),
            self.col_gateio_ask: np.full(max_history_length, np.nan, dtype=np.float64)
        }
        self._history_index = 0

        self.position: Optional[PositionEntry] = PositionEntry(entry_time=datetime.now(UTC))
        self.historical_positions: List[PositionEntry] = []

        self._last_update_time: datetime = datetime.now(UTC)
        self._update_interval: timedelta = timedelta(seconds=update_interval_seconds)

        self._max_history_length = max_history_length

        self._backtesting_params = backtesting_params
        self.analysis_results = {}
        self._get_live_signal_calls = 0

    def _update_price_history(self, book_tickers: Dict[ExchangeEnum, BookTicker]) -> None:
        """Update price history for volatility calculation using numpy arrays."""

        now = datetime.now(UTC)
        if self._last_update_time + self._update_interval > now:
            return

        self._last_update_time = now

        mexc_book = book_tickers.get(ExchangeEnum.MEXC)
        gateio_book = book_tickers.get(ExchangeEnum.GATEIO)
        
        if mexc_book and gateio_book:
            # Update price history using circular buffer with numpy
            values = [
                (self.col_mexc_bid, mexc_book.bid_price),
                (self.col_mexc_ask, mexc_book.ask_price),
                (self.col_gateio_bid, gateio_book.bid_price),
                (self.col_gateio_ask, gateio_book.ask_price)
            ]
            
            for key, value in values:
                if self._history_index < self._max_history_length:
                    self.price_history[key][self._history_index] = value
                else:
                    # Shift array and add new value (circular buffer)
                    self.price_history[key][:-1] = self.price_history[key][1:]
                    self.price_history[key][-1] = value
            
            # Update history index
            if self._history_index < self._max_history_length - 1:
                self._history_index += 1


    def _initialize_backtest(self, df: pd.DataFrame):
        """Initialize backtest state."""

        # init balances columns
        df[self.col_mexc_balance] = 0
        df[self.col_gateio_balance] = 0

        row = df.iloc[0]

        if row[self.col_mexc_ask] < row[self.col_gateio_ask]:
            qty = self._backtesting_params.initial_balance_usd / row[self.col_mexc_ask]
            trade = TradeEntry(
                exchange=ExchangeEnum.MEXC, 
                side=Side.BUY, 
                price=row[self.col_mexc_ask], 
                qty=qty,
                fee_pct=self.fees.get(ExchangeEnum.MEXC).taker_fee,
                slippage_pct=self._backtesting_params.slippage_pct
            )
        else:
            qty = self._backtesting_params.initial_balance_usd / row[self.col_gateio_ask]
            trade = TradeEntry(
                exchange=ExchangeEnum.GATEIO, 
                side=Side.BUY, 
                price=row[self.col_gateio_ask], 
                qty=qty,
                fee_pct=self.fees.get(ExchangeEnum.GATEIO_FUTURES).taker_fee,
                slippage_pct=self._backtesting_params.slippage_pct
            )

        self.position.add_trade(trade)
        df_backtest = df[1:]
        self._update_df_balance(df_backtest, df_backtest.index[0])
        return df_backtest


    def backtest(self, df: pd.DataFrame) -> PerformanceMetrics:
        df = self._prepare_backtesting_signals(df)
        self.analyze_signals(df)
        df = self._initialize_backtest(df)

        self._emulate_trading(df)

        return self.position.get_performance_metrics(self._backtesting_params.initial_balance_usd)

    def _update_df_balance(self, df: pd.DataFrame, idx: pd.Timestamp):
        balances = [self.position.balances.get(ExchangeEnum.MEXC, 0.0),
                    self.position.balances.get(ExchangeEnum.GATEIO, 0.0)]
        df.loc[idx:, [self.col_mexc_balance, self.col_gateio_balance]] = balances
        # df.loc[idx:, self.col_gateio_balance] = self.position.balances[ExchangeEnum.GATEIO]

    def _update_transfer_in_progress(self, df:pd.DataFrame, idx: pd.Timestamp):
        transfer_to = idx + pd.Timedelta(minutes=self._backtesting_params.transfer_delay_minutes)

        # Method 1: Using searchsorted (fastest for sorted DatetimeIndex)
        transfer_idx = df.index.searchsorted(transfer_to, side='left')
        if transfer_idx < len(df):
            actual_idx = df.index[transfer_idx]
            df.loc[idx:actual_idx, 'transfer_in_progress'] = True
        else:
            # transfer_to is beyond the end of the dataframe
            df.loc[idx:, 'transfer_in_progress'] = True

    def _emulate_trading(self, df: pd.DataFrame) -> None:
        """
        Internal vectorized position tracking for backtesting.

        Processes signal changes and manages positions/trades internally.
        This replaces the external PositionTracker.track_positions_vectorized() method.

        Args:
            df: DataFrame with signal column added
        """
        # Reset state for fresh backtest

        # Find signal changes
        profit_cols = ['mexc_to_gateio_signal', 'gateio_to_mexc_signal']
        changes_mask = df[profit_cols].ne(df[profit_cols].shift()).any(axis=1)
        signal_points = df[changes_mask].copy()

        for idx, row in signal_points.iterrows():
            if self.position and df.loc[idx,'transfer_in_progress']:
                continue  # Skip processing during transfer

            if row['mexc_to_gateio_signal']:
                qty = df.loc[idx, self.col_mexc_balance]
                if qty == 0:
                    continue

                self.position.add_arbitrage_trade(idx, [
                    TradeEntry(
                        exchange=ExchangeEnum.MEXC, 
                        side=Side.SELL,  # ✅ SELL on MEXC (higher price)
                        price=row[self.col_mexc_bid], 
                        qty=qty,
                        fee_pct=self.fees.get(ExchangeEnum.MEXC).taker_fee,
                        slippage_pct=self._backtesting_params.slippage_pct
                    ),
                    TradeEntry(
                        exchange=ExchangeEnum.GATEIO, 
                        side=Side.BUY,  # ✅ BUY on Gate.io (lower price)
                        price=row[self.col_gateio_ask], 
                        qty=qty,
                        fee_pct=self.fees.get(ExchangeEnum.GATEIO).taker_fee,
                        slippage_pct=self._backtesting_params.slippage_pct
                    )
                ])

                self.position.start_transfer(
                    self._backtesting_params.transfer_delay_minutes,
                    idx,
                    ExchangeEnum.GATEIO,
                    ExchangeEnum.MEXC,
                    self._backtesting_params.transfer_fee_usd
                )
                self._update_transfer_in_progress(df,idx)

                self._update_df_balance(df, idx)
            elif row['gateio_to_mexc_signal']:
                qty = df.loc[idx, self.col_gateio_balance]
                if qty == 0:
                    continue

                self.position.add_arbitrage_trade(idx, [
                    TradeEntry(
                        exchange=ExchangeEnum.GATEIO, 
                        side=Side.SELL,  # ✅ SELL on Gate.io (higher price)
                        price=row[self.col_gateio_bid], 
                        qty=qty,
                        fee_pct=self.fees.get(ExchangeEnum.MEXC).taker_fee,
                        slippage_pct=self._backtesting_params.slippage_pct
                    ),
                    TradeEntry(
                        exchange=ExchangeEnum.MEXC, 
                        side=Side.BUY,  # ✅ BUY on MEXC (lower price)
                        price=row[self.col_mexc_ask], 
                        qty=qty,
                        fee_pct=self.fees.get(ExchangeEnum.GATEIO).taker_fee,
                        slippage_pct=self._backtesting_params.slippage_pct
                    )
                ])

                self.position.start_transfer(
                    self._backtesting_params.transfer_delay_minutes,
                    idx,
                    ExchangeEnum.MEXC,
                    ExchangeEnum.GATEIO,
                    self._backtesting_params.transfer_fee_usd
                )
                self._update_transfer_in_progress(df,idx)

                self._update_df_balance(df, idx)

    def get_live_signal(self, mexc_buy: float, mexc_sell: float, gateio_buy: float, gateio_sell: float)-> Tuple[InventorySignalEnum, Dict[str, float]]:
        mexc_to_gateio_spread_bps = ((mexc_sell - gateio_buy) / gateio_buy * 10000)
        gateio_to_mexc_spread_bps = ((gateio_sell - mexc_buy) / mexc_buy * 10000)

        spreads = {'mexc_to_gateio': mexc_to_gateio_spread_bps, 'gateio_to_mexc': gateio_to_mexc_spread_bps}

        if mexc_to_gateio_spread_bps > self.params['mexc_spread_threshold_bps']:
            return InventorySignalEnum.MEXC_TO_GATEIO, spreads  # SELL on MEXC (higher), BUY on Gate.io (lower)
        elif gateio_to_mexc_spread_bps > self.params['gateio_spread_threshold_bps']:
            return InventorySignalEnum.GATEIO_TO_MEXC, spreads  # SELL on Gate.io (higher), BUY on MEXC (lower)

        return InventorySignalEnum.HOLD, spreads

    def _update_spread_stats(self, category: ArbitrageSignalType, new_stats: Dict[str, float]) -> None:
        """
        Update spread statistics using numpy arrays for optimal performance.
        
        Args:
            category: The arbitrage signal type ('both_market', 'limit_mexc', 'limit_gateio')
            new_stats: Dictionary with 'mexc_to_gateio' and 'gateio_to_mexc' spread values in BPS
        """
        if category not in self.stats:
            return
            
        for direction_key, spread_bps in new_stats.items():
            if direction_key in self.stats[category]:
                # Update the spread stats with new value using numpy operations
                current_stats = self.stats[category][direction_key]
                updated_stats = current_stats.update_with_spread(spread_bps=spread_bps)
                self.stats[category][direction_key] = updated_stats

    def get_spread_insights(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        Get comprehensive spread insights for analysis and optimization.
        
        Returns:
            Dictionary with spread statistics for each strategy and direction
        """
        insights = {}
        
        for strategy_type, directions in self.stats.items():
            insights[strategy_type] = {}
            for direction, stats in directions.items():
                # Only include strategies with valid data
                if stats.min_spread_bps != float('inf'):
                    # Calculate additional derived metrics
                    valid_history = stats.spread_history[~np.isnan(stats.spread_history)]
                    percentile_75 = float(np.percentile(valid_history, 75)) if len(valid_history) > 0 else 0.0
                    percentile_25 = float(np.percentile(valid_history, 25)) if len(valid_history) > 0 else 0.0
                    
                    insights[strategy_type][direction] = {
                        'min_spread_bps': stats.min_spread_bps,
                        'max_spread_bps': stats.max_spread_bps,
                        'avg_spread_bps': stats.avg_spread_bps,
                        'stddev_spread_bps': stats.spread_stddev_bps,
                        'percentile_25_bps': percentile_25,
                        'percentile_75_bps': percentile_75,
                        'sample_count': len(valid_history),
                        'coefficient_of_variation': stats.spread_stddev_bps / stats.avg_spread_bps if stats.avg_spread_bps != 0 else 0.0
                    }
        
        return insights

    # python
    def get_live_signal_book_ticker(self, book_tickers: Dict[ExchangeEnum, BookTicker], threshold: float) -> List[InventoryExecutionOpportunity]:
        # Update price history first
        self._update_price_history(book_tickers)
        
        mexc_bid = book_tickers[ExchangeEnum.MEXC].bid_price
        mexc_ask = book_tickers[ExchangeEnum.MEXC].ask_price
        gateio_bid = book_tickers[ExchangeEnum.GATEIO].bid_price
        gateio_ask = book_tickers[ExchangeEnum.GATEIO].ask_price

        results: List[InventoryExecutionOpportunity] = []
        # candidate signals for 3 scenarios
        market_signal, market_stats = self.get_live_signal(mexc_sell=mexc_bid, mexc_buy=mexc_ask,
                                             gateio_buy=gateio_ask, gateio_sell=gateio_bid)


        if market_stats['mexc_to_gateio'] > threshold:
            results.append(InventoryExecutionOpportunity(
                exchange=ExchangeEnum.MEXC,
                side=Side.SELL,
                is_market=True,
                spread_bps=market_stats['mexc_to_gateio'],
                pair='mexc_to_gateio',

            ))
            results.append(InventoryExecutionOpportunity(
                exchange=ExchangeEnum.GATEIO,
                side=Side.BUY,
                is_market=True,
                spread_bps=market_stats['mexc_to_gateio'],
                pair='mexc_to_gateio'
            ))
        elif market_stats['gateio_to_mexc'] > threshold:
            results.append(InventoryExecutionOpportunity(
                exchange=ExchangeEnum.GATEIO,
                side=Side.SELL,
                is_market=True,
                spread_bps=market_stats['gateio_to_mexc'],
                pair='gateio_to_mexc'
            ))
            results.append(InventoryExecutionOpportunity(
                exchange=ExchangeEnum.MEXC,
                side=Side.BUY,
                is_market=True,
                spread_bps=market_stats['gateio_to_mexc'],
                pair='gateio_to_mexc'
            ))

        limit_mexc_signal, limit_mexc_stats = self.get_live_signal(mexc_sell=mexc_ask, mexc_buy=mexc_bid,
                                                 gateio_buy=gateio_ask, gateio_sell=gateio_bid)
        if limit_mexc_stats['mexc_to_gateio'] > threshold:
            results.append(InventoryExecutionOpportunity(
                exchange=ExchangeEnum.MEXC,
                side=Side.SELL,
                is_market=False,
                spread_bps=limit_mexc_stats['mexc_to_gateio'],
                pair='mexc_to_gateio'
            ))
            results.append(InventoryExecutionOpportunity(
                exchange=ExchangeEnum.GATEIO,
                side=Side.BUY,
                is_market=True,
                spread_bps=limit_mexc_stats['mexc_to_gateio'],
                pair='mexc_to_gateio'
            ))
        elif limit_mexc_stats['gateio_to_mexc'] > threshold:
            results.append(InventoryExecutionOpportunity(
                exchange=ExchangeEnum.GATEIO,
                side=Side.SELL,
                is_market=True,
                spread_bps=limit_mexc_stats['gateio_to_mexc'],
                pair='gateio_to_mexc'
            ))
            results.append(InventoryExecutionOpportunity(
                exchange=ExchangeEnum.MEXC,
                side=Side.BUY,
                is_market=False,
                spread_bps=limit_mexc_stats['gateio_to_mexc'],
                pair='gateio_to_mexc'
            ))
        limit_gateio_signal, limit_gateio_stats = self.get_live_signal(mexc_sell=mexc_bid, mexc_buy=mexc_ask,
                                                   gateio_buy=gateio_bid, gateio_sell=gateio_ask)
        if limit_gateio_stats['mexc_to_gateio'] > threshold:
            results.append(InventoryExecutionOpportunity(
                exchange=ExchangeEnum.MEXC,
                side=Side.SELL,
                is_market=True,
                spread_bps=limit_gateio_stats['mexc_to_gateio'],
                pair='mexc_to_gateio'
            ))
            results.append(InventoryExecutionOpportunity(
                exchange=ExchangeEnum.GATEIO,
                side=Side.BUY,
                is_market=False,
                spread_bps=limit_gateio_stats['mexc_to_gateio'],
                pair='mexc_to_gateio'
            ))
        elif limit_gateio_stats['gateio_to_mexc'] > threshold:
            results.append(InventoryExecutionOpportunity(
                exchange=ExchangeEnum.GATEIO,
                side=Side.SELL,
                is_market=False,
                spread_bps=limit_gateio_stats['gateio_to_mexc'],
                pair='gateio_to_mexc'
            ))
            results.append(InventoryExecutionOpportunity(
                exchange=ExchangeEnum.MEXC,
                side=Side.BUY,
                is_market=True,
                spread_bps=limit_gateio_stats['gateio_to_mexc'],
                pair='gateio_to_mexc'
            ))

        # Update spread statistics using the new numpy-optimized method
        self._update_spread_stats('both_market', market_stats)
        self._update_spread_stats('limit_mexc', limit_mexc_stats)
        self._update_spread_stats('limit_gateio', limit_gateio_stats)

        if self._get_live_signal_calls % 3000 == 0:
            # Log spread statistics with enhanced info including mean and std dev
            info = f"\n{'Strategy':<14} | {'Direction':<16} | {'Min':<8} | {'Max':<8} | {'Mean':<8} | {'StdDev':<8}"
            info += f"\n{'-'*80}"
            
            for strategy_type, directions in self.stats.items():
                for direction, stats in directions.items():
                    # Only show stats if we have valid data (not infinity)
                    if stats.min_spread_bps != float('inf'):
                        info += f"\n{strategy_type:<14} | {direction:<16} | "
                        info += f"{stats.min_spread_bps:<8.1f} | {stats.max_spread_bps:<8.1f} | "
                        info += f"{stats.avg_spread_bps:<8.1f} | {stats.spread_stddev_bps:<8.1f}"

            self.logger.info(info)

        self._get_live_signal_calls += 1
        return results

        # mappings from InventorySignalEnum -> InventorySignalType for each scenario
        market_mapping = {
            InventorySignalEnum.MEXC_TO_GATEIO: {
                ExchangeEnum.MEXC: InventorySignalType(Side.SELL, True),
                ExchangeEnum.GATEIO: InventorySignalType(Side.BUY, True)
            },
            InventorySignalEnum.GATEIO_TO_MEXC: {
                ExchangeEnum.GATEIO: InventorySignalType(Side.SELL, True),
                ExchangeEnum.MEXC: InventorySignalType(Side.BUY, True)
            }
        }

        limit_mexc_mapping = {
            InventorySignalEnum.MEXC_TO_GATEIO: {
                ExchangeEnum.MEXC: InventorySignalType(Side.SELL, False),  # limit sell on MEXC
                ExchangeEnum.GATEIO: InventorySignalType(Side.BUY, True)  # market buy on Gate.io
            },
            InventorySignalEnum.GATEIO_TO_MEXC: {
                ExchangeEnum.GATEIO: InventorySignalType(Side.SELL, True),  # market sell on Gate.io
                ExchangeEnum.MEXC: InventorySignalType(Side.BUY, False)  # limit buy on MEXC
            }
        }

        limit_gateio_mapping = {
            InventorySignalEnum.MEXC_TO_GATEIO: {
                ExchangeEnum.MEXC: InventorySignalType(Side.SELL, True),  # market sell on MEXC
                ExchangeEnum.GATEIO: InventorySignalType(Side.BUY, False)  # limit buy on Gate.io
            },
            InventorySignalEnum.GATEIO_TO_MEXC: {
                ExchangeEnum.GATEIO: InventorySignalType(Side.SELL, False),  # limit sell on Gate.io
                ExchangeEnum.MEXC: InventorySignalType(Side.BUY, True)  # market buy on MEXC
            }
        }

        scenarios = [
            (market_signal, market_mapping),
            (limit_mexc_signal, limit_mexc_mapping),
            (limit_gateio_signal, limit_gateio_mapping)
        ]

        for sig, mapping in scenarios:
            if sig == InventorySignalEnum.HOLD:
                continue
            return mapping.get(sig, {})

        return {}

    # def get_live_signal_book_ticker(self, book_tickers: Dict[ExchangeEnum, BookTicker]) -> InventorySignalEnum:
    #     """
    #     Generate live trading signal using arbitrage analyzer logic.
    #
    #     Returns:
    #        Signal
    #     """
    #     mexc_bid = book_tickers[ExchangeEnum.MEXC].bid_price
    #     mexc_ask = book_tickers[ExchangeEnum.MEXC].ask_price
    #     gateio_bid = book_tickers[ExchangeEnum.GATEIO].bid_price
    #     gateio_ask = book_tickers[ExchangeEnum.GATEIO].ask_price
    #
    #     mexc_to_gateio_spread_bps = ((mexc_bid - gateio_ask)/ gateio_ask * 10000)
    #     gateio_to_mexc_spread_bps = ((gateio_bid - mexc_ask)/ mexc_ask * 10000)
    #
    #     if mexc_to_gateio_spread_bps > self.params['mexc_spread_threshold_bps']:
    #         return InventorySignalEnum.MEXC_TO_GATEIO  # SELL on MEXC (higher), BUY on Gate.io (lower)
    #     elif gateio_to_mexc_spread_bps > self.params['gateio_spread_threshold_bps']:
    #         return InventorySignalEnum.GATEIO_TO_MEXC # SELL on Gate.io (higher), BUY on MEXC (lower)
    #
    #     return InventorySignalEnum.HOLD
    
    def _prepare_backtesting_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply strategy signals to historical data using corrected arbitrage logic.
        
        Args:
            df: Historical market data DataFrame

        Returns:
            DataFrame with added signal columns
        """
        
        # mexc_to_gateio_signal: profitable when MEXC prices > Gate.io prices (sell MEXC, buy Gate.io)
        mexc_to_gateio_spread_bps = ((df[self.col_mexc_bid] - df[self.col_gateio_ask]) /
                                     df[self.col_gateio_ask] * 10000)
        
        # gateio_to_mexc_signal: profitable when Gate.io prices > MEXC prices (sell Gate.io, buy MEXC)  
        gateio_to_mexc_spread_bps = ((df[self.col_gateio_bid] - df[self.col_mexc_ask]) /
                                     df[self.col_mexc_ask] * 10000)

   

        df['mexc_to_gateio_signal'] = mexc_to_gateio_spread_bps > self.params['mexc_spread_threshold_bps']
        df['gateio_to_mexc_signal'] = gateio_to_mexc_spread_bps > self.params['gateio_spread_threshold_bps']

        df['mexc_spread_bps'] = mexc_to_gateio_spread_bps
        df['gateio_spread_bps'] = gateio_to_mexc_spread_bps
        
        df['has_opportunity'] = df['mexc_to_gateio_signal'] | df['gateio_to_mexc_signal']
        df['transfer_in_progress'] = False  # Placeholder for transfer logic

        return df


    def analyze_signals(self, df: pd.DataFrame):
        fees = {'mexc_spread_bps': self.params['mexc_spread_threshold_bps'],
                'gateio_spread_bps': self.params['gateio_spread_threshold_bps']}

        quantile_perc = [0.25, 0.5, 0.75, 0.9, 0.95, 0.97, 0.99]

        results = {}
        for v in fees.keys():
            item = {}
            exchange_threshold = fees[v]
            profitable_spreads = df[df[v]>exchange_threshold]
            rest_spreads = df[df[v] < exchange_threshold]
            positive_spread_count = len(profitable_spreads)
            negative_spread_count = len(df[v]) - positive_spread_count
            item[f'spreads'] = {'positive': positive_spread_count,
                                'negative': negative_spread_count,
                                'ratio': round(positive_spread_count/negative_spread_count,2)}
            profitable_quantiles =  profitable_spreads[v].quantile(quantile_perc)
            for quantile,value in profitable_quantiles.items():
                df_q = profitable_spreads[profitable_spreads[v]>=value][v]
                item[f'quantile_profitable_{quantile}'] = {'spread': value,
                                                'count': len(df_q),
                                                'sum': (df_q -exchange_threshold).sum()}

            rest_quantiles = rest_spreads[v].quantile(quantile_perc)
            for quantile, value in rest_quantiles.items():
                df_q = rest_spreads[rest_spreads[v] >= value][v]
                item[f'quantile_rest_{quantile}'] = {'spread': value,
                                                           'count': len(df_q),
                                                           'sum': (df_q - exchange_threshold).sum()}

            results[v] = item

        self.analysis_results = results
        return results