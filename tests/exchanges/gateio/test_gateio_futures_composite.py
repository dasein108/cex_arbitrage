"""
Tests for Gate.io futures composite exchange implementations.

Comprehensive test suite for Gate.io futures public and private composite
exchanges with mocking and performance validation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
from typing import Dict, List

from exchanges.integrations.gateio.gateio_futures_composite_public import GateioFuturesCompositePublicExchange
from exchanges.integrations.gateio.gateio_futures_composite_private import GateioFuturesCompositePrivateExchange
from exchanges.structs.common import Symbol, Order, Position, SymbolsInfo, SymbolInfo
from exchanges.structs.types import AssetName
from infrastructure.logging import HFTLoggerInterface


@pytest.fixture
def sample_symbols():
    """Sample futures symbols for testing."""
    return [
        Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=True),
        Symbol(base=AssetName('ETH'), quote=AssetName('USDT'), is_futures=True)
    ]


@pytest.fixture
def sample_symbols_info(sample_symbols):
    """Sample symbols info for initialization."""
    symbol_infos = []
    for symbol in sample_symbols:
        symbol_infos.append(SymbolInfo(
            symbol=symbol,
            price_precision=2,
            quantity_precision=4,
            min_quantity=Decimal('0.0001'),
            max_quantity=Decimal('10000'),
            min_price=Decimal('0.01'),
            max_price=Decimal('100000'),
            status='active'
        ))
    
    return SymbolsInfo(symbols=sample_symbols, symbol_infos=symbol_infos)


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    config = MagicMock()
    config.name = "gateio"
    config.api_key = "test_api_key"
    config.secret_key = "test_secret_key"
    config.base_url = "https://api.gateio.ws"
    config.futures_base_url = "https://api.gateio.ws/api/v4/futures"
    return config


@pytest.fixture
def mock_logger():
    """Mock logger for testing."""
    return MagicMock(spec=HFTLoggerInterface)


class TestGateioFuturesCompositePublicExchange:
    """Test suite for Gate.io futures public composite exchange."""

    @pytest.fixture
    def public_exchange(self, mock_config, mock_logger):
        """Create public exchange instance for testing."""
        return GateioFuturesCompositePublicExchange(mock_config, mock_logger)

    @pytest.mark.asyncio
    async def test_initialization(self, public_exchange, sample_symbols_info):
        """Test public exchange initialization."""
        # Mock the REST and WebSocket clients
        with patch.object(public_exchange, '_create_public_rest') as mock_rest, \
             patch.object(public_exchange, '_create_public_websocket') as mock_ws:
            
            mock_rest_client = AsyncMock()
            mock_ws_client = AsyncMock()
            mock_rest.return_value = mock_rest_client
            mock_ws.return_value = mock_ws_client
            
            # Initialize
            await public_exchange.initialize(sample_symbols_info)
            
            # Verify initialization calls
            mock_rest.assert_called_once()
            mock_ws.assert_called_once()
            mock_rest_client.initialize.assert_called_once()
            mock_ws_client.initialize.assert_called()

    @pytest.mark.asyncio
    async def test_funding_rate_methods(self, public_exchange):
        """Test futures-specific funding rate methods."""
        symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=True)
        
        # Mock REST client
        mock_rest = AsyncMock()
        public_exchange._public_rest = mock_rest
        
        # Test get_funding_rate
        expected_funding_rate = {
            'symbol': symbol,
            'funding_rate': Decimal('0.0001'),
            'funding_time': 1234567890
        }
        mock_rest.get_funding_rate.return_value = expected_funding_rate
        
        result = await public_exchange.get_funding_rate(symbol)
        assert result == expected_funding_rate
        mock_rest.get_funding_rate.assert_called_once_with(symbol)
        
        # Test get_funding_rate_history
        expected_history = [expected_funding_rate, expected_funding_rate]
        mock_rest.get_funding_rate_history.return_value = expected_history
        
        result = await public_exchange.get_funding_rate_history(symbol, 10)
        assert result == expected_history
        mock_rest.get_funding_rate_history.assert_called_once_with(symbol, 10)

    @pytest.mark.asyncio
    async def test_mark_price_methods(self, public_exchange):
        """Test futures-specific mark price methods."""
        symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=True)
        
        # Mock REST client
        mock_rest = AsyncMock()
        public_exchange._public_rest = mock_rest
        
        # Test get_mark_price
        expected_mark_price = {
            'symbol': symbol,
            'mark_price': Decimal('50000.0'),
            'timestamp': 1234567890
        }
        mock_rest.get_mark_price.return_value = expected_mark_price
        
        result = await public_exchange.get_mark_price(symbol)
        assert result == expected_mark_price
        mock_rest.get_mark_price.assert_called_once_with(symbol)
        
        # Test get_index_price
        expected_index_price = {
            'symbol': symbol,
            'index_price': Decimal('49950.0'),
            'timestamp': 1234567890
        }
        mock_rest.get_index_price.return_value = expected_index_price
        
        result = await public_exchange.get_index_price(symbol)
        assert result == expected_index_price
        mock_rest.get_index_price.assert_called_once_with(symbol)

    def test_supported_futures_channels(self, public_exchange):
        """Test supported futures WebSocket channels."""
        channels = public_exchange.get_supported_futures_channels()
        
        # Verify that futures-specific channels are included
        channel_types = [ch.value if hasattr(ch, 'value') else str(ch) for ch in channels]
        assert 'orderbook' in channel_types or 'ORDERBOOK' in channel_types
        assert 'trades' in channel_types or 'TRADES' in channel_types
        
        # Should have multiple channels for futures
        assert len(channels) >= 3

    def test_trading_stats(self, public_exchange):
        """Test trading stats for futures exchange."""
        # Mock parent stats
        with patch('exchanges.interfaces.composite.base_public_exchange.CompositePublicExchange.get_trading_stats') as mock_parent:
            mock_parent.return_value = {'base_stat': 'value'}
            
            stats = public_exchange.get_trading_stats()
            
            # Verify futures-specific stats are added
            assert stats['exchange_type'] == 'futures'
            assert 'supported_channels' in stats
            assert stats['base_stat'] == 'value'  # Parent stats preserved


class TestGateioFuturesCompositePrivateExchange:
    """Test suite for Gate.io futures private composite exchange."""

    @pytest.fixture
    def private_exchange(self, mock_config, mock_logger):
        """Create private exchange instance for testing."""
        return GateioFuturesCompositePrivateExchange(mock_config, mock_logger)

    @pytest.mark.asyncio
    async def test_initialization(self, private_exchange, sample_symbols_info):
        """Test private exchange initialization."""
        # Mock the REST and WebSocket clients and data loading methods
        with patch.object(private_exchange, '_create_private_rest') as mock_rest, \
             patch.object(private_exchange, '_create_private_websocket') as mock_ws, \
             patch.object(private_exchange, '_load_leverage_settings') as mock_leverage, \
             patch.object(private_exchange, '_load_margin_info') as mock_margin, \
             patch.object(private_exchange, '_load_futures_positions') as mock_positions, \
             patch('exchanges.interfaces.composite.base_private_exchange.CompositePrivateExchange.initialize') as mock_parent:
            
            mock_rest_client = AsyncMock()
            mock_ws_client = AsyncMock()
            mock_rest.return_value = mock_rest_client
            mock_ws.return_value = mock_ws_client
            
            # Initialize
            await private_exchange.initialize(sample_symbols_info)
            
            # Verify initialization calls
            mock_parent.assert_called_once_with(sample_symbols_info)
            mock_leverage.assert_called_once()
            mock_margin.assert_called_once()
            mock_positions.assert_called_once()

    @pytest.mark.asyncio
    async def test_leverage_management(self, private_exchange):
        """Test leverage setting and getting."""
        symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=True)
        
        # Mock REST client
        mock_rest = AsyncMock()
        private_exchange._private_rest = mock_rest
        
        # Test set_leverage
        mock_rest.modify_leverage.return_value = True
        
        result = await private_exchange.set_leverage(symbol, 10)
        assert result is True
        mock_rest.modify_leverage.assert_called_once_with(symbol, 10.0)
        
        # Verify leverage is cached
        assert symbol in private_exchange._leverage_settings
        assert private_exchange._leverage_settings[symbol]['leverage'] == 10
        
        # Test get_leverage (cached)
        cached_result = await private_exchange.get_leverage(symbol)
        assert cached_result['leverage'] == 10
        assert cached_result['symbol'] == symbol

    @pytest.mark.asyncio
    async def test_futures_order_placement(self, private_exchange):
        """Test futures order placement with advanced options."""
        symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=True)
        
        # Mock REST client
        mock_rest = AsyncMock()
        private_exchange._private_rest = mock_rest
        
        # Create expected order
        expected_order = Order(
            order_id='12345',
            symbol=symbol,
            side='buy',
            order_type='limit',
            quantity=Decimal('0.1'),
            price=Decimal('50000'),
            filled_quantity=Decimal('0'),
            remaining_quantity=Decimal('0.1'),
            status='open',
            timestamp=1234567890
        )
        mock_rest.place_order.return_value = expected_order
        
        # Place futures order with reduce_only
        result = await private_exchange.place_futures_order(
            symbol=symbol,
            side='buy',
            order_type='limit',
            quantity=Decimal('0.1'),
            price=Decimal('50000'),
            reduce_only=True,
            close_position=False
        )
        
        assert result == expected_order
        mock_rest.place_order.assert_called_once()
        
        # Verify order is tracked
        assert expected_order.order_id in private_exchange._orders

    @pytest.mark.asyncio
    async def test_position_closing(self, private_exchange):
        """Test position closing functionality."""
        symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=True)
        
        # Mock REST client
        mock_rest = AsyncMock()
        private_exchange._private_rest = mock_rest
        
        # Mock current positions
        current_position = Position(
            symbol=symbol,
            quantity=Decimal('0.5'),  # Long position
            entry_price=Decimal('49000'),
            mark_price=Decimal('50000'),
            unrealized_pnl=Decimal('500'),
            timestamp=1234567890
        )
        mock_rest.get_positions.return_value = [current_position]
        
        # Mock close order
        close_order = Order(
            order_id='close123',
            symbol=symbol,
            side='sell',
            order_type='market',
            quantity=Decimal('0.5'),
            price=Decimal('0'),
            filled_quantity=Decimal('0'),
            remaining_quantity=Decimal('0.5'),
            status='open',
            timestamp=1234567890
        )
        
        # Mock place_futures_order method
        with patch.object(private_exchange, 'place_futures_order') as mock_place:
            mock_place.return_value = close_order
            
            # Close position
            result = await private_exchange.close_position(symbol)
            
            assert len(result) == 1
            assert result[0] == close_order
            mock_place.assert_called_once_with(
                symbol=symbol,
                side='sell',
                order_type='market',
                quantity=Decimal('0.5'),
                reduce_only=True,
                close_position=True
            )

    @pytest.mark.asyncio
    async def test_position_handler(self, private_exchange):
        """Test position update handler."""
        symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=True)
        
        # Create position update
        position = Position(
            symbol=symbol,
            quantity=Decimal('0.2'),
            entry_price=Decimal('50000'),
            mark_price=Decimal('50100'),
            unrealized_pnl=Decimal('20'),
            timestamp=1234567890
        )
        
        # Handle position update
        await private_exchange._position_handler(position)
        
        # Verify position is stored
        assert symbol in private_exchange._futures_positions
        assert private_exchange._futures_positions[symbol] == position

    def test_trading_stats_futures(self, private_exchange):
        """Test trading stats for futures private exchange."""
        # Add some mock data
        symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=True)
        private_exchange._leverage_settings[symbol] = {'leverage': 10}
        private_exchange._margin_info[symbol] = {'available_margin': Decimal('1000')}
        
        # Add mock positions
        long_position = Position(
            symbol=symbol,
            quantity=Decimal('0.5'),  # Long
            entry_price=Decimal('50000'),
            mark_price=Decimal('50100'),
            unrealized_pnl=Decimal('50'),
            timestamp=1234567890
        )
        short_symbol = Symbol(base=AssetName('ETH'), quote=AssetName('USDT'), is_futures=True)
        short_position = Position(
            symbol=short_symbol,
            quantity=Decimal('-0.3'),  # Short
            entry_price=Decimal('3000'),
            mark_price=Decimal('2990'),
            unrealized_pnl=Decimal('3'),
            timestamp=1234567890
        )
        
        private_exchange._futures_positions[symbol] = long_position
        private_exchange._futures_positions[short_symbol] = short_position
        
        # Mock parent stats
        with patch('exchanges.interfaces.composite.base_private_futures_exchange.CompositePrivateFuturesExchange.get_trading_stats') as mock_parent:
            mock_parent.return_value = {'base_stat': 'value', 'active_positions': 2}
            
            stats = private_exchange.get_trading_stats()
            
            # Verify futures-specific stats
            assert stats['exchange_type'] == 'futures'
            assert stats['exchange_name'] == 'gateio'
            assert stats['leverage_symbols'] == 1
            assert stats['margin_symbols'] == 1
            assert stats['long_positions'] == 1
            assert stats['short_positions'] == 1
            assert stats['base_stat'] == 'value'


@pytest.mark.asyncio
async def test_exchange_lifecycle(mock_config, mock_logger, sample_symbols_info):
    """Test complete exchange lifecycle for both public and private."""
    public_exchange = GateioFuturesCompositePublicExchange(mock_config, mock_logger)
    private_exchange = GateioFuturesCompositePrivateExchange(mock_config, mock_logger)
    
    # Mock all components
    with patch.object(public_exchange, '_create_public_rest') as mock_pub_rest, \
         patch.object(public_exchange, '_create_public_websocket') as mock_pub_ws, \
         patch.object(private_exchange, '_create_private_rest') as mock_priv_rest, \
         patch.object(private_exchange, '_create_private_websocket') as mock_priv_ws, \
         patch.object(private_exchange, '_load_leverage_settings'), \
         patch.object(private_exchange, '_load_margin_info'), \
         patch.object(private_exchange, '_load_futures_positions'):
        
        # Setup mocks
        mock_pub_rest.return_value = AsyncMock()
        mock_pub_ws.return_value = AsyncMock()
        mock_priv_rest.return_value = AsyncMock()
        mock_priv_ws.return_value = AsyncMock()
        
        # Initialize both exchanges
        await public_exchange.initialize(sample_symbols_info)
        await private_exchange.initialize(sample_symbols_info)
        
        # Verify both are initialized
        assert public_exchange._tag == "gateio_futures_public"
        assert private_exchange._tag == "gateio_futures_private"
        
        # Close both exchanges
        await public_exchange.close()
        await private_exchange.close()


if __name__ == "__main__":
    pytest.main([__file__])