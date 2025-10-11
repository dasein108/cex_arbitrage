# Normalized Database Architecture Guide

## Overview

This guide documents the **normalized database architecture** principles used in the CEX Arbitrage Engine's high-frequency trading (HFT) system. The architecture eliminates data redundancy through strict normalization and leverages ultra-fast caching for symbol resolution.

## Core Architecture Principles

### 1. Strict Normalization - No Transient Fields

**Fundamental Rule**: Database models contain ONLY normalized data with foreign key relationships. No transient fields that duplicate reference data.

#### ✅ CORRECT: Normalized Model
```python
@struct
class BookTickerSnapshot:
    """Normalized model with foreign key only."""
    symbol_id: int  # Foreign key to symbols table
    bid_price: float
    bid_qty: float
    ask_price: float
    ask_qty: float
    timestamp: datetime
    # NO transient fields (exchange, symbol_base, symbol_quote)
```

#### ❌ WRONG: Model with Transient Fields
```python
@struct
class BadBookTickerSnapshot:
    """Anti-pattern: Redundant transient fields."""
    symbol_id: int
    exchange: str  # WRONG: Duplicates symbols.exchange
    symbol_base: str  # WRONG: Duplicates symbols.symbol_base
    symbol_quote: str  # WRONG: Duplicates symbols.symbol_quote
    bid_price: float
    ask_price: float
```

### 2. Cache-First Symbol Resolution

Symbol information is resolved through high-performance caching when needed for display or processing, NOT stored redundantly.

#### Performance Characteristics
- **Cache Lookups**: <1μs average latency
- **Hit Ratio**: >95% sustained
- **Memory Efficiency**: Single copy of symbol data
- **Consistency**: Single source of truth

#### Resolution Pattern
```python
from db.cache_operations import cached_get_symbol_by_id

async def get_snapshot_with_symbol(snapshot_id: int):
    """Pattern for resolving symbol information."""
    # 1. Fetch normalized data (contains only symbol_id)
    snapshot = await get_book_ticker_snapshot(snapshot_id)
    
    # 2. Resolve symbol via cache (<1μs lookup)
    symbol = cached_get_symbol_by_id(snapshot.symbol_id)
    
    # 3. Combine for display only
    return {
        'snapshot': snapshot,
        'exchange': symbol.exchange if symbol else 'Unknown',
        'pair': f"{symbol.symbol_base}/{symbol.symbol_quote}" if symbol else 'Unknown'
    }
```

## Database Schema Design

### Normalized Table Structure

```sql
-- Reference tables (source of truth)
exchanges (id, enum_value, exchange_name, market_type)
symbols (id, exchange_id FK, symbol_base, symbol_quote, exchange_symbol)

-- Time-series tables (normalized with foreign keys only)
book_ticker_snapshots (
    timestamp, 
    symbol_id FK,  -- Only foreign key, no symbol data
    bid_price, ask_price, bid_qty, ask_qty
)

funding_rate_snapshots (
    timestamp,
    symbol_id FK,  -- Only foreign key, no symbol data
    funding_rate, funding_time, next_funding_time
)

balance_snapshots (
    timestamp,
    exchange_id FK,  -- Only foreign key, no exchange name
    asset_name, available_balance, locked_balance
)
```

### Foreign Key Relationships

```
exchanges ←─────── symbols ←─────── book_ticker_snapshots
    ↑                  ↑
    │                  └────────── funding_rate_snapshots
    │                  
    └──────────────────────────── balance_snapshots
```

## HFT Performance Benefits

### 1. Reduced Memory Footprint
- **Without Normalization**: Each record stores redundant strings (exchange, symbol_base, symbol_quote)
- **With Normalization**: Only 4-byte integer foreign key per record
- **Savings**: ~50-100 bytes per record × millions of records = GB of memory saved

### 2. Faster Database Operations
- **Insert Performance**: Smaller records = faster writes (critical for HFT)
- **Query Performance**: Optimized JOINs with indexed foreign keys
- **Batch Operations**: <5ms for 100 record batches

### 3. Cache Efficiency
- **Symbol Cache**: >95% hit ratio with <1μs lookups
- **Memory Locality**: Hot data stays in CPU cache
- **Reduced Database Load**: Most symbol lookups never hit database

### 4. Data Consistency
- **Single Source of Truth**: Symbol data exists in one place only
- **No Synchronization Issues**: Update symbol once, reflected everywhere
- **Referential Integrity**: Foreign key constraints prevent orphaned data

## Implementation Guidelines

### Creating New Models

```python
# Step 1: Design normalized model
@struct
class NewTradingData:
    """Always use foreign keys, never duplicate reference data."""
    symbol_id: int  # Foreign key only
    exchange_id: int  # Foreign key only
    # ... other non-redundant fields
    timestamp: datetime
    
    # NO transient fields like:
    # - exchange_name
    # - symbol_base
    # - symbol_quote
```

### Database Operations

```python
# Step 2: Insert normalized data
async def insert_trading_data(data: NewTradingData) -> int:
    """Insert only normalized data."""
    query = """
        INSERT INTO trading_data (symbol_id, exchange_id, ...)
        VALUES ($1, $2, ...)
    """
    return await db.execute(query, data.symbol_id, data.exchange_id, ...)

# Step 3: Query with JOINs when needed
async def get_trading_data_with_symbols():
    """Use JOINs for complete data in analytics/reporting."""
    query = """
        SELECT td.*, s.symbol_base, s.symbol_quote, e.exchange_name
        FROM trading_data td
        JOIN symbols s ON td.symbol_id = s.id
        JOIN exchanges e ON td.exchange_id = e.id
        WHERE td.timestamp > NOW() - INTERVAL '1 hour'
    """
    return await db.fetch(query)
```

### Display Layer Pattern

```python
# Step 4: Resolve symbols for display
async def format_for_display(data: NewTradingData) -> Dict:
    """Resolve foreign keys via cache for display."""
    # Cache lookups (<1μs each)
    symbol = cached_get_symbol_by_id(data.symbol_id)
    exchange = cached_get_exchange_by_id(data.exchange_id)
    
    return {
        'exchange': exchange.exchange_name if exchange else 'Unknown',
        'pair': f"{symbol.symbol_base}/{symbol.symbol_quote}" if symbol else 'Unknown',
        # ... other fields
    }
```

## When to Use Cache vs Database

### Use Cache Operations
- **Hot Path Operations**: Trading decisions, order placement
- **High-Frequency Lookups**: Multiple lookups per second
- **Symbol Resolution**: Converting symbol_id to symbol details
- **Real-time Processing**: Where <1μs latency matters

### Use Database Queries
- **Analytics**: Complex queries with aggregations
- **Reporting**: Where 5-10ms latency is acceptable
- **Bulk Operations**: Data migration, batch updates
- **Cold Path**: One-time lookups, administrative queries

## Anti-Patterns to Avoid

### ❌ Never Do This

```python
# WRONG: Adding transient fields to models
@struct
class WrongModel:
    symbol_id: int
    exchange: str  # WRONG: Redundant
    symbol_base: str  # WRONG: Redundant
    symbol_quote: str  # WRONG: Redundant

# WRONG: Storing resolved data in database
snapshot.exchange = symbol.exchange  # WRONG
await save_snapshot(snapshot)  # Saves redundant data

# WRONG: Fetching symbol data with every query
SELECT bts.*, s.symbol_base, s.symbol_quote  # Unnecessary for hot path
FROM book_ticker_snapshots bts
JOIN symbols s ON bts.symbol_id = s.id
```

### ✅ Always Do This

```python
# CORRECT: Normalized models
@struct
class CorrectModel:
    symbol_id: int  # Foreign key only
    # ... other fields

# CORRECT: Resolve via cache when needed
symbol = cached_get_symbol_by_id(model.symbol_id)

# CORRECT: Store only foreign keys
snapshot = BookTickerSnapshot(symbol_id=symbol_id, ...)
await save_snapshot(snapshot)
```

## Migration Path

### Removing Transient Fields

If your codebase has existing transient fields:

1. **Identify Models**: Find all models with redundant fields
2. **Remove Fields**: Delete transient field declarations
3. **Update Operations**: Ensure operations don't reference removed fields
4. **Add Cache Lookups**: Implement cache resolution where display needed
5. **Test Performance**: Verify <1μs cache lookups, >95% hit ratio

### Example Migration

```python
# Before (with transient fields)
class OldModel:
    symbol_id: int
    exchange: str  # Remove
    symbol_base: str  # Remove
    symbol_quote: str  # Remove
    price: float

# After (normalized)
class NewModel:
    symbol_id: int
    price: float

# Add resolution layer
async def get_display_data(model: NewModel):
    symbol = cached_get_symbol_by_id(model.symbol_id)
    return {
        'price': model.price,
        'exchange': symbol.exchange,
        'pair': f"{symbol.symbol_base}/{symbol.symbol_quote}"
    }
```

## Performance Metrics

### Target Performance
- **Cache Hit Ratio**: >95%
- **Cache Lookup Time**: <1μs
- **Database Queries**: <5ms for normalized JOINs
- **Batch Inserts**: <5ms for 100 records
- **Memory Reduction**: 50-70% vs denormalized

### Monitoring
```python
from db.cache import get_cache_stats

async def monitor_cache_performance():
    """Monitor cache effectiveness."""
    stats = await get_cache_stats()
    assert stats['hit_ratio'] > 0.95, f"Cache hit ratio too low: {stats['hit_ratio']}"
    assert stats['avg_lookup_time_us'] < 1.0, f"Cache too slow: {stats['avg_lookup_time_us']}μs"
```

## Summary

The normalized database architecture provides:

1. **Data Consistency**: Single source of truth via foreign keys
2. **HFT Performance**: <1μs cache lookups, <5ms database operations
3. **Memory Efficiency**: 50-70% reduction in storage requirements
4. **Maintainability**: Update reference data once, reflected everywhere
5. **Scalability**: Optimized for millions of records

**Golden Rule**: Store foreign keys only. Resolve details via cache when needed for display. Never store redundant data.

---

*This guide represents the architectural foundation for all database operations in the CEX Arbitrage Engine's HFT system. Following these principles ensures optimal performance, data consistency, and system maintainability.*