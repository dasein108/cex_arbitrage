"""
Base Strategy Signal Implementation with Internal Position Tracking

Common implementation for all strategy signals with integrated position management.
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
from trading.analysis.signal_types import Signal


@dataclass
class Position:
    """Internal position representation for tracking."""
    entry_time: datetime
    strategy_type: str
    entry_signal: Signal
    entry_data: Dict[str, Any]
    position_size_usd: float
    entry_prices: Dict[str, float]  # e.g., {'mexc': 0.054, 'gateio': 0.053}
    unrealized_pnl_usd: float = 0.0
    unrealized_pnl_pct: float = 0.0
    hold_time_minutes: float = 0.0


@dataclass
class Trade:
    """Completed trade representation."""
    entry_time: datetime
    exit_time: datetime
    strategy_type: str
    entry_signal: Signal
    exit_signal: Signal
    position_size_usd: float
    entry_prices: Dict[str, float]
    exit_prices: Dict[str, float]
    pnl_usd: float
    pnl_pct: float
    hold_time_minutes: float
    entry_data: Dict[str, Any] = field(default_factory=dict)
    exit_data: Dict[str, Any] = field(default_factory=dict)


class BaseStrategySignal(StrategySignalInterface):
    """
    Base implementation with internal position tracking for all strategy signals.
    
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
                'MEXC_SPOT_bid_price', 'MEXC_SPOT_ask_price',
                'GATEIO_SPOT_bid_price', 'GATEIO_SPOT_ask_price',
                'GATEIO_FUTURES_bid_price', 'GATEIO_FUTURES_ask_price'
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
    
    def get_strategy_params(self) -> Dict[str, Any]:
        """Get current strategy parameters."""
        return {
            'strategy_type': self.strategy_type,
            'lookback_periods': self.lookback_periods,
            'min_history': self.min_history,
            'position_size_usd': self.position_size_usd,
            'total_fees': self.total_fees,
            **self.params
        }
    
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
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive performance metrics from internal position tracking.
        
        Returns:
            Dictionary containing complete trading performance data
        """
        total_trades = len(self._completed_trades)
        
        if total_trades == 0:
            return {
                'completed_trades': [],
                'total_trades': 0,
                'total_pnl_usd': 0.0,
                'total_pnl_pct': 0.0,
                'win_rate': 0.0,
                'avg_trade_duration': 0.0,
                'current_position': self._get_current_position_dict(),
                'max_drawdown': 0.0,
                'sharpe_ratio': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0
            }
        
        # Calculate basic metrics
        total_pnl_usd = sum(trade.pnl_usd for trade in self._completed_trades)
        total_pnl_pct = sum(trade.pnl_pct for trade in self._completed_trades)
        
        # Win rate calculation
        winning_trades = [t for t in self._completed_trades if t.pnl_usd > 0]
        win_rate = len(winning_trades) / total_trades * 100
        
        # Average trade duration
        avg_duration = sum(trade.hold_time_minutes for trade in self._completed_trades) / total_trades
        
        # Additional metrics
        wins = [t.pnl_usd for t in self._completed_trades if t.pnl_usd > 0]
        losses = [t.pnl_usd for t in self._completed_trades if t.pnl_usd < 0]
        
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
        
        return {
            'completed_trades': [self._trade_to_dict(t) for t in self._completed_trades],
            'total_trades': total_trades,
            'total_pnl_usd': total_pnl_usd,
            'total_pnl_pct': total_pnl_pct,
            'win_rate': win_rate,
            'avg_trade_duration': avg_duration,
            'current_position': self._get_current_position_dict(),
            'max_drawdown': max_drawdown,
            'sharpe_ratio': self._calculate_sharpe_ratio(),
            'avg_win': avg_win,
            'avg_loss': avg_loss
        }
    
    def reset_position_tracking(self) -> None:
        """
        Reset internal position tracking state.
        
        Clears all position history, completed trades, and current positions.
        """
        self._current_position = None
        self._completed_trades.clear()
        self._positions_history.clear()
        self.logger.info(f"Position tracking reset for {self.strategy_type}")
    
    def _track_positions_internally(self, df_with_signals: pd.DataFrame) -> None:
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
            market_data = row.to_dict()
            
            # Convert string signal to Signal enum
            if signal_str == 'enter':
                signal = Signal.ENTER
            elif signal_str == 'exit':
                signal = Signal.EXIT
            else:
                signal = Signal.HOLD
            
            # Process signal
            if signal == Signal.ENTER and self._current_position is None:
                self._internal_open_position(signal, market_data, current_time)
            elif signal == Signal.EXIT and self._current_position is not None:
                self._internal_close_position(signal, market_data, current_time)
    
    def _internal_open_position(self, signal: Signal, market_data: Dict[str, Any], timestamp: datetime) -> None:
        """
        Internal position opening with timestamp tracking.
        
        Args:
            signal: ENTER signal
            market_data: Market data snapshot
            timestamp: Position entry timestamp
        """
        # Calculate entry prices using strategy-specific logic
        entry_prices = self._calculate_entry_prices(market_data)
        
        if not entry_prices:
            self.logger.warning(f"Could not calculate entry prices for {self.strategy_type}")
            return
        
        # Create position
        position = Position(
            entry_time=timestamp,
            strategy_type=self.strategy_type,
            entry_signal=signal,
            entry_data=market_data.copy(),
            position_size_usd=self.position_size_usd,
            entry_prices=entry_prices
        )
        
        self._current_position = position
        self._positions_history.append(position)
        
        self.logger.debug(f"Position opened at {timestamp}: {entry_prices}")
    
    def _internal_close_position(self, signal: Signal, market_data: Dict[str, Any], timestamp: datetime) -> None:
        """
        Internal position closing with P&L calculation.
        
        Args:
            signal: EXIT signal
            market_data: Market data snapshot
            timestamp: Position exit timestamp
        """
        if not self._current_position:
            return
        
        # Calculate exit prices using strategy-specific logic
        exit_prices = self._calculate_exit_prices(market_data)
        
        if not exit_prices:
            self.logger.warning(f"Could not calculate exit prices for {self.strategy_type}")
            return
        
        # Calculate P&L using strategy-specific logic
        pnl_usd, pnl_pct = self._calculate_pnl(
            self._current_position.entry_prices,
            exit_prices,
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
            entry_prices=self._current_position.entry_prices.copy(),
            exit_prices=exit_prices,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            hold_time_minutes=hold_time,
            entry_data=self._current_position.entry_data.copy(),
            exit_data=market_data.copy()
        )
        
        self._completed_trades.append(trade)
        self._current_position = None
        
        self.logger.debug(f"Position closed at {timestamp}: P&L = ${pnl_usd:.2f} ({pnl_pct:.3f}%)")
    
    def _calculate_entry_prices(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate entry prices from market data.
        
        Default implementation - should be overridden by specific strategies.
        
        Args:
            market_data: Current market data snapshot
            
        Returns:
            Dictionary of entry prices by exchange/instrument
        """
        entry_prices = {}
        
        # Extract standard price fields with fallbacks
        mexc_ask = market_data.get('mexc_ask', market_data.get('MEXC_SPOT_ask_price', 0))
        gateio_bid = market_data.get('gateio_bid', market_data.get('GATEIO_SPOT_bid_price', 0))
        
        if mexc_ask > 0:
            entry_prices['mexc'] = mexc_ask
        if gateio_bid > 0:
            entry_prices['gateio'] = gateio_bid
            
        return entry_prices
    
    def _calculate_exit_prices(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate exit prices from market data.
        
        Default implementation - should be overridden by specific strategies.
        
        Args:
            market_data: Current market data snapshot
            
        Returns:
            Dictionary of exit prices by exchange/instrument
        """
        exit_prices = {}
        
        # Extract standard price fields with fallbacks
        mexc_bid = market_data.get('mexc_bid', market_data.get('MEXC_SPOT_bid_price', 0))
        gateio_ask = market_data.get('gateio_ask', market_data.get('GATEIO_SPOT_ask_price', 0))
        
        if mexc_bid > 0:
            exit_prices['mexc'] = mexc_bid
        if gateio_ask > 0:
            exit_prices['gateio'] = gateio_ask
            
        return exit_prices
    
    def _calculate_pnl(self, entry_prices: Dict[str, float], exit_prices: Dict[str, float], position_size_usd: float) -> Tuple[float, float]:
        """
        Calculate P&L for the trade.
        
        Default implementation for cross-exchange arbitrage.
        Should be overridden by specific strategies.
        
        Args:
            entry_prices: Entry prices by exchange
            exit_prices: Exit prices by exchange
            position_size_usd: Position size in USD
            
        Returns:
            Tuple of (pnl_usd, pnl_pct)
        """
        # Default cross-exchange arbitrage P&L calculation
        mexc_entry = entry_prices.get('mexc', 0)
        mexc_exit = exit_prices.get('mexc', 0)
        gateio_entry = entry_prices.get('gateio', 0)
        gateio_exit = exit_prices.get('gateio', 0)
        
        if not all([mexc_entry, mexc_exit, gateio_entry, gateio_exit]):
            return 0.0, 0.0
        
        # Calculate P&L for each leg
        mexc_pnl = (mexc_exit - mexc_entry) / mexc_entry * position_size_usd
        gateio_pnl = (gateio_entry - gateio_exit) / gateio_entry * position_size_usd
        
        # Total P&L minus fees
        total_pnl_usd = mexc_pnl + gateio_pnl - (position_size_usd * self.total_fees)
        total_pnl_pct = total_pnl_usd / position_size_usd * 100
        
        return total_pnl_usd, total_pnl_pct
    
    def _get_current_position_dict(self) -> Optional[Dict[str, Any]]:
        """
        Get current position as dictionary.
        
        Returns:
            Position dictionary or None if no current position
        """
        if not self._current_position:
            return None
        
        return {
            'entry_time': self._current_position.entry_time.isoformat(),
            'strategy_type': self._current_position.strategy_type,
            'entry_signal': self._current_position.entry_signal.value,
            'position_size_usd': self._current_position.position_size_usd,
            'entry_prices': self._current_position.entry_prices.copy(),
            'unrealized_pnl_usd': self._current_position.unrealized_pnl_usd,
            'unrealized_pnl_pct': self._current_position.unrealized_pnl_pct,
            'hold_time_minutes': self._current_position.hold_time_minutes
        }
    
    def _trade_to_dict(self, trade: Trade) -> Dict[str, Any]:
        """
        Convert Trade object to dictionary.
        
        Args:
            trade: Trade object
            
        Returns:
            Trade dictionary
        """
        return {
            'entry_time': trade.entry_time.isoformat(),
            'exit_time': trade.exit_time.isoformat(),
            'strategy_type': trade.strategy_type,
            'entry_signal': trade.entry_signal.value,
            'exit_signal': trade.exit_signal.value,
            'position_size_usd': trade.position_size_usd,
            'entry_prices': trade.entry_prices.copy(),
            'exit_prices': trade.exit_prices.copy(),
            'pnl_usd': trade.pnl_usd,
            'pnl_pct': trade.pnl_pct,
            'hold_time_minutes': trade.hold_time_minutes
        }
    
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
        df['mexc_spread'] = (df['MEXC_SPOT_ask_price'] - df['MEXC_SPOT_bid_price']) / df['MEXC_SPOT_ask_price'] * 100
        df['gateio_spot_spread'] = (df['GATEIO_SPOT_ask_price'] - df['GATEIO_SPOT_bid_price']) / df['GATEIO_SPOT_ask_price'] * 100
        df['gateio_futures_spread'] = (df['GATEIO_FUTURES_ask_price'] - df['GATEIO_FUTURES_bid_price']) / df['GATEIO_FUTURES_ask_price'] * 100
        
        # Calculate cross-exchange spreads
        df['mexc_vs_gateio_futures'] = (
            (df['MEXC_SPOT_bid_price'] - df['GATEIO_FUTURES_ask_price']) / 
            df['MEXC_SPOT_bid_price'] * 100
        )
        
        df['gateio_spot_vs_futures'] = (
            (df['GATEIO_SPOT_bid_price'] - df['GATEIO_FUTURES_ask_price']) / 
            df['GATEIO_SPOT_bid_price'] * 100
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
        
        # Extract prices with fallbacks
        mexc_bid = market_data.get('mexc_bid', market_data.get('MEXC_SPOT_bid_price', 0))
        mexc_ask = market_data.get('mexc_ask', market_data.get('MEXC_SPOT_ask_price', 0))
        gateio_spot_bid = market_data.get('gateio_spot_bid', market_data.get('GATEIO_SPOT_bid_price', 0))
        gateio_spot_ask = market_data.get('gateio_spot_ask', market_data.get('GATEIO_SPOT_ask_price', 0))
        gateio_futures_bid = market_data.get('gateio_futures_bid', market_data.get('GATEIO_FUTURES_bid_price', 0))
        gateio_futures_ask = market_data.get('gateio_futures_ask', market_data.get('GATEIO_FUTURES_ask_price', 0))
        
        # Calculate spreads
        if mexc_bid > 0 and gateio_futures_ask > 0:
            spreads['mexc_vs_gateio_futures'] = (mexc_bid - gateio_futures_ask) / mexc_bid * 100
        
        if gateio_spot_bid > 0 and gateio_futures_ask > 0:
            spreads['gateio_spot_vs_futures'] = (gateio_spot_bid - gateio_futures_ask) / gateio_spot_bid * 100
        
        # Calculate execution spreads
        if mexc_ask > 0 and mexc_bid > 0:
            spreads['mexc_spread'] = (mexc_ask - mexc_bid) / mexc_ask * 100
        
        if gateio_spot_ask > 0 and gateio_spot_bid > 0:
            spreads['gateio_spot_spread'] = (gateio_spot_ask - gateio_spot_bid) / gateio_spot_ask * 100
        
        if gateio_futures_ask > 0 and gateio_futures_bid > 0:
            spreads['gateio_futures_spread'] = (gateio_futures_ask - gateio_futures_bid) / gateio_futures_ask * 100
        
        return spreads
    
    # Default implementations of new interface methods
    # These should be overridden by specific strategy implementations
    
    def open_position(self, signal: Signal, market_data: Dict[str, Any]) -> None:
        """
        Default open_position implementation.
        
        This should be overridden by specific strategy implementations.
        """
        if signal != Signal.ENTER:
            return
            
        timestamp = datetime.now(timezone.utc)
        self._internal_open_position(signal, market_data, timestamp)
    
    def close_position(self, signal: Signal, market_data: Dict[str, Any]) -> None:
        """
        Default close_position implementation.
        
        This should be overridden by specific strategy implementations.
        """
        if signal != Signal.EXIT:
            return
            
        timestamp = datetime.now(timezone.utc)
        self._internal_close_position(signal, market_data, timestamp)