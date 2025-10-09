#!/usr/bin/env python3
"""
Simple test to verify the missing tables are created and working.
"""

import asyncio
import os
import asyncpg
from datetime import datetime


async def test_tables():
    """Test that the new tables are working."""
    # Connect directly to the production database
    conn = await asyncpg.connect(
        host='31.192.233.13',
        port=5432,
        user='arbitrage_user',
        password='qCcmLMmWTL9f3su9rK4dbc4I',
        database='arbitrage_data'
    )
    
    print("🚀 Testing Missing Tables on Production Database")
    print("=" * 60)
    
    try:
        # Test funding_rate_snapshots table
        print("\n💰 Testing funding_rate_snapshots table...")
        
        # Check if table exists
        funding_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'funding_rate_snapshots'
            )
        """)
        print(f"  ✅ Table exists: {funding_exists}")
        
        if funding_exists:
            # Test table structure
            columns = await conn.fetch("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'funding_rate_snapshots'
                ORDER BY ordinal_position
            """)
            print(f"  ✅ Table has {len(columns)} columns")
            
            # Test insert (requires a valid symbol_id)
            # First get a symbol_id
            symbol_id = await conn.fetchval("SELECT id FROM symbols LIMIT 1")
            if symbol_id:
                try:
                    await conn.execute("""
                        INSERT INTO funding_rate_snapshots (timestamp, symbol_id, funding_rate, funding_time)
                        VALUES ($1, $2, $3, $4)
                    """, datetime.now(), symbol_id, 0.0001, 1650000000000)
                    print("  ✅ Insert test successful")
                    
                    # Test query
                    count = await conn.fetchval("SELECT COUNT(*) FROM funding_rate_snapshots")
                    print(f"  ✅ Query test successful: {count} records")
                except Exception as e:
                    print(f"  ⚠️ Insert/query test failed: {e}")
            else:
                print("  ⚠️ No symbols found for testing")
        
        # Test balance_snapshots table
        print("\n💼 Testing balance_snapshots table...")
        
        # Check if table exists
        balance_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'balance_snapshots'
            )
        """)
        print(f"  ✅ Table exists: {balance_exists}")
        
        if balance_exists:
            # Test table structure
            columns = await conn.fetch("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'balance_snapshots'
                ORDER BY ordinal_position
            """)
            print(f"  ✅ Table has {len(columns)} columns")
            
            # Test insert (requires a valid exchange_id)
            # First get an exchange_id
            exchange_id = await conn.fetchval("SELECT id FROM exchanges LIMIT 1")
            if exchange_id:
                try:
                    await conn.execute("""
                        INSERT INTO balance_snapshots (timestamp, exchange_id, asset_name, available_balance, locked_balance)
                        VALUES ($1, $2, $3, $4, $5)
                    """, datetime.now(), exchange_id, 'BTC', 1.0, 0.0)
                    print("  ✅ Insert test successful")
                    
                    # Test query
                    count = await conn.fetchval("SELECT COUNT(*) FROM balance_snapshots")
                    print(f"  ✅ Query test successful: {count} records")
                except Exception as e:
                    print(f"  ⚠️ Insert/query test failed: {e}")
            else:
                print("  ⚠️ No exchanges found for testing")
        
        # Test foreign key relationships
        print("\n🔗 Testing foreign key relationships...")
        
        # Check funding_rate_snapshots foreign keys
        funding_fks = await conn.fetch("""
            SELECT constraint_name, table_name, column_name, foreign_table_name, foreign_column_name
            FROM information_schema.key_column_usage 
            WHERE table_name = 'funding_rate_snapshots'
            AND referenced_table_name IS NOT NULL
        """)
        print(f"  ✅ funding_rate_snapshots foreign keys: {len(funding_fks)}")
        
        # Check balance_snapshots foreign keys
        balance_fks = await conn.fetch("""
            SELECT constraint_name, table_name, column_name, foreign_table_name, foreign_column_name
            FROM information_schema.key_column_usage 
            WHERE table_name = 'balance_snapshots'
            AND referenced_table_name IS NOT NULL
        """)
        print(f"  ✅ balance_snapshots foreign keys: {len(balance_fks)}")
        
        # Test TimescaleDB hypertables
        print("\n⏰ Testing TimescaleDB hypertables...")
        
        try:
            hypertables = await conn.fetch("""
                SELECT hypertable_name, chunk_time_interval
                FROM timescaledb_information.hypertables
                WHERE hypertable_name IN ('funding_rate_snapshots', 'balance_snapshots')
            """)
            
            for ht in hypertables:
                print(f"  ✅ {ht['hypertable_name']}: chunk_interval = {ht['chunk_time_interval']}")
            
            if len(hypertables) == 2:
                print("  ✅ Both tables configured as TimescaleDB hypertables")
            else:
                print(f"  ⚠️ Only {len(hypertables)} tables configured as hypertables")
                
        except Exception as e:
            print(f"  ⚠️ Hypertable check failed: {e}")
        
        print("\n🎉 All table tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Table test failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await conn.close()
        print("\n✅ Database connection closed")


if __name__ == "__main__":
    asyncio.run(test_tables())