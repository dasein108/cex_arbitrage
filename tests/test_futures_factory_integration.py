"""
Tests for futures factory integration.

Test suite for validating that the composite exchange factory
properly supports futures exchanges with correct mappings.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from exchanges.factory.exchange_registry import ExchangeRegistry, ExchangeType, get_exchange_implementation
from exchanges.factory.composite_exchange_factory import CompositeExchangeFactory
from exchanges.structs.common import Symbol, SymbolsInfo
from exchanges.structs.types import AssetName


@pytest.fixture
def sample_futures_symbols():
    """Sample futures symbols for testing."""
    return [
        Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=True),
        Symbol(base=AssetName('ETH'), quote=AssetName('USDT'), is_futures=True)
    ]


@pytest.fixture
def mock_config_manager():
    """Mock configuration manager."""
    config_manager = MagicMock()
    
    # Mock Gate.io futures config
    gateio_config = MagicMock()
    gateio_config.name = "gateio"
    gateio_config.api_key = "test_key"
    gateio_config.secret_key = "test_secret"
    gateio_config.base_url = "https://api.gateio.ws"
    gateio_config.futures_base_url = "https://api.gateio.ws/api/v4/futures"
    
    config_manager.get_exchange_config.return_value = gateio_config
    return config_manager


class TestFuturesExchangeRegistry:
    """Test futures support in exchange registry."""

    def test_futures_exchange_type_exists(self):
        """Test that FUTURES exchange type is defined."""
        assert ExchangeType.FUTURES
        assert ExchangeType.FUTURES.value == "futures"

    def test_gateio_futures_registration(self):
        """Test that Gate.io futures is registered."""
        impl = ExchangeRegistry.get_implementation("gateio_futures")
        assert impl is not None
        assert impl.exchange_type == ExchangeType.FUTURES
        
        # Verify futures-specific features
        assert "futures" in impl.features
        assert "leverage" in impl.features
        assert "positions" in impl.features
        assert "funding_rate" in impl.features
        
        # Verify futures-specific order types
        assert "REDUCE_ONLY" in impl.supported_order_types
        assert "CLOSE_POSITION" in impl.supported_order_types

    def test_list_futures_exchanges(self):
        """Test listing futures exchanges."""
        futures_exchanges = ExchangeRegistry.list_futures_exchanges()
        assert "gateio_futures" in futures_exchanges
        
        # Verify only futures exchanges are returned
        for exchange_name in futures_exchanges:
            impl = ExchangeRegistry.get_implementation(exchange_name)
            assert impl.exchange_type == ExchangeType.FUTURES

    def test_futures_feature_detection(self):
        """Test futures feature detection."""
        assert ExchangeRegistry.has_feature("gateio_futures", "futures")
        assert ExchangeRegistry.has_feature("gateio_futures", "leverage")
        assert ExchangeRegistry.has_feature("gateio_futures", "positions")
        
        # Spot exchanges should not have futures features
        assert not ExchangeRegistry.has_feature("gateio_spot", "futures")
        assert not ExchangeRegistry.has_feature("mexc_spot", "leverage")

    def test_futures_order_type_support(self):
        """Test futures order type support."""
        assert ExchangeRegistry.supports_order_type("gateio_futures", "REDUCE_ONLY")
        assert ExchangeRegistry.supports_order_type("gateio_futures", "CLOSE_POSITION")
        assert ExchangeRegistry.supports_order_type("gateio_futures", "LIMIT")
        assert ExchangeRegistry.supports_order_type("gateio_futures", "MARKET")


class TestFuturesDynamicImport:
    """Test dynamic import for futures exchanges."""

    def test_gateio_futures_dynamic_import(self):
        """Test dynamic import of Gate.io futures implementation."""
        with patch('exchanges.integrations.gateio.gateio_futures_composite_public.GateioFuturesCompositePublicExchange') as mock_public, \
             patch('exchanges.integrations.gateio.gateio_futures_composite_private.GateioFuturesCompositePrivateExchange') as mock_private:
            
            # Get implementation (triggers dynamic import)
            impl = get_exchange_implementation("gateio_futures")
            
            # Verify classes are set
            assert impl.public_class is not None
            assert impl.private_class is not None
            assert impl.exchange_type == ExchangeType.FUTURES

    def test_unknown_futures_exchange_error(self):
        """Test error handling for unknown futures exchange."""
        with pytest.raises(ValueError, match="Unknown exchange: unknown_futures"):
            get_exchange_implementation("unknown_futures")


class TestCompositeFactoryFuturesSupport:
    """Test composite factory futures exchange creation."""

    @pytest.fixture
    def factory(self, mock_config_manager):
        """Create factory instance for testing."""
        return CompositeExchangeFactory(config_manager=mock_config_manager)

    @pytest.mark.asyncio
    async def test_create_futures_exchange_pair(self, factory, sample_futures_symbols):
        """Test creating futures exchange pair."""
        with patch('exchanges.integrations.gateio.gateio_futures_composite_public.GateioFuturesCompositePublicExchange') as mock_public_class, \
             patch('exchanges.integrations.gateio.gateio_futures_composite_private.GateioFuturesCompositePrivateExchange') as mock_private_class:
            
            # Setup mocks
            mock_public = AsyncMock()
            mock_private = AsyncMock()
            mock_public_class.return_value = mock_public
            mock_private_class.return_value = mock_private
            
            # Create exchange pair
            exchange_pair = await factory.create_exchange_pair(
                exchange_name="gateio_futures",
                symbols=sample_futures_symbols,
                private_enabled=True
            )
            
            # Verify exchange pair creation
            assert exchange_pair.public == mock_public
            assert exchange_pair.private == mock_private
            assert exchange_pair.has_private
            
            # Verify initialization was called
            mock_public.initialize.assert_called_once()
            mock_private.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_futures_public_only(self, factory, sample_futures_symbols):
        """Test creating futures public exchange only."""
        with patch('exchanges.integrations.gateio.gateio_futures_composite_public.GateioFuturesCompositePublicExchange') as mock_public_class:
            
            # Setup mock
            mock_public = AsyncMock()
            mock_public_class.return_value = mock_public
            
            # Create public-only exchange pair
            exchange_pair = await factory.create_exchange_pair(
                exchange_name="gateio_futures",
                symbols=sample_futures_symbols,
                private_enabled=False
            )
            
            # Verify public-only creation
            assert exchange_pair.public == mock_public
            assert exchange_pair.private is None
            assert not exchange_pair.has_private
            
            # Verify only public initialization was called
            mock_public.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_futures_exchange_creation(self, factory, sample_futures_symbols):
        """Test concurrent creation of multiple futures exchanges."""
        with patch('exchanges.integrations.gateio.gateio_futures_composite_public.GateioFuturesCompositePublicExchange') as mock_public_class, \
             patch('exchanges.integrations.gateio.gateio_futures_composite_private.GateioFuturesCompositePrivateExchange') as mock_private_class:
            
            # Setup mocks
            mock_public = AsyncMock()
            mock_private = AsyncMock()
            mock_public_class.return_value = mock_public
            mock_private_class.return_value = mock_private
            
            # Create multiple futures exchanges concurrently
            exchange_names = ["gateio_futures", "gateio_futures"]  # Create same exchange multiple times
            
            results = await factory.create_multiple_exchanges(
                exchange_names=exchange_names,
                symbols=sample_futures_symbols,
                private_enabled=True,
                max_concurrent=2
            )
            
            # Verify all exchanges were created
            assert len(results) == 2
            for result in results:
                assert result.success
                assert result.exchange_pair.has_private
                assert result.exchange_name == "gateio_futures"

    @pytest.mark.asyncio
    async def test_futures_exchange_error_handling(self, factory, sample_futures_symbols):
        """Test error handling during futures exchange creation."""
        with patch('exchanges.integrations.gateio.gateio_futures_composite_public.GateioFuturesCompositePublicExchange') as mock_public_class:
            
            # Setup mock to raise exception
            mock_public_class.side_effect = Exception("Initialization failed")
            
            # Create exchange pair should handle the error gracefully
            with pytest.raises(Exception, match="Initialization failed"):
                await factory.create_exchange_pair(
                    exchange_name="gateio_futures",
                    symbols=sample_futures_symbols,
                    private_enabled=False
                )

    def test_factory_performance_tracking_futures(self, factory):
        """Test performance tracking for futures exchanges."""
        # Verify metrics include futures-specific tracking
        metrics = factory.get_performance_metrics()
        
        # Should have basic tracking structure
        assert 'total_creations' in metrics
        assert 'average_creation_time' in metrics
        assert 'exchange_type_breakdown' in metrics
        
        # After creating futures exchanges, should track FUTURES type
        # (This would need actual exchange creation to populate)


class TestFuturesSpecificFeatures:
    """Test futures-specific features in factory integration."""

    def test_futures_vs_spot_feature_separation(self):
        """Test that futures and spot features are properly separated."""
        # Get spot and futures implementations
        spot_impl = ExchangeRegistry.get_implementation("gateio_spot")
        futures_impl = ExchangeRegistry.get_implementation("gateio_futures")
        
        assert spot_impl is not None
        assert futures_impl is not None
        
        # Verify spot doesn't have futures features
        assert "spot" in spot_impl.features
        assert "futures" not in spot_impl.features
        assert "leverage" not in spot_impl.features
        
        # Verify futures has futures features
        assert "futures" in futures_impl.features
        assert "leverage" in futures_impl.features
        assert "positions" in futures_impl.features

    def test_futures_order_types_comprehensive(self):
        """Test comprehensive futures order type support."""
        futures_order_types = ExchangeRegistry.get_implementation("gateio_futures").supported_order_types
        
        # Standard order types
        assert "LIMIT" in futures_order_types
        assert "MARKET" in futures_order_types
        
        # Futures-specific order types
        assert "REDUCE_ONLY" in futures_order_types
        assert "CLOSE_POSITION" in futures_order_types
        
        # Advanced order types
        assert "STOP_LOSS" in futures_order_types
        assert "TAKE_PROFIT" in futures_order_types

    def test_futures_symbol_handling(self, sample_futures_symbols):
        """Test that futures symbols are properly handled."""
        for symbol in sample_futures_symbols:
            assert symbol.is_futures
            assert symbol.base in [AssetName('BTC'), AssetName('ETH')]
            assert symbol.quote == AssetName('USDT')


@pytest.mark.integration
class TestFuturesFactoryIntegration:
    """Integration tests for futures factory functionality."""

    @pytest.mark.asyncio
    async def test_end_to_end_futures_creation(self, mock_config_manager, sample_futures_symbols):
        """Test end-to-end futures exchange creation."""
        factory = CompositeExchangeFactory(config_manager=mock_config_manager)
        
        with patch('exchanges.integrations.gateio.gateio_futures_composite_public.GateioFuturesCompositePublicExchange') as mock_public_class, \
             patch('exchanges.integrations.gateio.gateio_futures_composite_private.GateioFuturesCompositePrivateExchange') as mock_private_class:
            
            # Setup mocks
            mock_public = AsyncMock()
            mock_private = AsyncMock()
            mock_public_class.return_value = mock_public
            mock_private_class.return_value = mock_private
            
            # Full lifecycle test
            async with factory:
                exchange_pair = await factory.create_exchange_pair(
                    exchange_name="gateio_futures",
                    symbols=sample_futures_symbols,
                    private_enabled=True
                )
                
                # Verify complete setup
                assert exchange_pair.has_private
                mock_public.initialize.assert_called_once()
                mock_private.initialize.assert_called_once()
                
                # Test context manager cleanup
                await exchange_pair.close()


if __name__ == "__main__":
    pytest.main([__file__])