# Database Development Guide

## Overview

This guide covers the complete database development workflow for the CEX Arbitrage Engine, including current schema structure, adding new entities, applying changes to production, and maintaining integration tests.

## Table of Contents

1. [Current Database Structure](#current-database-structure)
2. [Adding New Database Entities](#adding-new-database-entities)
3. [Production Deployment Workflow](#production-deployment-workflow)
4. [Testing and Validation](#testing-and-validation)
5. [Migration System](#migration-system)
6. [Best Practices](#best-practices)
7. [Troubleshooting](#troubleshooting)

## Current Database Structure

### Core Normalized Schema

The database uses a **normalized schema** with proper foreign key relationships optimized for HFT performance:

```sql
-- Foundation Tables
exchanges (id, enum_value, exchange_name, market_type)
symbols (id, exchange_id FK, symbol_base, symbol_quote, exchange_symbol)

-- Time-Series Data Tables (TimescaleDB Hypertables)
book_ticker_snapshots (timestamp, symbol_id FK, bid_price, ask_price, ...)
funding_rate_snapshots (timestamp, symbol_id FK, funding_rate, funding_time, ...)
balance_snapshots (timestamp, exchange_id FK, asset_name, available_balance, ...)
trade_snapshots (timestamp, symbol_id FK, price, quantity, side, ...)

-- Analytics Tables
arbitrage_opportunities (timestamp, symbol_id FK, buy_exchange_id FK, sell_exchange_id FK, ...)
order_flow_metrics (timestamp, symbol_id FK, ofi_score, microprice, ...)
collector_status (timestamp, exchange_id FK, status, messages_per_second, ...)
```

### Key Relationships

1. **Exchanges → Symbols**: One-to-many relationship
   ```sql
   symbols.exchange_id → exchanges.id
   ```

2. **Symbols → Time-Series Data**: One-to-many relationships
   ```sql
   book_ticker_snapshots.symbol_id → symbols.id
   funding_rate_snapshots.symbol_id → symbols.id
   trade_snapshots.symbol_id → symbols.id
   ```

3. **Exchanges → Balance Data**: One-to-many relationship
   ```sql
   balance_snapshots.exchange_id → exchanges.id
   ```

### Exchange Enum Standards

Exchanges must follow the naming convention:
- **Format**: `{EXCHANGE_NAME}_{MARKET_TYPE}`
- **Examples**: `MEXC_SPOT`, `GATEIO_SPOT`, `GATEIO_FUTURES`
- **Validation**: Enforced by `chk_enum_format` constraint

### TimescaleDB Optimization

All time-series tables are configured as TimescaleDB hypertables:
- **book_ticker_snapshots**: 30-minute chunks (high frequency)
- **funding_rate_snapshots**: 1-hour chunks (moderate frequency)
- **balance_snapshots**: 6-hour chunks (low frequency)
- **trade_snapshots**: 30-minute chunks (high frequency)

## Adding New Database Entities

### Step 1: Design the Entity

Before creating a new table, consider:

1. **Normalization**: Should it reference existing entities (exchanges/symbols)?
2. **Time-Series**: Is it time-based data that needs TimescaleDB optimization?
3. **HFT Requirements**: Will it need sub-millisecond query performance?
4. **Foreign Keys**: What relationships are needed?

### Step 2: Create Migration Script

Create a new migration in `src/db/migrations/`:

```python
# src/db/migrations/002_add_new_entity.py
"""
Migration 002: Add new entity table

Description of what this migration does and why.
"""

import logging
from typing import Dict, Any
import asyncpg

from db.connection import get_db_manager

logger = logging.getLogger(__name__)

MIGRATION_ID = "002"
MIGRATION_NAME = "add_new_entity"


async def migrate_up() -> Dict[str, Any]:
    """Apply migration: Create new entity table."""
    db = get_db_manager()
    
    result = {
        'success': False,
        'tables_created': [],
        'indexes_created': 0,
        'hypertables_created': [],
        'errors': []
    }
    
    try:
        # Create the new table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS new_entity (
                id BIGSERIAL,
                timestamp TIMESTAMPTZ NOT NULL,
                symbol_id INTEGER NOT NULL REFERENCES symbols(id),
                
                -- Entity-specific fields
                field1 NUMERIC(20,8) NOT NULL,
                field2 VARCHAR(50) NOT NULL,
                
                -- Metadata
                created_at TIMESTAMPTZ DEFAULT NOW(),
                
                -- Constraints
                CONSTRAINT chk_positive_field1 CHECK (field1 > 0),
                CONSTRAINT chk_valid_field2 CHECK (field2 ~ '^[A-Z0-9]+$'),
                
                -- Primary key for time-series partitioning
                PRIMARY KEY (timestamp, symbol_id)
            );
        """)
        result['tables_created'].append('new_entity')
        
        # Create TimescaleDB hypertable if time-series
        await db.execute("""
            SELECT create_hypertable('new_entity', 'timestamp', 
                chunk_time_interval => INTERVAL '1 hour',
                if_not_exists => TRUE);
        """)
        result['hypertables_created'].append('new_entity')
        
        # Create indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_new_entity_symbol_time ON new_entity(symbol_id, timestamp DESC);",
            "CREATE INDEX IF NOT EXISTS idx_new_entity_field1 ON new_entity(field1) WHERE field1 > 100;"
        ]
        
        for index_sql in indexes:
            await db.execute(index_sql)
            result['indexes_created'] += 1
        
        # Add retention policy
        await db.execute("""
            SELECT add_retention_policy('new_entity', INTERVAL '7 days', if_not_exists => TRUE);
        """)
        
        result['success'] = True
        logger.info(f"Migration {MIGRATION_ID} completed successfully")
        
    except Exception as e:
        error_msg = f"Migration {MIGRATION_ID} failed: {e}"
        logger.error(error_msg)
        result['errors'].append(error_msg)
        raise
    
    return result


async def migrate_down() -> Dict[str, Any]:
    """Rollback migration: Drop the new entity table."""
    db = get_db_manager()
    
    try:
        await db.execute("DROP TABLE IF EXISTS new_entity CASCADE")
        logger.info(f"Migration {MIGRATION_ID} rollback completed")
        return {'success': True, 'tables_dropped': ['new_entity']}
    except Exception as e:
        logger.error(f"Migration {MIGRATION_ID} rollback failed: {e}")
        raise


async def get_migration_info() -> Dict[str, Any]:
    """Get information about this migration."""
    return {
        'id': MIGRATION_ID,
        'name': MIGRATION_NAME,
        'description': 'Add new entity table with TimescaleDB optimization',
        'tables_created': ['new_entity'],
        'dependencies': ['exchanges', 'symbols'],
        'version': '1.0.0'
    }
```

### Step 3: Update Schema Documentation

Add the new table to `docker/init-db.sql`:

```sql
-- New Entity table - NORMALIZED SCHEMA
CREATE TABLE IF NOT EXISTS new_entity (
    id BIGSERIAL,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    
    -- Entity-specific fields
    field1 NUMERIC(20,8) NOT NULL,
    field2 VARCHAR(50) NOT NULL,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT chk_positive_field1 CHECK (field1 > 0),
    CONSTRAINT chk_valid_field2 CHECK (field2 ~ '^[A-Z0-9]+$'),
    
    -- Primary key for time-series partitioning
    PRIMARY KEY (timestamp, symbol_id)
);

-- Convert to TimescaleDB hypertable
SELECT create_hypertable('new_entity', 'timestamp', 
    chunk_time_interval => INTERVAL '1 hour',
    if_not_exists => TRUE);

-- HFT-optimized indexes
CREATE INDEX IF NOT EXISTS idx_new_entity_symbol_time 
    ON new_entity(symbol_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_new_entity_field1 
    ON new_entity(field1) WHERE field1 > 100;

-- Retention policy
SELECT add_retention_policy('new_entity', INTERVAL '7 days', if_not_exists => TRUE);

-- Table ownership
ALTER TABLE new_entity OWNER TO arbitrage_user;

-- Table comment
COMMENT ON TABLE new_entity IS 'Description of the new entity and its purpose';
```

### Step 4: Create Data Models

Add the entity model to `src/db/models.py`:

```python
@struct
class NewEntity:
    """New entity data structure for HFT operations."""
    symbol_id: int
    field1: float
    field2: str
    timestamp: datetime
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    
    def validate(self) -> None:
        """Validate entity data for HFT compliance."""
        if self.field1 <= 0:
            raise ValueError(f"field1 must be positive, got: {self.field1}")
        if not re.match(r'^[A-Z0-9]+$', self.field2):
            raise ValueError(f"field2 must be alphanumeric uppercase, got: {self.field2}")
```

### Step 5: Create Database Operations

Add operations to `src/db/operations.py`:

```python
async def insert_new_entity(entity: NewEntity) -> int:
    """Insert a single new entity record."""
    db = get_db_manager()
    
    query = """
        INSERT INTO new_entity (timestamp, symbol_id, field1, field2)
        VALUES ($1, $2, $3, $4)
        RETURNING id
    """
    
    return await db.fetchval(
        query,
        entity.timestamp,
        entity.symbol_id,
        entity.field1,
        entity.field2
    )


async def insert_new_entity_batch(entities: List[NewEntity]) -> int:
    """Insert multiple new entity records efficiently."""
    if not entities:
        return 0
    
    db = get_db_manager()
    
    # Validate all entities
    for entity in entities:
        entity.validate()
    
    # Prepare data for COPY operation
    records = [
        (e.timestamp, e.symbol_id, e.field1, e.field2)
        for e in entities
    ]
    
    columns = ['timestamp', 'symbol_id', 'field1', 'field2']
    
    return await db.copy_records_to_table('new_entity', records, columns)


async def get_latest_new_entity_by_symbol(symbol_id: int) -> Optional[NewEntity]:
    """Get the latest new entity record for a symbol."""
    db = get_db_manager()
    
    query = """
        SELECT id, timestamp, symbol_id, field1, field2, created_at
        FROM new_entity
        WHERE symbol_id = $1
        ORDER BY timestamp DESC
        LIMIT 1
    """
    
    row = await db.fetchrow(query, symbol_id)
    if not row:
        return None
    
    return NewEntity(
        id=row['id'],
        timestamp=row['timestamp'],
        symbol_id=row['symbol_id'],
        field1=float(row['field1']),
        field2=row['field2'],
        created_at=row['created_at']
    )


async def get_new_entity_stats() -> Dict[str, Any]:
    """Get statistics for new entity table."""
    db = get_db_manager()
    
    stats_query = """
        SELECT 
            COUNT(*) as total_records,
            COUNT(DISTINCT symbol_id) as unique_symbols,
            MIN(timestamp) as earliest_record,
            MAX(timestamp) as latest_record,
            AVG(field1) as avg_field1
        FROM new_entity
    """
    
    row = await db.fetchrow(stats_query)
    
    return {
        'total_records': row['total_records'],
        'unique_symbols': row['unique_symbols'],
        'earliest_record': row['earliest_record'],
        'latest_record': row['latest_record'],
        'avg_field1': float(row['avg_field1']) if row['avg_field1'] else 0.0
    }
```

### Step 6: Update Integration Tests

Add tests to `src/examples/demo/db_operations_demo.py`:

```python
async def demo_new_entity_operations(symbol_id: int):
    """Demo new entity operations."""
    print("\n🆕 Testing new entity operations...")
    
    # Create mock new entity data
    now = datetime.now()
    new_entities = [
        NewEntity(
            symbol_id=symbol_id,
            field1=100.5 + i * 10,
            field2=f"TEST{i:02d}",
            timestamp=now - timedelta(minutes=i)
        )
        for i in range(3)
    ]
    
    try:
        # Test batch insert
        count = await insert_new_entity_batch(new_entities)
        print(f"✅ Inserted {count} new entity records")
        
        # Test latest record retrieval
        latest = await get_latest_new_entity_by_symbol(symbol_id)
        if latest:
            print(f"✅ Retrieved latest record: field1={latest.field1}, field2={latest.field2}")
        
        # Test statistics
        stats = await get_new_entity_stats()
        print(f"✅ New entity stats: {stats['total_records']} total records")
        
    except Exception as e:
        print(f"⚠️ New entity operations failed: {e}")
```

And add it to the main demo function:

```python
async def main():
    """Main demo function."""
    # ... existing code ...
    
    # Add new entity demo
    await demo_new_entity_operations(test_symbol.id)
    
    # ... rest of function ...
```

## Production Deployment Workflow

### Method 1: Automatic Migration (Recommended)

The system automatically applies migrations when connecting to the database:

```bash
# Set production database environment
export POSTGRES_HOST=31.192.233.13
export POSTGRES_PORT=5432
export POSTGRES_DB=arbitrage_data
export POSTGRES_USER=arbitrage_user
export POSTGRES_PASSWORD=qCcmLMmWTL9f3su9rK4dbc4I

# Run any application that connects to the database
python src/examples/demo/db_operations_demo.py
```

The migration system will:
1. Detect missing tables
2. Apply pending migrations automatically
3. Log all changes
4. Validate schema integrity

### Method 2: Manual Migration

For critical production changes, run migrations manually:

```python
# test_migration.py
import asyncio
from config.config_manager import HftConfig
from db.connection import initialize_database
from db.migrations import run_migration

async def apply_migration():
    config = HftConfig()
    db_config = config.get_database_config()
    await initialize_database(db_config)
    
    # Apply specific migration
    result = await run_migration("002")  # Migration ID
    print(f"Migration result: {result}")

asyncio.run(apply_migration())
```

### Method 3: Direct SQL Execution

For emergency fixes or when migrations aren't available:

```bash
# Connect to production database
psql -h 31.192.233.13 -p 5432 -U arbitrage_user -d arbitrage_data

-- Apply SQL directly
CREATE TABLE IF NOT EXISTS new_entity (...);
SELECT create_hypertable('new_entity', 'timestamp', if_not_exists => TRUE);
```

## Testing and Validation

### Step 1: Local Testing

Test migrations locally first:

```bash
# Use local database for testing
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=test_arbitrage_data
export POSTGRES_USER=test_user
export POSTGRES_PASSWORD=test_password

# Run integration tests
python src/examples/demo/db_operations_demo.py
```

### Step 2: Production Validation

Create a validation script:

```python
# validate_production_schema.py
import asyncio
import os
from config.config_manager import HftConfig
from db.connection import initialize_database, get_db_manager

async def validate_schema():
    # Set production credentials
    os.environ.update({
        'POSTGRES_HOST': '31.192.233.13',
        'POSTGRES_PORT': '5432',
        'POSTGRES_DB': 'arbitrage_data',
        'POSTGRES_USER': 'arbitrage_user',
        'POSTGRES_PASSWORD': 'qCcmLMmWTL9f3su9rK4dbc4I'
    })
    
    config = HftConfig()
    db_config = config.get_database_config()
    await initialize_database(db_config)
    
    db = get_db_manager()
    
    # Check if new table exists
    exists = await db.fetchval("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'new_entity'
        )
    """)
    
    print(f"New entity table exists: {exists}")
    
    # Check hypertable configuration
    if exists:
        hypertable = await db.fetchval("""
            SELECT COUNT(*) FROM timescaledb_information.hypertables
            WHERE hypertable_name = 'new_entity'
        """)
        print(f"TimescaleDB hypertable configured: {hypertable > 0}")
    
    # Test insert/query performance
    if exists:
        import time
        start = time.perf_counter()
        count = await db.fetchval("SELECT COUNT(*) FROM new_entity")
        elapsed = (time.perf_counter() - start) * 1000
        print(f"Query performance: {elapsed:.2f}ms (target: <5ms)")
    
    await db.close()

asyncio.run(validate_schema())
```

### Step 3: Integration Test Update

Always update the integration test to cover new functionality:

```python
# Add to src/examples/demo/db_operations_demo.py
async def demo_comprehensive_operations():
    """Test all database operations comprehensively."""
    
    # Test all existing operations
    await demo_book_ticker_operations(test_symbol)
    await demo_funding_rate_operations(test_symbol.id)
    await demo_balance_operations(test_exchange.id)
    
    # Test new entity operations
    await demo_new_entity_operations(test_symbol.id)
    
    # Cross-table validation
    await validate_foreign_keys()
    await validate_data_consistency()
```

## Migration System

### Automatic Migration Detection

The system automatically detects and applies migrations during database initialization:

1. **Connection Initialization**: `initialize_database()` calls `run_pending_migrations()`
2. **Migration Discovery**: System scans `src/db/migrations/` for new migration files
3. **Dependency Check**: Validates required tables exist before applying migrations
4. **Atomic Application**: Each migration runs in a transaction
5. **Logging**: All migration activities are logged for audit trails

### Migration File Structure

```
src/db/migrations/
├── __init__.py                    # Migration orchestration
├── 001_add_missing_tables.py     # Initial missing tables
├── 002_add_new_entity.py         # Your new entity
└── 003_add_analytics_tables.py   # Future migrations
```

### Migration Naming Convention

- **Format**: `{number:03d}_{descriptive_name}.py`
- **Number**: Sequential, starting from 001
- **Name**: Snake_case description of changes
- **Examples**: `001_add_missing_tables.py`, `002_add_performance_metrics.py`

## Best Practices

### Database Design

1. **Follow Normalization**: Always use foreign keys to exchanges/symbols tables
2. **Use TimescaleDB**: For any time-series data (timestamp column)
3. **Add Constraints**: Validate data at database level
4. **HFT Indexes**: Create indexes for sub-5ms query performance
5. **Retention Policies**: Set appropriate data retention (3-14 days)

### Development Workflow

1. **Local Development**: Test all changes locally first
2. **Migration Scripts**: Always create migration scripts for schema changes
3. **Update Documentation**: Keep `docker/init-db.sql` synchronized
4. **Integration Tests**: Add tests for new operations
5. **Performance Validation**: Ensure HFT compliance (<5ms queries)

### Code Standards

1. **Type Safety**: Use msgspec.Struct for all data models
2. **Validation**: Implement `validate()` methods for data integrity
3. **Error Handling**: Use try-except blocks for database operations
4. **Logging**: Log all significant database operations
5. **Documentation**: Document all new tables and operations

### Production Safety

1. **Backup First**: Always backup production database before changes
2. **Rollback Plan**: Ensure all migrations have rollback capability
3. **Monitoring**: Monitor performance after applying changes
4. **Gradual Rollout**: Test with small data sets first
5. **Validation**: Run comprehensive validation after deployment

## Troubleshooting

### Common Issues

#### Migration Failures

```bash
# Check migration status
python -c "
import asyncio
from db.migrations import get_available_migrations
print(asyncio.run(get_available_migrations()))
"

# Rollback failed migration
python -c "
import asyncio
from db.migrations import rollback_migration
print(asyncio.run(rollback_migration('002')))
"
```

#### Schema Inconsistencies

```sql
-- Check table existence
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;

-- Check foreign key constraints
SELECT constraint_name, table_name, column_name 
FROM information_schema.key_column_usage 
WHERE referenced_table_name IS NOT NULL;

-- Check TimescaleDB hypertables
SELECT hypertable_name, chunk_time_interval 
FROM timescaledb_information.hypertables;
```

#### Performance Issues

```sql
-- Check index usage
SELECT schemaname, tablename, indexname, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes 
WHERE schemaname = 'public'
ORDER BY idx_tup_read DESC;

-- Check query performance
EXPLAIN ANALYZE SELECT * FROM new_entity 
WHERE symbol_id = 1 
ORDER BY timestamp DESC LIMIT 10;
```

### Debug Scripts

#### Connection Test

```python
# test_connection.py
import asyncio
import asyncpg

async def test_connection():
    try:
        conn = await asyncpg.connect(
            host='31.192.233.13',
            port=5432,
            user='arbitrage_user',
            password='qCcmLMmWTL9f3su9rK4dbc4I',
            database='arbitrage_data'
        )
        version = await conn.fetchval('SELECT version()')
        print(f"✅ Connected: {version}")
        await conn.close()
    except Exception as e:
        print(f"❌ Connection failed: {e}")

asyncio.run(test_connection())
```

#### Schema Validation

```python
# validate_schema.py
import asyncio
from db.connection import initialize_database, get_db_manager
from config.config_manager import HftConfig

async def validate_complete_schema():
    config = HftConfig()
    db_config = config.get_database_config()
    await initialize_database(db_config)
    
    db = get_db_manager()
    
    # Required tables
    required_tables = [
        'exchanges', 'symbols', 'book_ticker_snapshots',
        'funding_rate_snapshots', 'balance_snapshots', 'trade_snapshots'
    ]
    
    print("📋 Schema Validation Results:")
    for table in required_tables:
        exists = await db.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = $1
            )
        """, table)
        status = "✅" if exists else "❌"
        print(f"  {status} {table}")
    
    await db.close()

asyncio.run(validate_complete_schema())
```

## Summary

This guide provides a complete workflow for database development in the CEX Arbitrage Engine:

1. **Design** your entity with proper normalization
2. **Create** migration scripts with up/down functions
3. **Update** `docker/init-db.sql` for documentation
4. **Implement** data models and operations
5. **Test** with integration tests
6. **Deploy** using automatic migration system
7. **Validate** schema and performance in production

The system is designed for safety, performance, and maintainability, with automatic migration detection and comprehensive testing workflows.

### Key Production Database Details

- **Host**: `31.192.233.13:5432`
- **Database**: `arbitrage_data`
- **User**: `arbitrage_user`
- **Features**: TimescaleDB, normalized schema, HFT optimization
- **Retention**: 3-14 days depending on table type
- **Performance**: Sub-5ms query targets for all operations

Follow this guide to ensure consistent, safe, and performant database development practices.