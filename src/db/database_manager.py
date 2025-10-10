"""
Simplified Database Manager

Unified database management class following PROJECT_GUIDES.md requirements.
Consolidates all database functionality into a single class with built-in caching.

Key Features:
- Float-Only Data Policy: NEVER use Decimal, ALWAYS use float for numerical operations
- Struct-First Data Policy: msgspec.Struct over dict for ALL data modeling
- HFT Performance Requirements: Sub-millisecond targets, minimal LOC
- Configuration Management: Use HftConfig with get_database_config()
- Built-in caching for lookup data (symbols, exchanges) with TTL management
- All CRUD operations in a single class to reduce complexity
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from collections import defaultdict
import threading
import asyncpg

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    pd = None

from config.config_manager import get_database_config
from .models import (
    Exchange, Symbol as DBSymbol, BookTickerSnapshot, TradeSnapshot, 
    FundingRateSnapshot, BalanceSnapshot, SymbolType
)
from exchanges.structs.common import Symbol
from exchanges.structs.enums import ExchangeEnum


class DatabaseManager:
    """
    Unified database manager with built-in caching and all database operations.
    
    Follows PROJECT_GUIDES.md requirements:
    - Float-Only Data Policy for all numerical operations
    - Struct-First Data Policy with msgspec.Struct throughout
    - HFT Performance Requirements with sub-microsecond cache lookups
    - Single class containing all database functionality
    """
    
    _instance: Optional["DatabaseManager"] = None
    _logger = logging.getLogger(__name__)
    
    def __new__(cls) -> "DatabaseManager":
        """Singleton pattern implementation."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize DatabaseManager with caching infrastructure."""
        if hasattr(self, '_initialized'):
            return
            
        self._pool: Optional[asyncpg.Pool] = None
        self._config = None
        
        # Built-in caching with TTL management
        self._symbol_cache: Dict[int, DBSymbol] = {}
        self._symbol_exchange_cache: Dict[Tuple[int, str, str], DBSymbol] = {}
        self._symbol_string_cache: Dict[Tuple[int, str], DBSymbol] = {}
        self._exchange_cache: Dict[int, Exchange] = {}
        self._exchange_enum_cache: Dict[str, Exchange] = {}
        
        # Cache TTL management
        self._cache_ttl_seconds = 300  # 5 minutes
        self._last_cache_refresh = datetime.utcnow()
        self._cache_lock = threading.RLock()
        
        # Performance tracking for HFT compliance
        self._cache_stats = {
            'hits': 0,
            'misses': 0,
            'total_requests': 0,
            'avg_lookup_time_ns': 0.0
        }
        self._lookup_times: List[float] = []
        
        # Deduplication cache for recent operations
        self._timestamp_cache: Dict[tuple, Set[datetime]] = defaultdict(set)
        self._cache_last_cleanup = time.time()
        
        self._initialized = True
        self._logger.info("DatabaseManager initialized with built-in caching")

    def _debug_query(self, query: str, params: list) -> str:
        """Debug helper to see the prepared query with values"""
        result = query
        for i, param in enumerate(params, 1):
            placeholder = f"${i}"
            if isinstance(param, str):
                value = f"'{param}'"
            elif isinstance(param, (datetime, date)):  # Add datetime handling
                value = f"'{param}'"
            elif param is None:
                value = "NULL"
            else:
                value = str(param)
            result = result.replace(placeholder, value, 1)
        return result

    async def initialize(self) -> None:
        """
        Initialize database connection using get_database_config() from HftConfig.
        
        Follows PROJECT_GUIDES.md requirement for configuration management.
        """
        if self._pool is not None:
            self._logger.warning("DatabaseManager already initialized")
            return
        
        # Use get_database_config() from HftConfig as required by PROJECT_GUIDES.md
        self._config = get_database_config()
        
        try:
            self._logger.info(f"Initializing database pool: {self._config.host}:{self._config.port}/{self._config.database}")
            
            # Create HFT-optimized connection pool
            self._pool = await asyncpg.create_pool(
                dsn=self._config.get_dsn(),
                min_size=self._config.min_pool_size,
                max_size=self._config.max_pool_size,
                max_queries=self._config.max_queries,
                max_inactive_connection_lifetime=self._config.max_inactive_connection_lifetime,
                command_timeout=self._config.command_timeout,
                statement_cache_size=self._config.statement_cache_size,
                server_settings={
                    'jit': 'off',  # Disable JIT for consistent latency
                    'application_name': 'cex_arbitrage_hft'
                }
            )
            
            # Test connection and verify database structure
            async with self._pool.acquire() as conn:
                version = await conn.fetchval('SELECT version()')
                self._logger.info(f"Database connected: {version}")
            
            # Initialize cache with data
            await self._refresh_cache()
            
            self._logger.info("DatabaseManager initialization complete")
            
        except Exception as e:
            self._logger.error(f"Database initialization failed: {e}")
            raise ConnectionError(f"Database initialization failed: {e}")
    
    async def close(self) -> None:
        """Close database connection and clear caches."""
        if self._pool is not None:
            self._logger.info("Closing database connection pool")
            await self._pool.close()
            self._pool = None
        
        with self._cache_lock:
            self._symbol_cache.clear()
            self._symbol_exchange_cache.clear()
            self._symbol_string_cache.clear()
            self._exchange_cache.clear()
            self._exchange_enum_cache.clear()
    
    def _record_cache_lookup(self, lookup_time_ns: float, hit: bool) -> None:
        """Record cache lookup performance for HFT compliance monitoring."""
        with self._cache_lock:
            self._cache_stats['total_requests'] += 1
            if hit:
                self._cache_stats['hits'] += 1
            else:
                self._cache_stats['misses'] += 1
            
            self._lookup_times.append(lookup_time_ns)
            if len(self._lookup_times) > 1000:  # Keep recent 1000 samples
                self._lookup_times = self._lookup_times[-1000:]
            
            if self._lookup_times:
                self._cache_stats['avg_lookup_time_ns'] = sum(self._lookup_times) / len(self._lookup_times)
    
    async def _refresh_cache(self) -> None:
        """Refresh cache with latest data from database."""
        if not self._pool:
            return
        
        start_time = time.perf_counter_ns()
        
        try:
            # Load exchanges
            await self._load_exchanges_to_cache()
            
            # Load symbols
            await self._load_symbols_to_cache()
            
            with self._cache_lock:
                self._last_cache_refresh = datetime.utcnow()
            
            refresh_time_ms = (time.perf_counter_ns() - start_time) / 1_000_000
            self._logger.debug(f"Cache refreshed in {refresh_time_ms:.2f}ms")
            
        except Exception as e:
            self._logger.error(f"Cache refresh failed: {e}")
    
    async def _load_exchanges_to_cache(self) -> None:
        """Load exchanges into cache."""
        query = """
            SELECT id, exchange_name, enum_value, market_type
            FROM exchanges
            ORDER BY exchange_name
        """
        
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        with self._cache_lock:
            self._exchange_cache.clear()
            self._exchange_enum_cache.clear()
            
            for row in rows:
                exchange = Exchange(
                    id=row['id'],
                    name=row['exchange_name'],
                    enum_value=row['enum_value'],
                    display_name=row['exchange_name'],
                    market_type=row['market_type']
                )
                self._exchange_cache[exchange.id] = exchange
                self._exchange_enum_cache[exchange.enum_value] = exchange
    
    async def _load_symbols_to_cache(self) -> None:
        """Load symbols into cache."""
        query = """
            SELECT id, exchange_id, symbol_base, symbol_quote, exchange_symbol,
                   is_active, symbol_type
            FROM symbols
            WHERE is_active = true
            ORDER BY exchange_id, symbol_base, symbol_quote
        """
        
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        with self._cache_lock:
            self._symbol_cache.clear()
            self._symbol_exchange_cache.clear()
            self._symbol_string_cache.clear()
            
            for row in rows:
                symbol = DBSymbol(
                    id=row['id'],
                    exchange_id=row['exchange_id'],
                    symbol_base=row['symbol_base'],
                    symbol_quote=row['symbol_quote'],
                    exchange_symbol=row['exchange_symbol'],
                    is_active=row['is_active'],
                    symbol_type=SymbolType(row['symbol_type'])
                )
                
                # Multiple cache indexes for optimal lookup performance
                self._symbol_cache[symbol.id] = symbol
                pair_key = (symbol.exchange_id, symbol.symbol_base.upper(), symbol.symbol_quote.upper())
                self._symbol_exchange_cache[pair_key] = symbol
                string_key = (symbol.exchange_id, symbol.exchange_symbol.upper())
                self._symbol_string_cache[string_key] = symbol
    
    def _should_refresh_cache(self) -> bool:
        """Check if cache should be refreshed based on TTL."""
        return (datetime.utcnow() - self._last_cache_refresh).total_seconds() > self._cache_ttl_seconds
    
    # =============================================================================
    # SYMBOL OPERATIONS (Cached)
    # =============================================================================
    
    def get_symbol_by_id(self, symbol_id: int) -> Optional[DBSymbol]:
        """
        Get symbol by ID with sub-microsecond cache lookup.
        
        Args:
            symbol_id: Symbol database ID
            
        Returns:
            Symbol instance or None if not found
        """
        start_time = time.perf_counter_ns()
        
        with self._cache_lock:
            symbol = self._symbol_cache.get(symbol_id)
            hit = symbol is not None
        
        self._record_cache_lookup(time.perf_counter_ns() - start_time, hit)
        return symbol
    
    def get_symbol_by_exchange_and_pair(
        self, 
        exchange_id: int, 
        symbol_base: str, 
        symbol_quote: str
    ) -> Optional[DBSymbol]:
        """
        Get symbol by exchange and base/quote pair with cache lookup.
        
        Args:
            exchange_id: Exchange database ID
            symbol_base: Base asset (e.g., 'BTC')
            symbol_quote: Quote asset (e.g., 'USDT')
            
        Returns:
            Symbol instance or None if not found
        """
        start_time = time.perf_counter_ns()
        
        with self._cache_lock:
            pair_key = (exchange_id, symbol_base.upper(), symbol_quote.upper())
            symbol = self._symbol_exchange_cache.get(pair_key)
            hit = symbol is not None
        
        self._record_cache_lookup(time.perf_counter_ns() - start_time, hit)
        return symbol
    
    def get_symbol_by_exchange_and_string(
        self, 
        exchange_id: int, 
        exchange_symbol: str
    ) -> Optional[DBSymbol]:
        """
        Get symbol by exchange and exchange-specific symbol string.
        
        Args:
            exchange_id: Exchange database ID
            exchange_symbol: Exchange-specific symbol (e.g., 'BTCUSDT')
            
        Returns:
            Symbol instance or None if not found
        """
        start_time = time.perf_counter_ns()
        
        with self._cache_lock:
            string_key = (exchange_id, exchange_symbol.upper())
            symbol = self._symbol_string_cache.get(string_key)
            hit = symbol is not None
        
        self._record_cache_lookup(time.perf_counter_ns() - start_time, hit)
        return symbol
    
    def get_symbol_by_exchange_and_symbol_string(
        self, 
        exchange_id: int, 
        symbol_string: str
    ) -> Optional[DBSymbol]:
        """
        Get symbol by exchange and symbol string (supports both formats).
        
        Handles both slash format ('BTC/USDT') and exchange format ('BTCUSDT')
        with automatic format detection and conversion. This is the recommended
        unified method for symbol resolution that provides maximum compatibility.
        
        Args:
            exchange_id: Exchange database ID
            symbol_string: Symbol in either format ('BTC/USDT' or 'BTCUSDT')
            
        Returns:
            Symbol instance or None if not found
            
        Performance: Target <1μs lookup time with fallback <2μs
        """
        start_time = time.perf_counter_ns()
        
        # Try direct lookup first (handles exchange format like 'BTCUSDT')
        symbol = self._get_symbol_direct(exchange_id, symbol_string.upper())
        if symbol:
            self._record_cache_lookup(time.perf_counter_ns() - start_time, True)
            return symbol
        
        # Try slash format conversion if contains '/'
        if '/' in symbol_string:
            parts = symbol_string.split('/')
            if len(parts) == 2:
                # Convert to exchange format and try lookup (BTC/USDT -> BTCUSDT)
                exchange_format = f"{parts[0]}{parts[1]}".upper()
                symbol = self._get_symbol_direct(exchange_id, exchange_format)
                if symbol:
                    self._record_cache_lookup(time.perf_counter_ns() - start_time, True)
                    return symbol
                
                # Try base/quote lookup as fallback
                symbol = self.get_symbol_by_exchange_and_pair(exchange_id, parts[0], parts[1])
                if symbol:
                    self._record_cache_lookup(time.perf_counter_ns() - start_time, True)
                    return symbol
        
        self._record_cache_lookup(time.perf_counter_ns() - start_time, False)
        return None
    
    def _get_symbol_direct(self, exchange_id: int, exchange_symbol: str) -> Optional[DBSymbol]:
        """
        Internal helper for direct cache lookup without timing overhead.
        
        Args:
            exchange_id: Exchange database ID
            exchange_symbol: Exchange-specific symbol (normalized to uppercase)
            
        Returns:
            Symbol instance or None if not found
        """
        with self._cache_lock:
            string_key = (exchange_id, exchange_symbol.upper())
            return self._symbol_string_cache.get(string_key)
    
    def resolve_symbol(self, exchange_enum_or_id, symbol_or_string) -> Optional[DBSymbol]:
        """
        Universal symbol resolution method for maximum compatibility.
        
        Handles all common patterns:
        - ExchangeEnum + Symbol object
        - ExchangeEnum + symbol string (both formats)
        - Exchange ID + symbol string (both formats)
        
        Args:
            exchange_enum_or_id: ExchangeEnum, exchange string, or exchange_id (int)
            symbol_or_string: Symbol object or string in any format
            
        Returns:
            Symbol instance or None if not found
            
        Examples:
            resolve_symbol(ExchangeEnum.MEXC, Symbol(base="BTC", quote="USDT"))
            resolve_symbol(ExchangeEnum.MEXC, "BTC/USDT")
            resolve_symbol(ExchangeEnum.MEXC, "BTCUSDT")
            resolve_symbol("MEXC_SPOT", "BTC/USDT")
            resolve_symbol(1, "BTCUSDT")
        """
        start_time = time.perf_counter_ns()
        
        # Resolve exchange_id
        if isinstance(exchange_enum_or_id, int):
            exchange_id = exchange_enum_or_id
        else:
            # Handle ExchangeEnum or string
            exchange = self.get_exchange_by_enum(exchange_enum_or_id)
            if not exchange:
                self._record_cache_lookup(time.perf_counter_ns() - start_time, False)
                return None
            exchange_id = exchange.id
        
        # Resolve symbol string
        if hasattr(symbol_or_string, 'base') and hasattr(symbol_or_string, 'quote'):
            # Symbol object - use base/quote lookup
            symbol = self.get_symbol_by_exchange_and_pair(
                exchange_id, 
                symbol_or_string.base, 
                symbol_or_string.quote
            )
        else:
            # String - use unified string resolution
            symbol = self.get_symbol_by_exchange_and_symbol_string(exchange_id, str(symbol_or_string))
        
        # Record timing (the individual methods already recorded, but we track overall)
        self._record_cache_lookup(time.perf_counter_ns() - start_time, symbol is not None)
        return symbol
    
    def get_symbols_by_exchange(self, exchange_id: int) -> List[DBSymbol]:
        """
        Get all symbols for an exchange from cache.
        
        Args:
            exchange_id: Exchange database ID
            
        Returns:
            List of symbols for the exchange
        """
        start_time = time.perf_counter_ns()
        
        with self._cache_lock:
            symbols = [
                symbol for symbol in self._symbol_cache.values()
                if symbol.exchange_id == exchange_id
            ]
        
        self._record_cache_lookup(time.perf_counter_ns() - start_time, True)
        return symbols
    
    async def insert_symbol(self, symbol: DBSymbol) -> int:
        """
        Insert new symbol and update cache.
        
        Args:
            symbol: Symbol instance to insert
            
        Returns:
            Database ID of inserted symbol
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        
        query = """
            INSERT INTO symbols (
                exchange_id, symbol_base, symbol_quote, exchange_symbol, 
                is_active, symbol_type
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
        """
        
        async with self._pool.acquire() as conn:
            symbol_id = await conn.fetchval(
                query,
                symbol.exchange_id,
                symbol.symbol_base.upper(),
                symbol.symbol_quote.upper(),
                symbol.exchange_symbol,
                symbol.is_active,
                symbol.symbol_type.name
            )
        
        # Update cache
        symbol.id = symbol_id
        with self._cache_lock:
            self._symbol_cache[symbol_id] = symbol
            pair_key = (symbol.exchange_id, symbol.symbol_base.upper(), symbol.symbol_quote.upper())
            self._symbol_exchange_cache[pair_key] = symbol
            string_key = (symbol.exchange_id, symbol.exchange_symbol.upper())
            self._symbol_string_cache[string_key] = symbol
        
        self._logger.info(f"Inserted symbol {symbol.symbol_base}/{symbol.symbol_quote} with ID {symbol_id}")
        return symbol_id
    
    # =============================================================================
    # EXCHANGE OPERATIONS (Cached)
    # =============================================================================
    
    def get_exchange_by_id(self, exchange_id: int) -> Optional[Exchange]:
        """
        Get exchange by ID with cache lookup.
        
        Args:
            exchange_id: Exchange database ID
            
        Returns:
            Exchange instance or None if not found
        """
        start_time = time.perf_counter_ns()
        
        with self._cache_lock:
            exchange = self._exchange_cache.get(exchange_id)
            hit = exchange is not None
        
        self._record_cache_lookup(time.perf_counter_ns() - start_time, hit)
        return exchange
    
    def get_exchange_by_enum(self, exchange_enum_or_str) -> Optional[Exchange]:
        """
        Get exchange by enum value or string with cache lookup.
        
        Args:
            exchange_enum_or_str: ExchangeEnum value or string (e.g., "MEXC_SPOT", "TEST_SPOT")
            
        Returns:
            Exchange instance or None if not found
        """
        start_time = time.perf_counter_ns()
        
        # Handle both ExchangeEnum and string inputs
        if isinstance(exchange_enum_or_str, ExchangeEnum):
            enum_value = str(exchange_enum_or_str.value)
        elif isinstance(exchange_enum_or_str, str):
            enum_value = exchange_enum_or_str
        else:
            # Try to convert to string as fallback
            enum_value = str(exchange_enum_or_str)
        
        with self._cache_lock:
            exchange = self._exchange_enum_cache.get(enum_value)
            hit = exchange is not None
        
        self._record_cache_lookup(time.perf_counter_ns() - start_time, hit)
        return exchange
    
    def get_all_exchanges(self) -> List[Exchange]:
        """
        Get all exchanges from cache.
        
        Returns:
            List of all exchanges
        """
        start_time = time.perf_counter_ns()
        
        with self._cache_lock:
            exchanges = list(self._exchange_cache.values())
        
        self._record_cache_lookup(time.perf_counter_ns() - start_time, True)
        return exchanges
    
    async def insert_exchange(self, exchange: Exchange) -> int:
        """
        Insert new exchange and update cache.
        
        Args:
            exchange: Exchange instance to insert
            
        Returns:
            Database ID of inserted exchange
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        
        query = """
            INSERT INTO exchanges (
                exchange_name, enum_value, market_type
            ) VALUES ($1, $2, $3)
            RETURNING id
        """
        
        async with self._pool.acquire() as conn:
            exchange_id = await conn.fetchval(
                query,
                exchange.name,
                exchange.enum_value,
                exchange.market_type
            )
        
        # Update cache
        exchange.id = exchange_id
        with self._cache_lock:
            self._exchange_cache[exchange_id] = exchange
            self._exchange_enum_cache[exchange.enum_value] = exchange
        
        self._logger.info(f"Inserted exchange {exchange.name} with ID {exchange_id}")
        return exchange_id
    
    # =============================================================================
    # BOOK TICKER OPERATIONS (Float-Only)
    # =============================================================================
    
    async def insert_book_ticker_snapshot(self, snapshot: BookTickerSnapshot) -> int:
        """
        Insert single book ticker snapshot with float-only policy.
        
        Args:
            snapshot: BookTickerSnapshot to insert
            
        Returns:
            Database ID of inserted record
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        
        query = """
            INSERT INTO book_ticker_snapshots (
                symbol_id, bid_price, bid_qty, ask_price, ask_qty, timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
        """
        
        async with self._pool.acquire() as conn:
            record_id = await conn.fetchval(
                query,
                snapshot.symbol_id,
                float(snapshot.bid_price),    # Ensure float type
                float(snapshot.bid_qty),      # Ensure float type
                float(snapshot.ask_price),    # Ensure float type
                float(snapshot.ask_qty),      # Ensure float type
                snapshot.timestamp
            )
        
        return record_id
    
    async def insert_book_ticker_snapshots_batch(self, snapshots: List[BookTickerSnapshot]) -> int:
        """
        Insert multiple book ticker snapshots with deduplication and float-only policy.
        
        Args:
            snapshots: List of BookTickerSnapshot objects
            
        Returns:
            Number of records inserted/updated
        """
        if not snapshots or not self._pool:
            return 0
        
        # Deduplication
        unique_snapshots = {}
        for snapshot in snapshots:
            key = (snapshot.symbol_id, snapshot.timestamp)
            unique_snapshots[key] = snapshot
        
        deduplicated_snapshots = list(unique_snapshots.values())
        
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
        
        count = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for snapshot in deduplicated_snapshots:
                    await conn.execute(
                        query,
                        snapshot.symbol_id,
                        float(snapshot.bid_price),    # Float-only policy
                        float(snapshot.bid_qty),      # Float-only policy
                        float(snapshot.ask_price),    # Float-only policy
                        float(snapshot.ask_qty),      # Float-only policy
                        snapshot.timestamp
                    )
                    count += 1
        
        return count
    
    async def get_latest_book_ticker_snapshots(
        self, 
        exchange: Optional[str] = None,
        symbol_base: Optional[str] = None,
        symbol_quote: Optional[str] = None,
        limit: int = 1000
    ) -> List[BookTickerSnapshot]:
        """
        Get latest book ticker snapshots with float conversion.
        
        Uses normalized schema with proper JOINs for optimal performance.
        Target: <5ms for normalized joins per HFT requirements.
        
        Args:
            exchange: Filter by exchange (optional)
            symbol_base: Filter by base asset (optional)
            symbol_quote: Filter by quote asset (optional)
            limit: Maximum records to return
            
        Returns:
            List of BookTickerSnapshot objects with float values
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        
        # Build dynamic WHERE clause using normalized schema
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
        
        params.append(limit)
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # Use normalized schema with proper JOINs for HFT performance
        query = f"""
            SELECT DISTINCT ON (e.enum_value, s.symbol_base, s.symbol_quote)
                   bts.id, bts.symbol_id, e.enum_value as exchange,
                   s.symbol_base, s.symbol_quote,
                   bts.bid_price, bts.bid_qty, bts.ask_price, bts.ask_qty, 
                   bts.timestamp, bts.created_at
            FROM book_ticker_snapshots bts
            INNER JOIN symbols s ON bts.symbol_id = s.id
            INNER JOIN exchanges e ON s.exchange_id = e.id
            {where_clause}
            ORDER BY e.enum_value, s.symbol_base, s.symbol_quote, bts.timestamp DESC
            LIMIT ${param_counter}
        """
        
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        snapshots = []
        for row in rows:
            snapshots.append(
                BookTickerSnapshot(
                    id=row['id'],
                    symbol_id=row['symbol_id'],
                    bid_price=float(row['bid_price']),    # Float-only policy
                    bid_qty=float(row['bid_qty']),        # Float-only policy
                    ask_price=float(row['ask_price']),    # Float-only policy
                    ask_qty=float(row['ask_qty']),        # Float-only policy
                    timestamp=row['timestamp'],
                    created_at=row['created_at'],
                    # Populate convenience fields from JOIN results
                    exchange=row['exchange'],
                    symbol_base=row['symbol_base'],
                    symbol_quote=row['symbol_quote']
                )
            )
        
        return snapshots
    
    # =============================================================================
    # PANDAS-NATIVE OPERATIONS (HFT-Optimized DataFrame Methods)
    # =============================================================================
    
    async def get_book_ticker_dataframe(
        self,
        exchange: Optional[str] = None,
        symbol_base: Optional[str] = None, 
        symbol_quote: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 10000
    ) -> "pd.DataFrame":
        """
        Get book ticker data as pandas DataFrame for HFT strategy analysis.
        
        Uses normalized schema with proper JOINs for data consistency.
        Maximum precision preservation: no PostgreSQL casting, Decimal->float conversion in Python.
        Calculates mid_price and spread_bps in Python to avoid database rounding.
        
        Args:
            exchange: Filter by exchange (e.g., "GATEIO_FUTURES")
            symbol_base: Filter by base asset (e.g., "MYX")
            symbol_quote: Filter by quote asset (e.g., "USDT") 
            start_time: Start time filter (optional)
            end_time: End time filter (optional)
            limit: Maximum records to return
            
        Returns:
            pandas DataFrame with columns: timestamp, exchange, symbol_base, symbol_quote,
            bid_price, bid_qty, ask_price, ask_qty, mid_price, spread_bps
        """
        if not PANDAS_AVAILABLE:
            raise ImportError("pandas is required for DataFrame operations. Install with: pip install pandas")
        
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        
        # Build dynamic WHERE clause using current production schema
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
            
        if start_time:
            where_conditions.append(f"bts.timestamp >= ${param_counter}")
            params.append(start_time)
            param_counter += 1
            
        if end_time:
            where_conditions.append(f"bts.timestamp <= ${param_counter}")
            params.append(end_time)
            param_counter += 1
        
        params.append(limit)
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # Use normalized schema with proper JOINs - no casting for maximum precision
        query = f"""
            SELECT 
                bts.timestamp,
                e.enum_value as exchange,
                s.symbol_base,
                s.symbol_quote,
                bts.bid_price,
                bts.bid_qty,
                bts.ask_price,
                bts.ask_qty
            FROM book_ticker_snapshots bts
            INNER JOIN symbols s ON bts.symbol_id = s.id
            INNER JOIN exchanges e ON s.exchange_id = e.id
            {where_clause}
            ORDER BY bts.timestamp DESC
            LIMIT ${param_counter}
        """
        
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        # Convert Decimal objects to float with maximum precision preservation
        if not rows:
            return pd.DataFrame(columns=[
                'timestamp', 'exchange', 'symbol_base', 'symbol_quote',
                'bid_price', 'bid_qty', 'ask_price', 'ask_qty', 'mid_price', 'spread_bps'
            ])
        
        # Convert Decimal to float and calculate mid_price/spread_bps in Python for precision
        data = []
        # TODO: maybe this is not necessary, check and remove
        for row in rows:
            bid_price = float(row['bid_price'])    # Convert Decimal to float
            bid_qty = float(row['bid_qty'])        # Convert Decimal to float  
            ask_price = float(row['ask_price'])    # Convert Decimal to float
            ask_qty = float(row['ask_qty'])        # Convert Decimal to float
            
            # Calculate mid_price and spread_bps in Python for maximum precision
            mid_price = (bid_price + ask_price) / 2.0
            spread_bps = ((ask_price - bid_price) / mid_price) * 10000.0 if mid_price > 0 else 0.0
            
            data.append({
                'timestamp': row['timestamp'],
                'exchange': row['exchange'],
                'symbol_base': row['symbol_base'],
                'symbol_quote': row['symbol_quote'],
                'bid_price': bid_price,
                'bid_qty': bid_qty,
                'ask_price': ask_price,
                'ask_qty': ask_qty,
                'mid_price': mid_price,
                'spread_bps': spread_bps
            })
        
        df = pd.DataFrame(data)
        
        # Set timestamp as index for time-series operations
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        
        return df
    
    async def get_aligned_market_data_dataframe(
        self,
        symbol_base: str,
        symbol_quote: str,
        exchanges: List[str],
        start_time: datetime,
        end_time: datetime,
        alignment_window: str = "1S"
    ) -> "pd.DataFrame":
        """
        Get time-aligned market data for multiple exchanges as single DataFrame.
        
        Uses normalized schema with proper JOINs for data consistency.
        Optimized for strategy_backtester.py cross-exchange analysis.
        Performs database-level alignment instead of post-processing.
        Target: <5ms queries with high precision arithmetic.
        
        Args:
            symbol_base: Base asset (e.g., "BTC")
            symbol_quote: Quote asset (e.g., "USDT")
            exchanges: List of exchange names (e.g., ["MEXC_SPOT", "GATEIO_SPOT"])
            start_time: Start time for data
            end_time: End time for data  
            alignment_window: Time window for alignment (e.g., "1S", "5S", "1T")
            
        Returns:
            pandas DataFrame with time-aligned data, columns prefixed by exchange name
        """
        if not PANDAS_AVAILABLE:
            raise ImportError("pandas is required for DataFrame operations. Install with: pip install pandas")
        
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        
        # Convert alignment window to PostgreSQL interval
        alignment_map = {
            "1S": "1 second", "5S": "5 seconds", "10S": "10 seconds", "30S": "30 seconds",
            "1T": "1 minute", "5T": "5 minutes", "15T": "15 minutes", "1H": "1 hour"
        }
        pg_interval = alignment_map.get(alignment_window, "1 second")
        
        # Build query for time-aligned data across exchanges using normalized schema
        exchange_conditions = " OR ".join([f"e.enum_value = '{ex.upper()}'" for ex in exchanges])
        
        # Use normalized schema with proper JOINs for HFT performance
        query = f"""
            WITH time_buckets AS (
                SELECT time_bucket(INTERVAL '{pg_interval}', bts.timestamp) as bucket_time
                FROM book_ticker_snapshots bts
                INNER JOIN symbols s ON bts.symbol_id = s.id
                INNER JOIN exchanges e ON s.exchange_id = e.id
                WHERE s.symbol_base = $1 
                  AND s.symbol_quote = $2
                  AND ({exchange_conditions})
                  AND bts.timestamp BETWEEN $3 AND $4
                GROUP BY bucket_time
                ORDER BY bucket_time
            ),
            aligned_data AS (
                SELECT 
                    tb.bucket_time,
                    e.enum_value as exchange,
                    FIRST(bts.bid_price ORDER BY bts.timestamp DESC) as bid_price,
                    FIRST(bts.bid_qty ORDER BY bts.timestamp DESC) as bid_qty,
                    FIRST(bts.ask_price ORDER BY bts.timestamp DESC) as ask_price,
                    FIRST(bts.ask_qty ORDER BY bts.timestamp DESC) as ask_qty
                FROM time_buckets tb
                LEFT JOIN book_ticker_snapshots bts ON 
                    time_bucket(INTERVAL '{pg_interval}', bts.timestamp) = tb.bucket_time
                INNER JOIN symbols s ON bts.symbol_id = s.id
                INNER JOIN exchanges e ON s.exchange_id = e.id
                WHERE s.symbol_base = $1 
                  AND s.symbol_quote = $2
                  AND ({exchange_conditions})
                GROUP BY tb.bucket_time, e.enum_value
            )
            SELECT * FROM aligned_data
            ORDER BY bucket_time, exchange
        """
        
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, symbol_base.upper(), symbol_quote.upper(), start_time, end_time)
        
        if not rows:
            return pd.DataFrame()
        
        # Convert Decimal objects to float with maximum precision preservation
        data = []
        # TODO: maybe this is not necessary, check and remove
        for row in rows:
            bid_price = float(row['bid_price']) if row['bid_price'] is not None else None
            bid_qty = float(row['bid_qty']) if row['bid_qty'] is not None else None
            ask_price = float(row['ask_price']) if row['ask_price'] is not None else None
            ask_qty = float(row['ask_qty']) if row['ask_qty'] is not None else None
            
            # Calculate mid_price in Python for maximum precision
            mid_price = None
            if bid_price is not None and ask_price is not None:
                mid_price = (bid_price + ask_price) / 2.0
            
            data.append({
                'bucket_time': row['bucket_time'],
                'exchange': row['exchange'],
                'bid_price': bid_price,
                'bid_qty': bid_qty,
                'ask_price': ask_price,
                'ask_qty': ask_qty,
                'mid_price': mid_price
            })
        
        df = pd.DataFrame(data)
        
        # Pivot to get exchange-specific columns
        pivoted = df.pivot_table(
            index='bucket_time',
            columns='exchange', 
            values=['bid_price', 'bid_qty', 'ask_price', 'ask_qty', 'mid_price'],
            aggfunc='first'
        )
        
        # Flatten column names (e.g., ('bid_price', 'MEXC_SPOT') -> 'MEXC_SPOT_bid_price')
        pivoted.columns = [f"{col[1]}_{col[0]}" for col in pivoted.columns]
        
        # Fill forward missing values for continuous data
        pivoted.fillna(method='ffill', inplace=True)
        
        return pivoted
    
    # =============================================================================
    # BALANCE OPERATIONS (Float-Only, HFT-Optimized)
    # =============================================================================
    
    async def insert_balance_snapshots_batch(self, snapshots: List[BalanceSnapshot]) -> int:
        """
        Insert balance snapshots with float-only policy and HFT optimization.
        
        Target: <5ms per batch (up to 100 snapshots).
        
        Args:
            snapshots: List of BalanceSnapshot objects
            
        Returns:
            Number of records inserted/updated
        """
        if not snapshots or not self._pool:
            return 0
        
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
        
        # Prepare data with float-only policy
        batch_data = []
        for snapshot in snapshots:
            batch_data.append((
                snapshot.timestamp,
                snapshot.exchange_id,
                snapshot.asset_name.upper(),
                float(snapshot.available_balance),    # Float-only policy
                float(snapshot.locked_balance),       # Float-only policy
                float(snapshot.frozen_balance or 0.0),     # Float-only policy
                float(snapshot.borrowing_balance or 0.0),  # Float-only policy
                float(snapshot.interest_balance or 0.0),   # Float-only policy
                snapshot.created_at or datetime.now()
            ))
        
        async with self._pool.acquire() as conn:
            await conn.executemany(query, batch_data)
        
        return len(snapshots)
    
    async def get_latest_balance_snapshots(
        self,
        exchange_name: Optional[str] = None,
        asset_name: Optional[str] = None
    ) -> List[BalanceSnapshot]:
        """
        Get latest balance snapshots with float conversion.
        
        Args:
            exchange_name: Filter by exchange (optional)
            asset_name: Filter by asset (optional)
            
        Returns:
            List of BalanceSnapshot objects with float values
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        
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
                   bs.timestamp, bs.created_at
            FROM balance_snapshots bs
            JOIN exchanges e ON bs.exchange_id = e.id
            {where_clause}
            ORDER BY bs.exchange_id, bs.asset_name, bs.timestamp DESC
        """
        
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        snapshots = [
            BalanceSnapshot(
                id=row['id'],
                exchange_id=row['exchange_id'],
                asset_name=row['asset_name'],
                available_balance=float(row['available_balance']),    # Float-only policy
                locked_balance=float(row['locked_balance']),          # Float-only policy
                frozen_balance=float(row['frozen_balance']) if row['frozen_balance'] else None,
                borrowing_balance=float(row['borrowing_balance']) if row['borrowing_balance'] else None,
                interest_balance=float(row['interest_balance']) if row['interest_balance'] else None,
                timestamp=row['timestamp'],
                created_at=row['created_at']
            )
            for row in rows
        ]
        
        return snapshots
    
    # =============================================================================
    # FUNDING RATE OPERATIONS (Float-Only)
    # =============================================================================
    
    async def insert_funding_rate_snapshots_batch(self, snapshots: List[FundingRateSnapshot]) -> int:
        """
        Insert funding rate snapshots with float-only policy and constraint validation.
        
        Args:
            snapshots: List of FundingRateSnapshot objects
            
        Returns:
            Number of records inserted/updated
        """
        if not snapshots or not self._pool:
            return 0
        
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
        
        # Prepare data with float-only policy and constraint validation
        batch_data = []
        for snapshot in snapshots:
            # Validate funding_time constraint (must be > 0)
            funding_time = snapshot.funding_time
            if funding_time is None or funding_time <= 0:
                # Generate valid funding_time (current time + 8 hours in milliseconds)
                funding_time = int(time.time() * 1000) + (8 * 60 * 60 * 1000)
            
            batch_data.append((
                snapshot.timestamp,
                snapshot.symbol_id,
                float(snapshot.funding_rate),    # Float-only policy
                funding_time,
                snapshot.next_funding_time,
                snapshot.created_at or datetime.now()
            ))
        
        async with self._pool.acquire() as conn:
            await conn.executemany(query, batch_data)
        
        return len(snapshots)
    
    async def insert_trade_snapshot(self, snapshot: TradeSnapshot) -> int:
        """
        Insert single trade snapshot with float-only policy.
        
        Args:
            snapshot: TradeSnapshot to insert
            
        Returns:
            Database ID of inserted record
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        
        query = """
            INSERT INTO trade_snapshots (
                symbol_id, price, quantity, side, trade_id, timestamp,
                quote_quantity, is_buyer, is_maker, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING id
        """
        
        async with self._pool.acquire() as conn:
            record_id = await conn.fetchval(
                query,
                snapshot.symbol_id,
                float(snapshot.price),        # Float-only policy
                float(snapshot.quantity),     # Float-only policy
                snapshot.side,
                snapshot.trade_id,
                snapshot.timestamp,
                float(snapshot.quote_quantity) if snapshot.quote_quantity else None,  # Float-only policy
                snapshot.is_buyer,
                snapshot.is_maker,
                snapshot.created_at or datetime.now()
            )
        
        return record_id
    
    async def insert_trade_snapshots_batch(self, snapshots: List[TradeSnapshot]) -> int:
        """
        Insert multiple trade snapshots with deduplication and float-only policy.
        
        Args:
            snapshots: List of TradeSnapshot objects
            
        Returns:
            Number of records inserted
        """
        if not snapshots or not self._pool:
            return 0
        
        # Deduplication
        unique_snapshots = {}
        for snapshot in snapshots:
            key = (snapshot.symbol_id, snapshot.timestamp, snapshot.trade_id)
            unique_snapshots[key] = snapshot
        
        deduplicated_snapshots = list(unique_snapshots.values())
        
        query = """
            INSERT INTO trade_snapshots (
                symbol_id, price, quantity, side, trade_id, timestamp,
                quote_quantity, is_buyer, is_maker, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (symbol_id, timestamp, trade_id)
            DO UPDATE SET
                price = EXCLUDED.price,
                quantity = EXCLUDED.quantity,
                side = EXCLUDED.side,
                quote_quantity = EXCLUDED.quote_quantity,
                is_buyer = EXCLUDED.is_buyer,
                is_maker = EXCLUDED.is_maker,
                created_at = EXCLUDED.created_at
        """
        
        count = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for snapshot in deduplicated_snapshots:
                    await conn.execute(
                        query,
                        snapshot.symbol_id,
                        float(snapshot.price),        # Float-only policy
                        float(snapshot.quantity),     # Float-only policy
                        snapshot.side,
                        snapshot.trade_id,
                        snapshot.timestamp,
                        float(snapshot.quote_quantity) if snapshot.quote_quantity else None,  # Float-only policy
                        snapshot.is_buyer,
                        snapshot.is_maker,
                        snapshot.created_at or datetime.now()
                    )
                    count += 1
        
        return count
    
    async def get_recent_trades(
        self,
        exchange_name: Optional[str] = None,
        symbol_base: Optional[str] = None,
        symbol_quote: Optional[str] = None,
        minutes_back: int = 60,
        limit: int = 1000
    ) -> List[TradeSnapshot]:
        """
        Get recent trades with float conversion.
        
        Args:
            exchange_name: Filter by exchange (optional)
            symbol_base: Filter by base asset (optional)
            symbol_quote: Filter by quote asset (optional)
            minutes_back: How many minutes of recent trades to retrieve
            limit: Maximum records to return
            
        Returns:
            List of TradeSnapshot objects with float values
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        
        timestamp_from = datetime.utcnow() - timedelta(minutes=minutes_back)
        
        # Build dynamic WHERE clause
        where_conditions = ["ts.timestamp >= $1"]
        params = [timestamp_from]
        param_counter = 2
        
        if exchange_name:
            where_conditions.append(f"e.enum_value = ${param_counter}")
            params.append(exchange_name.upper())
            param_counter += 1
        
        if symbol_base:
            where_conditions.append(f"s.symbol_base = ${param_counter}")
            params.append(symbol_base.upper())
            param_counter += 1
        
        if symbol_quote:
            where_conditions.append(f"s.symbol_quote = ${param_counter}")
            params.append(symbol_quote.upper())
            param_counter += 1
        
        params.append(limit)
        
        where_clause = " AND ".join(where_conditions)
        
        query = f"""
            SELECT ts.id, ts.symbol_id, ts.price, ts.quantity, ts.side,
                   ts.trade_id, ts.timestamp, ts.quote_quantity, ts.is_buyer, ts.is_maker,
                   ts.created_at
            FROM trade_snapshots ts
            JOIN symbols s ON ts.symbol_id = s.id
            JOIN exchanges e ON s.exchange_id = e.id
            WHERE {where_clause}
            ORDER BY ts.timestamp DESC, ts.id DESC
            LIMIT ${param_counter}
        """
        
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        snapshots = [
            TradeSnapshot(
                id=row['id'],
                symbol_id=row['symbol_id'],
                price=float(row['price']),        # Float-only policy
                quantity=float(row['quantity']),  # Float-only policy
                side=row['side'],
                trade_id=row['trade_id'],
                timestamp=row['timestamp'],
                quote_quantity=float(row['quote_quantity']) if row['quote_quantity'] else None,  # Float-only policy
                is_buyer=row['is_buyer'],
                is_maker=row['is_maker'],
                created_at=row['created_at']
            )
            for row in rows
        ]
        
        return snapshots
    
    # =============================================================================
    # UTILITY AND STATISTICS OPERATIONS
    # =============================================================================
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive database statistics for monitoring.
        
        Returns:
            Dictionary with database statistics across all tables
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        
        stats = {}
        
        # Book ticker statistics
        query = """
            SELECT 
                COUNT(*) as total_book_tickers,
                COUNT(DISTINCT symbol_id) as unique_symbols_with_tickers,
                MIN(timestamp) as earliest_book_ticker,
                MAX(timestamp) as latest_book_ticker
            FROM book_ticker_snapshots
        """
        
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query)
            stats['book_tickers'] = {
                'total_snapshots': row['total_book_tickers'],
                'unique_symbols': row['unique_symbols_with_tickers'],
                'earliest_timestamp': row['earliest_book_ticker'],
                'latest_timestamp': row['latest_book_ticker']
            }
            
            # Balance statistics
            query = """
                SELECT 
                    COUNT(*) as total_balance_snapshots,
                    COUNT(DISTINCT exchange_id) as unique_exchanges_with_balances,
                    COUNT(DISTINCT asset_name) as unique_assets,
                    MIN(timestamp) as earliest_balance,
                    MAX(timestamp) as latest_balance
                FROM balance_snapshots
            """
            
            row = await conn.fetchrow(query)
            stats['balances'] = {
                'total_snapshots': row['total_balance_snapshots'],
                'unique_exchanges': row['unique_exchanges_with_balances'],
                'unique_assets': row['unique_assets'],
                'earliest_timestamp': row['earliest_balance'],
                'latest_timestamp': row['latest_balance']
            }
            
            # Trade statistics
            query = """
                SELECT 
                    COUNT(*) as total_trades,
                    COUNT(DISTINCT symbol_id) as unique_symbols_with_trades,
                    MIN(timestamp) as earliest_trade,
                    MAX(timestamp) as latest_trade
                FROM trade_snapshots
            """
            
            row = await conn.fetchrow(query)
            stats['trades'] = {
                'total_snapshots': row['total_trades'],
                'unique_symbols': row['unique_symbols_with_trades'],
                'earliest_timestamp': row['earliest_trade'],
                'latest_timestamp': row['latest_trade']
            }
            
            # Funding rate statistics
            query = """
                SELECT 
                    COUNT(*) as total_funding_rates,
                    COUNT(DISTINCT symbol_id) as unique_symbols_with_funding,
                    MIN(timestamp) as earliest_funding,
                    MAX(timestamp) as latest_funding
                FROM funding_rate_snapshots
            """
            
            row = await conn.fetchrow(query)
            stats['funding_rates'] = {
                'total_snapshots': row['total_funding_rates'],
                'unique_symbols': row['unique_symbols_with_funding'],
                'earliest_timestamp': row['earliest_funding'],
                'latest_timestamp': row['latest_funding']
            }
        
        # Add cache statistics  
        from db.cache_operations import get_cache_stats
        cache_stats = get_cache_stats()
        stats['cache'] = {
            'hit_ratio': cache_stats.hit_ratio,
            'avg_lookup_time_us': cache_stats.avg_lookup_time_us,
            'cache_size': cache_stats.cache_size,
            'total_requests': cache_stats.total_requests
        }
        
        # Add connection pool statistics
        stats['connection_pool'] = {
            'size': self._pool.get_size(),
            'max_size': self._pool.get_max_size(),
            'min_size': self._pool.get_min_size(),
            'idle_size': self._pool.get_idle_size()
        }
        
        return stats
    
    async def cleanup_old_data(self, days_to_keep: int = 7) -> Dict[str, int]:
        """
        Clean up old data across all tables to manage database size.
        
        Args:
            days_to_keep: Number of days of data to retain
            
        Returns:
            Dictionary with count of records deleted per table
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        cleanup_results = {}
        
        tables_to_cleanup = [
            'book_ticker_snapshots',
            'trade_snapshots', 
            'balance_snapshots',
            'funding_rate_snapshots'
        ]
        
        async with self._pool.acquire() as conn:
            for table in tables_to_cleanup:
                query = f"DELETE FROM {table} WHERE created_at < $1"
                
                try:
                    result = await conn.execute(query, cutoff_date)
                    count = int(result.split()[-1])  # Extract count from "DELETE N"
                    cleanup_results[table] = count
                    
                    if count > 0:
                        self._logger.info(f"Cleaned {count} old records from {table}")
                        
                except Exception as e:
                    self._logger.error(f"Failed to cleanup {table}: {e}")
                    cleanup_results[table] = 0
        
        return cleanup_results
    
    async def ensure_exchanges_populated(self) -> None:
        """
        Ensure all ExchangeEnum values are present in the database.
        Creates missing exchanges with default configurations.
        """
        # Get existing exchanges from cache
        existing_exchanges = self.get_all_exchanges()
        existing_enum_values = {ex.enum_value for ex in existing_exchanges}
        
        # Check each ExchangeEnum value
        for exchange_enum in ExchangeEnum:
            enum_value = str(exchange_enum.value)
            
            if enum_value not in existing_enum_values:
                self._logger.info(f"Creating missing exchange for {enum_value}")
                
                # Create exchange with defaults
                exchange = Exchange.from_exchange_enum(exchange_enum)
                await self.insert_exchange(exchange)
    
    # =============================================================================
    # PERFORMANCE MONITORING
    # =============================================================================
    
    
    def reset_cache_stats(self) -> None:
        """Reset cache performance statistics."""
        with self._cache_lock:
            self._cache_stats = {
                'hits': 0,
                'misses': 0,
                'total_requests': 0,
                'avg_lookup_time_ns': 0.0
            }
            self._lookup_times.clear()
    
    async def force_cache_refresh(self) -> None:
        """Force immediate cache refresh."""
        await self._refresh_cache()
    
    @property
    def pool(self) -> asyncpg.Pool:
        """Get database connection pool."""
        if self._pool is None:
            raise RuntimeError("DatabaseManager not initialized. Call initialize() first.")
        return self._pool
    
    @property
    def is_initialized(self) -> bool:
        """Check if DatabaseManager is initialized."""
        return self._pool is not None


# Global instance
_database_manager: Optional[DatabaseManager] = None


def get_database_manager() -> DatabaseManager:
    """
    Get global DatabaseManager singleton instance.
    
    Returns:
        DatabaseManager singleton instance
    """
    global _database_manager
    if _database_manager is None:
        _database_manager = DatabaseManager()
    return _database_manager


async def initialize_database_manager() -> None:
    """
    Initialize global DatabaseManager with configuration.
    
    Follows PROJECT_GUIDES.md requirements for initialization.
    """
    # Initialize database manager (gets config internally)
    db_manager = get_database_manager()
    await db_manager.initialize()


async def close_database_manager() -> None:
    """Close global DatabaseManager."""
    global _database_manager
    if _database_manager is not None:
        await _database_manager.close()
        _database_manager = None