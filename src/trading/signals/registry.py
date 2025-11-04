"""
Strategy Signal Registry

Automatic registration of all strategy signal implementations.
"""

from .base.strategy_signal_factory import register_strategy_signal
from .implementations.reverse_delta_neutral_strategy_signal import ReverseDeltaNeutralStrategySignal
from .implementations.inventory_spot_strategy_signal import InventorySpotStrategySignal
from .implementations.volatility_harvesting_strategy_signal import VolatilityHarvestingStrategySignal


def register_all_strategies():
    """Register all available strategy signal implementations."""
    
    # Register all strategy implementations
    register_strategy_signal('reverse_delta_neutral', ReverseDeltaNeutralStrategySignal)
    register_strategy_signal('inventory_spot', InventorySpotStrategySignal)
    register_strategy_signal('volatility_harvesting', VolatilityHarvestingStrategySignal)
    
    # Register aliases for backward compatibility
    register_strategy_signal('delta_neutral', ReverseDeltaNeutralStrategySignal)
    register_strategy_signal('volatility', VolatilityHarvestingStrategySignal)


# Auto-register on import
register_all_strategies()