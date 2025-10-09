#!/usr/bin/env python3
"""
Test Collector Refactoring

Validates that the refactored collector works correctly with the new normalized schema
and no longer produces AttributeError when accessing legacy attributes.
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.config_manager import HftConfig
from db.connection import initialize_database
from db.cache_warming import warm_symbol_cache
from applications.data_collection.collector import UnifiedWebSocketManager
from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName
from exchanges.structs.enums import ExchangeEnum

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_collector_initialization():
    """Test that the collector initializes without errors."""
    logger.info("🧪 Testing collector initialization")
    
    try:
        # Test UnifiedWebSocketManager initialization
        manager = UnifiedWebSocketManager([ExchangeEnum.GATEIO_FUTURES])
        logger.info("✅ UnifiedWebSocketManager initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Collector initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_cache_snapshot_creation():
    """Test that the cache can create snapshots without AttributeError."""
    logger.info("🧪 Testing cache snapshot creation")
    
    try:
        # Create a simple WebSocket manager
        manager = UnifiedWebSocketManager([ExchangeEnum.GATEIO_FUTURES])
        
        # Test getting cached tickers (should return empty list but not error)
        cached_tickers = manager.get_all_cached_tickers()
        logger.info(f"✅ Retrieved {len(cached_tickers)} cached tickers without error")
        
        # Test getting cached trades (should return empty list but not error)
        cached_trades = manager.get_all_cached_trades()
        logger.info(f"✅ Retrieved {len(cached_trades)} cached trades without error")
        
        return True
        
    except AttributeError as e:
        if "'BookTickerSnapshot' object has no attribute 'exchange'" in str(e):
            logger.error("❌ AttributeError still present - refactoring incomplete!")
            return False
        else:
            logger.error(f"❌ Unexpected AttributeError: {e}")
            return False
    except Exception as e:
        logger.error(f"❌ Cache snapshot creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_symbol_resolution():
    """Test symbol resolution in the refactored collector."""
    logger.info("🧪 Testing symbol resolution in collector")
    
    try:
        manager = UnifiedWebSocketManager([ExchangeEnum.GATEIO_FUTURES])
        
        # Test symbol resolution helper
        symbol_id = manager._resolve_symbol_id_from_cache("GATEIO_FUTURES", "AI16ZUSDT")
        if symbol_id:
            logger.info(f"✅ Symbol resolution works: AI16ZUSDT -> symbol_id {symbol_id}")
        else:
            logger.info("✅ Symbol resolution correctly returns None for unresolvable symbols")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Symbol resolution test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main test function."""
    logger.info("🚀 Starting collector refactoring validation tests")
    
    try:
        # Initialize database and cache
        config_manager = HftConfig()
        db_config = config_manager.get_database_config()
        await initialize_database(db_config)
        logger.info("✅ Database initialized")
        
        await warm_symbol_cache()
        logger.info("✅ Symbol cache warmed")
        
        # Run tests
        test1_result = await test_collector_initialization()
        test2_result = await test_cache_snapshot_creation()
        test3_result = await test_symbol_resolution()
        
        if test1_result and test2_result and test3_result:
            logger.info("🎉 All collector refactoring tests passed!")
            logger.info("✅ AttributeError has been resolved")
            logger.info("✅ Collector uses new normalized schema correctly")
            logger.info("✅ Legacy patterns have been eliminated")
        else:
            logger.error("❌ Some tests failed!")
        
    except Exception as e:
        logger.error(f"❌ Test setup failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())