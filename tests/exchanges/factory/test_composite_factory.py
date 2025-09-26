"""
Comprehensive tests for composite exchange factory pattern.

Tests cover factory creation, exchange instantiation, migration adapter,
error handling, and performance characteristics.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from config.config_manager import HftConfig
from exchanges.structs.common import Symbol, OrderBook, BookTicker, AssetBalance, Order
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs import Side, OrderType, OrderStatus
from exchanges.factory.composite_exchange_factory import CompositeExchangeFactory
from exchanges.factory.enhanced_factory import EnhancedExchangeFactory
from exchanges.factory.migration_adapter import UnifiedToCompositeAdapter
from exchanges.factory.exchange_registry import ExchangeRegistry, ExchangeType, ExchangePair
from infrastructure.logging import HFTLoggerFactory


class TestExchangeRegistry:
    """Test exchange registry functionality."""
    
    def test_get_implementation(self):
        """Test getting exchange implementation."""
        impl = ExchangeRegistry.get_implementation("mexc_spot")
        assert impl is not None
        assert impl.exchange_type == ExchangeType.SPOT
        assert "spot" in impl.features
        assert "websocket" in impl.features
    
    def test_list_exchanges(self):
        """Test listing exchanges."""
        all_exchanges = ExchangeRegistry.list_exchanges()
        assert "mexc_spot" in all_exchanges
        assert "gateio_spot" in all_exchanges
        
        spot_exchanges = ExchangeRegistry.list_exchanges(ExchangeType.SPOT)
        assert "mexc_spot" in spot_exchanges
        assert "gateio_spot" in spot_exchanges
    
    def test_has_feature(self):
        """Test feature detection."""
        assert ExchangeRegistry.has_feature("mexc_spot", "spot")
        assert ExchangeRegistry.has_feature("gateio_spot", "spot")
        assert not ExchangeRegistry.has_feature("mexc_spot", "futures")
        assert not ExchangeRegistry.has_feature("unknown_exchange", "any_feature")
    
    def test_get_rate_limit(self):
        """Test rate limit retrieval."""
        mexc_public_limit = ExchangeRegistry.get_rate_limit("mexc_spot", "public")
        assert mexc_public_limit == 20
        
        gateio_public_limit = ExchangeRegistry.get_rate_limit("gateio_spot", "public")
        assert gateio_public_limit == 900
        
        unknown_limit = ExchangeRegistry.get_rate_limit("unknown_exchange", "public")
        assert unknown_limit is None
    
    def test_supports_order_type(self):
        """Test order type support."""
        assert ExchangeRegistry.supports_order_type("mexc_spot", "LIMIT")
        assert ExchangeRegistry.supports_order_type("mexc_spot", "MARKET")
        assert ExchangeRegistry.supports_order_type("gateio_spot", "IOC")
        assert not ExchangeRegistry.supports_order_type("mexc_spot", "IOC")


class TestCompositeExchangeFactory:
    """Test composite exchange factory."""
    
    @pytest.fixture
    def config_manager(self):
        """Create mock config manager."""
        mock_config = Mock(spec=HftConfig)
        mock_exchange_config = Mock()
        mock_exchange_config.name = "mexc_spot"
        mock_exchange_config.has_credentials.return_value = True
        mock_config.get_exchange_config.return_value = mock_exchange_config
        return mock_config
    
    @pytest.fixture
    def logger(self):
        """Create test logger."""
        return HFTLoggerFactory.create_logger("test_factory", "DEBUG")
    
    @pytest.fixture
    def factory(self, config_manager, logger):
        """Create factory instance."""
        return CompositeExchangeFactory(config_manager, logger)
    
    def test_factory_initialization(self, factory):
        """Test factory initialization."""
        assert factory.config_manager is not None
        assert factory.logger is not None
        assert factory._exchange_registry is not None
        assert isinstance(factory._created_exchanges, dict)
        assert isinstance(factory._initialization_times, dict)
    
    @pytest.mark.asyncio
    async def test_create_public_exchange(self, factory):
        """Test public exchange creation."""
        symbols = [Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))]
        
        # Mock the implementation classes
        with patch('exchanges.factory.exchange_registry.get_exchange_implementation') as mock_get_impl:
            mock_impl = Mock()
            mock_public_class = AsyncMock()
            mock_public_instance = AsyncMock()
            mock_public_class.return_value = mock_public_instance
            mock_impl.public_class = mock_public_class
            mock_get_impl.return_value = mock_impl
            
            public_exchange = await factory.create_public_exchange("mexc_spot", symbols)
            
            assert public_exchange == mock_public_instance
            mock_public_instance.initialize.assert_called_once_with(symbols)
    
    @pytest.mark.asyncio
    async def test_create_private_exchange(self, factory):
        """Test private exchange creation."""
        # Mock the implementation classes
        with patch('exchanges.factory.exchange_registry.get_exchange_implementation') as mock_get_impl:
            mock_impl = Mock()
            mock_private_class = AsyncMock()
            mock_private_instance = AsyncMock()
            mock_private_class.return_value = mock_private_instance
            mock_impl.private_class = mock_private_class
            mock_get_impl.return_value = mock_impl
            
            private_exchange = await factory.create_private_exchange("mexc_spot")
            
            assert private_exchange == mock_private_instance
            mock_private_instance.initialize.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_exchange_pair(self, factory):
        """Test exchange pair creation."""
        symbols = [Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))]
        
        # Mock both public and private creation
        with patch.object(factory, 'create_public_exchange') as mock_create_public, \
             patch.object(factory, 'create_private_exchange') as mock_create_private:
            
            mock_public = AsyncMock()
            mock_private = AsyncMock()
            mock_public.symbols_info = Mock()
            mock_create_public.return_value = mock_public
            mock_create_private.return_value = mock_private
            
            pair = await factory.create_exchange_pair("mexc_spot", symbols, private_enabled=True)
            
            assert isinstance(pair, ExchangePair)
            assert pair.public == mock_public
            assert pair.private == mock_private
            assert pair.has_private is True
            
            mock_create_public.assert_called_once_with("mexc_spot", symbols)
            mock_create_private.assert_called_once_with("mexc_spot", mock_public.symbols_info)
    
    @pytest.mark.asyncio
    async def test_create_multiple_exchanges(self, factory):
        """Test concurrent exchange creation."""
        exchange_names = ["mexc_spot", "gateio_spot"]
        symbols = [Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))]
        
        with patch.object(factory, 'create_exchange_pair') as mock_create_pair:
            mock_pair1 = Mock(spec=ExchangePair)
            mock_pair2 = Mock(spec=ExchangePair)
            mock_create_pair.side_effect = [mock_pair1, mock_pair2]
            
            exchange_map = await factory.create_multiple_exchanges(exchange_names, symbols)
            
            assert len(exchange_map) == 2
            assert "mexc_spot" in exchange_map
            assert "gateio_spot" in exchange_map
            assert exchange_map["mexc_spot"] == mock_pair1
            assert exchange_map["gateio_spot"] == mock_pair2
    
    def test_get_exchange_info(self, factory):
        """Test exchange info retrieval."""
        info = factory.get_exchange_info("mexc_spot")
        assert info["name"] == "mexc_spot"
        assert info["type"] == "spot"
        assert "spot" in info["features"]
        assert "rate_limits" in info
    
    def test_list_exchanges(self, factory):
        """Test exchange listing."""
        all_exchanges = factory.list_available_exchanges()
        assert "mexc_spot" in all_exchanges
        
        spot_exchanges = factory.list_spot_exchanges()
        assert "mexc_spot" in spot_exchanges
        assert "gateio_spot" in spot_exchanges


class TestMigrationAdapter:
    """Test migration adapter functionality."""
    
    @pytest.fixture
    def mock_public_exchange(self):
        """Create mock public exchange."""
        mock_public = AsyncMock()
        mock_public.get_best_bid_ask.return_value = BookTicker(
            symbol=Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
            bid_price=50000.0,
            bid_quantity=1.0,
            ask_price=50001.0,
            ask_quantity=1.0,
            timestamp=1234567890
        )
        mock_public._get_orderbook_snapshot.return_value = OrderBook(
            symbol=Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
            bids=[],
            asks=[],
            timestamp=1234567890
        )
        mock_public.active_symbols = {Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))}
        mock_public.symbols_info = Mock()
        mock_public.is_connected = True
        return mock_public
    
    @pytest.fixture
    def mock_private_exchange(self):
        """Create mock private exchange."""
        mock_private = AsyncMock()
        mock_private.place_limit_order.return_value = Order(
            symbol=Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
            order_id=OrderId("12345"),
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
            status=OrderStatus.NEW,
            filled_quantity=0.0,
            timestamp=1234567890
        )
        mock_private.balances = {
            AssetName("USDT"): AssetBalance(
                asset=AssetName("USDT"),
                available=10000.0,
                locked=0.0,
                total=10000.0
            )
        }
        mock_private.is_connected = True
        return mock_private
    
    @pytest.fixture
    def adapter(self, mock_public_exchange, mock_private_exchange):
        """Create adapter instance."""
        return UnifiedToCompositeAdapter(mock_public_exchange, mock_private_exchange)
    
    @pytest.mark.asyncio
    async def test_public_interface_delegation(self, adapter, mock_public_exchange):
        """Test public interface methods."""
        symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        
        # Test orderbook
        orderbook = await adapter.get_orderbook(symbol)
        mock_public_exchange._get_orderbook_snapshot.assert_called_once_with(symbol)
        
        # Test best bid/ask
        book_ticker = await adapter.get_best_bid_ask(symbol)
        mock_public_exchange.get_best_bid_ask.assert_called_once_with(symbol)
        
        # Test active symbols
        active_symbols = adapter.get_active_symbols()
        assert symbol in active_symbols
    
    @pytest.mark.asyncio
    async def test_private_interface_delegation(self, adapter, mock_private_exchange):
        """Test private interface methods."""
        symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        
        # Test limit order
        order = await adapter.place_limit_order(symbol, Side.BUY, 1.0, 50000.0)
        mock_private_exchange.place_limit_order.assert_called_once_with(symbol, Side.BUY, 1.0, 50000.0)
        
        # Test balance
        balance = await adapter.get_balance(AssetName("USDT"))
        assert balance.available == 10000.0
        
        # Test all balances
        balances = await adapter.get_balances()
        assert AssetName("USDT") in balances
    
    @pytest.mark.asyncio
    async def test_private_not_available_errors(self, mock_public_exchange):
        """Test errors when private exchange not available."""
        adapter = UnifiedToCompositeAdapter(mock_public_exchange, None)
        symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        
        with pytest.raises(RuntimeError, match="Private exchange not available"):
            await adapter.place_limit_order(symbol, Side.BUY, 1.0, 50000.0)
        
        with pytest.raises(RuntimeError, match="Private exchange not available"):
            await adapter.get_balance(AssetName("USDT"))
    
    @pytest.mark.asyncio
    async def test_context_manager(self, adapter, mock_public_exchange, mock_private_exchange):
        """Test async context manager support."""
        async with adapter as ctx_adapter:
            assert ctx_adapter == adapter
        
        mock_public_exchange.close.assert_called_once()
        mock_private_exchange.close.assert_called_once()
    
    def test_connection_status(self, adapter):
        """Test connection status reporting."""
        assert adapter.is_connected() is True
        
        status = adapter.get_connection_status()
        assert status["public_connected"] is True
        assert status["private_connected"] is True
        assert status["has_public"] is True
        assert status["has_private"] is True


class TestEnhancedExchangeFactory:
    """Test enhanced factory with migration support."""
    
    @pytest.fixture
    def config_manager(self):
        """Create mock config manager."""
        mock_config = Mock(spec=HftConfig)
        mock_exchange_config = Mock()
        mock_exchange_config.name = "mexc_spot"
        mock_exchange_config.has_credentials.return_value = True
        mock_config.get_exchange_config.return_value = mock_exchange_config
        return mock_config
    
    @pytest.fixture
    def enhanced_factory(self, config_manager):
        """Create enhanced factory instance."""
        return EnhancedExchangeFactory(config_manager)
    
    def test_migration_mode_detection(self, enhanced_factory):
        """Test migration mode detection."""
        # Default should be True (migration mode enabled)
        assert enhanced_factory._migration_mode is True
        
        # Test force composite detection
        with patch.dict('os.environ', {'FORCE_COMPOSITE_PATTERN': 'true'}):
            factory = EnhancedExchangeFactory()
            assert factory._check_force_composite() is True
    
    def test_legacy_component_detection(self, enhanced_factory):
        """Test legacy component detection."""
        # Test with custom legacy components
        with patch.dict('os.environ', {'LEGACY_COMPONENTS': 'arbitrageengine,custombot'}):
            factory = EnhancedExchangeFactory()
            legacy_components = factory._get_legacy_components()
            assert 'arbitrageengine' in legacy_components
            assert 'custombot' in legacy_components
    
    @pytest.mark.asyncio
    async def test_automatic_pattern_selection(self, enhanced_factory):
        """Test automatic pattern selection."""
        symbols = [Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))]
        
        with patch.object(enhanced_factory.composite_factory, 'create_exchange_pair') as mock_create_pair:
            mock_pair = Mock(spec=ExchangePair)
            mock_pair.public = AsyncMock()
            mock_pair.private = AsyncMock()
            mock_create_pair.return_value = mock_pair
            
            # Test composite pattern (default)
            result = await enhanced_factory.create_exchange("mexc_spot", symbols, use_unified=False)
            assert isinstance(result, ExchangePair)
            
            # Test unified pattern
            result = await enhanced_factory.create_exchange("mexc_spot", symbols, use_unified=True)
            assert isinstance(result, UnifiedToCompositeAdapter)
    
    @pytest.mark.asyncio
    async def test_multiple_exchange_creation(self, enhanced_factory):
        """Test multiple exchange creation."""
        exchange_names = ["mexc_spot", "gateio_spot"]
        symbols = [Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))]
        
        with patch.object(enhanced_factory, 'create_exchange') as mock_create:
            mock_exchange1 = Mock()
            mock_exchange2 = Mock()
            mock_create.side_effect = [mock_exchange1, mock_exchange2]
            
            exchange_map = await enhanced_factory.create_multiple_exchanges(
                exchange_names, symbols, use_unified=False
            )
            
            assert len(exchange_map) == 2
            assert "mexc_spot" in exchange_map
            assert "gateio_spot" in exchange_map
    
    def test_migration_statistics(self, enhanced_factory):
        """Test migration statistics tracking."""
        # Simulate some requests
        enhanced_factory._unified_requests = 5
        enhanced_factory._composite_requests = 10
        enhanced_factory._migration_warnings = 2
        
        stats = enhanced_factory.get_migration_stats()
        assert stats["total_requests"] == 15
        assert stats["unified_requests"] == 5
        assert stats["composite_requests"] == 10
        assert stats["unified_percentage"] == 33.33
        assert stats["migration_warnings"] == 2
    
    def test_migration_recommendations(self, enhanced_factory):
        """Test migration recommendations."""
        # No usage yet
        recommendations = enhanced_factory.recommend_migration()
        assert len(recommendations) == 1
        assert "good adoption" in recommendations[0]
        
        # Simulate unified usage
        enhanced_factory._unified_requests = 5
        enhanced_factory._migration_warnings = 2
        
        recommendations = enhanced_factory.recommend_migration()
        assert len(recommendations) == 2
        assert any("unified interface requests" in rec for rec in recommendations)
        assert any("legacy component warnings" in rec for rec in recommendations)
    
    def test_legacy_component_management(self, enhanced_factory):
        """Test legacy component management."""
        # Add legacy component
        enhanced_factory.add_legacy_component("CustomArbitrageBot")
        assert "customarbitragebot" in enhanced_factory._legacy_components
        
        # Remove legacy component
        enhanced_factory.remove_legacy_component("CustomArbitrageBot")
        assert "customarbitragebot" not in enhanced_factory._legacy_components


class TestFactoryIntegration:
    """Integration tests for factory pattern."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_exchange_creation(self):
        """Test complete exchange creation flow."""
        # This would require actual exchange implementations
        # For now, test the flow with mocks
        
        with patch('exchanges.factory.exchange_registry.get_exchange_implementation') as mock_get_impl:
            # Mock implementation
            mock_impl = Mock()
            mock_public_class = AsyncMock()
            mock_private_class = AsyncMock()
            mock_public_instance = AsyncMock()
            mock_private_instance = AsyncMock()
            
            mock_public_class.return_value = mock_public_instance
            mock_private_class.return_value = mock_private_instance
            mock_impl.public_class = mock_public_class
            mock_impl.private_class = mock_private_class
            mock_get_impl.return_value = mock_impl
            
            # Create factory and exchange
            factory = EnhancedExchangeFactory()
            symbols = [Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))]
            
            result = await factory.create_exchange("mexc_spot", symbols, use_unified=False)
            
            assert isinstance(result, ExchangePair)
            assert result.public == mock_public_instance
            assert result.private == mock_private_instance


if __name__ == "__main__":
    pytest.main([__file__, "-v"])