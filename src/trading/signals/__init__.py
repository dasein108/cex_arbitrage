"""
Strategy Signals Module

Comprehensive strategy signal generation system designed for high-frequency trading.
Eliminates if/else chains through proper strategy pattern implementation.

Architecture:
- Base interfaces and abstract classes for consistent implementation
- Individual strategy signal classes with isolated logic
- Factory pattern for strategy instantiation
- High-performance async-only backtesting system
- Real-time signal generation with sub-millisecond performance

Usage:

    # Generate live signal
    signal = await strategy.generate_live_signal(current_data)
    
    # Use in backtesting
    engine = StrategySignalEngine()
    results = await engine.run_backtest(data, strategy_type='reverse_delta_neutral')
"""

# Core interfaces and base classes
from trading.strategies.base.strategy_signal_interface import StrategySignalInterface
from trading.strategies.base.base_strategy_signal import BaseStrategySignal
from trading.strategies.base.strategy_signal_factory import StrategySignalFactory

# # Strategy implementations
# from .implementations.reverse_delta_neutral_strategy_signal import ReverseDeltaNeutralStrategySignal
# from .implementations.inventory_spot_strategy_signal import InventorySpotStrategySignal
# from .implementations.volatility_harvesting_strategy_signal import VolatilityHarvestingStrategySignal

# Signal engines
# Temporarily commented to break circular import
# from .engines.arbitrage_signal_engine import ArbitrageSignalEngine
from .engines.strategy_signal_engine import StrategySignalEngine

# Backtesting system
from .backtesting.vectorized_strategy_backtester import VectorizedStrategyBacktester

# Types and utilities
from .types.signal_types import Signal

# Auto-register all strategies
# Temporarily commented to break circular import
# from . import registry

__all__ = [
    # Core interfaces
    'StrategySignalInterface',
    'BaseStrategySignal',
    'StrategySignalFactory',

    # Strategy implementations
    # 'ReverseDeltaNeutralStrategySignal',
    # 'InventorySpotStrategySignal',
    # 'VolatilityHarvestingStrategySignal',
    
    # Engines
    # 'ArbitrageSignalEngine',  # Temporarily commented due to circular import
    'StrategySignalEngine',
    
    # Backtesting
    'VectorizedStrategyBacktester',
    
    # Types
    'Signal',

]

__version__ = "1.0.0"