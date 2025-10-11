# Database Development Guide

## 🚨 CRITICAL: NORMALIZED SCHEMA IS THE CURRENT ARCHITECTURE

**MANDATORY READING FOR ALL AGENTS**: This system uses a **FULLY NORMALIZED DATABASE SCHEMA** with foreign key relationships. Any suggestions to use legacy denormalized patterns will be rejected.

**THE NORMALIZED SCHEMA IS NOT A SUGGESTION - IT IS THE CURRENT IMPLEMENTATION**

## Overview

This guide covers the complete database development workflow for the CEX Arbitrage Engine's **normalized database architecture**, including current schema structure, adding new entities, applying changes to production, and maintaining integration tests.

**Key Architectural Facts**:
- ✅ **CURRENT**: All time-series tables use `symbol_id` foreign keys to `symbols` table
- ✅ **CURRENT**: All balance tables use `exchange_id` foreign keys to `exchanges` table  
- ✅ **CURRENT**: All queries MUST use JOINs with normalized foreign keys
- ❌ **LEGACY**: No direct `exchange`, `symbol_base`, `symbol_quote` fields in time-series tables
- ❌ **LEGACY**: No denormalized patterns are supported

## Table of Contents

1. [Current Database Structure](#current-database-structure)
2. [Adding New Database Entities](#adding-new-database-entities)
3. [Production Deployment Workflow](#production-deployment-workflow)
4. [Testing and Validation](#testing-and-validation)
5. [Migration System](#migration-system)
6. [Best Practices](#best-practices)
7. [Troubleshooting](#troubleshooting)

## Current Database Structure

### CURRENT DATABASE SCHEMA (FULLY NORMALIZED - NOT LEGACY)

🚨 **CRITICAL UNDERSTANDING**: The database uses a **FULLY NORMALIZED SCHEMA** with proper foreign key relationships. This is the **CURRENT IMPLEMENTATION**, not a future design:

**ACTUAL PRODUCTION SCHEMA** (currently deployed and functioning):

```sql
-- Foundation Tables (Reference Data) - NORMALIZED
exchanges (id, enum_value, exchange_name, market_type)
symbols (id, exchange_id FK, symbol_base, symbol_quote, exchange_symbol)

-- Time-Series Data Tables (TimescaleDB Hypertables) - NORMALIZED
book_ticker_snapshots (
    id, timestamp, symbol_id FK,
    bid_price, bid_qty, ask_price, ask_qty, sequence_number, update_type, created_at
)
funding_rate_snapshots (timestamp, symbol_id FK, funding_rate, funding_time, next_funding_time, ...)
balance_snapshots (timestamp, exchange_id FK, asset_name, available_balance, locked_balance, ...)
trade_snapshots (timestamp, symbol_id FK, price, quantity, side, trade_id, ...)

-- Analytics Tables
arbitrage_opportunities (timestamp, symbol_id FK, buy_exchange_id FK, sell_exchange_id FK, spread_bps, ...)
order_flow_metrics (timestamp, symbol_id FK, ofi_score, microprice, volume_imbalance, ...)
```

**Key Schema Details:**
- **Current Status**: Fully normalized schema with foreign key relationships throughout
- **All Time-Series Tables**: Use symbol_id FK to symbols table for data consistency
- **Balance Tables**: Use exchange_id FK to exchanges table
- **Foreign Key Integrity**: All data tables maintain referential integrity
- **Performance**: Optimized for sub-5ms queries with proper JOINs and indexing
- **TimescaleDB**: Configured as hypertable with timestamp partitioning
- **Indexes**: Composite indexes on (timestamp, symbol_id) and foreign key indexes

## 🚨 ANTI-PATTERNS TO AVOID - LEGACY DENORMALIZED PATTERNS

**CRITICAL WARNING**: These patterns are from the OLD system design and are **COMPLETELY INCOMPATIBLE** with the current normalized schema:

### ❌ WRONG: Legacy Denormalized Query Patterns (DO NOT USE)

```sql
-- WRONG: This pattern assumes exchange/symbol fields exist in time-series tables
-- These fields DO NOT EXIST in the current normalized schema
SELECT * FROM book_ticker_snapshots 
WHERE exchange = 'MEXC' 
  AND symbol_base = 'BTC' 
  AND symbol_quote = 'USDT'
-- ERROR: columns "exchange", "symbol_base", "symbol_quote" do not exist

-- WRONG: Attempting to INSERT with non-existent denormalized fields  
INSERT INTO book_ticker_snapshots (exchange, symbol_base, symbol_quote, bid_price, ask_price)
VALUES ('MEXC', 'BTC', 'USDT', 50000.0, 50001.0)
-- ERROR: columns "exchange", "symbol_base", "symbol_quote" do not exist

-- WRONG: Any query that assumes direct string fields in time-series tables
SELECT COUNT(*) FROM funding_rate_snapshots WHERE exchange = 'GATEIO_FUTURES'
-- ERROR: column "exchange" does not exist
```

### ✅ CORRECT: Normalized Schema Query Patterns (CURRENT IMPLEMENTATION)

```sql
-- CORRECT: Use JOINs with foreign key relationships (CURRENT SCHEMA)
SELECT bts.timestamp, s.symbol_base, s.symbol_quote, e.enum_value as exchange,
       bts.bid_price, bts.ask_price, bts.bid_qty, bts.ask_qty
FROM book_ticker_snapshots bts
INNER JOIN symbols s ON bts.symbol_id = s.id
INNER JOIN exchanges e ON s.exchange_id = e.id
WHERE e.enum_value = 'MEXC_SPOT' 
  AND s.symbol_base = 'BTC' 
  AND s.symbol_quote = 'USDT'
ORDER BY bts.timestamp DESC
LIMIT 10;

-- CORRECT: Insert using foreign keys (CURRENT SCHEMA)
INSERT INTO book_ticker_snapshots (timestamp, symbol_id, bid_price, ask_price, bid_qty, ask_qty)
VALUES (NOW(), 1, 50000.0, 50001.0, 1.5, 2.0)
-- Uses symbol_id foreign key, not redundant string fields

-- CORRECT: Cross-exchange analysis with normalized JOINs
SELECT 
    s.symbol_base, 
    s.symbol_quote,
    COUNT(*) as snapshot_count,
    AVG(bts.bid_price) as avg_bid_price
FROM book_ticker_snapshots bts
INNER JOIN symbols s ON bts.symbol_id = s.id
INNER JOIN exchanges e ON s.exchange_id = e.id
WHERE bts.timestamp > NOW() - INTERVAL '1 hour'
GROUP BY s.symbol_base, s.symbol_quote
ORDER BY snapshot_count DESC;

-- CORRECT: Balance queries with exchange foreign keys
SELECT bs.timestamp, e.enum_value as exchange, bs.asset_name, 
       bs.available_balance, bs.locked_balance, bs.total_balance
FROM balance_snapshots bs
INNER JOIN exchanges e ON bs.exchange_id = e.id
WHERE e.enum_value = 'GATEIO_FUTURES'
  AND bs.asset_name = 'USDT'
  AND bs.timestamp > NOW() - INTERVAL '24 hours'
ORDER BY bs.timestamp DESC;
```

### 🚫 COMMON MISTAKES TO NEVER MAKE

1. **Assuming Legacy Field Names**:
   ```sql
   -- WRONG: These columns don't exist
   WHERE exchange = 'MEXC'        -- Use: e.enum_value = 'MEXC_SPOT'
   WHERE symbol = 'BTCUSDT'       -- Use: s.symbol_base = 'BTC' AND s.symbol_quote = 'USDT'
   WHERE pair = 'BTC/USDT'        -- Use: JOINs with symbols table
   ```

2. **Creating Denormalized Models**:
   ```python
   # WRONG: Models with transient fields
   @struct
   class BadBookTicker:
       exchange: str        # WRONG: Not stored in database
       symbol_base: str     # WRONG: Not stored in database  
       symbol_quote: str    # WRONG: Not stored in database
       bid_price: float
   
   # CORRECT: Normalized model
   @struct
   class BookTicker:
       symbol_id: int       # CORRECT: Foreign key only
       bid_price: float
       ask_price: float
       timestamp: datetime
   ```

3. **Writing SQL Without JOINs**:
   ```sql
   -- WRONG: Assumes denormalized data
   SELECT * FROM trade_snapshots WHERE exchange = 'GATEIO_FUTURES';
   
   -- CORRECT: Uses proper JOINs
   SELECT ts.*, s.symbol_base, s.symbol_quote, e.enum_value
   FROM trade_snapshots ts
   INNER JOIN symbols s ON ts.symbol_id = s.id
   INNER JOIN exchanges e ON s.exchange_id = e.id
   WHERE e.enum_value = 'GATEIO_FUTURES';
   ```

### 💡 AGENT GUIDANCE: How to Verify Schema Compliance

Before suggesting ANY database query or operation:

1. **Check Table Structure**: All time-series tables have `symbol_id` foreign keys, NOT string fields
2. **Use JOINs Always**: Every query needing exchange/symbol info MUST JOIN with normalized tables
3. **No String Filters**: Never filter directly on `exchange`, `symbol_base`, `symbol_quote` in time-series tables
4. **Foreign Keys Only**: Models contain only foreign key integers, never resolved strings

### 📋 SCHEMA VERIFICATION CHECKLIST

- ✅ Query uses `symbol_id` foreign key to `symbols` table
- ✅ Query JOINs with `exchanges` table via `symbols.exchange_id`  
- ✅ No direct `exchange`, `symbol_base`, `symbol_quote` fields in time-series tables
- ✅ Models contain only foreign keys, no transient fields
- ✅ Symbol resolution done via cache operations when needed for display

**REMEMBER**: The normalized schema is the CURRENT reality. Legacy patterns will cause database errors.

### Key Relationships (Fully Normalized Schema)

1. **Exchanges → Symbols**: One-to-many relationship (NORMALIZED)
   ```sql
   symbols.exchange_id → exchanges.id
   ```

2. **Symbols → Time-Series Data**: One-to-many relationship (NORMALIZED)
   ```sql
   book_ticker_snapshots.symbol_id → symbols.id
   funding_rate_snapshots.symbol_id → symbols.id
   trade_snapshots.symbol_id → symbols.id
   ```

3. **Exchanges → Balance Data**: One-to-many relationship (NORMALIZED)
   ```sql
   balance_snapshots.exchange_id → exchanges.id
   ```

4. **Query Patterns**: All queries use JOINs with normalized foreign keys
   ```sql
   -- Time-series queries: Use JOINs for normalized schema (HFT optimized)
   SELECT bts.timestamp, s.symbol_base, s.symbol_quote, e.enum_value as exchange,
          bts.bid_price, bts.ask_price
   FROM book_ticker_snapshots bts
   INNER JOIN symbols s ON bts.symbol_id = s.id
   INNER JOIN exchanges e ON s.exchange_id = e.id
   WHERE e.enum_value = 'GATEIO_FUTURES' 
     AND s.symbol_base = 'MYX' 
     AND s.symbol_quote = 'USDT'
   
   -- Balance queries: Use JOINs with exchanges
   SELECT bs.timestamp, e.enum_value as exchange, bs.asset_name, bs.available_balance
   FROM balance_snapshots bs
   INNER JOIN exchanges e ON bs.exchange_id = e.id
   WHERE e.enum_value = 'GATEIO_FUTURES'
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
    """New entity data structure for HFT operations.
    
    IMPORTANT: This model follows normalized design principles:
    - Uses symbol_id foreign key for symbol resolution
    - NO transient fields (exchange, symbol_base, symbol_quote)
    - Symbol data resolved via cache operations when needed
    - Maintains single source of truth through foreign keys
    """
    symbol_id: int  # Foreign key to symbols table - NEVER duplicate symbol data
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

**Critical Design Principle**: 
- **NEVER add transient fields** for data available through foreign keys
- **Use cache operations** for symbol resolution when displaying data
- **Maintain data consistency** through single source of truth

### Step 5: Create Database Operations

Add operations to `src/db/operations.py`:

```python
from db.cache_operations import cached_get_symbol_by_id  # For symbol resolution

async def insert_new_entity(entity: NewEntity) -> int:
    """Insert a single new entity record.
    
    NOTE: Only stores normalized data with symbol_id foreign key.
    Symbol information resolved via cache when needed for display.
    """
    db = get_db_manager()
    
    query = """
        INSERT INTO new_entity (timestamp, symbol_id, field1, field2)
        VALUES ($1, $2, $3, $4)
        RETURNING id
    """
    
    return await db.fetchval(
        query,
        entity.timestamp,
        entity.symbol_id,  # Only foreign key - no duplicate symbol data
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
    """Get the latest new entity record for a symbol.
    
    Returns normalized model with symbol_id only.
    Use cache operations to resolve symbol details when needed.
    """
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
        symbol_id=row['symbol_id'],  # Only foreign key returned
        field1=float(row['field1']),
        field2=row['field2'],
        created_at=row['created_at']
    )


async def get_new_entity_with_symbol_info(entity_id: int) -> Dict[str, Any]:
    """Get new entity with resolved symbol information.
    
    Demonstrates cache-first symbol resolution pattern:
    1. Fetch normalized entity data with foreign key
    2. Resolve symbol details via cache lookup
    3. Combine for display purposes only
    """
    db = get_db_manager()
    
    # Get normalized entity
    entity = await get_latest_new_entity_by_symbol(entity_id)
    if not entity:
        return None
    
    # Resolve symbol via cache (sub-microsecond lookup)
    symbol = cached_get_symbol_by_id(entity.symbol_id)
    
    return {
        'entity': entity,
        'symbol': symbol,
        'display_name': f"{symbol.exchange}:{symbol.symbol_base}/{symbol.symbol_quote}" if symbol else "Unknown"
    }


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

### Database Design - Normalized Architecture

1. **Strict Normalization**: 
   - Always use foreign keys to exchanges/symbols tables
   - **NEVER add transient fields** (exchange, symbol_base, symbol_quote) to models
   - Maintain single source of truth through foreign key relationships
   - Prevents data redundancy and consistency issues in HFT systems

2. **Cache-First Symbol Resolution**:
   - Use `get_cached_symbol_by_id()` for sub-microsecond symbol lookups
   - Cache maintains >95% hit ratio for optimal HFT performance
   - Symbol resolution only when needed for display, not storage
   - Example pattern:
     ```python
     # ✅ CORRECT: Normalized storage, cache resolution
     entity = await get_entity(entity_id)  # Returns model with symbol_id only
     symbol = await get_cached_symbol_by_id(entity.symbol_id)  # <1μs lookup
     
     # ❌ WRONG: Transient fields in model
     class BadEntity:
         symbol_id: int
         exchange: str  # WRONG: Redundant transient field
         symbol_base: str  # WRONG: Redundant transient field
     ```

3. **Use TimescaleDB**: For any time-series data (timestamp column)

4. **Add Constraints**: Validate data at database level

5. **HFT Indexes**: Create indexes for sub-5ms query performance

6. **Retention Policies**: Set appropriate data retention (3-14 days)

### When to Use Cache vs Database Lookups

#### Use Cache Operations (`get_cached_symbol_*`):
- **High-frequency lookups** during trading operations
- **Symbol resolution** for display or validation
- **Real-time processing** where <1μs latency matters
- **Batch operations** requiring multiple symbol lookups

#### Use Direct Database Queries:
- **Analytics queries** with complex JOINs
- **Reporting** where 5-10ms latency is acceptable
- **Data migration** or bulk updates
- **One-time lookups** not in hot path

### HFT Performance Benefits

1. **Reduced Memory Footprint**: No duplicate string data in time-series records
2. **Faster Inserts**: Smaller record size = faster writes (critical for HFT)
3. **Cache Efficiency**: Symbol cache hit ratio >95% with <1μs lookups
4. **Data Consistency**: Single source of truth prevents discrepancies
5. **Simplified Updates**: Change symbol once, reflected everywhere

### Development Workflow

1. **Local Development**: Test all changes locally first
2. **Migration Scripts**: Always create migration scripts for schema changes
3. **Update Documentation**: Keep `docker/init-db.sql` synchronized
4. **Integration Tests**: Add tests for new operations
5. **Performance Validation**: Ensure HFT compliance (<5ms queries)

### Code Standards - Normalized Data Models

1. **Type Safety**: 
   - Use msgspec.Struct for all data models
   - Models contain ONLY normalized fields (foreign keys)
   - NO transient fields that duplicate reference data

2. **Model Design Principles**:
   ```python
   # ✅ CORRECT: Normalized model
   @struct
   class BookTickerSnapshot:
       symbol_id: int  # Foreign key only
       bid_price: float
       ask_price: float
       timestamp: datetime
   
   # ❌ WRONG: Model with transient fields
   @struct
   class BadBookTickerSnapshot:
       symbol_id: int
       exchange: str  # WRONG: Redundant
       symbol_base: str  # WRONG: Redundant
       symbol_quote: str  # WRONG: Redundant
       bid_price: float
       ask_price: float
   ```

3. **Symbol Resolution Pattern**:
   ```python
   # Display layer - resolve symbols via cache when needed
   async def format_for_display(snapshot: BookTickerSnapshot) -> Dict:
       symbol = await get_cached_symbol_by_id(snapshot.symbol_id)
       return {
           'exchange': symbol.exchange if symbol else 'Unknown',
           'pair': f"{symbol.symbol_base}/{symbol.symbol_quote}" if symbol else 'Unknown',
           'bid': snapshot.bid_price,
           'ask': snapshot.ask_price
       }
   ```

4. **Validation**: Implement `validate()` methods for data integrity

5. **Error Handling**: Use try-except blocks for database operations

6. **Logging**: Log all significant database operations

7. **Documentation**: Document normalization strategy and cache usage

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
- **Performance**: 
  - Database queries: Sub-5ms for normalized JOINs
  - Cache lookups: Sub-1μs for symbol resolution
  - Batch inserts: Sub-5ms for up to 100 records

### Architecture Principles Summary

1. **Normalized Storage**: Foreign keys only, no transient fields
2. **Cache-First Resolution**: <1μs symbol lookups with >95% hit ratio
3. **Single Source of Truth**: Data consistency through normalization
4. **HFT Optimized**: Reduced memory, faster inserts, efficient queries
5. **Clean Separation**: Storage layer (normalized) vs Display layer (resolved)

**Remember**: In HFT systems, data redundancy kills performance and consistency. Always normalize, never duplicate.

## 🛡️ ENFORCEMENT GUIDELINES FOR AGENTS

### Mandatory Pre-Flight Checks for ALL Database Operations

Before suggesting ANY database query, schema change, or data operation, ALL agents MUST verify:

#### ✅ Required Verification Checklist

1. **Schema Reality Check**:
   - ✅ Confirm time-series tables use `symbol_id` foreign keys, NOT string fields
   - ✅ Verify no direct `exchange`, `symbol_base`, `symbol_quote` columns exist
   - ✅ Check that JOINs are required for symbol/exchange information

2. **Query Pattern Compliance**:
   - ✅ All queries use proper JOINs with normalized foreign keys
   - ✅ Filter conditions use `e.enum_value = 'EXCHANGE_TYPE'` not `exchange = 'EXCHANGE'`
   - ✅ Symbol filtering uses `s.symbol_base = 'BTC' AND s.symbol_quote = 'USDT'`

3. **Model Structure Validation**:
   - ✅ Data models contain ONLY foreign key integers, no transient strings
   - ✅ No `exchange`, `symbol_base`, `symbol_quote` fields in struct definitions
   - ✅ Cache operations used for symbol resolution when needed for display

### 🚫 IMMEDIATE REJECTION CRITERIA

**REJECT any suggestion that includes**:
- Direct filtering on non-existent columns: `WHERE exchange = 'MEXC'`
- Models with transient fields: `exchange: str`, `symbol_base: str`, `symbol_quote: str`
- SQL without JOINs when needing exchange/symbol information
- References to "denormalized" schema as current implementation
- Attempts to add redundant string fields to time-series tables

### 📋 Agent Response Template

When asked about database operations, agents should respond with:

```python
# Step 1: Acknowledge normalized schema
"The database uses a FULLY NORMALIZED SCHEMA with foreign key relationships..."

# Step 2: Provide correct query pattern
"""
SELECT bts.timestamp, s.symbol_base, s.symbol_quote, e.enum_value as exchange,
       bts.bid_price, bts.ask_price
FROM book_ticker_snapshots bts
INNER JOIN symbols s ON bts.symbol_id = s.id
INNER JOIN exchanges e ON s.exchange_id = e.id
WHERE e.enum_value = 'MEXC_SPOT' AND s.symbol_base = 'BTC'
"""

# Step 3: Explain why legacy patterns won't work
"Legacy patterns with direct string fields will cause database errors because 
these columns do not exist in the current normalized schema."
```

### 🎯 Common Agent Scenarios and Required Responses

#### Scenario 1: Query Request for Trading Data
**WRONG Agent Response**:
```sql
SELECT * FROM book_ticker_snapshots WHERE exchange = 'MEXC' AND symbol_base = 'BTC'
```

**CORRECT Agent Response**:
```sql
-- The database uses normalized foreign keys, so we need JOINs:
SELECT bts.*, s.symbol_base, s.symbol_quote, e.enum_value as exchange
FROM book_ticker_snapshots bts
INNER JOIN symbols s ON bts.symbol_id = s.id  
INNER JOIN exchanges e ON s.exchange_id = e.id
WHERE e.enum_value = 'MEXC_SPOT' AND s.symbol_base = 'BTC'
```

#### Scenario 2: Model Creation Request
**WRONG Agent Response**:
```python
@struct
class BookTicker:
    exchange: str  # WRONG
    symbol_base: str  # WRONG
    bid_price: float
```

**CORRECT Agent Response**:
```python
@struct  
class BookTicker:
    symbol_id: int  # CORRECT: Foreign key only
    bid_price: float
    ask_price: float
    timestamp: datetime
    
# Symbol resolution done via cache when needed for display:
# symbol = cached_get_symbol_by_id(ticker.symbol_id)
```

#### Scenario 3: Analytics Query Request
**WRONG Agent Response**:
```sql
SELECT COUNT(*) FROM funding_rate_snapshots WHERE exchange = 'GATEIO_FUTURES'
```

**CORRECT Agent Response**:
```sql
-- Normalized schema requires JOINs to access exchange information:
SELECT COUNT(*) as funding_rate_count, e.enum_value as exchange
FROM funding_rate_snapshots frs
INNER JOIN symbols s ON frs.symbol_id = s.id
INNER JOIN exchanges e ON s.exchange_id = e.id
WHERE e.enum_value = 'GATEIO_FUTURES'
GROUP BY e.enum_value
```

### 📚 Required Reading for Agents

Before working with database operations, agents MUST understand:

1. **[Normalized Architecture Guide](specs/database/normalized-architecture-guide.md)** - Complete normalized design principles
2. **[Current Database Schema](docker/init-db.sql)** - Actual table structure (NOT legacy patterns)
3. **[Cache Operations](src/db/cache_operations.py)** - How to resolve symbols via cache

### 🔍 Schema Verification Commands

Agents can verify schema structure with:
```sql
-- Check actual table columns (NO exchange, symbol_base, symbol_quote in time-series tables)
\d book_ticker_snapshots
\d funding_rate_snapshots
\d balance_snapshots

-- Verify foreign key relationships
SELECT constraint_name, table_name, column_name, foreign_table_name, foreign_column_name
FROM information_schema.key_column_usage
WHERE referenced_table_name IS NOT NULL;
```

### 💡 Performance Justification

The normalized schema is NOT just a design choice - it provides measurable HFT benefits:
- **Memory Efficiency**: 50-70% reduction in storage vs denormalized
- **Cache Performance**: >95% hit ratio with <1μs symbol lookups
- **Data Consistency**: Single source of truth prevents discrepancies
- **Faster Inserts**: Smaller records = faster writes (critical for HFT)

### 🚨 Final Warning to Agents

**The normalized schema with foreign key relationships IS the current production system**. 

Any suggestions using legacy denormalized patterns will:
1. **Cause database errors** (columns don't exist)
2. **Break HFT performance requirements**
3. **Violate architectural principles**
4. **Be immediately rejected**

**When in doubt, always use JOINs with foreign keys. Never assume direct string fields exist in time-series tables.**

---

**This enforcement section ensures all agents understand and comply with the current normalized database architecture, preventing suggestions that would break the production system.**

Follow this guide to ensure consistent, safe, and performant database development practices.