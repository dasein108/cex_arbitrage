"""
Arbitrage Signal Generator - Contains actual strategy logic for signal generation.

Generates trading signals based on indicators and current market conditions.
Ports actual strategy logic from ArbitrageAnalyzer backtesting methods.
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any

from ..types.signal_types import Signal


class ArbitrageSignalGenerator:
    """
    Generates trading signals based on indicators and current market conditions.
    Contains actual strategy logic ported from ArbitrageAnalyzer.
    """
    
    def __init__(self, strategy_type: str):
        """
        Initialize signal generator for specific strategy type.
        
        Args:
            strategy_type: 'reverse_delta_neutral', 'inventory_spot', 'volatility_harvesting'
        """
        self.strategy_type = strategy_type
        self.signal_count = 0
        self.last_signal = Signal.HOLD
        self.position_state = {
            'in_position': False,
            'entry_time': None,
            'entry_spread': None,
            'position_type': None
        }
    
    def generate_signal(self, 
                       strategy_type: str,
                       current_indicators: pd.Series,
                       historical_context: pd.DataFrame) -> Signal:
        """
        Generate trading signal based on strategy type and current conditions.
        
        Args:
            strategy_type: Strategy type to use for signal generation
            current_indicators: Current indicator values
            historical_context: Historical context for signal generation
            
        Returns:
            Trading signal (ENTER, EXIT, HOLD)
        """
        self.signal_count += 1
        
        try:
            if strategy_type == 'reverse_delta_neutral':
                signal = self.generate_reverse_delta_neutral_signal(current_indicators, historical_context)
            elif strategy_type == 'inventory_spot':
                signal = self.generate_inventory_spot_signal(current_indicators, historical_context)
            elif strategy_type == 'volatility_harvesting':
                signal = self.generate_volatility_harvesting_signal(current_indicators, historical_context)
            else:
                signal = Signal.HOLD
            
            self.last_signal = signal
            return signal
            
        except Exception as e:
            print(f"⚠️ Error generating signal: {e}")
            return Signal.HOLD
    
    def generate_reverse_delta_neutral_signal(self, 
                                            indicators: pd.Series, 
                                            historical_context: pd.DataFrame) -> Signal:
        """
        Generate signal for reverse delta neutral strategy.
        Ports signal logic from add_reverse_delta_neutral_backtest.
        
        Strategy Logic:
        - ENTER: When net spread > entry threshold (0.5%) after costs
        - EXIT: When net spread < exit threshold (0.1%) or max holding time exceeded
        - Risk management: Stop loss on adverse spread moves
        """
        # Check if we have required indicators
        required_indicators = [
            'mexc_vs_gateio_futures_net', 'gateio_spot_vs_futures_net',
            'entry_threshold', 'exit_threshold'
        ]
        if not all(indicator in indicators.index for indicator in required_indicators):
            return Signal.HOLD
        
        # Get current spread values
        mexc_futures_net = indicators.get('mexc_vs_gateio_futures_net', 0)
        spot_futures_net = indicators.get('gateio_spot_vs_futures_net', 0)
        entry_threshold = indicators.get('entry_threshold', 0.5)
        exit_threshold = indicators.get('exit_threshold', 0.1)
        
        # Position management
        if not self.position_state['in_position']:
            # Look for entry opportunities
            
            # Entry signal 1: MEXC vs Futures arbitrage
            if mexc_futures_net > entry_threshold:
                self.position_state.update({
                    'in_position': True,
                    'entry_time': pd.Timestamp.now(),
                    'entry_spread': mexc_futures_net,
                    'position_type': 'mexc_futures'
                })
                return Signal.ENTER
            
            # Entry signal 2: Spot vs Futures arbitrage
            elif spot_futures_net > entry_threshold:
                self.position_state.update({
                    'in_position': True,
                    'entry_time': pd.Timestamp.now(),
                    'entry_spread': spot_futures_net,
                    'position_type': 'spot_futures'
                })
                return Signal.ENTER
        
        else:
            # In position - look for exit conditions
            current_spread = (
                mexc_futures_net if self.position_state['position_type'] == 'mexc_futures'
                else spot_futures_net
            )
            
            # Exit condition 1: Spread below exit threshold
            if current_spread < exit_threshold:
                self._reset_position_state()
                return Signal.EXIT
            
            # Exit condition 2: Maximum holding time (24 hours)
            if self.position_state['entry_time']:
                holding_time = pd.Timestamp.now() - self.position_state['entry_time']
                if holding_time.total_seconds() / 3600 > 24:  # 24 hours
                    self._reset_position_state()
                    return Signal.EXIT
            
            # Exit condition 3: Adverse move (stop loss)
            if current_spread < -0.5:  # 0.5% adverse move
                self._reset_position_state()
                return Signal.EXIT
        
        return Signal.HOLD
    
    def generate_inventory_spot_signal(self, 
                                     indicators: pd.Series, 
                                     historical_context: pd.DataFrame) -> Signal:
        """
        Generate signal for inventory spot arbitrage strategy.
        Ports signal logic from add_inventory_spot_arbitrage_backtest.
        
        Strategy Logic:
        - ENTER: When rebalancing is profitable and volume is sufficient
        - EXIT: When balances are rebalanced or opportunity expires
        - Focus on inventory management and balance optimization
        """
        # Check if we have required indicators
        if 'inventory_rebalance_signal' not in indicators.index:
            return Signal.HOLD
        
        rebalance_signal = indicators.get('inventory_rebalance_signal', False)
        volume_suitable = indicators.get('volume_suitability', True)
        mexc_futures_net = indicators.get('mexc_vs_gateio_futures_net', 0)
        
        # Entry conditions for inventory rebalancing
        if not self.position_state['in_position']:
            if rebalance_signal and volume_suitable and mexc_futures_net > 0.3:
                self.position_state.update({
                    'in_position': True,
                    'entry_time': pd.Timestamp.now(),
                    'entry_spread': mexc_futures_net,
                    'position_type': 'inventory_rebalance'
                })
                return Signal.ENTER
        
        else:
            # Exit conditions
            # Exit when spread becomes unprofitable
            if mexc_futures_net < 0.1:
                self._reset_position_state()
                return Signal.EXIT
            
            # Exit after maximum holding time (shorter for inventory strategy)
            if self.position_state['entry_time']:
                holding_time = pd.Timestamp.now() - self.position_state['entry_time']
                if holding_time.total_seconds() / 3600 > 6:  # 6 hours max
                    self._reset_position_state()
                    return Signal.EXIT
        
        return Signal.HOLD
    
    def generate_volatility_harvesting_signal(self, 
                                            indicators: pd.Series, 
                                            historical_context: pd.DataFrame) -> Signal:
        """
        Generate signal for volatility harvesting strategy.
        Ports signal logic from add_spread_volatility_harvesting_backtest.
        
        Strategy Logic:
        - ENTER: During high volatility with favorable spreads
        - EXIT: When volatility drops or stop loss triggered
        - Multi-tier position sizing based on volatility regime
        """
        # Check if we have required indicators
        required_indicators = ['harvest_signal', 'vol_regime', 'stop_loss_signal']
        if not all(indicator in indicators.index for indicator in required_indicators):
            return Signal.HOLD
        
        harvest_signal = indicators.get('harvest_signal', False)
        vol_regime = indicators.get('vol_regime', 'low')
        stop_loss_signal = indicators.get('stop_loss_signal', False)
        mexc_futures_net = indicators.get('mexc_vs_gateio_futures_net', 0)
        
        # Entry conditions for volatility harvesting
        if not self.position_state['in_position']:
            if harvest_signal and vol_regime == 'high' and abs(mexc_futures_net) > 0.5:
                self.position_state.update({
                    'in_position': True,
                    'entry_time': pd.Timestamp.now(),
                    'entry_spread': mexc_futures_net,
                    'position_type': 'volatility_harvest'
                })
                return Signal.ENTER
        
        else:
            # Exit conditions
            # Exit on stop loss signal
            if stop_loss_signal:
                self._reset_position_state()
                return Signal.EXIT
            
            # Exit when volatility regime changes to low
            if vol_regime == 'low':
                self._reset_position_state()
                return Signal.EXIT
            
            # Exit when spread normalizes
            if abs(mexc_futures_net) < 0.2:
                self._reset_position_state()
                return Signal.EXIT
            
            # Exit after maximum holding time (volatility strategies are shorter term)
            if self.position_state['entry_time']:
                holding_time = pd.Timestamp.now() - self.position_state['entry_time']
                if holding_time.total_seconds() / 3600 > 4:  # 4 hours max
                    self._reset_position_state()
                    return Signal.EXIT
        
        return Signal.HOLD
    
    def _reset_position_state(self):
        """Reset position state after exit."""
        self.position_state = {
            'in_position': False,
            'entry_time': None,
            'entry_spread': None,
            'position_type': None
        }
    
    def get_signal_stats(self) -> Dict[str, Any]:
        """Get signal generation statistics."""
        return {
            'strategy_type': self.strategy_type,
            'total_signals': self.signal_count,
            'last_signal': self.last_signal.value,
            'position_state': self.position_state.copy(),
            'in_position': self.position_state['in_position']
        }
    
    def reset_stats(self):
        """Reset signal statistics and position state."""
        self.signal_count = 0
        self.last_signal = Signal.HOLD
        self._reset_position_state()