"""
Database Operations

High-performance database operations for BookTicker snapshots.
Optimized for HFT requirements with minimal latency and maximum throughput.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Set
from collections import defaultdict
import time

from .connection import get_db_manager
from .models import (BookTickerSnapshot, TradeSnapshot, FundingRateSnapshot,
                     BalanceSnapshot, Exchange, Symbol as DBSymbol, SymbolType)
from exchanges.structs.common import Symbol


logger = logging.getLogger(__name__)

# Global deduplication cache for recent timestamps
# Structure: {(exchange, symbol_base, symbol_quote): {timestamp1, timestamp2, ...}}
_timestamp_cache: Dict[tuple, Set[datetime]] = defaultdict(set)
_cache_last_cleanup = time.time()
_cache_cleanup_interval = 300  # 5 minutes


def _cleanup_timestamp_cache():
    """
    Clean up old entries from the timestamp cache to prevent memory bloat.
    Removes timestamps older than 10 minutes.
    """
    global _cache_last_cleanup
    current_time = time.time()
    
    if current_time - _cache_last_cleanup < _cache_cleanup_interval:
        return
    
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    total_removed = 0
    
    # Clean up old timestamps from each cache entry
    for key in list(_timestamp_cache.keys()):
        timestamp_set = _timestamp_cache[key]
        old_size = len(timestamp_set)
        
        # Remove timestamps older than cutoff
        timestamp_set = {ts for ts in timestamp_set if ts > cutoff_time}
        _timestamp_cache[key] = timestamp_set
        
        # Remove empty entries
        if not timestamp_set:
            del _timestamp_cache[key]
        
        total_removed += old_size - len(timestamp_set)
    
    _cache_last_cleanup = current_time
    if total_removed > 0:
        logger.debug(f"Cleaned {total_removed} old timestamps from deduplication cache")


def _is_duplicate_timestamp(symbol_id: int, timestamp: datetime) -> bool:
    """
    Check if this timestamp has been seen recently for this symbol_id.
    
    Returns:
        True if this is a duplicate timestamp that should be skipped
    """
    key = (symbol_id,)
    
    # Check if we've seen this exact timestamp recently
    if timestamp in _timestamp_cache[key]:
        return True
    
    # Add to cache for future checks
    _timestamp_cache[key].add(timestamp)
    return False


async def insert_book_ticker_snapshot(snapshot: BookTickerSnapshot) -> int:
    """
    Insert a single BookTicker snapshot.
    
    Args:
        snapshot: BookTickerSnapshot to insert (must have valid symbol_id)
        
    Returns:
        Database ID of inserted record
        
    Raises:
        DatabaseError: If insert fails
    """
    db = get_db_manager()
    
    query = """
        INSERT INTO book_ticker_snapshots (
            symbol_id, bid_price, bid_qty, ask_price, ask_qty, timestamp
        ) VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
    """
    
    try:
        record_id = await db.fetchval(
            query,
            snapshot.symbol_id,
            snapshot.bid_price,
            snapshot.bid_qty,
            snapshot.ask_price,
            snapshot.ask_qty,
            snapshot.timestamp
        )
        
        logger.debug(f"Inserted book ticker snapshot {record_id} for symbol_id {snapshot.symbol_id}")
        return record_id
        
    except Exception as e:
        logger.error(f"Failed to insert book ticker snapshot: {e}")
        raise

async def insert_book_ticker_snapshots_batch(snapshots: List[BookTickerSnapshot]) -> int:
    """
    Insert multiple BookTicker snapshots efficiently with upsert logic.
    
    Uses ON CONFLICT DO UPDATE to handle duplicates gracefully.
    Includes both in-memory deduplication and timestamp cache checking.
    
    Args:
        snapshots: List of BookTickerSnapshot objects
        
    Returns:
        Number of records inserted/updated
        
    Raises:
        DatabaseError: If batch insert fails
    """
    if not snapshots:
        return 0
    
    # Clean up cache periodically
    _cleanup_timestamp_cache()
    
    # Filter out known duplicate timestamps using cache
    filtered_snapshots = []
    cache_hits = 0
    
    for snapshot in snapshots:
        if not _is_duplicate_timestamp(snapshot.symbol_id, snapshot.timestamp):
            filtered_snapshots.append(snapshot)
        else:
            cache_hits += 1
    
    if cache_hits > 0:
        logger.debug(f"Cache filtered {cache_hits} duplicate timestamps")
    
    if not filtered_snapshots:
        return 0
    
    # Deduplicate remaining snapshots in memory
    unique_snapshots = {}
    for snapshot in filtered_snapshots:
        key = (snapshot.symbol_id, snapshot.timestamp)
        # Keep the latest one if duplicate timestamps exist
        if key not in unique_snapshots:
            unique_snapshots[key] = snapshot
        else:
            # Compare and keep the one with most recent created_at or bid/ask prices
            existing = unique_snapshots[key]
            if hasattr(snapshot, 'created_at') and hasattr(existing, 'created_at'):
                if snapshot.created_at and existing.created_at and snapshot.created_at > existing.created_at:
                    unique_snapshots[key] = snapshot
    
    deduplicated_snapshots = list(unique_snapshots.values())
    
    if not deduplicated_snapshots:
        return 0
    
    if len(snapshots) != len(deduplicated_snapshots):
        logger.debug(f"Total deduplication: {len(snapshots)} -> {len(deduplicated_snapshots)} snapshots (cache: {cache_hits}, memory: {len(filtered_snapshots) - len(deduplicated_snapshots)})")
    
    db = get_db_manager()
    count = 0
    
    # Use individual upserts in transaction for reliability
    query = """
        INSERT INTO book_ticker_snapshots (
            symbol_id, bid_price, bid_qty, ask_price, ask_qty, timestamp
        ) VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (symbol_id, timestamp)
        DO UPDATE SET
            bid_price = EXCLUDED.bid_price,
            bid_qty = EXCLUDED.bid_qty,
            ask_price = EXCLUDED.ask_price,
            ask_qty = EXCLUDED.ask_qty,
            created_at = NOW()
    """
    
    try:
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                for snapshot in deduplicated_snapshots:
                    await conn.execute(
                        query,
                        snapshot.symbol_id,
                        snapshot.bid_price,
                        snapshot.bid_qty,
                        snapshot.ask_price,
                        snapshot.ask_qty,
                        snapshot.timestamp
                    )
                    count += 1
        
        logger.debug(f"Batch upsert processed {count} snapshots")
        return count
        
    except Exception as e:
        logger.error(f"Failed to batch upsert book ticker snapshots: {e}")
        raise

async def get_book_ticker_snapshots(
    exchange: Optional[str] = None,
    symbol_base: Optional[str] = None,
    symbol_quote: Optional[str] = None,
    timestamp_from: Optional[datetime] = None,
    timestamp_to: Optional[datetime] = None,
    limit: int = 1000,
    offset: int = 0
) -> List[BookTickerSnapshot]:
    """
    Retrieve BookTicker snapshots with flexible filtering using normalized schema.
    
    Args:
        exchange: Filter by exchange (optional)
        symbol_base: Filter by base asset (optional)
        symbol_quote: Filter by quote asset (optional)
        timestamp_from: Start time filter (optional)
        timestamp_to: End time filter (optional)
        limit: Maximum number of records to return
        offset: Number of records to skip
        
    Returns:
        List of BookTickerSnapshot objects with symbol_id
    """
    db = get_db_manager()
    
    # Build dynamic WHERE clause using JOINs for normalized schema
    where_conditions = []
    params = []
    param_counter = 1
    
    if exchange:
        where_conditions.append(f"e.enum_value = ${param_counter}")
        params.append(exchange.upper())
        param_counter += 1
    
    if symbol_base:
        where_conditions.append(f"s.symbol_base = ${param_counter}")
        params.append(symbol_base.upper())
        param_counter += 1
    
    if symbol_quote:
        where_conditions.append(f"s.symbol_quote = ${param_counter}")
        params.append(symbol_quote.upper())
        param_counter += 1
    
    if timestamp_from:
        where_conditions.append(f"bts.timestamp >= ${param_counter}")
        params.append(timestamp_from)
        param_counter += 1
    
    if timestamp_to:
        where_conditions.append(f"bts.timestamp <= ${param_counter}")
        params.append(timestamp_to)
        param_counter += 1
    
    # Add limit and offset
    params.extend([limit, offset])
    
    where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
    
    query = f"""
        SELECT bts.id, bts.symbol_id, bts.bid_price, bts.bid_qty, 
               bts.ask_price, bts.ask_qty, bts.timestamp, bts.created_at
        FROM book_ticker_snapshots bts
        JOIN symbols s ON bts.symbol_id = s.id
        JOIN exchanges e ON s.exchange_id = e.id
        {where_clause}
        ORDER BY bts.timestamp DESC, bts.id DESC
        LIMIT ${param_counter} OFFSET ${param_counter + 1}
    """
    
    try:
        rows = await db.fetch(query, *params)
        
        snapshots = [
            BookTickerSnapshot(
                id=row['id'],
                symbol_id=row['symbol_id'],
                bid_price=float(row['bid_price']),
                bid_qty=float(row['bid_qty']),
                ask_price=float(row['ask_price']),
                ask_qty=float(row['ask_qty']),
                timestamp=row['timestamp'],
                created_at=row['created_at']
            )
            for row in rows
        ]
        
        logger.debug(f"Retrieved {len(snapshots)} normalized book ticker snapshots")
        return snapshots
        
    except Exception as e:
        logger.error(f"Failed to retrieve book ticker snapshots: {e}")
        raise


async def get_latest_book_ticker_snapshots(
    exchange: Optional[str] = None,
    symbol_base: Optional[str] = None,
    symbol_quote: Optional[str] = None
) -> Dict[str, BookTickerSnapshot]:
    """
    Get the latest BookTicker snapshot for each exchange/symbol combination using normalized schema.
    
    Args:
        exchange: Filter by exchange (optional)
        symbol_base: Filter by base asset (optional)
        symbol_quote: Filter by quote asset (optional)
        
    Returns:
        Dictionary mapping "exchange_base_quote" to latest BookTickerSnapshot
    """
    db = get_db_manager()
    
    # Build dynamic WHERE clause using JOINs for normalized schema
    where_conditions = []
    params = []
    param_counter = 1
    
    if exchange:
        where_conditions.append(f"e.enum_value = ${param_counter}")
        params.append(exchange.upper())
        param_counter += 1
    
    if symbol_base:
        where_conditions.append(f"s.symbol_base = ${param_counter}")
        params.append(symbol_base.upper())
        param_counter += 1
    
    if symbol_quote:
        where_conditions.append(f"s.symbol_quote = ${param_counter}")
        params.append(symbol_quote.upper())
        param_counter += 1
    
    where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
    
    query = f"""
        SELECT DISTINCT ON (e.enum_value, s.symbol_base, s.symbol_quote)
               bts.id, bts.symbol_id, e.enum_value as exchange, 
               s.symbol_base, s.symbol_quote,
               bts.bid_price, bts.bid_qty, bts.ask_price, bts.ask_qty,
               bts.timestamp, bts.created_at
        FROM book_ticker_snapshots bts
        JOIN symbols s ON bts.symbol_id = s.id
        JOIN exchanges e ON s.exchange_id = e.id
        {where_clause}
        ORDER BY e.enum_value, s.symbol_base, s.symbol_quote, bts.timestamp DESC
    """
    
    try:
        rows = await db.fetch(query, *params)
        
        latest_snapshots = {}
        for row in rows:
            snapshot = BookTickerSnapshot(
                id=row['id'],
                symbol_id=row['symbol_id'],
                bid_price=float(row['bid_price']),
                bid_qty=float(row['bid_qty']),
                ask_price=float(row['ask_price']),
                ask_qty=float(row['ask_qty']),
                timestamp=row['timestamp'],
                created_at=row['created_at']
            )
            
            key = f"{row['exchange']}_{row['symbol_base']}_{row['symbol_quote']}"
            latest_snapshots[key] = snapshot
        
        logger.debug(f"Retrieved {len(latest_snapshots)} latest normalized book ticker snapshots")
        return latest_snapshots
        
    except Exception as e:
        logger.error(f"Failed to retrieve latest book ticker snapshots: {e}")
        raise


async def get_book_ticker_snapshots_by_exchange_and_symbol(
    exchange_enum_value: str,
    symbol_base: str,
    symbol_quote: str,
    timestamp_from: datetime,
    timestamp_to: datetime,
    limit: int = 10000
) -> List[BookTickerSnapshot]:
    """
    Retrieve BookTicker snapshots by exchange and symbol for backtesting (normalized schema).
    
    Optimized for HFT backtesting with the normalized book_ticker_snapshots schema.
    Target: <10ms for queries up to 10,000 records.
    
    Args:
        exchange_enum_value: Exchange enum value (e.g., 'MEXC_SPOT')
        symbol_base: Symbol base asset (e.g., 'NEIROETH')
        symbol_quote: Symbol quote asset (e.g., 'USDT')
        timestamp_from: Start time filter
        timestamp_to: End time filter
        limit: Maximum number of records to return
        
    Returns:
        List of BookTickerSnapshot objects ordered by timestamp ASC for backtesting
    """
    db = get_db_manager()
    
    # Query with normalized schema using JOINs to resolve symbol_id
    query = """
        SELECT bts.id, bts.symbol_id, s.symbol_base, s.symbol_quote, e.enum_value as exchange,
               bts.bid_price, bts.bid_qty, bts.ask_price, bts.ask_qty, 
               bts.timestamp, bts.created_at
        FROM book_ticker_snapshots bts
        JOIN symbols s ON bts.symbol_id = s.id
        JOIN exchanges e ON s.exchange_id = e.id
        WHERE e.enum_value = $1 
          AND s.symbol_base = $2
          AND s.symbol_quote = $3
          AND bts.timestamp >= $4
          AND bts.timestamp <= $5
        ORDER BY bts.timestamp ASC, bts.id ASC
        LIMIT $6
    """
    
    try:
        rows = await db.fetch(query, exchange_enum_value, symbol_base.upper(), symbol_quote.upper(), 
                             timestamp_from, timestamp_to, limit)
        
        snapshots = [
            BookTickerSnapshot(
                id=row['id'],
                symbol_id=row['symbol_id'],
                bid_price=float(row['bid_price']),
                bid_qty=float(row['bid_qty']),
                ask_price=float(row['ask_price']),
                ask_qty=float(row['ask_qty']),
                timestamp=row['timestamp'],
                created_at=row['created_at'],
                # Add transient fields for convenience
                exchange=row['exchange'],
                symbol_base=row['symbol_base'],
                symbol_quote=row['symbol_quote']
            )
            for row in rows
        ]
        
        logger.debug(f"Retrieved {len(snapshots)} book ticker snapshots for {exchange_enum_value} {symbol_base}/{symbol_quote}")
        return snapshots
        
    except Exception as e:
        logger.error(f"Failed to retrieve book ticker snapshots by exchange/symbol: {e}")
        raise


async def get_book_ticker_history(
    exchange: str,
    symbol: Symbol,
    hours_back: int = 24,
    sample_interval_minutes: int = 1
) -> List[BookTickerSnapshot]:
    """
    Get historical BookTicker data for a specific exchange/symbol using normalized schema.
    
    Args:
        exchange: Exchange identifier
        symbol: Symbol object
        hours_back: How many hours of history to retrieve
        sample_interval_minutes: Sampling interval in minutes (for downsampling)
        
    Returns:
        List of BookTickerSnapshot objects ordered by timestamp
    """
    db = get_db_manager()
    
    timestamp_from = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    
    # Use window function to sample data at intervals with normalized schema
    query = """
        SELECT sampled.id, sampled.symbol_id, sampled.bid_price, sampled.bid_qty,
               sampled.ask_price, sampled.ask_qty, sampled.timestamp, sampled.created_at
        FROM (
            SELECT bts.id, bts.symbol_id, bts.bid_price, bts.bid_qty,
                   bts.ask_price, bts.ask_qty, bts.timestamp, bts.created_at,
                   ROW_NUMBER() OVER (
                       PARTITION BY 
                           FLOOR(EXTRACT(EPOCH FROM bts.timestamp) / (60 * $4))
                       ORDER BY bts.timestamp DESC
                   ) as rn
            FROM book_ticker_snapshots bts
            JOIN symbols s ON bts.symbol_id = s.id
            JOIN exchanges e ON s.exchange_id = e.id
            WHERE e.enum_value = $1 
              AND s.symbol_base = $2 
              AND s.symbol_quote = $3
              AND bts.timestamp >= $5
        ) sampled
        WHERE sampled.rn = 1
        ORDER BY sampled.timestamp ASC
    """
    
    try:
        rows = await db.fetch(
            query,
            exchange.upper(),
            str(symbol.base).upper(),
            str(symbol.quote).upper(),
            sample_interval_minutes,
            timestamp_from
        )
        
        snapshots = [
            BookTickerSnapshot(
                id=row['id'],
                symbol_id=row['symbol_id'],
                bid_price=float(row['bid_price']),
                bid_qty=float(row['bid_qty']),
                ask_price=float(row['ask_price']),
                ask_qty=float(row['ask_qty']),
                timestamp=row['timestamp'],
                created_at=row['created_at']
            )
            for row in rows
        ]
        
        logger.debug(f"Retrieved {len(snapshots)} historical normalized book ticker snapshots for {exchange} {symbol.base}/{symbol.quote}")
        return snapshots
        
    except Exception as e:
        logger.error(f"Failed to retrieve book ticker history: {e}")
        raise


async def cleanup_old_snapshots(days_to_keep: int = 7) -> int:
    """
    Clean up old BookTicker snapshots to manage database size.
    
    Args:
        days_to_keep: Number of days of data to retain
        
    Returns:
        Number of records deleted
    """
    db = get_db_manager()
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
    
    query = """
        DELETE FROM book_ticker_snapshots
        WHERE created_at < $1
    """
    
    try:
        result = await db.execute(query, cutoff_date)
        count = int(result.split()[-1])  # Extract count from "DELETE N"
        
        logger.info(f"Cleaned up {count} old book ticker snapshots (older than {days_to_keep} days)")
        return count
        
    except Exception as e:
        logger.error(f"Failed to cleanup old snapshots: {e}")
        raise


async def get_database_stats() -> Dict[str, Any]:
    """
    Get database statistics for monitoring.
    
    Returns:
        Dictionary with database statistics
    """
    db = get_db_manager()
    
    queries = {
        'total_snapshots': "SELECT COUNT(*) FROM book_ticker_snapshots",
        'exchanges': """
            SELECT COUNT(DISTINCT e.enum_value) 
            FROM book_ticker_snapshots bts
            JOIN symbols s ON bts.symbol_id = s.id
            JOIN exchanges e ON s.exchange_id = e.id
        """,
        'symbols': """
            SELECT COUNT(DISTINCT s.symbol_base || '/' || s.symbol_quote) 
            FROM book_ticker_snapshots bts
            JOIN symbols s ON bts.symbol_id = s.id
        """,
        'latest_timestamp': "SELECT MAX(timestamp) FROM book_ticker_snapshots",
        'oldest_timestamp': "SELECT MIN(timestamp) FROM book_ticker_snapshots",
        'table_size': """
            SELECT pg_size_pretty(pg_total_relation_size('book_ticker_snapshots')) as size
        """
    }
    
    stats = {}
    
    try:
        for key, query in queries.items():
            result = await db.fetchval(query)
            stats[key] = result
        
        # Add connection pool stats
        stats['connection_pool'] = await db.get_connection_stats()
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to retrieve database stats: {e}")
        return {}


# Trade Operations
# Similar pattern to BookTicker operations but for trade data

# Global deduplication cache for trade timestamps
_trade_timestamp_cache: Dict[tuple, Set] = defaultdict(set)


def _is_duplicate_trade_timestamp(symbol_id: int, timestamp: datetime, trade_id: str) -> bool:
    """
    Check if this trade timestamp/ID has been seen recently for this symbol_id.
    
    Returns:
        True if this is a duplicate trade that should be skipped
    """
    key = (symbol_id,)
    trade_key = (timestamp, trade_id) if trade_id else timestamp
    
    # Check if we've seen this exact trade recently
    if trade_key in _trade_timestamp_cache[key]:
        return True
    
    # Add to cache for future checks
    _trade_timestamp_cache[key].add(trade_key)
    return False


def _cleanup_trade_timestamp_cache():
    """
    Clean up old entries from the trade timestamp cache.
    """
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    total_removed = 0
    
    for key in list(_trade_timestamp_cache.keys()):
        trade_set = _trade_timestamp_cache[key]
        old_size = len(trade_set)
        
        # Remove old trade entries
        new_set = set()
        for item in trade_set:
            if isinstance(item, tuple) and len(item) == 2:
                timestamp, trade_id = item
                if timestamp > cutoff_time:
                    new_set.add(item)
            elif isinstance(item, datetime) and item > cutoff_time:
                new_set.add(item)
        
        _trade_timestamp_cache[key] = new_set
        
        # Remove empty entries
        if not new_set:
            del _trade_timestamp_cache[key]
        
        total_removed += old_size - len(new_set)
    
    if total_removed > 0:
        logger.debug(f"Cleaned {total_removed} old trade timestamps from cache")


async def insert_trade_snapshot(snapshot: TradeSnapshot) -> int:
    """
    Insert a single Trade snapshot.
    
    Args:
        snapshot: TradeSnapshot to insert
        
    Returns:
        Database ID of inserted record
        
    Raises:
        DatabaseError: If insert fails
    """
    db = get_db_manager()
    
    query = """
        INSERT INTO trade_snapshots (
            symbol_id, price, quantity, side, trade_id, timestamp,
            quote_quantity, is_buyer, is_maker, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING id
    """
    
    try:
        record_id = await db.fetchval(
            query,
            snapshot.symbol_id,
            snapshot.price,
            snapshot.quantity,
            snapshot.side,
            snapshot.trade_id,
            snapshot.timestamp,
            snapshot.quote_quantity,
            snapshot.is_buyer,
            snapshot.is_maker,
            snapshot.created_at or datetime.now(timezone.utc)
        )
        
        logger.debug(f"Inserted trade snapshot {record_id} for symbol_id {snapshot.symbol_id}")
        return record_id
        
    except Exception as e:
        logger.error(f"Failed to insert trade snapshot: {e}")
        raise


async def insert_funding_rate_snapshots_batch(snapshots: List[FundingRateSnapshot]) -> int:
    """
    Insert funding rate snapshots in batch for optimal performance.
    
    Args:
        snapshots: List of FundingRateSnapshot objects
        
    Returns:
        Number of records inserted/updated
    """
    if not snapshots:
        return 0
        
    db = get_db_manager()
    
    # Prepare batch insert with ON CONFLICT handling
    query = """
    INSERT INTO funding_rate_snapshots (
        timestamp, symbol_id, funding_rate, funding_time, next_funding_time, created_at
    ) VALUES ($1, $2, $3, $4, $5, $6)
    ON CONFLICT (timestamp, symbol_id) 
    DO UPDATE SET
        funding_rate = EXCLUDED.funding_rate,
        funding_time = EXCLUDED.funding_time,
        next_funding_time = EXCLUDED.next_funding_time,
        created_at = EXCLUDED.created_at
    """
    
    # Prepare data for batch insert
    batch_data = []
    for snapshot in snapshots:
        # Validate next_funding_time to prevent constraint violations
        funding_time = snapshot.next_funding_time
        
        # Handle both datetime and int types for funding_time
        if funding_time is None:
            # Generate a valid funding_time (current time + 8 hours in milliseconds)
            import time
            funding_time = int(time.time() * 1000) + (8 * 60 * 60 * 1000)
            logger.warning(f"Invalid next_funding_time (None) for symbol_id {snapshot.symbol_id}, using fallback: {funding_time}")
        elif isinstance(funding_time, datetime):
            # Convert datetime to Unix timestamp in milliseconds
            funding_time = int(funding_time.timestamp() * 1000)
        elif isinstance(funding_time, (int, float)) and funding_time <= 0:
            # Generate a valid funding_time for invalid numeric values
            import time
            funding_time = int(time.time() * 1000) + (8 * 60 * 60 * 1000)
            logger.warning(f"Invalid next_funding_time ({snapshot.next_funding_time}) for symbol_id {snapshot.symbol_id}, using fallback: {funding_time}")
        elif isinstance(funding_time, (int, float)):
            # Ensure it's an integer
            funding_time = int(funding_time)
        
        batch_data.append((
            snapshot.timestamp,
            snapshot.symbol_id,
            float(snapshot.funding_rate),  # Float-only policy
            funding_time,                  # Already converted to int above
            funding_time,                  # Use same value for next_funding_time field
            snapshot.created_at or datetime.now(timezone.utc)
        ))
    
    try:
        # Execute batch insert
        await db.executemany(query, batch_data)
        
        logger.debug(f"Successfully inserted/updated {len(snapshots)} funding rate snapshots")
        return len(snapshots)
        
    except Exception as e:
        logger.error(f"Failed to insert funding rate snapshots: {e}")
        raise


async def insert_trade_snapshots_batch(snapshots: List[TradeSnapshot]) -> int:
    """
    Insert multiple Trade snapshots efficiently with deduplication.
    
    Args:
        snapshots: List of TradeSnapshot objects
        
    Returns:
        Number of records inserted
        
    Raises:
        DatabaseError: If batch insert fails
    """
    if not snapshots:
        return 0
    
    # Clean up cache periodically
    _cleanup_trade_timestamp_cache()
    
    # Filter out known duplicate trades using cache
    filtered_snapshots = []
    cache_hits = 0
    
    for snapshot in snapshots:
        if not _is_duplicate_trade_timestamp(
            snapshot.symbol_id, snapshot.timestamp, snapshot.trade_id or ""
        ):
            filtered_snapshots.append(snapshot)
        else:
            cache_hits += 1
    
    if cache_hits > 0:
        logger.debug(f"Cache filtered {cache_hits} duplicate trades")
    
    if not filtered_snapshots:
        return 0
    
    # Deduplicate remaining snapshots in memory
    unique_snapshots = {}
    for snapshot in filtered_snapshots:
        # Use both timestamp and trade_id for deduplication
        key = (snapshot.symbol_id, snapshot.timestamp, snapshot.trade_id)
        unique_snapshots[key] = snapshot
    
    deduplicated_snapshots = list(unique_snapshots.values())
    
    if not deduplicated_snapshots:
        return 0
    
    if len(snapshots) != len(deduplicated_snapshots):
        logger.debug(
            f"Trade deduplication: {len(snapshots)} -> {len(deduplicated_snapshots)} trades "
            f"(cache: {cache_hits}, memory: {len(filtered_snapshots) - len(deduplicated_snapshots)})"
        )
    
    db = get_db_manager()
    count = 0
    
    # Simple INSERT without ON CONFLICT - let duplicates be handled by deduplication logic above
    query = """
        INSERT INTO trade_snapshots (
            symbol_id, price, quantity, side, trade_id, timestamp,
            quote_quantity, is_buyer, is_maker, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    """
    
    try:
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                for snapshot in deduplicated_snapshots:
                    await conn.execute(
                        query,
                        snapshot.symbol_id,
                        snapshot.price,
                        snapshot.quantity,
                        snapshot.side,
                        snapshot.trade_id,
                        snapshot.timestamp,
                        snapshot.quote_quantity,
                        snapshot.is_buyer,
                        snapshot.is_maker,
                        snapshot.created_at or datetime.now(timezone.utc)
                    )
                    count += 1
        
        logger.debug(f"Batch inserted {count} trade snapshots")
        return count
        
    except Exception as e:
        logger.error(f"Failed in trade batch insert: {e}")
        logger.error(f"Error details: {type(e).__name__}: {str(e)}")
        if deduplicated_snapshots:
            sample = deduplicated_snapshots[0]
            logger.error(f"Sample snapshot data - symbol_id: {sample.symbol_id}, trade_id: {sample.trade_id}, timestamp: {sample.timestamp}")
        logger.error(f"Attempting to insert {len(deduplicated_snapshots)} trade snapshots")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise




async def get_recent_trades(
    exchange: str,
    symbol: Symbol,
    minutes_back: int = 60
) -> List[TradeSnapshot]:
    """
    Get recent trades for a specific exchange/symbol.
    
    Args:
        exchange: Exchange identifier
        symbol: Symbol object
        minutes_back: How many minutes of recent trades to retrieve
        
    Returns:
        List of TradeSnapshot objects ordered by timestamp DESC
    """
    db = get_db_manager()
    timestamp_from = datetime.now(timezone.utc) - timedelta(minutes=minutes_back)
    
    query = """
        SELECT ts.id, ts.symbol_id, ts.price, ts.quantity, ts.side,
               ts.trade_id, ts.timestamp, ts.created_at, ts.quote_quantity, 
               ts.is_buyer, ts.is_maker
        FROM trade_snapshots ts
        JOIN symbols s ON ts.symbol_id = s.id
        JOIN exchanges e ON s.exchange_id = e.id
        WHERE e.enum_value = $1 AND s.symbol_base = $2 AND s.symbol_quote = $3 AND ts.timestamp >= $4
        ORDER BY ts.timestamp DESC, ts.id DESC
        LIMIT 10000
    """
    
    try:
        rows = await db.fetch(query, exchange.upper(), str(symbol.base).upper(), str(symbol.quote).upper(), timestamp_from)
        
        snapshots = []
        for row in rows:
            snapshot = TradeSnapshot(
                id=row['id'],
                symbol_id=row['symbol_id'],
                price=float(row['price']),
                quantity=float(row['quantity']),
                side=row['side'],
                trade_id=row['trade_id'],
                timestamp=row['timestamp'],
                created_at=row['created_at'],
                quote_quantity=float(row['quote_quantity']) if row['quote_quantity'] else None,
                is_buyer=row['is_buyer'],
                is_maker=row['is_maker']
            )
            snapshots.append(snapshot)
        
        logger.debug(f"Retrieved {len(snapshots)} recent trade snapshots")
        return snapshots
        
    except Exception as e:
        logger.error(f"Failed to retrieve recent trades: {e}")
        raise


async def get_trade_database_stats() -> Dict[str, Any]:
    """
    Get trade database statistics for monitoring.
    
    Returns:
        Dictionary with trade database statistics
    """
    db = get_db_manager()
    
    queries = {
        'total_trades': "SELECT COUNT(*) FROM trade_snapshots",
        'exchanges': "SELECT COUNT(DISTINCT e.enum_value) FROM trade_snapshots ts JOIN symbols s ON ts.symbol_id = s.id JOIN exchanges e ON s.exchange_id = e.id",
        'symbols': "SELECT COUNT(DISTINCT CONCAT(s.symbol_base, '_', s.symbol_quote)) FROM trade_snapshots ts JOIN symbols s ON ts.symbol_id = s.id",
        'latest_timestamp': "SELECT MAX(timestamp) FROM trade_snapshots",
        'oldest_timestamp': "SELECT MIN(timestamp) FROM trade_snapshots",
        'table_size': """
            SELECT pg_size_pretty(pg_total_relation_size('trade_snapshots')) as size
        """,
        'avg_trades_per_minute': """
            SELECT AVG(trade_count) FROM (
                SELECT COUNT(*) as trade_count
                FROM trade_snapshots 
                WHERE timestamp > NOW() - INTERVAL '1 hour'
                GROUP BY DATE_TRUNC('minute', timestamp)
            ) minute_counts
        """
    }
    
    stats = {}
    
    try:
        for key, query in queries.items():
            result = await db.fetchval(query)
            stats[key] = result
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to retrieve trade database stats: {e}")
        return {}


# =============================================================================
# BALANCE OPERATIONS (HFT-OPTIMIZED)
# =============================================================================

async def insert_balance_snapshots_batch(snapshots: List[BalanceSnapshot]) -> int:
    """
    Insert balance snapshots in batch for optimal performance.
    
    Uses ON CONFLICT handling and follows HFT performance requirements.
    Target: <5ms per batch (up to 100 snapshots).
    
    Args:
        snapshots: List of BalanceSnapshot objects
        
    Returns:
        Number of records inserted/updated
    """
    if not snapshots:
        return 0
        
    db = get_db_manager()
    
    # Prepare batch insert with ON CONFLICT handling
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
        interest_balance = EXCLUDED.interest_balance,
        created_at = EXCLUDED.created_at
    """
    
    # Prepare data for batch insert using float values
    batch_data = []
    for snapshot in snapshots:
        batch_data.append((
            snapshot.timestamp,
            snapshot.exchange_id,
            snapshot.asset_name.upper(),
            float(snapshot.available_balance),
            float(snapshot.locked_balance),
            float(snapshot.frozen_balance or 0.0),
            float(snapshot.borrowing_balance or 0.0),
            float(snapshot.interest_balance or 0.0),
            snapshot.created_at or datetime.now(timezone.utc)
        ))
    
    try:
        # Execute batch insert (HFT optimized)
        await db.executemany(query, batch_data)
        
        logger.debug(f"Successfully inserted/updated {len(snapshots)} balance snapshots")
        return len(snapshots)
        
    except Exception as e:
        logger.error(f"Failed to insert balance snapshots: {e}")
        raise


async def get_latest_balance_snapshots(
    exchange_name: Optional[str] = None,
    asset_name: Optional[str] = None
) -> Dict[str, BalanceSnapshot]:
    """
    Get latest balance snapshot for each exchange/asset combination.
    
    Target: <3ms per exchange/asset combination.
    
    Args:
        exchange_name: Filter by exchange (optional)
        asset_name: Filter by asset (optional)
        
    Returns:
        Dictionary mapping "exchange_asset" to latest BalanceSnapshot
    """
    db = get_db_manager()
    
    # Build dynamic WHERE clause
    where_conditions = []
    params = []
    param_counter = 1
    
    if exchange_name:
        where_conditions.append(f"e.enum_value = ${param_counter}")
        params.append(exchange_name.upper())
        param_counter += 1
    
    if asset_name:
        where_conditions.append(f"bs.asset_name = ${param_counter}")
        params.append(asset_name.upper())
        param_counter += 1
    
    where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
    
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
    
    try:
        rows = await db.fetch(query, *params)
        
        latest_balances = {}
        for row in rows:
            snapshot = BalanceSnapshot(
                id=row['id'],
                exchange_id=row['exchange_id'],
                asset_name=row['asset_name'],
                available_balance=float(row['available_balance']),
                locked_balance=float(row['locked_balance']),
                frozen_balance=float(row['frozen_balance']) if row['frozen_balance'] else None,
                borrowing_balance=float(row['borrowing_balance']) if row['borrowing_balance'] else None,
                interest_balance=float(row['interest_balance']) if row['interest_balance'] else None,
                timestamp=row['timestamp'],
                created_at=row['created_at']
            )
            
            key = f"{row['exchange_name']}_{snapshot.asset_name}"
            latest_balances[key] = snapshot
        
        logger.debug(f"Retrieved {len(latest_balances)} latest balance snapshots")
        return latest_balances
        
    except Exception as e:
        logger.error(f"Failed to retrieve latest balance snapshots: {e}")
        raise


async def get_balance_history(
    exchange_name: str,
    asset_name: str,
    hours_back: int = 24
) -> List[BalanceSnapshot]:
    """
    Get historical balance data for a specific exchange/asset.
    
    Target: <10ms for 24 hours of data.
    
    Args:
        exchange_name: Exchange identifier
        asset_name: Asset symbol
        hours_back: How many hours of history to retrieve
        
    Returns:
        List of BalanceSnapshot objects ordered by timestamp
    """
    db = get_db_manager()
    
    timestamp_from = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    
    query = """
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
    """
    
    try:
        rows = await db.fetch(
            query,
            exchange_name.upper(),
            asset_name.upper(),
            timestamp_from
        )
        
        snapshots = []
        for row in rows:
            snapshot = BalanceSnapshot(
                id=row['id'],
                exchange_id=row['exchange_id'],
                asset_name=row['asset_name'],
                available_balance=float(row['available_balance']),
                locked_balance=float(row['locked_balance']),
                frozen_balance=float(row['frozen_balance']) if row['frozen_balance'] else None,
                borrowing_balance=float(row['borrowing_balance']) if row['borrowing_balance'] else None,
                interest_balance=float(row['interest_balance']) if row['interest_balance'] else None,
                timestamp=row['timestamp'],
                created_at=row['created_at']
            )
            snapshots.append(snapshot)
        
        logger.debug(f"Retrieved {len(snapshots)} historical balance snapshots for {exchange_name} {asset_name}")
        return snapshots
        
    except Exception as e:
        logger.error(f"Failed to retrieve balance history: {e}")
        raise


async def get_active_balances(
    exchange_name: Optional[str] = None,
    min_total_balance: float = 0.001
) -> List[BalanceSnapshot]:
    """
    Get active balances (non-zero) across exchanges.
    
    Args:
        exchange_name: Filter by exchange (optional)
        min_total_balance: Minimum total balance threshold
        
    Returns:
        List of BalanceSnapshot objects with non-zero balances
    """
    db = get_db_manager()
    
    where_conditions = ["bs.total_balance > $1"]
    params = [min_total_balance]
    param_counter = 2
    
    if exchange_name:
        where_conditions.append(f"e.enum_value = ${param_counter}")
        params.append(exchange_name.upper())
        param_counter += 1
    
    where_clause = " AND ".join(where_conditions)
    
    query = f"""
        SELECT DISTINCT ON (bs.exchange_id, bs.asset_name)
               bs.id, bs.exchange_id, bs.asset_name,
               bs.available_balance, bs.locked_balance, bs.frozen_balance,
               bs.borrowing_balance, bs.interest_balance,
               bs.timestamp, bs.created_at,
               e.enum_value as exchange_name
        FROM balance_snapshots bs
        JOIN exchanges e ON bs.exchange_id = e.id
        WHERE {where_clause}
        ORDER BY bs.exchange_id, bs.asset_name, bs.timestamp DESC
    """
    
    try:
        rows = await db.fetch(query, *params)
        
        active_balances = []
        for row in rows:
            snapshot = BalanceSnapshot(
                id=row['id'],
                exchange_id=row['exchange_id'],
                asset_name=row['asset_name'],
                available_balance=float(row['available_balance']),
                locked_balance=float(row['locked_balance']),
                frozen_balance=float(row['frozen_balance']) if row['frozen_balance'] else None,
                borrowing_balance=float(row['borrowing_balance']) if row['borrowing_balance'] else None,
                interest_balance=float(row['interest_balance']) if row['interest_balance'] else None,
                timestamp=row['timestamp'],
                created_at=row['created_at']
            )
            active_balances.append(snapshot)
        
        logger.debug(f"Retrieved {len(active_balances)} active balance snapshots")
        return active_balances
        
    except Exception as e:
        logger.error(f"Failed to retrieve active balances: {e}")
        raise


async def get_balance_database_stats() -> Dict[str, Any]:
    """
    Get balance database statistics for monitoring.
    
    Returns:
        Dictionary with balance database statistics
    """
    db = get_db_manager()
    
    try:
        query = """
            SELECT 
                COUNT(*) as total_snapshots,
                COUNT(DISTINCT exchange_id) as unique_exchanges,
                COUNT(DISTINCT asset_name) as unique_assets,
                MIN(timestamp) as earliest_timestamp,
                MAX(timestamp) as latest_timestamp
            FROM balance_snapshots
        """
        
        row = await db.fetchrow(query)
        
        return {
            "total_snapshots": row["total_snapshots"],
            "unique_exchanges": row["unique_exchanges"],
            "unique_assets": row["unique_assets"],
            "earliest_timestamp": row["earliest_timestamp"],
            "latest_timestamp": row["latest_timestamp"]
        }
        
    except Exception as e:
        logger.error(f"Failed to retrieve balance database stats: {e}")
        return {}


# =============================================================================
# EXCHANGE OPERATIONS (NORMALIZED SCHEMA)
# =============================================================================

async def get_exchange_by_enum(exchange_enum_or_str) -> Optional[Exchange]:
    """
    Get exchange by ExchangeEnum value or string.
    
    Args:
        exchange_enum_or_str: ExchangeEnum value or string (e.g., "MEXC_SPOT", "TEST_SPOT")
        
    Returns:
        Exchange instance or None if not found
    """
    from exchanges.structs.enums import ExchangeEnum
    
    # Handle both ExchangeEnum and string inputs
    if isinstance(exchange_enum_or_str, ExchangeEnum):
        enum_value = str(exchange_enum_or_str.value)
    elif isinstance(exchange_enum_or_str, str):
        enum_value = exchange_enum_or_str
    else:
        # Try to convert to string as fallback
        enum_value = str(exchange_enum_or_str)
    
    db = get_db_manager()
    
    query = """
        SELECT id, exchange_name, enum_value, market_type
        FROM exchanges 
        WHERE enum_value = $1     """
    
    try:
        row = await db.fetchrow(query, enum_value)
        
        if row:
            return Exchange(
                name=row['exchange_name'],
                enum_value=row['enum_value'],
                display_name=row['exchange_name'],  # Use exchange_name as display_name
                market_type=row['market_type'],
                id=row['id']
            )
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to get exchange by enum {exchange_enum_or_str}: {e}")
        raise


async def get_exchange_by_id(exchange_id: int) -> Optional[Exchange]:
    """
    Get exchange by database ID.
    
    Args:
        exchange_id: Database primary key
        
    Returns:
        Exchange instance or None if not found
    """
    db = get_db_manager()
    
    query = """
        SELECT id, exchange_name, enum_value, market_type
        FROM exchanges 
        WHERE id = $1
    """
    
    try:
        row = await db.fetchrow(query, exchange_id)
        
        if row:
            return Exchange(
                name=row['exchange_name'],
                enum_value=row['enum_value'],
                display_name=row['exchange_name'],  # Use exchange_name as display_name
                market_type=row['market_type'],
                id=row['id']
            )
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to get exchange by id {exchange_id}: {e}")
        raise


async def get_all_active_exchanges() -> List[Exchange]:
    """
    Get all active exchanges.
    
    Returns:
        List of active Exchange instances
    """
    db = get_db_manager()
    
    query = """
        SELECT id, exchange_name, enum_value, market_type
        FROM exchanges 
                ORDER BY exchange_name
    """
    
    try:
        rows = await db.fetch(query)
        
        exchanges = []
        for row in rows:
            exchange = Exchange(
                name=row['exchange_name'],
                enum_value=row['enum_value'],
                display_name=row['exchange_name'],  # Use exchange_name as display_name
                market_type=row['market_type'],
                id=row['id']
            )
            exchanges.append(exchange)
        
        logger.debug(f"Retrieved {len(exchanges)} active exchanges")
        return exchanges
        
    except Exception as e:
        logger.error(f"Failed to get active exchanges: {e}")
        raise


async def get_exchanges_by_market_type(market_type: str) -> List[Exchange]:
    """
    Get exchanges filtered by market type.
    
    Args:
        market_type: Market type filter (SPOT, FUTURES, OPTIONS)
        
    Returns:
        List of Exchange instances for the market type
    """
    db = get_db_manager()
    
    query = """
        SELECT id, exchange_name, enum_value, market_type
        FROM exchanges 
        WHERE market_type = $1         ORDER BY exchange_name
    """
    
    try:
        rows = await db.fetch(query, market_type.upper())
        
        exchanges = []
        for row in rows:
            exchange = Exchange(
                name=row['exchange_name'],
                enum_value=row['enum_value'],
                display_name=row['exchange_name'],  # Use exchange_name as display_name
                market_type=row['market_type'],
                id=row['id']
            )
            exchanges.append(exchange)
        
        logger.debug(f"Retrieved {len(exchanges)} {market_type} exchanges")
        return exchanges
        
    except Exception as e:
        logger.error(f"Failed to get {market_type} exchanges: {e}")
        raise


# Exchange CRUD Operations
# Complete Create, Read, Update, Delete operations for Exchange management

async def insert_exchange(exchange: Exchange) -> int:
    """
    Insert a new exchange record.
    
    Args:
        exchange: Exchange instance to insert
        
    Returns:
        Database ID of inserted exchange
        
    Raises:
        ValueError: If exchange data is invalid
        DatabaseError: If insert fails
    """
    db = get_db_manager()
    
    # Validate required fields
    if not exchange.name or not exchange.enum_value:
        raise ValueError("Exchange name and enum_value are required")
    
    query = """
        INSERT INTO exchanges (
            exchange_name, enum_value, market_type
        ) VALUES ($1, $2, $3)
        RETURNING id
    """
    
    try:
        exchange_id = await db.fetchval(
            query,
            exchange.name,
            exchange.enum_value,
            exchange.market_type
        )
        
        logger.info(f"Inserted exchange {exchange.name} with ID {exchange_id}")
        return exchange_id
        
    except Exception as e:
        logger.error(f"Failed to insert exchange {exchange.name}: {e}")
        raise


async def update_exchange(exchange_id: int, updates: Dict[str, Any]) -> bool:
    """
    Update exchange record with provided fields.
    
    Args:
        exchange_id: Exchange ID to update
        updates: Dictionary of field updates
        
    Returns:
        True if update successful, False if exchange not found
        
    Raises:
        DatabaseError: If update fails
    """
    db = get_db_manager()
    
    if not updates:
        return True  # No updates needed
    
    # Build dynamic update query
    set_clauses = []
    params = []
    param_counter = 1
    
    for field, value in updates.items():
        set_clauses.append(f"{field} = ${param_counter}")
        params.append(value)
        param_counter += 1
    
    # Always update the updated_at timestamp
    set_clauses.append(f"updated_at = ${param_counter}")
    params.append(datetime.now(timezone.utc))
    param_counter += 1
    
    # Add WHERE clause parameter
    params.append(exchange_id)
    
    query = f"""
        UPDATE exchanges 
        SET {', '.join(set_clauses)}
        WHERE id = ${param_counter}
    """
    
    try:
        result = await db.execute(query, *params)
        
        # Check if any rows were updated
        updated = result.endswith('1')  # UPDATE command returns "UPDATE n"
        
        if updated:
            logger.info(f"Updated exchange {exchange_id} with fields: {list(updates.keys())}")
        else:
            logger.warning(f"No exchange found with ID {exchange_id}")
        
        return updated
        
    except Exception as e:
        logger.error(f"Failed to update exchange {exchange_id}: {e}")
        raise


async def deactivate_exchange(exchange_id: int) -> bool:
    """
    Deactivate an exchange (soft delete).
    
    Args:
        exchange_id: Exchange ID to deactivate
        
    Returns:
        True if deactivation successful, False if exchange not found
    """
    return await update_exchange(exchange_id, {'is_active': False})


async def activate_exchange(exchange_id: int) -> bool:
    """
    Reactivate an exchange.
    
    Args:
        exchange_id: Exchange ID to activate
        
    Returns:
        True if activation successful, False if exchange not found
    """
    return await update_exchange(exchange_id, {'is_active': True})


async def get_exchange_stats() -> Dict[str, Any]:
    """
    Get exchange statistics for monitoring.
    
    Returns:
        Dictionary with exchange statistics
    """
    db = get_db_manager()
    
    try:
        query = """
            SELECT 
                COUNT(*) as total_exchanges,
                COUNT(*) FILTER (WHERE is_active = true) as active_exchanges,
                COUNT(*) FILTER (WHERE market_type = 'SPOT') as spot_exchanges,
                COUNT(*) FILTER (WHERE market_type = 'FUTURES') as futures_exchanges
            FROM exchanges
        """
        
        row = await db.fetchrow(query)
        
        return {
            "total_exchanges": row["total_exchanges"],
            "active_exchanges": row["active_exchanges"],
            "spot_exchanges": row["spot_exchanges"],
            "futures_exchanges": row["futures_exchanges"]
        }
        
    except Exception as e:
        logger.error(f"Failed to retrieve exchange stats: {e}")
        return {}


async def ensure_exchanges_populated() -> None:
    """
    Ensure all ExchangeEnum values are present in the database.
    Creates missing exchanges with default configurations.
    """
    from exchanges.structs.enums import ExchangeEnum
    
    db = get_db_manager()
    
    # Get existing exchanges
    existing_exchanges = await get_all_active_exchanges()
    existing_enum_values = {ex.enum_value for ex in existing_exchanges}
    
    # Check each ExchangeEnum value
    for exchange_enum in ExchangeEnum:
        enum_value = str(exchange_enum.value)
        
        if enum_value not in existing_enum_values:
            logger.info(f"Creating missing exchange for {enum_value}")
            
            # Create exchange with defaults
            exchange = Exchange.from_exchange_enum(exchange_enum)
            await insert_exchange(exchange)


# ================================================================================================
# Symbol Operations
# High-performance symbol lookup and management for HFT operations
# ================================================================================================

async def get_symbol_by_id(symbol_id: int) -> Optional[DBSymbol]:
    """
    Get symbol by database ID.
    
    Args:
        symbol_id: Symbol database ID
        
    Returns:
        Symbol instance or None if not found
    """
    db = get_db_manager()
    
    query = """
        SELECT id, exchange_id, symbol_base, symbol_quote, exchange_symbol,
               is_active, symbol_type
        FROM symbols
        WHERE id = $1
    """
    
    try:
        row = await db.fetchrow(query, symbol_id)
        
        if not row:
            return None
        
        return DBSymbol(
            id=row['id'],
            exchange_id=row['exchange_id'],
            symbol_base=row['symbol_base'],
            symbol_quote=row['symbol_quote'],
            exchange_symbol=row['exchange_symbol'],
            is_active=row['is_active'],
            symbol_type=SymbolType[row['symbol_type']]  # Convert string to SymbolType enum
        )
        
    except Exception as e:
        logger.error(f"Failed to get symbol by ID {symbol_id}: {e}")
        raise


async def get_symbol_by_exchange_and_pair(
    exchange_id: int, 
    symbol_base: str, 
    symbol_quote: str
) -> Optional[DBSymbol]:
    """
    Get symbol by exchange ID and base/quote pair.
    
    Args:
        exchange_id: Exchange database ID
        symbol_base: Base asset (e.g., 'BTC')
        symbol_quote: Quote asset (e.g., 'USDT')
        
    Returns:
        Symbol instance or None if not found
    """
    db = get_db_manager()
    
    query = """
        SELECT id, exchange_id, symbol_base, symbol_quote, exchange_symbol,
               is_active, symbol_type
        FROM symbols
        WHERE exchange_id = $1 
          AND symbol_base = $2 
          AND symbol_quote = $3
              """
    
    try:
        row = await db.fetchrow(query, exchange_id, symbol_base.upper(), symbol_quote.upper())
        
        if not row:
            return None
        
        return DBSymbol(
            id=row['id'],
            exchange_id=row['exchange_id'],
            symbol_base=row['symbol_base'],
            symbol_quote=row['symbol_quote'],
            exchange_symbol=row['exchange_symbol'],
            is_active=row['is_active'],
            symbol_type=SymbolType[row['symbol_type']]  # Convert string to SymbolType enum
        )
        
    except Exception as e:
        logger.error(f"Failed to get symbol for exchange {exchange_id}, {symbol_base}/{symbol_quote}: {e}")
        raise


async def get_symbols_by_exchange(exchange_id: int, active_only: bool = True) -> List[DBSymbol]:
    """
    Get all symbols for a specific exchange.
    
    Args:
        exchange_id: Exchange database ID
        active_only: Only return active symbols
        
    Returns:
        List of Symbol instances
    """
    db = get_db_manager()
    
    base_query = """
        SELECT id, exchange_id, symbol_base, symbol_quote, exchange_symbol,
               is_active, symbol_type
        FROM symbols
        WHERE exchange_id = $1
    """
    
    if active_only:
        query = base_query + " AND is_active = true"
    else:
        query = base_query
    
    query += " ORDER BY symbol_base, symbol_quote"
    
    try:
        rows = await db.fetch(query, exchange_id)
        
        symbols = [
            DBSymbol(
                id=row['id'],
                exchange_id=row['exchange_id'],
                symbol_base=row['symbol_base'],
                symbol_quote=row['symbol_quote'],
                exchange_symbol=row['exchange_symbol'],
                is_active=row['is_active'],
                symbol_type=SymbolType[row['symbol_type']]  # Convert string to SymbolType enum
            )
            for row in rows
        ]
        
        logger.debug(f"Retrieved {len(symbols)} symbols for exchange {exchange_id}")
        return symbols
        
    except Exception as e:
        logger.error(f"Failed to get symbols for exchange {exchange_id}: {e}")
        raise


async def get_all_active_symbols() -> List[DBSymbol]:
    """
    Get all active symbols across all exchanges.
    
    Returns:
        List of active Symbol instances
    """
    db = get_db_manager()
    
    query = """
        SELECT s.id, s.exchange_id, s.symbol_base, s.symbol_quote, s.exchange_symbol,
               s.is_active, s.symbol_type
        FROM symbols s
        JOIN exchanges e ON s.exchange_id = e.id
        WHERE s.is_active = true
        ORDER BY e.exchange_name, s.symbol_base, s.symbol_quote
    """
    
    try:
        rows = await db.fetch(query)
        
        symbols = [
            DBSymbol(
                id=row['id'],
                exchange_id=row['exchange_id'],
                symbol_base=row['symbol_base'],
                symbol_quote=row['symbol_quote'],
                exchange_symbol=row['exchange_symbol'],
                is_active=row['is_active'],
                symbol_type=SymbolType[row['symbol_type']]  # Convert string to SymbolType enum
            )
            for row in rows
        ]
        
        logger.debug(f"Retrieved {len(symbols)} active symbols")
        return symbols
        
    except Exception as e:
        logger.error(f"Failed to get all active symbols: {e}")
        raise


async def get_symbols_by_market_type(market_type: str, active_only: bool = True) -> List[DBSymbol]:
    """
    Get symbols filtered by market type (SPOT/FUTURES).
    
    Args:
        market_type: 'SPOT' or 'FUTURES'
        active_only: Only return active symbols
        
    Returns:
        List of Symbol instances
    """
    db = get_db_manager()
    
    base_query = """
        SELECT s.id, s.exchange_id, s.symbol_base, s.symbol_quote, s.exchange_symbol,
               s.is_active, s.symbol_type
        FROM symbols s
        JOIN exchanges e ON s.exchange_id = e.id
        WHERE e.market_type = $1
    """
    
    conditions = []
    if active_only:
        conditions.append("s.is_active = true")
    
    if conditions:
        base_query += " AND " + " AND ".join(conditions)
    
    query = base_query + " ORDER BY e.exchange_name, s.symbol_base, s.symbol_quote"
    
    try:
        rows = await db.fetch(query, market_type.upper())
        
        symbols = [
            DBSymbol(
                id=row['id'],
                exchange_id=row['exchange_id'],
                symbol_base=row['symbol_base'],
                symbol_quote=row['symbol_quote'],
                exchange_symbol=row['exchange_symbol'],
                is_active=row['is_active'],
                symbol_type=SymbolType[row['symbol_type']]  # Convert string to SymbolType enum
            )
            for row in rows
        ]
        
        logger.debug(f"Retrieved {len(symbols)} {market_type} symbols")
        return symbols
        
    except Exception as e:
        logger.error(f"Failed to get {market_type} symbols: {e}")
        raise


# ================================================================================================
# Symbol CRUD Operations
# Complete Create, Read, Update, Delete operations for Symbol management
# ================================================================================================

async def insert_symbol(symbol: DBSymbol) -> int:
    """
    Insert a new symbol record.
    
    Args:
        symbol: Symbol instance to insert
        
    Returns:
        Database ID of inserted symbol
        
    Raises:
        ValueError: If symbol data is invalid
        DatabaseError: If insert fails
    """
    db = get_db_manager()
    
    # Validate required fields
    if not symbol.exchange_id or not symbol.symbol_base or not symbol.symbol_quote:
        raise ValueError("Symbol exchange_id, symbol_base, and symbol_quote are required")
    
    query = """
        INSERT INTO symbols (
            exchange_id, symbol_base, symbol_quote, exchange_symbol, is_active, symbol_type
        ) VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
    """
    
    try:
        symbol_id = await db.fetchval(
            query,
            symbol.exchange_id,
            symbol.symbol_base.upper(),
            symbol.symbol_quote.upper(),
            symbol.exchange_symbol,
            symbol.is_active,
            symbol.symbol_type.name  # Convert SymbolType enum to string
        )
        
        logger.info(f"Inserted symbol {symbol.symbol_base}/{symbol.symbol_quote} for exchange {symbol.exchange_id} with ID {symbol_id}")
        return symbol_id
        
    except Exception as e:
        logger.error(f"Failed to insert symbol {symbol.symbol_base}/{symbol.symbol_quote}: {e}")
        raise


async def update_symbol(symbol_id: int, updates: Dict[str, Any]) -> bool:
    """
    Update symbol record with provided fields.
    
    Args:
        symbol_id: Symbol ID to update
        updates: Dictionary of field updates
        
    Returns:
        True if update successful, False if symbol not found
        
    Raises:
        DatabaseError: If update fails
    """
    db = get_db_manager()
    
    if not updates:
        return True  # No updates needed
    
    # Build dynamic update query
    set_clauses = []
    params = []
    param_counter = 1
    
    for field, value in updates.items():
        set_clauses.append(f"{field} = ${param_counter}")
        params.append(value)
        param_counter += 1
    
    # Always update the updated_at timestamp
    set_clauses.append(f"updated_at = ${param_counter}")
    params.append(datetime.now(timezone.utc))
    param_counter += 1
    
    # Add WHERE clause parameter
    params.append(symbol_id)
    
    query = f"""
        UPDATE symbols 
        SET {', '.join(set_clauses)}
        WHERE id = ${param_counter}
    """
    
    try:
        result = await db.execute(query, *params)
        
        # Check if any rows were updated
        updated = result.endswith('1')  # UPDATE command returns "UPDATE n"
        
        if updated:
            logger.info(f"Updated symbol {symbol_id} with fields: {list(updates.keys())}")
        else:
            logger.warning(f"No symbol found with ID {symbol_id}")
        
        return updated
        
    except Exception as e:
        logger.error(f"Failed to update symbol {symbol_id}: {e}")
        raise


async def deactivate_symbol(symbol_id: int) -> bool:
    """
    Deactivate a symbol (soft delete).
    
    Args:
        symbol_id: Symbol ID to deactivate
        
    Returns:
        True if deactivation successful, False if symbol not found
    """
    return await update_symbol(symbol_id, {'is_active': False})


async def activate_symbol(symbol_id: int) -> bool:
    """
    Reactivate a symbol.
    
    Args:
        symbol_id: Symbol ID to activate
        
    Returns:
        True if activation successful, False if symbol not found
    """
    return await update_symbol(symbol_id, {'is_active': True})


async def bulk_insert_symbols(symbols: List[DBSymbol]) -> List[int]:
    """
    Insert multiple symbols efficiently using batch operations.
    
    Args:
        symbols: List of Symbol instances to insert
        
    Returns:
        List of database IDs for inserted symbols
        
    Raises:
        DatabaseError: If bulk insert fails
    """
    if not symbols:
        return []
    
    db = get_db_manager()
    
    # Prepare data for bulk insert
    records = []
    for symbol in symbols:
        records.append((
            symbol.exchange_id,
            symbol.symbol_base.upper(),
            symbol.symbol_quote.upper(),
            symbol.exchange_symbol,
            symbol.is_active,
            symbol.is_futures,
            symbol.min_order_size,
            symbol.max_order_size,
            symbol.price_precision,
            symbol.quantity_precision,
            symbol.tick_size,
            symbol.step_size,
            symbol.min_notional
        ))
    
    columns = [
        'exchange_id', 'symbol_base', 'symbol_quote', 'exchange_symbol',
        'is_active', 'is_futures', 'min_order_size', 'max_order_size',
        'price_precision', 'quantity_precision', 'tick_size', 'step_size', 'min_notional'
    ]
    
    try:
        # Use COPY for maximum performance
        result_count = await db.copy_records_to_table('symbols', records, columns)
        
        logger.info(f"Bulk inserted {result_count} symbols")
        
        # Since COPY doesn't return IDs, we need to fetch them
        # This is a trade-off between performance and returning IDs
        # For HFT systems, we often don't need the IDs immediately
        return []  # Return empty list for now, can be enhanced if needed
        
    except Exception as e:
        logger.error(f"Failed to bulk insert {len(symbols)} symbols: {e}")
        raise


async def get_symbol_stats() -> Dict[str, Any]:
    """
    Get symbol statistics for monitoring.
    
    Returns:
        Dictionary with symbol statistics
    """
    db = get_db_manager()
    
    queries = {
        'total_symbols': "SELECT COUNT(*) FROM symbols",
        'active_symbols': "SELECT COUNT(*) FROM symbols WHERE is_active = true",
        'spot_symbols': "SELECT COUNT(*) FROM symbols s JOIN exchanges e ON s.exchange_id = e.id WHERE e.market_type = 'SPOT' AND s.is_active = true",
        'futures_symbols': "SELECT COUNT(*) FROM symbols s JOIN exchanges e ON s.exchange_id = e.id WHERE e.market_type = 'FUTURES' AND s.is_active = true",
        'latest_update': "SELECT MAX(CURRENT_TIMESTAMP) FROM symbols"
    }
    
    stats = {}
    
    try:
        for key, query in queries.items():
            result = await db.fetchval(query)
            stats[key] = result
        
        # Add exchange breakdown
        exchange_breakdown_query = """
            SELECT e.exchange_name as name, COUNT(s.id) as symbol_count
            FROM exchanges e
            LEFT JOIN symbols s ON e.id = s.exchange_id AND s.is_active = true
            WHERE 1=1
            GROUP BY e.exchange_name
            ORDER BY symbol_count DESC
        """
        
        breakdown_rows = await db.fetch(exchange_breakdown_query)
        stats['symbols_by_exchange'] = {
            row['name']: row['symbol_count'] for row in breakdown_rows
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to retrieve symbol stats: {e}")
        return {}


async def populate_symbols_from_existing_data() -> int:
    """
    Populate symbols table from existing book_ticker_snapshots data (normalized schema).
    
    Note: This function is now deprecated since the database uses a normalized schema.
    In the normalized schema, book_ticker_snapshots only contains symbol_id references,
    not direct exchange/symbol columns. This function will return 0.
    
    Returns:
        Number of symbols populated (always 0 for normalized schema)
    """
    db = get_db_manager()
    
    # In normalized schema, we can't extract symbols from book_ticker_snapshots
    # because it only contains symbol_id references, not the actual symbol data.
    # The symbols must be populated separately through symbol synchronization services.
    logger.warning("populate_symbols_from_existing_data is deprecated for normalized schema")
    logger.info("Use symbol synchronization services to populate symbols from exchange APIs")
    return 0


async def get_exchange_by_enum_value(enum_value: str) -> Optional[Exchange]:
    """
    Helper function to get exchange by enum value.
    
    Args:
        enum_value: Exchange enum value (e.g., 'MEXC_SPOT')
        
    Returns:
        Exchange instance or None if not found
    """
    db = get_db_manager()
    
    query = """
        SELECT id, exchange_name, enum_value, market_type
        FROM exchanges
        WHERE enum_value = $1     """
    
    try:
        row = await db.fetchrow(query, enum_value)
        
        if not row:
            return None
        
        return Exchange(
            id=row['id'],
            name=row['exchange_name'],
            enum_value=row['enum_value'],
            display_name=row['exchange_name'],  # Use exchange_name as display_name
            market_type=row['market_type']
        )
        
    except Exception as e:
        logger.error(f"Failed to get exchange by enum value {enum_value}: {e}")
        raise


# ================================================================================================
# Normalized Snapshot Operations


# ================================================================================================
# Symbol Auto-Population from Exchange Data
# Automatically discovers and populates symbols from exchange connections
# ================================================================================================

async def auto_populate_symbols_from_exchanges(
    exchange_configs: List[tuple], 
    max_symbols_per_exchange: int = 100
) -> Dict[str, int]:
    """
    Auto-populate symbols table by connecting to exchanges and discovering tradable symbols.
    
    Args:
        exchange_configs: List of (exchange_enum, symbols_to_check) tuples
        max_symbols_per_exchange: Maximum symbols to populate per exchange
        
    Returns:
        Dictionary with exchange names and symbol counts populated
    """
    from exchanges.structs.enums import ExchangeEnum
    
    results = {}
    
    for exchange_enum, symbols_to_check in exchange_configs:
        try:
            logger.info(f"Auto-populating symbols for {exchange_enum.value}")
            
            # Get exchange from database
            exchange = await get_exchange_by_enum(exchange_enum)
            if not exchange:
                logger.warning(f"Exchange {exchange_enum.value} not found in database")
                continue
            
            symbols_populated = 0
            
            for symbol in symbols_to_check[:max_symbols_per_exchange]:
                try:
                    # Check if symbol already exists
                    existing_symbol = await get_symbol_by_exchange_and_pair(
                        exchange.id,
                        str(symbol.base),
                        str(symbol.quote)
                    )
                    
                    if existing_symbol:
                        logger.debug(f"Symbol {symbol.base}/{symbol.quote} already exists for {exchange_enum.value}")
                        continue
                    
                    # Create new symbol
                    db_symbol = DBSymbol(
                        exchange_id=exchange.id,
                        symbol_base=str(symbol.base).upper(),
                        symbol_quote=str(symbol.quote).upper(),
                        exchange_symbol=f"{symbol.base}{symbol.quote}".upper(),
                        is_active=True,
                        symbol_type=SymbolType.SPOT  # Default to spot
                    )
                    
                    # Insert symbol
                    await insert_symbol(db_symbol)
                    symbols_populated += 1
                    
                    logger.debug(f"Populated symbol {symbol.base}/{symbol.quote} for {exchange_enum.value}")
                    
                except Exception as e:
                    logger.warning(f"Failed to populate symbol {symbol.base}/{symbol.quote} for {exchange_enum.value}: {e}")
                    continue
            
            results[exchange_enum.value] = symbols_populated
            logger.info(f"Auto-populated {symbols_populated} symbols for {exchange_enum.value}")
            
        except Exception as e:
            logger.error(f"Failed to auto-populate symbols for {exchange_enum.value}: {e}")
            results[exchange_enum.value] = 0
    
    return results


# ================================================================================================
