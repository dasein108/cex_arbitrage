#!/usr/bin/env python3
"""
Symbol Mapper Factory Demo

Demonstrates the new factory-based symbol mapping architecture.
Shows how to use ExchangeSymbolMapperFactory instead of singleton pattern.

Usage:
    PYTHONPATH=src python src/examples/symbol_mapper_factory_demo.py
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.cex.utils import ExchangeSymbolMapperFactory, get_symbol_mapper
from structs.exchange import Symbol, AssetName
from cex.mexc.services.symbol_mapper import MexcSymbolMapperInterface  # Import to register mappers
from cex.gateio.services.symbol_mapper import GateioSymbolMapperInterface

# Import to register mappers


def demo_factory_usage():
    """Demonstrate factory pattern usage."""
    print("🏭 Symbol Mapper Factory Demo")
    print("=" * 50)
    ExchangeSymbolMapperFactory.register_mapper("MEXC", MexcSymbolMapperInterface)
    ExchangeSymbolMapperFactory.register_mapper("GATEIO", GateioSymbolMapperInterface)
    # Show supported cex
    supported = ExchangeSymbolMapperFactory.get_supported_exchanges()
    print(f"📋 Supported Exchanges: {supported}")
    print()
    
    # Get mappers using factory
    mexc_mapper = ExchangeSymbolMapperFactory.get_mapper('MEXC')
    gateio_mapper = ExchangeSymbolMapperFactory.get_mapper('GATEIO')
    
    print(f"✅ MEXC Mapper: {mexc_mapper.__class__.__name__}")
    print(f"✅ Gate.io Mapper: {gateio_mapper.__class__.__name__}")
    print()
    
    # Test symbol conversion
    test_symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
    
    # MEXC format (concatenated)
    mexc_pair = mexc_mapper.symbol_to_pair(test_symbol)
    print(f"🔄 MEXC Format: {test_symbol} → {mexc_pair}")
    
    # Gate.io format (underscore)
    gateio_pair = gateio_mapper.symbol_to_pair(test_symbol)
    print(f"🔄 Gate.io Format: {test_symbol} → {gateio_pair}")
    print()
    
    # Test reverse conversion
    mexc_symbol = mexc_mapper.pair_to_symbol("ETHUSDC")
    gateio_symbol = gateio_mapper.pair_to_symbol("ETH_USDC")
    
    print(f"🔄 MEXC Parse: ETHUSDC → {mexc_symbol}")
    print(f"🔄 Gate.io Parse: ETH_USDC → {gateio_symbol}")
    print()


def demo_convenience_function():
    """Demonstrate convenience function usage."""
    print("🚀 Convenience Function Demo")
    print("=" * 50)
    
    # Using convenience function
    mexc_mapper = get_symbol_mapper('MEXC')
    gateio_mapper = get_symbol_mapper('GATEIO')
    
    print(f"✅ MEXC via convenience: {mexc_mapper.__class__.__name__}")
    print(f"✅ Gate.io via convenience: {gateio_mapper.__class__.__name__}")
    print()


def demo_performance_comparison():
    """Compare performance with repeated operations."""
    print("⚡ Performance Demo")
    print("=" * 50)
    
    mexc_mapper = get_symbol_mapper('MEXC')
    test_symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
    
    # Warm up cache
    mexc_mapper.symbol_to_pair(test_symbol)
    mexc_mapper.pair_to_symbol("BTCUSDT")
    
    # Performance test
    iterations = 10000
    
    # Symbol to pair conversion
    start_time = time.perf_counter()
    for _ in range(iterations):
        mexc_mapper.symbol_to_pair(test_symbol)
    symbol_to_pair_time = time.perf_counter() - start_time
    
    # Pair to symbol conversion  
    start_time = time.perf_counter()
    for _ in range(iterations):
        mexc_mapper.pair_to_symbol("BTCUSDT")
    pair_to_symbol_time = time.perf_counter() - start_time
    
    print(f"📊 Performance Results ({iterations:,} iterations):")
    print(f"   Symbol → Pair: {symbol_to_pair_time*1000:.3f}ms ({symbol_to_pair_time/iterations*1000000:.3f}μs per operation)")
    print(f"   Pair → Symbol: {pair_to_symbol_time*1000:.3f}ms ({pair_to_symbol_time/iterations*1000000:.3f}μs per operation)")
    print()


def demo_cache_statistics():
    """Show cache statistics and validation."""
    print("📊 Cache Statistics Demo")
    print("=" * 50)
    
    # Get all mappers to populate caches
    mexc_mapper = get_symbol_mapper('MEXC')
    gateio_mapper = get_symbol_mapper('GATEIO')
    
    # Perform some operations to populate caches
    test_symbols = [
        Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
        Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
        Symbol(base=AssetName("BNB"), quote=AssetName("USDC")),
    ]
    
    for symbol in test_symbols:
        mexc_mapper.symbol_to_pair(symbol)
        gateio_mapper.symbol_to_pair(symbol)
    
    # Show statistics
    stats = ExchangeSymbolMapperFactory.get_cache_statistics()
    
    print(f"🏭 Factory Info:")
    factory_info = stats['factory_info']
    print(f"   Registered Exchanges: {factory_info['registered_exchanges']}")
    print(f"   Active Instances: {factory_info['active_instances']}")
    print(f"   Supported: {factory_info['supported_exchanges']}")
    print()
    
    print(f"📈 Exchange Cache Stats:")
    for exchange, stats_data in stats['exchange_stats'].items():
        cache_stats = stats_data['cache_stats']
        print(f"   {exchange}:")
        print(f"     Symbol→Pair Cache: {cache_stats['symbol_to_pair_cache_size']}")
        print(f"     Pair→Symbol Cache: {cache_stats['pair_to_symbol_cache_size']}")
        print(f"     Quote Assets: {len(stats_data['quote_assets'])}")
    print()


def demo_validation():
    """Demonstrate validation features."""
    print("✅ Validation Demo")
    print("=" * 50)
    
    # Validate all mappers
    validation_results = ExchangeSymbolMapperFactory.validate_all_mappers()
    
    print("🔍 Mapper Validation Results:")
    for exchange, is_valid in validation_results.items():
        status = "✅ Valid" if is_valid else "❌ Invalid"
        print(f"   {exchange}: {status}")
    print()
    
    # Test symbol validation
    mexc_mapper = get_symbol_mapper('MEXC')
    
    valid_symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
    invalid_symbol = Symbol(base=AssetName("BTC"), quote=AssetName("INVALID"))
    
    print("🔍 Symbol Validation:")
    print(f"   {valid_symbol}: {'✅ Valid' if mexc_mapper.validate_symbol(valid_symbol) else '❌ Invalid'}")
    print(f"   {invalid_symbol}: {'✅ Valid' if mexc_mapper.validate_symbol(invalid_symbol) else '❌ Invalid'}")
    print()


def main():
    """Run all demonstrations."""
    try:
        demo_factory_usage()
        demo_convenience_function() 
        demo_performance_comparison()
        demo_cache_statistics()
        demo_validation()
        
        print("🎉 All demos completed successfully!")
        print("\n💡 Migration Guide:")
        print("   Old: mexc_symbol_mapper = MexcSymbolMapper()")
        print("   New: mexc_mapper = get_symbol_mapper('MEXC')")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()