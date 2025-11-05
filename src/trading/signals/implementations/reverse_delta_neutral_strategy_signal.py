"""
Reverse Delta Neutral Strategy Signal

Implements the reverse delta neutral arbitrage strategy with hedge optimization.
Captures price discrepancies between MEXC spot and Gate.io futures while hedging
through Gate.io spot positions.
"""

from typing import Dict, Any, Tuple, Union
import pandas as pd
import numpy as np
from datetime import datetime

from trading.strategies.base.base_strategy_signal import BaseStrategySignal
from ..types.signal_types import Signal


class ReverseDeltaNeutralStrategySignal(BaseStrategySignal):
    """
    Reverse delta neutral arbitrage strategy implementation.
    
    Strategy Logic:
    - ENTER: MEXC vs Gate.io futures spread < entry threshold (negative)
    - EXIT: Gate.io spot vs futures spread > exit threshold (positive)
    - Uses hedge ratio optimization for risk management
    """
    
    def __init__(self, 
                 strategy_type: str = 'reverse_delta_neutral',
                 entry_threshold: float = -0.8,
                 exit_threshold: float = 0.3,
                 max_exit_threshold: float = 1.0,
                 min_profit_threshold: float = 0.05,
                 **params):
        """
        Initialize reverse delta neutral strategy.
        
        Args:
            strategy_type: Strategy identifier
            entry_threshold: MEXC vs futures spread threshold for entry (negative)
            exit_threshold: Gate.io spread threshold for exit (positive)
            max_exit_threshold: Maximum exit threshold for opportunity quality
            min_profit_threshold: Minimum profit required for signal generation
            **params: Additional parameters passed to base class
        """
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.max_exit_threshold = max_exit_threshold
        self.min_profit_threshold = min_profit_threshold
        
        super().__init__(
            strategy_type=strategy_type,
            entry_threshold=entry_threshold,
            exit_threshold=exit_threshold,
            max_exit_threshold=max_exit_threshold,
            min_profit_threshold=min_profit_threshold,
            **params
        )
        
        # Strategy-specific indicators
        self.current_position = None
        self.hedge_ratio = 1.0
    
    def generate_live_signal(self, market_data: Dict[str, Any], **params) -> Tuple[Signal, float]:
        """
        Generate live trading signal for reverse delta neutral strategy.
        
        Args:
            market_data: Current market data snapshot
            **params: Override parameters
            
        Returns:
            Tuple of (Signal, confidence_score)
        """
        # Validate market data
        if not self.validate_market_data(market_data):
            return Signal.HOLD, 0.0
        
        # Calculate current spreads
        spreads = self._calculate_spread_from_market_data(market_data)
        
        if not spreads:
            return Signal.HOLD, 0.0
        
        # Get current spread values
        mexc_vs_futures = spreads.get('mexc_vs_gateio_futures', 0)
        gateio_spread = spreads.get('gateio_spot_vs_futures', 0)
        
        # Update rolling indicators
        mexc_stats = self._update_rolling_statistics(mexc_vs_futures, 'mexc_vs_gateio_futures')
        gateio_stats = self._update_rolling_statistics(gateio_spread, 'gateio_spot_vs_futures')
        
        # Check if we have enough history
        if len(self.rolling_windows.get('mexc_vs_gateio_futures', [])) < self.min_history:
            return Signal.HOLD, 0.0
        
        # Override parameters
        entry_thresh = params.get('entry_threshold', self.entry_threshold)
        exit_thresh = params.get('exit_threshold', self.exit_threshold)
        max_exit_thresh = params.get('max_exit_threshold', self.max_exit_threshold)
        min_profit = params.get('min_profit_threshold', self.min_profit_threshold)
        
        # Generate signal
        signal = self._generate_signal_logic(
            mexc_vs_futures, gateio_spread,
            mexc_stats, gateio_stats,
            entry_thresh, exit_thresh, max_exit_thresh, min_profit
        )
        
        # Calculate confidence
        confidence = self.calculate_signal_confidence({
            'mexc_z_score': mexc_stats['z_score'],
            'gateio_z_score': gateio_stats['z_score'],
            'spread_quality': abs(mexc_vs_futures / (mexc_stats['std'] + 1e-8))
        })
        
        # Update tracking
        self.last_signal = signal
        self.last_signal_time = datetime.now()
        self.signal_count += 1
        
        return signal, confidence
    
    def apply_signal_to_backtest(self, df: pd.DataFrame, **params) -> pd.DataFrame:
        """
        Apply strategy signals to historical data for backtesting.
        
        Args:
            df: Historical market data DataFrame with indicators
            **params: Override parameters
            
        Returns:
            DataFrame with added signal columns
        """
        # Ensure we have the required columns
        required_cols = ['mexc_vs_gateio_futures', 'gateio_spot_vs_futures']
        if not all(col in df.columns for col in required_cols):
            # Calculate common indicators first
            df = self._calculate_common_indicators(df)
        
        # Override parameters
        entry_thresh = params.get('entry_threshold', self.entry_threshold)
        exit_thresh = params.get('exit_threshold', self.exit_threshold)
        max_exit_thresh = params.get('max_exit_threshold', self.max_exit_threshold)
        min_profit = params.get('min_profit_threshold', self.min_profit_threshold)
        
        # Initialize signal column
        df['signal'] = Signal.HOLD.value
        df['confidence'] = 0.0
        
        # Vectorized signal generation
        mexc_condition = df['mexc_vs_gateio_futures'] < entry_thresh
        gateio_condition = df['gateio_spot_vs_futures'] > exit_thresh
        
        # Adaptive exit threshold based on opportunity quality
        # Better opportunities (lower MEXC spread) get higher exit tolerance
        adaptive_exit_thresh = np.where(
            df['mexc_vs_gateio_futures'] < entry_thresh * 1.5,  # Very good opportunities
            max_exit_thresh,  # Use higher exit threshold
            exit_thresh  # Use standard exit threshold
        )
        
        gateio_adaptive_condition = df['gateio_spot_vs_futures'] > adaptive_exit_thresh
        
        # Profit validation
        total_spread = df['mexc_vs_gateio_futures'] + df['gateio_spot_vs_futures']
        profit_condition = total_spread > min_profit
        
        # Apply signals
        enter_mask = mexc_condition & profit_condition
        exit_mask = gateio_adaptive_condition & profit_condition
        
        df.loc[enter_mask, 'signal'] = 'enter'
        df.loc[exit_mask, 'signal'] = 'exit'
        
        # Calculate confidence scores
        df['confidence'] = self._calculate_vectorized_confidence(df)
        
        # Run internal position tracking for this backtest
        self._track_positions_internally(df)
        
        return df
    
    def open_position(self, signal: Signal, market_data: Dict[str, Any]) -> None:
        """
        Open position for reverse delta neutral strategy with internal tracking.
        
        Strategy positions:
        - Buy MEXC spot (source)
        - Sell Gate.io futures (hedge)
        - Hold Gate.io spot position for exit
        
        Args:
            signal: Trading signal (should be ENTER)
            market_data: Current market data
        """
        # Internal tracking handled by base class
        # This method is called during backtesting by _internal_open_position
        pass
    
    def close_position(self, signal: Signal, market_data: Dict[str, Any]) -> None:
        """
        Close position for reverse delta neutral strategy with internal tracking.
        
        Closing actions:
        - Sell MEXC spot position
        - Buy back Gate.io futures position
        - Calculate realized P&L
        
        Args:
            signal: Trading signal (should be EXIT)
            market_data: Current market data
        """
        # Internal tracking handled by base class
        # This method is called during backtesting by _internal_close_position
        pass
    
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
    
    def calculate_signal_confidence(self, indicators: Dict[str, float]) -> float:
        """
        Calculate confidence score specific to reverse delta neutral strategy.
        
        Args:
            indicators: Current indicator values
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        confidence = 0.5
        
        # Confidence based on MEXC spread z-score magnitude
        mexc_z = abs(indicators.get('mexc_z_score', 0))
        if mexc_z > 3:
            confidence = 0.95
        elif mexc_z > 2:
            confidence = 0.8
        elif mexc_z > 1:
            confidence = 0.6
        else:
            confidence = 0.3
        
        # Adjust for spread quality
        spread_quality = indicators.get('spread_quality', 0)
        if spread_quality > 2:
            confidence = min(confidence * 1.2, 1.0)
        elif spread_quality < 0.5:
            confidence = confidence * 0.8
        
        return max(min(confidence, 1.0), 0.0)
    
    # Private helper methods
    
    def _generate_signal_logic(self, mexc_spread: float, gateio_spread: float,
                             mexc_stats: Dict[str, float], gateio_stats: Dict[str, float],
                             entry_thresh: float, exit_thresh: float, 
                             max_exit_thresh: float, min_profit: float) -> Signal:
        """
        Core signal generation logic.
        
        Args:
            mexc_spread: Current MEXC vs futures spread
            gateio_spread: Current Gate.io spot vs futures spread
            mexc_stats: MEXC spread statistics
            gateio_stats: Gate.io spread statistics
            entry_thresh: Entry threshold
            exit_thresh: Exit threshold
            max_exit_thresh: Maximum exit threshold
            min_profit: Minimum profit threshold
            
        Returns:
            Generated signal
        """
        # Calculate total profit potential
        total_spread = mexc_spread + gateio_spread
        
        # Check minimum profit requirement
        if total_spread < min_profit:
            return Signal.HOLD
        
        # Entry signal: MEXC spread below threshold (negative)
        if mexc_spread < entry_thresh:
            return Signal.ENTER
        
        # Exit signal: Gate.io spread above threshold (positive)
        # Use adaptive threshold based on opportunity quality
        effective_exit_thresh = max_exit_thresh if mexc_spread < entry_thresh * 1.5 else exit_thresh
        
        if gateio_spread > effective_exit_thresh:
            return Signal.EXIT
        
        return Signal.HOLD
    
    def _calculate_vectorized_confidence(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate confidence scores for entire DataFrame.
        
        Args:
            df: DataFrame with spread data
            
        Returns:
            Series of confidence scores
        """
        # Base confidence
        confidence = pd.Series(0.5, index=df.index)
        
        # Calculate z-scores if available
        if 'mexc_vs_gateio_futures_z_score' in df.columns:
            z_scores = df['mexc_vs_gateio_futures_z_score'].abs()
            confidence = np.where(z_scores > 3, 0.95,
                         np.where(z_scores > 2, 0.8,
                         np.where(z_scores > 1, 0.6, 0.3)))
        
        # Adjust for spread quality
        if 'mexc_vs_gateio_futures_std' in df.columns:
            spread_quality = df['mexc_vs_gateio_futures'].abs() / (df['mexc_vs_gateio_futures_std'] + 1e-8)
            confidence = np.where(spread_quality > 2, confidence * 1.2,
                         np.where(spread_quality < 0.5, confidence * 0.8, confidence))
        
        return pd.Series(confidence, index=df.index).clip(0.0, 1.0)
    
    # Override price calculation methods for strategy-specific logic
    
    def _calculate_entry_prices(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate entry prices for reverse delta neutral strategy.
        
        Strategy-specific entry prices:
        - MEXC: Buy at ask (going long)
        - Gate.io Futures: Sell at bid (going short)
        
        Args:
            market_data: Current market data snapshot
            
        Returns:
            Dictionary of entry prices by exchange/instrument
        """
        entry_prices = {}
        
        # Reverse delta neutral strategy entry prices
        mexc_ask = market_data.get('mexc_ask', market_data.get('MEXC_SPOT_ask_price', 0))
        gateio_futures_bid = market_data.get('gateio_futures_bid', market_data.get('GATEIO_FUTURES_bid_price', 0))
        
        if mexc_ask > 0:
            entry_prices['mexc'] = mexc_ask  # Buy MEXC spot at ask
        if gateio_futures_bid > 0:
            entry_prices['gateio_futures'] = gateio_futures_bid  # Sell Gate.io futures at bid
            
        return entry_prices
    
    def _calculate_exit_prices(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate exit prices for reverse delta neutral strategy.
        
        Strategy-specific exit prices:
        - MEXC: Sell at bid (closing long)
        - Gate.io Futures: Buy at ask (closing short)
        
        Args:
            market_data: Current market data snapshot
            
        Returns:
            Dictionary of exit prices by exchange/instrument
        """
        exit_prices = {}
        
        # Reverse delta neutral strategy exit prices
        mexc_bid = market_data.get('mexc_bid', market_data.get('MEXC_SPOT_bid_price', 0))
        gateio_futures_ask = market_data.get('gateio_futures_ask', market_data.get('GATEIO_FUTURES_ask_price', 0))
        
        if mexc_bid > 0:
            exit_prices['mexc'] = mexc_bid  # Sell MEXC spot at bid
        if gateio_futures_ask > 0:
            exit_prices['gateio_futures'] = gateio_futures_ask  # Buy Gate.io futures at ask
            
        return exit_prices
    
    def _calculate_pnl(self, entry_prices: Dict[str, float], exit_prices: Dict[str, float], position_size_usd: float) -> Tuple[float, float]:
        """
        Calculate P&L for reverse delta neutral strategy trade.
        
        Strategy-specific P&L calculation:
        - MEXC: Long position (buy low, sell high)
        - Gate.io Futures: Short position (sell high, buy low)
        
        Args:
            entry_prices: Entry prices by exchange
            exit_prices: Exit prices by exchange
            position_size_usd: Position size in USD
            
        Returns:
            Tuple of (pnl_usd, pnl_pct)
        """
        # Reverse delta neutral P&L calculation
        mexc_entry = entry_prices.get('mexc', 0)
        mexc_exit = exit_prices.get('mexc', 0)
        gateio_futures_entry = entry_prices.get('gateio_futures', 0)
        gateio_futures_exit = exit_prices.get('gateio_futures', 0)
        
        if not all([mexc_entry, mexc_exit, gateio_futures_entry, gateio_futures_exit]):
            return 0.0, 0.0
        
        # Calculate P&L for each leg
        # MEXC long: profit when exit > entry
        mexc_pnl = (mexc_exit - mexc_entry) / mexc_entry * position_size_usd
        
        # Gate.io futures short: profit when entry > exit
        gateio_futures_pnl = (gateio_futures_entry - gateio_futures_exit) / gateio_futures_entry * position_size_usd
        
        # Total P&L minus fees
        total_pnl_usd = mexc_pnl + gateio_futures_pnl - (position_size_usd * self.total_fees)
        total_pnl_pct = total_pnl_usd / position_size_usd * 100
        
        return total_pnl_usd, total_pnl_pct