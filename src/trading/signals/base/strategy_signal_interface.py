"""
Strategy Signal Interface

Abstract base class defining the interface for all strategy signal implementations.
Provides unified interface for both real-time trading and backtesting operations.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union, Tuple
import pandas as pd
import numpy as np
from datetime import datetime

from ..types.signal_types import Signal
from ..types.performance_metrics import PerformanceMetrics


class StrategySignalInterface(ABC):
    """
    Abstract base interface for all strategy signal implementations.
    
    Defines the contract that all strategy signals must implement for both
    real-time trading and backtesting operations.
    """
    
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
    def apply_signal_to_backtest(self, df: pd.DataFrame, **params) -> pd.DataFrame:
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
    def open_position(self, signal: Signal, market_data: Dict[str, Any], **params) -> None:
        """
        Open position with internal tracking.
        
        Args:
            signal: Trading signal (should be ENTER)
            market_data: Current market data
            **params: Additional parameters (position_size_usd, etc.)
        """
        pass
    
    @abstractmethod
    def close_position(self, signal: Signal, market_data: Dict[str, Any], **params) -> None:
        """
        Close position with internal tracking.
        
        Args:
            signal: Trading signal (should be EXIT)
            market_data: Current market data
            **params: Additional parameters
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
    def get_strategy_params(self) -> Dict[str, Any]:
        """
        Get current strategy parameters.
        
        Returns:
            Dictionary of strategy configuration parameters
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
    def get_performance_metrics(self) -> PerformanceMetrics:
        """
        Get comprehensive performance metrics for this strategy.
        
        Returns:
            PerformanceMetrics struct with current performance data
        """
        pass
    
    @abstractmethod
    def reset_position_tracking(self) -> None:
        """Reset all internal position tracking data."""
        pass