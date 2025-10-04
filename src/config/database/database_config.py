"""
Database configuration manager.

Provides specialized configuration management for database settings including:
- Connection configuration
- Pool settings  
- Performance optimization
- Data collector configuration integration
"""

import os
import logging
from typing import Dict, Any, Optional, List
from ..structs import DatabaseConfig, AnalyticsConfig, DataCollectorConfig
from infrastructure.exceptions.exchange import ConfigurationError


class DatabaseConfigManager:
    """Manages database-specific configuration settings."""
    
    def __init__(self, config_data: Dict[str, Any]):
        self.config_data = config_data
        self._database_config: Optional[DatabaseConfig] = None
        self._data_collector_config: Optional[DataCollectorConfig] = None
        self._logger = logging.getLogger(__name__)
    
    def get_database_config(self) -> DatabaseConfig:
        """
        Get database configuration.
        
        Returns:
            DatabaseConfig struct with database settings
            
        Raises:
            KeyError: If required config keys are missing
            ValueError: If config values are invalid
        """
        if self._database_config is None:
            # Trust config structure, extract from nested sections
            db = self.config_data['database']
            pool = db['pool']
            perf = db['performance']
            
            self._database_config = DatabaseConfig(
                host=db['host'],
                port=int(db['port']),
                database=db['database'],
                username=db['username'],
                password=self._get_database_password(),
                min_pool_size=int(pool['min_size']),
                max_pool_size=int(pool['max_size']),
                max_queries=int(pool['max_queries']),
                max_inactive_connection_lifetime=int(pool['max_inactive_connection_lifetime']),
                command_timeout=int(pool['command_timeout']),
                statement_cache_size=int(perf['statement_cache_size'])
            )
        return self._database_config
    
    def get_data_collector_config(self) -> DataCollectorConfig:
        """
        Get data collector configuration with database integration.
        
        Returns:
            DataCollectorConfig struct with complete data collection settings
            
        Raises:
            ConfigurationError: If data collector configuration is invalid
        """
        if self._data_collector_config is None:
            self._data_collector_config = self._build_data_collector_config()
        return self._data_collector_config
    
    
    def _build_data_collector_config(self) -> DataCollectorConfig:
        """
        Build data collector configuration from config data.
        
        This preserves the existing data collector functionality that was 
        recently consolidated into the main config manager.
        """
        # Import here to avoid circular imports

        # Get data_collector section or use defaults
        dc_config = self.config_data.get("data_collector", self._get_default_data_collector_config())
        
        # Parse database config
        db_config = self.get_database_config()
        
        # Parse analytics config
        analytics_data = dc_config.get("analytics", {})
        analytics_config = AnalyticsConfig(
            arbitrage_threshold=float(analytics_data.get("arbitrage_threshold", 0.05)),
            volume_threshold=float(analytics_data.get("volume_threshold", 1000)),
            spread_alert_threshold=float(analytics_data.get("spread_alert_threshold", 0.1))
        )
        
        # Parse symbols from arbitrage pairs
        symbols = self._parse_symbols_for_data_collector()
        
        # Parse exchanges directly to ExchangeEnum (no normalization needed)
        exchanges = []
        exchange_names = dc_config.get("exchanges", [])
        for exchange_name in exchange_names:
            try:
                from utils.exchange_utils import get_exchange_enum
                exchange_enum = get_exchange_enum(exchange_name)
                exchanges.append(exchange_enum)
            except ValueError:
                self._logger.warning(f"Unknown exchange '{exchange_name}', skipping")
        
        try:
            return DataCollectorConfig(
                enabled=bool(dc_config.get("enabled", True)),
                snapshot_interval=float(dc_config.get("snapshot_interval", 0.5)),
                analytics_interval=float(dc_config.get("analytics_interval", 10)),
                database=db_config,
                exchanges=exchanges,
                analytics=analytics_config,
                symbols=symbols,
                collect_trades=bool(dc_config.get("collect_trades", True)),
                trade_snapshot_interval=float(dc_config.get("trade_snapshot_interval", 1.0))
            )
        except (ValueError, TypeError) as e:
            raise ConfigurationError(f"Failed to parse data collector configuration: {e}", "data_collector") from e
    
    def _get_database_password(self) -> str:
        """Get database password from config or environment variable."""
        # Check if password is in config (for non-production environments)
        db_config = self.config_data.get('database', {})
        if 'password' in db_config and db_config['password']:
            return db_config['password']
        
        # Otherwise require environment variable (production)
        try:
            return os.environ['DB_PASSWORD']
        except KeyError:
            raise ValueError("DB_PASSWORD environment variable is required but not set. Please set it with: export DB_PASSWORD=your_password")
    
    def _parse_symbols_for_data_collector(self) -> List:
        """
        Parse symbols from arbitrage pairs configuration for data collector.
        
        This preserves the existing logic that was in the main config manager.
        """
        from exchanges.structs.common import Symbol
        
        symbols = []
        arbitrage_config = self.config_data.get("arbitrage", {})
        pairs = arbitrage_config.get("arbitrage_pairs", [])
        
        for pair in pairs:
            if pair.get("is_enabled", True):
                base_asset = pair.get("base_asset", "")
                quote_asset = pair.get("quote_asset", "")
                
                if base_asset and quote_asset:
                    symbol = Symbol(base_asset, quote_asset)
                    symbols.append(symbol)
        
        # If no symbols found in arbitrage pairs, add defaults
        if not symbols:
            default_symbols = [
                ("BTC", "USDT"),
                ("ETH", "USDT"),
                ("BNB", "USDT")
            ]
            
            for base, quote in default_symbols:
                symbol = Symbol(base, quote)
                symbols.append(symbol)
        
        return symbols
    
    def _get_default_data_collector_config(self) -> Dict[str, Any]:
        """Get default data collector configuration."""
        return {
            "enabled": True,
            "snapshot_interval": 1,  # seconds
            "analytics_interval": 10,  # seconds
            "exchanges": ["mexc", "gateio"],  # Direct enum values
            "collect_trades": True,
            "trade_snapshot_interval": 1.0,
            "analytics": {
                "arbitrage_threshold": 0.05,  # 5%
                "volume_threshold": 1000,  # USD
                "spread_alert_threshold": 0.1  # 10%
            }
        }
    
    def validate_database_config(self) -> None:
        """
        Validate database configuration for HFT requirements.
        
        Raises:
            ValueError: If configuration violates HFT requirements
        """
        config = self.get_database_config()
        
        # Trust config is correct, but enforce HFT requirements - fail fast
        if config.max_pool_size > 50:
            raise ValueError(f"max_pool_size {config.max_pool_size} > 50 violates HFT requirements")
        
        if config.min_pool_size < 5:
            raise ValueError(f"min_pool_size {config.min_pool_size} < 5 violates HFT requirements")
        
        if config.max_queries < 10000:
            raise ValueError(f"max_queries {config.max_queries} < 10000 violates HFT requirements")
        
        if config.max_inactive_connection_lifetime > 600:
            raise ValueError(f"max_inactive_connection_lifetime {config.max_inactive_connection_lifetime} > 600 violates HFT requirements")
        
        if config.command_timeout > 30000:
            raise ValueError(f"command_timeout {config.command_timeout} > 30000ms violates HFT requirements")
    
    def get_connection_info(self) -> Dict[str, Any]:
        """
        Get database connection information for diagnostics.
        
        Returns:
            Dictionary with connection information (passwords masked)
        """
        config = self.get_database_config()
        
        return {
            "host": config.host,
            "port": config.port,
            "database": config.database,
            "username": config.username,
            "password_configured": bool(config.password),
            "pool_settings": {
                "min_pool_size": config.min_pool_size,
                "max_pool_size": config.max_pool_size,
                "max_queries": config.max_queries,
                "max_inactive_connection_lifetime": config.max_inactive_connection_lifetime
            },
            "performance_settings": {
                "command_timeout": config.command_timeout,
                "statement_cache_size": config.statement_cache_size
            }
        }