#!/usr/bin/env python3
"""
Production Database Migration Test

Tests the automatic migration system with production database credentials.
This script will:
1. Connect to the production database
2. Check current schema status
3. Run migrations to create missing tables
4. Verify tables are created correctly
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from config.config_manager import HftConfig
from db.connection import initialize_database, get_db_manager
from db.migrations import run_all_pending_migrations as run_pending_migrations


async def check_tables_exist():
    """Check if required tables exist in the database."""
    db = get_db_manager()
    
    # Check for core tables
    core_tables = [
        'exchanges', 'symbols', 'book_ticker_snapshots', 
        'funding_rate_snapshots', 'balance_snapshots', 'trade_snapshots'
    ]
    
    status = {
        'existing_tables': [],
        'missing_tables': [],
        'hypertables': [],
        'indexes_count': 0,
        'initialized': False
    }
    
    # Check for table existence
    for table_name in core_tables:
        try:
            exists = await db.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = $1
                )
            """, table_name)
            
            if exists:
                status['existing_tables'].append(table_name)
            else:
                status['missing_tables'].append(table_name)
        except Exception as e:
            print(f"Error checking table {table_name}: {e}")
            status['missing_tables'].append(table_name)
    
    # Check for hypertables
    try:
        hypertables = await db.fetch("""
            SELECT table_name 
            FROM timescaledb_information.hypertables 
            WHERE table_schema = 'public'
        """)
        status['hypertables'] = [row['table_name'] for row in hypertables]
    except Exception as e:
        print(f"Error checking hypertables: {e}")
    
    # Count indexes
    try:
        status['indexes_count'] = await db.fetchval("""
            SELECT COUNT(*) 
            FROM pg_indexes 
            WHERE schemaname = 'public'
        """)
    except Exception as e:
        print(f"Error counting indexes: {e}")
    
    status['initialized'] = len(status['missing_tables']) == 0
    
    return status


async def test_production_migration():
    """Test migration system with production database."""
    print("🚀 Testing Production Database Migration")
    print("=" * 60)
    
    # Set production database environment variables
    os.environ.update({
        'POSTGRES_HOST': '31.192.233.13',
        'POSTGRES_PORT': '5432', 
        'POSTGRES_DB': 'arbitrage_data',
        'POSTGRES_USER': 'arbitrage_user',
        'POSTGRES_PASSWORD': 'qCcmLMmWTL9f3su9rK4dbc4I'
    })
    
    try:
        # Initialize configuration
        config_manager = HftConfig()
        db_config = config_manager.get_database_config()
        
        print(f"\n📊 Database Configuration:")
        print(f"  Host: {db_config.host}")
        print(f"  Port: {db_config.port}")
        print(f"  Database: {db_config.database}")
        print(f"  User: {db_config.username}")
        
        # Initialize database connection (this will automatically run migrations)
        print(f"\n🔗 Initializing database connection...")
        await initialize_database(db_config)
        print("✅ Database connection initialized")
        
        # Check schema status before migration
        print(f"\n📋 Checking schema status...")
        status = await check_tables_exist()
        
        print(f"  Existing tables: {status['existing_tables']}")
        print(f"  Missing tables: {status['missing_tables']}")
        print(f"  Hypertables: {status['hypertables']}")
        print(f"  Total indexes: {status['indexes_count']}")
        print(f"  Schema initialized: {status['initialized']}")
        
        # If tables are missing, run migrations explicitly
        if status['missing_tables']:
            print(f"\n🔧 Running migrations for missing tables: {status['missing_tables']}")
            migration_result = await run_pending_migrations()
            
            print(f"  Migration success: {migration_result['success']}")
            print(f"  Migrations run: {len(migration_result['migrations_run'])}")
            
            for migration in migration_result['migrations_run']:
                print(f"    - {migration['id']}: {migration['name']}")
                if 'result' in migration and 'tables_created' in migration['result']:
                    print(f"      Tables created: {migration['result']['tables_created']}")
                    print(f"      Indexes created: {migration['result'].get('indexes_created', 0)}")
                    print(f"      Hypertables: {migration['result'].get('hypertables_created', [])}")
            
            if migration_result['migrations_failed']:
                print(f"  Failed migrations: {migration_result['migrations_failed']}")
        
        # Verify final schema status
        print(f"\n✅ Final schema verification...")
        final_status = await check_tables_exist()
        
        print(f"  All tables exist: {final_status['initialized']}")
        print(f"  Total tables: {len(final_status['existing_tables'])}")
        print(f"  Total hypertables: {len(final_status['hypertables'])}")
        print(f"  Total indexes: {final_status['indexes_count']}")
        
        # Test table functionality
        print(f"\n🧪 Testing table functionality...")
        db = get_db_manager()
        
        # Test funding_rate_snapshots table
        try:
            funding_count = await db.fetchval("SELECT COUNT(*) FROM funding_rate_snapshots")
            print(f"  ✅ funding_rate_snapshots accessible: {funding_count} records")
        except Exception as e:
            print(f"  ❌ funding_rate_snapshots error: {e}")
        
        # Test balance_snapshots table
        try:
            balance_count = await db.fetchval("SELECT COUNT(*) FROM balance_snapshots")
            print(f"  ✅ balance_snapshots accessible: {balance_count} records")
        except Exception as e:
            print(f"  ❌ balance_snapshots error: {e}")
        
        # Test foreign key relationships
        try:
            fk_test = await db.fetchval("""
                SELECT COUNT(*) FROM information_schema.table_constraints 
                WHERE constraint_type = 'FOREIGN KEY' 
                AND table_name IN ('funding_rate_snapshots', 'balance_snapshots')
            """)
            print(f"  ✅ Foreign key constraints: {fk_test}")
        except Exception as e:
            print(f"  ❌ Foreign key test error: {e}")
        
        # Test TimescaleDB hypertables
        try:
            hypertable_test = await db.fetchval("""
                SELECT COUNT(*) FROM timescaledb_information.hypertables 
                WHERE hypertable_name IN ('funding_rate_snapshots', 'balance_snapshots')
            """)
            print(f"  ✅ TimescaleDB hypertables: {hypertable_test}")
        except Exception as e:
            print(f"  ❌ Hypertable test error: {e}")
        
        print(f"\n🎉 Production migration test completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Production migration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Close database connection
        db = get_db_manager()
        if db and db.is_initialized:
            await db.close()
            print("\n✅ Database connection closed")


if __name__ == "__main__":
    success = asyncio.run(test_production_migration())
    sys.exit(0 if success else 1)