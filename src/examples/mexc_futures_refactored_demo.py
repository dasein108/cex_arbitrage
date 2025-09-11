#!/usr/bin/env python3
"""
MEXC Futures Refactored Implementation Demo

Demonstrates the complete refactored MEXC futures implementation with:
- Direct PublicExchangeInterface compliance
- UltraSimpleRestClient integration
- Zero code duplication
- Unified exception handling
- Enhanced performance monitoring

This example showcases all key features of the refactored architecture.
"""

import asyncio
import time
import logging
from typing import List

# Import refactored MEXC futures implementation
from exchanges.mexc.mexc_futures_public import (
    MexcPublicFuturesExchange, 
    create_mexc_futures_client,
    FuturesPerformanceMonitor
)
from structs.exchange import Symbol, AssetName
from common.exceptions import ExchangeAPIError, RateLimitError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def demonstrate_refactored_futures():
    """
    Comprehensive demonstration of the refactored MEXC futures implementation.
    
    Shows all major features and performance improvements.
    """
    logger.info("🚀 Starting MEXC Futures Refactored Implementation Demo")
    
    # Create client using factory function
    async with await create_mexc_futures_client() as client:
        logger.info(f"✅ Created {client.exchange} client with refactored architecture")
        
        # Initialize performance monitor
        monitor = FuturesPerformanceMonitor(client)
        
        # Test symbols for demonstration
        test_symbols = [
            Symbol(base=AssetName("BTC"), quote=AssetName("USDT"), is_futures=True),
            Symbol(base=AssetName("ETH"), quote=AssetName("USDT"), is_futures=True),
            Symbol(base=AssetName("BNB"), quote=AssetName("USDT"), is_futures=True),
        ]
        
        # Initialize exchange with test symbols
        await client.init(test_symbols)
        
        # Demonstrate connectivity with ping
        logger.info("📡 Testing connectivity...")
        ping_result = await client.ping()
        logger.info(f"Ping result: {'✅ Success' if ping_result else '❌ Failed'}")
        
        # Get server time
        server_time = await client.get_server_time()
        logger.info(f"🕒 Server time: {server_time}")
        
        # Demonstrate exchange info retrieval
        logger.info("📊 Fetching exchange information...")
        start_time = time.time()
        
        try:
            exchange_info = await client.get_exchange_info()
            elapsed = (time.time() - start_time) * 1000
            
            logger.info(f"✅ Retrieved {len(exchange_info)} symbols in {elapsed:.2f}ms")
            
            # Show sample symbols
            sample_symbols = list(exchange_info.keys())[:3]
            for symbol in sample_symbols:
                info = exchange_info[symbol]
                logger.info(f"  Symbol: {symbol.base}_{symbol.quote}")
                logger.info(f"    Precision: Base={info.base_precision}, Quote={info.quote_precision}")
                logger.info(f"    Min amount: {info.min_base_amount}")
                logger.info(f"    Active: {not info.inactive}")
        
        except Exception as e:
            logger.error(f"❌ Exchange info failed: {e}")
        
        # Demonstrate order book retrieval with performance tracking
        logger.info("\n📈 Testing order book retrieval...")
        
        for symbol in test_symbols:
            try:
                start_time = time.time()
                orderbook = await client.get_orderbook(symbol, limit=50)
                elapsed = (time.time() - start_time) * 1000
                
                logger.info(f"✅ {symbol.base}_{symbol.quote} orderbook in {elapsed:.2f}ms")
                logger.info(f"  Bids: {len(orderbook.bids)}, Asks: {len(orderbook.asks)}")
                
                if orderbook.bids and orderbook.asks:
                    best_bid = orderbook.bids[0]
                    best_ask = orderbook.asks[0]
                    spread = best_ask.price - best_bid.price
                    spread_pct = (spread / best_bid.price) * 100
                    
                    logger.info(f"  Best bid: ${best_bid.price:.2f}")
                    logger.info(f"  Best ask: ${best_ask.price:.2f}")
                    logger.info(f"  Spread: ${spread:.2f} ({spread_pct:.4f}%)")
                
            except Exception as e:
                logger.error(f"❌ Orderbook for {symbol.base}_{symbol.quote} failed: {e}")
        
        # Demonstrate recent trades retrieval
        logger.info("\n📊 Testing recent trades retrieval...")
        
        for symbol in test_symbols:
            try:
                start_time = time.time()
                trades = await client.get_recent_trades(symbol, limit=10)
                elapsed = (time.time() - start_time) * 1000
                
                logger.info(f"✅ {symbol.base}_{symbol.quote} trades in {elapsed:.2f}ms")
                logger.info(f"  Recent trades: {len(trades)}")
                
                if trades:
                    latest_trade = trades[0]
                    logger.info(f"  Latest: ${latest_trade.price:.2f} x {latest_trade.amount:.4f} ({latest_trade.side})")
                
            except Exception as e:
                logger.error(f"❌ Trades for {symbol.base}_{symbol.quote} failed: {e}")
        
        # Demonstrate performance metrics
        logger.info("\n📊 Performance Analysis:")
        
        # Get client performance metrics
        client_metrics = client.get_performance_metrics()
        logger.info(f"  HTTP Client: {client_metrics['http_client']}")
        logger.info(f"  Architecture: {client_metrics['architecture']}")
        logger.info(f"  Total requests: {client_metrics['total_requests']}")
        logger.info(f"  Avg response time: {client_metrics['average_response_time_ms']:.2f}ms")
        logger.info(f"  Performance target met: {'✅' if client_metrics['performance_target_met'] else '❌'}")
        logger.info(f"  Connection pool optimization: {'✅' if client_metrics['connection_pool_optimization'] else '❌'}")
        logger.info(f"  Unified exception handling: {'✅' if client_metrics['unified_exception_handling'] else '❌'}")
        
        # Get performance monitor summary
        monitor_summary = monitor.get_summary()
        logger.info(f"  Uptime: {monitor_summary['uptime_seconds']:.2f}s")
        logger.info(f"  Requests/sec: {monitor_summary['requests_per_second']:.2f}")
        logger.info(f"  Meets arbitrage targets: {'✅' if monitor_summary['meets_arbitrage_targets'] else '❌'}")
        logger.info(f"  Interface compliant: {'✅' if monitor_summary['interface_compliant'] else '❌'}")
        logger.info(f"  Refactoring status: {monitor_summary['refactoring_status']}")
        logger.info(f"  Code reduction: {monitor_summary['code_reduction']}")
        logger.info(f"  Duplication eliminated: {'✅' if monitor_summary['duplication_eliminated'] else '❌'}")
        
        # Display LRU cache statistics
        logger.info("\n🗄️ LRU Cache Performance:")
        cache_info = client_metrics['lru_cache_info']
        for cache_name, info in cache_info.items():
            hit_rate = info['hits'] / (info['hits'] + info['misses']) * 100 if (info['hits'] + info['misses']) > 0 else 0
            logger.info(f"  {cache_name}: {info['hits']} hits, {info['misses']} misses ({hit_rate:.1f}% hit rate)")
        
        # Test WebSocket health (should show no WebSocket in public-only implementation)
        ws_health = client.get_websocket_health()
        logger.info(f"\n🌐 WebSocket Health: {ws_health['message']}")
        
        logger.info("\n✅ MEXC Futures Refactored Demo Complete!")
        logger.info("🎯 Key Achievements:")
        logger.info("   • Direct PublicExchangeInterface inheritance")
        logger.info("   • UltraSimpleRestClient integration")
        logger.info("   • Zero code duplication")
        logger.info("   • Unified exception handling")
        logger.info("   • Enhanced LRU caching")
        logger.info("   • Sub-10ms response time optimization")


async def demonstrate_symbol_conversion():
    """Demonstrate optimized symbol conversion with caching."""
    logger.info("\n🔄 Symbol Conversion Performance Demo")
    
    # Test symbols
    test_pairs = ["BTC_USDT", "ETH_USDT", "BNB_USDT", "SOL_USDT", "ADA_USDT"]
    
    # Convert pairs to symbols and back (should hit cache on second pass)
    start_time = time.time()
    
    for pair in test_pairs:
        symbol = MexcPublicFuturesExchange.pair_to_symbol(pair)
        converted_back = MexcPublicFuturesExchange.symbol_to_pair(symbol)
        
        logger.info(f"  {pair} -> {symbol} -> {converted_back}")
        assert pair == converted_back, f"Conversion mismatch: {pair} != {converted_back}"
    
    elapsed = (time.time() - start_time) * 1000
    logger.info(f"✅ Symbol conversions completed in {elapsed:.2f}ms")
    
    # Test cache performance by repeating conversions
    start_time = time.time()
    for _ in range(1000):
        for pair in test_pairs:
            symbol = MexcPublicFuturesExchange.pair_to_symbol(pair)
            MexcPublicFuturesExchange.symbol_to_pair(symbol)
    
    elapsed = (time.time() - start_time) * 1000
    logger.info(f"✅ 10,000 cached conversions in {elapsed:.2f}ms ({elapsed/10000:.4f}ms per conversion)")


async def demonstrate_error_handling():
    """Demonstrate unified exception handling."""
    logger.info("\n⚠️ Error Handling Demo")
    
    async with await create_mexc_futures_client() as client:
        # Test with invalid symbol
        try:
            invalid_symbol = Symbol(base=AssetName("INVALID"), quote=AssetName("PAIR"), is_futures=True)
            await client.get_orderbook(invalid_symbol)
        except ExchangeAPIError as e:
            logger.info(f"✅ Caught ExchangeAPIError: {e}")
        except Exception as e:
            logger.info(f"✅ Caught general exception: {e}")
        
        # Test pair conversion error handling
        try:
            MexcPublicFuturesExchange.pair_to_symbol("INVALID_PAIR_FORMAT")
        except ValueError as e:
            logger.info(f"✅ Caught ValueError for invalid pair: {e}")


if __name__ == "__main__":
    async def main():
        """Run all demonstrations."""
        try:
            await demonstrate_refactored_futures()
            await demonstrate_symbol_conversion()
            await demonstrate_error_handling()
            
        except KeyboardInterrupt:
            logger.info("Demo interrupted by user")
        except Exception as e:
            logger.error(f"Demo failed: {e}")
    
    # Run the demonstration
    asyncio.run(main())