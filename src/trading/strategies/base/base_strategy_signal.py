"""
Base Strategy Signal Implementation with Internal Position Tracking

Common implementation for all strategy signals_v2 with integrated position management.
Eliminates external PositionTracker dependency by handling all tracking internally.
"""

from typing import Dict, Any, Optional, Union, List, Tuple
import pandas as pd
import numpy as np
from collections import deque
from datetime import datetime, timezone
import logging
from dataclasses import dataclass, field

from trading.strategies.base.strategy_signal_interface import StrategySignalInterface
from trading.signals.types.signal_types import Signal
from trading.strategies.base.types import PerformanceMetrics
from exchanges.structs.enums import ExchangeEnum, Side

@dataclass
class TradeEntry:
    side: Side
    entry_price: float
    exit_price: Optional[float] = None

@dataclass
class Position:
    """Internal position representation for tracking."""
    entry_time: datetime
    entry_signal: Signal
    entry_data: Dict[str, Any]
    position_size_usd: float
    entries: Dict[ExchangeEnum, List[TradeEntry]]  # e.g., {ExchangeEnum.MEXC: TradeEntry(...)}
    strategy_type: Optional[str] = None
    unrealized_pnl_usd: float = 0.0
    unrealized_pnl_pct: float = 0.0
    hold_time_minutes: float = 0.0
    transfer_completion_time: Optional[datetime] = None

    def is_transfer_in_progress(self, current_time: datetime) -> bool:
        """Check if transfer is in progress."""
        if self.transfer_completion_time is None:
            return False

        return current_time < self.transfer_completion_time



@dataclass
class Trade:
    """Completed trade representation."""
    entry_time: datetime
    exit_time: datetime
    strategy_type: str
    entry_signal: Signal
    exit_signal: Signal
    position_size_usd: float
    entries: Dict[ExchangeEnum, TradeEntry]  # Entry side trades
    exits: Dict[ExchangeEnum, TradeEntry]    # Exit side trades
    pnl_usd: float
    pnl_pct: float
    hold_time_minutes: float
    entry_data: Dict[str, Any] = field(default_factory=dict)
    exit_data: Dict[str, Any] = field(default_factory=dict)


class BaseStrategySignal(StrategySignalInterface):
    """
    Base implementation with internal position tracking for all strategy signals_v2.
    
    Provides complete position management functionality:
    - Internal position tracking and state management
    - Integrated P&L calculation and trade recording
    - Performance metrics and analytics
    - Simplified method interfaces (signal, market_data only)
    - Eliminates external PositionTracker dependency
    """
    
    def __init__(self, 
                 strategy_type: str,
                 lookback_periods: int = 500,
                 min_history: int = 50,
                 position_size_usd: float = 1000.0,
                 total_fees: float = 0.0025,
                 **params):
        """
        Initialize base strategy signal with internal position tracking.
        
        Args:
            strategy_type: Name of the strategy
            lookback_periods: Number of periods for rolling calculations
            min_history: Minimum history required for signal generation
            position_size_usd: Default position size in USD
            total_fees: Total round-trip fees as decimal
            **params: Additional strategy parameters
        """
        self.strategy_type = strategy_type
        self.lookback_periods = lookback_periods
        self.min_history = min_history
        self.position_size_usd = position_size_usd
        self.total_fees = total_fees
        
        # Store additional parameters
        self.params = params
        
        # Initialize indicator storage
        self.indicators = {}
        self.rolling_windows = {}
        
        # Performance tracking
        self.signal_count = 0
        self.last_signal = Signal.HOLD
        self.last_signal_time = None
        
        # Internal position tracking state
        self._current_position: Optional[Position] = None
        self._completed_trades: List[Trade] = []
        self._positions_history: List[Position] = []
        
        # Logger
        self.logger = logging.getLogger(f"{self.__class__.__name__}")
    
    async def preload(self, historical_data: pd.DataFrame, **params) -> None:
        """
        Preload historical data for strategy initialization.
        
        Default implementation that can be overridden by specific strategies.
        """
        if historical_data.empty:
            self.logger.warning("Empty historical data provided for preload")
            return
        
        # Validate data
        if not self.validate_market_data(historical_data):
            raise ValueError("Invalid historical data format")
        
        # Calculate common indicators
        self._calculate_common_indicators(historical_data)
        
        # Initialize rolling windows with historical data
        self._initialize_rolling_windows(historical_data)
        
        self.logger.info(f"Preloaded {len(historical_data)} historical records")
    
    def validate_market_data(self, data: Union[Dict[str, Any], pd.DataFrame]) -> bool:
        """
        Validate that market data has required fields.
        
        Can be overridden for strategy-specific validation.
        """
        if isinstance(data, pd.DataFrame):
            # Required columns for DataFrame
            required_columns = [
                'MEXC_SPOT:bid_price', 'MEXC_SPOT:ask_price',
                'GATEIO_SPOT:bid_price', 'GATEIO_SPOT:ask_price',
                'GATEIO_FUTURES:bid_price', 'GATEIO_FUTURES:ask_price'
            ]
            return all(col in data.columns for col in required_columns)
        else:
            # Required fields for dict
            required_fields = [
                'mexc_bid', 'mexc_ask',
                'gateio_spot_bid', 'gateio_spot_ask',
                'gateio_futures_bid', 'gateio_futures_ask'
            ]
            return all(field in data for field in required_fields)
    
    def get_required_lookback(self) -> int:
        """Get the minimum lookback period required."""
        return self.lookback_periods
    
    def calculate_signal_confidence(self, indicators: Dict[str, float]) -> float:
        """
        Calculate base confidence score.
        
        Can be overridden for strategy-specific confidence calculations.
        """
        # Default confidence based on indicator strength
        confidence = 0.5
        
        # Adjust based on spread quality
        if 'spread_z_score' in indicators:
            z_score = abs(indicators['spread_z_score'])
            if z_score > 3:
                confidence = 0.9
            elif z_score > 2:
                confidence = 0.7
            elif z_score > 1:
                confidence = 0.5
            else:
                confidence = 0.3
        
        return min(max(confidence, 0.0), 1.0)
    
    # Internal Position Tracking Implementation
    
    def _get_performance_metrics(self) -> PerformanceMetrics:
        """
        Get comprehensive performance metrics from internal position tracking.
        
        Returns:
            PerformanceMetrics object containing complete trading performance data
        """
        total_trades = len(self._completed_trades)
        
        # Initialize PerformanceMetrics with strategy type
        metrics = PerformanceMetrics(
            strategy_type=self.strategy_type,
            total_positions=len(self._positions_history),
            completed_trades=total_trades
        )
        
        if total_trades == 0:
            return metrics
        
        # Calculate basic metrics
        total_pnl_usd = sum(trade.pnl_usd for trade in self._completed_trades)
        total_pnl_pct = sum(trade.pnl_pct for trade in self._completed_trades)
        
        # Win rate calculation
        winning_trades = [t for t in self._completed_trades if t.pnl_usd > 0]
        losing_trades = [t for t in self._completed_trades if t.pnl_usd < 0]
        win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0.0
        
        # Average trade duration
        avg_duration = sum(trade.hold_time_minutes for trade in self._completed_trades) / total_trades
        
        # Additional metrics
        wins = [t.pnl_usd for t in winning_trades]
        losses = [abs(t.pnl_usd) for t in losing_trades]  # Use absolute values for avg_loss
        
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        
        # Calculate drawdown
        cumulative_pnl = []
        running_pnl = 0.0
        for trade in self._completed_trades:
            running_pnl += trade.pnl_usd
            cumulative_pnl.append(running_pnl)
        
        max_drawdown = 0.0
        if cumulative_pnl:
            peak = cumulative_pnl[0]
            for pnl in cumulative_pnl:
                if pnl > peak:
                    peak = pnl
                drawdown = peak - pnl
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
        
        # Calculate profit factor
        total_wins = sum(wins) if wins else 0.0
        total_losses = sum(losses) if losses else 0.0
        profit_factor = total_wins / total_losses if total_losses > 0 else 0.0
        
        # Calculate min/max hold times
        hold_times = [trade.hold_time_minutes for trade in self._completed_trades]
        min_hold_time = min(hold_times) if hold_times else 0.0
        max_hold_time = max(hold_times) if hold_times else 0.0
        
        # Update metrics object
        metrics.total_pnl_usd = total_pnl_usd
        metrics.total_pnl_pct = total_pnl_pct
        metrics.realized_pnl_usd = total_pnl_usd  # All completed trades are realized
        metrics.realized_pnl_pct = total_pnl_pct
        metrics.win_rate = win_rate
        metrics.avg_win_usd = avg_win
        metrics.avg_loss_usd = avg_loss
        metrics.profit_factor = profit_factor
        metrics.avg_hold_time_minutes = avg_duration
        metrics.min_hold_time_minutes = min_hold_time
        metrics.max_hold_time_minutes = max_hold_time
        metrics.max_drawdown_usd = max_drawdown
        metrics.sharpe_ratio = self._calculate_sharpe_ratio()
        
        # Include open positions if any
        if self._current_position:
            metrics.open_positions = 1
            # Add current position's unrealized P&L if available
            metrics.unrealized_pnl_usd = self._current_position.unrealized_pnl_usd
        
        # Use the update_pnl_metrics method to ensure proper calculation
        # Convert Trade objects to compatible format for the method
        metrics.update_pnl_metrics(self._completed_trades)
        
        return metrics
    
    def reset_position_tracking(self) -> None:
        """
        Reset internal position tracking state.
        
        Clears all position history, completed trades, and current positions.
        """
        self._current_position = None
        self._completed_trades.clear()
        self._positions_history.clear()
        self.logger.info(f"Position tracking reset for {self.strategy_type}")

    def _apply_signal_to_backtest(self, df: pd.DataFrame, **params) -> pd.DataFrame:
        raise NotImplementedError("Should be implemented in inheriting class")



    def backtest(self, df: pd.DataFrame, **params) -> PerformanceMetrics:
        df = self._apply_signal_to_backtest(df, **params)

        self._emulate_trading(df)

        return self._get_performance_metrics()

    def _emulate_trading(self, df_with_signals: pd.DataFrame) -> None:
        """
        Internal vectorized position tracking for backtesting.
        
        Processes signal changes and manages positions/trades internally.
        This replaces the external PositionTracker.track_positions_vectorized() method.
        
        Args:
            df_with_signals: DataFrame with signal column added
        """
        # Reset state for fresh backtest
        self.reset_position_tracking()
        
        # Find signal changes
        signal_changes = df_with_signals['signal'].ne(df_with_signals['signal'].shift())
        signal_points = df_with_signals[signal_changes].copy()
        
        current_time = None
        
        for idx, row in signal_points.iterrows():
            current_time = row.name if hasattr(row.name, 'to_pydatetime') else datetime.now(timezone.utc)
            signal_str = row['signal']

            # Convert string signal to Signal enum
            if signal_str == 'enter':
                signal = Signal.ENTER
            elif signal_str == 'exit':
                signal = Signal.EXIT
            else:
                signal = Signal.HOLD
            
            # Process signal
            if signal == Signal.ENTER and self._current_position is None:
                self._open_position(signal, row, current_time)
            elif signal == Signal.EXIT and self._current_position is not None:
                self._close_position(signal, row, current_time)
    
    def _open_position(self, signal: Signal, row: pd.Series, timestamp: datetime) -> None:
        """
        Internal position opening with timestamp tracking.
        
        Args:
            signal: ENTER signal
            row: Market data snapshot
            timestamp: Position entry timestamp
        """
        # Calculate entry prices using strategy-specific logic
        entry_prices = self._calculate_entry_prices(row)
        
        if not entry_prices:
            self.logger.warning(f"Could not calculate entry prices for {self.strategy_type}")
            return
        
        # Create TradeEntry objects for each exchange
        trade_entries = {}
        for exchange, price in entry_prices.items():
            # Determine side based on strategy logic (default: BUY for entry)
            side = self._determine_entry_side(exchange, row)
            trade_entries[exchange] = TradeEntry(
                side=side,
                entry_price=price,
                exit_price=None
            )
        
        # Create position
        position = Position(
            entry_time=timestamp,
            strategy_type=self.strategy_type,
            entry_signal=signal,
            entry_data=row.copy(),
            position_size_usd=self.position_size_usd,
            entries=trade_entries
        )
        
        self._current_position = position
        self._positions_history.append(position)
        
        self.logger.debug(f"Position opened at {timestamp}: {entry_prices}")
    
    def _close_position(self, signal: Signal, row: pd.Series, timestamp: datetime) -> None:
        """
        Internal position closing with P&L calculation.
        
        Args:
            signal: EXIT signal
            row: Market data snapshot
            timestamp: Position exit timestamp
        """
        if not self._current_position:
            return
        
        # Calculate exit prices using strategy-specific logic
        exit_prices = self._calculate_exit_prices(row)
        
        if not exit_prices:
            self.logger.warning(f"Could not calculate exit prices for {self.strategy_type}")
            return
        
        # Create TradeEntry objects for exits
        exit_entries = {}
        for exchange, price in exit_prices.items():
            # Determine exit side (opposite of entry side)
            entry_side = self._current_position.entries[exchange].side if exchange in self._current_position.entries else Side.BUY
            exit_side = Side.SELL if entry_side == Side.BUY else Side.BUY
            exit_entries[exchange] = TradeEntry(
                side=exit_side,
                entry_price=price,  # For exits, this is the exit price
                exit_price=None
            )
        
        # Calculate P&L using strategy-specific logic
        pnl_usd, pnl_pct = self._calculate_pnl_from_entries(
            self._current_position.entries,
            exit_entries,
            self._current_position.position_size_usd
        )
        
        # Calculate hold time
        hold_time = (timestamp - self._current_position.entry_time).total_seconds() / 60.0
        
        # Create completed trade
        trade = Trade(
            entry_time=self._current_position.entry_time,
            exit_time=timestamp,
            strategy_type=self.strategy_type,
            entry_signal=self._current_position.entry_signal,
            exit_signal=signal,
            position_size_usd=self._current_position.position_size_usd,
            entries=self._current_position.entries.copy(),
            exits=exit_entries,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            hold_time_minutes=hold_time,
            entry_data=self._current_position.entry_data.copy(),
            exit_data=row.copy()
        )
        
        self._completed_trades.append(trade)
        self._current_position = None
        
        self.logger.debug(f"Position closed at {timestamp}: P&L = ${pnl_usd:.2f} ({pnl_pct:.3f}%)")
    
    def _determine_entry_side(self, exchange: ExchangeEnum, market_data: Dict[str, Any]) -> Side:
        """
        Determine the trading side for entry on a specific exchange.
        
        Default implementation - should be overridden by specific strategies.
        
        Args:
            exchange: Exchange enum
            market_data: Current market data snapshot
            
        Returns:
            Side enum (BUY or SELL)
        """
        # Default strategy: BUY on cheaper exchange, SELL on expensive exchange
        mexc_spot_ask_price = market_data.get('MEXC_SPOT:ask_price', 0)
        gateio_spot_bid_price = market_data.get('GATEIO_SPOT:bid_price', 0)
        
        if exchange == ExchangeEnum.MEXC:
            # Default: BUY on MEXC if it's cheaper
            return Side.BUY if mexc_spot_ask_price < gateio_spot_bid_price else Side.SELL
        elif exchange == ExchangeEnum.GATEIO:
            # Default: SELL on GATEIO if MEXC is cheaper
            return Side.SELL if mexc_spot_ask_price < gateio_spot_bid_price else Side.BUY
        else:
            # Default for futures or other exchanges
            return Side.BUY
    
    def _calculate_entry_prices(self, market_data: Dict[str, Any]) -> Dict[ExchangeEnum, float]:
        """
        Calculate entry prices from market data.
        
        Default implementation - should be overridden by specific strategies.
        
        Args:
            market_data: Current market data snapshot
            
        Returns:
            Dictionary of entry prices by exchange using ExchangeEnum keys
        """
        entry_prices = {}
        
        # Extract standard price fields
        mexc_spot_ask_price = market_data.get('MEXC_SPOT:ask_price', 0)
        gateio_spot_bid_price = market_data.get('GATEIO_SPOT:bid_price', 0)
        gateio_futures_bid_price = market_data.get('GATEIO_FUTURES:bid_price', 0)
        
        if mexc_spot_ask_price > 0:
            entry_prices[ExchangeEnum.MEXC] = mexc_spot_ask_price
        if gateio_spot_bid_price > 0:
            entry_prices[ExchangeEnum.GATEIO] = gateio_spot_bid_price
        if gateio_futures_bid_price > 0:
            entry_prices[ExchangeEnum.GATEIO_FUTURES] = gateio_futures_bid_price
            
        return entry_prices
    
    def _calculate_exit_prices(self, market_data: Dict[str, Any]) -> Dict[ExchangeEnum, float]:
        """
        Calculate exit prices from market data.
        
        Default implementation - should be overridden by specific strategies.
        
        Args:
            market_data: Current market data snapshot
            
        Returns:
            Dictionary of exit prices by exchange using ExchangeEnum keys
        """
        exit_prices = {}
        
        # Extract standard price fields
        mexc_spot_bid_price = market_data.get('MEXC_SPOT:bid_price', 0)
        gateio_spot_ask_price = market_data.get('GATEIO_SPOT:ask_price', 0)
        gateio_futures_ask_price = market_data.get('GATEIO_FUTURES:ask_price', 0)
        
        if mexc_spot_bid_price > 0:
            exit_prices[ExchangeEnum.MEXC] = mexc_spot_bid_price
        if gateio_spot_ask_price > 0:
            exit_prices[ExchangeEnum.GATEIO] = gateio_spot_ask_price
        if gateio_futures_ask_price > 0:
            exit_prices[ExchangeEnum.GATEIO_FUTURES] = gateio_futures_ask_price
            
        return exit_prices
    
    def _calculate_pnl_from_entries(self, entry_trades: Dict[ExchangeEnum, TradeEntry], exit_trades: Dict[ExchangeEnum, TradeEntry], position_size_usd: float) -> Tuple[float, float]:
        """
        Calculate P&L for the trade using TradeEntry objects.
        
        Default implementation for cross-exchange arbitrage.
        Should be overridden by specific strategies.
        
        Args:
            entry_trades: Entry TradeEntry objects by exchange
            exit_trades: Exit TradeEntry objects by exchange
            position_size_usd: Position size in USD
            
        Returns:
            Tuple of (pnl_usd, pnl_pct)
        """
        total_pnl_usd = 0.0
        
        # Calculate P&L for each exchange leg
        for exchange in entry_trades.keys():
            if exchange not in exit_trades:
                continue
                
            entry_trade = entry_trades[exchange]
            exit_trade = exit_trades[exchange]
            
            entry_price = entry_trade.entry_price
            exit_price = exit_trade.entry_price  # For exits, entry_price holds the exit price
            
            if not entry_price or not exit_price:
                continue
            
            # Calculate P&L based on side
            if entry_trade.side == Side.BUY:
                # Bought at entry, sell at exit
                pnl_per_unit = exit_price - entry_price
            else:
                # Sold at entry, buy back at exit
                pnl_per_unit = entry_price - exit_price
            
            # Calculate position units (simplified)
            units = position_size_usd / (2 * entry_price)  # Divide by 2 for dual-leg arbitrage
            exchange_pnl = pnl_per_unit * units
            total_pnl_usd += exchange_pnl
        
        # Subtract fees
        total_pnl_usd -= (position_size_usd * self.total_fees)
        total_pnl_pct = total_pnl_usd / position_size_usd * 100 if position_size_usd > 0 else 0
        
        return total_pnl_usd, total_pnl_pct
    
    def _calculate_pnl(self, entry_prices: Dict[ExchangeEnum, float], exit_prices: Dict[ExchangeEnum, float], position_size_usd: float) -> Tuple[float, float]:
        """
        Calculate P&L for the trade (legacy method for backward compatibility).
        
        Default implementation for cross-exchange arbitrage.
        Should be overridden by specific strategies.
        
        Args:
            entry_prices: Entry prices by exchange using ExchangeEnum keys
            exit_prices: Exit prices by exchange using ExchangeEnum keys
            position_size_usd: Position size in USD
            
        Returns:
            Tuple of (pnl_usd, pnl_pct)
        """
        # Default cross-exchange arbitrage P&L calculation
        MEXC_entry_price = entry_prices.get(ExchangeEnum.MEXC, 0)
        MEXC_exit_price = exit_prices.get(ExchangeEnum.MEXC, 0)
        GATEIO_entry_price = entry_prices.get(ExchangeEnum.GATEIO, 0)
        GATEIO_exit_price = exit_prices.get(ExchangeEnum.GATEIO, 0)
        
        if not all([MEXC_entry_price, MEXC_exit_price, GATEIO_entry_price, GATEIO_exit_price]):
            return 0.0, 0.0
        
        # Calculate P&L for each leg
        MEXC_pnl = (MEXC_exit_price - MEXC_entry_price) / MEXC_entry_price * position_size_usd
        GATEIO_pnl = (GATEIO_entry_price - GATEIO_exit_price) / GATEIO_entry_price * position_size_usd
        
        # Total P&L minus fees
        total_pnl_usd = MEXC_pnl + GATEIO_pnl - (position_size_usd * self.total_fees)
        total_pnl_pct = total_pnl_usd / position_size_usd * 100
        
        return total_pnl_usd, total_pnl_pct
    
    def _calculate_sharpe_ratio(self) -> float:
        """
        Calculate Sharpe ratio from completed trades.
        
        Returns:
            Sharpe ratio (assumes risk-free rate of 0)
        """
        if len(self._completed_trades) < 2:
            return 0.0
        
        returns = [trade.pnl_pct for trade in self._completed_trades]
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        
        if std_return == 0:
            return 0.0
        
        # Annualized Sharpe (assuming daily returns)
        return (mean_return / std_return) * np.sqrt(365)
    
    # Protected helper methods
    
    def _calculate_common_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate common indicators used by all strategies.
        
        Args:
            df: Market data DataFrame
            
        Returns:
            DataFrame with added indicator columns
        """
        # Calculate spreads
        df['MEXC_SPOT:spread'] = (df['MEXC_SPOT:ask_price'] - df['MEXC_SPOT:bid_price']) / df['MEXC_SPOT:ask_price'] * 100
        df['GATEIO_SPOT:spread'] = (df['GATEIO_SPOT:ask_price'] - df['GATEIO_SPOT:bid_price']) / df['GATEIO_SPOT:ask_price'] * 100
        df['GATEIO_FUTURES:spread'] = (df['GATEIO_FUTURES:ask_price'] - df['GATEIO_FUTURES:bid_price']) / df['GATEIO_FUTURES:ask_price'] * 100
        
        # Calculate cross-exchange spreads
        df['mexc_vs_gateio_futures'] = (
            (df['MEXC_SPOT:bid_price'] - df['GATEIO_FUTURES:ask_price']) / 
            df['MEXC_SPOT:bid_price'] * 100
        )
        
        df['gateio_spot_vs_futures'] = (
            (df['GATEIO_SPOT:bid_price'] - df['GATEIO_FUTURES:ask_price']) / 
            df['GATEIO_SPOT:bid_price'] * 100
        )
        
        # Calculate rolling statistics
        for spread_col in ['mexc_vs_gateio_futures', 'gateio_spot_vs_futures']:
            if spread_col in df.columns:
                df[f'{spread_col}_mean'] = df[spread_col].rolling(window=self.lookback_periods, min_periods=1).mean()
                df[f'{spread_col}_std'] = df[spread_col].rolling(window=self.lookback_periods, min_periods=1).std()
                df[f'{spread_col}_z_score'] = (df[spread_col] - df[f'{spread_col}_mean']) / (df[f'{spread_col}_std'] + 1e-8)
        
        return df
    
    def _initialize_rolling_windows(self, df: pd.DataFrame) -> None:
        """
        Initialize rolling windows with historical data.
        
        Args:
            df: Historical data DataFrame
        """
        # Initialize deques for rolling calculations
        self.rolling_windows['mexc_vs_gateio_futures'] = deque(
            df['mexc_vs_gateio_futures'].tail(self.lookback_periods).tolist(),
            maxlen=self.lookback_periods
        )
        
        self.rolling_windows['gateio_spot_vs_futures'] = deque(
            df['gateio_spot_vs_futures'].tail(self.lookback_periods).tolist(),
            maxlen=self.lookback_periods
        )
        
        # Store latest indicators
        self.indicators = {
            'mexc_vs_gateio_futures_mean': df['mexc_vs_gateio_futures_mean'].iloc[-1] if 'mexc_vs_gateio_futures_mean' in df.columns else 0,
            'mexc_vs_gateio_futures_std': df['mexc_vs_gateio_futures_std'].iloc[-1] if 'mexc_vs_gateio_futures_std' in df.columns else 1,
            'gateio_spot_vs_futures_mean': df['gateio_spot_vs_futures_mean'].iloc[-1] if 'gateio_spot_vs_futures_mean' in df.columns else 0,
            'gateio_spot_vs_futures_std': df['gateio_spot_vs_futures_std'].iloc[-1] if 'gateio_spot_vs_futures_std' in df.columns else 1,
        }
    
    def _update_rolling_statistics(self, new_value: float, window_name: str) -> Dict[str, float]:
        """
        Update rolling statistics with new value.
        
        Args:
            new_value: New value to add
            window_name: Name of the rolling window
            
        Returns:
            Updated statistics dictionary
        """
        if window_name not in self.rolling_windows:
            self.rolling_windows[window_name] = deque(maxlen=self.lookback_periods)
        
        self.rolling_windows[window_name].append(new_value)
        
        if len(self.rolling_windows[window_name]) >= self.min_history:
            values = np.array(self.rolling_windows[window_name])
            return {
                'mean': np.mean(values),
                'std': np.std(values),
                'min': np.min(values),
                'max': np.max(values),
                'current': new_value,
                'z_score': (new_value - np.mean(values)) / (np.std(values) + 1e-8)
            }
        else:
            return {
                'mean': 0,
                'std': 1,
                'min': 0,
                'max': 0,
                'current': new_value,
                'z_score': 0
            }
    
    def _calculate_spread_from_market_data(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate spreads from live market data.
        
        Args:
            market_data: Current market data snapshot
            
        Returns:
            Dictionary of calculated spreads
        """
        spreads = {}
        
        # Extract prices
        mexc_spot_bid_price = market_data.get('MEXC_SPOT:bid_price', 0)
        mexc_spot_ask_price = market_data.get('MEXC_SPOT:ask_price', 0)
        gateio_spot_bid_price = market_data.get('GATEIO_SPOT:bid_price', 0)
        gateio_spot_ask_price = market_data.get('GATEIO_SPOT:ask_price', 0)
        gateio_futures_bid_price = market_data.get('GATEIO_FUTURES:bid_price', 0)
        gateio_futures_ask_price = market_data.get('GATEIO_FUTURES:ask_price', 0)
        
        # Calculate spreads
        if mexc_spot_bid_price > 0 and gateio_futures_ask_price > 0:
            spreads['mexc_vs_gateio_futures'] = (mexc_spot_bid_price - gateio_futures_ask_price) / mexc_spot_bid_price * 100
        
        if gateio_spot_bid_price > 0 and gateio_futures_ask_price > 0:
            spreads['gateio_spot_vs_futures'] = (gateio_spot_bid_price - gateio_futures_ask_price) / gateio_spot_bid_price * 100
        
        # Calculate execution spreads
        if mexc_spot_ask_price > 0 and mexc_spot_bid_price > 0:
            spreads['MEXC_SPOT:spread'] = (mexc_spot_ask_price - mexc_spot_bid_price) / mexc_spot_ask_price * 100
        
        if gateio_spot_ask_price > 0 and gateio_spot_bid_price > 0:
            spreads['GATEIO_SPOT:spread'] = (gateio_spot_ask_price - gateio_spot_bid_price) / gateio_spot_ask_price * 100
        
        if gateio_futures_ask_price > 0 and gateio_futures_bid_price > 0:
            spreads['GATEIO_FUTURES:spread'] = (gateio_futures_ask_price - gateio_futures_bid_price) / gateio_futures_ask_price * 100
        
        return spreads