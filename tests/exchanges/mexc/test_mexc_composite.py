"""Test MEXC composite exchange implementations."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from exchanges.integrations.mexc.mexc_composite_public import MexcCompositePublicExchange
from exchanges.integrations.mexc.mexc_composite_private import MexcCompositePrivateExchange
from exchanges.structs.common import Symbol, OrderBook, AssetBalance, Order
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs import Side, OrderStatus
from config.structs import ExchangeConfig
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers, PrivateWebsocketHandlers


class TestMexcCompositePublic:
    """Test MEXC public composite exchange."""
    
    @pytest.fixture
    def config(self):
        """Create test config."""
        config = MagicMock(spec=ExchangeConfig)
        config.name = "mexc"
        config.enable_websocket = True
        return config

    @pytest.fixture
    async def public_exchange(self, config):
        """Create test public exchange."""
        exchange = MexcCompositePublicExchange(config)
        yield exchange
        await exchange.close()
    
    async def test_factory_methods(self, public_exchange):
        """Test factory methods create correct clients."""
        # Mock the MEXC clients
        with patch('exchanges.integrations.mexc.mexc_composite_public.MexcPublicSpotRest') as mock_rest, \
             patch('exchanges.integrations.mexc.mexc_composite_public.MexcPublicSpotWebsocket') as mock_ws:
            
            # Test REST client creation
            rest_client = await public_exchange._create_public_rest()
            mock_rest.assert_called_once_with(public_exchange.config, public_exchange.logger)
            assert rest_client == mock_rest.return_value
            
            # Test WebSocket client creation
            handlers = PublicWebsocketHandlers(
                orderbook_handler=AsyncMock(),
                ticker_handler=AsyncMock(),
                trade_handler=AsyncMock(),
                book_ticker_handler=AsyncMock()
            )
            ws_client = await public_exchange._create_public_websocket(handlers)
            mock_ws.assert_called_once_with(
                config=public_exchange.config,
                handlers=handlers,
                logger=public_exchange.logger
            )
            assert ws_client == mock_ws.return_value

    async def test_websocket_disabled(self, config):
        """Test WebSocket creation when disabled."""
        config.enable_websocket = False
        exchange = MexcCompositePublicExchange(config)
        
        handlers = PublicWebsocketHandlers(
            orderbook_handler=AsyncMock(),
            ticker_handler=AsyncMock(),
            trade_handler=AsyncMock(),
            book_ticker_handler=AsyncMock()
        )
        
        ws_client = await exchange._create_public_websocket(handlers)
        assert ws_client is None

    async def test_websocket_handlers(self, public_exchange):
        """Test WebSocket handlers creation."""
        handlers = public_exchange._create_inner_websocket_handlers()
        
        assert isinstance(handlers, PublicWebsocketHandlers)
        assert handlers.orderbook_handler == public_exchange._handle_orderbook
        assert handlers.ticker_handler == public_exchange._handle_ticker
        assert handlers.trade_handler == public_exchange._handle_trade
        assert handlers.book_ticker_handler == public_exchange._handle_book_ticker

    async def test_orderbooks_property(self, public_exchange):
        """Test orderbooks property returns thread-safe copy."""
        # Set up internal orderbooks
        btc_usdt = Symbol('BTC', 'USDT')
        mock_orderbook = MagicMock(spec=OrderBook)
        public_exchange._orderbooks[btc_usdt] = mock_orderbook
        
        orderbooks = public_exchange.orderbooks
        
        # Should return copy, not direct reference
        assert orderbooks == {btc_usdt: mock_orderbook}
        assert orderbooks is not public_exchange._orderbooks


class TestMexcCompositePrivate:
    """Test MEXC private composite exchange."""
    
    @pytest.fixture
    def config(self):
        """Create test config with credentials."""
        config = MagicMock(spec=ExchangeConfig)
        config.name = "mexc"
        config.enable_websocket = True
        config.has_credentials.return_value = True
        return config

    @pytest.fixture
    async def private_exchange(self, config):
        """Create test private exchange."""
        exchange = MexcCompositePrivateExchange(config)
        yield exchange
        await exchange.close()
    
    async def test_factory_methods(self, private_exchange):
        """Test private factory methods create correct clients."""
        # Mock the MEXC clients
        with patch('exchanges.integrations.mexc.mexc_composite_private.MexcPrivateSpotRest') as mock_rest, \
             patch('exchanges.integrations.mexc.mexc_composite_private.MexcPrivateSpotWebsocket') as mock_ws:
            
            # Test REST client creation
            rest_client = await private_exchange._create_private_rest()
            mock_rest.assert_called_once_with(private_exchange.config, private_exchange.logger)
            assert rest_client == mock_rest.return_value
            
            # Test WebSocket client creation
            ws_client = await private_exchange._create_private_websocket()
            mock_ws.assert_called_once_with(
                config=private_exchange.config,
                handlers=private_exchange.handlers,
                logger=private_exchange.logger
            )
            assert ws_client == mock_ws.return_value

    async def test_websocket_handlers(self, private_exchange):
        """Test private WebSocket handlers creation."""
        handlers = private_exchange._create_inner_websocket_handlers()
        
        assert isinstance(handlers, PrivateWebsocketHandlers)
        assert handlers.order_handler == private_exchange._order_handler
        assert handlers.balance_handler == private_exchange._balance_handler
        assert handlers.execution_handler == private_exchange._execution_handler

    async def test_balances_property(self, private_exchange):
        """Test balances property returns thread-safe copy."""
        # Set up internal balances
        mock_balance = MagicMock(spec=AssetBalance)
        private_exchange._balances['USDT'] = mock_balance
        
        balances = private_exchange.balances
        
        # Should return copy, not direct reference
        assert balances == {'USDT': mock_balance}
        assert balances is not private_exchange._balances

    async def test_open_orders_property(self, private_exchange):
        """Test open_orders property returns thread-safe copy."""
        # Set up internal orders
        btc_usdt = Symbol('BTC', 'USDT')
        mock_order = MagicMock(spec=Order)
        mock_order.order_id = "123"
        private_exchange._open_orders[btc_usdt] = {"123": mock_order}
        
        open_orders = private_exchange.open_orders
        
        # Should return copy with list values
        assert open_orders == {btc_usdt: [mock_order]}
        assert open_orders is not private_exchange._open_orders

    async def test_trading_operations_delegation(self, private_exchange):
        """Test trading operations delegate to REST client."""
        # Mock the private REST client
        mock_rest = AsyncMock()
        private_exchange._private_rest = mock_rest
        
        btc_usdt = Symbol('BTC', 'USDT')
        
        # Test order placement
        await private_exchange.place_limit_order(btc_usdt, Side.BUY, 1.0, 50000.0)
        mock_rest.place_limit_order.assert_called_once_with(btc_usdt, Side.BUY, 1.0, 50000.0)
        
        # Test order cancellation
        await private_exchange.cancel_order(btc_usdt, "123")
        mock_rest.cancel_order.assert_called_once_with(btc_usdt, "123")
        
        # Test order status
        await private_exchange.get_order(btc_usdt, "123")
        mock_rest.get_order_status.assert_called_once_with(btc_usdt, "123")

    async def test_error_handling(self, private_exchange):
        """Test error handling in trading operations."""
        # Mock the private REST client to raise an exception
        mock_rest = AsyncMock()
        mock_rest.place_limit_order.side_effect = Exception("MEXC API Error")
        private_exchange._private_rest = mock_rest
        
        btc_usdt = Symbol('BTC', 'USDT')
        
        # Should propagate the exception
        with pytest.raises(Exception, match="MEXC API Error"):
            await private_exchange.place_limit_order(btc_usdt, Side.BUY, 1.0, 50000.0)