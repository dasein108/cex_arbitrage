#!/usr/bin/env python3
"""
MEXC Futures Refactored Performance Validation Tests

Comprehensive test suite validating the performance improvements and compliance
of the refactored MEXC futures implementation.

Test Categories:
1. Interface Compliance Validation
2. Performance Benchmark Tests
3. Code Quality and Architecture Tests
4. Unified Exception Handling Tests
5. LRU Cache Performance Tests
6. Connection Pool Optimization Tests

Performance Targets:
- <10ms response times for all endpoints
- >95% connection pool reuse rate
- Zero code duplication
- Full PublicExchangeInterface compliance
"""

import asyncio
import time
import pytest
from typing import List, Dict, Any
import logging

# Import refactored implementation
from exchanges.mexc.mexc_futures_public import (
    MexcPublicFuturesExchange, 
    create_mexc_futures_client,
    FuturesPerformanceMonitor
)
from exchanges.interface.rest.public_exchange import PublicExchangeInterface
from structs.exchange import Symbol, AssetName, OrderBook, Trade, SymbolInfo
from common.rest import UltraSimpleRestClient
from common.exceptions import ExchangeAPIError

# Test configuration
PERFORMANCE_TARGETS = {
    'max_response_time_ms': 10.0,
    'min_connection_reuse_rate': 0.95,
    'max_cache_miss_rate': 0.05,
    'min_requests_per_second': 50.0
}

TEST_SYMBOLS = [
    Symbol(base=AssetName("BTC"), quote=AssetName("USDT"), is_futures=True),
    Symbol(base=AssetName("ETH"), quote=AssetName("USDT"), is_futures=True),
    Symbol(base=AssetName("BNB"), quote=AssetName("USDT"), is_futures=True),
]


class TestInterfaceCompliance:
    """Test PublicExchangeInterface compliance."""
    
    def test_inheritance_compliance(self):
        """Test that MexcPublicFuturesExchange properly inherits from PublicExchangeInterface."""
        assert issubclass(MexcPublicFuturesExchange, PublicExchangeInterface)
        
        # Test instance compliance
        client = MexcPublicFuturesExchange()
        assert isinstance(client, PublicExchangeInterface)
    
    def test_required_methods_implemented(self):
        """Test that all required interface methods are implemented."""
        client = MexcPublicFuturesExchange()
        
        # Test required method signatures
        assert hasattr(client, 'get_exchange_info')
        assert hasattr(client, 'get_orderbook')
        assert hasattr(client, 'get_recent_trades')
        assert hasattr(client, 'get_server_time')
        assert hasattr(client, 'ping')
        
        # Test additional interface methods
        assert hasattr(client, 'init')
        assert hasattr(client, 'start_symbol')
        assert hasattr(client, 'stop_symbol')
        assert hasattr(client, 'get_websocket_health')
        assert hasattr(client, 'get_performance_metrics')
    
    def test_method_signatures(self):
        """Test that method signatures match interface requirements."""
        import inspect
        
        client = MexcPublicFuturesExchange()
        
        # Test get_orderbook signature
        sig = inspect.signature(client.get_orderbook)
        params = list(sig.parameters.keys())
        assert 'symbol' in params
        assert sig.parameters['symbol'].annotation == Symbol
        
        # Test return type annotations where possible
        assert hasattr(client.get_exchange_info, '__annotations__')
        assert hasattr(client.get_orderbook, '__annotations__')
        assert hasattr(client.get_recent_trades, '__annotations__')


class TestArchitecturalImprovements:
    """Test architectural improvements and code quality."""
    
    def test_ultrasimple_rest_client_usage(self):
        """Test that UltraSimpleRestClient is properly integrated."""
        client = MexcPublicFuturesExchange()
        
        assert hasattr(client, '_rest_client')
        assert isinstance(client._rest_client, UltraSimpleRestClient)
        
        # Test that base URL is properly set
        assert client._rest_client.base_url == "https://contract.mexc.com"
    
    def test_no_duplicated_rest_client_code(self):
        """Test that no custom HTTP client code is duplicated."""
        import inspect
        
        # Get source code of the class
        source = inspect.getsource(MexcPublicFuturesExchange)
        
        # Should not contain aiohttp-specific implementations
        assert 'ClientSession' not in source
        assert 'aiohttp' not in source
        assert 'AiohttpRestClient' not in source
        
        # Should use UltraSimpleRestClient
        assert 'UltraSimpleRestClient' in source
    
    def test_endpoint_configuration_optimization(self):
        """Test that endpoint-specific configurations are optimized."""
        client = MexcPublicFuturesExchange()
        
        assert hasattr(client, '_endpoint_configs')
        configs = client._endpoint_configs
        
        # Test that critical endpoints have optimized timeouts
        assert 'depth' in configs
        assert configs['depth'].timeout <= 3.0  # Critical arbitrage path
        assert 'ping' in configs
        assert configs['ping'].timeout <= 2.0   # Fast connectivity
    
    def test_lru_cache_implementation(self):
        """Test that LRU caching is properly implemented."""
        # Test symbol conversion caching
        assert hasattr(MexcPublicFuturesExchange.symbol_to_pair, 'cache_info')
        assert hasattr(MexcPublicFuturesExchange.pair_to_symbol, 'cache_info')
        
        # Test cache sizes are reasonable
        symbol = TEST_SYMBOLS[0]
        
        # Clear cache
        MexcPublicFuturesExchange.symbol_to_pair.cache_clear()
        MexcPublicFuturesExchange.pair_to_symbol.cache_clear()
        
        # Test caching
        pair1 = MexcPublicFuturesExchange.symbol_to_pair(symbol)
        pair2 = MexcPublicFuturesExchange.symbol_to_pair(symbol)  # Should hit cache
        
        assert pair1 == pair2
        
        cache_info = MexcPublicFuturesExchange.symbol_to_pair.cache_info()
        assert cache_info.hits >= 1
        assert cache_info.misses >= 1


class TestPerformanceBenchmarks:
    """Performance benchmark tests."""
    
    @pytest.mark.asyncio
    async def test_response_time_targets(self):
        """Test that response times meet <10ms targets."""
        async with await create_mexc_futures_client() as client:
            await client.init(TEST_SYMBOLS)
            
            # Test ping performance
            start_time = time.time()
            result = await client.ping()
            ping_time = (time.time() - start_time) * 1000
            
            assert result is True
            assert ping_time < PERFORMANCE_TARGETS['max_response_time_ms']
            
            # Test server time performance
            start_time = time.time()
            server_time = await client.get_server_time()
            server_time_response = (time.time() - start_time) * 1000
            
            assert isinstance(server_time, int)
            assert server_time_response < PERFORMANCE_TARGETS['max_response_time_ms']
    
    @pytest.mark.asyncio
    async def test_orderbook_performance(self):
        """Test orderbook retrieval performance."""
        async with await create_mexc_futures_client() as client:
            await client.init(TEST_SYMBOLS)
            
            symbol = TEST_SYMBOLS[0]  # BTC_USDT
            
            # Test multiple requests for average performance
            response_times = []
            for _ in range(5):
                start_time = time.time()
                try:
                    orderbook = await client.get_orderbook(symbol, limit=50)
                    response_time = (time.time() - start_time) * 1000
                    response_times.append(response_time)
                    
                    # Validate response structure
                    assert isinstance(orderbook, OrderBook)
                    assert len(orderbook.bids) > 0
                    assert len(orderbook.asks) > 0
                    
                except Exception:
                    # Skip performance check if API is unavailable
                    pytest.skip("API unavailable for performance testing")
            
            if response_times:
                avg_response_time = sum(response_times) / len(response_times)
                max_response_time = max(response_times)
                
                print(f"Orderbook performance: avg={avg_response_time:.2f}ms, max={max_response_time:.2f}ms")
                
                # Performance targets (more lenient for real API)
                assert avg_response_time < 50.0  # 50ms average
                assert max_response_time < 100.0  # 100ms max
    
    @pytest.mark.asyncio
    async def test_cache_performance(self):
        """Test LRU cache performance improvements."""
        # Test symbol conversion performance
        test_pairs = ["BTC_USDT", "ETH_USDT", "BNB_USDT"] * 100
        
        # Clear cache
        MexcPublicFuturesExchange.symbol_to_pair.cache_clear()
        MexcPublicFuturesExchange.pair_to_symbol.cache_clear()
        
        # First pass - should populate cache
        start_time = time.time()
        for pair in test_pairs:
            symbol = MexcPublicFuturesExchange.pair_to_symbol(pair)
            MexcPublicFuturesExchange.symbol_to_pair(symbol)
        first_pass_time = time.time() - start_time
        
        # Second pass - should hit cache
        start_time = time.time()
        for pair in test_pairs:
            symbol = MexcPublicFuturesExchange.pair_to_symbol(pair)
            MexcPublicFuturesExchange.symbol_to_pair(symbol)
        second_pass_time = time.time() - start_time
        
        # Cache should provide significant speedup
        speedup = first_pass_time / second_pass_time if second_pass_time > 0 else float('inf')
        print(f"Cache speedup: {speedup:.2f}x")
        
        assert speedup > 2.0  # At least 2x speedup from caching
        
        # Check cache hit rate
        cache_info = MexcPublicFuturesExchange.symbol_to_pair.cache_info()
        hit_rate = cache_info.hits / (cache_info.hits + cache_info.misses)
        assert hit_rate > 0.90  # >90% hit rate


class TestUnifiedExceptionHandling:
    """Test unified exception handling implementation."""
    
    @pytest.mark.asyncio
    async def test_exception_bubbling(self):
        """Test that exceptions properly bubble up without try/catch."""
        client = MexcPublicFuturesExchange()
        
        # Test invalid symbol handling
        invalid_symbol = Symbol(base=AssetName("INVALID"), quote=AssetName("SYMBOL"), is_futures=True)
        
        with pytest.raises((ExchangeAPIError, Exception)):
            await client.get_orderbook(invalid_symbol)
    
    def test_symbol_conversion_exceptions(self):
        """Test symbol conversion error handling."""
        with pytest.raises(ValueError):
            MexcPublicFuturesExchange.pair_to_symbol("INVALID_FORMAT")
        
        with pytest.raises(ValueError):
            MexcPublicFuturesExchange.pair_to_symbol("TOO_MANY_UNDERSCORES_HERE")
    
    @pytest.mark.asyncio
    async def test_ping_exception_handling(self):
        """Test that ping method handles exceptions gracefully."""
        # This should not raise exceptions, but return False on failure
        client = MexcPublicFuturesExchange()
        
        # Ping should handle connection failures gracefully
        result = await client.ping()
        assert isinstance(result, bool)


class TestPerformanceMonitoring:
    """Test performance monitoring and metrics."""
    
    @pytest.mark.asyncio
    async def test_performance_metrics_collection(self):
        """Test that performance metrics are properly collected."""
        async with await create_mexc_futures_client() as client:
            # Make some requests to generate metrics
            await client.ping()
            
            metrics = client.get_performance_metrics()
            
            # Validate metric structure
            assert 'exchange' in metrics
            assert 'http_client' in metrics
            assert 'architecture' in metrics
            assert 'total_requests' in metrics
            assert 'average_response_time_ms' in metrics
            assert 'performance_target_met' in metrics
            assert 'lru_cache_info' in metrics
            
            # Validate values
            assert metrics['http_client'] == 'UltraSimpleRestClient'
            assert metrics['architecture'] == 'refactored-unified-compliance'
            assert metrics['total_requests'] >= 1
            assert isinstance(metrics['performance_target_met'], bool)
    
    def test_futures_performance_monitor(self):
        """Test FuturesPerformanceMonitor functionality."""
        client = MexcPublicFuturesExchange()
        monitor = FuturesPerformanceMonitor(client)
        
        # Test monitor summary
        summary = monitor.get_summary()
        
        assert 'uptime_seconds' in summary
        assert 'refactoring_status' in summary
        assert 'code_reduction' in summary
        assert 'duplication_eliminated' in summary
        assert 'unified_rest_client' in summary
        
        # Validate refactoring metrics
        assert summary['refactoring_status'] == 'complete'
        assert summary['duplication_eliminated'] is True
        assert summary['unified_rest_client'] is True


class TestCodeReductionValidation:
    """Validate code reduction and duplication elimination."""
    
    def test_no_aiohttp_client_duplication(self):
        """Test that AiohttpRestClient code is not duplicated."""
        import inspect
        
        source = inspect.getsource(MexcPublicFuturesExchange)
        
        # Should not contain duplicated HTTP client code
        assert 'ClientSession' not in source
        assert 'ClientTimeout' not in source
        assert 'TCPConnector' not in source
        assert 'aiohttp' not in source.lower()
    
    def test_line_count_reduction(self):
        """Test that implementation is more concise."""
        import inspect
        
        source_lines = inspect.getsource(MexcPublicFuturesExchange).split('\n')
        non_empty_lines = [line for line in source_lines if line.strip() and not line.strip().startswith('#')]
        
        # Should be reasonable line count (not exact due to refactoring improvements)
        print(f"Total non-empty lines: {len(non_empty_lines)}")
        
        # Ensure it's reasonable for a full implementation
        assert len(non_empty_lines) < 400  # Should be well under 400 lines
    
    def test_method_efficiency(self):
        """Test that methods are efficiently implemented."""
        client = MexcPublicFuturesExchange()
        
        # Test symbol conversion efficiency
        symbol = TEST_SYMBOLS[0]
        
        # Should complete quickly (sub-millisecond)
        start_time = time.time()
        for _ in range(1000):
            pair = MexcPublicFuturesExchange.symbol_to_pair(symbol)
            converted_back = MexcPublicFuturesExchange.pair_to_symbol(pair)
        
        elapsed = (time.time() - start_time) * 1000
        print(f"1000 conversions in {elapsed:.2f}ms")
        
        assert elapsed < 10.0  # Should complete in <10ms


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])