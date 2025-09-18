"""
Database Operations

High-performance database operations for BookTicker snapshots.
Optimized for HFT requirements with minimal latency and maximum throughput.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import asyncpg

from .connection import get_db_manager
from .models import BookTickerSnapshot
from structs.common import Symbol


logger = logging.getLogger(__name__)


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
    Insert multiple BookTicker snapshots efficiently using COPY.
    
    This is the most performant method for batch inserts.
    
    Args:
        snapshots: List of BookTickerSnapshot objects
        
    Returns:
        Number of records inserted
        
    Raises:
        DatabaseError: If batch insert fails
    """
    if not snapshots:
        return 0
    
    db = get_db_manager()
    
    # Convert snapshots to tuples for COPY command
    records = [
        (
            snapshot.exchange,
            snapshot.symbol_base,
            snapshot.symbol_quote,
            snapshot.bid_price,
            snapshot.bid_qty,
            snapshot.ask_price,
            snapshot.ask_qty,
            snapshot.timestamp
        )
        for snapshot in snapshots
    ]
    
    columns = [
        'exchange', 'symbol_base', 'symbol_quote',
        'bid_price', 'bid_qty', 'ask_price', 'ask_qty',
        'timestamp'
    ]
    
    try:
        count = await db.copy_records_to_table(
            'book_ticker_snapshots',
            records=records,
            columns=columns
        )
        
        logger.info(f"Batch inserted {count} book ticker snapshots")
        return count
        
    except Exception as e:
        logger.error(f"Failed to batch insert book ticker snapshots: {e}")
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