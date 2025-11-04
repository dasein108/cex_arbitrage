"""
Volatility Harvesting Strategy Signal

Implements volatility harvesting strategy that captures profits from market volatility
through dynamic spread trading and mean reversion patterns.
"""

from typing import Dict, Any, Tuple, Union
import pandas as pd
import numpy as np
from datetime import datetime

from ..base.base_strategy_signal import BaseStrategySignal
from ..types.signal_types import Signal


class VolatilityHarvestingStrategySignal(BaseStrategySignal):
    """
    Volatility harvesting strategy implementation.
    
    Strategy Logic:
    - ENTER: High volatility periods with mean reversion potential
    - EXIT: Volatility subsides or profit targets reached
    - Focuses on capturing profits from price oscillations
    """
    
    def __init__(self, 
                 strategy_type: str = 'volatility_harvesting',
                 volatility_threshold: float = 2.0,
                 mean_reversion_threshold: float = 1.5,
                 profit_target_pct: float = 0.3,
                 volatility_window: int = 20,
                 **params):
        """
        Initialize volatility harvesting strategy.
        
        Args:
            strategy_type: Strategy identifier
            volatility_threshold: Volatility z-score threshold for entry
            mean_reversion_threshold: Mean reversion signal threshold
            profit_target_pct: Target profit percentage
            volatility_window: Window for volatility calculations
            **params: Additional parameters passed to base class
        """
        self.volatility_threshold = volatility_threshold
        self.mean_reversion_threshold = mean_reversion_threshold
        self.profit_target_pct = profit_target_pct
        self.volatility_window = volatility_window
        
        super().__init__(
            strategy_type=strategy_type,
            volatility_threshold=volatility_threshold,
            mean_reversion_threshold=mean_reversion_threshold,
            profit_target_pct=profit_target_pct,
            volatility_window=volatility_window,
            **params
        )
        
        # Strategy-specific indicators
        self.volatility_indicators = {}
        self.volatility_history = []
        self.spread_history = []
    
    def generate_live_signal(self, market_data: Dict[str, Any], **params) -> Tuple[Signal, float]:
        """
        Generate live trading signal for volatility harvesting strategy.
        
        Args:
            market_data: Current market data snapshot
            **params: Override parameters
            
        Returns:
            Tuple of (Signal, confidence_score)
        """
        # Validate market data
        if not self.validate_market_data(market_data):
            return Signal.HOLD, 0.0
        
        # Calculate current spreads and volatility
        spreads = self._calculate_spread_from_market_data(market_data)
        volatility_metrics = self._calculate_volatility_metrics(spreads)
        
        if not spreads or not volatility_metrics:
            return Signal.HOLD, 0.0
        
        # Update indicators
        self._update_volatility_indicators(volatility_metrics)
        
        # Check if we have enough history
        if len(self.volatility_history) < self.min_history:
            return Signal.HOLD, 0.0
        
        # Override parameters
        vol_thresh = params.get('volatility_threshold', self.volatility_threshold)
        mean_rev_thresh = params.get('mean_reversion_threshold', self.mean_reversion_threshold)
        
        # Generate signal
        signal = self._generate_volatility_signal_logic(
            volatility_metrics, vol_thresh, mean_rev_thresh
        )
        
        # Calculate confidence
        confidence = self.calculate_signal_confidence({
            'volatility_z_score': volatility_metrics.get('volatility_z_score', 0),
            'mean_reversion_strength': volatility_metrics.get('mean_reversion_strength', 0),
            'spread_momentum': volatility_metrics.get('spread_momentum', 0)
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
        # Ensure we have required spread columns
        if 'mexc_vs_gateio_futures' not in df.columns:
            df = self._calculate_common_indicators(df)
        
        # Calculate volatility indicators
        df = self._calculate_volatility_indicators_vectorized(df)
        
        # Override parameters
        vol_thresh = params.get('volatility_threshold', self.volatility_threshold)
        mean_rev_thresh = params.get('mean_reversion_threshold', self.mean_reversion_threshold)
        profit_target = params.get('profit_target_pct', self.profit_target_pct)
        
        # Initialize signal column
        df['signal'] = Signal.HOLD.value
        df['confidence'] = 0.0
        
        # Vectorized signal generation
        high_volatility = df['volatility_z_score'] > vol_thresh
        mean_reversion = df['mean_reversion_signal'] > mean_rev_thresh
        profit_opportunity = df['estimated_profit'] > profit_target
        
        # Entry conditions
        enter_condition = high_volatility & mean_reversion & profit_opportunity
        
        # Exit conditions (volatility subsides or profit taken)
        exit_condition = (
            (df['volatility_z_score'] < vol_thresh * 0.5) |
            (df['profit_reached'] > profit_target)
        )
        
        # Apply signals
        df.loc[enter_condition, 'signal'] = Signal.ENTER.value
        df.loc[exit_condition, 'signal'] = Signal.EXIT.value
        
        # Calculate confidence scores
        df['confidence'] = self._calculate_vectorized_confidence(df)
        
        return df
    
    def open_position(self, signal: Signal, market_data: Dict[str, Any], **params) -> Dict[str, Any]:
        """
        Calculate position opening details for volatility harvesting strategy.
        
        Strategy positions:
        - Dynamic position based on volatility direction
        - Can be long or short depending on mean reversion signal
        
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
        volatility_metrics = self._calculate_volatility_metrics(spreads)
        position_size = params.get('position_size_usd', self.position_size_usd)
        
        # Determine position direction based on mean reversion signal
        mean_reversion_signal = volatility_metrics.get('mean_reversion_direction', 0)
        
        # Extract prices
        mexc_bid = market_data.get('mexc_bid', market_data.get('MEXC_SPOT_bid_price', 0))
        mexc_ask = market_data.get('mexc_ask', market_data.get('MEXC_SPOT_ask_price', 0))
        gateio_spot_bid = market_data.get('gateio_spot_bid', market_data.get('GATEIO_SPOT_bid_price', 0))
        gateio_spot_ask = market_data.get('gateio_spot_ask', market_data.get('GATEIO_SPOT_ask_price', 0))
        gateio_futures_bid = market_data.get('gateio_futures_bid', market_data.get('GATEIO_FUTURES_bid_price', 0))
        gateio_futures_ask = market_data.get('gateio_futures_ask', market_data.get('GATEIO_FUTURES_ask_price', 0))
        
        if not all([mexc_bid, mexc_ask, gateio_futures_bid, gateio_futures_ask]):
            return {}
        
        # Dynamic position sizing based on volatility
        volatility_multiplier = min(2.0, volatility_metrics.get('volatility_z_score', 1.0))
        adjusted_position_size = position_size * volatility_multiplier
        
        position = {
            'strategy_type': self.strategy_type,
            'signal': signal.value,
            'timestamp': datetime.now(),
            'position_size_usd': adjusted_position_size,
            'volatility_multiplier': volatility_multiplier,
            
            # Entry prices (depends on direction)
            'mexc_entry_price': mexc_ask if mean_reversion_signal > 0 else mexc_bid,
            'gateio_futures_entry_price': gateio_futures_bid if mean_reversion_signal > 0 else gateio_futures_ask,
            
            # Position direction
            'position_direction': 'LONG' if mean_reversion_signal > 0 else 'SHORT',
            'mean_reversion_signal': mean_reversion_signal,
            
            # Volatility metrics at entry
            'entry_volatility': volatility_metrics.get('current_volatility', 0),
            'volatility_z_score': volatility_metrics.get('volatility_z_score', 0),
            'mean_reversion_strength': volatility_metrics.get('mean_reversion_strength', 0),
            
            # Risk metrics
            'profit_target': self.profit_target_pct,
            'max_loss_bps': -150,  # 1.5% max loss
            'target_profit_bps': self.profit_target_pct * 100,
        }
        
        self.current_position = position
        return position
    
    def close_position(self, position: Dict[str, Any], market_data: Dict[str, Any], **params) -> Dict[str, Any]:
        """
        Calculate position closing details and P&L.
        
        Args:
            position: Current position details
            market_data: Current market data
            **params: Exit parameters
            
        Returns:
            Trade closure details with P&L
        """
        spreads = self._calculate_spread_from_market_data(market_data)
        volatility_metrics = self._calculate_volatility_metrics(spreads)
        
        # Extract current prices
        mexc_bid = market_data.get('mexc_bid', market_data.get('MEXC_SPOT_bid_price', 0))
        mexc_ask = market_data.get('mexc_ask', market_data.get('MEXC_SPOT_ask_price', 0))
        gateio_futures_bid = market_data.get('gateio_futures_bid', market_data.get('GATEIO_FUTURES_bid_price', 0))
        gateio_futures_ask = market_data.get('gateio_futures_ask', market_data.get('GATEIO_FUTURES_ask_price', 0))
        
        if not all([mexc_bid, mexc_ask, gateio_futures_bid, gateio_futures_ask]):
            return {}
        
        # Determine exit prices based on original position direction
        position_direction = position.get('position_direction', 'LONG')
        
        if position_direction == 'LONG':
            mexc_exit_price = mexc_bid  # Sell at bid
            gateio_futures_exit_price = gateio_futures_ask  # Buy at ask
        else:
            mexc_exit_price = mexc_ask  # Buy at ask
            gateio_futures_exit_price = gateio_futures_bid  # Sell at bid
        
        # Calculate P&L based on position direction
        mexc_entry = position['mexc_entry_price']
        gateio_entry = position['gateio_futures_entry_price']
        
        if position_direction == 'LONG':
            mexc_pnl = mexc_exit_price - mexc_entry
            gateio_pnl = gateio_entry - gateio_futures_exit_price
        else:
            mexc_pnl = mexc_entry - mexc_exit_price
            gateio_pnl = gateio_futures_exit_price - gateio_entry
        
        # Total P&L per unit
        total_pnl_per_unit = mexc_pnl + gateio_pnl
        
        # Scale to position size
        position_size = position['position_size_usd']
        entry_price = mexc_entry
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
            'position_direction': position_direction,
            
            # Entry details
            'mexc_entry_price': mexc_entry,
            'gateio_futures_entry_price': gateio_entry,
            
            # Exit details
            'mexc_exit_price': mexc_exit_price,
            'gateio_futures_exit_price': gateio_futures_exit_price,
            
            # P&L breakdown
            'mexc_pnl_per_unit': mexc_pnl,
            'gateio_futures_pnl_per_unit': gateio_pnl,
            'total_pnl_per_unit': total_pnl_per_unit,
            'total_pnl_usd': total_pnl_usd,
            'fees_usd': fees_usd,
            'net_pnl_usd': net_pnl_usd,
            'pnl_percentage': (net_pnl_usd / position_size) * 100 if position_size > 0 else 0,
            
            # Volatility analysis
            'entry_volatility': position.get('entry_volatility', 0),
            'exit_volatility': volatility_metrics.get('current_volatility', 0),
            'volatility_change': volatility_metrics.get('current_volatility', 0) - position.get('entry_volatility', 0),
            'volatility_z_score_change': volatility_metrics.get('volatility_z_score', 0) - position.get('volatility_z_score', 0),
        }
        
        self.current_position = None
        return trade_result
    
    def update_indicators(self, new_data: Union[Dict[str, Any], pd.DataFrame]) -> None:
        """
        Update rolling indicators with new market data.
        
        Args:
            new_data: New market data (single row or snapshot)
        """
        # Calculate spreads and volatility
        if isinstance(new_data, pd.DataFrame) and not new_data.empty:
            spreads = self._calculate_spread_from_market_data(new_data.iloc[-1].to_dict())
        else:
            spreads = self._calculate_spread_from_market_data(new_data)
        
        if spreads:
            volatility_metrics = self._calculate_volatility_metrics(spreads)
            self._update_volatility_indicators(volatility_metrics)
    
    def calculate_signal_confidence(self, indicators: Dict[str, float]) -> float:
        """
        Calculate confidence score specific to volatility harvesting strategy.
        
        Args:
            indicators: Current indicator values
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        confidence = 0.5
        
        # Confidence based on volatility z-score
        vol_z = abs(indicators.get('volatility_z_score', 0))
        if vol_z > 3:
            confidence = 0.95
        elif vol_z > 2:
            confidence = 0.8
        elif vol_z > 1.5:
            confidence = 0.6
        else:
            confidence = 0.3
        
        # Adjust for mean reversion strength
        mean_rev_strength = indicators.get('mean_reversion_strength', 0)
        if mean_rev_strength > 2:
            confidence = min(confidence * 1.3, 1.0)
        elif mean_rev_strength < 1:
            confidence = confidence * 0.8
        
        # Adjust for spread momentum
        momentum = abs(indicators.get('spread_momentum', 0))
        if momentum > 1.5:
            confidence = min(confidence * 1.1, 1.0)
        
        return max(min(confidence, 1.0), 0.0)
    
    # Private helper methods
    
    def _calculate_volatility_metrics(self, spreads: Dict[str, float]) -> Dict[str, float]:
        """
        Calculate volatility-related metrics.
        
        Args:
            spreads: Current spread values
            
        Returns:
            Dictionary of volatility metrics
        """
        # Get main spread
        main_spread = spreads.get('mexc_vs_gateio_futures', 0)
        
        # Update spread history
        self.spread_history.append(main_spread)
        if len(self.spread_history) > self.lookback_periods:
            self.spread_history.pop(0)
        
        if len(self.spread_history) < self.volatility_window:
            return {}
        
        # Calculate volatility
        recent_spreads = self.spread_history[-self.volatility_window:]
        volatility = np.std(recent_spreads)
        mean_spread = np.mean(recent_spreads)
        
        # Update volatility history
        self.volatility_history.append(volatility)
        if len(self.volatility_history) > self.lookback_periods:
            self.volatility_history.pop(0)
        
        if len(self.volatility_history) < self.min_history:
            return {}
        
        # Calculate volatility z-score
        vol_mean = np.mean(self.volatility_history)
        vol_std = np.std(self.volatility_history)
        vol_z_score = (volatility - vol_mean) / (vol_std + 1e-8)
        
        # Calculate mean reversion signal
        current_deviation = main_spread - mean_spread
        mean_reversion_strength = abs(current_deviation) / (volatility + 1e-8)
        mean_reversion_direction = -np.sign(current_deviation)  # Revert to mean
        
        # Calculate momentum
        if len(recent_spreads) >= 5:
            momentum = (recent_spreads[-1] - recent_spreads[-5]) / (volatility + 1e-8)
        else:
            momentum = 0
        
        return {
            'current_volatility': volatility,
            'volatility_z_score': vol_z_score,
            'mean_reversion_strength': mean_reversion_strength,
            'mean_reversion_direction': mean_reversion_direction,
            'spread_momentum': momentum,
            'spread_deviation': current_deviation
        }
    
    def _update_volatility_indicators(self, volatility_metrics: Dict[str, float]) -> None:
        """
        Update volatility indicator storage.
        
        Args:
            volatility_metrics: New volatility metrics
        """
        self.volatility_indicators.update(volatility_metrics)
    
    def _generate_volatility_signal_logic(self, volatility_metrics: Dict[str, float],
                                        vol_thresh: float, mean_rev_thresh: float) -> Signal:
        """
        Core signal generation logic for volatility harvesting.
        
        Args:
            volatility_metrics: Current volatility metrics
            vol_thresh: Volatility threshold
            mean_rev_thresh: Mean reversion threshold
            
        Returns:
            Generated signal
        """
        vol_z_score = volatility_metrics.get('volatility_z_score', 0)
        mean_rev_strength = volatility_metrics.get('mean_reversion_strength', 0)
        
        # Entry: High volatility + strong mean reversion signal
        if vol_z_score > vol_thresh and mean_rev_strength > mean_rev_thresh:
            return Signal.ENTER
        
        # Exit: Volatility subsides
        if vol_z_score < vol_thresh * 0.5:
            return Signal.EXIT
        
        return Signal.HOLD
    
    def _calculate_volatility_indicators_vectorized(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate volatility indicators for entire DataFrame.
        
        Args:
            df: DataFrame with spread data
            
        Returns:
            DataFrame with added volatility indicators
        """
        # Calculate rolling volatility
        vol_window = min(self.volatility_window, len(df))
        df['spread_volatility'] = df['mexc_vs_gateio_futures'].rolling(window=vol_window).std()
        df['spread_mean'] = df['mexc_vs_gateio_futures'].rolling(window=vol_window).mean()
        
        # Calculate volatility z-score
        lookback = min(self.lookback_periods, len(df))
        df['volatility_mean'] = df['spread_volatility'].rolling(window=lookback).mean()
        df['volatility_std'] = df['spread_volatility'].rolling(window=lookback).std()
        df['volatility_z_score'] = (
            (df['spread_volatility'] - df['volatility_mean']) / 
            (df['volatility_std'] + 1e-8)
        )
        
        # Calculate mean reversion signal
        df['spread_deviation'] = df['mexc_vs_gateio_futures'] - df['spread_mean']
        df['mean_reversion_signal'] = (
            df['spread_deviation'].abs() / (df['spread_volatility'] + 1e-8)
        )
        
        # Calculate momentum
        df['spread_momentum'] = (
            (df['mexc_vs_gateio_futures'] - df['mexc_vs_gateio_futures'].shift(5)) / 
            (df['spread_volatility'] + 1e-8)
        )
        
        # Estimate profit opportunity
        df['estimated_profit'] = df['mean_reversion_signal'] * df['spread_volatility']
        df['profit_reached'] = df['estimated_profit']
        
        return df
    
    def _calculate_vectorized_confidence(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate confidence scores for entire DataFrame.
        
        Args:
            df: DataFrame with volatility data
            
        Returns:
            Series of confidence scores
        """
        # Base confidence
        confidence = pd.Series(0.5, index=df.index)
        
        # Confidence based on volatility z-score
        if 'volatility_z_score' in df.columns:
            vol_z = df['volatility_z_score'].abs()
            confidence = np.where(vol_z > 3, 0.95,
                         np.where(vol_z > 2, 0.8,
                         np.where(vol_z > 1.5, 0.6, 0.3)))
        
        # Adjust for mean reversion strength
        if 'mean_reversion_signal' in df.columns:
            mean_rev = df['mean_reversion_signal']
            confidence = np.where(mean_rev > 2, confidence * 1.3,
                         np.where(mean_rev < 1, confidence * 0.8, confidence))
        
        # Adjust for momentum
        if 'spread_momentum' in df.columns:
            momentum = df['spread_momentum'].abs()
            confidence = np.where(momentum > 1.5, confidence * 1.1, confidence)
        
        return pd.Series(confidence, index=df.index).clip(0.0, 1.0)