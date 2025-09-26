"""
Integration tests for Gate.io composite exchange implementations.

Tests verify the composite pattern implementation following the same patterns
as MEXC but adapted for Gate.io-specific features.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from exchanges.integrations.gateio.gateio_composite_public import GateioCompositePublicExchange
from exchanges.integrations.gateio.gateio_composite_private import GateioCompositePrivateExchange
from exchanges.structs.common import Symbol, OrderBook, Order, AssetBalance, BookTicker, Trade
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs import Side, OrderType, OrderStatus
from config.structs import ExchangeConfig
from infrastructure.logging import HFTLoggerFactory


class TestGateioCompositePublicExchange:
    """Test Gate.io public composite exchange implementation."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return ExchangeConfig(
            name="gateio_spot",
            base_url="https://api.gateio.ws",
            websocket_url="wss://api.gateio.ws/ws/v4/"
        )

    @pytest.fixture
    def logger(self):
        """Create test logger."""
        return HFTLoggerFactory.create_logger("test_gateio", "DEBUG")

    @pytest.fixture
    def exchange(self, config, logger):
        """Create Gate.io public composite exchange instance."""
        return GateioCompositePublicExchange(config, logger)

    @pytest.mark.asyncio
    async def test_factory_methods(self, exchange):
        """Test factory methods return correct client types."""
        # Test public REST factory
        public_rest = await exchange._create_public_rest()
        assert public_rest is not None
        assert hasattr(public_rest, 'get_orderbook')
        assert hasattr(public_rest, 'get_exchange_info')

        # Test WebSocket factory with mock handlers
        mock_handlers = Mock()
        public_ws = await exchange._create_public_ws_with_handlers(mock_handlers)
        assert public_ws is not None
        assert hasattr(public_ws, 'initialize')

    @pytest.mark.asyncio
    async def test_websocket_handler_creation(self, exchange):
        """Test WebSocket handler creation and configuration."""
        handlers = await exchange._get_websocket_handlers()
        
        assert handlers is not None
        assert handlers.orderbook_handler is not None
        assert handlers.ticker_handler is not None
        assert handlers.trades_handler is not None
        assert handlers.book_ticker_handler is not None

    @pytest.mark.asyncio
    async def test_orderbook_handler(self, exchange):
        """Test orderbook update handling."""
        symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        orderbook = OrderBook(
            symbol=symbol,
            bids=[],
            asks=[],
            timestamp=1234567890
        )

        # Mock the parent method
        with patch.object(exchange.__class__.__bases__[0], '_handle_orderbook', new_callable=AsyncMock) as mock_parent:
            await exchange._handle_orderbook(orderbook)
            mock_parent.assert_called_once_with(orderbook)

    @pytest.mark.asyncio
    async def test_book_ticker_handler(self, exchange):
        """Test book ticker update handling."""
        symbol = Symbol(base=AssetName("ETH"), quote=AssetName("USDT"))
        book_ticker = BookTicker(
            symbol=symbol,
            bid_price=2000.0,
            bid_quantity=1.5,
            ask_price=2001.0,
            ask_quantity=2.0,
            timestamp=1234567890
        )

        # Mock the parent method
        with patch.object(exchange.__class__.__bases__[0], '_handle_book_ticker', new_callable=AsyncMock) as mock_parent:
            await exchange._handle_book_ticker(book_ticker)
            mock_parent.assert_called_once_with(book_ticker)

    @pytest.mark.asyncio
    async def test_initialization_lifecycle(self, exchange):
        """Test complete initialization lifecycle."""
        symbols = [Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))]
        
        # Mock dependencies to avoid real network calls
        with patch.object(exchange, '_create_public_rest') as mock_rest, \
             patch.object(exchange, '_load_symbols_info') as mock_symbols, \
             patch.object(exchange, '_load_initial_orderbooks') as mock_orderbooks, \
             patch.object(exchange, '_initialize_best_bid_ask_from_rest') as mock_best_bid_ask, \
             patch.object(exchange, '_initialize_public_websocket') as mock_ws:
            
            mock_rest.return_value = AsyncMock()
            mock_symbols.return_value = None
            mock_orderbooks.return_value = None
            mock_best_bid_ask.return_value = None
            mock_ws.return_value = None

            await exchange.initialize(symbols)
            
            assert exchange._initialized is True
            assert symbols[0] in exchange._active_symbols


class TestGateioCompositePrivateExchange:
    """Test Gate.io private composite exchange implementation."""

    @pytest.fixture
    def config(self):
        """Create test configuration with credentials."""
        config = ExchangeConfig(
            name="gateio_spot",
            base_url="https://api.gateio.ws",
            websocket_url="wss://api.gateio.ws/ws/v4/"
        )
        # Mock credentials
        config.api_key = "test_key"
        config.secret = "test_secret"
        return config

    @pytest.fixture
    def logger(self):
        """Create test logger."""
        return HFTLoggerFactory.create_logger("test_gateio_private", "DEBUG")

    @pytest.fixture
    def exchange(self, config, logger):
        """Create Gate.io private composite exchange instance."""
        return GateioCompositePrivateExchange(config, logger)

    @pytest.mark.asyncio
    async def test_factory_methods(self, exchange):
        """Test factory methods return correct client types."""
        # Test private REST factory
        private_rest = await exchange._create_private_rest()
        assert private_rest is not None
        assert hasattr(private_rest, 'place_order')
        assert hasattr(private_rest, 'cancel_order')
        assert hasattr(private_rest, 'get_balance')

        # Test WebSocket factory with mock handlers
        mock_handlers = Mock()
        private_ws = await exchange._create_private_ws_with_handlers(mock_handlers)
        assert private_ws is not None
        assert hasattr(private_ws, 'initialize')

    @pytest.mark.asyncio
    async def test_websocket_handler_creation(self, exchange):
        """Test private WebSocket handler creation."""
        handlers = await exchange._get_websocket_handlers()
        
        assert handlers is not None
        assert handlers.order_handler is not None
        assert handlers.balance_handler is not None
        assert handlers.execution_handler is not None

    @pytest.mark.asyncio
    async def test_order_handler(self, exchange):
        """Test order update handling."""
        symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        order = Order(
            symbol=symbol,
            order_id=OrderId("12345"),
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
            status=OrderStatus.FILLED,
            filled_quantity=1.0,
            timestamp=1234567890
        )

        await exchange._order_handler(order)
        
        # Check order was processed correctly
        assert symbol in exchange._executed_orders
        assert order.order_id in exchange._executed_orders[symbol]

    @pytest.mark.asyncio
    async def test_balance_handler(self, exchange):
        """Test balance update handling."""
        balances = {
            AssetName("BTC"): AssetBalance(
                asset=AssetName("BTC"),
                available=1.5,
                locked=0.0,
                total=1.5
            ),
            AssetName("USDT"): AssetBalance(
                asset=AssetName("USDT"),
                available=75000.0,
                locked=0.0,
                total=75000.0
            )
        }

        await exchange._balance_handler(balances)
        
        # Check balances were updated
        current_balances = exchange.balances
        assert AssetName("BTC") in current_balances
        assert AssetName("USDT") in current_balances
        assert current_balances[AssetName("BTC")].available == 1.5

    @pytest.mark.asyncio
    async def test_execution_handler(self, exchange):
        """Test trade execution handling."""
        symbol = Symbol(base=AssetName("ETH"), quote=AssetName("USDT"))
        trade = Trade(
            symbol=symbol,
            side=Side.SELL,
            quantity=2.0,
            price=2000.0,
            timestamp=1234567890,
            is_maker=True
        )

        # Should not raise any exceptions
        await exchange._execution_handler(trade)

    @pytest.mark.asyncio
    async def test_thread_safe_properties(self, exchange):
        """Test thread-safe property access."""
        # Test empty state
        balances = exchange.balances
        open_orders = exchange.open_orders
        
        assert isinstance(balances, dict)
        assert isinstance(open_orders, dict)
        
        # Test with some data
        test_balance = AssetBalance(
            asset=AssetName("BTC"),
            available=1.0,
            locked=0.0,
            total=1.0
        )
        exchange._balances[AssetName("BTC")] = test_balance
        
        # Properties should return copies, not references
        balances_copy = exchange.balances
        assert AssetName("BTC") in balances_copy
        
        # Modifying the copy shouldn't affect internal state
        balances_copy.clear()
        assert AssetName("BTC") in exchange._balances

    @pytest.mark.asyncio
    async def test_trading_operations_delegation(self, exchange):
        """Test that trading operations delegate to REST client."""
        symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        
        # Mock the private REST client
        mock_rest = AsyncMock()
        exchange._private_rest = mock_rest
        
        # Test limit order
        await exchange.place_limit_order(symbol, Side.BUY, 1.0, 50000.0)
        mock_rest.place_order.assert_called_once_with(symbol, Side.BUY, OrderType.LIMIT, 1.0, 50000.0)
        
        # Test market order
        mock_rest.reset_mock()
        await exchange.place_market_order(symbol, Side.SELL, 0.5)
        mock_rest.place_market_order.assert_called_once_with(symbol, Side.SELL, OrderType.MARKET, 0.5)
        
        # Test cancel order
        mock_rest.reset_mock()
        order_id = OrderId("12345")
        await exchange.cancel_order(symbol, order_id)
        mock_rest.cancel_order.assert_called_once_with(symbol, order_id)

    @pytest.mark.asyncio
    async def test_withdrawal_operations_delegation(self, exchange):
        """Test that withdrawal operations delegate to REST client."""
        # Mock the private REST client
        mock_rest = AsyncMock()
        exchange._private_rest = mock_rest
        
        # Test withdrawal
        withdrawal_request = WithdrawalRequest(
            asset=AssetName("BTC"),
            amount=0.1,
            address="bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
        )
        await exchange.withdraw(withdrawal_request)
        mock_rest.submit_withdrawal.assert_called_once_with(withdrawal_request)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])