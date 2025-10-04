# Database Configuration Specification

Complete specification for the DatabaseConfigManager that handles database connection configuration, data collection settings, and analytics integration for HFT operations.

## Overview

The **DatabaseConfigManager** provides specialized configuration management for database operations including connection pooling, performance optimization, data collection configuration, and analytics integration. Designed for HFT requirements with comprehensive validation and error handling.

## Architecture

### Core Design Principles

1. **Performance Optimization** - Connection pooling and performance settings for HFT operations
2. **Data Collection Integration** - Unified configuration for real-time data collection
3. **Analytics Configuration** - Arbitrage opportunity detection and alerting
4. **HFT Compliance** - Database settings optimized for sub-millisecond operations
5. **Environment Security** - Secure password management via environment variables
6. **Comprehensive Validation** - Type-safe access with performance requirement enforcement

### Manager Integration
```
HftConfig → DatabaseConfigManager → DatabaseConfig/DataCollectorConfig → Connection Pool
    ↓              ↓                           ↓                              ↓
Config Data → Analytics Config → Symbol Parsing → Exchange Integration → Performance Tuning
```

## DatabaseConfigManager Class Specification

### Class Definition
```python
class DatabaseConfigManager:
    """
    Manages database-specific configuration settings.
    
    Provides specialized configuration management for:
    - Database connection configuration with pool settings
    - Performance optimization for HFT operations
    - Data collector configuration integration
    - Analytics and alerting configuration
    - Comprehensive validation and error handling
    """
    
    def __init__(self, config_data: Dict[str, Any]):
        self.config_data = config_data
        self._database_config: Optional[DatabaseConfig] = None
        self._data_collector_config: Optional[DataCollectorConfig] = None
        self._logger = logging.getLogger(__name__)
```

### Database Configuration Management

#### DatabaseConfig Structure
```python
class DatabaseConfig(Struct, frozen=True):
    """Database configuration settings with connection pool parameters."""
    host: str
    port: int
    database: str
    username: str
    password: str
    
    # Connection pool settings
    min_pool_size: int = 5
    max_pool_size: int = 20
    max_queries: int = 50000
    max_inactive_connection_lifetime: int = 300  # 5 minutes
    command_timeout: int = 60  # 60 seconds
    statement_cache_size: int = 1024
    
    def get_dsn(self) -> str:
        """Generate PostgreSQL DSN (Data Source Name) connection string."""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    def validate(self) -> None:
        """Validate database configuration."""
        if not self.host:
            raise ValueError("Database host cannot be empty")
        if self.port <= 0 or self.port > 65535:
            raise ValueError("Database port must be between 1 and 65535")
        if not self.database:
            raise ValueError("Database name cannot be empty")
        if not self.username:
            raise ValueError("Database username cannot be empty")
        if self.min_pool_size <= 0:
            raise ValueError("min_pool_size must be positive")
        if self.max_pool_size <= 0:
            raise ValueError("max_pool_size must be positive")
        if self.min_pool_size > self.max_pool_size:
            raise ValueError("min_pool_size cannot be greater than max_pool_size")
        if self.command_timeout <= 0:
            raise ValueError("command_timeout must be positive")
        if self.max_queries <= 0:
            raise ValueError("max_queries must be positive")
```

#### Database Configuration Parsing
```python
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
```

### Data Collection Configuration

#### DataCollectorConfig Structure
```python
class DataCollectorConfig(Struct, frozen=True):
    """Main configuration for the data collector."""
    enabled: bool
    snapshot_interval: float  # seconds
    analytics_interval: float  # seconds
    database: DatabaseConfig
    exchanges: List['ExchangeName']
    analytics: AnalyticsConfig
    symbols: List['Symbol']  # Forward reference to avoid circular import
    collect_trades: bool = True
    trade_snapshot_interval: float = 1.0
    
    def validate(self) -> None:
        """Validate data collector configuration."""
        if self.snapshot_interval <= 0:
            raise ValueError("snapshot_interval must be positive")
        if self.trade_snapshot_interval <= 0:
            raise ValueError("trade_snapshot_interval must be positive")
        if self.analytics_interval <= 0:
            raise ValueError("analytics_interval must be positive")
        if not self.exchanges:
            raise ValueError("At least one exchange must be configured")
        if not self.symbols:
            raise ValueError("At least one symbol must be configured")
        
        # Validate sub-components
        self.database.validate()
        self.analytics.validate()
```

#### AnalyticsConfig Structure
```python
class AnalyticsConfig(Struct, frozen=True):
    """Analytics configuration for real-time opportunity detection."""
    arbitrage_threshold: float
    volume_threshold: float
    spread_alert_threshold: float
    
    def validate(self) -> None:
        """Validate analytics configuration."""
        if self.arbitrage_threshold <= 0:
            raise ValueError("arbitrage_threshold must be positive")
        if self.volume_threshold <= 0:
            raise ValueError("volume_threshold must be positive")
        if self.spread_alert_threshold <= 0:
            raise ValueError("spread_alert_threshold must be positive")
```

#### Data Collector Configuration Building

```python
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
    from exchanges.structs.common import Symbol
    from exchanges.structs.enums import ExchangeEnum

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
```

### Symbol and Exchange Integration

#### Symbol Parsing from Arbitrage Configuration
```python
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
```

#### Default Configuration
```python
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
```

## HFT Performance Validation

### Database Configuration Validation for HFT
```python
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
```

### HFT Performance Requirements
- **Connection Pool Size**: 5-50 connections (optimal for HFT throughput)
- **Query Limit**: Minimum 10,000 queries per connection
- **Connection Lifetime**: Maximum 600 seconds (10 minutes)
- **Command Timeout**: Maximum 30 seconds for database operations
- **Statement Cache**: Minimum 1,024 cached statements for performance

## Diagnostics and Monitoring

### Connection Information
```python
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
```

## Configuration Examples

### YAML Database Configuration
```yaml
database:
  host: "${DB_HOST:localhost}"
  port: 5432
  database: "${DB_NAME:arbitrage}"
  username: "${DB_USER:postgres}"
  password: "${DB_PASSWORD}"  # Environment variable required
  
  pool:
    min_size: 10
    max_size: 30
    max_queries: 50000
    max_inactive_connection_lifetime: 300  # 5 minutes
    command_timeout: 30  # 30 seconds
    
  performance:
    statement_cache_size: 2048
    enable_prepared_statements: true
    connection_pool_timeout: 10
```

### Data Collector Configuration
```yaml
data_collector:
  enabled: true
  snapshot_interval: 0.5  # 500ms for HFT
  trade_snapshot_interval: 1.0  # 1 second for trade data
  analytics_interval: 10  # 10 seconds for analytics
  
  exchanges:
    - "mexc"
    - "gateio"
    
  collect_trades: true
  
  analytics:
    arbitrage_threshold: 0.05  # 5% minimum profit
    volume_threshold: 1000  # $1000 minimum volume
    spread_alert_threshold: 0.1  # 10% spread alert
```

### Integration with Arbitrage Configuration
```yaml
arbitrage:
  arbitrage_pairs:
    - id: "btc_usdt_arb"
      base_asset: "BTC"
      quote_asset: "USDT"
      min_profit_bps: 30
      is_enabled: true
      
    - id: "eth_usdt_arb" 
      base_asset: "ETH"
      quote_asset: "USDT"
      min_profit_bps: 25
      is_enabled: true
```

## Environment Variable Integration

### Security Best Practices
```bash
# Required environment variables for production
export DB_HOST="your-database-host"
export DB_NAME="arbitrage_prod"
export DB_USER="hft_user"
export DB_PASSWORD="secure_password_here"

# Optional environment variables with defaults
export DB_PORT="5432"  # Default: 5432
export DB_SSL_MODE="require"  # Default: prefer
```

### Environment Variable Validation
```python
def _validate_environment_variables(self) -> None:
    """Validate required environment variables for database configuration."""
    required_vars = ['DB_HOST', 'DB_NAME', 'DB_USER', 'DB_PASSWORD']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        raise ConfigurationError(
            f"Missing required environment variables: {missing_vars}",
            "database.environment_variables"
        )
```

## Usage Examples

### Basic Database Configuration Access
```python
from src.config.config_manager import get_config

# Get configuration instance
config = get_config()

# Database configuration
database_config = config.get_database_config()
connection_string = database_config.get_dsn()

# Connection pool setup
pool = await asyncpg.create_pool(
    dsn=connection_string,
    min_size=database_config.min_pool_size,
    max_size=database_config.max_pool_size,
    command_timeout=database_config.command_timeout
)

# Data collector configuration
data_collector_config = config.get_data_collector_config()
if data_collector_config.enabled:
    collector = DataCollector(data_collector_config)
    await collector.start_collection()
```

### HFT Performance Validation
```python
# Validate database configuration for HFT compliance
database_manager = config._database_manager

try:
    database_manager.validate_database_config()
    logger.info("Database configuration meets HFT requirements")
except ValueError as e:
    logger.error(f"Database configuration violates HFT requirements: {e}")
    raise
```

### Analytics Integration
```python
# Access analytics configuration
data_collector_config = config.get_data_collector_config()
analytics_config = data_collector_config.analytics

# Setup arbitrage detection
arbitrage_detector = ArbitrageDetector(
    threshold=analytics_config.arbitrage_threshold,
    volume_threshold=analytics_config.volume_threshold,
    alert_threshold=analytics_config.spread_alert_threshold
)

# Monitor symbols from configuration
for symbol in data_collector_config.symbols:
    arbitrage_detector.add_symbol(symbol)
```

## Integration Patterns

### Database Connection Pool Management
```python
class DatabaseConnectionManager:
    """Manages database connections with HFT-optimized settings."""
    
    def __init__(self, database_config: DatabaseConfig):
        self.config = database_config
        self.pool = None
    
    async def initialize_pool(self) -> None:
        """Initialize connection pool with optimized settings."""
        self.pool = await asyncpg.create_pool(
            dsn=self.config.get_dsn(),
            min_size=self.config.min_pool_size,
            max_size=self.config.max_pool_size,
            max_queries=self.config.max_queries,
            max_inactive_connection_lifetime=self.config.max_inactive_connection_lifetime,
            command_timeout=self.config.command_timeout,
            statement_cache_size=self.config.statement_cache_size
        )
```

### Data Collection Integration
```python
class DataCollectionService:
    """Manages real-time data collection with analytics integration."""
    
    def __init__(self, data_collector_config: DataCollectorConfig):
        self.config = data_collector_config
        self.database_manager = DatabaseConnectionManager(data_collector_config.database)
        self.analytics_engine = AnalyticsEngine(data_collector_config.analytics)
    
    async def start_collection(self) -> None:
        """Start data collection with configured intervals."""
        await self.database_manager.initialize_pool()
        
        # Start periodic collection tasks
        asyncio.create_task(self._collect_orderbook_snapshots())
        asyncio.create_task(self._collect_trade_data())
        asyncio.create_task(self._run_analytics())
```

---

*This Database Configuration specification provides comprehensive management for database operations, data collection, and analytics integration while maintaining HFT performance requirements and security best practices.*