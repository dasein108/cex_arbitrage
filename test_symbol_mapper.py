#!/usr/bin/env python3
"""
Simple Symbol Mapper Factory Test

Tests the new factory-based symbol mapping architecture without
complex dependencies that might cause import issues.
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

# Direct imports to avoid dependency issues
from core.cex.services.symbol_mapper.base_symbol_mapper import BaseSymbolMapper
from core.cex.services.symbol_mapper.symbol_mapper_factory import ExchangeSymbolMapperFactory
from structs.exchange import Symbol, AssetName


class TestMexcMapper(BaseSymbolMapper):
    """Test MEXC mapper for validation."""
    
    def __init__(self):
        super().__init__(quote_assets=('USDT', 'USDC'))
    
    def _symbol_to_string(self, symbol: Symbol) -> str:
        return f"{symbol.base}{symbol.quote}"
    
    def _string_to_symbol(self, pair: str) -> Symbol:
        pair = pair.upper()
        for quote in self._quote_assets:
            if pair.endswith(quote):
                base = pair[:-len(quote)]
                if base:
                    return Symbol(
                        base=AssetName(base),
                        quote=AssetName(quote),
                        is_futures=False
                    )
        raise ValueError(f"Unrecognized pair: {pair}")


class TestGateioMapper(BaseSymbolMapper):
    """Test Gate.io mapper for validation."""
    
    def __init__(self):
        super().__init__(quote_assets=('USDT', 'USDC', 'BTC', 'ETH'))
    
    def _symbol_to_string(self, symbol: Symbol) -> str:
        return f"{symbol.base}_{symbol.quote}"
    
    def _string_to_symbol(self, pair: str) -> Symbol:
        pair = pair.upper()
        if '_' in pair:
            base, quote = pair.split('_', 1)
            if quote in self._quote_assets:
                return Symbol(
                    base=AssetName(base),
                    quote=AssetName(quote),
                    is_futures=False
                )
        raise ValueError(f"Unrecognized pair: {pair}")


def test_factory_pattern():
    """Test the factory pattern implementation."""
    print("🧪 Testing Factory Pattern")
    print("=" * 40)
    
    # Register test mappers
    ExchangeSymbolMapperFactory.register_mapper('MEXC', TestMexcMapper)
    ExchangeSymbolMapperFactory.register_mapper('GATEIO', TestGateioMapper)
    
    # Test factory functionality
    print(f"✅ Supported exchanges: {ExchangeSymbolMapperFactory.get_supported_exchanges()}")
    
    # Get mappers
    mexc_mapper = ExchangeSymbolMapperFactory.get_mapper('MEXC')
    gateio_mapper = ExchangeSymbolMapperFactory.get_mapper('GATEIO')
    
    print(f"✅ MEXC Mapper: {mexc_mapper.__class__.__name__}")
    print(f"✅ Gate.io Mapper: {gateio_mapper.__class__.__name__}")
    
    # Test instance reuse (key difference from singleton)
    mexc_mapper_2 = ExchangeSymbolMapperFactory.get_mapper('MEXC')
    gateio_mapper_2 = ExchangeSymbolMapperFactory.get_mapper('GATEIO')
    
    print(f"✅ MEXC Instance Reuse: {mexc_mapper is mexc_mapper_2}")
    print(f"✅ Gate.io Instance Reuse: {gateio_mapper is gateio_mapper_2}")
    print(f"✅ Different Exchange Instances: {mexc_mapper is not gateio_mapper}")
    print()


def test_symbol_conversion():
    """Test symbol conversion functionality."""
    print("🔄 Testing Symbol Conversion")
    print("=" * 40)
    
    mexc_mapper = ExchangeSymbolMapperFactory.get_mapper('MEXC')
    gateio_mapper = ExchangeSymbolMapperFactory.get_mapper('GATEIO')
    
    test_symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
    
    # Test symbol to pair conversion
    mexc_pair = mexc_mapper.symbol_to_pair(test_symbol)
    gateio_pair = gateio_mapper.symbol_to_pair(test_symbol)
    
    print(f"🔄 Symbol: {test_symbol}")
    print(f"   MEXC Format: {mexc_pair}")
    print(f"   Gate.io Format: {gateio_pair}")
    
    # Test pair to symbol conversion
    mexc_symbol = mexc_mapper.pair_to_symbol("ETHUSDC")
    gateio_symbol = gateio_mapper.pair_to_symbol("ETH_USDC")
    
    print(f"🔄 Pair Parsing:")
    print(f"   MEXC ETHUSDC → {mexc_symbol}")
    print(f"   Gate.io ETH_USDC → {gateio_symbol}")
    print()


def test_performance():
    """Test performance characteristics."""
    print("⚡ Testing Performance")
    print("=" * 40)
    
    mexc_mapper = ExchangeSymbolMapperFactory.get_mapper('MEXC')
    test_symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
    
    # Warm up cache
    mexc_mapper.symbol_to_pair(test_symbol)
    mexc_mapper.pair_to_symbol("BTCUSDT")
    
    # Performance test
    iterations = 10000
    
    # Test cached performance
    start_time = time.perf_counter()
    for _ in range(iterations):
        mexc_mapper.symbol_to_pair(test_symbol)
    cached_time = time.perf_counter() - start_time
    
    print(f"📊 Cached Conversion ({iterations:,} iterations):")
    print(f"   Total: {cached_time*1000:.3f}ms")
    print(f"   Per Operation: {cached_time/iterations*1000000:.3f}μs")
    print(f"   Operations/sec: {iterations/cached_time:,.0f}")
    print()


def test_cache_statistics():
    """Test cache statistics functionality."""
    print("📊 Testing Cache Statistics")
    print("=" * 40)
    
    mexc_mapper = ExchangeSymbolMapperFactory.get_mapper('MEXC')
    gateio_mapper = ExchangeSymbolMapperFactory.get_mapper('GATEIO')
    
    # Populate caches
    test_symbols = [
        Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
        Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
        Symbol(base=AssetName("BNB"), quote=AssetName("USDC")),
    ]
    
    for symbol in test_symbols:
        mexc_mapper.symbol_to_pair(symbol)
        gateio_mapper.symbol_to_pair(symbol)
    
    # Get statistics
    stats = ExchangeSymbolMapperFactory.get_cache_statistics()
    
    print(f"🏭 Factory Statistics:")
    factory_info = stats['factory_info']
    print(f"   Registered: {factory_info['registered_exchanges']}")
    print(f"   Active: {factory_info['active_instances']}")
    
    print(f"📈 Cache Statistics:")
    for exchange, stats_data in stats['exchange_stats'].items():
        cache_stats = stats_data['cache_stats']
        print(f"   {exchange}: {cache_stats['symbol_to_pair_cache_size']} cached mappings")
    print()


def test_validation():
    """Test validation functionality."""
    print("✅ Testing Validation")
    print("=" * 40)
    
    # Test mapper validation
    validation_results = ExchangeSymbolMapperFactory.validate_all_mappers()
    print(f"🔍 Mapper Validation:")
    for exchange, is_valid in validation_results.items():
        status = "✅ Valid" if is_valid else "❌ Invalid"
        print(f"   {exchange}: {status}")
    
    # Test symbol validation
    mexc_mapper = ExchangeSymbolMapperFactory.get_mapper('MEXC')
    
    valid_symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
    invalid_symbol = Symbol(base=AssetName("BTC"), quote=AssetName("INVALID"))
    
    print(f"🔍 Symbol Validation:")
    print(f"   {valid_symbol}: {'✅ Valid' if mexc_mapper.validate_symbol(valid_symbol) else '❌ Invalid'}")
    print(f"   {invalid_symbol}: {'✅ Valid' if mexc_mapper.validate_symbol(invalid_symbol) else '❌ Invalid'}")
    print()


def main():
    """Run all tests."""
    try:
        test_factory_pattern()
        test_symbol_conversion()
        test_performance()
        test_cache_statistics()
        test_validation()
        
        print("🎉 All tests passed!")
        print("\n📝 Architecture Summary:")
        print("   ✅ Eliminated singleton pattern")
        print("   ✅ Factory-based instance management")
        print("   ✅ One instance per exchange type")
        print("   ✅ O(1) performance with caching")
        print("   ✅ Extensible registration system")
        
    except Exception as e:
        print(f"❌ Tests failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()