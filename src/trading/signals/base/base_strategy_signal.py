"""
Base Strategy Signal Implementation

Common implementation for all strategy signals with shared functionality.
"""

from typing import Dict, Any, Optional, Union, List, Tuple
import pandas as pd
import numpy as np
from collections import deque
from datetime import datetime, timezone
import logging
from dataclasses import dataclass

from .strategy_signal_interface import StrategySignalInterface
from ..types.signal_types import Signal
from ..types.performance_metrics import PerformanceMetrics


@dataclass
class Position:
    """Internal position tracking for strategy signals."""
    entry_time: datetime
    strategy_type: str
    entry_signal: Signal
    entry_data: Dict[str, Any]
    position_size_usd: float
    entry_prices: Dict[str, float]
    unrealized_pnl_usd: float = 0.0
    unrealized_pnl_pct: float = 0.0
    hold_time_minutes: float = 0.0


@dataclass
class Trade:
    """Completed trade tracking for strategy signals."""
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
    fees_usd: float = 0.0


class BaseStrategySignal(StrategySignalInterface):
    """
    Base implementation with common functionality for all strategy signals.
    
    Provides default implementations for common operations like:
    - Data validation
    - Indicator management
    - Performance tracking
    - Risk calculations
    """
    
    def __init__(self, 
                 strategy_type: str,
                 lookback_periods: int = 500,
                 min_history: int = 50,
                 position_size_usd: float = 1000.0,
                 total_fees: float = 0.0025,
                 **params):
        """
        Initialize base strategy signal.
        
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
        
        # Logger
        self.logger = logging.getLogger(f"{self.__class__.__name__}")
        
        # Internal position tracking
        self.open_positions: List[Position] = []
        self.completed_trades: List[Trade] = []
        self.position_counter = 0
    
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
    
    def update_indicators(self, new_data: Union[Dict[str, Any], pd.DataFrame]) -> None:
        """
        Update rolling indicators with new market data.
        
        Args:
            new_data: New market data (single row or snapshot)
        """
        if isinstance(new_data, pd.DataFrame) and not new_data.empty:
            # Handle DataFrame input (last row)
            latest_row = new_data.iloc[-1]
            mexc_spread = latest_row.get('mexc_vs_gateio_futures', 0)
            gateio_spread = latest_row.get('gateio_spot_vs_futures', 0)
        else:
            # Handle dict input
            spreads = self._calculate_spread_from_market_data(new_data)
            mexc_spread = spreads.get('mexc_vs_gateio_futures', 0)
            gateio_spread = spreads.get('gateio_spot_vs_futures', 0)
        
        # Update rolling windows
        if mexc_spread != 0:
            self._update_rolling_statistics(mexc_spread, 'mexc_vs_gateio_futures')
        
        if gateio_spread != 0:
            self._update_rolling_statistics(gateio_spread, 'gateio_spot_vs_futures')
    
    def get_performance_metrics(self) -> PerformanceMetrics:
        """
        Get comprehensive performance metrics for this strategy.
        
        Returns:
            PerformanceMetrics struct with current performance data
        """
        # Create metrics instance
        metrics = PerformanceMetrics(
            strategy_type=self.strategy_type,
            signal_count=self.signal_count,
            last_signal_time=self.last_signal_time,
            total_positions=self.position_counter,
            open_positions=len(self.open_positions),
            completed_trades=len(self.completed_trades)
        )
        
        # Update with trade data
        metrics.update_pnl_metrics(self.completed_trades)
        metrics.update_position_metrics(self.open_positions)
        
        return metrics
    
    def reset_position_tracking(self) -> None:
        """Reset all internal position tracking data."""
        self.open_positions.clear()
        self.completed_trades.clear()
        self.position_counter = 0
        self.signal_count = 0
        self.last_signal_time = None
    
    def open_position(self, signal: Signal, market_data: Dict[str, Any], **params) -> None:
        """
        Open position with internal tracking.
        
        Args:
            signal: Trading signal (should be ENTER)
            market_data: Current market data
            **params: Additional parameters (position_size_usd, etc.)
        """
        position_size_usd = params.get('position_size_usd', self.position_size_usd)
        
        # Calculate entry prices using strategy-specific logic
        entry_prices = self._calculate_entry_prices(market_data)
        
        if not entry_prices:
            self.logger.warning("No valid entry prices calculated - skipping position open")
            return
        
        # Create position
        position = Position(
            entry_time=datetime.now(timezone.utc),
            strategy_type=self.strategy_type,
            entry_signal=signal,
            entry_data=market_data.copy(),
            position_size_usd=position_size_usd,
            entry_prices=entry_prices
        )
        
        # Add to internal tracking
        self.open_positions.append(position)
        self.position_counter += 1
        
        self.logger.info(f"Opened {self.strategy_type} position #{self.position_counter} with entry prices: {entry_prices}")
    
    def close_position(self, signal: Signal, market_data: Dict[str, Any], **params) -> None:
        """
        Close position with internal tracking.
        
        Args:
            signal: Trading signal (should be EXIT)
            market_data: Current market data
            **params: Additional parameters
        """
        if not self.open_positions:
            self.logger.warning("No open positions to close")
            return
        
        # Get the oldest position (FIFO)
        position = self.open_positions.pop(0)
        
        # Calculate exit prices using strategy-specific logic
        exit_prices = self._calculate_exit_prices(market_data)
        
        if not exit_prices:
            self.logger.warning("No valid exit prices calculated - position not closed properly")
            return
        
        # Calculate P&L using strategy-specific logic
        pnl_usd, pnl_pct = self._calculate_pnl(position.entry_prices, exit_prices, position.position_size_usd)
        
        # Calculate hold time
        exit_time = datetime.now(timezone.utc)
        hold_time_minutes = (exit_time - position.entry_time).total_seconds() / 60
        
        # Create completed trade
        trade = Trade(
            entry_time=position.entry_time,
            exit_time=exit_time,
            strategy_type=position.strategy_type,
            entry_signal=position.entry_signal,
            exit_signal=signal,
            position_size_usd=position.position_size_usd,
            entry_prices=position.entry_prices,
            exit_prices=exit_prices,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            hold_time_minutes=hold_time_minutes,
            fees_usd=position.position_size_usd * self.total_fees
        )
        
        # Add to completed trades
        self.completed_trades.append(trade)
        
        self.logger.info(f"Closed {self.strategy_type} position: P&L ${pnl_usd:.2f} ({pnl_pct:.3f}%) in {hold_time_minutes:.1f}min")
    
    def _track_positions_internally(self, df_with_signals: pd.DataFrame) -> None:
        """
        Internal vectorized position tracking for backtesting.
        
        Args:
            df_with_signals: DataFrame with signal column
        """
        # Reset for clean backtesting
        self.reset_position_tracking()
        
        # Process signals sequentially to maintain position state
        for idx, row in df_with_signals.iterrows():
            signal_value = row.get('signal', 'hold')
            
            # Convert string signals to Signal enum
            if isinstance(signal_value, str):
                if signal_value.lower() == 'enter':
                    signal = Signal.ENTER
                elif signal_value.lower() == 'exit':
                    signal = Signal.EXIT
                else:
                    signal = Signal.HOLD
            elif isinstance(signal_value, Signal):
                signal = signal_value
            else:
                continue
            
            # Convert row to dict for market data
            market_data = row.to_dict()
            
            # Process signal
            if signal == Signal.ENTER and len(self.open_positions) == 0:
                self.open_position(signal, market_data)
            elif signal == Signal.EXIT and len(self.open_positions) > 0:
                self.close_position(signal, market_data)
    
    # Abstract methods for strategy-specific implementations
    
    def _calculate_entry_prices(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate entry prices for this strategy.
        
        Should be overridden by specific strategy implementations.
        
        Args:
            market_data: Current market data snapshot
            
        Returns:
            Dictionary of entry prices by exchange/instrument
        """
        # Default implementation - should be overridden
        return {}
    
    def _calculate_exit_prices(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate exit prices for this strategy.
        
        Should be overridden by specific strategy implementations.
        
        Args:
            market_data: Current market data snapshot
            
        Returns:
            Dictionary of exit prices by exchange/instrument
        """
        # Default implementation - should be overridden
        return {}
    
    def _calculate_pnl(self, entry_prices: Dict[str, float], exit_prices: Dict[str, float], position_size_usd: float) -> Tuple[float, float]:
        """
        Calculate P&L for this strategy trade.
        
        Should be overridden by specific strategy implementations.
        
        Args:
            entry_prices: Entry prices by exchange
            exit_prices: Exit prices by exchange
            position_size_usd: Position size in USD
            
        Returns:
            Tuple of (pnl_usd, pnl_pct)
        """
        # Default implementation - should be overridden
        return 0.0, 0.0