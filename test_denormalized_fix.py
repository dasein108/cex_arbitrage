#!/usr/bin/env python3
"""
Test script to verify denormalized database schema fixes.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from db.database_manager import get_database_manager

async def test_denormalized_queries():
    """Test that the denormalized database queries work correctly."""
    
    print("Testing denormalized database queries...")
    
    # Initialize database manager
    db_manager = get_database_manager()
    await db_manager.initialize()
    
    try:
        # Test 1: Basic get_book_ticker_dataframe query
        print("\n1. Testing get_book_ticker_dataframe with exchange filter...")
        df = await db_manager.get_book_ticker_dataframe(
            exchange="GATEIO_FUTURES", 
            symbol_base="NEIROETH",
            symbol_quote="USDT",
            limit=10
        )
        print(f"   Result: Retrieved {len(df)} rows")
        if len(df) > 0:
            print(f"   Columns: {list(df.columns)}")
            print(f"   Sample data:")
            print(df.head())
        
        # Test 2: get_latest_book_ticker_snapshots
        print("\n2. Testing get_latest_book_ticker_snapshots...")
        snapshots = await db_manager.get_latest_book_ticker_snapshots(
            exchange="GATEIO_FUTURES",
            symbol_base="NEIROETH", 
            symbol_quote="USDT",
            limit=5
        )
        print(f"   Result: Retrieved {len(snapshots)} snapshots")
        if snapshots:
            snapshot = snapshots[0]
            print(f"   Sample: symbol_id={snapshot.symbol_id}, bid={snapshot.bid_price}, ask={snapshot.ask_price}")
        
        # Test 3: Basic DataFrame without filters
        print("\n3. Testing get_book_ticker_dataframe without filters...")
        df_all = await db_manager.get_book_ticker_dataframe(limit=5)
        print(f"   Result: Retrieved {len(df_all)} rows")
        if len(df_all) > 0:
            print(f"   Exchanges found: {df_all['exchange'].unique()}")
        
        print("\n✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        await db_manager.close()
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_denormalized_queries())
    sys.exit(0 if success else 1)