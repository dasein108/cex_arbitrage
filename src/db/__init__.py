"""
Database Module

High-performance PostgreSQL integration for the CEX Arbitrage Engine.
Provides asyncpg-based connection management and operations optimized for HFT requirements.

Key Features:
- Ultra-fast asyncpg connection pooling
- HFT-optimized BookTicker storage
- Automatic schema migrations
- Sub-millisecond insert/query performance
- Prepared statement caching
"""

from .connection import DatabaseManager, get_db_manager
from .operations import (
    insert_book_ticker_snapshot,
    insert_book_ticker_snapshots_batch,
    get_book_ticker_snapshots,
    get_latest_book_ticker_snapshots,
    get_book_ticker_history
)
from .models import BookTickerSnapshot
from .migrations import run_migrations

__all__ = [
    'DatabaseManager',
    'get_db_manager', 
    'insert_book_ticker_snapshot',
    'insert_book_ticker_snapshots_batch',
    'get_book_ticker_snapshots',
    'get_latest_book_ticker_snapshots',
    'get_book_ticker_history',
    'BookTickerSnapshot',
    'run_migrations'
]