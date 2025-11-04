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

from ..base.base_strategy_signal import BaseStrategySignal
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
        
        df.loc[enter_mask, 'signal'] = Signal.ENTER.value
        df.loc[exit_mask, 'signal'] = Signal.EXIT.value
        
        # Calculate confidence scores
        df['confidence'] = self._calculate_vectorized_confidence(df)
        
        return df
    
    def open_position(self, signal: Signal, market_data: Dict[str, Any], **params) -> Dict[str, Any]:
        """
        Calculate position opening details for reverse delta neutral strategy.
        
        Strategy positions:
        - Buy MEXC spot (source)
        - Sell Gate.io futures (hedge)
        - Hold Gate.io spot position for exit
        
        Args:
            signal: Trading signal (should be ENTER)
            market_data: Current market data
            **params: Position parameters
            
        Returns:
            Position details dictionary
        """
        if signal != Signal.ENTER:
            return {}
        
        spreads = self._calculate_spread_from_market_data(market_data)
        position_size = params.get('position_size_usd', self.position_size_usd)
        
        # Extract prices
        mexc_bid = market_data.get('mexc_bid', market_data.get('MEXC_SPOT_bid_price', 0))
        mexc_ask = market_data.get('mexc_ask', market_data.get('MEXC_SPOT_ask_price', 0))
        gateio_futures_bid = market_data.get('gateio_futures_bid', market_data.get('GATEIO_FUTURES_bid_price', 0))
        gateio_futures_ask = market_data.get('gateio_futures_ask', market_data.get('GATEIO_FUTURES_ask_price', 0))
        
        if not all([mexc_ask, gateio_futures_bid]):
            return {}
        
        # Calculate hedge ratio (simplified to 1:1 for now)
        self.hedge_ratio = 1.0
        
        position = {
            'strategy_type': self.strategy_type,
            'signal': signal.value,
            'timestamp': datetime.now(),
            'position_size_usd': position_size,
            'hedge_ratio': self.hedge_ratio,
            
            # Entry prices (what we actually pay/receive)
            'mexc_entry_price': mexc_ask,  # Buy at ask
            'gateio_futures_entry_price': gateio_futures_bid,  # Sell at bid
            
            # Spreads at entry
            'entry_mexc_vs_futures_spread': spreads.get('mexc_vs_gateio_futures', 0),
            'entry_gateio_spread': spreads.get('gateio_spot_vs_futures', 0),
            
            # Position details
            'mexc_position': 'LONG',
            'gateio_futures_position': 'SHORT',
            'expected_profit_bps': spreads.get('mexc_vs_gateio_futures', 0) * 100,
            
            # Risk metrics
            'max_loss_bps': -200,  # 2% max loss
            'target_profit_bps': 50,  # 0.5% target profit
        }
        
        self.current_position = position
        return position
    
    def close_position(self, position: Dict[str, Any], market_data: Dict[str, Any], **params) -> Dict[str, Any]:
        """
        Calculate position closing details and P&L.
        
        Closing actions:
        - Sell MEXC spot position
        - Buy back Gate.io futures position
        - Calculate realized P&L
        
        Args:
            position: Current position details
            market_data: Current market data
            **params: Exit parameters
            
        Returns:
            Trade closure details with P&L
        """
        spreads = self._calculate_spread_from_market_data(market_data)
        
        # Extract current prices
        mexc_bid = market_data.get('mexc_bid', market_data.get('MEXC_SPOT_bid_price', 0))
        mexc_ask = market_data.get('mexc_ask', market_data.get('MEXC_SPOT_ask_price', 0))
        gateio_futures_bid = market_data.get('gateio_futures_bid', market_data.get('GATEIO_FUTURES_bid_price', 0))
        gateio_futures_ask = market_data.get('gateio_futures_ask', market_data.get('GATEIO_FUTURES_ask_price', 0))
        
        if not all([mexc_bid, gateio_futures_ask]):
            return {}
        
        # Exit prices (what we receive/pay when closing)
        mexc_exit_price = mexc_bid  # Sell at bid
        gateio_futures_exit_price = gateio_futures_ask  # Buy at ask
        
        # Calculate P&L components
        mexc_pnl = mexc_exit_price - position['mexc_entry_price']
        gateio_futures_pnl = position['gateio_futures_entry_price'] - gateio_futures_exit_price
        
        # Total P&L per unit
        total_pnl_per_unit = mexc_pnl + gateio_futures_pnl
        
        # Scale to position size
        position_size = position['position_size_usd']
        entry_price = position['mexc_entry_price']
        units = position_size / entry_price if entry_price > 0 else 0
        
        total_pnl_usd = total_pnl_per_unit * units
        
        # Calculate fees
        fees_usd = position_size * self.total_fees
        net_pnl_usd = total_pnl_usd - fees_usd
        
        trade_result = {
            'strategy_type': self.strategy_type,
            'entry_timestamp': position.get('timestamp'),
            'exit_timestamp': datetime.now(),
            'position_size_usd': position_size,
            
            # Entry details
            'mexc_entry_price': position['mexc_entry_price'],
            'gateio_futures_entry_price': position['gateio_futures_entry_price'],
            
            # Exit details
            'mexc_exit_price': mexc_exit_price,
            'gateio_futures_exit_price': gateio_futures_exit_price,
            
            # P&L breakdown
            'mexc_pnl_per_unit': mexc_pnl,
            'gateio_futures_pnl_per_unit': gateio_futures_pnl,
            'total_pnl_per_unit': total_pnl_per_unit,
            'total_pnl_usd': total_pnl_usd,
            'fees_usd': fees_usd,
            'net_pnl_usd': net_pnl_usd,
            'pnl_percentage': (net_pnl_usd / position_size) * 100 if position_size > 0 else 0,
            
            # Spread analysis
            'entry_spread': position.get('entry_mexc_vs_futures_spread', 0),
            'exit_gateio_spread': spreads.get('gateio_spot_vs_futures', 0),
            'spread_capture': position.get('entry_mexc_vs_futures_spread', 0) + spreads.get('gateio_spot_vs_futures', 0),
        }
        
        self.current_position = None
        return trade_result
    
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