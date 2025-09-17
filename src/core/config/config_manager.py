"""
HFT Configuration Management Module

Comprehensive YAML-based configuration system for multi-exchange HFT trading
including MEXC, Gate.io, and arbitrage engine settings.

Key Features:
- YAML-based configuration for better readability
- Multi-exchange support (MEXC, Gate.io)
- HFT arbitrage engine configuration
- Secure API key management
- Type-safe configuration access
- Clear error messages for missing settings

Usage:
    from common.config import config
    
    # NEW: Structured configuration access (HFT-optimized)
    mexc_config = config.get_exchange_config_struct('mexc')  # Returns ExchangeConfig with WebSocket config
    network_config = config.get_network_config()  # Returns NetworkConfig
    websocket_template = config.get_websocket_config_template()  # Returns Dict (template for exchange configs)
    
    # Legacy: Dictionary access (maintained for backward compatibility)
    mexc_credentials_dict = config.get_exchange_credentials('mexc')  # Returns Dict[str, str]
    gateio_config_dict = config.get_exchange_config('gateio')  # Returns Dict[str, Any]
    
    # System settings
    timeout = config.REQUEST_TIMEOUT
    debug = config.DEBUG_MODE
    
    # Arbitrage configuration
    arb_config = config.get_arbitrage_config()
    risk_limits = config.get_arbitrage_risk_limits()
"""

import os
import re
import logging
import time
from typing import Dict, Optional, Any, Union, TypeVar, Type
from pathlib import Path
import yaml
from dotenv import load_dotenv
import traceback
from dataclasses import dataclass
from core.exceptions.exchange import ConfigurationError
from core.config.structs import ExchangeCredentials, NetworkConfig, RateLimitConfig, WebSocketConfig, ExchangeConfig, RestTransportConfig
from common.logging.simple_logger import getLogger
from enum import Enum
from msgspec import Struct

# Type aliases and constants
T = TypeVar('T')

# Performance monitoring
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

# Pre-compiled regex patterns for performance
ENV_VAR_PATTERN = re.compile(r'\$\{([^}]+)\}')
ENV_VAR_DEFAULT_PATTERN = re.compile(r'^([^:]+):(.*)$')

def guess_file_paths(file_name: str) -> list[Path]:
    """
    Returns a list of possible .env file locations to search.
    """
    return [
        Path(__file__).parent.parent.parent / file_name,  # Project root
        Path(__file__).parent.parent / file_name,         # src directory
        Path.cwd() / file_name,                           # Current working directory
        Path.home() / file_name,                          # User home directory (fallback)
    ]

def validate_config_dict(config: Dict[str, Any], required_keys: list[str], config_name: str) -> None:
    """Validate that required configuration keys are present.
    
    Args:
        config: Configuration dictionary to validate
        required_keys: List of required keys
        config_name: Name of configuration section for error reporting
        
    Raises:
        ConfigurationError: If required keys are missing
    """
    missing_keys = [key for key in required_keys if key not in config]
    if missing_keys:
        raise ConfigurationError(
            f"Missing required keys in {config_name}: {missing_keys}",
            config_name
        )

def safe_get_config_value(config: Dict[str, Any], key: str, default: T, value_type: Type[T], config_name: str) -> T:
    """Safely extract and validate configuration value with type checking.
    
    Args:
        config: Configuration dictionary
        key: Configuration key
        default: Default value if key is missing
        value_type: Expected type for validation
        config_name: Configuration section name for error reporting
        
    Returns:
        Configuration value cast to expected type
        
    Raises:
        ConfigurationError: If value cannot be cast to expected type
    """
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

def parse_network_config(part_config: Dict[str, Any]) -> NetworkConfig:
    """
    Parse network configuration from dictionary with comprehensive validation.

    Args:
        part_config: Dictionary with network configuration keys

    Returns:
        NetworkConfig struct with parsed and validated values
        
    Raises:
        ConfigurationError: If configuration values are invalid
    """
    try:
        return NetworkConfig(
            request_timeout=safe_get_config_value(part_config, 'request_timeout', 10.0, float, 'network'),
            connect_timeout=safe_get_config_value(part_config, 'connect_timeout', 5.0, float, 'network'),
            max_retries=safe_get_config_value(part_config, 'max_retries', 3, int, 'network'),
            retry_delay=safe_get_config_value(part_config, 'retry_delay', 1.0, float, 'network')
        )
    except Exception as e:
        raise ConfigurationError(f"Failed to parse network configuration: {e}", "network") from e

def parse_rate_limit_config(part_config: Dict[str, Any]) -> RateLimitConfig:
    """
    Parse rate limiting configuration from dictionary with validation.

    Args:
        part_config: Dictionary with rate limiting configuration keys

    Returns:
        RateLimitConfig struct with parsed and validated values
        
    Raises:
        ConfigurationError: If configuration values are invalid
    """
    try:
        requests_per_second = safe_get_config_value(part_config, 'requests_per_second', 15, int, 'rate_limiting')
        
        # HFT validation: Ensure reasonable rate limits
        if requests_per_second <= 0:
            raise ConfigurationError(
                f"requests_per_second must be positive, got: {requests_per_second}",
                "rate_limiting.requests_per_second"
            )
        if requests_per_second > 1000:  # Reasonable upper bound
            raise ConfigurationError(
                f"requests_per_second exceeds reasonable limit (1000), got: {requests_per_second}",
                "rate_limiting.requests_per_second"
            )
            
        return RateLimitConfig(requests_per_second=requests_per_second)
    except Exception as e:
        raise ConfigurationError(f"Failed to parse rate limiting configuration: {e}", "rate_limiting") from e

def parse_websocket_config(part_config: Dict[str, Any], websocket_url: str) -> WebSocketConfig:
    """
    Parse WebSocket configuration from dictionary with URL injection and validation.

    Args:
        part_config: Dictionary with WebSocket configuration keys
        websocket_url: WebSocket URL from exchange configuration

    Returns:
        WebSocketConfig struct with parsed, validated values and injected URL
        
    Raises:
        ConfigurationError: If configuration values are invalid
    """
    try:
        # Validate WebSocket URL
        if not websocket_url or not isinstance(websocket_url, str):
            raise ConfigurationError(
                f"Invalid WebSocket URL: {websocket_url}",
                "websocket_url"
            )
        if not (websocket_url.startswith('ws://') or websocket_url.startswith('wss://')):
            raise ConfigurationError(
                f"WebSocket URL must start with ws:// or wss://, got: {websocket_url}",
                "websocket_url"
            )
        
        return WebSocketConfig(
            # Injected URL from exchange config
            url=websocket_url,
            
            # Connection settings with validation
            connect_timeout=safe_get_config_value(part_config, 'connect_timeout', 10.0, float, 'websocket'),
            ping_interval=safe_get_config_value(part_config, 'ping_interval', 20.0, float, 'websocket'),
            ping_timeout=safe_get_config_value(part_config, 'ping_timeout', 10.0, float, 'websocket'),
            close_timeout=safe_get_config_value(part_config, 'close_timeout', 5.0, float, 'websocket'),
            
            # Reconnection settings with validation
            max_reconnect_attempts=safe_get_config_value(part_config, 'max_reconnect_attempts', 10, int, 'websocket'),
            reconnect_delay=safe_get_config_value(part_config, 'reconnect_delay', 1.0, float, 'websocket'),
            reconnect_backoff=safe_get_config_value(part_config, 'reconnect_backoff', 2.0, float, 'websocket'),
            max_reconnect_delay=safe_get_config_value(part_config, 'max_reconnect_delay', 60.0, float, 'websocket'),
            
            # Performance settings with validation
            max_message_size=safe_get_config_value(part_config, 'max_message_size', 1048576, int, 'websocket'),  # 1MB
            max_queue_size=safe_get_config_value(part_config, 'max_queue_size', 1000, int, 'websocket'),
            heartbeat_interval=safe_get_config_value(part_config, 'heartbeat_interval', 30.0, float, 'websocket'),
            
            # Optimization settings with validation
            enable_compression=safe_get_config_value(part_config, 'enable_compression', True, bool, 'websocket'),
            text_encoding=safe_get_config_value(part_config, 'text_encoding', 'utf-8', str, 'websocket')
        )
    except Exception as e:
        raise ConfigurationError(f"Failed to parse WebSocket configuration: {e}", "websocket") from e

def parse_transport_config(part_config: Dict[str, Any], exchange_name: str, is_private: bool = False) -> RestTransportConfig:
    """
    Parse REST transport configuration from dictionary with validation.

    Args:
        part_config: Dictionary with transport configuration keys
        exchange_name: Exchange name for strategy selection
        is_private: Whether this is for private API operations

    Returns:
        RestTransportConfig struct with parsed and validated values
        
    Raises:
        ConfigurationError: If configuration values are invalid
    """
    try:
        return RestTransportConfig(
            # Strategy Selection
            exchange_name=exchange_name,
            is_private=is_private,
            
            # Performance Targets
            max_latency_ms=safe_get_config_value(part_config, 'max_latency_ms', 50.0, float, 'transport'),
            target_throughput_rps=safe_get_config_value(part_config, 'target_throughput_rps', 100.0, float, 'transport'),
            max_retry_attempts=safe_get_config_value(part_config, 'max_retry_attempts', 3, int, 'transport'),
            
            # Connection Settings
            connection_timeout_ms=safe_get_config_value(part_config, 'connection_timeout_ms', 2000.0, float, 'transport'),
            read_timeout_ms=safe_get_config_value(part_config, 'read_timeout_ms', 5000.0, float, 'transport'),
            max_concurrent_requests=safe_get_config_value(part_config, 'max_concurrent_requests', 10, int, 'transport'),
            
            # Rate Limiting
            requests_per_second=safe_get_config_value(part_config, 'requests_per_second', 20.0, float, 'transport'),
            burst_capacity=safe_get_config_value(part_config, 'burst_capacity', 50, int, 'transport'),
            
            # Advanced Settings
            enable_connection_pooling=safe_get_config_value(part_config, 'enable_connection_pooling', True, bool, 'transport'),
            enable_compression=safe_get_config_value(part_config, 'enable_compression', True, bool, 'transport'),
            user_agent=safe_get_config_value(part_config, 'user_agent', "HFTArbitrageEngine/1.0", str, 'transport')
        )
    except Exception as e:
        raise ConfigurationError(f"Failed to parse transport configuration for {exchange_name}: {e}", f"{exchange_name}.transport") from e

class HftConfig:
    """
    Comprehensive HFT configuration management with YAML support and performance monitoring.
    
    This class implements a singleton pattern to ensure consistent configuration access
    across the application. It loads configuration from config.yaml file and provides
    type-safe access to multi-exchange settings including MEXC, Gate.io, and arbitrage
    engine configuration with risk limits and performance parameters.
    
    Features:
    - HFT-compliant configuration loading (<50ms)
    - Type-safe configuration access with validation
    - Environment variable substitution with fallbacks
    - Comprehensive error reporting and debugging
    - Performance monitoring and metrics
    - Singleton pattern for consistent access
    
    Usage Examples:
        # Get exchange configuration (structured)
        config = HftConfig()
        mexc_config = config.get_exchange_config('mexc')
        
        # Get network configuration
        network_config = config.get_network_config()
        
        # Check performance metrics
        metrics = config.get_loading_metrics()
        if not metrics.is_hft_compliant():
            logger.warning("Configuration loading exceeds HFT requirements")
    """
    
    # Class-level cache for singleton pattern
    _instance: Optional['HftConfig'] = None
    _initialized: bool = False

    # Class-level configuration state
    ENVIRONMENT: Optional[str] = None
    DEBUG_MODE: bool = True
    
    # Performance monitoring
    _loading_metrics: Optional[ConfigLoadingMetrics] = None

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
            
            # Calculate total loading time
            total_time = time.perf_counter() - start_time
            HftConfig._loading_metrics.total_load_time = total_time
            
            # Mark as initialized
            HftConfig._initialized = True
            
            # Log performance metrics
            self._logger.info(f"HFT configuration initialized for environment: {HftConfig.ENVIRONMENT}")
            if HftConfig._loading_metrics.is_hft_compliant():
                self._logger.info(f"Configuration loading: {total_time*1000:.2f}ms (HFT compliant)")
            else:
                self._logger.warning(
                    f"Configuration loading: {total_time*1000:.2f}ms (EXCEEDS HFT requirement of 50ms)"
                )
                
        except Exception as e:
            self._logger.error(f"Failed to initialize HFT configuration: {e}")
            raise ConfigurationError(f"Configuration initialization failed: {e}") from e
    
    def _load_env_file(self) -> None:
        """
        Load environment variables from .env file in project root.
        
        Tries multiple locations to find the .env file:
        1. Project root (preferred)
        2. Parent directories
        3. Current working directory
        """

        env_loaded = False
        for env_path in guess_file_paths('.env'):
            if env_path.exists():
                try:
                    # Load the .env file
                    load_dotenv(dotenv_path=env_path, override=False)
                    self._logger.info(f"Loaded environment variables from: {env_path}")
                    env_loaded = True
                    break
                except Exception as e:
                    self._logger.warning(f"Failed to load .env from {env_path}: {e}")
                    continue
        
        if not env_loaded:
            self._logger.debug("No .env file found - using system environment variables only")
            # Still try to load from default location (load_dotenv will search automatically)
            try:
                if load_dotenv(override=False):
                    self._logger.info("Loaded environment variables from default .env location")
            except Exception:
                pass
    
    def _load_yaml_config(self) -> None:
        """Load configuration from YAML file with environment variable substitution and performance monitoring."""
        yaml_start = time.perf_counter()
        
        config_data = None
        config_file_path = None
        
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
                    config_file_path = config_path
                    break
                    
                except yaml.YAMLError as e:
                    self._logger.error(f"YAML parsing error in {config_path}: {e}")
                    raise ConfigurationError(
                        f"Invalid YAML syntax in {config_path}: {e}",
                        str(config_path)
                    ) from e
                except Exception as e:
                    self._logger.warning(f"Failed to load config from {config_path}: {e}")
                    continue
        
        if config_data is None:
            searched_paths = ", ".join(str(p) for p in config_paths)
            raise ConfigurationError(
                f"No valid config.yaml found. Searched paths: {searched_paths}",
                "config_file"
            )
        
        # Record YAML loading time
        yaml_time = time.perf_counter() - yaml_start
        HftConfig._loading_metrics.yaml_load_time = yaml_time
        
        self._logger.info(f"Configuration loaded from: {config_file_path}")
        
        # Validate and process configuration
        validation_start = time.perf_counter()
        self._validate_and_process_config(config_data)
        validation_time = time.perf_counter() - validation_start
        HftConfig._loading_metrics.validation_time = validation_time

    def _validate_and_process_config(self, config_data: Dict[str, Any]) -> None:
        """Validate and process configuration data with comprehensive error checking.
        
        Args:
            config_data: Parsed YAML configuration data
            
        Raises:
            ConfigurationError: If configuration is invalid
        """
        # Store complete config data for arbitrage access
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
        websocket_config = config_data.get('websocket', {})
        # Store as template - will be used as fallback for exchange-specific configs
        self._websocket_config_template = websocket_config
        
        # Process exchange configurations
        self._process_exchange_configs(config_data)
    
    def _process_exchange_configs(self, config_data: Dict[str, Any]) -> None:
        """Process exchange configurations with validation.
        
        Args:
            config_data: Complete configuration data
            
        Raises:
            ConfigurationError: If exchange configuration is invalid
        """
        exchanges_config = config_data.get('exchanges', {})
        if not exchanges_config:
            raise ConfigurationError(
                "No exchanges configured. At least one exchange must be configured.",
                "exchanges"
            )
        
        # Create exchange configurations
        self._exchange_configs: Dict[str, ExchangeConfig] = {}
        
        for exchange_name, exchange_data in exchanges_config.items():
            try:
                
                # Validate exchange data structure
                required_exchange_keys = ['base_url', 'websocket_url']
                validate_config_dict(exchange_data, required_exchange_keys, f'exchanges.{exchange_name}')
                
                # Create credentials with validation
                api_key = exchange_data.get('api_key', '')
                secret_key = exchange_data.get('secret_key', '')
                credentials = ExchangeCredentials(api_key=api_key, secret_key=secret_key)

                # Use global network config unless overridden at exchange level
                network_config = self._network_config
                if 'network_config' in exchange_data:
                    network_config = parse_network_config(exchange_data['network_config'])

                # Handle rate limiting - check exchange-specific first, then global fallback
                rate_limit_config = exchange_data.get('rate_limiting', {})
                if not rate_limit_config:
                    # Fallback to global rate limiting
                    rate_limit_config = config_data.get('rate_limiting', {})
                rate_limit = parse_rate_limit_config(rate_limit_config)

                # Create WebSocket config with URL injection from exchange config
                websocket_config_data = self._websocket_config_template.copy()
                if 'websocket_config' in exchange_data:
                    websocket_config_data.update(exchange_data['websocket_config'])

                # Inject URL from exchange configuration
                websocket_url = exchange_data.get('websocket_url', '')
                websocket_config = parse_websocket_config(websocket_config_data, websocket_url)

                # Parse transport configuration if present
                transport_config = None
                if 'transport' in exchange_data:
                    transport_config_data = exchange_data['transport']
                    # Parse transport config (is_private=False for base config)
                    transport_config = parse_transport_config(transport_config_data, exchange_name, is_private=False)

                # Validate base URL
                base_url = exchange_data.get('base_url', '')
                if not base_url or not isinstance(base_url, str):
                    raise ConfigurationError(
                        f"Invalid base_url for exchange {exchange_name}: {base_url}",
                        f"exchanges.{exchange_name}.base_url"
                    )
                if not (base_url.startswith('http://') or base_url.startswith('https://')):
                    raise ConfigurationError(
                        f"base_url must start with http:// or https:// for exchange {exchange_name}: {base_url}",
                        f"exchanges.{exchange_name}.base_url"
                    )

                # Create exchange config
                exchange_config = ExchangeConfig(
                    name=exchange_name,
                    credentials=credentials,
                    base_url=base_url,
                    websocket_url=websocket_url,
                    enabled=exchange_data.get('enabled', True),
                    network=network_config,
                    rate_limit=rate_limit,
                    websocket=websocket_config,
                    transport=transport_config
                )

                self._exchange_configs[exchange_name] = exchange_config
                self._logger.debug(f"Configured exchange: {exchange_name} (enabled: {exchange_config.enabled})")
                
            except Exception as e:
                raise ConfigurationError(
                    f"Failed to configure exchange '{exchange_name}': {e}",
                    f"exchanges.{exchange_name}"
                ) from e
    
    def _substitute_env_vars(self, content: str) -> str:
        """
        Substitute environment variables in configuration content with improved performance.
        
        Supports syntax:
        - ${VAR_NAME} - Required environment variable
        - ${VAR_NAME:default} - Optional with default value
        
        Performance optimizations:
        - Pre-compiled regex patterns
        - Cached environment variable access
        - Efficient string operations
        
        Args:
            content: Raw configuration content
            
        Returns:
            Content with environment variables substituted
            
        Raises:
            ConfigurationError: If environment variable substitution fails
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
    
    # New structured configuration methods (HFT-optimized)
    
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
        exchange_name = exchange_name.lower()
        if exchange_name not in self._exchange_configs:
            available_exchanges = list(self._exchange_configs.keys())
            raise ConfigurationError(
                f"Exchange '{exchange_name}' is not configured. Available exchanges: {available_exchanges}",
                exchange_name
            )
        return self._exchange_configs[exchange_name]
    
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
    
    def get_all_exchange_configs(self) -> Dict[str, ExchangeConfig]:
        """
        Get all configured cex as structured objects.
        
        Returns:
            Dictionary mapping exchange names to ExchangeConfig structs
        """
        return self._exchange_configs.copy()
    
    def get_configured_exchanges(self) -> list[str]:
        """
        Get list of configured exchange names.
        
        Returns:
            List of exchange names that have been configured
        """
        return list(self._exchange_configs.keys())
    
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

    def get_logger(self, name: str):
        """
        Get a logger instance with the specified name.

        Args:
            name: Name of the logger

        Returns:
            Configured logger instance
        """
        return getLogger(name)
    
    def validate_configuration(self) -> bool:
        """
        Perform comprehensive configuration validation.
        
        Returns:
            True if all configuration is valid
            
        Raises:
            ConfigurationError: If configuration validation fails
        """
        try:
            # Validate that at least one exchange is enabled
            enabled_exchanges = [name for name, config in self._exchange_configs.items() if config.enabled]
            if not enabled_exchanges:
                raise ConfigurationError(
                    "No exchanges are enabled. At least one exchange must be enabled.",
                    "exchanges"
                )
            
            # Validate exchange credentials for enabled exchanges
            for exchange_name, exchange_config in self._exchange_configs.items():
                if exchange_config.enabled and not exchange_config.has_credentials():
                    self._logger.warning(
                        f"Exchange '{exchange_name}' is enabled but has no credentials - running in public mode only"
                    )
            
            # Validate arbitrage configuration if present
            if self.has_arbitrage_config():
                arbitrage_config = self.get_arbitrage_config()
                if 'enabled_exchanges' in arbitrage_config:
                    arbitrage_exchanges = arbitrage_config['enabled_exchanges']
                    for arb_exchange in arbitrage_exchanges:
                        if arb_exchange.lower() not in self._exchange_configs:
                            raise ConfigurationError(
                                f"Arbitrage references unconfigured exchange: {arb_exchange}",
                                "arbitrage.enabled_exchanges"
                            )
            
            self._logger.info("Configuration validation passed")
            return True
            
        except Exception as e:
            self._logger.error(f"Configuration validation failed: {e}")
            raise
    
    def get_config_summary(self) -> str:
        """
        Get a summary of the current configuration state.
        
        Returns:
            Formatted configuration summary string
        """
        summary_lines = [
            "=== HFT Configuration Summary ===",
            f"Environment: {HftConfig.ENVIRONMENT}",
            f"Debug Mode: {HftConfig.DEBUG_MODE}",
            f"Configured Exchanges: {len(self._exchange_configs)}",
        ]
        
        # Add exchange details
        for name, config in self._exchange_configs.items():
            status = "enabled" if config.enabled else "disabled"
            auth_status = "authenticated" if config.has_credentials() else "public-only"
            summary_lines.append(f"  - {name.upper()}: {status}, {auth_status}")
        
        # Add performance metrics
        if HftConfig._loading_metrics:
            summary_lines.extend([
                "",
                "=== Performance Metrics ===",
                HftConfig._loading_metrics.get_performance_report()
            ])
        
        return "\n".join(summary_lines)


# Create singleton instance
config = HftConfig()


def get_config() -> HftConfig:
    """
    Get the global configuration instance.
    
    Returns:
        Singleton HftConfig instance
    """
    return config


# Convenience functions
def is_production() -> bool:
    """Check if running in production environment."""
    return config.ENVIRONMENT == 'prod'


def is_debug_enabled() -> bool:
    """Check if debug mode is enabled."""
    return config.DEBUG_MODE

def get_arbitrage_config() -> Dict[str, Any]:
    """
    Get arbitrage configuration.
    
    Returns:
        Dictionary with arbitrage configuration settings
    """
    return config.get_arbitrage_config()


def get_arbitrage_risk_limits() -> Dict[str, Any]:
    """
    Get arbitrage risk limits.
    
    Returns:
        Dictionary with risk limits settings
    """
    return config.get_arbitrage_risk_limits()


# New structured convenience functions (HFT-optimized)

def get_exchange_config(exchange_name: str) -> ExchangeConfig:
    """
    Get exchange configuration as structured object.
    
    Args:
        exchange_name: Name of the exchange (e.g., 'mexc', 'gateio')
    
    Returns:
        ExchangeConfig struct with complete exchange configuration
    """
    return config.get_exchange_config(exchange_name)

def get_network_config() -> NetworkConfig:
    """
    Get network configuration as structured object.
    
    Returns:
        NetworkConfig struct with network settings
    """
    return config.get_network_config()

def get_all_exchange_configs() -> Dict[str, ExchangeConfig]:
    """
    Get all configured exchanges as structured objects.
    
    Returns:
        Dictionary mapping exchange names to ExchangeConfig structs
    """
    return config.get_all_exchange_configs()

def validate_hft_compliance() -> bool:
    """
    Validate that configuration loading meets HFT performance requirements.
    
    Returns:
        True if configuration loading is HFT compliant (<50ms)
    """
    return config.validate_hft_compliance()

def get_performance_report() -> str:
    """
    Get detailed configuration loading performance report.
    
    Returns:
        Formatted performance report string
    """
    return config.get_performance_report()

def get_loading_metrics() -> ConfigLoadingMetrics:
    """
    Get configuration loading performance metrics.
    
    Returns:
        ConfigLoadingMetrics with performance data
    """
    return config.get_loading_metrics()

