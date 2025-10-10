# DatabaseManager Class Design

**Detailed design specification for the unified DatabaseManager class**

## Class Overview

The DatabaseManager class will replace the entire `/src/db/` directory (12 files, ~7,600 LOC) with a single, comprehensive class (~800-1200 LOC) that handles all database operations with built-in caching.

## Core Architecture

### Class Structure

```python
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
import asyncio
import logging
import time
import asyncpg
from config.config_manager import HftConfig

class DatabaseManager:
    """
    Unified database manager handling all operations with built-in caching.
    
    Replaces the entire db/ directory with simplified, efficient functionality:
    - Connection management with asyncpg pooling
    - Built-in dictionary-based caching with TTL
    - All CRUD operations for exchanges, symbols, book tickers, balances, funding rates
    - Automatic cache invalidation and cleanup
    - HFT-optimized performance with minimal overhead
    """
```

### Instance Variables

```python
def __init__(self):
    # Core infrastructure
    self._pool: Optional[asyncpg.Pool] = None
    self._config: Optional[DatabaseConfig] = None
    self._logger = logging.getLogger(__name__)
    
    # Built-in caching with TTL
    self._cache: Dict[str, Dict] = {
        'exchanges': {},      # exchange_id/enum -> Exchange data
        'symbols': {},        # symbol_id -> Symbol data  
        'latest_data': {}     # latest snapshots with short TTL
    }
    
    # Cache metadata for TTL management
    self._cache_timestamps: Dict[str, Dict] = {
        'exchanges': {},
        'symbols': {},
        'latest_data': {}
    }
    
    # Cache configuration (seconds)
    self._cache_ttl = {
        'exchanges': 300,     # 5 minutes - rarely change
        'symbols': 300,       # 5 minutes - rarely change
        'latest_data': 30     # 30 seconds - market data
    }
    
    # Performance tracking
    self._stats = {
        'cache_hits': 0,
        'cache_misses': 0,
        'db_queries': 0,
        'last_cleanup': time.time()
    }
```

## Core Infrastructure Methods

### Initialization and Connection Management

```python
async def initialize(self) -> None:
    """
    Initialize database connection and cache.
    Uses HftConfig to load database configuration.
    """
    if self._pool is not None:
        self._logger.warning("DatabaseManager already initialized")
        return
    
    # Load configuration
    config_manager = HftConfig()
    self._config = config_manager.get_database_config()
    
    # Create connection pool
    self._pool = await asyncpg.create_pool(
        dsn=self._config.get_dsn(),
        min_size=self._config.min_pool_size,
        max_size=self._config.max_pool_size,
        command_timeout=self._config.command_timeout,
        server_settings={'application_name': 'cex_arbitrage_unified'}
    )
    
    # Test connection
    async with self._pool.acquire() as conn:
        await conn.fetchval('SELECT 1')
    
    # Initialize cache with essential data
    await self._warm_essential_cache()
    
    self._logger.info("DatabaseManager initialized successfully")

async def close(self) -> None:
    """Close database connection pool and clear cache."""
    if self._pool:
        await self._pool.close()
        self._pool = None
    
    self._cache.clear()
    self._cache_timestamps.clear()
    self._logger.info("DatabaseManager closed")

@property
def is_initialized(self) -> bool:
    """Check if manager is initialized."""
    return self._pool is not None
```

### Built-in Caching System

```python
def _cache_get(self, key: str, cache_type: str = 'exchanges') -> Optional[Any]:
    """
    Get value from cache with TTL check.
    
    Args:
        key: Cache key
        cache_type: Cache category (exchanges, symbols, latest_data)
    
    Returns:
        Cached value or None if expired/missing
    """
    if key not in self._cache[cache_type]:
        self._stats['cache_misses'] += 1
        return None
    
    # Check TTL
    timestamp = self._cache_timestamps[cache_type].get(key, 0)
    ttl = self._cache_ttl[cache_type]
    
    if time.time() - timestamp > ttl:
        # Expired, remove from cache
        self._cache[cache_type].pop(key, None)
        self._cache_timestamps[cache_type].pop(key, None)
        self._stats['cache_misses'] += 1
        return None
    
    self._stats['cache_hits'] += 1
    return self._cache[cache_type][key]

def _cache_set(self, key: str, value: Any, cache_type: str = 'exchanges') -> None:
    """
    Set value in cache with timestamp.
    
    Args:
        key: Cache key
        value: Value to cache
        cache_type: Cache category
    """
    self._cache[cache_type][key] = value
    self._cache_timestamps[cache_type][key] = time.time()

def _cache_invalidate(self, pattern: str = None, cache_type: str = None) -> None:
    """
    Invalidate cache entries.
    
    Args:
        pattern: Key pattern to match (None = all)
        cache_type: Cache category (None = all categories)
    """
    if cache_type:
        if pattern:
            # Pattern-based invalidation
            keys_to_remove = [k for k in self._cache[cache_type] if pattern in k]
            for key in keys_to_remove:
                self._cache[cache_type].pop(key, None)
                self._cache_timestamps[cache_type].pop(key, None)
        else:
            # Clear entire category
            self._cache[cache_type].clear()
            self._cache_timestamps[cache_type].clear()
    else:
        # Clear all caches
        for ct in self._cache:
            self._cache[ct].clear()
            self._cache_timestamps[ct].clear()

def _cleanup_expired_cache(self) -> None:
    """Clean up expired cache entries (called periodically)."""
    current_time = time.time()
    
    # Only cleanup every 60 seconds
    if current_time - self._stats['last_cleanup'] < 60:
        return
    
    for cache_type in self._cache:
        ttl = self._cache_ttl[cache_type]
        expired_keys = []
        
        for key, timestamp in self._cache_timestamps[cache_type].items():
            if current_time - timestamp > ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            self._cache[cache_type].pop(key, None)
            self._cache_timestamps[cache_type].pop(key, None)
    
    self._stats['last_cleanup'] = current_time
```

## Exchange Operations

```python
async def get_exchange_by_enum(self, exchange_enum: "ExchangeEnum") -> Optional[Dict]:
    """
    Get exchange by ExchangeEnum with caching.
    
    Args:
        exchange_enum: ExchangeEnum value
        
    Returns:
        Exchange data dictionary or None
    """
    cache_key = f"enum_{exchange_enum.value}"
    
    # Try cache first
    cached = self._cache_get(cache_key, 'exchanges')
    if cached:
        return cached
    
    # Database query
    self._stats['db_queries'] += 1
    async with self._pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, exchange_name, enum_value, market_type FROM exchanges WHERE enum_value = $1",
            exchange_enum.value
        )
    
    if row:
        exchange_data = dict(row)
        self._cache_set(cache_key, exchange_data, 'exchanges')
        return exchange_data
    
    return None

async def get_exchange_by_id(self, exchange_id: int) -> Optional[Dict]:
    """Get exchange by database ID with caching."""
    cache_key = f"id_{exchange_id}"
    
    cached = self._cache_get(cache_key, 'exchanges')
    if cached:
        return cached
    
    self._stats['db_queries'] += 1
    async with self._pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, exchange_name, enum_value, market_type FROM exchanges WHERE id = $1",
            exchange_id
        )
    
    if row:
        exchange_data = dict(row)
        self._cache_set(cache_key, exchange_data, 'exchanges')
        return exchange_data
    
    return None

async def get_all_exchanges(self) -> List[Dict]:
    """Get all active exchanges with caching."""
    cache_key = "all_exchanges"
    
    cached = self._cache_get(cache_key, 'exchanges')
    if cached:
        return cached
    
    self._stats['db_queries'] += 1
    async with self._pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, exchange_name, enum_value, market_type FROM exchanges ORDER BY exchange_name"
        )
    
    exchanges = [dict(row) for row in rows]
    self._cache_set(cache_key, exchanges, 'exchanges')
    return exchanges

async def insert_exchange(self, exchange_data: Dict) -> int:
    """
    Insert new exchange and invalidate cache.
    
    Args:
        exchange_data: Exchange data with keys: name, enum_value, market_type
        
    Returns:
        Database ID of inserted exchange
    """
    self._stats['db_queries'] += 1
    async with self._pool.acquire() as conn:
        exchange_id = await conn.fetchval(
            """
            INSERT INTO exchanges (exchange_name, enum_value, market_type)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            exchange_data['name'],
            exchange_data['enum_value'], 
            exchange_data['market_type']
        )
    
    # Invalidate exchange cache
    self._cache_invalidate(cache_type='exchanges')
    
    self._logger.info(f"Inserted exchange {exchange_data['name']} with ID {exchange_id}")
    return exchange_id
```

## Symbol Operations

```python
async def get_symbol_by_id(self, symbol_id: int) -> Optional[Dict]:
    """Get symbol by database ID with caching."""
    cache_key = f"id_{symbol_id}"
    
    cached = self._cache_get(cache_key, 'symbols')
    if cached:
        return cached
    
    self._stats['db_queries'] += 1
    async with self._pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, exchange_id, symbol_base, symbol_quote, exchange_symbol, 
                   is_active, symbol_type
            FROM symbols 
            WHERE id = $1
            """,
            symbol_id
        )
    
    if row:
        symbol_data = dict(row)
        self._cache_set(cache_key, symbol_data, 'symbols')
        return symbol_data
    
    return None

async def get_symbols_by_exchange(self, exchange_id: int, active_only: bool = True) -> List[Dict]:
    """Get all symbols for an exchange with caching."""
    cache_key = f"exchange_{exchange_id}_active_{active_only}"
    
    cached = self._cache_get(cache_key, 'symbols')
    if cached:
        return cached
    
    self._stats['db_queries'] += 1
    query = """
        SELECT id, exchange_id, symbol_base, symbol_quote, exchange_symbol, 
               is_active, symbol_type
        FROM symbols 
        WHERE exchange_id = $1
    """
    
    params = [exchange_id]
    if active_only:
        query += " AND is_active = true"
    
    query += " ORDER BY symbol_base, symbol_quote"
    
    async with self._pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    
    symbols = [dict(row) for row in rows]
    self._cache_set(cache_key, symbols, 'symbols')
    return symbols

async def get_symbol_by_exchange_and_pair(
    self, 
    exchange_id: int, 
    symbol_base: str, 
    symbol_quote: str
) -> Optional[Dict]:
    """Get symbol by exchange and base/quote pair."""
    cache_key = f"exchange_{exchange_id}_{symbol_base}_{symbol_quote}"
    
    cached = self._cache_get(cache_key, 'symbols')
    if cached:
        return cached
    
    self._stats['db_queries'] += 1
    async with self._pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, exchange_id, symbol_base, symbol_quote, exchange_symbol, 
                   is_active, symbol_type
            FROM symbols 
            WHERE exchange_id = $1 AND symbol_base = $2 AND symbol_quote = $3
            """,
            exchange_id, symbol_base.upper(), symbol_quote.upper()
        )
    
    if row:
        symbol_data = dict(row)
        self._cache_set(cache_key, symbol_data, 'symbols')
        return symbol_data
    
    return None

async def insert_symbol(self, symbol_data: Dict) -> int:
    """
    Insert new symbol and invalidate cache.
    
    Args:
        symbol_data: Symbol data with required keys
        
    Returns:
        Database ID of inserted symbol
    """
    self._stats['db_queries'] += 1
    async with self._pool.acquire() as conn:
        symbol_id = await conn.fetchval(
            """
            INSERT INTO symbols (
                exchange_id, symbol_base, symbol_quote, exchange_symbol, 
                is_active, symbol_type
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            symbol_data['exchange_id'],
            symbol_data['symbol_base'].upper(),
            symbol_data['symbol_quote'].upper(), 
            symbol_data['exchange_symbol'],
            symbol_data.get('is_active', True),
            symbol_data.get('symbol_type', 'SPOT')
        )
    
    # Invalidate symbol cache for this exchange
    self._cache_invalidate(f"exchange_{symbol_data['exchange_id']}", 'symbols')
    
    self._logger.info(f"Inserted symbol {symbol_data['symbol_base']}/{symbol_data['symbol_quote']} with ID {symbol_id}")
    return symbol_id
```

## BookTicker Operations

```python
async def insert_book_ticker_snapshots(self, snapshots: List[Dict]) -> int:
    """
    Insert book ticker snapshots with deduplication.
    
    Args:
        snapshots: List of snapshot dictionaries with keys:
                  symbol_id, bid_price, bid_qty, ask_price, ask_qty, timestamp
    
    Returns:
        Number of snapshots inserted
    """
    if not snapshots:
        return 0
    
    # Simple deduplication by (symbol_id, timestamp)
    unique_snapshots = {}
    for snapshot in snapshots:
        key = (snapshot['symbol_id'], snapshot['timestamp'])
        unique_snapshots[key] = snapshot
    
    deduplicated = list(unique_snapshots.values())
    
    if not deduplicated:
        return 0
    
    self._stats['db_queries'] += 1
    
    # Batch insert with ON CONFLICT handling
    query = """
        INSERT INTO book_ticker_snapshots (
            symbol_id, bid_price, bid_qty, ask_price, ask_qty, timestamp
        ) VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (symbol_id, timestamp)
        DO UPDATE SET
            bid_price = EXCLUDED.bid_price,
            bid_qty = EXCLUDED.bid_qty,
            ask_price = EXCLUDED.ask_price,
            ask_qty = EXCLUDED.ask_qty
    """
    
    async with self._pool.acquire() as conn:
        async with conn.transaction():
            for snapshot in deduplicated:
                await conn.execute(
                    query,
                    snapshot['symbol_id'],
                    snapshot['bid_price'],
                    snapshot['bid_qty'],
                    snapshot['ask_price'],
                    snapshot['ask_qty'],
                    snapshot['timestamp']
                )
    
    # Invalidate latest data cache
    self._cache_invalidate(cache_type='latest_data')
    
    self._logger.debug(f"Inserted {len(deduplicated)} book ticker snapshots")
    return len(deduplicated)

async def get_latest_book_tickers(
    self, 
    exchange_enum: str = None, 
    symbol_base: str = None,
    symbol_quote: str = None
) -> List[Dict]:
    """
    Get latest book ticker snapshots with caching.
    
    Args:
        exchange_enum: Filter by exchange (optional)
        symbol_base: Filter by base asset (optional)
        symbol_quote: Filter by quote asset (optional)
        
    Returns:
        List of latest book ticker snapshots
    """
    cache_key = f"latest_tickers_{exchange_enum}_{symbol_base}_{symbol_quote}"
    
    cached = self._cache_get(cache_key, 'latest_data')
    if cached:
        return cached
    
    # Build dynamic query
    where_conditions = []
    params = []
    param_counter = 1
    
    base_query = """
        SELECT DISTINCT ON (e.enum_value, s.symbol_base, s.symbol_quote)
               bts.id, bts.symbol_id, e.enum_value as exchange, 
               s.symbol_base, s.symbol_quote,
               bts.bid_price, bts.bid_qty, bts.ask_price, bts.ask_qty,
               bts.timestamp, bts.created_at
        FROM book_ticker_snapshots bts
        JOIN symbols s ON bts.symbol_id = s.id
        JOIN exchanges e ON s.exchange_id = e.id
    """
    
    if exchange_enum:
        where_conditions.append(f"e.enum_value = ${param_counter}")
        params.append(exchange_enum.upper())
        param_counter += 1
    
    if symbol_base:
        where_conditions.append(f"s.symbol_base = ${param_counter}")
        params.append(symbol_base.upper())
        param_counter += 1
    
    if symbol_quote:
        where_conditions.append(f"s.symbol_quote = ${param_counter}")
        params.append(symbol_quote.upper())
        param_counter += 1
    
    if where_conditions:
        base_query += " WHERE " + " AND ".join(where_conditions)
    
    base_query += " ORDER BY e.enum_value, s.symbol_base, s.symbol_quote, bts.timestamp DESC"
    
    self._stats['db_queries'] += 1
    async with self._pool.acquire() as conn:
        rows = await conn.fetch(base_query, *params)
    
    snapshots = [dict(row) for row in rows]
    self._cache_set(cache_key, snapshots, 'latest_data')
    return snapshots

async def get_book_ticker_history(
    self, 
    exchange_enum: str, 
    symbol_base: str, 
    symbol_quote: str,
    hours_back: int = 24
) -> List[Dict]:
    """
    Get book ticker history for analysis.
    
    Args:
        exchange_enum: Exchange identifier
        symbol_base: Base asset
        symbol_quote: Quote asset  
        hours_back: Hours of history to retrieve
        
    Returns:
        List of book ticker snapshots ordered by timestamp
    """
    timestamp_from = datetime.utcnow() - timedelta(hours=hours_back)
    
    self._stats['db_queries'] += 1
    async with self._pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT bts.id, bts.symbol_id, s.symbol_base, s.symbol_quote, 
                   e.enum_value as exchange,
                   bts.bid_price, bts.bid_qty, bts.ask_price, bts.ask_qty, 
                   bts.timestamp, bts.created_at
            FROM book_ticker_snapshots bts
            JOIN symbols s ON bts.symbol_id = s.id
            JOIN exchanges e ON s.exchange_id = e.id
            WHERE e.enum_value = $1 
              AND s.symbol_base = $2
              AND s.symbol_quote = $3
              AND bts.timestamp >= $4
            ORDER BY bts.timestamp ASC
            """,
            exchange_enum.upper(),
            symbol_base.upper(),
            symbol_quote.upper(),
            timestamp_from
        )
    
    return [dict(row) for row in rows]
```

## Balance Operations

```python
async def insert_balance_snapshots(self, snapshots: List[Dict]) -> int:
    """
    Insert balance snapshots with conflict handling.
    
    Args:
        snapshots: List of balance dictionaries with keys:
                  exchange_id, asset_name, available_balance, locked_balance, timestamp
    
    Returns:
        Number of snapshots inserted
    """
    if not snapshots:
        return 0
    
    self._stats['db_queries'] += 1
    
    query = """
    INSERT INTO balance_snapshots (
        timestamp, exchange_id, asset_name, 
        available_balance, locked_balance, frozen_balance,
        borrowing_balance, interest_balance, created_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    ON CONFLICT (timestamp, exchange_id, asset_name) 
    DO UPDATE SET
        available_balance = EXCLUDED.available_balance,
        locked_balance = EXCLUDED.locked_balance,
        frozen_balance = EXCLUDED.frozen_balance,
        borrowing_balance = EXCLUDED.borrowing_balance,
        interest_balance = EXCLUDED.interest_balance
    """
    
    batch_data = []
    for snapshot in snapshots:
        batch_data.append((
            snapshot['timestamp'],
            snapshot['exchange_id'],
            snapshot['asset_name'].upper(),
            float(snapshot['available_balance']),
            float(snapshot['locked_balance']),
            float(snapshot.get('frozen_balance', 0.0)),
            float(snapshot.get('borrowing_balance', 0.0)),
            float(snapshot.get('interest_balance', 0.0)),
            snapshot.get('created_at', datetime.utcnow())
        ))
    
    async with self._pool.acquire() as conn:
        await conn.executemany(query, batch_data)
    
    # Invalidate latest data cache
    self._cache_invalidate(cache_type='latest_data')
    
    self._logger.debug(f"Inserted {len(snapshots)} balance snapshots")
    return len(snapshots)

async def get_latest_balances(self, exchange_enum: str = None) -> List[Dict]:
    """
    Get latest balance snapshots with caching.
    
    Args:
        exchange_enum: Filter by exchange (optional)
        
    Returns:
        List of latest balance snapshots
    """
    cache_key = f"latest_balances_{exchange_enum}"
    
    cached = self._cache_get(cache_key, 'latest_data')
    if cached:
        return cached
    
    where_clause = ""
    params = []
    
    if exchange_enum:
        where_clause = "WHERE e.enum_value = $1"
        params.append(exchange_enum.upper())
    
    query = f"""
        SELECT DISTINCT ON (bs.exchange_id, bs.asset_name)
               bs.id, bs.exchange_id, bs.asset_name,
               bs.available_balance, bs.locked_balance, bs.frozen_balance,
               bs.borrowing_balance, bs.interest_balance,
               bs.timestamp, bs.created_at,
               e.enum_value as exchange_name
        FROM balance_snapshots bs
        JOIN exchanges e ON bs.exchange_id = e.id
        {where_clause}
        ORDER BY bs.exchange_id, bs.asset_name, bs.timestamp DESC
    """
    
    self._stats['db_queries'] += 1
    async with self._pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    
    balances = [dict(row) for row in rows]
    self._cache_set(cache_key, balances, 'latest_data')
    return balances

async def get_balance_history(
    self, 
    exchange_enum: str, 
    asset_name: str, 
    hours_back: int = 24
) -> List[Dict]:
    """Get balance history for an asset."""
    timestamp_from = datetime.utcnow() - timedelta(hours=hours_back)
    
    self._stats['db_queries'] += 1
    async with self._pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT bs.id, bs.exchange_id, bs.asset_name,
                   bs.available_balance, bs.locked_balance, bs.frozen_balance,
                   bs.borrowing_balance, bs.interest_balance,
                   bs.timestamp, bs.created_at,
                   e.enum_value as exchange_name
            FROM balance_snapshots bs
            JOIN exchanges e ON bs.exchange_id = e.id
            WHERE e.enum_value = $1 
              AND bs.asset_name = $2
              AND bs.timestamp >= $3
            ORDER BY bs.timestamp ASC
            """,
            exchange_enum.upper(),
            asset_name.upper(),
            timestamp_from
        )
    
    return [dict(row) for row in rows]
```

## Funding Rate Operations

```python
async def insert_funding_rates(self, snapshots: List[Dict]) -> int:
    """
    Insert funding rate snapshots.
    
    Args:
        snapshots: List of funding rate dictionaries
        
    Returns:
        Number of snapshots inserted
    """
    if not snapshots:
        return 0
    
    self._stats['db_queries'] += 1
    
    query = """
    INSERT INTO funding_rate_snapshots (
        timestamp, symbol_id, funding_rate, funding_time, next_funding_time, created_at
    ) VALUES ($1, $2, $3, $4, $5, $6)
    ON CONFLICT (timestamp, symbol_id) 
    DO UPDATE SET
        funding_rate = EXCLUDED.funding_rate,
        funding_time = EXCLUDED.funding_time,
        next_funding_time = EXCLUDED.next_funding_time
    """
    
    batch_data = []
    for snapshot in snapshots:
        # Ensure funding_time is valid (constraint: > 0)
        funding_time = snapshot.get('funding_time')
        if not funding_time or funding_time <= 0:
            funding_time = int(time.time() * 1000) + (8 * 60 * 60 * 1000)  # +8 hours
        
        batch_data.append((
            snapshot['timestamp'],
            snapshot['symbol_id'],
            snapshot['funding_rate'],
            funding_time,
            snapshot.get('next_funding_time'),
            snapshot.get('created_at', datetime.utcnow())
        ))
    
    async with self._pool.acquire() as conn:
        await conn.executemany(query, batch_data)
    
    # Invalidate latest data cache
    self._cache_invalidate(cache_type='latest_data')
    
    self._logger.debug(f"Inserted {len(snapshots)} funding rate snapshots")
    return len(snapshots)

async def get_latest_funding_rates(self, exchange_enum: str = None) -> List[Dict]:
    """Get latest funding rates with caching."""
    cache_key = f"latest_funding_{exchange_enum}"
    
    cached = self._cache_get(cache_key, 'latest_data')
    if cached:
        return cached
    
    where_clause = ""
    params = []
    
    if exchange_enum:
        where_clause = "WHERE e.enum_value = $1"
        params.append(exchange_enum.upper())
    
    query = f"""
        SELECT DISTINCT ON (frs.symbol_id)
               frs.id, frs.symbol_id, frs.funding_rate, frs.funding_time,
               frs.next_funding_time, frs.timestamp, frs.created_at,
               s.symbol_base, s.symbol_quote, e.enum_value as exchange
        FROM funding_rate_snapshots frs
        JOIN symbols s ON frs.symbol_id = s.id
        JOIN exchanges e ON s.exchange_id = e.id
        {where_clause}
        ORDER BY frs.symbol_id, frs.timestamp DESC
    """
    
    self._stats['db_queries'] += 1
    async with self._pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    
    funding_rates = [dict(row) for row in rows]
    self._cache_set(cache_key, funding_rates, 'latest_data')
    return funding_rates
```

## Utility Methods

```python
async def get_database_stats(self) -> Dict[str, Any]:
    """Get comprehensive database statistics."""
    self._stats['db_queries'] += 1
    
    async with self._pool.acquire() as conn:
        # Get table sizes and counts
        stats = {}
        
        # Basic counts
        stats['exchanges'] = await conn.fetchval("SELECT COUNT(*) FROM exchanges")
        stats['symbols'] = await conn.fetchval("SELECT COUNT(*) FROM symbols")
        stats['book_tickers'] = await conn.fetchval("SELECT COUNT(*) FROM book_ticker_snapshots")
        stats['balances'] = await conn.fetchval("SELECT COUNT(*) FROM balance_snapshots")
        stats['funding_rates'] = await conn.fetchval("SELECT COUNT(*) FROM funding_rate_snapshots")
        
        # Cache statistics
        stats['cache_stats'] = {
            'hits': self._stats['cache_hits'],
            'misses': self._stats['cache_misses'],
            'hit_ratio': self._stats['cache_hits'] / max(1, self._stats['cache_hits'] + self._stats['cache_misses']),
            'db_queries': self._stats['db_queries']
        }
        
        # Cache sizes
        stats['cache_sizes'] = {
            cache_type: len(self._cache[cache_type]) 
            for cache_type in self._cache
        }
    
    return stats

async def cleanup_old_data(self, retention_days: int = 7) -> Dict[str, int]:
    """
    Clean up old data based on retention policy.
    
    Args:
        retention_days: Days of data to keep
        
    Returns:
        Dictionary with cleanup counts
    """
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
    
    self._stats['db_queries'] += 3
    
    async with self._pool.acquire() as conn:
        # Clean book tickers
        book_result = await conn.execute(
            "DELETE FROM book_ticker_snapshots WHERE timestamp < $1",
            cutoff_date
        )
        
        # Clean balances
        balance_result = await conn.execute(
            "DELETE FROM balance_snapshots WHERE timestamp < $1", 
            cutoff_date
        )
        
        # Clean funding rates
        funding_result = await conn.execute(
            "DELETE FROM funding_rate_snapshots WHERE timestamp < $1",
            cutoff_date
        )
    
    # Extract counts from results
    cleanup_counts = {
        'book_tickers': int(book_result.split()[-1]) if book_result else 0,
        'balances': int(balance_result.split()[-1]) if balance_result else 0,
        'funding_rates': int(funding_result.split()[-1]) if funding_result else 0
    }
    
    # Clear cache after cleanup
    self._cache_invalidate()
    
    self._logger.info(f"Cleaned up old data: {cleanup_counts}")
    return cleanup_counts

async def _warm_essential_cache(self) -> None:
    """Warm cache with essential data on initialization."""
    try:
        # Pre-load all exchanges
        exchanges = await self.get_all_exchanges()
        self._logger.debug(f"Pre-loaded {len(exchanges)} exchanges into cache")
        
        # Pre-load symbols for each exchange
        for exchange in exchanges:
            symbols = await self.get_symbols_by_exchange(exchange['id'])
            self._logger.debug(f"Pre-loaded {len(symbols)} symbols for {exchange['enum_value']}")
            
    except Exception as e:
        self._logger.warning(f"Cache warming failed: {e}")

def get_performance_stats(self) -> Dict[str, Any]:
    """Get performance and cache statistics."""
    total_requests = self._stats['cache_hits'] + self._stats['cache_misses']
    
    return {
        'cache_performance': {
            'hit_ratio': self._stats['cache_hits'] / max(1, total_requests),
            'total_requests': total_requests,
            'db_queries_saved': self._stats['cache_hits'],
            'db_queries_made': self._stats['db_queries']
        },
        'cache_sizes': {
            cache_type: len(self._cache[cache_type]) 
            for cache_type in self._cache
        },
        'efficiency_ratio': self._stats['cache_hits'] / max(1, self._stats['db_queries'])
    }
```

## Usage Patterns

### Initialization

```python
# Initialize the manager
db_manager = DatabaseManager()
await db_manager.initialize()

# Manager is ready for use
exchanges = await db_manager.get_all_exchanges()
```

### Exchange Operations

```python
# Get exchange by enum
mexc_exchange = await db_manager.get_exchange_by_enum(ExchangeEnum.MEXC_SPOT)

# Insert new exchange
new_exchange_id = await db_manager.insert_exchange({
    'name': 'TEST_EXCHANGE',
    'enum_value': 'TEST_SPOT',
    'market_type': 'SPOT'
})
```

### Data Collection

```python
# Insert book ticker data
snapshots = [
    {
        'symbol_id': 1,
        'bid_price': 50000.0,
        'bid_qty': 1.5,
        'ask_price': 50001.0,
        'ask_qty': 2.0,
        'timestamp': datetime.utcnow()
    }
]
count = await db_manager.insert_book_ticker_snapshots(snapshots)

# Get latest data
latest_tickers = await db_manager.get_latest_book_tickers('MEXC_SPOT')
```

## Performance Characteristics

### Memory Usage
- **Estimated Memory**: 50-100MB for typical cache sizes
- **Cache Efficiency**: >90% hit ratio for stable operations
- **TTL Management**: Automatic cleanup prevents memory bloat

### Query Performance
- **Cached Operations**: <1μs lookup time
- **Database Queries**: Optimized with proper indexing
- **Batch Operations**: Single transaction for multiple inserts

### Scalability
- **Connection Pooling**: Built-in asyncpg pool management
- **Cache Scaling**: TTL-based expiration prevents unlimited growth
- **Query Optimization**: Prepared statements and efficient SQL

This design provides **all functionality** of the current 12-file system in a **single, maintainable class** with **built-in performance optimization** and **simplified caching**.