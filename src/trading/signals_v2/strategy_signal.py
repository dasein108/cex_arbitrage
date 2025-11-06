from trading.signals_v2.entities import PerformanceMetrics
from abc import ABC, abstractmethod
import pandas as pd


class StrategySignal(ABC):
    @abstractmethod
    def backtest(self, df: pd.DataFrame) -> PerformanceMetrics:
        """
        Backtest the strategy signal on the provided DataFrame.

        Args:
            df: DataFrame containing market data for backtesting.

        Returns:
            PerformanceMetrics: The performance metrics of the backtest.
        """
        pass

