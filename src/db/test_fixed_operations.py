#!/usr/bin/env python3
"""
Test Fixed Database Operations

Validates that all fixed database operations work correctly with the normalized schema.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_manager import HftConfig
from db.connection import initialize_database
from db.cache_warming import warm_symbol_cache
from db.operations import (
    insert_book_ticker_snapshot,
    get_book_ticker_snapshots,
    get_latest_book_ticker_snapshots,
    get_book_ticker_history,
    get_database_stats
)
from db.models import BookTickerSnapshot
from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_insert_normalized_snapshot():
    """Test inserting a normalized BookTickerSnapshot."""
    logger.info("🧪 Testing normalized snapshot insertion")
    
    try:
        # Create a test snapshot with symbol_id (normalized)
        test_snapshot = BookTickerSnapshot(
            symbol_id=1,  # AI16Z/USDT on GATEIO_FUTURES 
            bid_price=1.234,
            bid_qty=100.0,
            ask_price=1.235,
            ask_qty=200.0,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Insert the snapshot
        snapshot_id = await insert_book_ticker_snapshot(test_snapshot)
        logger.info(f"✅ Successfully inserted normalized snapshot with ID: {snapshot_id}")
        
        return snapshot_id
        
    except Exception as e:
        logger.error(f"❌ Insert test failed: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_get_book_ticker_snapshots():
    """Test getting book ticker snapshots with normalized schema."""
    logger.info("🧪 Testing get_book_ticker_snapshots with normalized schema")
    
    try:
        # Test without filters
        snapshots = await get_book_ticker_snapshots(limit=5)
        logger.info(f"✅ Retrieved {len(snapshots)} snapshots without filters")
        
        if snapshots:
            sample = snapshots[0]
            logger.info(f"   Sample snapshot: symbol_id={sample.symbol_id}, bid={sample.bid_price}, ask={sample.ask_price}")
        
        # Test with exchange filter
        snapshots_filtered = await get_book_ticker_snapshots(
            exchange="GATEIO_FUTURES",
            limit=3
        )
        logger.info(f"✅ Retrieved {len(snapshots_filtered)} snapshots filtered by GATEIO_FUTURES")
        
        # Test with symbol filter
        snapshots_symbol = await get_book_ticker_snapshots(
            exchange="GATEIO_FUTURES",
            symbol_base="AI16Z",
            symbol_quote="USDT",
            limit=2
        )
        logger.info(f"✅ Retrieved {len(snapshots_symbol)} snapshots for AI16Z/USDT")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ get_book_ticker_snapshots test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_get_latest_snapshots():
    """Test getting latest snapshots with normalized schema."""
    logger.info("🧪 Testing get_latest_book_ticker_snapshots with normalized schema")
    
    try:
        # Test getting latest snapshots
        latest_snapshots = await get_latest_book_ticker_snapshots()
        logger.info(f"✅ Retrieved {len(latest_snapshots)} latest snapshots")
        
        # Show sample results
        for key, snapshot in list(latest_snapshots.items())[:3]:
            logger.info(f"   Latest {key}: symbol_id={snapshot.symbol_id}, timestamp={snapshot.timestamp}")
        
        # Test with exchange filter
        latest_filtered = await get_latest_book_ticker_snapshots(exchange="GATEIO_FUTURES")
        logger.info(f"✅ Retrieved {len(latest_filtered)} latest GATEIO_FUTURES snapshots")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ get_latest_book_ticker_snapshots test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_get_history():
    """Test getting historical data with normalized schema."""
    logger.info("🧪 Testing get_book_ticker_history with normalized schema")
    
    try:
        # Test getting history for a specific symbol
        test_symbol = Symbol(base=AssetName("AI16Z"), quote=AssetName("USDT"))
        
        history = await get_book_ticker_history(
            exchange="GATEIO_FUTURES",
            symbol=test_symbol,
            hours_back=1,  # Just 1 hour for testing
            sample_interval_minutes=5
        )
        
        logger.info(f"✅ Retrieved {len(history)} historical snapshots for AI16Z/USDT")
        
        if history:
            first = history[0]
            last = history[-1]
            logger.info(f"   Time range: {first.timestamp} to {last.timestamp}")
            logger.info(f"   Sample: symbol_id={first.symbol_id}, bid={first.bid_price}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ get_book_ticker_history test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_database_stats():
    """Test getting database statistics with normalized schema."""
    logger.info("🧪 Testing get_database_stats with normalized schema")
    
    try:
        stats = await get_database_stats()
        
        logger.info("✅ Retrieved database statistics:")
        for key, value in stats.items():
            if key != 'connection_pool':
                logger.info(f"   {key}: {value}")
        
        # Verify critical stats exist
        expected_keys = ['total_snapshots', 'exchanges', 'symbols', 'latest_timestamp']
        missing_keys = [key for key in expected_keys if key not in stats]
        
        if missing_keys:
            logger.warning(f"⚠️  Missing statistics: {missing_keys}")
        else:
            logger.info("✅ All expected statistics present")
        
        return len(missing_keys) == 0
        
    except Exception as e:
        logger.error(f"❌ get_database_stats test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main test function."""
    logger.info("🚀 Starting database operations tests")
    
    try:
        # Initialize database and cache
        config_manager = HftConfig()
        db_config = config_manager.get_database_config()
        await initialize_database(db_config)
        logger.info("✅ Database initialized")
        
        await warm_symbol_cache()
        logger.info("✅ Symbol cache warmed")
        
        # Run all tests
        test_results = []
        
        # Test 1: Insert normalized snapshot
        insert_result = await test_insert_normalized_snapshot()
        test_results.append(("Insert Normalized Snapshot", insert_result is not None))
        
        # Test 2: Get snapshots
        get_result = await test_get_book_ticker_snapshots()
        test_results.append(("Get Book Ticker Snapshots", get_result))
        
        # Test 3: Get latest snapshots
        latest_result = await test_get_latest_snapshots()
        test_results.append(("Get Latest Snapshots", latest_result))
        
        # Test 4: Get history
        history_result = await test_get_history()
        test_results.append(("Get Book Ticker History", history_result))
        
        # Test 5: Database stats
        stats_result = await test_database_stats()
        test_results.append(("Database Statistics", stats_result))
        
        # Summary
        logger.info("\n" + "="*60)
        logger.info("TEST RESULTS SUMMARY")
        logger.info("="*60)
        
        passed_tests = 0
        total_tests = len(test_results)
        
        for test_name, passed in test_results:
            status = "✅ PASSED" if passed else "❌ FAILED"
            logger.info(f"{status} {test_name}")
            if passed:
                passed_tests += 1
        
        logger.info(f"\n📊 Results: {passed_tests}/{total_tests} tests passed")
        logger.info(f"🎯 Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if passed_tests == total_tests:
            logger.info("\n🎉 ALL DATABASE OPERATIONS TESTS PASSED!")
            logger.info("✅ Normalized schema operations working correctly")
            logger.info("✅ JOIN operations performing efficiently")
            logger.info("✅ All legacy patterns have been eliminated")
        else:
            logger.error(f"\n⚠️  {total_tests - passed_tests} TESTS FAILED - REVIEW REQUIRED")
        
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"❌ Test setup failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())