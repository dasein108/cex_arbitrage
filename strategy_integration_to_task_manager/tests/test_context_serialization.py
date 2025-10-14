"""
Test ArbitrageTaskContext serialization/deserialization

Verifies that ArbitrageTaskContext can be properly serialized and restored with all
arbitrage-specific fields including active orders, positions, and nested structures.
"""

import json
import time
import pytest
from typing import Dict, Any
import sys
import os

# Add project root to path
sys.path.insert(0, '/Users/dasein/dev/cex_arbitrage/src')
sys.path.insert(0, '/Users/dasein/dev/cex_arbitrage/strategy_integration_to_task_manager/implementation')

from exchanges.structs import Symbol, Side, Order, OrderType
from trading.struct import TradingStrategyState

from arbitrage_task_context import (
    ArbitrageTaskContext, 
    ArbitrageState, 
    Position, 
    PositionState,
    TradingParameters,
    ArbitrageOpportunity
)
from arbitrage_serialization import ArbitrageTaskSerializer


def create_test_context() -> ArbitrageTaskContext:
    """Create a comprehensive test context with all arbitrage fields populated."""
    symbol = Symbol(base="BTC", quote="USDT")
    
    # Create test positions
    spot_position = Position(qty=0.1, price=50000.0, side=Side.BUY)
    futures_position = Position(qty=0.1, price=50100.0, side=Side.SELL)
    positions = PositionState(spot=spot_position, futures=futures_position)
    
    # Create test orders
    spot_order = Order(
        order_id="spot_123",
        symbol=symbol,
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=0.05,
        price=49950.0
    )
    
    futures_order = Order(
        order_id="futures_456", 
        symbol=symbol,
        side=Side.SELL,
        order_type=OrderType.LIMIT,
        quantity=0.05,
        price=50150.0
    )
    
    active_orders = {
        'spot': {'spot_123': spot_order},
        'futures': {'futures_456': futures_order}
    }
    
    # Create test opportunity
    opportunity = ArbitrageOpportunity(
        direction="spot_to_futures",
        spread_pct=0.2,
        buy_price=49950.0,
        sell_price=50150.0,
        max_quantity=0.1,
        timestamp=time.time()
    )
    
    # Create trading parameters
    params = TradingParameters(
        max_entry_cost_pct=0.6,
        min_profit_pct=0.15,
        max_hours=8.0,
        spot_fee=0.001,
        fut_fee=0.001
    )
    
    return ArbitrageTaskContext(
        task_id="arbitrage_test_123",
        state=TradingStrategyState.EXECUTING,
        symbol=symbol,
        base_position_size_usdt=100.0,
        futures_leverage=2.0,
        params=params,
        positions=positions,
        active_orders=active_orders,
        arbitrage_state=ArbitrageState.EXECUTING,
        current_opportunity=opportunity,
        position_start_time=time.time(),
        arbitrage_cycles=5,
        total_volume_usdt=500.0,
        total_profit=25.0,
        total_fees=2.5,
        min_quote_quantity={'spot': 10.0, 'futures': 10.0}
    )


def test_arbitrage_context_serialization():
    """Test that ArbitrageTaskContext can be serialized to JSON."""
    context = create_test_context()
    
    # Serialize to JSON
    json_data = ArbitrageTaskSerializer.serialize_context(context)
    
    # Should be valid JSON
    parsed_data = json.loads(json_data)
    
    # Check basic fields
    assert parsed_data['task_id'] == 'arbitrage_test_123'
    assert parsed_data['state'] == TradingStrategyState.EXECUTING.value
    assert parsed_data['base_position_size_usdt'] == 100.0
    assert parsed_data['futures_leverage'] == 2.0
    
    # Check arbitrage-specific fields
    assert parsed_data['arbitrage_state'] == ArbitrageState.EXECUTING.value
    assert parsed_data['arbitrage_cycles'] == 5
    assert parsed_data['total_volume_usdt'] == 500.0
    assert parsed_data['total_profit'] == 25.0
    assert parsed_data['total_fees'] == 2.5
    
    # Check symbol serialization
    assert parsed_data['symbol']['base'] == 'BTC'
    assert parsed_data['symbol']['quote'] == 'USDT'
    
    # Check positions
    assert parsed_data['positions']['spot']['qty'] == 0.1
    assert parsed_data['positions']['spot']['price'] == 50000.0
    assert parsed_data['positions']['spot']['side'] == Side.BUY.value
    
    assert parsed_data['positions']['futures']['qty'] == 0.1
    assert parsed_data['positions']['futures']['price'] == 50100.0
    assert parsed_data['positions']['futures']['side'] == Side.SELL.value
    
    # Check active orders
    assert 'active_orders' in parsed_data
    assert 'spot' in parsed_data['active_orders']
    assert 'futures' in parsed_data['active_orders']
    assert 'spot_123' in parsed_data['active_orders']['spot']
    assert 'futures_456' in parsed_data['active_orders']['futures']
    
    # Check opportunity
    assert parsed_data['current_opportunity']['direction'] == 'spot_to_futures'
    assert parsed_data['current_opportunity']['spread_pct'] == 0.2
    assert parsed_data['current_opportunity']['buy_price'] == 49950.0
    assert parsed_data['current_opportunity']['sell_price'] == 50150.0
    
    # Check parameters
    assert parsed_data['params']['max_entry_cost_pct'] == 0.6
    assert parsed_data['params']['min_profit_pct'] == 0.15
    assert parsed_data['params']['max_hours'] == 8.0
    
    # Check metadata
    assert '_persisted_at' in parsed_data
    assert '_schema_version' in parsed_data


def test_arbitrage_context_deserialization():
    """Test that ArbitrageTaskContext can be restored from JSON."""
    original_context = create_test_context()
    
    # Serialize then deserialize
    json_data = ArbitrageTaskSerializer.serialize_context(original_context)
    restored_context = ArbitrageTaskSerializer.deserialize_context(json_data, ArbitrageTaskContext)
    
    # Check basic fields
    assert restored_context.task_id == original_context.task_id
    assert restored_context.state == original_context.state
    assert restored_context.symbol.base == original_context.symbol.base
    assert restored_context.symbol.quote == original_context.symbol.quote
    assert restored_context.base_position_size_usdt == original_context.base_position_size_usdt
    assert restored_context.futures_leverage == original_context.futures_leverage
    
    # Check arbitrage-specific fields
    assert restored_context.arbitrage_state == original_context.arbitrage_state
    assert restored_context.arbitrage_cycles == original_context.arbitrage_cycles
    assert restored_context.total_volume_usdt == original_context.total_volume_usdt
    assert restored_context.total_profit == original_context.total_profit
    assert restored_context.total_fees == original_context.total_fees
    
    # Check positions
    assert restored_context.positions.spot.qty == original_context.positions.spot.qty
    assert restored_context.positions.spot.price == original_context.positions.spot.price
    assert restored_context.positions.spot.side == original_context.positions.spot.side
    
    assert restored_context.positions.futures.qty == original_context.positions.futures.qty
    assert restored_context.positions.futures.price == original_context.positions.futures.price
    assert restored_context.positions.futures.side == original_context.positions.futures.side
    
    # Check active orders count
    assert restored_context.get_active_order_count('spot') == 1
    assert restored_context.get_active_order_count('futures') == 1
    assert restored_context.has_active_orders() == True
    
    # Check opportunity
    if original_context.current_opportunity and restored_context.current_opportunity:
        assert restored_context.current_opportunity.direction == original_context.current_opportunity.direction
        assert restored_context.current_opportunity.spread_pct == original_context.current_opportunity.spread_pct
        assert restored_context.current_opportunity.buy_price == original_context.current_opportunity.buy_price
        assert restored_context.current_opportunity.sell_price == original_context.current_opportunity.sell_price
    
    # Check parameters
    assert restored_context.params.max_entry_cost_pct == original_context.params.max_entry_cost_pct
    assert restored_context.params.min_profit_pct == original_context.params.min_profit_pct
    assert restored_context.params.max_hours == original_context.params.max_hours


def test_arbitrage_context_evolution():
    """Test that ArbitrageTaskContext evolution works correctly."""
    context = create_test_context()
    
    # Test basic field evolution
    evolved_context = context.evolve(
        arbitrage_cycles=10,
        total_volume_usdt=1000.0,
        arbitrage_state=ArbitrageState.MONITORING
    )
    
    assert evolved_context.arbitrage_cycles == 10
    assert evolved_context.total_volume_usdt == 1000.0
    assert evolved_context.arbitrage_state == ArbitrageState.MONITORING
    
    # Original context should be unchanged
    assert context.arbitrage_cycles == 5
    assert context.total_volume_usdt == 500.0
    assert context.arbitrage_state == ArbitrageState.EXECUTING
    
    # Test dict field evolution (Django-style)
    evolved_context = context.evolve(
        min_quote_quantity__spot=20.0,
        active_orders__spot={}  # Clear spot orders
    )
    
    assert evolved_context.min_quote_quantity['spot'] == 20.0
    assert len(evolved_context.active_orders['spot']) == 0
    assert len(evolved_context.active_orders['futures']) == 1  # Unchanged


def test_empty_arbitrage_context_serialization():
    """Test serialization of minimal ArbitrageTaskContext."""
    symbol = Symbol(base="ETH", quote="USDT")
    
    context = ArbitrageTaskContext(
        task_id="minimal_test",
        symbol=symbol
    )
    
    # Should serialize without error
    json_data = ArbitrageTaskSerializer.serialize_context(context)
    parsed_data = json.loads(json_data)
    
    # Check defaults
    assert parsed_data['arbitrage_state'] == ArbitrageState.IDLE.value
    assert parsed_data['arbitrage_cycles'] == 0
    assert parsed_data['total_volume_usdt'] == 0.0
    assert parsed_data['base_position_size_usdt'] == 20.0
    assert parsed_data['active_orders'] == {'spot': {}, 'futures': {}}
    
    # Should deserialize correctly
    restored_context = ArbitrageTaskSerializer.deserialize_context(json_data, ArbitrageTaskContext)
    assert restored_context.symbol.base == "ETH"
    assert restored_context.symbol.quote == "USDT"
    assert restored_context.arbitrage_state == ArbitrageState.IDLE
    assert not restored_context.has_active_orders()
    assert not restored_context.positions.has_positions


if __name__ == "__main__":
    print("Testing ArbitrageTaskContext serialization...")
    
    test_arbitrage_context_serialization()
    print("✅ Serialization test passed")
    
    test_arbitrage_context_deserialization()
    print("✅ Deserialization test passed")
    
    test_arbitrage_context_evolution()
    print("✅ Evolution test passed")
    
    test_empty_arbitrage_context_serialization()
    print("✅ Empty context test passed")
    
    print("🎉 All ArbitrageTaskContext tests passed!")