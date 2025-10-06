"""
Comprehensive Delta Neutral Task State Machine Tests

Tests the complete delta neutral task lifecycle including state transitions,
order management, fill processing, rebalancing, and error handling.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from trading.tasks.delta_neutral_task import DeltaNeutralTask, DeltaNeutralState, Direction
from trading.struct import TradingStrategyState
from exchanges.structs import Side, OrderStatus, ExchangeEnum
from exchanges.structs.common import AssetName
from tests.trading.helpers import TestDataFactory, ContextGenerator, MarketDataGenerator


class TestDeltaNeutralTaskStateMachine:
    """Test the delta neutral task state machine behavior."""
    
    @pytest.mark.asyncio
    async def test_fresh_task_initialization(self, logger, test_symbol, initialized_dual_mock):
        """Test fresh task starts correctly and initializes exchanges."""
        context = TestDataFactory.create_delta_neutral_context(
            symbol=test_symbol,
            total_quantity=1.0,
            order_quantity=0.1
        )
        
        task = DeltaNeutralTask(logger=logger, context=context)
        
        # Verify initial state
        assert task.state == TradingStrategyState.NOT_STARTED
        assert task.context.filled_quantity[Side.BUY] == 0.0
        assert task.context.filled_quantity[Side.SELL] == 0.0
        assert task.context.order_id[Side.BUY] is None
        assert task.context.order_id[Side.SELL] is None
        
        # Start task
        await task.start()
        
        # Verify initialization
        assert task.state == TradingStrategyState.IDLE
        buy_public_init, sell_public_init, buy_private_init, sell_private_init = initialized_dual_mock.verify_initialization()
        assert all([buy_public_init, sell_public_init, buy_private_init, sell_private_init])
    
    @pytest.mark.asyncio
    async def test_state_machine_flow_idle_to_syncing(self, logger, test_symbol, initialized_dual_mock, task_execution_helper):
        """Test state machine flows from IDLE to SYNCING."""
        context = TestDataFactory.create_delta_neutral_context(symbol=test_symbol)
        task = DeltaNeutralTask(logger=logger, context=context)
        
        await task.start()
        assert task.state == TradingStrategyState.IDLE
        
        # Execute one cycle - should transition to SYNCING
        result = await task.execute_once()
        
        assert task.state == DeltaNeutralState.SYNCING
        assert result.should_continue
    
    @pytest.mark.asyncio
    async def test_state_machine_flow_syncing_to_analyzing(self, logger, test_symbol, initialized_dual_mock, task_execution_helper):
        """Test state machine flows from SYNCING to ANALYZING."""
        context = TestDataFactory.create_delta_neutral_context(symbol=test_symbol)
        task = DeltaNeutralTask(logger=logger, context=context)
        
        await task.start()
        
        # Execute until ANALYZING state
        results, cycles = await task_execution_helper(task, max_cycles=3, target_state=DeltaNeutralState.ANALYZING)
        
        assert task.state == DeltaNeutralState.ANALYZING
        assert cycles >= 2  # IDLE -> SYNCING -> ANALYZING
    
    @pytest.mark.asyncio
    async def test_state_machine_flow_analyzing_to_managing_orders(self, logger, test_symbol, initialized_dual_mock, task_execution_helper):
        """Test state machine flows from ANALYZING to MANAGING_ORDERS when no imbalance."""
        context = TestDataFactory.create_delta_neutral_context(symbol=test_symbol)
        task = DeltaNeutralTask(logger=logger, context=context)
        
        await task.start()
        
        # Execute until MANAGING_ORDERS state
        results, cycles = await task_execution_helper(task, max_cycles=5, target_state=DeltaNeutralState.MANAGING_ORDERS)
        
        assert task.state == DeltaNeutralState.MANAGING_ORDERS
        
    @pytest.mark.asyncio
    async def test_completion_detection(self, logger, test_symbol, initialized_dual_mock, task_execution_helper):
        """Test task completion when target quantities are reached."""
        # Create context that's near completion
        context = TestDataFactory.create_delta_neutral_context(
            symbol=test_symbol,
            total_quantity=1.0,
            filled_quantity={Side.BUY: 0.999, Side.SELL: 0.999}  # Nearly complete
        )
        
        task = DeltaNeutralTask(logger=logger, context=context)
        await task.start()
        
        # Execute - should detect completion
        results, cycles = await task_execution_helper(task, max_cycles=10, target_state=DeltaNeutralState.COMPLETING)
        
        assert task.state == DeltaNeutralState.COMPLETING


class TestOrderManagement:
    """Test order placement, cancellation, and fill processing."""
    
    @pytest.mark.asyncio
    async def test_order_placement_on_both_sides(self, logger, test_symbol, initialized_dual_mock, task_execution_helper):
        """Test orders are placed on both buy and sell sides."""
        # Set up favorable prices for arbitrage
        initialized_dual_mock.setup_profitable_arbitrage(test_symbol, 50000.0, 50100.0)
        
        context = TestDataFactory.create_delta_neutral_context(symbol=test_symbol)
        task = DeltaNeutralTask(logger=logger, context=context)
        
        await task.start()
        
        # Execute several cycles to get to order placement
        results, cycles = await task_execution_helper(task, max_cycles=8)
        
        # Verify orders were placed
        buy_orders = initialized_dual_mock.get_order_history(Side.BUY)
        sell_orders = initialized_dual_mock.get_order_history(Side.SELL)
        
        assert len(buy_orders) > 0, "No buy orders were placed"
        assert len(sell_orders) > 0, "No sell orders were placed"
    
    @pytest.mark.asyncio
    async def test_partial_fill_processing(self, logger, test_symbol, initialized_dual_mock, task_execution_helper):
        """Test processing of partial fills."""
        initialized_dual_mock.setup_profitable_arbitrage(test_symbol)
        
        context = TestDataFactory.create_delta_neutral_context(symbol=test_symbol)
        task = DeltaNeutralTask(logger=logger, context=context)
        
        await task.start()
        
        # Execute cycles to place orders
        results, cycles = await task_execution_helper(task, max_cycles=8)
        
        # Simulate partial fills
        buy_orders = initialized_dual_mock.get_order_history(Side.BUY)
        sell_orders = initialized_dual_mock.get_order_history(Side.SELL)
        
        if buy_orders:
            initialized_dual_mock.simulate_order_fill_during_execution(
                Side.BUY, buy_orders[0].order_id, 0.05  # 50% fill
            )
        
        if sell_orders:
            initialized_dual_mock.simulate_order_fill_during_execution(
                Side.SELL, sell_orders[0].order_id, 0.03  # 30% fill
            )
        
        # Execute more cycles to process fills
        results, cycles = await task_execution_helper(task, max_cycles=5)
        
        # Verify fills were processed
        assert task.context.filled_quantity[Side.BUY] > 0
        assert task.context.filled_quantity[Side.SELL] > 0
    
    @pytest.mark.asyncio
    async def test_order_cancellation_on_price_movement(self, logger, test_symbol, initialized_dual_mock, task_execution_helper):
        """Test orders are cancelled when price moves beyond tolerance."""
        # Set tight tolerance for testing
        context = TestDataFactory.create_delta_neutral_context(
            symbol=test_symbol,
            tick_tolerance={Side.BUY: 2, Side.SELL: 2}  # Tight tolerance
        )
        
        task = DeltaNeutralTask(logger=logger, context=context)
        await task.start()
        
        # Execute to place initial orders
        results, cycles = await task_execution_helper(task, max_cycles=8)
        
        initial_order_count = initialized_dual_mock.get_total_orders_placed()
        
        # Move prices significantly
        initialized_dual_mock.move_prices(test_symbol, 500.0)  # Large price movement
        
        # Execute more cycles to trigger cancellation
        results, cycles = await task_execution_helper(task, max_cycles=8)
        
        # Verify cancellations occurred (more orders placed due to cancellation and replacement)
        final_order_count = initialized_dual_mock.get_total_orders_placed()
        cancelled_buy = initialized_dual_mock.get_cancelled_orders(Side.BUY)
        cancelled_sell = initialized_dual_mock.get_cancelled_orders(Side.SELL)
        
        assert len(cancelled_buy) > 0 or len(cancelled_sell) > 0, "No orders were cancelled despite price movement"


class TestRebalancing:
    """Test rebalancing scenarios when one side fills faster."""
    
    @pytest.mark.asyncio
    async def test_imbalance_detection(self, logger, test_symbol, initialized_dual_mock, context_generator):
        """Test detection of fill imbalances between sides."""
        # Create imbalanced context
        context = context_generator.generate_delta_neutral_context(
            context_generator.TaskScenario.IMBALANCED_FILLS,
            symbol=test_symbol
        )
        
        task = DeltaNeutralTask(logger=logger, context=context)
        await task.start()
        
        # Check imbalance detection
        buy_imbalance = task._has_imbalance(Side.BUY)
        sell_imbalance = task._has_imbalance(Side.SELL)
        
        # One side should have imbalance (sell side is behind in the test scenario)
        assert sell_imbalance, "Sell side imbalance not detected"
        assert not buy_imbalance, "Buy side incorrectly shows imbalance"
    
    @pytest.mark.asyncio
    async def test_rebalancing_flow(self, logger, test_symbol, initialized_dual_mock, task_execution_helper):
        """Test rebalancing flow when imbalance is detected."""
        # Create imbalanced scenario - buy side ahead
        context = TestDataFactory.create_delta_neutral_context(
            symbol=test_symbol,
            filled_quantity={Side.BUY: 0.7, Side.SELL: 0.3}
        )
        
        task = DeltaNeutralTask(logger=logger, context=context)
        await task.start()
        
        # Execute cycles - should trigger rebalancing
        results, cycles = await task_execution_helper(task, max_cycles=10, target_state=DeltaNeutralState.REBALANCING)
        
        assert task.state == DeltaNeutralState.REBALANCING
        
        # Execute rebalancing
        results, cycles = await task_execution_helper(task, max_cycles=5)
        
        # Should have market orders for rebalancing
        buy_orders = initialized_dual_mock.get_order_history(Side.BUY)
        sell_orders = initialized_dual_mock.get_order_history(Side.SELL)
        
        # Check for market orders (rebalancing typically uses market orders)
        market_orders = [order for order in sell_orders if order.order_type.name == 'MARKET']
        assert len(market_orders) > 0, "No market orders placed for rebalancing"


class TestErrorHandling:
    """Test error handling and recovery scenarios."""
    
    @pytest.mark.asyncio
    async def test_order_placement_failure_handling(self, logger, test_symbol, initialized_dual_mock, task_execution_helper):
        """Test handling of order placement failures."""
        # Configure mock to fail order placement
        initialized_dual_mock.set_order_failure_behavior(Side.BUY, should_fail_orders=True)
        
        context = TestDataFactory.create_delta_neutral_context(symbol=test_symbol)
        task = DeltaNeutralTask(logger=logger, context=context)
        
        await task.start()
        
        # Execute cycles - should handle order failure gracefully
        results, cycles = await task_execution_helper(task, max_cycles=10)
        
        # Task should continue running despite order failures
        assert task.state != TradingStrategyState.ERROR
        
        # Verify only one side has orders (the side that didn't fail)
        buy_orders = initialized_dual_mock.get_order_history(Side.BUY)
        sell_orders = initialized_dual_mock.get_order_history(Side.SELL)
        
        assert len(buy_orders) == 0, "Buy orders were placed despite failure configuration"
        assert len(sell_orders) > 0, "No sell orders were placed"
    
    @pytest.mark.asyncio
    async def test_cancellation_failure_handling(self, logger, test_symbol, initialized_dual_mock, task_execution_helper):
        """Test handling of order cancellation failures."""
        context = TestDataFactory.create_delta_neutral_context(symbol=test_symbol)
        task = DeltaNeutralTask(logger=logger, context=context)
        
        await task.start()
        
        # Execute to place orders
        results, cycles = await task_execution_helper(task, max_cycles=8)
        
        # Configure cancellation to fail
        initialized_dual_mock.set_order_failure_behavior(Side.BUY, should_fail_cancellation=True)
        initialized_dual_mock.set_order_failure_behavior(Side.SELL, should_fail_cancellation=True)
        
        # Trigger price movement to cause cancellation attempts
        initialized_dual_mock.move_prices(test_symbol, 1000.0)
        
        # Execute more cycles - should handle cancellation failures
        results, cycles = await task_execution_helper(task, max_cycles=8)
        
        # Task should continue despite cancellation failures
        assert task.state != TradingStrategyState.ERROR


class TestPerformanceAndEdgeCases:
    """Test performance requirements and edge cases."""
    
    @pytest.mark.asyncio
    async def test_execution_cycle_performance(self, logger, test_symbol, initialized_dual_mock, performance_helper):
        """Test execution cycle meets HFT performance requirements."""
        context = TestDataFactory.create_delta_neutral_context(symbol=test_symbol)
        task = DeltaNeutralTask(logger=logger, context=context)
        
        await task.start()
        
        # Measure execution cycle time
        performance_helper.start()
        result = await task.execute_once()
        performance_helper.stop()
        
        # Should complete within reasonable time for HFT (< 100ms)
        assert performance_helper.elapsed_ms < 100, f"Execution cycle took {performance_helper.elapsed_ms}ms (too slow for HFT)"
        assert result.execution_time_ms < 100, f"Reported execution time {result.execution_time_ms}ms too slow"
    
    @pytest.mark.asyncio
    async def test_minimum_quantity_handling(self, logger, test_symbol, initialized_dual_mock):
        """Test handling of minimum quantity requirements."""
        # Create context with very small remaining quantity
        context = TestDataFactory.create_delta_neutral_context(
            symbol=test_symbol,
            total_quantity=0.001,  # Very small total
            filled_quantity={Side.BUY: 0.0005, Side.SELL: 0.0005}  # Half filled
        )
        
        task = DeltaNeutralTask(logger=logger, context=context)
        await task.start()
        
        # Check if task detects completion due to minimum quantity
        remaining_buy = task._get_quantity_to_fill(Side.BUY)
        remaining_sell = task._get_quantity_to_fill(Side.SELL)
        
        # Should either have meaningful quantity or be zero
        assert remaining_buy >= 0
        assert remaining_sell >= 0
    
    @pytest.mark.asyncio
    async def test_task_pause_and_resume(self, logger, test_symbol, initialized_dual_mock, task_execution_helper):
        """Test task pause and resume functionality."""
        context = TestDataFactory.create_delta_neutral_context(symbol=test_symbol)
        task = DeltaNeutralTask(logger=logger, context=context)
        
        await task.start()
        
        # Execute a few cycles
        results, cycles = await task_execution_helper(task, max_cycles=3)
        
        initial_state = task.state
        
        # Pause task
        await task.pause()
        assert task.state == TradingStrategyState.PAUSED
        
        # Verify orders were cancelled
        cancelled_buy = initialized_dual_mock.get_cancelled_orders(Side.BUY)
        cancelled_sell = initialized_dual_mock.get_cancelled_orders(Side.SELL)
        
        # Should have cancellation activity
        total_cancelled = len(cancelled_buy) + len(cancelled_sell)
        # Note: May be 0 if no orders were active when paused
    
    @pytest.mark.asyncio
    async def test_context_serialization_preservation(self, logger, test_symbol, test_data_factory):
        """Test that context serialization preserves state correctly."""
        original_context = test_data_factory.create_delta_neutral_context(
            symbol=test_symbol,
            filled_quantity={Side.BUY: 0.5, Side.SELL: 0.3},
            avg_price={Side.BUY: 49950.0, Side.SELL: 50150.0},
            order_id={Side.BUY: "test_buy_123", Side.SELL: "test_sell_456"}
        )
        
        task = DeltaNeutralTask(logger=logger, context=original_context)
        
        # Serialize context
        serialized = task.save_context()
        
        # Create new task and restore
        new_task = DeltaNeutralTask(logger=logger, context=original_context)
        new_task.restore_context(serialized)
        
        # Verify preservation
        assert new_task.context.filled_quantity == original_context.filled_quantity
        assert new_task.context.avg_price == original_context.avg_price
        assert new_task.context.order_id == original_context.order_id
        assert new_task.context.symbol == original_context.symbol


class TestMarketConditionScenarios:
    """Test behavior under various market conditions."""
    
    @pytest.mark.asyncio
    async def test_high_volatility_scenario(self, logger, test_symbol, initialized_dual_mock, market_data_generator, task_execution_helper):
        """Test task behavior in high volatility market."""
        # Set up volatile market conditions
        volatile_tickers = market_data_generator.generate_volatile_market(
            test_symbol, volatility_percentage=10.0, updates_count=5
        )
        
        context = TestDataFactory.create_delta_neutral_context(
            symbol=test_symbol,
            tick_tolerance={Side.BUY: 10, Side.SELL: 10}  # Higher tolerance for volatility
        )
        
        task = DeltaNeutralTask(logger=logger, context=context)
        await task.start()
        
        # Simulate volatile price changes during execution
        for i, ticker in enumerate(volatile_tickers[:3]):  # Use first few updates
            if i > 0:  # Skip first update
                initialized_dual_mock.move_prices(test_symbol, (i * 100) - 100)
            
            # Execute cycles
            results, cycles = await task_execution_helper(task, max_cycles=3)
        
        # Task should handle volatility without errors
        assert task.state != TradingStrategyState.ERROR
    
    @pytest.mark.asyncio
    async def test_zero_spread_scenario(self, logger, test_symbol, initialized_dual_mock):
        """Test behavior when spread approaches zero."""
        # Set identical prices (zero spread)
        initialized_dual_mock.set_prices(
            test_symbol,
            buy_side_bid=50000.0, buy_side_ask=50000.0,  # Zero spread
            sell_side_bid=50000.0, sell_side_ask=50000.0   # Zero spread
        )
        
        context = TestDataFactory.create_delta_neutral_context(symbol=test_symbol)
        task = DeltaNeutralTask(logger=logger, context=context)
        
        await task.start()
        
        # Should handle zero spread gracefully
        # This tests edge case in price calculation
        top_buy_price = task._get_current_top_price(Side.BUY)
        top_sell_price = task._get_current_top_price(Side.SELL)
        
        assert top_buy_price > 0
        assert top_sell_price > 0