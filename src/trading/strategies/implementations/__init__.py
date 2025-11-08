# Temporarily commented to fix missing analysis module dependencies
# from .base_strategy.base_strategy import BaseStrategyTask, BaseStrategyContext
# from .cross_exchange_arbitrage_strategy.cross_exchange_arbitrage_task import (CrossExchangeArbitrageTask,
#                                                                              CrossExchangeArbitrageTaskContext,
#                                                                              ExchangeData, ExchangeRoleType)

# Strategy Signal Implementations
from .reverse_delta_neutral_strategy_signal import ReverseDeltaNeutralStrategySignal
from .inventory_spot_strategy_signal import InventorySpotStrategySignal
from .volatility_harvesting_strategy_signal import VolatilityHarvestingStrategySignal

# Auto-register all strategy implementations
from trading.strategies.base.strategy_signal_factory import register_strategy_signal

# Import V2 implementations from signals_v2 module
# from trading.signals_v2.implementation.inventory_spot_strategy_signal import InventorySpotStrategySignalV2
from trading.signals.implementations.unsupported.volatility_harvesting_strategy_signal_v2 import VolatilityHarvestingStrategySignalV2

# Register all strategy signals_v2 with the factory
register_strategy_signal('reverse_delta_neutral', ReverseDeltaNeutralStrategySignal)
register_strategy_signal('delta_neutral', ReverseDeltaNeutralStrategySignal)  # Alias
register_strategy_signal('inventory_spot', InventorySpotStrategySignal)
register_strategy_signal('volatility_harvesting', VolatilityHarvestingStrategySignal)
register_strategy_signal('volatility', VolatilityHarvestingStrategySignal)  # Alias

# Register V2 strategies
# register_strategy_signal('inventory_spot_v2', InventorySpotStrategySignalV2)
register_strategy_signal('volatility_harvesting_v2', VolatilityHarvestingStrategySignalV2)
# register_strategy_signal('inventory_v2', InventorySpotStrategySignalV2)  # Alias
register_strategy_signal('volatility_v2', VolatilityHarvestingStrategySignalV2)  # Alias