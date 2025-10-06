"""
Simple Delta Neutral Task State Machine Tests

Working tests for the delta neutral task without complex async fixtures.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from trading.tasks.delta_neutral_task import DeltaNeutralTask, DeltaNeutralState, Direction, DeltaNeutralTaskContext
from trading.struct import TradingStrategyState
from exchanges.structs import Side, OrderStatus, ExchangeEnum, Symbol
from exchanges.structs.common import AssetName
from infrastructure.logging import get_logger


@pytest.fixture
def test_symbol():
    """Provide test symbol."""
    return Symbol(base=AssetName('BTC'), quote=AssetName('USDT'))


@pytest.fixture
def logger():
    """Provide test logger."""
    return get_logger("test_delta_neutral_simple")


@pytest.fixture
def simple_context(test_symbol):
    """Create a simple delta neutral context."""
    return DeltaNeutralTaskContext(
        symbol=test_symbol,
        total_quantity=1.0,
        order_quantity=0.1,
        exchange_names={
            Side.BUY: ExchangeEnum.GATEIO,
            Side.SELL: ExchangeEnum.MEXC
        },
        direction=Direction.NONE,
        filled_quantity={Side.BUY: 0.0, Side.SELL: 0.0},
        avg_price={Side.BUY: 0.0, Side.SELL: 0.0},
        offset_ticks={Side.BUY: 0, Side.SELL: 0},
        tick_tolerance={Side.BUY: 5, Side.SELL: 5},
        order_id={Side.BUY: None, Side.SELL: None}
    )


class TestDeltaNeutralTaskBasic:
    """Basic tests for delta neutral task without complex mocks."""

    @pytest.mark.asyncio
    async def test_context_creation(self, simple_context, test_symbol):
        """Test that context is created properly."""
        assert simple_context.symbol == test_symbol
        assert simple_context.total_quantity == 1.0
        assert simple_context.order_quantity == 0.1
        assert simple_context.exchange_names[Side.BUY] == ExchangeEnum.GATEIO
        assert simple_context.exchange_names[Side.SELL] == ExchangeEnum.MEXC
        assert simple_context.filled_quantity[Side.BUY] == 0.0
        assert simple_context.filled_quantity[Side.SELL] == 0.0

    @pytest.mark.asyncio 
    async def test_task_initialization_with_mocked_exchanges(self, logger, simple_context):
        """Test task initialization with mocked exchange creation."""
        
        # Mock the exchange factory and config functions
        with patch('trading.tasks.delta_neutral_task.get_exchange_config') as mock_config, \
             patch('trading.tasks.delta_neutral_task.DualExchange') as mock_dual_exchange:
            
            # Configure mocks
            mock_config.return_value = AsyncMock()
            mock_dual_exchange.get_instance.return_value = AsyncMock()
            
            # Create task
            task = DeltaNeutralTask(logger=logger, context=simple_context)
            
            # Verify initial state - comparing key fields since task_id gets auto-generated
            assert task.context.symbol == simple_context.symbol
            assert task.context.total_quantity == simple_context.total_quantity
            assert task.context.order_quantity == simple_context.order_quantity
            assert task.context.exchange_names == simple_context.exchange_names
            assert hasattr(task, '_exchanges')
            
            # Verify context fields
            assert task.context.filled_quantity[Side.BUY] == 0.0
            assert task.context.filled_quantity[Side.SELL] == 0.0

    @pytest.mark.asyncio
    async def test_update_side_context(self, logger, simple_context):
        """Test updating context for specific side."""
        
        with patch('trading.tasks.delta_neutral_task.get_exchange_config') as mock_config, \
             patch('trading.tasks.delta_neutral_task.DualExchange') as mock_dual_exchange:
            
            # Configure mocks to return proper objects
            mock_config.return_value = AsyncMock()
            mock_exchange_instance = AsyncMock()
            mock_dual_exchange.get_instance.return_value = mock_exchange_instance
            
            task = DeltaNeutralTask(logger=logger, context=simple_context)
            
            # Test updating filled quantity for BUY side
            task._update_side_context(Side.BUY, filled_quantity=0.5)
            assert task.context.filled_quantity[Side.BUY] == 0.5
            assert task.context.filled_quantity[Side.SELL] == 0.0  # Should remain unchanged
            
            # Test updating order_id for SELL side
            task._update_side_context(Side.SELL, order_id="test_order_123")
            assert task.context.order_id[Side.SELL] == "test_order_123"
            assert task.context.order_id[Side.BUY] is None  # Should remain unchanged

    @pytest.mark.asyncio
    async def test_quantity_calculations(self, logger, simple_context):
        """Test quantity calculation methods."""
        
        with patch('trading.tasks.delta_neutral_task.get_exchange_config') as mock_config, \
             patch('trading.tasks.delta_neutral_task.DualExchange') as mock_dual_exchange:
            
            # Configure mocks to return proper objects
            mock_config.return_value = AsyncMock()
            mock_exchange_instance = AsyncMock()
            mock_dual_exchange.get_instance.return_value = mock_exchange_instance
            
            task = DeltaNeutralTask(logger=logger, context=simple_context)
            
            # Mock symbol info and price
            mock_symbol_info = AsyncMock()
            mock_symbol_info.min_quote_quantity = 10.0
            task._symbol_info[Side.BUY] = mock_symbol_info
            task._symbol_info[Side.SELL] = mock_symbol_info
            
            # Mock price getter
            task._get_current_top_price = lambda side: 50000.0
            
            # Test minimum quantity calculation
            min_qty_buy = task._get_min_quantity(Side.BUY)
            min_qty_sell = task._get_min_quantity(Side.SELL)
            
            expected_min_qty = 10.0 / 50000.0  # min_quote_quantity / price
            assert min_qty_buy == expected_min_qty
            assert min_qty_sell == expected_min_qty
            
            # Test quantity to fill calculation
            qty_to_fill_buy = task._get_quantity_to_fill(Side.BUY)
            qty_to_fill_sell = task._get_quantity_to_fill(Side.SELL)
            
            # Should be total_quantity (1.0) - filled_quantity (0.0) = 1.0
            assert qty_to_fill_buy == 1.0
            assert qty_to_fill_sell == 1.0

    @pytest.mark.asyncio
    async def test_imbalance_detection(self, logger, simple_context):
        """Test imbalance detection logic."""
        
        with patch('trading.tasks.delta_neutral_task.get_exchange_config') as mock_config, \
             patch('trading.tasks.delta_neutral_task.DualExchange') as mock_dual_exchange:
            
            # Configure mocks to return proper objects
            mock_config.return_value = AsyncMock()
            mock_exchange_instance = AsyncMock()
            mock_dual_exchange.get_instance.return_value = mock_exchange_instance
            
            task = DeltaNeutralTask(logger=logger, context=simple_context)
            
            # Mock minimum quantity
            task._get_min_quantity = lambda side: 0.01
            
            # Test no imbalance initially
            assert not task._has_imbalance(Side.BUY)
            assert not task._has_imbalance(Side.SELL)
            
            # Create imbalance - BUY side filled more than SELL
            task._update_side_context(Side.BUY, filled_quantity=0.5)
            task._update_side_context(Side.SELL, filled_quantity=0.2)
            
            # Check imbalance calculation
            buy_sell_imbalance = task._buy_sell_imbalance()
            assert buy_sell_imbalance == 0.3  # 0.5 - 0.2
            
            # SELL side should have imbalance (needs to catch up)
            assert task._has_imbalance(Side.SELL)
            # BUY side should not have imbalance (it's ahead)
            assert not task._has_imbalance(Side.BUY)

    @pytest.mark.asyncio
    async def test_completion_detection(self, logger, simple_context):
        """Test completion detection logic."""
        
        with patch('trading.tasks.delta_neutral_task.get_exchange_config') as mock_config, \
             patch('trading.tasks.delta_neutral_task.DualExchange') as mock_dual_exchange:
            
            # Configure mocks to return proper objects
            mock_config.return_value = AsyncMock()
            mock_exchange_instance = AsyncMock()
            mock_dual_exchange.get_instance.return_value = mock_exchange_instance
            
            task = DeltaNeutralTask(logger=logger, context=simple_context)
            
            # Mock minimum quantity
            task._get_min_quantity = lambda side: 0.01
            
            # Initially not complete
            assert not task._check_completing()
            
            # Fill both sides to near completion
            task._update_side_context(Side.BUY, filled_quantity=0.999)
            task._update_side_context(Side.SELL, filled_quantity=0.999)
            
            # Should be complete (remaining < min_quantity)
            assert task._check_completing()

    @pytest.mark.asyncio
    async def test_state_transitions(self, logger, simple_context):
        """Test basic state transitions."""
        
        with patch('trading.tasks.delta_neutral_task.get_exchange_config') as mock_config, \
             patch('trading.tasks.delta_neutral_task.DualExchange') as mock_dual_exchange:
            
            # Configure mocks to return proper objects
            mock_config.return_value = AsyncMock()
            mock_exchange_instance = AsyncMock()
            mock_dual_exchange.get_instance.return_value = mock_exchange_instance
            
            task = DeltaNeutralTask(logger=logger, context=simple_context)
            
            # Test initial state
            assert task.state == TradingStrategyState.NOT_STARTED
            
            # Test state transition
            task._transition(DeltaNeutralState.SYNCING)
            assert task.state == DeltaNeutralState.SYNCING
            
            task._transition(DeltaNeutralState.ANALYZING)
            assert task.state == DeltaNeutralState.ANALYZING
            
            task._transition(DeltaNeutralState.MANAGING_ORDERS)
            assert task.state == DeltaNeutralState.MANAGING_ORDERS


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])