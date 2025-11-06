"""
Strategy Signal Base Classes

This module defines the abstract interfaces for cryptocurrency arbitrage strategy signals
with comprehensive backtesting capabilities and performance measurement.
"""

from trading.signals_v2.entities import PerformanceMetrics
from abc import ABC, abstractmethod
import pandas as pd


class StrategySignal(ABC):
    """
    Abstract base class for cryptocurrency arbitrage strategy signals.
    
    This class defines the interface for implementing arbitrage strategies with
    comprehensive backtesting, performance measurement, and live signal generation.
    
    All strategy implementations must provide backtesting capabilities with
    realistic cost modeling, risk management, and performance analytics.
    """
    
    @abstractmethod
    def backtest(self, df: pd.DataFrame) -> PerformanceMetrics:
        """
        Execute comprehensive backtest of the arbitrage strategy.

        This method should implement realistic trading simulation including:
        - Trading fees and slippage costs
        - Transfer delays between exchanges  
        - Execution failure scenarios
        - Proper profit/loss calculation
        - Risk-adjusted performance metrics

        Args:
            df: DataFrame containing historical market data with OHLCV data
                for all relevant exchanges and trading pairs

        Returns:
            PerformanceMetrics: Comprehensive performance results including:
                - Total P&L in USD and percentage terms
                - Risk-adjusted metrics (Sharpe ratio, max drawdown)
                - Trade statistics (win rate, average trade P&L)
                - Individual trade details for analysis
        """
        pass

