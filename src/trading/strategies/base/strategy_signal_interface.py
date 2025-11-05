"""
Strategy Signal Interface

Abstract base class defining the interface for all strategy signal implementations.
Provides unified interface for both real-time trading and backtesting operations.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union, Tuple
import pandas as pd

from trading.signals.types import PerformanceMetrics
from trading.signals.types.signal_types import Signal


class StrategySignalInterface(ABC):
    """
    Abstract base interface for all strategy signal implementations.
    
    Defines the contract that all strategy signals must implement for both
    real-time trading and backtesting operations.
    """

    strategy_type: Optional[str] = None

    @abstractmethod
    async def preload(self, historical_data: pd.DataFrame, **params) -> None:
        """
        Preload historical data for strategy initialization.
        
        Called once during strategy initialization to load historical context.
        Used for both backtesting (full dataset) and live trading (recent history).
        
        Args:
            historical_data: Historical market data DataFrame
            **params: Strategy-specific parameters
        """
        pass
    
    @abstractmethod
    def generate_live_signal(self, market_data: Dict[str, Any], **params) -> Tuple[Signal, float]:
        """
        Generate trading signal from live market data.
        
        Optimized for real-time trading with sub-millisecond performance.
        
        Args:
            market_data: Current market data snapshot
            **params: Strategy-specific parameters
            
        Returns:
            Tuple of (Signal, confidence_score)
        """
        pass


    @abstractmethod
    def backtest(self, df: pd.DataFrame, **params) -> PerformanceMetrics:
        """
        Apply strategy signals to historical data for backtesting.
        
        Vectorized implementation for efficient backtesting across large datasets.
        
        Args:
            df: Historical market data DataFrame
            **params: Strategy-specific parameters
            
        Returns:
            DataFrame with added signal columns
        """
        pass
    

    
    @abstractmethod
    def update_indicators(self, new_data: Union[Dict[str, Any], pd.DataFrame]) -> None:
        """
        Update rolling indicators with new market data.
        
        Maintains indicator state for continuous signal generation.
        Called periodically in live trading to keep indicators synchronized.
        
        Args:
            new_data: New market data (single row or snapshot)
        """
        pass
    
    @abstractmethod
    def get_required_lookback(self) -> int:
        """
        Get the minimum lookback period required for the strategy.
        
        Returns:
            Number of historical periods needed for indicator calculation
        """
        pass
    

    @abstractmethod
    def validate_market_data(self, data: Union[Dict[str, Any], pd.DataFrame]) -> bool:
        """
        Validate that market data has required fields for the strategy.
        
        Args:
            data: Market data to validate
            
        Returns:
            True if data is valid, False otherwise
        """
        pass
    
    @abstractmethod
    def calculate_signal_confidence(self, indicators: Dict[str, float]) -> float:
        """
        Calculate confidence score for the current signal.
        
        Args:
            indicators: Current indicator values
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        pass
    

    @abstractmethod
    def reset_position_tracking(self) -> None:
        """
        Reset internal position tracking state.
        
        Clears all position history, completed trades, and current positions.
        Used for starting fresh backtests or live trading sessions.
        """
        pass