"""
Pytest configuration and shared fixtures for trading task tests.

Provides common fixtures and setup for testing trading tasks with
mock exchanges and realistic test data.
"""

import pytest
import asyncio
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Configure test environment
os.environ['ENVIRONMENT'] = 'test'

from infrastructure.logging import get_logger
from infrastructure.logging.factory import LoggerFactory
from infrastructure.logging.structs import (
    LoggingConfig, ConsoleBackendConfig, PerformanceConfig, RouterConfig
)

from tests.trading.mocks import DualExchangeMockSystem
from tests.trading.helpers import TestDataFactory, OrderGenerator, MarketDataGenerator, ContextGenerator
from exchanges.structs import Symbol, ExchangeEnum, Side
from exchanges.structs.common import AssetName


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_logging():
    """Set up test-appropriate logging configuration."""
    LoggerFactory._default_config = LoggingConfig(
        environment="test",
        console=ConsoleBackendConfig(enabled=True, min_level="WARNING", color=False),
        performance=PerformanceConfig(buffer_size=10, batch_size=1, dispatch_interval=0.001),
        router=RouterConfig(default_backends=["console"])
    )


@pytest.fixture
def logger():
    """Provide HFT logger for tests."""
    return get_logger("test_delta_neutral")


@pytest.fixture
def test_symbol():
    """Provide default test symbol."""
    return TestDataFactory.DEFAULT_SYMBOL


@pytest.fixture
def alt_symbol():
    """Provide alternative test symbol."""
    return TestDataFactory.ALT_SYMBOL


@pytest.fixture
def dual_exchange_mock():
    """Provide dual exchange mock system."""
    mock_system = DualExchangeMockSystem()
    yield mock_system
    # Cleanup handled by test teardown


@pytest.fixture
async def initialized_dual_mock(dual_exchange_mock, test_symbol):
    """Provide initialized dual exchange mock system."""
    await dual_exchange_mock.setup([test_symbol])
    dual_exchange_mock.patch_exchange_factory()
    yield dual_exchange_mock
    await dual_exchange_mock.teardown()


@pytest.fixture
def test_data_factory():
    """Provide test data factory."""
    return TestDataFactory()


@pytest.fixture
def order_generator():
    """Provide order generator."""
    generator = OrderGenerator()
    yield generator
    generator.reset_counter()


@pytest.fixture
def market_data_generator():
    """Provide market data generator."""
    generator = MarketDataGenerator()
    yield generator
    generator.reset_timestamp()


@pytest.fixture
def context_generator():
    """Provide context generator."""
    return ContextGenerator()


@pytest.fixture
def fresh_context(test_symbol, context_generator):
    """Provide fresh delta neutral context."""
    return context_generator.generate_delta_neutral_context(
        scenario=context_generator.TaskScenario.FRESH_START,
        symbol=test_symbol
    )


@pytest.fixture
def arbitrage_scenario(test_symbol, market_data_generator):
    """Provide profitable arbitrage scenario data."""
    return market_data_generator.generate_arbitrage_opportunity(
        symbol=test_symbol,
        profit_margin=100.0,
        spread_width=2.0
    )


@pytest.fixture
def exchange_pairs():
    """Provide common exchange pairs for testing."""
    return {
        'gateio_mexc': (ExchangeEnum.GATEIO, ExchangeEnum.MEXC),
        'mexc_gateio': (ExchangeEnum.MEXC, ExchangeEnum.GATEIO),
    }


# Async test helpers
@pytest.fixture
def task_execution_helper():
    """Helper for running task execution cycles."""
    
    async def execute_cycles(task, max_cycles=10, target_state=None):
        """Execute task cycles until completion or target state."""
        cycles = 0
        results = []
        
        while cycles < max_cycles:
            result = await task.execute_once()
            results.append(result)
            cycles += 1
            
            # Check completion conditions
            if not result.should_continue:
                break
            
            if target_state and task.state == target_state:
                break
            
            # Small delay to prevent tight loops in tests
            await asyncio.sleep(0.001)
        
        return results, cycles
    
    return execute_cycles


# Test data validation helpers
@pytest.fixture
def validation_helper():
    """Helper for validating test results."""
    
    def validate_state_transition(old_state, new_state, valid_transitions):
        """Validate state transition is allowed."""
        return new_state in valid_transitions.get(old_state, [])
    
    def validate_order_placement(orders, expected_count, expected_sides=None):
        """Validate order placement matches expectations."""
        if len(orders) != expected_count:
            return False
        
        if expected_sides:
            order_sides = [order.side for order in orders]
            return set(order_sides) == set(expected_sides)
        
        return True
    
    def validate_fill_balance(buy_filled, sell_filled, tolerance=0.01):
        """Validate fill amounts are balanced within tolerance."""
        return abs(buy_filled - sell_filled) <= tolerance
    
    return type('ValidationHelper', (), {
        'validate_state_transition': validate_state_transition,
        'validate_order_placement': validate_order_placement,
        'validate_fill_balance': validate_fill_balance
    })()


# Performance testing helpers
@pytest.fixture
def performance_helper():
    """Helper for performance testing."""
    import time
    
    class PerformanceTimer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
        
        def start(self):
            self.start_time = time.time()
        
        def stop(self):
            self.end_time = time.time()
        
        @property
        def elapsed_ms(self):
            if self.start_time and self.end_time:
                return (self.end_time - self.start_time) * 1000
            return None
    
    return PerformanceTimer