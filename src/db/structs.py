"""
Database-related data structures.

Centralized database configuration and data structures following SOLID principles.
All database-related structures should be defined here.
"""

import msgspec


class DatabaseConfig(msgspec.Struct):
    """
    Database configuration structure.
    
    Maps to the database section in config.yaml.
    """
    host: str
    port: int
    database: str
    username: str
    password: str
    
    # Pool settings
    min_pool_size: int = 5
    max_pool_size: int = 20
    max_queries: int = 50000
    max_inactive_connection_lifetime: float = 300.0
    command_timeout: float = 10.0
    
    # Performance settings
    statement_cache_size: int = 1024
    enable_asyncpg_record: bool = True
    enable_connection_logging: bool = False
    
    def get_dsn(self) -> str:
        """
        Get PostgreSQL connection DSN.
        
        Returns:
            PostgreSQL connection string
        """
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"