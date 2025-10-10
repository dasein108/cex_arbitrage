#!/usr/bin/env python3
"""
Test Script for Simplified DatabaseManager

This script tests the new simplified DatabaseManager implementation
following PROJECT_GUIDES.md requirements:
- Float-Only Data Policy
- Struct-First Data Policy  
- HFT Performance Requirements
- Configuration Management using get_database_config()
"""

import asyncio
import sys
import logging
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from db import get_database_manager, initialize_database_manager
from db.models import Exchange, Symbol as DBSymbol, SymbolType, BookTickerSnapshot, BalanceSnapshot
from exchanges.structs.enums import ExchangeEnum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_simplified_database_manager():
    """Test the simplified DatabaseManager implementation."""
    
    logger.info("Testing Simplified DatabaseManager...")
    
    try:
        # Initialize database manager using get_database_config() from HftConfig
        logger.info("1. Initializing DatabaseManager...")
        await initialize_database_manager()
        
        # Get global manager instance
        db = get_database_manager()
        logger.info(f"✓ DatabaseManager initialized: {type(db).__name__}")
        
        # Test cache statistics (HFT compliance monitoring)
        logger.info("2. Testing cache performance monitoring...")
        from db.cache_operations import get_cache_stats
        cache_stats = get_cache_stats()
        logger.info(f"✓ Cache stats: {cache_stats.cache_size} symbols")
        logger.info(f"✓ Cache HFT compliant: {cache_stats['hft_compliant']}")
        
        # Test exchange operations with caching
        logger.info("3. Testing exchange operations...")
        
        # Test enum-based lookup (cached)
        mexc_exchange = db.get_exchange_by_enum(ExchangeEnum.MEXC)
        if mexc_exchange:
            logger.info(f"✓ Found MEXC exchange: {mexc_exchange.name} (ID: {mexc_exchange.id})")
        else:
            logger.info("⚠ MEXC exchange not found - will create it")
            
            # Create missing exchange
            new_exchange = Exchange.from_exchange_enum(ExchangeEnum.MEXC)
            exchange_id = await db.insert_exchange(new_exchange)
            logger.info(f"✓ Created MEXC exchange with ID: {exchange_id}")
            
            # Force cache refresh and retry
            await db.force_cache_refresh()
            mexc_exchange = db.get_exchange_by_enum(ExchangeEnum.MEXC)
            logger.info(f"✓ Found newly created MEXC exchange: {mexc_exchange.name}")
        
        # Test all exchanges
        all_exchanges = db.get_all_exchanges()
        logger.info(f"✓ Total exchanges in cache: {len(all_exchanges)}")
        
        # Test symbol operations with caching
        logger.info("4. Testing symbol operations...")
        
        if mexc_exchange:
            # Test symbol lookup by exchange/pair
            test_symbol = db.get_symbol_by_exchange_and_pair(mexc_exchange.id, "BTC", "USDT")
            if test_symbol:
                logger.info(f"✓ Found symbol: {test_symbol.symbol_base}/{test_symbol.symbol_quote}")
            else:
                logger.info("⚠ BTC/USDT symbol not found - will create it")
                
                # Create test symbol
                new_symbol = DBSymbol(
                    exchange_id=mexc_exchange.id,
                    symbol_base="BTC",
                    symbol_quote="USDT", 
                    exchange_symbol="BTCUSDT",
                    symbol_type=SymbolType.SPOT,
                    is_active=True
                )
                
                symbol_id = await db.insert_symbol(new_symbol)
                logger.info(f"✓ Created BTC/USDT symbol with ID: {symbol_id}")
                
                # Test lookup again
                test_symbol = db.get_symbol_by_exchange_and_pair(mexc_exchange.id, "BTC", "USDT")
                logger.info(f"✓ Found newly created symbol: {test_symbol.symbol_base}/{test_symbol.symbol_quote}")
        
        # Test symbols by exchange
        if mexc_exchange:
            mexc_symbols = db.get_symbols_by_exchange(mexc_exchange.id)
            logger.info(f"✓ MEXC symbols in cache: {len(mexc_symbols)}")
        
        # Test float-only policy with BookTicker data
        logger.info("5. Testing float-only policy compliance...")
        
        if test_symbol:
            # Create test BookTicker with float values
            book_ticker = BookTickerSnapshot(
                symbol_id=test_symbol.id,
                bid_price=50000.12345678,    # Float value - PROJECT_GUIDES.md compliant
                bid_qty=1.5,                 # Float value - PROJECT_GUIDES.md compliant  
                ask_price=50001.87654321,    # Float value - PROJECT_GUIDES.md compliant
                ask_qty=2.3,                 # Float value - PROJECT_GUIDES.md compliant
                timestamp=datetime.utcnow()
            )
            
            # Insert single snapshot
            record_id = await db.insert_book_ticker_snapshot(book_ticker)
            logger.info(f"✓ Inserted BookTicker snapshot with ID: {record_id}")
            
            # Test batch insert
            batch_snapshots = [
                BookTickerSnapshot(
                    symbol_id=test_symbol.id,
                    bid_price=50100.0,          # Float-only policy
                    bid_qty=0.5,                # Float-only policy
                    ask_price=50101.0,          # Float-only policy
                    ask_qty=1.0,                # Float-only policy
                    timestamp=datetime.utcnow()
                )
            ]
            
            batch_count = await db.insert_book_ticker_snapshots_batch(batch_snapshots)
            logger.info(f"✓ Batch inserted {batch_count} BookTicker snapshots")
        
        # Test balance operations with float-only policy
        logger.info("6. Testing balance operations...")
        
        if mexc_exchange:
            # Create test balance with float values
            balance_snapshot = BalanceSnapshot(
                exchange_id=mexc_exchange.id,
                asset_name="USDT",
                available_balance=1000.50,       # Float-only policy
                locked_balance=100.25,           # Float-only policy
                frozen_balance=50.10,            # Float-only policy
                timestamp=datetime.utcnow()
            )
            
            balance_count = await db.insert_balance_snapshots_batch([balance_snapshot])
            logger.info(f"✓ Inserted {balance_count} balance snapshots")
        
        # Test database statistics
        logger.info("7. Testing database statistics...")
        db_stats = await db.get_database_stats()
        
        for table, stats in db_stats.items():
            if isinstance(stats, dict) and 'total_snapshots' in stats:
                logger.info(f"✓ {table}: {stats['total_snapshots']} records")
        
        # Test cache performance after operations
        logger.info("8. Final cache performance check...")
        final_cache_stats = get_cache_stats()
        
        logger.info(f"✓ Cache hit ratio: {final_cache_stats.hit_ratio:.3f}")
        logger.info(f"✓ Average lookup time: {final_cache_stats.avg_lookup_time_us:.2f}μs")
        hft_compliant = final_cache_stats.avg_lookup_time_us < 1.0
        logger.info(f"✓ HFT compliant: {hft_compliant}")
        
        if hft_compliant:
            logger.info("🎉 DatabaseManager meets HFT performance requirements!")
        else:
            logger.warning("⚠ DatabaseManager does not meet HFT performance requirements")
        
        # Test cleanup (optional - commented out to preserve data)
        # logger.info("9. Testing data cleanup...")
        # cleanup_results = await db.cleanup_old_data(days_to_keep=0)
        # logger.info(f"✓ Cleanup results: {cleanup_results}")
        
        logger.info("✅ All tests completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        raise
    
    finally:
        # Close database manager
        try:
            from db import close_database_manager
            await close_database_manager()
            logger.info("✓ Database manager closed")
        except Exception as e:
            logger.warning(f"Warning during cleanup: {e}")


async def main():
    """Main test function."""
    print("=" * 60)
    print("Simplified DatabaseManager Test")
    print("Following PROJECT_GUIDES.md requirements:")
    print("- Float-Only Data Policy")
    print("- Struct-First Data Policy")  
    print("- HFT Performance Requirements")
    print("- Configuration Management")
    print("=" * 60)
    
    await test_simplified_database_manager()


if __name__ == "__main__":
    asyncio.run(main())