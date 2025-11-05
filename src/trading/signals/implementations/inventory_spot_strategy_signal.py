"""
Inventory Spot Strategy Signal

Implements the inventory spot arbitrage strategy with focus on spot market inefficiencies.
Captures opportunities by trading MEXC vs Gate.io spot price differences while maintaining
minimal market exposure.
"""

from typing import Dict, Any, Tuple, Union
import pandas as pd
import numpy as np
from datetime import datetime

from trading.strategies.base.base_strategy_signal import BaseStrategySignal
from ..types.signal_types import Signal


class InventorySpotStrategySignal(BaseStrategySignal):
    """
    Inventory spot arbitrage strategy implementation.
    
    Strategy Logic:
    - ENTER: MEXC vs Gate.io spot spread > entry threshold (positive)  
    - EXIT: Spread normalizes or reverses below exit threshold
    - Focuses on spot-to-spot arbitrage opportunities
    """
    
    def __init__(self, 
                 strategy_type: str = 'inventory_spot',
                 entry_threshold: float = 0.5,
                 exit_threshold: float = 0.1,
                 max_position_time: int = 300,  # 5 minutes max hold
                 inventory_rebalance_threshold: float = 0.2,
                 **params):
        """
        Initialize inventory spot strategy.
        
        Args:
            strategy_type: Strategy identifier
            entry_threshold: Spot spread threshold for entry (positive)
            exit_threshold: Spread threshold for exit (lower positive)
            max_position_time: Maximum position hold time in seconds
            inventory_rebalance_threshold: Threshold for inventory rebalancing
            **params: Additional parameters passed to base class
        """
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.max_position_time = max_position_time
        self.inventory_rebalance_threshold = inventory_rebalance_threshold
        
        super().__init__(
            strategy_type=strategy_type,
            entry_threshold=entry_threshold,
            exit_threshold=exit_threshold,
            max_position_time=max_position_time,
            inventory_rebalance_threshold=inventory_rebalance_threshold,
            **params
        )
        
        # Strategy-specific tracking
        self.mexc_inventory = 0.0
        self.gateio_inventory = 0.0
        self.position_start_time = None
    
    def generate_live_signal(self, market_data: Dict[str, Any], **params) -> Tuple[Signal, float]:
        """
        Generate live trading signal for inventory spot strategy.
        
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
        
        # Calculate MEXC vs Gate.io spot spread
        mexc_bid = market_data.get('mexc_bid', market_data.get('MEXC_SPOT_bid_price', 0))
        mexc_ask = market_data.get('mexc_ask', market_data.get('MEXC_SPOT_ask_price', 0))
        gateio_spot_bid = market_data.get('gateio_spot_bid', market_data.get('GATEIO_SPOT_bid_price', 0))
        gateio_spot_ask = market_data.get('gateio_spot_ask', market_data.get('GATEIO_SPOT_ask_price', 0))
        
        if not all([mexc_bid, mexc_ask, gateio_spot_bid, gateio_spot_ask]):
            return Signal.HOLD, 0.0
        
        # Calculate spot arbitrage spread (MEXC bid vs Gate.io ask)
        spot_spread = (mexc_bid - gateio_spot_ask) / mexc_bid * 100 if mexc_bid > 0 else 0
        
        # Update rolling indicators
        spread_stats = self._update_rolling_statistics(spot_spread, 'mexc_vs_gateio_spot')
        
        # Check if we have enough history
        if len(self.rolling_windows.get('mexc_vs_gateio_spot', [])) < self.min_history:
            return Signal.HOLD, 0.0
        
        # Override parameters
        entry_thresh = params.get('entry_threshold', self.entry_threshold)
        exit_thresh = params.get('exit_threshold', self.exit_threshold)
        
        # Check position time limits
        if self.current_position and self.position_start_time:
            time_held = (datetime.now() - self.position_start_time).total_seconds()
            if time_held > self.max_position_time:
                return Signal.EXIT, 0.8  # Force exit due to time limit
        
        # Generate signal
        signal = self._generate_spot_signal_logic(
            spot_spread, spread_stats, entry_thresh, exit_thresh
        )
        
        # Calculate confidence
        confidence = self.calculate_signal_confidence({
            'spot_z_score': spread_stats['z_score'],
            'spread_magnitude': abs(spot_spread),
            'inventory_balance': self._calculate_inventory_imbalance()
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
        # Calculate spot arbitrage spread
        df['mexc_vs_gateio_spot'] = (
            (df['MEXC_SPOT_bid_price'] - df['GATEIO_SPOT_ask_price']) / 
            df['MEXC_SPOT_bid_price'] * 100
        )
        
        # Calculate rolling statistics
        window = min(self.lookback_periods, len(df))
        df['spot_spread_mean'] = df['mexc_vs_gateio_spot'].rolling(window=window, min_periods=1).mean()
        df['spot_spread_std'] = df['mexc_vs_gateio_spot'].rolling(window=window, min_periods=1).std()
        df['spot_spread_z_score'] = (
            (df['mexc_vs_gateio_spot'] - df['spot_spread_mean']) / 
            (df['spot_spread_std'] + 1e-8)
        )
        
        # Override parameters
        entry_thresh = params.get('entry_threshold', self.entry_threshold)
        exit_thresh = params.get('exit_threshold', self.exit_threshold)
        
        # Initialize signal column
        df['signal'] = Signal.HOLD.value
        df['confidence'] = 0.0
        
        # Vectorized signal generation
        enter_condition = df['mexc_vs_gateio_spot'] > entry_thresh
        exit_condition = df['mexc_vs_gateio_spot'] < exit_thresh
        
        # Apply signals
        df.loc[enter_condition, 'signal'] = Signal.ENTER.value
        df.loc[exit_condition, 'signal'] = Signal.EXIT.value
        
        # Calculate confidence scores
        df['confidence'] = self._calculate_vectorized_confidence(df)
        
        # Add position time tracking
        df = self._add_position_time_tracking(df)
        
        return df
    
    def open_position(self, signal: Signal, market_data: Dict[str, Any]) -> None:
        """
        Open position for inventory spot strategy with internal tracking.
        
        Strategy positions:
        - Sell MEXC spot (higher price)
        - Buy Gate.io spot (lower price)
        - Profit from spread capture
        
        Args:
            signal: Trading signal (should be ENTER)
            market_data: Current market data
        """
        # Internal tracking handled by base class
        # This method is called during backtesting by _internal_open_position
        pass
    
    def close_position(self, signal: Signal, market_data: Dict[str, Any]) -> None:
        """
        Close position for inventory spot strategy with internal tracking.
        
        Closing actions:
        - Buy back MEXC spot position  
        - Sell Gate.io spot position
        - Calculate realized P&L
        
        Args:
            signal: Trading signal (should be EXIT)
            market_data: Current market data
        """
        # Internal tracking handled by base class
        # This method is called during backtesting by _internal_close_position
        pass
    
    # Override price calculation methods for strategy-specific logic
    
    def _calculate_entry_prices(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate entry prices for inventory spot strategy.
        
        Strategy-specific entry prices:
        - MEXC: Sell at bid (going short)
        - Gate.io Spot: Buy at ask (going long)
        
        Args:
            market_data: Current market data snapshot
            
        Returns:
            Dictionary of entry prices by exchange/instrument
        """
        entry_prices = {}
        
        # Inventory spot strategy entry prices
        mexc_bid = market_data.get('mexc_bid', market_data.get('MEXC_SPOT_bid_price', 0))
        gateio_spot_ask = market_data.get('gateio_spot_ask', market_data.get('gateio_ask', market_data.get('GATEIO_SPOT_ask_price', 0)))
        
        if mexc_bid > 0:
            entry_prices['mexc'] = mexc_bid  # Sell MEXC spot at bid
        if gateio_spot_ask > 0:
            entry_prices['gateio_spot'] = gateio_spot_ask  # Buy Gate.io spot at ask
            
        return entry_prices
    
    def _calculate_exit_prices(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate exit prices for inventory spot strategy.
        
        Strategy-specific exit prices:
        - MEXC: Buy at ask (closing short)
        - Gate.io Spot: Sell at bid (closing long)
        
        Args:
            market_data: Current market data snapshot
            
        Returns:
            Dictionary of exit prices by exchange/instrument
        """
        exit_prices = {}
        
        # Inventory spot strategy exit prices
        mexc_ask = market_data.get('mexc_ask', market_data.get('MEXC_SPOT_ask_price', 0))
        gateio_spot_bid = market_data.get('gateio_spot_bid', market_data.get('gateio_bid', market_data.get('GATEIO_SPOT_bid_price', 0)))
        
        if mexc_ask > 0:
            exit_prices['mexc'] = mexc_ask  # Buy MEXC spot at ask
        if gateio_spot_bid > 0:
            exit_prices['gateio_spot'] = gateio_spot_bid  # Sell Gate.io spot at bid
            
        return exit_prices
    
    def _calculate_pnl(self, entry_prices: Dict[str, float], exit_prices: Dict[str, float], position_size_usd: float) -> Tuple[float, float]:
        """
        Calculate P&L for inventory spot strategy trade.
        
        Strategy-specific P&L calculation:
        - MEXC: Short position (sell high, buy low)
        - Gate.io Spot: Long position (buy low, sell high)
        
        Args:
            entry_prices: Entry prices by exchange
            exit_prices: Exit prices by exchange
            position_size_usd: Position size in USD
            
        Returns:
            Tuple of (pnl_usd, pnl_pct)
        """
        # Inventory spot P&L calculation
        mexc_entry = entry_prices.get('mexc', 0)
        mexc_exit = exit_prices.get('mexc', 0)
        gateio_spot_entry = entry_prices.get('gateio_spot', 0)
        gateio_spot_exit = exit_prices.get('gateio_spot', 0)
        
        if not all([mexc_entry, mexc_exit, gateio_spot_entry, gateio_spot_exit]):
            return 0.0, 0.0
        
        # Calculate P&L for each leg
        # MEXC short: profit when exit < entry
        mexc_pnl = (mexc_entry - mexc_exit) / mexc_entry * position_size_usd
        
        # Gate.io spot long: profit when exit > entry
        gateio_spot_pnl = (gateio_spot_exit - gateio_spot_entry) / gateio_spot_entry * position_size_usd
        
        # Total P&L minus fees
        total_pnl_usd = mexc_pnl + gateio_spot_pnl - (position_size_usd * self.total_fees)
        total_pnl_pct = total_pnl_usd / position_size_usd * 100
        
        return total_pnl_usd, total_pnl_pct
    
    def update_indicators(self, new_data: Union[Dict[str, Any], pd.DataFrame]) -> None:
        """
        Update rolling indicators with new market data.
        
        Args:
            new_data: New market data (single row or snapshot)
        """
        if isinstance(new_data, pd.DataFrame) and not new_data.empty:
            # Handle DataFrame input
            latest_row = new_data.iloc[-1]
            mexc_bid = latest_row.get('MEXC_SPOT_bid_price', 0)
            gateio_ask = latest_row.get('GATEIO_SPOT_ask_price', 0)
        else:
            # Handle dict input
            mexc_bid = new_data.get('mexc_bid', new_data.get('MEXC_SPOT_bid_price', 0))
            gateio_ask = new_data.get('gateio_spot_ask', new_data.get('GATEIO_SPOT_ask_price', 0))
        
        # Calculate spot spread
        if mexc_bid > 0 and gateio_ask > 0:
            spot_spread = (mexc_bid - gateio_ask) / mexc_bid * 100
            self._update_rolling_statistics(spot_spread, 'mexc_vs_gateio_spot')
    
    def calculate_signal_confidence(self, indicators: Dict[str, float]) -> float:
        """
        Calculate confidence score specific to inventory spot strategy.
        
        Args:
            indicators: Current indicator values
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        confidence = 0.5
        
        # Confidence based on spot spread z-score
        spot_z = abs(indicators.get('spot_z_score', 0))
        if spot_z > 2:
            confidence = 0.9
        elif spot_z > 1.5:
            confidence = 0.7
        elif spot_z > 1:
            confidence = 0.5
        else:
            confidence = 0.3
        
        # Adjust for spread magnitude
        spread_magnitude = indicators.get('spread_magnitude', 0)
        if spread_magnitude > 1.0:
            confidence = min(confidence * 1.3, 1.0)
        elif spread_magnitude < 0.2:
            confidence = confidence * 0.7
        
        # Adjust for inventory imbalance
        inventory_imbalance = abs(indicators.get('inventory_balance', 0))
        if inventory_imbalance > 0.5:
            confidence = confidence * 0.8  # Reduce confidence if inventory imbalanced
        
        return max(min(confidence, 1.0), 0.0)
    
    # Private helper methods
    
    def _generate_spot_signal_logic(self, spot_spread: float, spread_stats: Dict[str, float],
                                  entry_thresh: float, exit_thresh: float) -> Signal:
        """
        Core signal generation logic for spot arbitrage.
        
        Args:
            spot_spread: Current spot arbitrage spread
            spread_stats: Spread statistics
            entry_thresh: Entry threshold
            exit_thresh: Exit threshold
            
        Returns:
            Generated signal
        """
        # Entry signal: positive spread above threshold
        if spot_spread > entry_thresh:
            return Signal.ENTER
        
        # Exit signal: spread normalizes below exit threshold
        if spot_spread < exit_thresh:
            return Signal.EXIT
        
        return Signal.HOLD
    
    def _calculate_inventory_imbalance(self) -> float:
        """
        Calculate inventory imbalance ratio.
        
        Returns:
            Inventory imbalance (-1 to 1, 0 = balanced)
        """
        total_inventory = abs(self.mexc_inventory) + abs(self.gateio_inventory)
        if total_inventory == 0:
            return 0.0
        
        net_inventory = self.mexc_inventory - self.gateio_inventory
        return net_inventory / total_inventory
    
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
        
        # Confidence based on z-scores
        if 'spot_spread_z_score' in df.columns:
            z_scores = df['spot_spread_z_score'].abs()
            confidence = np.where(z_scores > 2, 0.9,
                         np.where(z_scores > 1.5, 0.7,
                         np.where(z_scores > 1, 0.5, 0.3)))
        
        # Adjust for spread magnitude
        spread_magnitude = df['mexc_vs_gateio_spot'].abs()
        confidence = np.where(spread_magnitude > 1.0, confidence * 1.3,
                     np.where(spread_magnitude < 0.2, confidence * 0.7, confidence))
        
        return pd.Series(confidence, index=df.index).clip(0.0, 1.0)
    
    def _add_position_time_tracking(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add position time tracking for backtesting.
        
        Args:
            df: DataFrame with signals
            
        Returns:
            DataFrame with position time tracking
        """
        # Track position entry/exit times
        df['position_entry'] = (df['signal'] == Signal.ENTER.value).astype(int)
        df['position_exit'] = (df['signal'] == Signal.EXIT.value).astype(int)
        
        # Calculate position duration
        df['position_duration'] = 0
        in_position = False
        entry_idx = 0
        
        for i in range(len(df)):
            if df.iloc[i]['position_entry'] == 1 and not in_position:
                in_position = True
                entry_idx = i
            elif df.iloc[i]['position_exit'] == 1 and in_position:
                in_position = False
                duration = i - entry_idx
                df.iloc[entry_idx:i+1, df.columns.get_loc('position_duration')] = duration
        
        # Force exit if position held too long
        max_duration = self.max_position_time // 300  # Convert to 5-min periods
        long_positions = df['position_duration'] > max_duration
        df.loc[long_positions, 'signal'] = Signal.EXIT.value
        
        return df