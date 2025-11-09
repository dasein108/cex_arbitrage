"""
Cross-Exchange Mean Reversion Arbitrage Signal V2

This strategy profits from temporary price divergences between exchanges by entering
during high spreads and exiting when prices revert to parity using real-time bid/ask data.

Strategy Logic:
1. Monitor price differences between MEXC spot and Gate.io futures using bid/ask prices
2. Enter positions when price spreads are HIGH (divergence from parity)
3. Exit when spreads return to LOW levels (mean reversion to equilibrium)
4. Profit from the convergence back to fair value parity

Key Advantages:
- Uses bid/ask prices for more precise arbitrage detection
- Integrated with SignalBacktester architecture
- Realistic cost modeling with fees and slippage
- Enhanced performance metrics
"""

from typing import Dict, List, Optional
import pandas as pd
import numpy as np
from datetime import datetime, UTC, timedelta

from exchanges.structs import Symbol, BookTicker, Fees
from exchanges.structs.enums import ExchangeEnum, Side
from infrastructure.logging import HFTLoggerInterface, get_logger
from trading.signals_v2.entities import PositionEntry, TradeEntry, PerformanceMetrics, BacktestingParams
from trading.signals_v2.strategy_signal import StrategySignal
from trading.data_sources.column_utils import get_column_key

# Default parameters for cross-exchange parity strategy
DEFAULT_PARITY_PARAMS = {
    'parity_threshold_bps': 8.0,           # Exit threshold - back to parity (8 basis points = 0.08%)
    'lookback_periods': 50,                # Periods to calculate median spread
    'divergence_multiplier': 2.0,          # Enter when spread > median * 2.0 (reduced from 2.5)
    'position_size_usd': 1000.0,           # Position size
    'max_position_time_minutes': 120,      # Maximum hold time (2 hours)
    'min_hold_time_minutes': 5,            # Minimum hold time to avoid noise
    'max_spread_bps': 100.0,               # Emergency exit if spread too wide (100 bps = 1.0%)
    'take_profit_bps': 30.0,               # Minimum entry threshold (30 basis points = 0.3%)
    'max_daily_positions': 10,             # Increased position limit
    'min_volume_ratio': 0.1,               # Min volume ratio between exchanges
    'volatility_filter': True              # Avoid high volatility periods
}

class CrossExchangeParitySignal(StrategySignal):
    """
    Cross-Exchange Mean Reversion Arbitrage Strategy V2
    
    This strategy profits from temporary price divergences between exchanges
    by entering during high spreads and exiting when prices converge back to parity.
    
    Key Features:
    - Uses bid/ask prices for precise arbitrage detection
    - Integrated with SignalBacktester architecture
    - Realistic cost modeling with fees and slippage
    - Enhanced performance metrics
    """
    
    name: str = "cross_exchange_parity_signal"
    
    def __init__(self,
                 params: Dict[str, float] = None,
                 backtesting_params: BacktestingParams = None,
                 fees: Dict[ExchangeEnum, Fees] = None,
                 logger: HFTLoggerInterface = None):
        """
        Initialize cross-exchange parity arbitrage strategy.
        
        Args:
            params: Strategy parameters dictionary
            backtesting_params: Backtesting configuration
            fees: Exchange fee structure
            logger: HFT logger interface
        """
        self.logger = logger or get_logger(__name__)
        self.params = {**DEFAULT_PARITY_PARAMS, **(params or {})}
        self.fees = fees or {}
        self._backtesting_params = backtesting_params or BacktestingParams()
        
        # Column mappings for DataFrame access
        self.col_mexc_bid = get_column_key(ExchangeEnum.MEXC, 'bid_price')
        self.col_mexc_ask = get_column_key(ExchangeEnum.MEXC, 'ask_price')
        self.col_gateio_futures_bid = get_column_key(ExchangeEnum.GATEIO_FUTURES, 'bid_price')
        self.col_gateio_futures_ask = get_column_key(ExchangeEnum.GATEIO_FUTURES, 'ask_price')
        
        # Position tracking
        self.position: Optional[PositionEntry] = PositionEntry(entry_time=datetime.now(UTC))
        self.historical_positions: List[PositionEntry] = []
        
        # Analysis results for reporting
        self.analysis_results = {}
        
    def backtest(self, df: pd.DataFrame) -> PerformanceMetrics:
        """Required method for SignalBacktester integration."""
        
        # Prepare signals from DataFrame
        df_with_signals = self._prepare_parity_signals(df)
        
        # Analyze signals for reporting
        self.analyze_signals(df_with_signals)
        
        # Initialize backtest state
        df_backtest = self._initialize_backtest(df_with_signals)
        
        # Emulate trading using signals
        self._emulate_parity_trading(df_backtest)
        
        # Return performance metrics
        return self.position.get_performance_metrics(self._backtesting_params.initial_balance_usd)
    
    def _prepare_parity_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate parity entry/exit signals from book ticker data."""
        
        # Log data quality statistics
        total_rows = len(df)
        valid_mexc = df[self.col_mexc_bid].notna() & df[self.col_mexc_ask].notna()
        valid_futures = df[self.col_gateio_futures_bid].notna() & df[self.col_gateio_futures_ask].notna()
        valid_both = valid_mexc & valid_futures
        
        if hasattr(self, '_logger') and self._logger:
            self._logger.info(f"Data quality - Total rows: {total_rows}, "
                            f"MEXC valid: {valid_mexc.sum()} ({valid_mexc.mean()*100:.1f}%), "
                            f"Futures valid: {valid_futures.sum()} ({valid_futures.mean()*100:.1f}%), "
                            f"Both valid: {valid_both.sum()} ({valid_both.mean()*100:.1f}%)")
        
        # Calculate mid prices for both exchanges
        df['mexc_mid'] = (df[self.col_mexc_bid] + df[self.col_mexc_ask]) / 2
        df['futures_mid'] = (df[self.col_gateio_futures_bid] + df[self.col_gateio_futures_ask]) / 2
        
        # Calculate spread in basis points
        df['mid_price'] = (df['mexc_mid'] + df['futures_mid']) / 2
        df['spread_bps'] = (abs(df['mexc_mid'] - df['futures_mid']) / df['mid_price'] * 10000).fillna(0)
        
        # Calculate rolling median spread for dynamic thresholds
        df['median_spread_bps'] = df['spread_bps'].rolling(
            window=int(self.params['lookback_periods']), 
            min_periods=10
        ).median().fillna(0)
        
        # Calculate dynamic entry threshold (enter when spread is high - divergence)
        df['target_entry_spread_bps'] = np.maximum(
            df['median_spread_bps'] * self.params['divergence_multiplier'],
            self.params['take_profit_bps']
        )
        
        # Entry signals: spread divergence (high spread - opportunity for mean reversion)
        df['parity_entry_signal'] = (
            (df['spread_bps'] >= df['target_entry_spread_bps']) &
            (df['median_spread_bps'] > 0) &  # Ensure valid median
            (df['spread_bps'] <= self.params['max_spread_bps'])  # Not too extreme
        )
        
        # Exit signals: back to parity (low spread - mean reversion completed)
        df['parity_exit_signal'] = df['spread_bps'] <= self.params['parity_threshold_bps']
        
        # Emergency exit: spread too wide
        df['emergency_exit_signal'] = df['spread_bps'] >= self.params['max_spread_bps']
        
        # Combined exit signal
        df['exit_signal'] = df['parity_exit_signal'] | df['emergency_exit_signal']
        
        # Direction signals based on price difference
        # df['mexc_higher'] = df['mexc_mid'] > df['futures_mid']  # Sell MEXC, buy futures
        # df['futures_higher'] = df['futures_mid'] > df['mexc_mid']  # Buy MEXC, sell futures
        df['mexc_higher'] = df[self.col_mexc_bid] > df[self.col_gateio_futures_ask]  # Sell MEXC, buy futures
        df['futures_higher'] = df[self.col_gateio_futures_bid] > df[self.col_mexc_ask]  # Buy MEXC, sell futures

        return df
    
    def _initialize_backtest(self, df: pd.DataFrame) -> pd.DataFrame:
        """Initialize backtest state and set initial position."""
        
        # Initialize position tracking
        self.position = PositionEntry(entry_time=datetime.now(UTC))
        
        # Add position state columns
        df['position_active'] = False
        df['entry_time'] = pd.NaT
        df['hold_time_minutes'] = 0.0
        
        return df.copy()
    
    def _check_time_exit(self, current_time, entry_time) -> bool:
        """Check if position should be exited due to time limits."""
        if entry_time is None:
            return False
            
        hold_time = (current_time - entry_time).total_seconds() / 60
        return hold_time >= self.params['max_position_time_minutes']
    
    def _check_min_hold_time(self, current_time, entry_time) -> bool:
        """Check if minimum hold time has passed."""
        if entry_time is None:
            return True
            
        hold_time = (current_time - entry_time).total_seconds() / 60
        return hold_time >= self.params['min_hold_time_minutes']
    
    def _emulate_parity_trading(self, df: pd.DataFrame) -> None:
        """Emulate parity trading using vectorized approach."""
        
        # Track position state
        position_active = False
        entry_time = None
        daily_position_count = 0
        last_trade_date = None
        
        # Find signal changes for efficient processing
        signal_changes = (
            df['parity_entry_signal'].ne(df['parity_entry_signal'].shift()) |
            df['exit_signal'].ne(df['exit_signal'].shift())
        )
        signal_points = df[signal_changes].copy()
        
        for idx, row in signal_points.iterrows():
            current_time = idx
            current_date = current_time.date() if hasattr(current_time, 'date') else None
            
            # Data validation: Skip rows with NaN prices
            required_prices = [
                row[self.col_mexc_bid], row[self.col_mexc_ask],
                row[self.col_gateio_futures_bid], row[self.col_gateio_futures_ask]
            ]
            if pd.isna(required_prices).any():
                continue  # Skip this row if any required price is NaN
            
            # Reset daily counter
            if last_trade_date != current_date:
                daily_position_count = 0
                last_trade_date = current_date
            
            # Entry logic
            if (not position_active and 
                row['parity_entry_signal'] and 
                daily_position_count < self.params['max_daily_positions']):
                
                # Determine direction and create trades
                if row['mexc_higher']:  # Sell MEXC (higher), buy futures (lower)
                    # Use average price for quantity to ensure equal quantities
                    avg_price = (row[self.col_mexc_bid] + row[self.col_gateio_futures_ask]) / 2
                    qty = self.params['position_size_usd'] / avg_price
                    
                    trades = [
                        TradeEntry(
                            exchange=ExchangeEnum.MEXC,
                            side=Side.SELL,
                            price=row[self.col_mexc_bid],
                            qty=qty,
                            fee_pct=self.fees.get(ExchangeEnum.MEXC, Fees()).taker_fee,
                            slippage_pct=self._backtesting_params.slippage_pct
                        ),
                        TradeEntry(
                            exchange=ExchangeEnum.GATEIO_FUTURES,
                            side=Side.BUY,
                            price=row[self.col_gateio_futures_ask],
                            qty=qty,
                            fee_pct=self.fees.get(ExchangeEnum.GATEIO_FUTURES, Fees()).taker_fee,
                            slippage_pct=self._backtesting_params.slippage_pct
                        )
                    ]
                elif row['futures_higher']:  # Buy MEXC (lower), sell futures (higher)
                    # Use average price for quantity to ensure equal quantities
                    avg_price = (row[self.col_mexc_ask] + row[self.col_gateio_futures_bid]) / 2
                    qty = self.params['position_size_usd'] / avg_price
                    
                    trades = [
                        TradeEntry(
                            exchange=ExchangeEnum.MEXC,
                            side=Side.BUY,
                            price=row[self.col_mexc_ask],
                            qty=qty,
                            fee_pct=self.fees.get(ExchangeEnum.MEXC, Fees()).taker_fee,
                            slippage_pct=self._backtesting_params.slippage_pct
                        ),
                        TradeEntry(
                            exchange=ExchangeEnum.GATEIO_FUTURES,
                            side=Side.SELL,
                            price=row[self.col_gateio_futures_bid],
                            qty=qty,
                            fee_pct=self.fees.get(ExchangeEnum.GATEIO_FUTURES, Fees()).taker_fee,
                            slippage_pct=self._backtesting_params.slippage_pct
                        )
                    ]
                else:
                    continue  # No clear direction
                
                # Execute entry trades
                self.position.add_arbitrage_trade(current_time, trades)
                position_active = True
                entry_time = current_time
                daily_position_count += 1
                
            # Exit logic
            elif (position_active and 
                  (row['exit_signal'] or 
                   self._check_time_exit(current_time, entry_time))):
                
                # Check minimum hold time
                if self._check_min_hold_time(current_time, entry_time):
                    # Close position (reverse trades)
                    self._close_parity_position(current_time, row)
                    position_active = False
                    entry_time = None
    
    def _close_parity_position(self, current_time, row) -> None:
        """Close parity position with appropriate trades."""
        # Data validation: Check for NaN prices before closing position
        required_prices = [
            row[self.col_mexc_bid], row[self.col_mexc_ask],
            row[self.col_gateio_futures_bid], row[self.col_gateio_futures_ask]
        ]
        if pd.isna(required_prices).any():
            return  # Cannot close position with NaN prices
        
        # Get the most recent arbitrage trade to determine direction
        if not self.position.arbitrage_trades:
            return
            
        # Get the last trade timestamp and trades
        last_timestamp = max(self.position.arbitrage_trades.keys())
        entry_trades = self.position.arbitrage_trades[last_timestamp]
        
        if len(entry_trades) != 2:
            return
            
        # Reverse the entry trades for exit
        exit_trades = []
        
        for entry_trade in entry_trades:
            # Reverse the side (buy becomes sell, sell becomes buy)
            exit_side = Side.SELL if entry_trade.side == Side.BUY else Side.BUY
            
            # Use appropriate price based on new side
            if entry_trade.exchange == ExchangeEnum.MEXC:
                exit_price = row[self.col_mexc_bid] if exit_side == Side.SELL else row[self.col_mexc_ask]
            else:  # GATEIO_FUTURES
                exit_price = row[self.col_gateio_futures_bid] if exit_side == Side.SELL else row[self.col_gateio_futures_ask]
            
            exit_trades.append(TradeEntry(
                exchange=entry_trade.exchange,
                side=exit_side,
                price=exit_price,
                qty=entry_trade.qty,
                fee_pct=self.fees.get(entry_trade.exchange, Fees()).taker_fee,
                slippage_pct=self._backtesting_params.slippage_pct
            ))
        
        # Execute exit trades
        self.position.add_arbitrage_trade(current_time, exit_trades)
    
    def analyze_signals(self, df: pd.DataFrame) -> Dict:
        """Analyze parity signals for reporting."""
        
        results = {}
        
        # Entry signal analysis
        entry_signals = df[df['parity_entry_signal']]
        exit_signals = df[df['exit_signal']]
        
        results['entry_analysis'] = {
            'total_entry_signals': len(entry_signals),
            'pct_of_data': len(entry_signals) / len(df) * 100 if len(df) > 0 else 0,
            'avg_spread_bps': entry_signals['spread_bps'].mean() if len(entry_signals) > 0 else 0,
            'median_spread_bps': entry_signals['spread_bps'].median() if len(entry_signals) > 0 else 0
        }
        
        results['exit_analysis'] = {
            'total_exit_signals': len(exit_signals),
            'pct_of_data': len(exit_signals) / len(df) * 100 if len(df) > 0 else 0,
            'avg_spread_bps': exit_signals['spread_bps'].mean() if len(exit_signals) > 0 else 0,
            'median_spread_bps': exit_signals['spread_bps'].median() if len(exit_signals) > 0 else 0
        }
        
        # Spread statistics
        results['spread_statistics'] = {
            'avg_spread_bps': df['spread_bps'].mean(),
            'median_spread_bps': df['spread_bps'].median(),
            'std_spread_bps': df['spread_bps'].std(),
            'min_spread_bps': df['spread_bps'].min(),
            'max_spread_bps': df['spread_bps'].max(),
            'quantiles': {
                '25%': df['spread_bps'].quantile(0.25),
                '50%': df['spread_bps'].quantile(0.50),
                '75%': df['spread_bps'].quantile(0.75),
                '95%': df['spread_bps'].quantile(0.95),
                '99%': df['spread_bps'].quantile(0.99)
            }
        }
        
        # Parameter analysis
        results['parameter_analysis'] = {
            'parity_threshold_bps': self.params['parity_threshold_bps'],
            'take_profit_bps': self.params['take_profit_bps'],
            'max_spread_bps': self.params['max_spread_bps'],
            'divergence_multiplier': self.params['divergence_multiplier'],
            'signals_below_parity_threshold': (df['spread_bps'] <= self.params['parity_threshold_bps']).sum(),
            'signals_above_take_profit': (df['spread_bps'] >= self.params['take_profit_bps']).sum()
        }
        
        self.analysis_results = results
        return results
    
    def get_live_signal(self, book_tickers: Dict[ExchangeEnum, BookTicker]) -> Optional[Dict]:
        """Generate live trading signal using book ticker data."""
        
        mexc_book = book_tickers.get(ExchangeEnum.MEXC)
        futures_book = book_tickers.get(ExchangeEnum.GATEIO_FUTURES)
        
        if not mexc_book or not futures_book:
            return None
        
        # Calculate mid prices
        mexc_mid = (mexc_book.bid_price + mexc_book.ask_price) / 2
        futures_mid = (futures_book.bid_price + futures_book.ask_price) / 2
        
        # Calculate spread
        mid_price = (mexc_mid + futures_mid) / 2
        spread_bps = abs(mexc_mid - futures_mid) / mid_price * 10000
        
        # Check divergence entry condition (high spread - opportunity for mean reversion)
        if spread_bps >= self.params['take_profit_bps'] and spread_bps <= self.params['max_spread_bps']:
            direction = 'mexc_higher' if mexc_mid > futures_mid else 'futures_higher'
            
            return {
                'signal': 'ENTER',
                'direction': direction,
                'spread_bps': spread_bps,
                'mexc_mid': mexc_mid,
                'futures_mid': futures_mid,
                'reason': f'Divergence entry: {spread_bps:.1f}bps spread (expecting mean reversion)'
            }
        
        return None
