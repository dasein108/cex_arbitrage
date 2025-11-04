"""
Base Strategy Signal Components

Core interfaces and abstract classes providing the foundation for all strategy signals.
"""

from .strategy_signal_interface import StrategySignalInterface
from .base_strategy_signal import BaseStrategySignal
from .strategy_signal_factory import StrategySignalFactory, get_strategy_signal

__all__ = [
    'StrategySignalInterface',
    'BaseStrategySignal', 
    'StrategySignalFactory',
    'get_strategy_signal'
]