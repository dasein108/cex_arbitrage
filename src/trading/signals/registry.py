"""
Strategy Signal Registry

Automatic registration of all strategy signal implementations.
"""

from .base.strategy_signal_factory import register_strategy_signal
# from .implementations.reverse_delta_neutral_strategy_signal import ReverseDeltaNeutralStrategySignal
# from .implementations.inventory_spot_strategy_signal import InventorySpotStrategySignal
# from .implementations.volatility_harvesting_strategy_signal import VolatilityHarvestingStrategySignal
from .implementations.inventory_spot_strategy_signal_v2 import InventorySpotStrategySignalV2
from trading.signals.implementations.unsupported.volatility_harvesting_strategy_signal_v2 import VolatilityHarvestingStrategySignalV2


def register_all_strategies():
    """Register all available strategy signal implementations."""
    
    # Register all strategy implementations
    # register_strategy_signal('reverse_delta_neutral', ReverseDeltaNeutralStrategySignal)
    # register_strategy_signal('inventory_spot', InventorySpotStrategySignal)
    # register_strategy_signal('volatility_harvesting', VolatilityHarvestingStrategySignal)
    #
    # Register v2 implementations with arbitrage analyzer logic
    register_strategy_signal('inventory_spot_v2', InventorySpotStrategySignalV2)
    register_strategy_signal('volatility_harvesting_v2', VolatilityHarvestingStrategySignalV2)


# Auto-register on import
register_all_strategies()