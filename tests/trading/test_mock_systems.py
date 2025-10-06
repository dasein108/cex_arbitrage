"""
Mock System Tests

Tests for the mock exchange systems to ensure they behave correctly
and provide reliable testing infrastructure.
"""

import pytest
import asyncio

from tests.trading.mocks import DualExchangeMockSystem, MockPublicExchange, MockPrivateExchange
from tests.trading.helpers import TestDataFactory, OrderGenerator
from exchanges.structs import Symbol, ExchangeEnum, Side, OrderType, OrderStatus
from exchanges.structs.common import AssetName


class TestMockPublicExchange:
    """Test mock public exchange functionality."""
    
    @pytest.mark.asyncio
    async def test_initialization(self, test_symbol):
        """Test mock public exchange initialization."""
        mock = MockPublicExchange(ExchangeEnum.MEXC_SPOT)
        
        assert not mock.is_connected()
        assert not mock.was_initialized()
        
        await mock.initialize([test_symbol])
        
        assert mock.is_connected()
        assert mock.was_initialized()
        assert test_symbol in mock.symbols_info
        assert test_symbol in mock._book_ticker
    
    @pytest.mark.asyncio
    async def test_market_data_control(self, test_symbol):
        """Test market data manipulation."""
        mock = MockPublicExchange(ExchangeEnum.MEXC_SPOT)
        await mock.initialize([test_symbol])
        
        # Test price updates
        mock.set_book_ticker(test_symbol, 50000.0, 50001.0)
        ticker = mock._book_ticker[test_symbol]
        
        assert ticker.bid_price == 50000.0
        assert ticker.ask_price == 50001.0
        
        # Test price movement
        mock.update_price(test_symbol, 51000.0, spread=2.0)
        updated_ticker = mock._book_ticker[test_symbol]
        
        assert updated_ticker.bid_price == 50999.0  # 51000 - 1
        assert updated_ticker.ask_price == 51001.0  # 51000 + 1
    
    @pytest.mark.asyncio
    async def test_symbol_info_customization(self, test_symbol):
        """Test symbol info customization."""
        mock = MockPublicExchange(ExchangeEnum.MEXC_SPOT)
        await mock.initialize([test_symbol])
        
        # Modify symbol info
        mock.set_symbol_info(test_symbol, min_base_quantity=0.01, tick=0.1)
        
        info = mock.symbols_info[test_symbol]
        assert info.min_base_quantity == 0.01
        assert info.tick == 0.1
    
    @pytest.mark.asyncio
    async def test_cleanup(self, test_symbol):
        """Test proper cleanup."""
        mock = MockPublicExchange(ExchangeEnum.MEXC_SPOT)
        await mock.initialize([test_symbol])
        
        assert mock.is_connected()
        
        await mock.close()
        
        assert not mock.is_connected()
        assert mock.was_closed()


class TestMockPrivateExchange:
    """Test mock private exchange functionality."""
    
    @pytest.mark.asyncio
    async def test_order_placement(self, test_symbol):
        """Test order placement functionality."""
        mock = MockPrivateExchange(ExchangeEnum.MEXC_SPOT)
        await mock.initialize([test_symbol])
        
        # Place limit order
        order = await mock.place_limit_order(
            symbol=test_symbol,
            side=Side.BUY,
            quantity=0.1,
            price=50000.0
        )
        
        assert order.symbol == test_symbol
        assert order.side == Side.BUY
        assert order.quantity == 0.1
        assert order.price == 50000.0
        assert order.status == OrderStatus.NEW
        
        # Verify tracking
        placed_orders = mock.get_placed_orders()
        assert len(placed_orders) == 1
        assert placed_orders[0].order_id == order.order_id
    
    @pytest.mark.asyncio
    async def test_market_order_placement(self, test_symbol):
        """Test market order placement."""
        mock = MockPrivateExchange(ExchangeEnum.MEXC_SPOT)
        await mock.initialize([test_symbol])
        
        # Place market order
        order = await mock.place_market_order(
            symbol=test_symbol,
            side=Side.SELL,
            price=50000.0,
            quote_quantity=1000.0
        )
        
        assert order.order_type == OrderType.MARKET
        assert order.status == OrderStatus.FILLED  # Market orders fill immediately
        assert order.filled_quantity > 0
    
    @pytest.mark.asyncio
    async def test_order_cancellation(self, test_symbol):
        """Test order cancellation."""
        mock = MockPrivateExchange(ExchangeEnum.MEXC_SPOT)
        await mock.initialize([test_symbol])
        
        # Place order
        order = await mock.place_limit_order(test_symbol, Side.BUY, 0.1, 50000.0)
        
        # Cancel order
        cancelled_order = await mock.cancel_order(test_symbol, order.order_id)
        
        assert cancelled_order.status == OrderStatus.CANCELLED
        assert order.order_id in mock.get_cancelled_orders()
    
    @pytest.mark.asyncio
    async def test_fill_simulation(self, test_symbol):
        """Test order fill simulation."""
        mock = MockPrivateExchange(ExchangeEnum.MEXC_SPOT)
        await mock.initialize([test_symbol])
        
        # Place order
        order = await mock.place_limit_order(test_symbol, Side.BUY, 0.1, 50000.0)
        
        # Simulate partial fill
        mock.simulate_order_fill(order.order_id, 0.05)
        
        # Fetch updated order
        updated_order = await mock.fetch_order(test_symbol, order.order_id)
        
        assert updated_order.filled_quantity == 0.05
        assert updated_order.status == OrderStatus.PARTIALLY_FILLED
    
    @pytest.mark.asyncio
    async def test_failure_simulation(self, test_symbol):
        """Test failure behavior simulation."""
        mock = MockPrivateExchange(ExchangeEnum.MEXC_SPOT)
        await mock.initialize([test_symbol])
        
        # Configure to fail orders
        mock.set_should_fail_orders(True)
        
        with pytest.raises(Exception, match="Mock order placement failure"):
            await mock.place_limit_order(test_symbol, Side.BUY, 0.1, 50000.0)
        
        # Configure to fail cancellations
        mock.set_should_fail_orders(False)
        mock.set_should_fail_cancellation(True)
        
        order = await mock.place_limit_order(test_symbol, Side.BUY, 0.1, 50000.0)
        
        with pytest.raises(Exception, match="Mock order cancellation failure"):
            await mock.cancel_order(test_symbol, order.order_id)
    
    def test_tracking_reset(self, test_symbol):
        """Test tracking reset functionality."""
        mock = MockPrivateExchange(ExchangeEnum.MEXC_SPOT)
        
        # Simulate some activity
        mock._placed_orders = [TestDataFactory.create_order()]
        mock._cancelled_orders = ["order_123"]
        
        assert len(mock.get_placed_orders()) == 1
        assert len(mock.get_cancelled_orders()) == 1
        
        # Reset tracking
        mock.reset_tracking()
        
        assert len(mock.get_placed_orders()) == 0
        assert len(mock.get_cancelled_orders()) == 0


class TestDualExchangeMockSystem:
    """Test dual exchange mock system."""
    
    @pytest.mark.asyncio
    async def test_system_setup(self, test_symbol):
        """Test dual exchange system setup."""
        system = DualExchangeMockSystem()
        
        await system.setup([test_symbol])
        
        # Verify all exchanges are initialized
        init_status = system.verify_initialization()
        assert all(init_status)
        
        # Verify exchanges are accessible
        assert Side.BUY in system.public_exchanges
        assert Side.SELL in system.public_exchanges
        assert Side.BUY in system.private_exchanges
        assert Side.SELL in system.private_exchanges
        
        await system.teardown()
    
    @pytest.mark.asyncio
    async def test_market_scenario_setup(self, test_symbol):
        """Test market scenario setup."""
        system = DualExchangeMockSystem()
        await system.setup([test_symbol])
        
        # Test arbitrage scenario
        system.setup_profitable_arbitrage(test_symbol, 50000.0, 50100.0)
        
        buy_ticker = system.public_exchanges[Side.BUY]._book_ticker[test_symbol]
        sell_ticker = system.public_exchanges[Side.SELL]._book_ticker[test_symbol]
        
        # Buy side should have lower price
        buy_mid = (buy_ticker.bid_price + buy_ticker.ask_price) / 2
        sell_mid = (sell_ticker.bid_price + sell_ticker.ask_price) / 2
        
        assert buy_mid < sell_mid  # Profitable arbitrage
        
        await system.teardown()
    
    @pytest.mark.asyncio
    async def test_order_behavior_control(self, test_symbol):
        """Test order behavior control."""
        system = DualExchangeMockSystem()
        await system.setup([test_symbol])
        
        # Configure one side to fail
        system.set_order_failure_behavior(Side.BUY, should_fail_orders=True)
        
        # Test that configuration is applied
        buy_exchange = system.private_exchanges[Side.BUY]
        sell_exchange = system.private_exchanges[Side.SELL]
        
        # Buy side should fail
        with pytest.raises(Exception):
            await buy_exchange.place_limit_order(test_symbol, Side.BUY, 0.1, 50000.0)
        
        # Sell side should work
        order = await sell_exchange.place_limit_order(test_symbol, Side.SELL, 0.1, 50000.0)
        assert order is not None
        
        await system.teardown()
    
    @pytest.mark.asyncio
    async def test_price_movement_simulation(self, test_symbol):
        """Test price movement simulation."""
        system = DualExchangeMockSystem()
        await system.setup([test_symbol])
        
        # Get initial prices
        initial_buy = system.public_exchanges[Side.BUY]._book_ticker[test_symbol]
        initial_sell = system.public_exchanges[Side.SELL]._book_ticker[test_symbol]
        
        initial_buy_mid = (initial_buy.bid_price + initial_buy.ask_price) / 2
        initial_sell_mid = (initial_sell.bid_price + initial_sell.ask_price) / 2
        
        # Move prices
        price_change = 100.0
        system.move_prices(test_symbol, price_change)
        
        # Verify price movement
        new_buy = system.public_exchanges[Side.BUY]._book_ticker[test_symbol]
        new_sell = system.public_exchanges[Side.SELL]._book_ticker[test_symbol]
        
        new_buy_mid = (new_buy.bid_price + new_buy.ask_price) / 2
        new_sell_mid = (new_sell.bid_price + new_sell.ask_price) / 2
        
        assert abs(new_buy_mid - initial_buy_mid - price_change) < 1.0
        assert abs(new_sell_mid - initial_sell_mid - price_change) < 1.0
        
        await system.teardown()
    
    def test_patch_management(self, test_symbol):
        """Test patch management."""
        system = DualExchangeMockSystem()
        
        # Apply patches
        patches = system.patch_exchange_factory()
        
        assert len(system._active_patches) == 2  # Factory and config patches
        
        # Should be able to import patched functions
        from exchanges.exchange_factory import get_composite_implementation
        from config.config_manager import get_exchange_config
        
        # Cleanup should remove patches
        system._active_patches.clear()
    
    def test_verification_methods(self, test_symbol):
        """Test verification and tracking methods."""
        system = DualExchangeMockSystem()
        
        # Test reset functionality
        system.reset_for_new_test()
        
        assert system.get_total_orders_placed() == 0
        assert len(system.get_order_history(Side.BUY)) == 0
        assert len(system.get_order_history(Side.SELL)) == 0