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
    from trading.signals import get_strategy_signal, StrategySignalEngine
    
    # Create strategy signal instance
    strategy = get_strategy_signal('reverse_delta_neutral')
    
    # Generate live signal
    signal = await strategy.generate_live_signal(current_data)
    
    # Use in backtesting
    engine = StrategySignalEngine()
    results = await engine.run_backtest(data, strategy_type='reverse_delta_neutral')
"""

# Core interfaces and base classes
from .base.strategy_signal_interface import StrategySignalInterface
from .base.base_strategy_signal import BaseStrategySignal
from .base.strategy_signal_factory import StrategySignalFactory, get_strategy_signal

# Strategy implementations
from .implementations.reverse_delta_neutral_strategy_signal import ReverseDeltaNeutralStrategySignal
from .implementations.inventory_spot_strategy_signal import InventorySpotStrategySignal
from .implementations.volatility_harvesting_strategy_signal import VolatilityHarvestingStrategySignal

# Signal engines
from .engines.arbitrage_signal_engine import ArbitrageSignalEngine
from .engines.strategy_signal_engine import StrategySignalEngine

# Backtesting system
from .backtesting.strategy_signal_backtester import StrategySignalBacktester
from .backtesting.vectorized_strategy_backtester import VectorizedStrategyBacktester

# Types and utilities
from .types.signal_types import Signal
from .types.signal_validators import ValidationResult, RDNSignalValidator, MarketRegimeValidator

# Auto-register all strategies
from . import registry

__all__ = [
    # Core interfaces
    'StrategySignalInterface',
    'BaseStrategySignal',
    'StrategySignalFactory',
    'get_strategy_signal',
    
    # Strategy implementations
    'ReverseDeltaNeutralStrategySignal',
    'InventorySpotStrategySignal', 
    'VolatilityHarvestingStrategySignal',
    
    # Engines
    'ArbitrageSignalEngine',
    'StrategySignalEngine',
    
    # Backtesting
    'StrategySignalBacktester',
    'VectorizedStrategyBacktester',
    
    # Types
    'Signal',
    'ValidationResult',
    'RDNSignalValidator',
    'MarketRegimeValidator'
]

__version__ = "1.0.0"