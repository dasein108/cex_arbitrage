#!/usr/bin/env python3
"""
Test BookTickerSnapshot.from_symbol_and_data Fix

Tests the fixed BookTickerSnapshot.from_symbol_and_data method to ensure
it correctly resolves symbols using exchange_symbol lookups.
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
from db.models import BookTickerSnapshot
from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_bookticker_from_symbol_and_data():
    """Test BookTickerSnapshot.from_symbol_and_data method."""
    logger.info("🧪 Testing BookTickerSnapshot.from_symbol_and_data method")
    
    try:
        # Test with a symbol that should exist in cache
        test_symbol = Symbol(base=AssetName("AI16Z"), quote=AssetName("USDT"))
        
        # Create BookTickerSnapshot using the fixed from_symbol_and_data method
        snapshot = BookTickerSnapshot.from_symbol_and_data(
            exchange="GATEIO_FUTURES",
            symbol=test_symbol,
            bid_price=1.234,
            bid_qty=100.0,
            ask_price=1.235,
            ask_qty=200.0,
            timestamp=datetime.now(timezone.utc)
        )
        
        logger.info(f"✅ Successfully created BookTickerSnapshot with symbol_id: {snapshot.symbol_id}")
        logger.info(f"   - Bid: {snapshot.bid_price} x {snapshot.bid_qty}")
        logger.info(f"   - Ask: {snapshot.ask_price} x {snapshot.ask_qty}")
        logger.info(f"   - Spread: {snapshot.get_spread():.6f}")
        logger.info(f"   - Mid price: {snapshot.get_mid_price():.6f}")
        
        # Test the to_symbol method
        reconstructed_symbol = snapshot.to_symbol()
        logger.info(f"✅ Reconstructed symbol: {reconstructed_symbol.base}/{reconstructed_symbol.quote}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_invalid_symbol():
    """Test BookTickerSnapshot.from_symbol_and_data with invalid symbol."""
    logger.info("🧪 Testing BookTickerSnapshot.from_symbol_and_data with invalid symbol")
    
    try:
        # Test with a symbol that should NOT exist
        test_symbol = Symbol(base=AssetName("INVALID"), quote=AssetName("TOKEN"))
        
        snapshot = BookTickerSnapshot.from_symbol_and_data(
            exchange="GATEIO_FUTURES",
            symbol=test_symbol,
            bid_price=1.0,
            bid_qty=1.0,
            ask_price=1.01,
            ask_qty=1.0,
            timestamp=datetime.now(timezone.utc)
        )
        
        logger.error("❌ Should have failed with invalid symbol, but didn't!")
        return False
        
    except ValueError as e:
        logger.info(f"✅ Correctly rejected invalid symbol: {e}")
        return True
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return False


async def main():
    """Main test function."""
    logger.info("🚀 Starting BookTickerSnapshot fix tests")
    
    try:
        # Initialize database and cache
        config_manager = HftConfig()
        db_config = config_manager.get_database_config()
        await initialize_database(db_config)
        logger.info("✅ Database initialized")
        
        await warm_symbol_cache()
        logger.info("✅ Symbol cache warmed")
        
        # Run tests
        test1_result = await test_bookticker_from_symbol_and_data()
        test2_result = await test_invalid_symbol()
        
        if test1_result and test2_result:
            logger.info("🎉 All BookTickerSnapshot tests passed!")
        else:
            logger.error("❌ Some tests failed!")
        
    except Exception as e:
        logger.error(f"❌ Test setup failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())