# Trading Task Testing Framework

Comprehensive testing framework for the CEX Arbitrage trading system, specifically designed for testing delta neutral and other trading task state machines without requiring actual exchange connections.

## Overview

This testing framework provides:

- **Dual Exchange Mock System**: Realistic mock implementations of public and private exchanges
- **Test Data Factories**: Consistent generation of orders, market data, and contexts
- **State Machine Testing**: Comprehensive tests for trading task workflows
- **Performance Testing**: HFT-compliant performance verification
- **Edge Case Coverage**: Error handling, market volatility, and failure scenarios

## Framework Architecture

### Mock Systems (`tests/trading/mocks/`)

- **`DualExchangeMockSystem`**: Complete dual exchange simulation for arbitrage testing
- **`MockPublicExchange`**: Market data simulation (orderbooks, tickers, symbols)
- **`MockPrivateExchange`**: Trading operations simulation (orders, balances, fills)

### Test Data Helpers (`tests/trading/helpers/`)

- **`TestDataFactory`**: Central factory for creating consistent test data
- **`OrderGenerator`**: Specialized order creation with fill patterns
- **`MarketDataGenerator`**: Market condition and price movement simulation
- **`ContextGenerator`**: Task context creation for various scenarios

### Test Suites (`tests/trading/tasks/`)

- **`test_delta_neutral_task.py`**: Comprehensive delta neutral state machine tests
- **`test_base_task.py`**: Base trading task functionality tests
- **`test_mock_systems.py`**: Mock system reliability tests

## Quick Start

### Run All Tests with Pytest

```bash
# Run all tests
pytest tests/

# Run only delta neutral tests
pytest tests/trading/tasks/test_delta_neutral_task.py

# Run with verbose output
pytest tests/ -v

# Run performance tests only
pytest tests/ -m performance
```

### Run Standalone Test Suite

```bash
# Quick test runner (no pytest required)
python tests/run_delta_neutral_tests.py
```

### Run Individual Test Classes

```bash
# Test state machine flow only
pytest tests/trading/tasks/test_delta_neutral_task.py::TestDeltaNeutralTaskStateMachine

# Test rebalancing scenarios
pytest tests/trading/tasks/test_delta_neutral_task.py::TestRebalancing
```

## Key Test Scenarios

### 1. State Machine Flow Testing

Tests the complete workflow: `IDLE → SYNCING → ANALYZING → MANAGING_ORDERS → COMPLETING`

```python
async def test_state_machine_flow():
    context = TestDataFactory.create_delta_neutral_context(symbol=test_symbol)
    task = DeltaNeutralTask(logger=logger, context=context)
    
    await task.start()
    results, cycles = await task_execution_helper(task, max_cycles=10)
    
    assert task.state == DeltaNeutralState.COMPLETING
```

### 2. Arbitrage Scenario Testing

```python
async def test_profitable_arbitrage():
    # Setup profitable arbitrage opportunity
    mock_system.setup_profitable_arbitrage(symbol, 50000.0, 50100.0)
    
    # Execute task and verify order placement
    task = DeltaNeutralTask(logger=logger, context=context)
    # ... test execution
```

### 3. Rebalancing Testing

```python
async def test_imbalance_rebalancing():
    # Create imbalanced fills
    context = TestDataFactory.create_delta_neutral_context(
        filled_quantity={Side.BUY: 0.7, Side.SELL: 0.3}
    )
    
    # Verify rebalancing is triggered
    # ... test execution
```

### 4. Error Handling Testing

```python
async def test_order_failure_handling():
    # Configure mock to fail orders
    mock_system.set_order_failure_behavior(Side.BUY, should_fail_orders=True)
    
    # Verify graceful handling
    # ... test execution
```

## Mock System Usage

### Basic Setup

```python
@pytest.fixture
async def initialized_dual_mock(test_symbol):
    mock_system = DualExchangeMockSystem()
    await mock_system.setup([test_symbol])
    mock_system.patch_exchange_factory()
    yield mock_system
    await mock_system.teardown()
```

### Market Data Control

```python
# Set specific prices
mock_system.set_prices(
    symbol,
    buy_side_bid=49999.0, buy_side_ask=50001.0,
    sell_side_bid=50099.0, sell_side_ask=50101.0
)

# Simulate price movement
mock_system.move_prices(symbol, price_change=100.0)

# Setup arbitrage scenario
mock_system.setup_profitable_arbitrage(symbol, 50000.0, 50100.0)
```

### Order Behavior Control

```python
# Control fill behavior
mock_system.set_order_fill_behavior(Side.BUY, "order_123", fill_quantity=0.05)

# Simulate failures
mock_system.set_order_failure_behavior(Side.SELL, should_fail_orders=True)

# Simulate fills during execution
mock_system.simulate_order_fill_during_execution(Side.BUY, order_id, 0.03)
```

### Verification Methods

```python
# Check order history
buy_orders = mock_system.get_order_history(Side.BUY)
total_orders = mock_system.get_total_orders_placed()
cancelled_orders = mock_system.get_cancelled_orders(Side.SELL)

# Verify initialization
init_status = mock_system.verify_initialization()
assert all(init_status)
```

## Test Data Generation

### Creating Test Contexts

```python
# Fresh start scenario
context = context_generator.generate_delta_neutral_context(
    ContextGenerator.TaskScenario.FRESH_START,
    symbol=test_symbol
)

# Partially executed scenario
context = context_generator.generate_delta_neutral_context(
    ContextGenerator.TaskScenario.PARTIALLY_EXECUTED,
    symbol=test_symbol
)

# Custom context
context = TestDataFactory.create_delta_neutral_context(
    symbol=test_symbol,
    total_quantity=1.0,
    filled_quantity={Side.BUY: 0.3, Side.SELL: 0.5}
)
```

### Generating Orders

```python
# Dual side orders with fill patterns
orders = order_generator.generate_dual_side_orders(
    symbol,
    buy_fill_pattern=FillPattern.PARTIAL_FILL,
    sell_fill_pattern=FillPattern.FULL_FILL
)

# Progressive fill sequence
fill_sequence = order_generator.generate_progressive_fill_sequence(
    symbol, Side.BUY, total_quantity=1.0
)

# Imbalanced scenario
scenario = order_generator.generate_imbalanced_scenario(
    symbol, buy_fill_ratio=0.7, sell_fill_ratio=0.3
)
```

### Market Data Scenarios

```python
# Arbitrage opportunity
arbitrage = market_data_generator.generate_arbitrage_opportunity(
    symbol, profit_margin=100.0
)

# Volatile market
volatile_tickers = market_data_generator.generate_volatile_market(
    symbol, volatility_percentage=10.0
)

# Price movement patterns
price_sequence = market_data_generator.generate_price_movement_sequence(
    symbol, PriceMovementPattern.SUDDEN_SPIKE
)
```

## Performance Testing

The framework includes HFT-compliant performance testing:

```python
async def test_execution_performance():
    # Measure execution cycle time
    performance_helper.start()
    result = await task.execute_once()
    performance_helper.stop()
    
    # Verify HFT compliance (<100ms)
    assert performance_helper.elapsed_ms < 100
    assert result.execution_time_ms < 100
```

## Test Configuration

### Pytest Markers

- `@pytest.mark.unit`: Unit tests for individual components
- `@pytest.mark.integration`: Integration tests requiring external systems
- `@pytest.mark.performance`: Performance and timing tests
- `@pytest.mark.slow`: Tests that take longer to run
- `@pytest.mark.mock`: Tests using mock systems

### Environment Setup

Tests automatically configure a test environment with:

- Minimal logging (warnings only)
- Fast performance dispatch
- Isolated test state
- Proper cleanup

## Best Practices

### 1. Test Isolation

- Each test gets fresh mock instances
- Automatic cleanup after tests
- Reset tracking between tests

### 2. Realistic Scenarios

- Use actual trading quantities and prices
- Simulate real market conditions
- Test edge cases that occur in production

### 3. Performance Awareness

- Keep tests fast (<1s each)
- Measure HFT compliance
- Avoid unnecessary delays

### 4. Comprehensive Coverage

- Test happy path and error conditions
- Verify state transitions
- Check order lifecycle management
- Test rebalancing scenarios

## Extending the Framework

### Adding New Mock Behaviors

```python
class CustomMockExchange(MockPrivateExchange):
    def set_custom_behavior(self, behavior_config):
        # Implement custom behavior
        pass
```

### Creating New Test Scenarios

```python
def generate_custom_scenario(self, symbol: Symbol) -> Context:
    return TestDataFactory.create_delta_neutral_context(
        symbol=symbol,
        # Custom configuration
    )
```

### Adding Performance Metrics

```python
@pytest.fixture
def custom_performance_helper():
    # Custom performance measurement
    pass
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure `src/` is in Python path
2. **Mock Patch Conflicts**: Use `await mock_system.teardown()` 
3. **Async Test Issues**: Use `@pytest.mark.asyncio`
4. **State Machine Hangs**: Check `max_cycles` in execution helpers

### Debug Mode

Enable detailed logging:

```python
# In test setup
LoggerFactory._default_config.console.min_level = "DEBUG"
```

### Test Data Inspection

```python
# Inspect test results
print(f"Orders placed: {mock_system.get_total_orders_placed()}")
print(f"Final state: {task.state.name}")
print(f"Fill status: {task.context.filled_quantity}")
```

## Integration with CI/CD

The framework is designed for automated testing:

- Fast execution (<30s for full suite)
- No external dependencies
- Clear pass/fail reporting
- Performance regression detection

Add to your CI pipeline:

```yaml
- name: Run Trading Task Tests
  run: |
    python -m pytest tests/ --tb=short
    python tests/run_delta_neutral_tests.py
```

This testing framework provides comprehensive coverage for trading task development while maintaining HFT performance requirements and realistic trading scenarios.