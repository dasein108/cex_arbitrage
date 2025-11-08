"""
Strategy Signal Base Components

Core infrastructure for strategy signal implementations.
"""

from .strategy_signal_interface import StrategySignalInterface
from .base_strategy_signal import BaseStrategySignal
from .strategy_signal_factory import (
    StrategySignalFactory,
    create_strategy_signal,
    register_strategy_signal,
    get_available_strategy_signals,
    normalize_strategy_type
)
from .types import PerformanceMetrics

__all__ = [
    'StrategySignalInterface',
    'BaseStrategySignal',
    'StrategySignalFactory',
    'create_strategy_signal',
    'register_strategy_signal', 
    'get_available_strategy_signals',
    'normalize_strategy_type',
    'PerformanceMetrics'
]