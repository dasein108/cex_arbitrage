from .base_strategy.base_strategy import BaseStrategyTask, BaseStrategyContext
from .cross_exchange_arbitrage_strategy.cross_exchange_arbitrage_task import (CrossExchangeArbitrageTask,
                                                                              CrossExchangeArbitrageTaskContext,
                                                                              ExchangeData, ExchangeRoleType)

# Strategy Signal Implementations
from .reverse_delta_neutral_strategy_signal import ReverseDeltaNeutralStrategySignal
from .inventory_spot_strategy_signal import InventorySpotStrategySignal
from .volatility_harvesting_strategy_signal import VolatilityHarvestingStrategySignal

# Auto-register all strategy implementations
from trading.strategies.base.strategy_signal_factory import register_strategy_signal

# Register all strategy signals with the factory
register_strategy_signal('reverse_delta_neutral', ReverseDeltaNeutralStrategySignal)
register_strategy_signal('delta_neutral', ReverseDeltaNeutralStrategySignal)  # Alias
register_strategy_signal('inventory_spot', InventorySpotStrategySignal)
register_strategy_signal('volatility_harvesting', VolatilityHarvestingStrategySignal)
register_strategy_signal('volatility', VolatilityHarvestingStrategySignal)  # Alias