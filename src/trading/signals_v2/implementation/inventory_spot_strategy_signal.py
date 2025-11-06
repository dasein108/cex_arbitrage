"""
Inventory Spot Strategy Signal V2

"""

from typing import Dict, Optional, List
import pandas as pd
from datetime import datetime, timedelta, UTC

from exchanges.structs import BookTicker
from trading.signals.types import Signal
from exchanges.structs.enums import ExchangeEnum, Side

from trading.signals_v2.entities import PerformanceMetrics, TradeEntry, PositionEntry, BacktestingParams
from trading.signals_v2.strategy_signal import StrategySignal
from trading.data_sources.column_utils import get_column_key

class InventorySpotStrategySignal(StrategySignal):
    name: str = "inventory_spot_signal"
    """
    Inventory spot arbitrage strategy V2 - matches arbitrage_analyzer.py logic.
    
    Strategy Logic:
    - Preload: buy initial amount on exchange where price is lower, hedge with futures
    - Futures position stay open continuously
    - transfer assets between exchanges if balance on one exchange >= max_balance_usd and other == 0
    - then buy low/sell high between exchanges when spread exceeds threshold
    """
    
    def __init__(self, 
                 min_profit_bps: float = 10.0,  # 10 basis points minimum profit
                 update_interval_seconds: int = 60,
                 max_history_length: int = 100,
                 backtesting_params: BacktestingParams = BacktestingParams()
                 ):
        """
        Initialize inventory spot strategy V2.
        
        Args:
            min_profit_bps: Minimum profit in basis points (10 bps = 0.1%)
        """
        self.min_profit_bps = min_profit_bps

        self.col_mexc_bid = get_column_key(ExchangeEnum.MEXC, 'bid_price')
        self.col_mexc_ask = get_column_key(ExchangeEnum.MEXC, 'ask_price')
        self.col_gateio_bid = get_column_key(ExchangeEnum.GATEIO, 'bid_price')
        self.col_gateio_ask = get_column_key(ExchangeEnum.GATEIO, 'ask_price')

        self.col_mexc_balance = get_column_key(ExchangeEnum.MEXC, 'balance')
        self.col_gateio_balance = get_column_key(ExchangeEnum.GATEIO, 'balance')

        self.price_history = {
            self.col_mexc_bid: [],
            self.col_mexc_ask: [],
            self.col_gateio_bid: [],
            self.col_gateio_ask: []
        }

        self.position: Optional[PositionEntry] = PositionEntry(entry_time=datetime.now(UTC))
        self.historical_positions: List[PositionEntry] = []

        self._last_update_time: datetime = datetime.now(UTC)
        self._update_interval: timedelta = timedelta(seconds=update_interval_seconds)

        self._max_history_length = max_history_length

        self._backtesting_params = backtesting_params

    def _update_price_history(self, book_tickers: Dict[ExchangeEnum, BookTicker]) -> None:
        """Update price history for volatility calculation."""

        now = datetime.now(UTC)
        if self._last_update_time + self._update_interval < now:
            return

        self._last_update_time = now

        mexc_book = book_tickers.get(ExchangeEnum.MEXC)
        gateio_book = book_tickers.get(ExchangeEnum.GATEIO)
        for key, value in [
            (self.col_mexc_bid, mexc_book.bid_price), (self.col_mexc_ask, mexc_book.ask_price),
            (self.col_gateio_bid, gateio_book.bid_price), (self.col_gateio_ask, gateio_book.ask_price)
        ]:
            self.price_history[key].append(value)
            if len(self.price_history[key]) > self._max_history_length:
                self.price_history[key].pop(0)

    
    def generate_live_signal(self, book_tickers: Dict[ExchangeEnum, BookTicker]) -> Signal:
        """
        Generate live trading signal using arbitrage analyzer logic.
        

        Returns:
           Signal
        """
        # Validate market data


        # Update price history for volatility calculation
        self._update_price_history(book_tickers)
        
        # TODO: implement live signal generation logic
        return Signal.HOLD

    def initialize_backtest(self, df: pd.DataFrame):
        """Initialize backtest state."""

        # init balances columns
        df[self.col_mexc_balance] = 0
        df[self.col_gateio_balance] = 0

        row = df.iloc[0]

        if row[self.col_mexc_ask] < row[self.col_gateio_ask]:
            qty = self._backtesting_params.initial_balance_usd / row[self.col_mexc_ask]
            trade = TradeEntry(exchange=ExchangeEnum.MEXC, side=Side.BUY, price=row[self.col_mexc_ask], qty=qty)
        else:
            qty = self._backtesting_params.initial_balance_usd / row[self.col_gateio_ask]
            trade = TradeEntry(exchange=ExchangeEnum.GATEIO, side=Side.BUY, price=row[self.col_gateio_ask], qty=qty)

        self.position.add_trade(trade)
        df_backtest = df[1:]
        self._update_df_balance(df_backtest, df_backtest.index[0])
        return df_backtest


    def backtest(self, df: pd.DataFrame) -> PerformanceMetrics:
        df = self._prepare_signals(df)
        df = self.initialize_backtest(df)

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
        profit_cols = ['mexc_to_gateio_spread', 'gateio_to_mexc_spread']
        changes_mask = df[profit_cols].ne(df[profit_cols].shift()).any(axis=1)
        signal_points = df[changes_mask].copy()

        for idx, row in signal_points.iterrows():
            if self.position and df.loc[idx,'transfer_in_progress']:
                continue  # Skip processing during transfer

            if row['mexc_to_gateio_spread']:
                qty = df.loc[idx, self.col_mexc_balance]
                if qty == 0:
                    continue

                self.position.add_arbitrage_trade(idx, [
                    TradeEntry(exchange=ExchangeEnum.MEXC, side=Side.BUY, price=row[self.col_mexc_ask], qty=qty),
                    TradeEntry(exchange=ExchangeEnum.GATEIO, side=Side.SELL, price=row[self.col_gateio_bid], qty=qty)
                ]).start_transfer(self._backtesting_params.transfer_delay_minutes, idx,
                                  ExchangeEnum.MEXC, ExchangeEnum.GATEIO)

                self._update_df_balance(df, idx)
                self._update_transfer_in_progress(df,idx)
            elif row['gateio_to_mexc_spread']:
                qty = df.loc[idx, self.col_gateio_balance]
                if qty == 0:
                    continue

                self.position.add_arbitrage_trade(idx,[
                    TradeEntry(exchange=ExchangeEnum.GATEIO, side=Side.BUY, price=row[self.col_gateio_ask], qty=qty),
                    TradeEntry(exchange=ExchangeEnum.MEXC, side=Side.SELL, price=row[self.col_mexc_bid], qty=qty)
                ]).start_transfer(self._backtesting_params.transfer_delay_minutes, idx,
                                  ExchangeEnum.GATEIO, ExchangeEnum.MEXC)

                self._update_df_balance(df, idx)
                self._update_transfer_in_progress(df,idx)


    def _prepare_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply strategy signals_v2 to historical data using arbitrage analyzer logic.
        
        Args:
            df: Historical market data DataFrame

        Returns:
            DataFrame with added signal columns
        """


        gateio_spread_bps = ((df[self.col_gateio_bid] - df[self.col_mexc_ask]) /
                             df[self.col_mexc_ask] * 10000)

        mexc_spread_bps = ((df[self.col_mexc_bid] - df[self.col_gateio_ask]) /
                           df[self.col_gateio_ask] * 10000)

        df['mexc_to_gateio_spread'] = gateio_spread_bps > self.min_profit_bps
        df['gateio_to_mexc_spread'] = mexc_spread_bps > self.min_profit_bps

        df['has_opportunity'] = df['mexc_to_gateio_spread'] | df['gateio_to_mexc_spread']
        df['transfer_in_progress'] = False  # Placeholder for transfer logic


        return df