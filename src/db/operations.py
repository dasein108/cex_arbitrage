"""
Database Operations

High-performance database operations for BookTicker snapshots.
Optimized for HFT requirements with minimal latency and maximum throughput.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Set
import asyncpg
from collections import defaultdict
import time

from .connection import get_db_manager
from .models import BookTickerSnapshot
from structs.common import Symbol


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
    
    cutoff_time = datetime.utcnow() - timedelta(minutes=10)
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


def _is_duplicate_timestamp(exchange: str, symbol_base: str, symbol_quote: str, timestamp: datetime) -> bool:
    """
    Check if this timestamp has been seen recently for this exchange/symbol.
    
    Returns:
        True if this is a duplicate timestamp that should be skipped
    """
    key = (exchange, symbol_base, symbol_quote)
    
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
        snapshot: BookTickerSnapshot to insert
        
    Returns:
        Database ID of inserted record
        
    Raises:
        DatabaseError: If insert fails
    """
    db = get_db_manager()
    
    query = """
        INSERT INTO book_ticker_snapshots (
            exchange, symbol_base, symbol_quote,
            bid_price, bid_qty, ask_price, ask_qty,
            timestamp
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id
    """
    
    try:
        record_id = await db.fetchval(
            query,
            snapshot.exchange,
            snapshot.symbol_base,
            snapshot.symbol_quote,
            snapshot.bid_price,
            snapshot.bid_qty,
            snapshot.ask_price,
            snapshot.ask_qty,
            snapshot.timestamp
        )
        
        logger.debug(f"Inserted book ticker snapshot {record_id} for {snapshot.exchange} {snapshot.symbol_base}/{snapshot.symbol_quote}")
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
    
    # Step 0: Clean up cache periodically
    _cleanup_timestamp_cache()
    
    # Step 1: Filter out known duplicate timestamps using cache
    filtered_snapshots = []
    cache_hits = 0
    
    for snapshot in snapshots:
        if not _is_duplicate_timestamp(snapshot.exchange, snapshot.symbol_base, 
                                      snapshot.symbol_quote, snapshot.timestamp):
            filtered_snapshots.append(snapshot)
        else:
            cache_hits += 1
    
    if cache_hits > 0:
        logger.debug(f"Cache filtered {cache_hits} duplicate timestamps")
    
    if not filtered_snapshots:
        return 0
    
    # Step 2: Deduplicate remaining snapshots in memory
    unique_snapshots = {}
    for snapshot in filtered_snapshots:
        key = (snapshot.exchange, snapshot.symbol_base, snapshot.symbol_quote, snapshot.timestamp)
        # Keep the latest one if duplicate timestamps exist
        if key not in unique_snapshots:
            unique_snapshots[key] = snapshot
        else:
            # Compare and keep the one with most recent created_at or bid/ask prices
            existing = unique_snapshots[key]
            if hasattr(snapshot, 'created_at') and hasattr(existing, 'created_at'):
                if snapshot.created_at > existing.created_at:
                    unique_snapshots[key] = snapshot
    
    deduplicated_snapshots = list(unique_snapshots.values())
    
    if not deduplicated_snapshots:
        return 0
    
    if len(snapshots) != len(deduplicated_snapshots):
        logger.debug(f"Total deduplication: {len(snapshots)} -> {len(deduplicated_snapshots)} snapshots (cache: {cache_hits}, memory: {len(filtered_snapshots) - len(deduplicated_snapshots)})")
    
    db = get_db_manager()
    
    # Step 2: Use batch upsert with ON CONFLICT DO UPDATE
    query = """
        INSERT INTO book_ticker_snapshots (
            exchange, symbol_base, symbol_quote,
            bid_price, bid_qty, ask_price, ask_qty,
            timestamp
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (timestamp, exchange, symbol_base, symbol_quote)
        DO UPDATE SET
            bid_price = EXCLUDED.bid_price,
            bid_qty = EXCLUDED.bid_qty,
            ask_price = EXCLUDED.ask_price,
            ask_qty = EXCLUDED.ask_qty,
            created_at = NOW()
        RETURNING (xmax = 0) AS inserted
    """
    
    try:
        # Use the simple fallback method which is more reliable
        return await insert_book_ticker_snapshots_batch_fallback(deduplicated_snapshots)
        
    except Exception as e:
        logger.error(f"Failed to batch upsert book ticker snapshots: {e}")
        raise


async def insert_book_ticker_snapshots_batch_simple(snapshots: List[BookTickerSnapshot]) -> int:
    """
    Simplified batch insert with upsert using single query for better performance.
    Includes timestamp cache deduplication.
    
    Args:
        snapshots: List of BookTickerSnapshot objects
        
    Returns:
        Number of records processed
    """
    if not snapshots:
        return 0
    
    # Clean up cache periodically
    _cleanup_timestamp_cache()
    
    # Filter out known duplicate timestamps using cache
    filtered_snapshots = []
    cache_hits = 0
    
    for snapshot in snapshots:
        if not _is_duplicate_timestamp(snapshot.exchange, snapshot.symbol_base, 
                                      snapshot.symbol_quote, snapshot.timestamp):
            filtered_snapshots.append(snapshot)
        else:
            cache_hits += 1
    
    if cache_hits > 0:
        logger.debug(f"Cache filtered {cache_hits} duplicate timestamps")
    
    # Deduplicate by unique key
    unique_snapshots = {}
    for snapshot in filtered_snapshots:
        key = (snapshot.exchange, snapshot.symbol_base, snapshot.symbol_quote, snapshot.timestamp)
        unique_snapshots[key] = snapshot
    
    deduplicated_snapshots = list(unique_snapshots.values())
    
    if not deduplicated_snapshots:
        return 0
    
    if len(snapshots) != len(deduplicated_snapshots):
        logger.debug(f"Total deduplication: {len(snapshots)} -> {len(deduplicated_snapshots)} snapshots (cache: {cache_hits}, memory: {len(filtered_snapshots) - len(deduplicated_snapshots)})")
    
    db = get_db_manager()
    
    # Use a single query with unnest for best performance
    query = """
        INSERT INTO book_ticker_snapshots (
            exchange, symbol_base, symbol_quote,
            bid_price, bid_qty, ask_price, ask_qty,
            timestamp
        )
        SELECT * FROM unnest($1::text[], $2::text[], $3::text[], 
                           $4::numeric[], $5::numeric[], $6::numeric[], $7::numeric[],
                           $8::timestamptz[])
        ON CONFLICT (timestamp, exchange, symbol_base, symbol_quote)
        DO UPDATE SET
            bid_price = EXCLUDED.bid_price,
            bid_qty = EXCLUDED.bid_qty,
            ask_price = EXCLUDED.ask_price,
            ask_qty = EXCLUDED.ask_qty,
            created_at = NOW()
    """
    
    try:
        # Prepare arrays for unnest
        exchanges = [s.exchange for s in deduplicated_snapshots]
        symbol_bases = [s.symbol_base for s in deduplicated_snapshots]
        symbol_quotes = [s.symbol_quote for s in deduplicated_snapshots]
        bid_prices = [s.bid_price for s in deduplicated_snapshots]
        bid_qtys = [s.bid_qty for s in deduplicated_snapshots]
        ask_prices = [s.ask_price for s in deduplicated_snapshots]
        ask_qtys = [s.ask_qty for s in deduplicated_snapshots]
        timestamps = [s.timestamp for s in deduplicated_snapshots]
        
        result = await db.execute(
            query,
            exchanges, symbol_bases, symbol_quotes,
            bid_prices, bid_qtys, ask_prices, ask_qtys,
            timestamps
        )
        
        logger.debug(f"Batch upsert processed {len(deduplicated_snapshots)} snapshots")
        return len(deduplicated_snapshots)
        
    except Exception as e:
        logger.error(f"Failed to batch upsert book ticker snapshots: {e}")
        # Fall back to the original method if the optimized one fails
        logger.info("Falling back to individual insert method")
        return await insert_book_ticker_snapshots_batch_fallback(deduplicated_snapshots)


async def insert_book_ticker_snapshots_batch_fallback(snapshots: List[BookTickerSnapshot]) -> int:
    """
    Fallback method using individual upserts for compatibility.
    """
    if not snapshots:
        return 0
        
    db = get_db_manager()
    count = 0
    
    query = """
        INSERT INTO book_ticker_snapshots (
            exchange, symbol_base, symbol_quote,
            bid_price, bid_qty, ask_price, ask_qty,
            timestamp
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (timestamp, exchange, symbol_base, symbol_quote)
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
                for snapshot in snapshots:
                    await conn.execute(
                        query,
                        snapshot.exchange,
                        snapshot.symbol_base,
                        snapshot.symbol_quote,
                        snapshot.bid_price,
                        snapshot.bid_qty,
                        snapshot.ask_price,
                        snapshot.ask_qty,
                        snapshot.timestamp
                    )
                    count += 1
        
        logger.debug(f"Fallback upsert processed {count} snapshots")
        return count
        
    except Exception as e:
        logger.error(f"Failed in fallback upsert method: {e}")
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
    Retrieve BookTicker snapshots with flexible filtering.
    
    Args:
        exchange: Filter by exchange (optional)
        symbol_base: Filter by base asset (optional)
        symbol_quote: Filter by quote asset (optional)
        timestamp_from: Start time filter (optional)
        timestamp_to: End time filter (optional)
        limit: Maximum number of records to return
        offset: Number of records to skip
        
    Returns:
        List of BookTickerSnapshot objects
    """
    db = get_db_manager()
    
    # Build dynamic WHERE clause
    where_conditions = []
    params = []
    param_counter = 1
    
    if exchange:
        where_conditions.append(f"exchange = ${param_counter}")
        params.append(exchange.upper())
        param_counter += 1
    
    if symbol_base:
        where_conditions.append(f"symbol_base = ${param_counter}")
        params.append(symbol_base.upper())
        param_counter += 1
    
    if symbol_quote:
        where_conditions.append(f"symbol_quote = ${param_counter}")
        params.append(symbol_quote.upper())
        param_counter += 1
    
    if timestamp_from:
        where_conditions.append(f"timestamp >= ${param_counter}")
        params.append(timestamp_from)
        param_counter += 1
    
    if timestamp_to:
        where_conditions.append(f"timestamp <= ${param_counter}")
        params.append(timestamp_to)
        param_counter += 1
    
    # Add limit and offset
    params.extend([limit, offset])
    
    where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
    
    query = f"""
        SELECT id, exchange, symbol_base, symbol_quote,
               bid_price, bid_qty, ask_price, ask_qty,
               timestamp, created_at
        FROM book_ticker_snapshots
        {where_clause}
        ORDER BY timestamp DESC, id DESC
        LIMIT ${param_counter} OFFSET ${param_counter + 1}
    """
    
    try:
        rows = await db.fetch(query, *params)
        
        snapshots = [
            BookTickerSnapshot(
                id=row['id'],
                exchange=row['exchange'],
                symbol_base=row['symbol_base'],
                symbol_quote=row['symbol_quote'],
                bid_price=float(row['bid_price']),
                bid_qty=float(row['bid_qty']),
                ask_price=float(row['ask_price']),
                ask_qty=float(row['ask_qty']),
                timestamp=row['timestamp'],
                created_at=row['created_at']
            )
            for row in rows
        ]
        
        logger.debug(f"Retrieved {len(snapshots)} book ticker snapshots")
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
    Get the latest BookTicker snapshot for each exchange/symbol combination.
    
    Args:
        exchange: Filter by exchange (optional)
        symbol_base: Filter by base asset (optional)
        symbol_quote: Filter by quote asset (optional)
        
    Returns:
        Dictionary mapping "exchange_base_quote" to latest BookTickerSnapshot
    """
    db = get_db_manager()
    
    # Build dynamic WHERE clause
    where_conditions = []
    params = []
    param_counter = 1
    
    if exchange:
        where_conditions.append(f"exchange = ${param_counter}")
        params.append(exchange.upper())
        param_counter += 1
    
    if symbol_base:
        where_conditions.append(f"symbol_base = ${param_counter}")
        params.append(symbol_base.upper())
        param_counter += 1
    
    if symbol_quote:
        where_conditions.append(f"symbol_quote = ${param_counter}")
        params.append(symbol_quote.upper())
        param_counter += 1
    
    where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
    
    query = f"""
        SELECT DISTINCT ON (exchange, symbol_base, symbol_quote)
               id, exchange, symbol_base, symbol_quote,
               bid_price, bid_qty, ask_price, ask_qty,
               timestamp, created_at
        FROM book_ticker_snapshots
        {where_clause}
        ORDER BY exchange, symbol_base, symbol_quote, timestamp DESC
    """
    
    try:
        rows = await db.fetch(query, *params)
        
        latest_snapshots = {}
        for row in rows:
            snapshot = BookTickerSnapshot(
                id=row['id'],
                exchange=row['exchange'],
                symbol_base=row['symbol_base'],
                symbol_quote=row['symbol_quote'],
                bid_price=float(row['bid_price']),
                bid_qty=float(row['bid_qty']),
                ask_price=float(row['ask_price']),
                ask_qty=float(row['ask_qty']),
                timestamp=row['timestamp'],
                created_at=row['created_at']
            )
            
            key = f"{snapshot.exchange}_{snapshot.symbol_base}_{snapshot.symbol_quote}"
            latest_snapshots[key] = snapshot
        
        logger.debug(f"Retrieved {len(latest_snapshots)} latest book ticker snapshots")
        return latest_snapshots
        
    except Exception as e:
        logger.error(f"Failed to retrieve latest book ticker snapshots: {e}")
        raise


async def get_book_ticker_history(
    exchange: str,
    symbol: Symbol,
    hours_back: int = 24,
    sample_interval_minutes: int = 1
) -> List[BookTickerSnapshot]:
    """
    Get historical BookTicker data for a specific exchange/symbol.
    
    Args:
        exchange: Exchange identifier
        symbol: Symbol object
        hours_back: How many hours of history to retrieve
        sample_interval_minutes: Sampling interval in minutes (for downsampling)
        
    Returns:
        List of BookTickerSnapshot objects ordered by timestamp
    """
    db = get_db_manager()
    
    timestamp_from = datetime.utcnow() - timedelta(hours=hours_back)
    
    # Use window function to sample data at intervals
    query = """
        SELECT id, exchange, symbol_base, symbol_quote,
               bid_price, bid_qty, ask_price, ask_qty,
               timestamp, created_at
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY 
                           DATE_TRUNC('minute', timestamp) / $5
                       ORDER BY timestamp DESC
                   ) as rn
            FROM book_ticker_snapshots
            WHERE exchange = $1 
              AND symbol_base = $2 
              AND symbol_quote = $3
              AND timestamp >= $4
        ) sampled
        WHERE rn = 1
        ORDER BY timestamp ASC
    """
    
    try:
        rows = await db.fetch(
            query,
            exchange.upper(),
            str(symbol.base).upper(),
            str(symbol.quote).upper(),
            timestamp_from,
            sample_interval_minutes
        )
        
        snapshots = [
            BookTickerSnapshot(
                id=row['id'],
                exchange=row['exchange'],
                symbol_base=row['symbol_base'],
                symbol_quote=row['symbol_quote'],
                bid_price=float(row['bid_price']),
                bid_qty=float(row['bid_qty']),
                ask_price=float(row['ask_price']),
                ask_qty=float(row['ask_qty']),
                timestamp=row['timestamp'],
                created_at=row['created_at']
            )
            for row in rows
        ]
        
        logger.debug(f"Retrieved {len(snapshots)} historical book ticker snapshots for {exchange} {symbol.base}/{symbol.quote}")
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
    
    cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
    
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
        'exchanges': "SELECT COUNT(DISTINCT exchange) FROM book_ticker_snapshots",
        'symbols': "SELECT COUNT(DISTINCT symbol_base || '/' || symbol_quote) FROM book_ticker_snapshots",
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