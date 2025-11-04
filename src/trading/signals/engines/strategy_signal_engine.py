"""
Strategy Signal Engine

Modern signal engine using the strategy signal architecture.
Eliminates if/else chains and provides clean separation of concerns.
"""

from typing import Dict, Any, Optional, Union, List
import pandas as pd
import logging
from datetime import datetime

from ..base.strategy_signal_factory import create_strategy_signal, normalize_strategy_type
from ..base.strategy_signal_interface import StrategySignalInterface
from ..types.signal_types import Signal


class StrategySignalEngine:
    """
    Modern signal engine using strategy signal architecture.
    
    Eliminates if/else chains by delegating to strategy-specific implementations.
    Provides unified interface for both real-time and backtesting operations.
    """
    
    def __init__(self, 
                 default_strategy_type: str = 'reverse_delta_neutral',
                 cache_strategies: bool = True):
        """
        Initialize strategy signal engine.
        
        Args:
            default_strategy_type: Default strategy to use
            cache_strategies: Whether to cache strategy instances
        """
        self.default_strategy_type = normalize_strategy_type(default_strategy_type)
        self.cache_strategies = cache_strategies
        
        # Strategy cache
        self._strategy_cache: Dict[str, StrategySignalInterface] = {}
        
        # Performance tracking
        self._signal_count = 0
        self._cache_hits = 0
        self._cache_misses = 0
        
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def generate_live_signal(self, 
                                 market_data: Dict[str, Any], 
                                 strategy_type: Optional[str] = None,
                                 **params) -> Dict[str, Any]:
        """
        Generate live trading signal using strategy signal architecture.
        
        Args:
            market_data: Current market data snapshot
            strategy_type: Strategy type to use (optional)
            **params: Strategy parameters
            
        Returns:
            Signal result dictionary
        """
        strategy_type = normalize_strategy_type(strategy_type or self.default_strategy_type)
        
        try:
            # Get strategy instance
            strategy = self._get_strategy_instance(strategy_type, **params)
            
            # Generate signal
            signal, confidence = strategy.generate_live_signal(market_data, **params)
            
            self._signal_count += 1
            
            return {
                'signal': signal,
                'confidence': confidence,
                'strategy_type': strategy_type,
                'timestamp': datetime.now(),
                'success': True
            }
            
        except Exception as e:
            self.logger.error(f"Error generating live signal with {strategy_type}: {e}")
            return {
                'signal': Signal.HOLD,
                'confidence': 0.0,
                'strategy_type': strategy_type,
                'timestamp': datetime.now(),
                'success': False,
                'error': str(e)
            }
    
    async def apply_signals_to_backtest(self, 
                                      df: pd.DataFrame,
                                      strategy_type: Optional[str] = None,
                                      **params) -> pd.DataFrame:
        """
        Apply strategy signals to historical data for backtesting.
        
        Args:
            df: Historical market data DataFrame
            strategy_type: Strategy type to use (optional)
            **params: Strategy parameters
            
        Returns:
            DataFrame with added signal columns
        """
        strategy_type = normalize_strategy_type(strategy_type or self.default_strategy_type)
        
        try:
            # Get strategy instance
            strategy = self._get_strategy_instance(strategy_type, **params)
            
            # Preload strategy with historical data
            await strategy.preload(df, **params)
            
            # Apply signals to backtest
            result_df = strategy.apply_signal_to_backtest(df, **params)
            
            # Add metadata
            result_df['strategy_type'] = strategy_type
            
            self.logger.info(f"Applied {strategy_type} signals to {len(result_df)} periods")
            return result_df
            
        except Exception as e:
            self.logger.error(f"Error applying {strategy_type} signals to backtest: {e}")
            # Return original DataFrame with HOLD signals
            df['signal'] = Signal.HOLD.value
            df['confidence'] = 0.0
            df['strategy_type'] = strategy_type
            return df
    
    async def preload_strategy(self, 
                             historical_data: pd.DataFrame,
                             strategy_type: Optional[str] = None,
                             **params) -> bool:
        """
        Preload a strategy with historical data.
        
        Args:
            historical_data: Historical market data
            strategy_type: Strategy type to preload
            **params: Strategy parameters
            
        Returns:
            True if successful, False otherwise
        """
        strategy_type = normalize_strategy_type(strategy_type or self.default_strategy_type)
        
        try:
            strategy = self._get_strategy_instance(strategy_type, **params)
            await strategy.preload(historical_data, **params)
            
            self.logger.info(f"Preloaded {strategy_type} with {len(historical_data)} periods")
            return True
            
        except Exception as e:
            self.logger.error(f"Error preloading {strategy_type}: {e}")
            return False
    
    def update_strategy_indicators(self, 
                                 new_data: Union[Dict[str, Any], pd.DataFrame],
                                 strategy_type: Optional[str] = None,
                                 **params) -> bool:
        """
        Update strategy indicators with new market data.
        
        Args:
            new_data: New market data
            strategy_type: Strategy type to update
            **params: Strategy parameters
            
        Returns:
            True if successful, False otherwise
        """
        strategy_type = normalize_strategy_type(strategy_type or self.default_strategy_type)
        
        try:
            strategy = self._get_strategy_instance(strategy_type, **params)
            strategy.update_indicators(new_data)
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating {strategy_type} indicators: {e}")
            return False
    
    def get_strategy_info(self, strategy_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get information about a strategy.
        
        Args:
            strategy_type: Strategy type to query
            
        Returns:
            Strategy information dictionary
        """
        strategy_type = normalize_strategy_type(strategy_type or self.default_strategy_type)
        
        try:
            strategy = self._get_strategy_instance(strategy_type)
            
            return {
                'strategy_type': strategy_type,
                'required_lookback': strategy.get_required_lookback(),
                'parameters': strategy.get_strategy_params(),
                'class_name': strategy.__class__.__name__
            }
            
        except Exception as e:
            return {
                'strategy_type': strategy_type,
                'error': str(e)
            }
    
    def clear_strategy_cache(self) -> None:
        """Clear the strategy cache."""
        self._strategy_cache.clear()
        self.logger.info("Strategy cache cleared")
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get performance statistics for the signal engine.
        
        Returns:
            Performance statistics dictionary
        """
        total_requests = self._cache_hits + self._cache_misses
        cache_hit_rate = (self._cache_hits / total_requests) * 100 if total_requests > 0 else 0
        
        return {
            'total_signals_generated': self._signal_count,
            'cached_strategies': len(self._strategy_cache),
            'cache_hit_rate_pct': cache_hit_rate,
            'cache_hits': self._cache_hits,
            'cache_misses': self._cache_misses
        }
    
    # Private methods
    
    def _get_strategy_instance(self, strategy_type: str, **params) -> StrategySignalInterface:
        """
        Get strategy instance, using cache if enabled.
        
        Args:
            strategy_type: Strategy type
            **params: Strategy parameters
            
        Returns:
            Strategy instance
        """
        cache_key = self._get_cache_key(strategy_type, **params)
        
        if self.cache_strategies and cache_key in self._strategy_cache:
            self._cache_hits += 1
            return self._strategy_cache[cache_key]
        
        self._cache_misses += 1
        
        # Create new strategy instance
        strategy = create_strategy_signal(strategy_type, **params)
        
        if self.cache_strategies:
            self._strategy_cache[cache_key] = strategy
        
        return strategy
    
    def _get_cache_key(self, strategy_type: str, **params) -> str:
        """
        Generate cache key for strategy instance.
        
        Args:
            strategy_type: Strategy type
            **params: Strategy parameters
            
        Returns:
            Cache key string
        """
        # Create a simple cache key based on strategy type and key parameters
        key_params = {
            'entry_threshold': params.get('entry_threshold'),
            'exit_threshold': params.get('exit_threshold'),
            'lookback_periods': params.get('lookback_periods'),
            'position_size_usd': params.get('position_size_usd')
        }
        
        # Filter out None values
        key_params = {k: v for k, v in key_params.items() if v is not None}
        
        # Create cache key
        params_str = '_'.join(f"{k}={v}" for k, v in sorted(key_params.items()))
        return f"{strategy_type}_{params_str}" if params_str else strategy_type


# Convenience functions for backward compatibility

async def generate_live_signal(market_data: Dict[str, Any], 
                             strategy_type: str = 'reverse_delta_neutral',
                             **params) -> Dict[str, Any]:
    """
    Convenience function to generate a live signal.
    
    Args:
        market_data: Current market data
        strategy_type: Strategy type to use
        **params: Strategy parameters
        
    Returns:
        Signal result dictionary
    """
    engine = StrategySignalEngine()
    return await engine.generate_live_signal(market_data, strategy_type, **params)


async def apply_signals_to_backtest(df: pd.DataFrame,
                                  strategy_type: str = 'reverse_delta_neutral',
                                  **params) -> pd.DataFrame:
    """
    Convenience function to apply signals to backtest data.
    
    Args:
        df: Historical market data
        strategy_type: Strategy type to use
        **params: Strategy parameters
        
    Returns:
        DataFrame with signals
    """
    engine = StrategySignalEngine()
    return await engine.apply_signals_to_backtest(df, strategy_type, **params)