# Core Configuration Manager Specification

Complete specification for the HftConfig singleton that orchestrates all configuration management with specialized manager delegation and HFT performance compliance.

## Overview

The **HftConfig** class serves as the primary configuration orchestrator, providing unified access to all system configuration while delegating specialized functionality to domain-specific managers. Built for sub-50ms loading performance with comprehensive validation and error handling.

## Architecture

### Class Hierarchy
```
HftConfig (Singleton)
├── DatabaseConfigManager (database configuration)
├── ExchangeConfigManager (exchange configuration) 
├── LoggingConfigManager (logging configuration)
└── Direct Management (network, arbitrage, validation)
```

### Core Design Principles

1. **Singleton Pattern** - Single configuration instance across application
2. **Specialized Manager Delegation** - Domain expertise handled by specialized managers
3. **HFT Performance Compliance** - Sub-50ms total loading time with monitoring
4. **Environment Variable Integration** - Secure credential management
5. **Comprehensive Validation** - Type-safe access with error handling
6. **Performance Monitoring** - ConfigLoadingMetrics with sub-component timing

## Core Class Specification

### HftConfig Class Definition

```python
class HftConfig:
    """
    Comprehensive HFT configuration management with YAML support and performance monitoring.
    
    Orchestrates specialized managers while preserving all existing functionality.
    Implements singleton pattern for consistent configuration access across the application.
    """
    
    # Class-level singleton state
    _instance: Optional['HftConfig'] = None
    _initialized: bool = False
    
    # Configuration state
    ENVIRONMENT: Optional[str] = None
    DEBUG_MODE: bool = True
    
    # Performance monitoring
    _loading_metrics: Optional[ConfigLoadingMetrics] = None
```

### Initialization and Loading

#### Constructor and Singleton Pattern
```python
def __new__(cls) -> 'HftConfig':
    """Singleton pattern for configuration management."""
    if cls._instance is None:
        cls._instance = super().__new__(cls)
    return cls._instance

def __init__(self):
    """Initialize configuration with YAML loading, validation, and performance monitoring."""
    if self._initialized:
        return
    
    # Initialize performance tracking
    start_time = time.perf_counter()
    HftConfig._loading_metrics = ConfigLoadingMetrics()
    
    self._logger = logging.getLogger(__name__)
    
    try:
        # Load environment variables from .env file
        self._load_env_file()
        
        # Load configuration from YAML
        self._load_yaml_config()
        
        # Initialize specialized managers
        self._initialize_managers()
        
        # Calculate total loading time
        total_time = time.perf_counter() - start_time
        HftConfig._loading_metrics.total_load_time = total_time
        
        # Mark as initialized
        HftConfig._initialized = True
        
        # Validate HFT compliance
        if not HftConfig._loading_metrics.is_hft_compliant():
            self._logger.warning(
                f"Configuration loading: {total_time*1000:.2f}ms (EXCEEDS HFT requirement of 50ms)"
            )
                
    except Exception as e:
        self._logger.error(f"Failed to initialize HFT configuration: {e}")
        raise ConfigurationError(f"Configuration initialization failed: {e}") from e
```

#### Environment File Discovery
```python
def _load_env_file(self) -> None:
    """
    Load environment variables from .env file in project root.
    
    Search Strategy:
    1. Project root (preferred)
    2. Parent directories  
    3. Current working directory
    4. User home directory (fallback)
    """
    env_loaded = False
    for env_path in guess_file_paths('.env'):
        if env_path.exists():
            try:
                load_dotenv(dotenv_path=env_path, override=False)
                self._logger.info(f"Loaded environment variables from: {env_path}")
                env_loaded = True
                break
            except Exception as e:
                self._logger.warning(f"Failed to load .env from {env_path}: {e}")
                continue
    
    if not env_loaded:
        self._logger.debug("No .env file found - using system environment variables only")
```

#### YAML Configuration Loading
```python
def _load_yaml_config(self) -> None:
    """Load configuration from YAML file with environment variable substitution and performance monitoring."""
    yaml_start = time.perf_counter()
    
    # Search for config.yaml in standard locations
    config_paths = guess_file_paths('config.yaml')
    
    for config_path in config_paths:
        if config_path.exists():
            try:
                # Load and parse YAML
                with open(config_path, 'r', encoding='utf-8') as f:
                    raw_content = f.read()
                
                # Time environment variable substitution
                env_start = time.perf_counter()
                substituted_content = self._substitute_env_vars(raw_content)
                env_time = time.perf_counter() - env_start
                HftConfig._loading_metrics.env_substitution_time = env_time
                
                # Parse YAML
                config_data = yaml.safe_load(substituted_content)
                break
                
            except yaml.YAMLError as e:
                raise ConfigurationError(
                    f"Invalid YAML syntax in {config_path}: {e}",
                    str(config_path)
                ) from e
    
    # Record YAML loading time
    yaml_time = time.perf_counter() - yaml_start
    HftConfig._loading_metrics.yaml_load_time = yaml_time
    
    # Validate and process configuration
    validation_start = time.perf_counter()
    self._validate_and_process_config(config_data)
    validation_time = time.perf_counter() - validation_start
    HftConfig._loading_metrics.validation_time = validation_time
```

### Environment Variable Substitution

#### Variable Substitution Implementation
```python
def _substitute_env_vars(self, content: str) -> str:
    """
    Substitute environment variables in configuration content with improved performance.
    
    Syntax Support:
    - ${VAR_NAME} - Required environment variable
    - ${VAR_NAME:default} - Optional with default value
    
    Performance Optimizations:
    - Pre-compiled regex patterns
    - Cached environment variable access
    - Efficient string operations
    """
    try:
        def replace_var(match):
            var_expr = match.group(1)
            
            # Check for default value syntax using pre-compiled pattern
            default_match = ENV_VAR_DEFAULT_PATTERN.match(var_expr)
            if default_match:
                var_name, default_value = default_match.groups()
                env_value = os.getenv(var_name.strip())
                if env_value is None:
                    self._logger.debug(f"Using default value for {var_name}: {default_value}")
                    return default_value
                return env_value
            else:
                # Required environment variable (but allow empty for public mode)
                var_name = var_expr.strip()
                env_value = os.getenv(var_name)
                if env_value is None:
                    self._logger.warning(f"Environment variable {var_name} not set - using empty value")
                    return ""
                return env_value
        
        # Perform substitution using pre-compiled pattern
        result = ENV_VAR_PATTERN.sub(replace_var, content)
        return result
    except Exception as e:
        raise ConfigurationError(f"Failed to substitute environment variables: {e}") from e
```

### Configuration Validation and Processing

#### Configuration Validation
```python
def _validate_and_process_config(self, config_data: Dict[str, Any]) -> None:
    """Validate and process configuration data with comprehensive error checking."""
    # Store complete config data for arbitrage access and manager initialization
    self._config_data = config_data
    
    # Validate top-level structure
    validate_config_dict(config_data, ['environment'], 'config')
    
    # Process environment configuration
    environment_config = config_data.get('environment', {})
    if isinstance(environment_config, dict):
        HftConfig.ENVIRONMENT = environment_config.get('name', 'dev').lower()
    else:
        HftConfig.ENVIRONMENT = str(environment_config).lower()

    # Validate environment
    valid_environments = ('dev', 'prod', 'test')
    if HftConfig.ENVIRONMENT not in valid_environments:
        raise ConfigurationError(
            f"Invalid environment '{HftConfig.ENVIRONMENT}'. Valid options: {valid_environments}",
            'environment.name'
        )

    # Process debug mode
    HftConfig.DEBUG_MODE = bool(environment_config.get('debug', False))

    # Parse network configuration with validation
    network_config = config_data.get('network', {})
    self._network_config = parse_network_config(network_config)
    
    # Create global WebSocket configuration template (without URL)
    websocket_config = config_data.get('ws', {})
    self._websocket_config_template = websocket_config
```

### Specialized Manager Initialization

#### Manager Initialization
```python
def _initialize_managers(self) -> None:
    """Initialize specialized configuration managers."""
    # Initialize database manager
    self._database_manager = DatabaseConfigManager(self._config_data)
    
    # Initialize exchange manager with network config and websocket template
    self._exchange_manager = ExchangeConfigManager(
        self._config_data, 
        self._network_config, 
        self._websocket_config_template
    )
    
    # Initialize logging manager
    self._logging_manager = LoggingConfigManager(self._config_data)
```

## Manager Delegation Methods

### Database Configuration Access
```python
def get_database_config(self) -> DatabaseConfig:
    """
    Get database configuration as structured object.
    
    Returns:
        DatabaseConfig struct with database settings
    """
    return self._database_manager.get_database_config()

def get_data_collector_config(self) -> DataCollectorConfig:
    """
    Get data collector configuration as structured object.
    
    Returns:
        DataCollectorConfig struct with complete data collection settings
    """
    return self._database_manager.get_data_collector_config()
```

### Exchange Configuration Access
```python
def get_exchange_config(self, exchange_name: str) -> ExchangeConfig:
    """
    Get exchange configuration as structured object.
    
    Args:
        exchange_name: Name of the exchange (e.g., 'mexc', 'gateio')
    
    Returns:
        ExchangeConfig struct with complete exchange configuration
    
    Raises:
        ConfigurationError: If exchange is not configured
    """
    config = self._exchange_manager.get_exchange_config(exchange_name)
    if config is None:
        available_exchanges = self._exchange_manager.get_configured_exchanges()
        raise ConfigurationError(
            f"Exchange '{exchange_name}' is not configured. Available exchanges: {available_exchanges}",
            exchange_name
        )
    return config

def get_all_exchange_configs(self) -> Dict[str, ExchangeConfig]:
    """
    Get all configured exchanges as structured objects.
    
    Returns:
        Dictionary mapping exchange names to ExchangeConfig structs
    """
    return self._exchange_manager.get_all_exchange_configs()

def get_configured_exchanges(self) -> list[str]:
    """
    Get list of configured exchange names.
    
    Returns:
        List of exchange names that have been configured
    """
    return self._exchange_manager.get_configured_exchanges()
```

### Logging Configuration Access
```python
def get_logging_config(self) -> Dict[str, Any]:
    """
    Get logging configuration from config.yaml.
    
    Returns:
        Dictionary with logging configuration settings including:
        - console: Console output settings
        - file: File output settings  
        - prometheus: Metrics collection settings
        - performance: Performance optimization settings
    """
    return self._logging_manager.get_logging_config()
```

## Performance Monitoring

### ConfigLoadingMetrics Structure
```python
@dataclass
class ConfigLoadingMetrics:
    """HFT performance metrics for configuration loading."""
    yaml_load_time: float = 0.0
    env_substitution_time: float = 0.0
    validation_time: float = 0.0
    total_load_time: float = 0.0
    
    def is_hft_compliant(self) -> bool:
        """Check if configuration loading meets HFT requirements (<50ms)."""
        return self.total_load_time < 0.050  # 50ms in seconds
    
    def get_performance_report(self) -> str:
        """Generate human-readable performance report."""
        return (
            f"Configuration Loading Performance:\n"
            f"  YAML Load: {self.yaml_load_time*1000:.2f}ms\n"
            f"  Env Substitution: {self.env_substitution_time*1000:.2f}ms\n"
            f"  Validation: {self.validation_time*1000:.2f}ms\n"
            f"  Total: {self.total_load_time*1000:.2f}ms\n"
            f"  HFT Compliant: {'✓' if self.is_hft_compliant() else '✗'}"
        )
```

### Performance Access Methods
```python
def get_loading_metrics(self) -> ConfigLoadingMetrics:
    """
    Get configuration loading performance metrics.
    
    Returns:
        ConfigLoadingMetrics with performance data
    """
    if HftConfig._loading_metrics is None:
        return ConfigLoadingMetrics()  # Return empty metrics if not initialized
    return HftConfig._loading_metrics

def validate_hft_compliance(self) -> bool:
    """
    Validate that configuration loading meets HFT performance requirements.
    
    Returns:
        True if configuration loading is HFT compliant (<50ms)
    """
    return self.get_loading_metrics().is_hft_compliant()

def get_performance_report(self) -> str:
    """
    Get detailed configuration loading performance report.
    
    Returns:
        Formatted performance report string
    """
    return self.get_loading_metrics().get_performance_report()
```

## Direct Configuration Access

### Network Configuration
```python
def get_network_config(self) -> NetworkConfig:
    """
    Get network configuration as structured object.
    
    Returns:
        NetworkConfig struct with network settings
    """
    return self._network_config

def get_websocket_config_template(self) -> Dict[str, Any]:
    """
    Get global WebSocket configuration template.
    
    Returns:
        Dictionary with global WebSocket configuration template
    """
    return self._websocket_config_template
```

### Arbitrage Configuration
```python
def get_arbitrage_config(self) -> Dict[str, Any]:
    """
    Get arbitrage-specific configuration dictionary.
    
    Returns:
        Dictionary with arbitrage configuration settings
    """
    return self._config_data.get('arbitrage', {})

def has_arbitrage_config(self) -> bool:
    """
    Check if arbitrage configuration is available.
    
    Returns:
        True if arbitrage configuration exists in config.yaml
    """
    arbitrage_config = self._config_data.get('arbitrage', {})
    return bool(arbitrage_config)

def get_arbitrage_risk_limits(self) -> Dict[str, Any]:
    """
    Get arbitrage risk limits configuration.
    
    Returns:
        Dictionary with risk limits settings
    """
    arbitrage_config = self._config_data.get('arbitrage', {})
    return arbitrage_config.get('risk_limits', {})
```

## Comprehensive Validation

### Configuration Validation
```python
def validate_configuration(self) -> bool:
    """
    Perform comprehensive configuration validation using specialized managers.
    
    Returns:
        True if all configuration is valid
        
    Raises:
        ConfigurationError: If configuration validation fails
    """
    try:
        # Validate that at least one exchange is enabled
        enabled_exchanges = self._exchange_manager.get_enabled_exchanges()
        if not enabled_exchanges:
            raise ConfigurationError(
                "No exchanges are enabled. At least one exchange must be enabled.",
                "exchanges"
            )
        
        # Validate exchange credentials for enabled exchanges
        for exchange_name in enabled_exchanges:
            exchange_config = self._exchange_manager.get_exchange_config(exchange_name)
            if not exchange_config.has_credentials():
                self._logger.warning(
                    f"Exchange '{exchange_name}' is enabled but has no credentials - running in public mode only"
                )
        
        # Validate arbitrage configuration if present
        if self.has_arbitrage_config():
            arbitrage_config = self.get_arbitrage_config()
            if 'enabled_exchanges' in arbitrage_config:
                arbitrage_exchanges = arbitrage_config['enabled_exchanges']
                configured_exchanges = self.get_configured_exchanges()
                
                # Create mapping from arbitrage names to actual config names
                name_mapping = {
                    'mexc': 'mexc_spot',
                    'gateio': 'gateio_spot',
                    'gateio_futures': 'gateio_futures'
                }
                
                for arb_exchange in arbitrage_exchanges:
                    # Try exact match first, then mapped match
                    arb_lower = arb_exchange.lower()
                    mapped_name = name_mapping.get(arb_lower, arb_lower)
                    
                    if arb_lower not in configured_exchanges and mapped_name not in configured_exchanges:
                        self._logger.warning(
                            f"Arbitrage references exchange '{arb_exchange}' which is not configured. "
                            f"Available exchanges: {configured_exchanges}"
                        )
        
        self._logger.info("Configuration validation passed")
        return True
        
    except Exception as e:
        self._logger.error(f"Configuration validation failed: {e}")
        raise
```

## Utility Functions

### Helper Functions
```python
def guess_file_paths(file_name: str) -> list[Path]:
    """
    Returns a list of possible .env file locations to search.
    """
    return [
        Path(__file__).parent.parent.parent.parent / file_name,  # Project root
        Path(__file__).parent.parent.parent / file_name,  # Project root
        Path.cwd() / file_name,                           # Current working directory
        Path.home() / file_name,                          # User home directory (fallback)
    ]

def validate_config_dict(config: Dict[str, Any], required_keys: list[str], config_name: str) -> None:
    """Validate that required configuration keys are present."""
    missing_keys = [key for key in required_keys if key not in config]
    if missing_keys:
        raise ConfigurationError(
            f"Missing required keys in {config_name}: {missing_keys}",
            config_name
        )

def safe_get_config_value(config: Dict[str, Any], key: str, default: T, value_type: Type[T], config_name: str) -> T:
    """Safely extract and validate configuration value with type checking."""
    try:
        value = config.get(key, default)
        if value_type == float:
            return float(value)
        elif value_type == int:
            return int(value)
        elif value_type == bool:
            return bool(value)
        elif value_type == str:
            return str(value)
        else:
            return value_type(value)
    except (ValueError, TypeError) as e:
        raise ConfigurationError(
            f"Invalid value for {config_name}.{key}: {config.get(key)} (expected {value_type.__name__})",
            f"{config_name}.{key}"
        ) from e
```

## Global Configuration Access

### Singleton Access
```python
# Create singleton instance
config = HftConfig()

def get_config() -> HftConfig:
    """
    Get the global configuration instance.
    
    Returns:
        Singleton HftConfig instance
    """
    return config
```

### Convenience Functions
```python
def is_production() -> bool:
    """Check if running in production environment."""
    return config.ENVIRONMENT == 'prod'

def is_debug_enabled() -> bool:
    """Check if debug mode is enabled."""
    return config.DEBUG_MODE

def get_arbitrage_config() -> Dict[str, Any]:
    """Get arbitrage configuration."""
    return config.get_arbitrage_config()

def get_arbitrage_risk_limits() -> Dict[str, Any]:
    """Get arbitrage risk limits."""
    return config.get_arbitrage_risk_limits()

def get_exchange_config(exchange_name: str) -> ExchangeConfig:
    """Get exchange configuration as structured object."""
    return config.get_exchange_config(exchange_name)

def get_network_config() -> NetworkConfig:
    """Get network configuration as structured object."""
    return config.get_network_config()

def get_all_exchange_configs() -> Dict[str, ExchangeConfig]:
    """Get all configured exchanges as structured objects."""
    return config.get_all_exchange_configs()

def get_logging_config() -> Dict[str, Any]:
    """Get logging configuration from config.yaml."""
    return config.get_logging_config()

def validate_hft_compliance() -> bool:
    """Validate that configuration loading meets HFT performance requirements."""
    return config.validate_hft_compliance()

def get_performance_report() -> str:
    """Get detailed configuration loading performance report."""
    return config.get_performance_report()

def get_loading_metrics() -> ConfigLoadingMetrics:
    """Get configuration loading performance metrics."""
    return config.get_loading_metrics()

def get_database_config() -> DatabaseConfig:
    """Get database configuration as structured object."""
    return config.get_database_config()

def get_data_collector_config() -> DataCollectorConfig:
    """Get data collector configuration as structured object."""
    return config.get_data_collector_config()
```

## Integration Examples

### Factory Integration
```python
# Exchange factory integration
from src.config.config_manager import get_config

config = get_config()

# Get exchange configuration
mexc_config = config.get_exchange_config('mexc_spot')

# Create separated domain instances
if mexc_config.has_credentials():
    # Private domain (trading operations)
    private_exchange = factory.create_private_exchange('mexc_spot', mexc_config)
    
    # Public domain (market data)
    public_exchange = factory.create_public_exchange('mexc_spot', mexc_config)
else:
    # Public-only mode
    public_exchange = factory.create_public_exchange('mexc_spot', mexc_config)
```

### Performance Monitoring Integration
```python
# Monitor configuration loading performance
config = get_config()

# Check HFT compliance
if not config.validate_hft_compliance():
    logger.warning("Configuration loading exceeds HFT requirements")
    
# Get detailed performance report
performance_report = config.get_performance_report()
logger.info(performance_report)

# Access individual metrics
metrics = config.get_loading_metrics()
if metrics.yaml_load_time > 0.010:  # 10ms
    logger.warning(f"YAML loading is slow: {metrics.yaml_load_time*1000:.2f}ms")
```

---

*This Core Configuration Manager specification provides the foundation for unified, high-performance configuration management with specialized manager delegation and comprehensive HFT compliance monitoring.*