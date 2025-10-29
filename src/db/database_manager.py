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
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Any, Tuple
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
    Simplified database manager with minimal lookup table.
    
    Follows PROJECT_GUIDES.md requirements:
    - Float-Only Data Policy for all numerical operations
    - Struct-First Data Policy with msgspec.Struct throughout
    - Minimal LOC with simple (ExchangeEnum, Symbol) -> symbol_id lookup
    - Auto-resolution: create missing exchanges/symbols automatically
    """
    
    _instance: Optional["DatabaseManager"] = None
    _logger = logging.getLogger(__name__)
    
    def __new__(cls) -> "DatabaseManager":
        """Singleton pattern implementation."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize DatabaseManager with simple lookup table."""
        if hasattr(self, '_initialized'):
            return
            
        self._pool: Optional[asyncpg.Pool] = None
        self._config = None
        
        # Simple lookup table: (exchange_enum, base, quote) -> symbol_id
        self._lookup_table: Dict[Tuple[str, str, str], int] = {}
        
        self._initialized = True
        self._logger.info("DatabaseManager initialized with simple lookup table")

    def _resolve_symbol_id(self, exchange_enum: ExchangeEnum, symbol: Symbol) -> int:
        """
        Core resolution method: lookup symbol_id or create new records.
        
        Args:
            exchange_enum: Exchange enum (e.g., ExchangeEnum.MEXC_SPOT)
            symbol: Symbol object with base/quote
            
        Returns:
            symbol_id from database
        """
        key = (exchange_enum.value, symbol.base.upper(), symbol.quote.upper())
        
        # Try lookup first
        if key in self._lookup_table:
            return self._lookup_table[key]
        
        # Not found -> create new records synchronously
        # This is called from async context, so we need to handle it properly
        symbol_id = asyncio.create_task(self._create_symbol_record(exchange_enum, symbol))
        return symbol_id
    
    async def _create_symbol_record(self, exchange_enum: ExchangeEnum, symbol: Symbol) -> int:
        """
        Create new exchange and symbol records, update lookup table.
        
        Args:
            exchange_enum: Exchange enum
            symbol: Symbol object
            
        Returns:
            New symbol_id
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        
        async with self._pool.acquire() as conn:
            # Get or create exchange
            exchange_id = await self._get_or_create_exchange(conn, exchange_enum)
            
            # Create symbol
            symbol_id = await conn.fetchval(
                """
                INSERT INTO symbols (
                    exchange_id, symbol_base, symbol_quote, exchange_symbol, 
                    is_active, symbol_type
                ) VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                exchange_id,
                symbol.base.upper(),
                symbol.quote.upper(),
                f"{symbol.base}{symbol.quote}".upper(),  # Default exchange symbol format
                True,
                'SPOT'
            )
            
            # Update lookup table
            key = (exchange_enum.value, symbol.base.upper(), symbol.quote.upper())
            self._lookup_table[key] = symbol_id
            
            self._logger.info(f"Created new symbol {symbol.base}/{symbol.quote} on {exchange_enum.value} with ID {symbol_id}")
            return symbol_id
    
    async def _get_or_create_exchange(self, conn: asyncpg.Connection, exchange_enum: ExchangeEnum) -> int:
        """
        Get existing exchange_id or create new exchange.
        
        Args:
            conn: Database connection
            exchange_enum: Exchange enum
            
        Returns:
            exchange_id
        """
        # Try to get existing exchange
        exchange_id = await conn.fetchval(
            "SELECT id FROM exchanges WHERE enum_value = $1",
            exchange_enum.value
        )
        
        if exchange_id:
            return exchange_id
        
        # Create new exchange
        exchange_id = await conn.fetchval(
            """
            INSERT INTO exchanges (exchange_name, enum_value, market_type)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            exchange_enum.value.replace('_', ' ').title(),  # MEXC_SPOT -> Mexc Spot
            exchange_enum.value,
            'SPOT' if 'SPOT' in exchange_enum.value else 'FUTURES'
        )
        
        self._logger.info(f"Created new exchange {exchange_enum.value} with ID {exchange_id}")
        return exchange_id

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
            
            # Load existing symbols into lookup table
            await self._load_lookup_table()
            
            self._logger.info("DatabaseManager initialization complete")
            
        except Exception as e:
            self._logger.error(f"Database initialization failed: {e}")
            raise ConnectionError(f"Database initialization failed: {e}")
    
    async def _load_lookup_table(self) -> None:
        """
        Load existing symbols into simple lookup table.
        """
        if not self._pool:
            return
        
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT s.id, e.enum_value, s.symbol_base, s.symbol_quote
                FROM symbols s
                JOIN exchanges e ON s.exchange_id = e.id
                WHERE s.is_active = true
                """
            )
        
        for row in rows:
            key = (row['enum_value'], row['symbol_base'].upper(), row['symbol_quote'].upper())
            self._lookup_table[key] = row['id']
        
        self._logger.info(f"Loaded {len(self._lookup_table)} symbols into lookup table")
    
    async def close(self) -> None:
        """Close database connection and clear lookup table."""
        if self._pool is not None:
            self._logger.info("Closing database connection pool")
            await self._pool.close()
            self._pool = None
        
        self._lookup_table.clear()
    
    def get_symbol_id(self, exchange_enum: ExchangeEnum, symbol: Symbol) -> int:
        """
        Get symbol_id with auto-resolution for missing symbols.
        
        Args:
            exchange_enum: Exchange enum
            symbol: Symbol object
            
        Returns:
            symbol_id
        """
        # This needs to be called from async context
        # For now, we'll make it sync but this should be refactored
        key = (exchange_enum.value, symbol.base.upper(), symbol.quote.upper())
        
        if key in self._lookup_table:
            return self._lookup_table[key]
        
        # This is a limitation - we need async context for creation
        # The caller should use resolve_symbol_id_async instead
        raise RuntimeError(f"Symbol {symbol.base}/{symbol.quote} not found on {exchange_enum.value}. Use resolve_symbol_id_async() to create.")
    
    async def resolve_symbol_id_async(self, exchange_enum: ExchangeEnum, symbol: Symbol) -> int:
        """
        Async version of symbol resolution with auto-creation.
        
        Args:
            exchange_enum: Exchange enum
            symbol: Symbol object
            
        Returns:
            symbol_id (existing or newly created)
        """
        key = (exchange_enum.value, symbol.base.upper(), symbol.quote.upper())
        
        # Try lookup first
        if key in self._lookup_table:
            return self._lookup_table[key]
        
        # Create new symbol record
        return await self._create_symbol_record(exchange_enum, symbol)
    
    # =============================================================================
    # LOW-LEVEL DATABASE OPERATIONS (Consolidated from connection.py)
    # =============================================================================
    
    async def execute(self, query: str, *args) -> str:
        """
        Execute a query and return the result.
        
        Args:
            query: SQL query
            *args: Query parameters
            
        Returns:
            Query execution result
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args) -> list:
        """
        Fetch multiple rows from a query.
        
        Args:
            query: SQL query
            *args: Query parameters
            
        Returns:
            List of rows
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """
        Fetch a single row from a query.
        
        Args:
            query: SQL query
            *args: Query parameters
            
        Returns:
            Single row or None
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args) -> Any:
        """
        Fetch a single value from a query.
        
        Args:
            query: SQL query
            *args: Query parameters
            
        Returns:
            Single value or None
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *args)
    
    async def executemany(self, query: str, args_list: list) -> None:
        """
        Execute a query multiple times with different parameters.
        
        Optimized for batch inserts with minimal overhead.
        
        Args:
            query: SQL query
            args_list: List of parameter tuples
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        async with self._pool.acquire() as conn:
            await conn.executemany(query, args_list)
    
    async def copy_records_to_table(self, table_name: str, records: list, columns: list) -> int:
        """
        High-performance bulk insert using COPY command.
        
        Most efficient method for large batch inserts.
        
        Args:
            table_name: Target table name
            records: List of record tuples
            columns: List of column names
            
        Returns:
            Number of records inserted
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        async with self._pool.acquire() as conn:
            result = await conn.copy_records_to_table(
                table_name, 
                records=records,
                columns=columns
            )
            return int(result.split()[-1])  # Extract count from "COPY N"
    
    async def get_connection_stats(self) -> Dict[str, Any]:
        """
        Get connection pool statistics.
        
        Returns:
            Dictionary with pool statistics
        """
        if not self._pool:
            return {}
        
        return {
            'size': self._pool.get_size(),
            'max_size': self._pool.get_max_size(),
            'min_size': self._pool.get_min_size(),
            'idle_size': self._pool.get_idle_size(),
            'config': {
                'host': self._config.host if self._config else None,
                'database': self._config.database if self._config else None,
                'max_queries': self._config.max_queries if self._config else None
            }
        }
    
    # =============================================================================
    # SIMPLIFIED SYMBOL OPERATIONS
    # =============================================================================
    
    async def get_symbol_by_id(self, symbol_id: int) -> Optional[DBSymbol]:
        """
        Get symbol by ID from database.
        
        Args:
            symbol_id: Symbol database ID
            
        Returns:
            Symbol instance or None if not found
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        
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
        
        if not row:
            return None
        
        return DBSymbol(
            id=row['id'],
            exchange_id=row['exchange_id'],
            symbol_base=row['symbol_base'],
            symbol_quote=row['symbol_quote'],
            exchange_symbol=row['exchange_symbol'],
            is_active=row['is_active'],
            symbol_type=SymbolType[row['symbol_type']]
        )
    
    async def get_exchange_by_enum(self, exchange_enum: ExchangeEnum) -> Optional[Exchange]:
        """
        Get exchange by enum value from database.
        
        Args:
            exchange_enum: Exchange enum value
            
        Returns:
            Exchange instance or None if not found
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, exchange_name, enum_value, market_type FROM exchanges WHERE enum_value = $1",
                exchange_enum.value
            )
        
        if not row:
            return None
        
        return Exchange(
            id=row['id'],
            name=row['exchange_name'],
            enum_value=row['enum_value'],
            display_name=row['exchange_name'],
            market_type=row['market_type']
        )
    
    # =============================================================================
    # BOOK TICKER OPERATIONS (Float-Only)
    # =============================================================================
    
    async def insert_book_ticker_snapshot(self, exchange_enum: ExchangeEnum, symbol: Symbol, snapshot: BookTickerSnapshot) -> int:
        """
        Insert single book ticker snapshot with auto symbol resolution.
        
        Args:
            exchange_enum: Exchange enum
            symbol: Symbol object
            snapshot: BookTickerSnapshot to insert
            
        Returns:
            Database ID of inserted record
        """
        if not self._pool:
            raise RuntimeError("DatabaseManager not initialized")
        
        # Resolve symbol_id (create if missing)
        symbol_id = await self.resolve_symbol_id_async(exchange_enum, symbol)
        
        query = """
            INSERT INTO book_ticker_snapshots (
                symbol_id, bid_price, bid_qty, ask_price, ask_qty, timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
        """
        
        async with self._pool.acquire() as conn:
            record_id = await conn.fetchval(
                query,
                symbol_id,
                float(snapshot.bid_price),    # Ensure float type
                float(snapshot.bid_qty),      # Ensure float type
                float(snapshot.ask_price),    # Ensure float type
                float(snapshot.ask_qty),      # Ensure float type
                snapshot.timestamp
            )
        
        return record_id
    
    async def insert_book_ticker_snapshots_batch(self, exchange_enum: ExchangeEnum, symbol: Symbol, snapshots: List[BookTickerSnapshot]) -> int:
        """
        Insert multiple book ticker snapshots with HFT-optimized batch processing.
        
        Uses proper batch inserts with chunking for optimal performance targeting <5ms operations.
        Maintains existing deduplication logic and schema compatibility.
        
        Args:
            exchange_enum: Exchange enum
            symbol: Symbol object
            snapshots: List of BookTickerSnapshot objects
            
        Returns:
            Number of records inserted/updated
        """
        if not snapshots or not self._pool:
            return 0
        
        # Use existing schema with exchange, symbol_base, symbol_quote columns
        exchange_name = exchange_enum.value
        
        # Deduplication based on existing schema
        unique_snapshots = {}
        for snapshot in snapshots:
            key = (exchange_name, symbol.base.upper(), symbol.quote.upper(), snapshot.timestamp)
            unique_snapshots[key] = snapshot
        
        deduplicated_snapshots = list(unique_snapshots.values())
        
        query = """
            INSERT INTO book_ticker_snapshots (
                exchange, symbol_base, symbol_quote, bid_price, bid_qty, ask_price, ask_qty, timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (timestamp, exchange, symbol_base, symbol_quote)
            DO UPDATE SET
                bid_price = EXCLUDED.bid_price,
                bid_qty = EXCLUDED.bid_qty,
                ask_price = EXCLUDED.ask_price,
                ask_qty = EXCLUDED.ask_qty,
                created_at = NOW()
        """
        
        # Prepare batch data with float-only policy
        batch_data = []
        for snapshot in deduplicated_snapshots:
            batch_data.append((
                exchange_name,
                symbol.base.upper(),
                symbol.quote.upper(),
                float(snapshot.bid_price),    # Float-only policy
                float(snapshot.bid_qty),      # Float-only policy
                float(snapshot.ask_price),    # Float-only policy
                float(snapshot.ask_qty),      # Float-only policy
                snapshot.timestamp
            ))
        
        # Process in chunks of 10 for optimal performance as per HFT requirements
        total_inserted = 0
        chunk_size = 10
        
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for i in range(0, len(batch_data), chunk_size):
                    chunk = batch_data[i:i + chunk_size]
                    await conn.executemany(query, chunk)
                    total_inserted += len(chunk)
        
        return total_inserted
    
    async def get_latest_book_ticker_snapshots(
        self, 
        exchange: Optional[str] = None,
        symbol_base: Optional[str] = None,
        symbol_quote: Optional[str] = None,
        limit: int = 1000
    ) -> List[BookTickerSnapshot]:
        """
        Get latest book ticker snapshots with float conversion.
        
        Compatible with existing schema using exchange, symbol_base, symbol_quote columns.
        Target: <5ms per HFT requirements.
        
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
        
        # Build dynamic WHERE clause using existing schema
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
        
        params.append(limit)
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # Use existing schema directly
        query = f"""
            SELECT DISTINCT ON (exchange, symbol_base, symbol_quote)
                   id, exchange, symbol_base, symbol_quote,
                   bid_price, bid_qty, ask_price, ask_qty, 
                   timestamp, created_at
            FROM book_ticker_snapshots
            {where_clause}
            ORDER BY exchange, symbol_base, symbol_quote, timestamp DESC
            LIMIT ${param_counter}
        """
        
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        snapshots = []
        for row in rows:
            # Create compatibility BookTickerSnapshot with dummy symbol_id 
            snapshots.append(
                BookTickerSnapshot(
                    id=row['id'],
                    symbol_id=0,  # Dummy value for compatibility
                    bid_price=float(row['bid_price']),    # Float-only policy
                    bid_qty=float(row['bid_qty']),        # Float-only policy
                    ask_price=float(row['ask_price']),    # Float-only policy
                    ask_qty=float(row['ask_qty']),        # Float-only policy
                    timestamp=row['timestamp'],
                    created_at=row['created_at'],
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
        limit: Optional[int] = None
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
            
        if start_time:
            where_conditions.append(f"bts.timestamp >= ${param_counter}")
            params.append(start_time)
            param_counter += 1
            
        if end_time:
            where_conditions.append(f"bts.timestamp <= ${param_counter}")
            params.append(end_time)
            param_counter += 1
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

        limit_clause = ""
        if limit:
            limit_clause = f"LIMIT ${param_counter}"
            params.append(limit)

        # Use normalized schema with proper JOINs for data consistency
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
            {limit_clause}
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
            spread_pct = ((ask_price - bid_price) / mid_price)  if mid_price > 0 else 0.0

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
                'spread_pct': spread_pct
            })
        
        df = pd.DataFrame(data)
        
        # Set timestamp as index for time-series operations
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        
        return df
    
    # =============================================================================
    # BALANCE OPERATIONS (Float-Only, HFT-Optimized)
    # =============================================================================
    
    async def insert_balance_snapshots_batch(self, exchange_enum: ExchangeEnum, snapshots: List[BalanceSnapshot]) -> int:
        """
        Insert balance snapshots with auto exchange resolution.
        
        Args:
            exchange_enum: Exchange enum
            snapshots: List of BalanceSnapshot objects
            
        Returns:
            Number of records inserted/updated
        """
        if not snapshots or not self._pool:
            return 0
        
        # Get or create exchange_id
        async with self._pool.acquire() as conn:
            exchange_id = await self._get_or_create_exchange(conn, exchange_enum)
        
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
                exchange_id,
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
    
    async def insert_funding_rate_snapshots_batch(self, exchange_enum: ExchangeEnum, symbol: Symbol, snapshots: List[FundingRateSnapshot]) -> int:
        """
        Insert funding rate snapshots with auto symbol resolution.
        
        Args:
            exchange_enum: Exchange enum
            symbol: Symbol object
            snapshots: List of FundingRateSnapshot objects
            
        Returns:
            Number of records inserted/updated
        """
        if not snapshots or not self._pool:
            return 0
        
        # Resolve symbol_id once (create if missing)
        symbol_id = await self.resolve_symbol_id_async(exchange_enum, symbol)
        
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
            funding_time = snapshot.next_funding_time
            if funding_time is None or funding_time <= 0:
                # Generate valid funding_time (current time + 8 hours in milliseconds)
                funding_time = int(time.time() * 1000) + (8 * 60 * 60 * 1000)
            
            batch_data.append((
                snapshot.timestamp,
                symbol_id,
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
        
        # Add lookup table statistics
        stats['lookup_table'] = {
            'size': len(self._lookup_table),
            'memory_usage_bytes': sum(len(str(k)) + 8 for k in self._lookup_table.keys())  # Rough estimate
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
        if not self._pool:
            return
        
        async with self._pool.acquire() as conn:
            # Get existing exchanges
            existing_enums = await conn.fetch("SELECT enum_value FROM exchanges")
            existing_enum_values = {row['enum_value'] for row in existing_enums}
            
            # Check each ExchangeEnum value
            for exchange_enum in ExchangeEnum:
                if exchange_enum.value not in existing_enum_values:
                    await self._get_or_create_exchange(conn, exchange_enum)
                    self._logger.info(f"Created missing exchange for {exchange_enum.value}")
    
    # =============================================================================
    # UTILITY METHODS
    # =============================================================================
    
    def get_lookup_table_stats(self) -> Dict[str, Any]:
        """Get lookup table statistics."""
        return {
            'size': len(self._lookup_table),
            'entries': list(self._lookup_table.keys())[:10],  # First 10 entries for debugging
            'memory_estimate_kb': len(self._lookup_table) * 64 / 1024  # Rough estimate
        }
    
    async def refresh_lookup_table(self) -> None:
        """Manual refresh of lookup table from database."""
        await self._load_lookup_table()
        self._logger.info(f"Lookup table refreshed with {len(self._lookup_table)} entries")
    
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
    
    @property
    def lookup_table_size(self) -> int:
        """Get current lookup table size."""
        return len(self._lookup_table)


# Global instance
_database_manager: Optional[DatabaseManager] = None


async def get_database_manager() -> DatabaseManager:
    """
    Get global DatabaseManager singleton instance.
    
    Returns:
        DatabaseManager singleton instance
    """
    global _database_manager
    if _database_manager is None:
        _database_manager = DatabaseManager()
        await _database_manager.initialize()

    return _database_manager


async def initialize_database_manager() -> None:
    """
    Initialize global DatabaseManager with configuration.
    
    Follows PROJECT_GUIDES.md requirements for initialization.
    """
    # Initialize database manager (gets config internally)
    await  get_database_manager()


async def close_database_manager() -> None:
    """Close global DatabaseManager."""
    global _database_manager
    if _database_manager is not None:
        await _database_manager.close()
        _database_manager = None


# =============================================================================
# BACKWARD COMPATIBILITY ALIASES (from connection.py)
# =============================================================================

# Create aliases to maintain backward compatibility with connection.py
def get_db_manager() -> DatabaseManager:
    """
    Get global database manager instance (compatibility alias).
    
    Returns:
        DatabaseManager singleton instance
    """
    global _database_manager
    if _database_manager is None:
        raise RuntimeError("Database manager not initialized. Call initialize_database_manager() first.")
    return _database_manager

async def initialize_database(config) -> None:
    """
    Initialize global database manager and run pending migrations (compatibility alias).
    
    Args:
        config: Database configuration (compatible with both DatabaseConfig and dict)
    """
    from config.config_manager import HftConfig
    
    # Handle both DatabaseConfig objects and legacy usage patterns
    if hasattr(config, 'get_dsn'):
        # It's already a DatabaseConfig, use it directly through HftConfig
        pass
    
    # Initialize using the new pattern
    db_manager = await get_database_manager()

    # Run pending migrations automatically (from connection.py pattern)
    try:
        from .migrations import run_all_pending_migrations as run_pending_migrations
        migration_result = await run_pending_migrations()
        
        if migration_result['success']:
            if migration_result['migrations_run']:
                db_manager._logger.info(f"Applied {len(migration_result['migrations_run'])} database migrations")
        else:
            db_manager._logger.warning(f"Some migrations failed: {migration_result['migrations_failed']}")
            
    except Exception as e:
        db_manager._logger.warning(f"Migration check failed: {e} - continuing without migrations")

async def close_database() -> None:
    """
    Close global database manager (compatibility alias).
    """
    await close_database_manager()