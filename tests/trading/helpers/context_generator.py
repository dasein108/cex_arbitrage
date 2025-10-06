"""
Context Generator for Trading Task Tests

Specialized helper for generating task contexts with various configurations
and states commonly used in trading task testing scenarios.
"""

from typing import Dict, Optional, Any
from enum import Enum

from exchanges.structs import Symbol, Side, ExchangeEnum
from trading.tasks.delta_neutral_task import DeltaNeutralTaskContext, Direction
from trading.struct import TradingStrategyState
from .test_data_factory import TestDataFactory


class TaskScenario(Enum):
    """Common task scenarios for testing."""
    FRESH_START = "fresh_start"
    PARTIALLY_EXECUTED = "partially_executed"
    IMBALANCED_FILLS = "imbalanced_fills"
    NEAR_COMPLETION = "near_completion"
    ERROR_RECOVERY = "error_recovery"
    MARKET_MOVING = "market_moving"


class ContextGenerator:
    """Generator for creating task contexts with specific scenarios."""
    
    def generate_delta_neutral_context(self, scenario: TaskScenario,
                                     symbol: Optional[Symbol] = None,
                                     **kwargs) -> DeltaNeutralTaskContext:
        """Generate delta neutral context for specific scenario."""
        if symbol is None:
            symbol = TestDataFactory.DEFAULT_SYMBOL
        
        if scenario == TaskScenario.FRESH_START:
            return self._generate_fresh_start_context(symbol, **kwargs)
        elif scenario == TaskScenario.PARTIALLY_EXECUTED:
            return self._generate_partially_executed_context(symbol, **kwargs)
        elif scenario == TaskScenario.IMBALANCED_FILLS:
            return self._generate_imbalanced_context(symbol, **kwargs)
        elif scenario == TaskScenario.NEAR_COMPLETION:
            return self._generate_near_completion_context(symbol, **kwargs)
        elif scenario == TaskScenario.ERROR_RECOVERY:
            return self._generate_error_recovery_context(symbol, **kwargs)
        elif scenario == TaskScenario.MARKET_MOVING:
            return self._generate_market_moving_context(symbol, **kwargs)
        else:
            return self._generate_fresh_start_context(symbol, **kwargs)
    
    def generate_context_with_state(self, symbol: Symbol,
                                   state: TradingStrategyState,
                                   **kwargs) -> DeltaNeutralTaskContext:
        """Generate context with specific state."""
        context = TestDataFactory.create_delta_neutral_context(symbol=symbol, **kwargs)
        context = context.evolve(state=state)
        return context
    
    def generate_context_with_fills(self, symbol: Symbol,
                                   buy_filled: float = 0.0,
                                   sell_filled: float = 0.0,
                                   buy_avg_price: float = 50000.0,
                                   sell_avg_price: float = 50100.0,
                                   **kwargs) -> DeltaNeutralTaskContext:
        """Generate context with specific fill amounts."""
        context = TestDataFactory.create_delta_neutral_context(symbol=symbol, **kwargs)
        
        context = context.evolve(
            filled_quantity={Side.BUY: buy_filled, Side.SELL: sell_filled},
            avg_price={Side.BUY: buy_avg_price, Side.SELL: sell_avg_price}
        )
        
        return context
    
    def generate_context_with_active_orders(self, symbol: Symbol,
                                          buy_order_id: Optional[str] = "buy_123",
                                          sell_order_id: Optional[str] = "sell_456",
                                          **kwargs) -> DeltaNeutralTaskContext:
        """Generate context with active orders."""
        context = TestDataFactory.create_delta_neutral_context(symbol=symbol, **kwargs)
        
        order_ids = {}
        if buy_order_id:
            order_ids[Side.BUY] = buy_order_id
        if sell_order_id:
            order_ids[Side.SELL] = sell_order_id
        
        if order_ids:
            context = context.evolve(order_id=order_ids)
        
        return context
    
    def generate_multi_scenario_contexts(self, symbol: Symbol) -> Dict[str, DeltaNeutralTaskContext]:
        """Generate contexts for multiple test scenarios."""
        scenarios = {}
        
        for scenario in TaskScenario:
            scenarios[scenario.value] = self.generate_delta_neutral_context(scenario, symbol)
        
        return scenarios
    
    def _generate_fresh_start_context(self, symbol: Symbol, **kwargs) -> DeltaNeutralTaskContext:
        """Generate context for fresh task start."""
        defaults = {
            'symbol': symbol,
            'total_quantity': 1.0,
            'order_quantity': 0.1,
            'state': TradingStrategyState.NOT_STARTED,
            'exchange_names': {
                Side.BUY: TestDataFactory.DEFAULT_BUY_EXCHANGE,
                Side.SELL: TestDataFactory.DEFAULT_SELL_EXCHANGE
            },
            'direction': Direction.NONE,
            'filled_quantity': {Side.BUY: 0.0, Side.SELL: 0.0},
            'avg_price': {Side.BUY: 0.0, Side.SELL: 0.0},
            'offset_ticks': {Side.BUY: 1, Side.SELL: 1},
            'tick_tolerance': {Side.BUY: 5, Side.SELL: 5},
            'order_id': {Side.BUY: None, Side.SELL: None}
        }
        
        defaults.update(kwargs)
        return DeltaNeutralTaskContext(**defaults)
    
    def _generate_partially_executed_context(self, symbol: Symbol, **kwargs) -> DeltaNeutralTaskContext:
        """Generate context for partially executed task."""
        defaults = {
            'symbol': symbol,
            'total_quantity': 1.0,
            'order_quantity': 0.1,
            'state': TradingStrategyState.EXECUTING,
            'exchange_names': {
                Side.BUY: TestDataFactory.DEFAULT_BUY_EXCHANGE,
                Side.SELL: TestDataFactory.DEFAULT_SELL_EXCHANGE
            },
            'direction': Direction.FILL,
            'filled_quantity': {Side.BUY: 0.3, Side.SELL: 0.3},
            'avg_price': {Side.BUY: 50000.0, Side.SELL: 50100.0},
            'offset_ticks': {Side.BUY: 1, Side.SELL: 1},
            'tick_tolerance': {Side.BUY: 5, Side.SELL: 5},
            'order_id': {Side.BUY: "active_buy_order", Side.SELL: "active_sell_order"}
        }
        
        defaults.update(kwargs)
        return DeltaNeutralTaskContext(**defaults)
    
    def _generate_imbalanced_context(self, symbol: Symbol, **kwargs) -> DeltaNeutralTaskContext:
        """Generate context with imbalanced fills."""
        defaults = {
            'symbol': symbol,
            'total_quantity': 1.0,
            'order_quantity': 0.1,
            'state': TradingStrategyState.EXECUTING,
            'exchange_names': {
                Side.BUY: TestDataFactory.DEFAULT_BUY_EXCHANGE,
                Side.SELL: TestDataFactory.DEFAULT_SELL_EXCHANGE
            },
            'direction': Direction.FILL,
            'filled_quantity': {Side.BUY: 0.7, Side.SELL: 0.3},  # Imbalanced
            'avg_price': {Side.BUY: 49950.0, Side.SELL: 50150.0},
            'offset_ticks': {Side.BUY: 1, Side.SELL: 1},
            'tick_tolerance': {Side.BUY: 5, Side.SELL: 5},
            'order_id': {Side.BUY: None, Side.SELL: "pending_sell_order"}
        }
        
        defaults.update(kwargs)
        return DeltaNeutralTaskContext(**defaults)
    
    def _generate_near_completion_context(self, symbol: Symbol, **kwargs) -> DeltaNeutralTaskContext:
        """Generate context near task completion."""
        defaults = {
            'symbol': symbol,
            'total_quantity': 1.0,
            'order_quantity': 0.1,
            'state': TradingStrategyState.EXECUTING,
            'exchange_names': {
                Side.BUY: TestDataFactory.DEFAULT_BUY_EXCHANGE,
                Side.SELL: TestDataFactory.DEFAULT_SELL_EXCHANGE
            },
            'direction': Direction.FILL,
            'filled_quantity': {Side.BUY: 0.95, Side.SELL: 0.95},  # Near completion
            'avg_price': {Side.BUY: 49975.0, Side.SELL: 50125.0},
            'offset_ticks': {Side.BUY: 1, Side.SELL: 1},
            'tick_tolerance': {Side.BUY: 5, Side.SELL: 5},
            'order_id': {Side.BUY: "final_buy_order", Side.SELL: "final_sell_order"}
        }
        
        defaults.update(kwargs)
        return DeltaNeutralTaskContext(**defaults)
    
    def _generate_error_recovery_context(self, symbol: Symbol, **kwargs) -> DeltaNeutralTaskContext:
        """Generate context for error recovery testing."""
        defaults = {
            'symbol': symbol,
            'total_quantity': 1.0,
            'order_quantity': 0.1,
            'state': TradingStrategyState.ERROR,
            'exchange_names': {
                Side.BUY: TestDataFactory.DEFAULT_BUY_EXCHANGE,
                Side.SELL: TestDataFactory.DEFAULT_SELL_EXCHANGE
            },
            'direction': Direction.FILL,
            'filled_quantity': {Side.BUY: 0.4, Side.SELL: 0.2},
            'avg_price': {Side.BUY: 50000.0, Side.SELL: 50100.0},
            'offset_ticks': {Side.BUY: 1, Side.SELL: 1},
            'tick_tolerance': {Side.BUY: 5, Side.SELL: 5},
            'order_id': {Side.BUY: "error_buy_order", Side.SELL: None},
            'error': Exception("Test error scenario")
        }
        
        defaults.update(kwargs)
        return DeltaNeutralTaskContext(**defaults)
    
    def _generate_market_moving_context(self, symbol: Symbol, **kwargs) -> DeltaNeutralTaskContext:
        """Generate context for market movement testing."""
        defaults = {
            'symbol': symbol,
            'total_quantity': 1.0,
            'order_quantity': 0.1,
            'state': TradingStrategyState.EXECUTING,
            'exchange_names': {
                Side.BUY: TestDataFactory.DEFAULT_BUY_EXCHANGE,
                Side.SELL: TestDataFactory.DEFAULT_SELL_EXCHANGE
            },
            'direction': Direction.FILL,
            'filled_quantity': {Side.BUY: 0.2, Side.SELL: 0.2},
            'avg_price': {Side.BUY: 50000.0, Side.SELL: 50100.0},
            'offset_ticks': {Side.BUY: 2, Side.SELL: 2},
            'tick_tolerance': {Side.BUY: 3, Side.SELL: 3},  # Tight tolerance for movement testing
            'order_id': {Side.BUY: "market_buy_order", Side.SELL: "market_sell_order"}
        }
        
        defaults.update(kwargs)
        return DeltaNeutralTaskContext(**defaults)