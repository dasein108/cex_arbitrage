"""Test the refactored TradingTaskContext hierarchy."""

import pytest
from typing import Dict, List, Tuple
import msgspec

from exchanges.structs import Symbol, Side, ExchangeEnum
from trading.struct import TradingStrategyState
from trading.tasks.base_task import (
    TradingTaskContext, 
    SingleExchangeTaskContext
)
from trading.tasks.iceberg_task import IcebergTaskContext


class MultiExchangeArbitrageContext(TradingTaskContext):
    """Example of a multi-exchange context extending base directly."""
    exchanges: List[ExchangeEnum]
    symbol: Symbol  # Same symbol across exchanges
    spreads: Dict[str, float] = msgspec.field(default_factory=dict)
    positions: Dict[str, float] = msgspec.field(default_factory=dict)


class HedgeTaskContext(TradingTaskContext):
    """Example of a hedge task context for multiple symbols."""
    exchanges: List[ExchangeEnum]
    hedge_pairs: List[Tuple[Symbol, Symbol]]
    hedge_ratios: Dict[str, float] = msgspec.field(default_factory=dict)


def test_base_context_minimal():
    """Test that base context only has minimal fields."""
    context = TradingTaskContext(
        task_id="test_123",
        state=TradingStrategyState.IDLE
    )
    
    # Base context should not have exchange or symbol
    assert not hasattr(context, 'exchange_name')
    assert not hasattr(context, 'symbol')
    assert not hasattr(context, 'side')
    assert not hasattr(context, 'order_id')
    
    # But should have base fields
    assert context.task_id == "test_123"
    assert context.state == TradingStrategyState.IDLE
    assert context.error is None
    assert context.metadata == {}


def test_single_exchange_context():
    """Test SingleExchangeTaskContext has exchange/symbol fields."""
    symbol = Symbol(base="BTC", quote="USDT")
    context = SingleExchangeTaskContext(
        exchange_name=ExchangeEnum.MEXC,
        symbol=symbol,
        side=Side.BUY,
        task_id="single_123",
        state=TradingStrategyState.EXECUTING
    )
    
    # Should have all single exchange fields
    assert context.exchange_name == ExchangeEnum.MEXC
    assert context.symbol == symbol
    assert context.side == Side.BUY
    assert context.order_id is None  # Optional field with default
    
    # Should also have base fields
    assert context.task_id == "single_123"
    assert context.state == TradingStrategyState.EXECUTING


def test_iceberg_context_inheritance():
    """Test IcebergTaskContext properly extends SingleExchangeTaskContext."""
    symbol = Symbol(base="ETH", quote="USDT")
    context = IcebergTaskContext(
        exchange_name=ExchangeEnum.GATEIO,
        symbol=symbol,
        side=Side.SELL,
        total_quantity=100.0,
        order_quantity=10.0,
        task_id="iceberg_456"
    )
    
    # Should have iceberg-specific fields
    assert context.total_quantity == 100.0
    assert context.order_quantity == 10.0
    assert context.filled_quantity == 0.0
    assert context.offset_ticks == 0
    assert context.tick_tolerance == 1
    assert context.avg_price == 0.0
    
    # Should have single exchange fields
    assert context.exchange_name == ExchangeEnum.GATEIO
    assert context.symbol == symbol
    assert context.side == Side.SELL
    
    # Should have base fields
    assert context.task_id == "iceberg_456"
    assert context.state == TradingStrategyState.NOT_STARTED


def test_multi_exchange_arbitrage_context():
    """Test multi-exchange context extending base directly."""
    symbol = Symbol(base="BTC", quote="USDT")
    context = MultiExchangeArbitrageContext(
        exchanges=[ExchangeEnum.MEXC, ExchangeEnum.GATEIO],
        symbol=symbol,
        task_id="arb_789",
        spreads={"MEXC_GATEIO": 0.001}
    )
    
    # Should have multi-exchange specific fields
    assert context.exchanges == [ExchangeEnum.MEXC, ExchangeEnum.GATEIO]
    assert context.symbol == symbol
    assert context.spreads == {"MEXC_GATEIO": 0.001}
    assert context.positions == {}
    
    # Should NOT have single exchange fields
    assert not hasattr(context, 'exchange_name')
    assert not hasattr(context, 'side')
    assert not hasattr(context, 'order_id')
    
    # Should have base fields
    assert context.task_id == "arb_789"
    assert context.state == TradingStrategyState.NOT_STARTED


def test_hedge_task_context():
    """Test hedge context for multiple symbols and exchanges."""
    btc_usdt = Symbol(base="BTC", quote="USDT")
    btc_perp = Symbol(base="BTC", quote="PERP", is_futures=True)
    
    context = HedgeTaskContext(
        exchanges=[ExchangeEnum.MEXC, ExchangeEnum.GATEIO],
        hedge_pairs=[(btc_usdt, btc_perp)],
        hedge_ratios={"BTC": 1.0},
        task_id="hedge_999"
    )
    
    # Should have hedge-specific fields
    assert context.exchanges == [ExchangeEnum.MEXC, ExchangeEnum.GATEIO]
    assert context.hedge_pairs == [(btc_usdt, btc_perp)]
    assert context.hedge_ratios == {"BTC": 1.0}
    
    # Should NOT have single exchange fields
    assert not hasattr(context, 'exchange_name')
    assert not hasattr(context, 'symbol')
    
    # Should have base fields
    assert context.task_id == "hedge_999"


def test_context_evolution():
    """Test context evolution works across hierarchy."""
    # Start with base context
    context = TradingTaskContext(task_id="evolve_test")
    assert context.state == TradingStrategyState.NOT_STARTED
    
    # Evolve state
    context2 = context.evolve(state=TradingStrategyState.EXECUTING)
    assert context2.state == TradingStrategyState.EXECUTING
    assert context.state == TradingStrategyState.NOT_STARTED  # Original unchanged
    
    # Test with SingleExchangeTaskContext
    single_context = SingleExchangeTaskContext(
        exchange_name=ExchangeEnum.MEXC,
        symbol=Symbol(base="BTC", quote="USDT"),
        task_id="single_evolve"
    )
    
    # Evolve with order_id
    single_context2 = single_context.evolve(order_id="ORDER_123", side=Side.BUY)
    assert single_context2.order_id == "ORDER_123"
    assert single_context2.side == Side.BUY
    assert single_context.order_id is None  # Original unchanged
    assert single_context.side is None


def test_serialization_base_context():
    """Test serialization of base context."""
    context = TradingTaskContext(
        task_id="serialize_base",
        state=TradingStrategyState.EXECUTING,
        metadata={"key": "value"}
    )
    
    # Serialize
    json_bytes = context.to_json()
    
    # Deserialize
    restored = TradingTaskContext.from_json(json_bytes)
    
    assert restored.task_id == context.task_id
    assert restored.state == context.state
    assert restored.metadata == context.metadata


def test_serialization_single_exchange_context():
    """Test serialization of SingleExchangeTaskContext."""
    symbol = Symbol(base="ETH", quote="USDT")
    context = SingleExchangeTaskContext(
        exchange_name=ExchangeEnum.GATEIO,
        symbol=symbol,
        side=Side.SELL,
        order_id="ORDER_456",
        task_id="serialize_single",
        state=TradingStrategyState.PAUSED
    )
    
    # Serialize
    json_bytes = context.to_json()
    
    # Deserialize
    restored = SingleExchangeTaskContext.from_json(json_bytes)
    
    assert restored.exchange_name == context.exchange_name
    assert restored.symbol.base == context.symbol.base
    assert restored.symbol.quote == context.symbol.quote
    assert restored.side == context.side
    assert restored.order_id == context.order_id
    assert restored.task_id == context.task_id
    assert restored.state == context.state


def test_serialization_iceberg_context():
    """Test serialization of IcebergTaskContext."""
    symbol = Symbol(base="SOL", quote="USDT")
    context = IcebergTaskContext(
        exchange_name=ExchangeEnum.MEXC,
        symbol=symbol,
        side=Side.BUY,
        total_quantity=1000.0,
        order_quantity=100.0,
        filled_quantity=250.0,
        avg_price=45.5,
        task_id="serialize_iceberg"
    )
    
    # Serialize using parent class method
    json_bytes = context.to_json()
    
    # Deserialize
    restored = IcebergTaskContext.from_json(json_bytes)
    
    # Check all fields preserved
    assert restored.exchange_name == context.exchange_name
    assert restored.symbol.base == context.symbol.base
    assert restored.symbol.quote == context.symbol.quote
    assert restored.side == context.side
    assert restored.total_quantity == context.total_quantity
    assert restored.order_quantity == context.order_quantity
    assert restored.filled_quantity == context.filled_quantity
    assert restored.avg_price == context.avg_price
    assert restored.task_id == context.task_id


def test_error_serialization():
    """Test error field serialization."""
    context = TradingTaskContext(
        task_id="error_test",
        state=TradingStrategyState.ERROR,
        error=ValueError("Test error message")
    )
    
    # Serialize
    json_bytes = context.to_json()
    
    # Deserialize
    restored = TradingTaskContext.from_json(json_bytes)
    
    assert restored.error is not None
    assert str(restored.error) == "Test error message"
    assert restored.state == TradingStrategyState.ERROR


if __name__ == "__main__":
    # Run all tests
    test_base_context_minimal()
    test_single_exchange_context()
    test_iceberg_context_inheritance()
    test_multi_exchange_arbitrage_context()
    test_hedge_task_context()
    test_context_evolution()
    test_serialization_base_context()
    test_serialization_single_exchange_context()
    test_serialization_iceberg_context()
    test_error_serialization()
    
    print("✅ All tests passed!")