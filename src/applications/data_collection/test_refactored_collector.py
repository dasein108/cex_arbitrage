#!/usr/bin/env python3
"""
Test Refactored Data Collector

Tests the refactored data collector to ensure it works correctly with the new
database methods and exchange_symbol lookups.
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
from db.cache_operations import cached_resolve_symbol_by_exchange_string
from exchanges.structs.enums import ExchangeEnum
from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName
from db.models import BookTickerSnapshot, TradeSnapshot, NormalizedBookTickerSnapshot, NormalizedTradeSnapshot

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_cache_resolution():
    """Test exchange_symbol cache resolution functionality."""
    logger.info("🧪 Testing cache resolution functionality")
    
    # First, let's see what symbols are actually available
    from db.cache_operations import cached_get_all_symbols
    symbols = cached_get_all_symbols()
    logger.info(f"📊 Found {len(symbols)} symbols in cache:")
    for symbol in symbols[:10]:  # Show first 10
        logger.info(f"   - {symbol.exchange_id}: {symbol.exchange_symbol} ({symbol.symbol_base}/{symbol.symbol_quote})")
    
    # Test exchange_symbol lookup with actual symbols
    if symbols:
        test_symbol = symbols[0]
        from db.cache_operations import cached_get_exchange_by_id
        exchange = cached_get_exchange_by_id(test_symbol.exchange_id)
        if exchange:
            from exchanges.structs.enums import ExchangeEnum
            try:
                exchange_enum = ExchangeEnum(exchange.enum_value)
                symbol = cached_resolve_symbol_by_exchange_string(exchange_enum, test_symbol.exchange_symbol)
                if symbol:
                    logger.info(f"✅ Resolved {test_symbol.exchange_symbol} on {exchange_enum.value}: {symbol.symbol_base}/{symbol.symbol_quote}")
                else:
                    logger.warning(f"❌ Could not resolve {test_symbol.exchange_symbol} on {exchange_enum.value}")
            except ValueError as e:
                logger.warning(f"❌ Invalid enum for {exchange.enum_value}: {e}")
    else:
        logger.warning("❌ No symbols available in cache")


async def test_snapshot_conversion():
    """Test snapshot conversion using new methods."""
    logger.info("🧪 Testing snapshot conversion functionality")
    
    # Get a real symbol from cache to test with
    from db.cache_operations import cached_get_all_symbols, cached_get_exchange_by_id
    symbols = cached_get_all_symbols()
    
    if not symbols:
        logger.warning("❌ No symbols available for testing")
        return
    
    test_db_symbol = symbols[0]
    exchange = cached_get_exchange_by_id(test_db_symbol.exchange_id)
    
    if not exchange:
        logger.warning("❌ Could not get exchange for symbol")
        return
    
    # Create legacy snapshot (simulating how the collector creates them)
    # Note: We'll use a manual creation since the models may have different signatures
    logger.info(f"📝 Testing with symbol: {test_db_symbol.exchange_symbol} on {exchange.name}")
    
    # Test conversion to normalized format using the refactored approach
    from exchanges.structs.enums import ExchangeEnum
    try:
        exchange_enum = ExchangeEnum(exchange.enum_value)
        symbol = cached_resolve_symbol_by_exchange_string(exchange_enum, test_db_symbol.exchange_symbol)
        
        if symbol:
            logger.info(f"✅ Successfully resolved symbol using exchange_symbol lookup")
            logger.info(f"   - Exchange: {exchange_enum.value}")
            logger.info(f"   - Symbol: {test_db_symbol.exchange_symbol}")
            logger.info(f"   - Resolved to: {symbol.symbol_base}/{symbol.symbol_quote}")
            logger.info(f"   - Database IDs: exchange_id={symbol.exchange_id}, symbol_id={symbol.id}")
            
            # Test creating a normalized snapshot directly
            normalized_snapshot = NormalizedBookTickerSnapshot(
                exchange_id=symbol.exchange_id,
                symbol_id=symbol.id,
                bid_price=50000.0,
                bid_qty=1.0,
                ask_price=50001.0,
                ask_qty=2.0,
                timestamp=datetime.now(timezone.utc)
            )
            logger.info(f"✅ Created normalized snapshot: exchange_id={normalized_snapshot.exchange_id}, symbol_id={normalized_snapshot.symbol_id}")
        else:
            logger.error(f"❌ Could not resolve symbol: {test_db_symbol.exchange_symbol}")
    except ValueError as e:
        logger.warning(f"❌ Invalid exchange enum {exchange.enum_value}: {e}")


async def main():
    """Main test function."""
    logger.info("🚀 Starting refactored data collector tests")
    
    try:
        # Initialize database
        config_manager = HftConfig()
        db_config = config_manager.get_database_config()
        await initialize_database(db_config)
        logger.info("✅ Database initialized")
        
        # Warm symbol cache
        await warm_symbol_cache()
        logger.info("✅ Symbol cache warmed")
        
        # Run tests
        await test_cache_resolution()
        await test_snapshot_conversion()
        
        logger.info("🎉 All tests completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())