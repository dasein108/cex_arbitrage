"""
Data Collector Configuration Management

Loads and validates configuration for the data collection system.
Leverages the core configuration manager for consistent config handling.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from structs.common import Symbol, AssetName
from core.config.config_manager import HftConfig


@dataclass
class DatabaseConfig:
    """Database configuration for the data collector."""
    host: str
    port: int
    database: str
    username: str
    password: str
    
    def get_dsn(self) -> str:
        """Get PostgreSQL connection DSN."""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class AnalyticsConfig:
    """Analytics configuration for real-time opportunity detection."""
    arbitrage_threshold: float
    volume_threshold: float
    spread_alert_threshold: float


@dataclass
class DataCollectorConfig:
    """Main configuration for the data collector."""
    enabled: bool
    snapshot_interval: float  # seconds
    analytics_interval: float  # seconds
    database: DatabaseConfig
    exchanges: List[str]
    analytics: AnalyticsConfig
    symbols: List[Symbol]


class ConfigManager:
    """
    Configuration manager for the data collector.
    
    Leverages the core HftConfig for consistent configuration handling.
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize configuration manager.
        
        Args:
            config_path: Path to the YAML configuration file (for compatibility)
        """
        # Use the core configuration manager which already handles everything
        self._core_config = HftConfig()
        self._data_collector_config: Optional[DataCollectorConfig] = None
    
    def load_config(self) -> DataCollectorConfig:
        """
        Load and parse configuration using the core config manager.
        
        Returns:
            DataCollectorConfig instance
            
        Raises:
            ValueError: If configuration is invalid
        """
        # The core config is already loaded by HftConfig singleton
        # Parse data collector configuration from it
        self._data_collector_config = self._parse_data_collector_config()
        
        return self._data_collector_config
    
    def _parse_data_collector_config(self) -> DataCollectorConfig:
        """
        Parse data collector configuration from core config manager.
        
        Returns:
            DataCollectorConfig instance
        """
        # Get raw config data from core manager
        raw_config = self._core_config._config_data
        
        # Get data_collector section or use defaults
        dc_config = raw_config.get("data_collector", self._get_default_data_collector_config())
        
        # Parse database config from main database section
        db_config = self._parse_database_config(raw_config)
        
        # Parse analytics config
        analytics_data = dc_config.get("analytics", {})
        analytics_config = AnalyticsConfig(
            arbitrage_threshold=analytics_data.get("arbitrage_threshold", 0.05),
            volume_threshold=analytics_data.get("volume_threshold", 1000),
            spread_alert_threshold=analytics_data.get("spread_alert_threshold", 0.1)
        )
        
        # Parse symbols from arbitrage pairs
        symbols = self._parse_symbols(raw_config)
        
        return DataCollectorConfig(
            enabled=dc_config.get("enabled", True),
            snapshot_interval=dc_config.get("snapshot_interval", 0.5),
            analytics_interval=dc_config.get("analytics_interval", 10),
            database=db_config,
            exchanges=dc_config.get("exchanges", ["mexc", "gateio"]),
            analytics=analytics_config,
            symbols=symbols
        )
    
    def _parse_database_config(self, raw_config: Dict[str, Any]) -> DatabaseConfig:
        """
        Parse database configuration from main database section.
        
        Args:
            raw_config: Complete configuration dictionary
            
        Returns:
            DatabaseConfig instance
        """
        db_data = raw_config.get("database", {})
        return DatabaseConfig(
            host=db_data.get("host", "localhost"),
            port=int(db_data.get("port", 5432)),
            database=db_data.get("database", "cex_arbitrage"),
            username=db_data.get("username", "arbitrage_user"),
            password=db_data.get("password", "")
        )
    
    def _parse_symbols(self, raw_config: Dict[str, Any]) -> List[Symbol]:
        """
        Parse symbols from arbitrage pairs configuration.
        
        Args:
            raw_config: Complete configuration dictionary
            
        Returns:
            List of Symbol objects
        """
        symbols = []
        arbitrage_config = raw_config.get("arbitrage", {})
        pairs = arbitrage_config.get("arbitrage_pairs", [])
        
        for pair in pairs:
            if pair.get("is_enabled", True):
                base_asset = pair.get("base_asset", "")
                quote_asset = pair.get("quote_asset", "")
                
                if base_asset and quote_asset:
                    symbol = Symbol(
                        base=AssetName(base_asset),
                        quote=AssetName(quote_asset),
                        is_futures=False
                    )
                    symbols.append(symbol)
        
        # If no symbols found in arbitrage pairs, add some defaults
        if not symbols:
            default_symbols = [
                ("BTC", "USDT"),
                ("ETH", "USDT"),
                ("BNB", "USDT")
            ]
            
            for base, quote in default_symbols:
                symbol = Symbol(
                    base=AssetName(base),
                    quote=AssetName(quote),
                    is_futures=False
                )
                symbols.append(symbol)
        
        return symbols
    
    def _get_default_data_collector_config(self) -> Dict[str, Any]:
        """
        Get default data collector configuration.
        
        Returns:
            Default configuration dictionary
        """
        return {
            "enabled": True,
            "snapshot_interval": 1,  # seconds
            "analytics_interval": 10,  # seconds
            "exchanges": ["mexc", "gateio"],
            "analytics": {
                "arbitrage_threshold": 0.05,  # 5%
                "volume_threshold": 1000,  # USD
                "spread_alert_threshold": 0.1  # 10%
            }
        }
    
    def get_config(self) -> Optional[DataCollectorConfig]:
        """
        Get loaded configuration.
        
        Returns:
            DataCollectorConfig instance if loaded, None otherwise
        """
        return self._data_collector_config
    
    def validate_config(self) -> bool:
        """
        Validate the loaded configuration.
        
        Returns:
            True if configuration is valid
            
        Raises:
            ValueError: If configuration is invalid
        """
        if not self._data_collector_config:
            raise ValueError("Configuration not loaded")
        
        config = self._data_collector_config
        
        # Validate snapshot interval
        if config.snapshot_interval <= 0:
            raise ValueError("snapshot_interval must be positive")
        
        # Validate analytics interval
        if config.analytics_interval <= 0:
            raise ValueError("analytics_interval must be positive")
        
        # Validate database config
        if not config.database.host:
            raise ValueError("Database host cannot be empty")
        
        if config.database.port <= 0 or config.database.port > 65535:
            raise ValueError("Database port must be between 1 and 65535")
        
        # Validate exchanges
        if not config.exchanges:
            raise ValueError("At least one exchange must be configured")
        
        # Use configured exchanges from core config
        configured_exchanges = self._core_config.get_configured_exchanges()
        for exchange in config.exchanges:
            if exchange.lower() not in configured_exchanges:
                raise ValueError(f"Unsupported exchange: {exchange}. Available: {configured_exchanges}")
        
        # Validate symbols
        if not config.symbols:
            raise ValueError("At least one symbol must be configured")
        
        return True


def load_data_collector_config(config_path: str = "config.yaml") -> DataCollectorConfig:
    """
    Convenience function to load data collector configuration.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        DataCollectorConfig instance
    """
    manager = ConfigManager(config_path)
    config = manager.load_config()
    manager.validate_config()
    return config