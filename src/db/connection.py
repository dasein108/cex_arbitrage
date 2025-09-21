"""
Database Connection Management

High-performance asyncpg connection pool manager optimized for HFT requirements.
Provides singleton pattern for global database access with connection pooling.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
import asyncpg

from .structs import DatabaseConfig


class DatabaseManager:
    """
    Singleton database manager with asyncpg connection pooling.
    
    Optimized for high-frequency database operations with:
    - Connection pooling for minimal latency
    - Prepared statement caching
    - Automatic reconnection handling
    - HFT-compliant performance settings
    """
    
    _instance: Optional["DatabaseManager"] = None
    _pool: Optional[asyncpg.Pool] = None
    _config: Optional[DatabaseConfig] = None
    _logger = logging.getLogger(__name__)
    
    def __new__(cls) -> "DatabaseManager":
        """Singleton pattern implementation."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def initialize(self, config: DatabaseConfig) -> None:
        """
        Initialize database connection pool.
        
        Args:
            config: Database configuration
            
        Raises:
            ConnectionError: If unable to establish database connection
        """
        if self._pool is not None:
            self._logger.warning("Database manager already initialized")
            return
        
        self._config = config
        
        try:
            self._logger.info(f"Initializing database connection pool to {config.host}:{config.port}/{config.database}")
            
            # Create connection pool with HFT-optimized settings
            self._pool = await asyncpg.create_pool(
                dsn=config.get_dsn(),
                min_size=config.min_pool_size,
                max_size=config.max_pool_size,
                max_queries=config.max_queries,
                max_inactive_connection_lifetime=config.max_inactive_connection_lifetime,
                command_timeout=config.command_timeout,
                statement_cache_size=config.statement_cache_size,
                # Performance optimizations
                server_settings={
                    'jit': 'off',  # Disable JIT for consistent latency
                    'application_name': 'cex_arbitrage_hft'
                }
            )
            
            # Test connection
            async with self._pool.acquire() as conn:
                version = await conn.fetchval('SELECT version()')
                self._logger.info(f"Database connection established: {version}")
                
        except Exception as e:
            self._logger.error(f"Failed to initialize database connection pool: {e}")
            raise ConnectionError(f"Database initialization failed: {e}")
    
    async def close(self) -> None:
        """
        Close database connection pool.
        """
        if self._pool is not None:
            self._logger.info("Closing database connection pool")
            await self._pool.close()
            self._pool = None
            self._config = None
    
    @property
    def pool(self) -> asyncpg.Pool:
        """
        Get database connection pool.
        
        Returns:
            asyncpg.Pool instance
            
        Raises:
            RuntimeError: If database manager not initialized
        """
        if self._pool is None:
            raise RuntimeError("Database manager not initialized. Call initialize() first.")
        return self._pool
    
    @property
    def is_initialized(self) -> bool:
        """
        Check if database manager is initialized.
        
        Returns:
            True if initialized, False otherwise
        """
        return self._pool is not None
    
    async def execute(self, query: str, *args) -> str:
        """
        Execute a query and return the result.
        
        Args:
            query: SQL query
            *args: Query parameters
            
        Returns:
            Query execution result
        """
        async with self.pool.acquire() as conn:
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
        async with self.pool.acquire() as conn:
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
        async with self.pool.acquire() as conn:
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
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)
    
    async def executemany(self, query: str, args_list: list) -> None:
        """
        Execute a query multiple times with different parameters.
        
        Optimized for batch inserts with minimal overhead.
        
        Args:
            query: SQL query
            args_list: List of parameter tuples
        """
        async with self.pool.acquire() as conn:
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
        async with self.pool.acquire() as conn:
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


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """
    Get global database manager instance.
    
    Returns:
        DatabaseManager singleton instance
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


async def initialize_database(config: DatabaseConfig) -> None:
    """
    Initialize global database manager.
    
    Args:
        config: Database configuration
    """
    db_manager = get_db_manager()
    await db_manager.initialize(config)


async def close_database() -> None:
    """
    Close global database manager.
    """
    global _db_manager
    if _db_manager is not None:
        await _db_manager.close()
        _db_manager = None