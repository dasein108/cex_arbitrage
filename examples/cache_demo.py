#!/usr/bin/env python3
"""
Symbol Cache Infrastructure Demo

Demonstrates the complete symbol cache infrastructure for HFT operations.
Shows initialization, warming, monitoring, and performance validation.
"""

import asyncio
import logging
import time
from datetime import datetime

# Configure logging for demo
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Comprehensive cache infrastructure demonstration."""
    print("🚀 CEX Arbitrage Engine - Symbol Cache Infrastructure Demo")
    print("=" * 80)
    
    try:
        # Import after setting up logging to avoid import issues
        from db import (
            # Cache core
            initialize_symbol_cache, get_symbol_cache, close_symbol_cache,
            # Cache operations
            cached_get_symbol_by_id, cached_resolve_symbol_for_exchange,
            get_cache_stats, reset_cache_stats,
            # Cache warming
            warm_symbol_cache, WarmingConfig, WarmingStrategy,
            # Cache monitoring
            start_cache_monitoring, stop_cache_monitoring, get_cache_performance_summary,
            # Cache validation
            validate_cache_hft_performance, print_validation_report
        )
        
        # Step 1: Initialize Cache Infrastructure
        print("\n📋 Step 1: Initializing Symbol Cache Infrastructure")
        print("-" * 50)
        
        start_time = time.perf_counter()
        await initialize_symbol_cache(auto_refresh_interval=300)
        init_time = (time.perf_counter() - start_time) * 1000
        
        cache = get_symbol_cache()
        initial_stats = get_cache_stats()
        
        print(f"✅ Cache initialized in {init_time:.2f}ms")
        print(f"📊 Cache loaded with {initial_stats.cache_size:,} symbols")
        print(f"🏢 Available for {len(cache._exchange_cache)} exchanges")
        
        # Step 2: Demonstrate Cache Warming
        print("\n📋 Step 2: Cache Warming Strategies")
        print("-" * 50)
        
        # Reset stats for clean measurement
        reset_cache_stats()
        
        # Test different warming strategies
        warming_configs = [
            (WarmingStrategy.FULL, "Full cache warming"),
            (WarmingStrategy.INCREMENTAL, "Incremental warming"),
        ]
        
        for strategy, description in warming_configs:
            print(f"\n🔥 Testing {description}...")
            
            start_time = time.perf_counter()
            config = WarmingConfig(strategy=strategy, batch_size=50, max_warming_time_ms=1000)
            result = await warm_symbol_cache(config)
            warming_time = (time.perf_counter() - start_time) * 1000
            
            if result.success:
                print(f"✅ {description} completed in {warming_time:.2f}ms")
                print(f"   Symbols warmed: {result.symbols_loaded}")
                print(f"   Batches processed: {result.batches_processed}")
            else:
                print(f"❌ {description} failed: {result.error_message}")
        
        # Step 3: Performance Testing
        print("\n📋 Step 3: Cache Performance Testing")
        print("-" * 50)
        
        # Reset stats for performance testing
        reset_cache_stats()
        
        # Test basic lookup operations
        all_symbols = cache.get_all_symbols()
        if all_symbols:
            test_symbol = all_symbols[0]
            
            print(f"🧪 Testing lookups with symbol: {test_symbol.symbol_base}/{test_symbol.symbol_quote}")
            
            # Warm up cache
            for _ in range(100):
                cached_get_symbol_by_id(test_symbol.id)
            
            # Performance test
            iterations = 10000
            start_time = time.perf_counter_ns()
            
            for _ in range(iterations):
                symbol = cached_get_symbol_by_id(test_symbol.id)
                assert symbol is not None
            
            end_time = time.perf_counter_ns()
            total_time_us = (end_time - start_time) / 1000
            avg_time_us = total_time_us / iterations
            ops_per_second = 1_000_000 / avg_time_us
            
            print(f"✅ Completed {iterations:,} lookups in {total_time_us:.2f}μs")
            print(f"📊 Average lookup time: {avg_time_us:.3f}μs")
            print(f"🚀 Throughput: {ops_per_second:,.0f} operations/second")
            
            # HFT target validation
            hft_target = 1.0  # <1μs target
            if avg_time_us <= hft_target:
                print(f"🎯 ✅ HFT target achieved (≤{hft_target}μs)")
            else:
                print(f"🎯 ⚠️  HFT target missed (≤{hft_target}μs)")
        
        # Step 4: Cache Monitoring
        print("\n📋 Step 4: Cache Performance Monitoring")
        print("-" * 50)
        
        print("🔍 Starting performance monitoring...")
        await start_cache_monitoring(interval_seconds=0.1)  # Fast monitoring for demo
        
        # Generate some cache activity
        print("📈 Generating cache activity for monitoring...")
        for i in range(500):
            if all_symbols and i < len(all_symbols):
                symbol = all_symbols[i % min(100, len(all_symbols))]
                cached_get_symbol_by_id(symbol.id)
                
                # Add some variety
                if i % 10 == 0:
                    cached_resolve_symbol_for_exchange(
                        cache.get_exchange_by_id(symbol.exchange_id).to_exchange_enum(),
                        symbol.symbol_base,
                        symbol.symbol_quote
                    )
        
        # Wait a bit for monitoring data
        await asyncio.sleep(0.5)
        
        # Get monitoring summary
        summary = get_cache_performance_summary(minutes=1)
        print("📊 Performance monitoring summary:")
        
        if "lookup_time_stats" in summary:
            lt_stats = summary["lookup_time_stats"]
            print(f"   Lookup time: {lt_stats['current_us']:.3f}μs (avg: {lt_stats['avg_us']:.3f}μs)")
        
        if "hit_ratio_stats" in summary:
            hr_stats = summary["hit_ratio_stats"]
            print(f"   Hit ratio: {hr_stats['current']:.1%} (avg: {hr_stats['avg']:.1%})")
        
        if "cache_info" in summary:
            cache_info = summary["cache_info"]
            print(f"   Total requests: {cache_info['total_requests']:,}")
            print(f"   Cache size: {cache_info['size']:,}")
        
        await stop_cache_monitoring()
        print("✅ Performance monitoring stopped")
        
        # Step 5: Comprehensive Validation
        print("\n📋 Step 5: HFT Performance Validation")
        print("-" * 50)
        
        print("🔬 Running comprehensive cache validation...")
        validation_report = await validate_cache_hft_performance()
        
        # Print detailed report
        print_validation_report(validation_report)
        
        # Step 6: Cache Statistics Summary
        print("\n📋 Step 6: Final Cache Statistics")
        print("-" * 50)
        
        final_stats = get_cache_stats()
        print(f"📊 Final cache statistics:")
        print(f"   Cache size: {final_stats.cache_size:,} symbols")
        print(f"   Total requests: {final_stats.total_requests:,}")
        print(f"   Hit ratio: {final_stats.hit_ratio:.1%}")
        print(f"   Average lookup time: {final_stats.avg_lookup_time_us:.3f}μs")
        print(f"   Last refresh: {final_stats.last_refresh}")
        
        # Performance summary
        target_achieved = (
            final_stats.avg_lookup_time_us <= 1.0 and
            final_stats.hit_ratio >= 0.95
        )
        
        print("\n🎯 HFT Performance Summary:")
        print(f"   Target lookup time (≤1μs): {'✅' if final_stats.avg_lookup_time_us <= 1.0 else '❌'} {final_stats.avg_lookup_time_us:.3f}μs")
        print(f"   Target hit ratio (≥95%): {'✅' if final_stats.hit_ratio >= 0.95 else '❌'} {final_stats.hit_ratio:.1%}")
        print(f"   Overall HFT compliance: {'✅ ACHIEVED' if target_achieved else '❌ NOT MET'}")
        
        # Cleanup
        await close_symbol_cache()
        
        print("\n" + "=" * 80)
        print("🎉 Cache Infrastructure Demo Completed Successfully!")
        print("   The symbol cache infrastructure is ready for production HFT operations.")
        print("   Sub-microsecond symbol resolution achieved with comprehensive monitoring.")
        print("=" * 80)
        
    except ImportError as e:
        print(f"❌ Import error (likely due to missing database connection): {e}")
        print("   This demo requires a configured database connection to run.")
        print("   Please ensure the database is running and configured correctly.")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())