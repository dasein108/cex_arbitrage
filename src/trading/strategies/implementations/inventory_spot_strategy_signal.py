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
from trading.analysis.signal_types import Signal


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
    
    def open_position(self, signal: Signal, market_data: Dict[str, Any], **params) -> Dict[str, Any]:
        """
        Calculate position opening details for inventory spot strategy.
        
        Strategy positions:
        - Sell MEXC spot (higher price)
        - Buy Gate.io spot (lower price)
        - Profit from spread capture
        
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
        gateio_spot_bid = market_data.get('gateio_spot_bid', market_data.get('GATEIO_SPOT_bid_price', 0))
        gateio_spot_ask = market_data.get('gateio_spot_ask', market_data.get('GATEIO_SPOT_ask_price', 0))
        
        if not all([mexc_bid, gateio_spot_ask]):
            return {}
        
        # Calculate spot arbitrage spread
        spot_spread = (mexc_bid - gateio_spot_ask) / mexc_bid * 100
        
        position = {
            'strategy_type': self.strategy_type,
            'signal': signal.value,
            'timestamp': datetime.now(),
            'position_size_usd': position_size,
            
            # Entry prices
            'mexc_entry_price': mexc_bid,  # Sell at bid
            'gateio_entry_price': gateio_spot_ask,  # Buy at ask
            
            # Spreads at entry
            'entry_spot_spread': spot_spread,
            'mexc_spread': spreads.get('mexc_spread', 0),
            'gateio_spread': spreads.get('gateio_spot_spread', 0),
            
            # Position details
            'mexc_position': 'SHORT',
            'gateio_position': 'LONG',
            'expected_profit_bps': spot_spread * 100,
            
            # Risk metrics
            'max_loss_bps': -100,  # 1% max loss
            'target_profit_bps': 25,  # 0.25% target profit
        }
        
        # Update inventory tracking
        units = position_size / mexc_bid if mexc_bid > 0 else 0
        self.mexc_inventory -= units  # Short position
        self.gateio_inventory += units  # Long position
        
        self.current_position = position
        self.position_start_time = datetime.now()
        return position
    
    def close_position(self, position: Dict[str, Any], market_data: Dict[str, Any], **params) -> Dict[str, Any]:
        """
        Calculate position closing details and P&L.
        
        Closing actions:
        - Buy back MEXC spot position  
        - Sell Gate.io spot position
        - Calculate realized P&L
        
        Args:
            position: Current position details
            market_data: Current market data
            **params: Exit parameters
            
        Returns:
            Trade closure details with P&L
        """
        # Extract current prices
        mexc_bid = market_data.get('mexc_bid', market_data.get('MEXC_SPOT_bid_price', 0))
        mexc_ask = market_data.get('mexc_ask', market_data.get('MEXC_SPOT_ask_price', 0))
        gateio_spot_bid = market_data.get('gateio_spot_bid', market_data.get('GATEIO_SPOT_bid_price', 0))
        gateio_spot_ask = market_data.get('gateio_spot_ask', market_data.get('GATEIO_SPOT_ask_price', 0))
        
        if not all([mexc_ask, gateio_spot_bid]):
            return {}
        
        # Exit prices (reverse of entry)
        mexc_exit_price = mexc_ask  # Buy at ask to close short
        gateio_exit_price = gateio_spot_bid  # Sell at bid to close long
        
        # Calculate P&L components
        mexc_pnl = position['mexc_entry_price'] - mexc_exit_price  # Short position P&L
        gateio_pnl = gateio_exit_price - position['gateio_entry_price']  # Long position P&L
        
        # Total P&L per unit
        total_pnl_per_unit = mexc_pnl + gateio_pnl
        
        # Scale to position size
        position_size = position['position_size_usd']
        entry_price = position['mexc_entry_price']
        units = position_size / entry_price if entry_price > 0 else 0
        
        total_pnl_usd = total_pnl_per_unit * units
        
        # Calculate fees
        fees_usd = position_size * self.total_fees
        net_pnl_usd = total_pnl_usd - fees_usd
        
        # Calculate current spot spread
        current_spot_spread = (mexc_bid - gateio_spot_ask) / mexc_bid * 100 if mexc_bid > 0 else 0
        
        trade_result = {
            'strategy_type': self.strategy_type,
            'entry_timestamp': position.get('timestamp'),
            'exit_timestamp': datetime.now(),
            'position_size_usd': position_size,
            'hold_time_seconds': (datetime.now() - position.get('timestamp')).total_seconds(),
            
            # Entry details
            'mexc_entry_price': position['mexc_entry_price'],
            'gateio_entry_price': position['gateio_entry_price'],
            
            # Exit details
            'mexc_exit_price': mexc_exit_price,
            'gateio_exit_price': gateio_exit_price,
            
            # P&L breakdown
            'mexc_pnl_per_unit': mexc_pnl,
            'gateio_pnl_per_unit': gateio_pnl,
            'total_pnl_per_unit': total_pnl_per_unit,
            'total_pnl_usd': total_pnl_usd,
            'fees_usd': fees_usd,
            'net_pnl_usd': net_pnl_usd,
            'pnl_percentage': (net_pnl_usd / position_size) * 100 if position_size > 0 else 0,
            
            # Spread analysis
            'entry_spot_spread': position.get('entry_spot_spread', 0),
            'exit_spot_spread': current_spot_spread,
            'spread_capture': position.get('entry_spot_spread', 0) - current_spot_spread,
        }
        
        # Update inventory tracking
        units = position_size / entry_price if entry_price > 0 else 0
        self.mexc_inventory += units  # Close short position
        self.gateio_inventory -= units  # Close long position
        
        self.current_position = None
        self.position_start_time = None
        return trade_result
    
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