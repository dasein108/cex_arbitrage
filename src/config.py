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
    mexc_config = config.get_exchange_config_struct('mexc')  # Returns ExchangeConfig
    mexc_credentials = config.get_exchange_credentials_struct('mexc')  # Returns ExchangeCredentials
    network_config = config.get_network_config()  # Returns NetworkConfig
    websocket_config = config.get_websocket_config()  # Returns WebSocketConfig
    
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
from typing import Dict, Optional, Any
from pathlib import Path
import yaml
from dotenv import load_dotenv
import traceback
from core.exceptions.exchange import ConfigurationError
from structs.config import ExchangeCredentials, NetworkConfig, RateLimitConfig, WebSocketConfig, ExchangeConfig
from common.logging.simple_logger import getLogger
from enum import Enum

# Exchange constants
class ExchangeEnum(str, Enum):
    MEXC = 'mexc'
    GATEIO = 'gateio'

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

class HftConfig:
    """
    Comprehensive HFT configuration management with YAML support.
    
    Loads configuration from config.yaml file and provides type-safe access
    to multi-exchange settings including MEXC, Gate.io, and arbitrage engine
    configuration with risk limits and performance parameters.
    """
    
    # Class-level cache for singleton pattern
    _instance: Optional['HftConfig'] = None
    _initialized: bool = False

    ENVIRONMENT = None
    DEBUG_MODE = True

    def __new__(cls) -> 'HftConfig':
        """Singleton pattern for configuration management."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize configuration with YAML loading and validation."""
        if self._initialized:
            return
        
        self._logger = logging.getLogger(__name__)
        
        # Load environment variables from .env file
        self._load_env_file()
        
        # Load configuration from YAML
        self._load_yaml_config()

        # Mark as initialized
        HftConfig._initialized = True
        self._logger.info(f"HFT configuration initialized for environment: {HftConfig.ENVIRONMENT}")
    
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
        """Load configuration from YAML file with environment variable substitution."""
        

        config_data = None
        config_file_path = None
        
        for config_path in guess_file_paths('config.yaml'):
            if config_path.exists():
                try:
                    with open(config_path, 'r') as f:
                        raw_content = f.read()
                    
                    # Substitute environment variables
                    substituted_content = self._substitute_env_vars(raw_content)
                    config_data = yaml.safe_load(substituted_content)
                    config_file_path = config_path
                    break
                except Exception as e:
                    traceback.print_exc()
                    self._logger.warning(f"Failed to load config from {config_path}: {e}")
                    continue
        
        if config_data is None:
            raise ConfigurationError(
                f"No valid config.yaml found"
            )
        
        self._logger.info(f"Configuration loaded from: {config_file_path}")

        # Store complete config data for arbitrage access
        self._config_data = config_data



        environment_config = self._config_data.get('environment', {})
        if isinstance(environment_config, dict):
            self.ENVIRONMENT = environment_config.get('name', 'dev').lower()
        else:
            self.ENVIRONMENT = str(environment_config).lower()
        if self.ENVIRONMENT not in ('dev', 'prod'):
            raise ConfigurationError(f"Invalid environment '{self.ENVIRONMENT}' in config.yaml", 'environment')

        self.DEBUG_MODE = bool(self._config_data.get('debug_mode', False))

        network_config = self._config_data.get('network', {})
        self._network_config = NetworkConfig(
            request_timeout=float(network_config.get('request_timeout', 10.0)),
            connect_timeout=float(network_config.get('connect_timeout', 5.0)),
            max_retries=int(network_config.get('max_retries', 3)),
            retry_delay=float(network_config.get('retry_delay', 1.0))
        )
        
        # Create WebSocket configuration
        websocket_config = self._config_data.get('websocket', {})
        self._websocket_config = WebSocketConfig(
            connect_timeout=float(websocket_config.get('connect_timeout', 10.0)),
            heartbeat_interval=float(websocket_config.get('heartbeat_interval', 30.0)),
            max_reconnect_attempts=int(websocket_config.get('max_reconnect_attempts', 10)),
            reconnect_delay=float(websocket_config.get('reconnect_delay', 5.0))
        )
        
        # Create exchange configurations
        self._exchange_configs: Dict[str, ExchangeConfig] = {}
        
        for exchange_name, exchange_data in self._config_data.get('exchanges', {}).items():
            # Create credentials
            credentials = ExchangeCredentials(
                api_key=exchange_data.get('api_key', ''),
                secret_key=exchange_data.get('secret_key', '')
            )
            
            # Create rate limit config
            # TODO: rate limiting can be tuned for each endpoint later
            rate_limit_config = self._config_data.get('rate_limiting', {})
            rate_limit_key = f'{exchange_name}_requests_per_second'
            default_rate_limit = 18 if exchange_name == 'mexc' else 15
            rate_limit = RateLimitConfig(
                requests_per_second=int(rate_limit_config.get(rate_limit_key, default_rate_limit))
            )
            
            # Create exchange config
            exchange_config = ExchangeConfig(
                name=exchange_name,
                credentials=credentials,
                base_url=exchange_data.get('base_url', ''),
                websocket_url=exchange_data.get('websocket_url', ''),
                testnet_base_url=exchange_data.get('testnet_base_url'),
                testnet_websocket_url=exchange_data.get('testnet_websocket_url'),
                network=self._network_config,
                rate_limit=rate_limit
            )
            
            self._exchange_configs[exchange_name] = exchange_config
    
    def _substitute_env_vars(self, content: str) -> str:
        """
        Substitute environment variables in configuration content.
        
        Supports syntax:
        - ${VAR_NAME} - Required environment variable
        - ${VAR_NAME:default} - Optional with default value
        
        Args:
            content: Raw configuration content
            
        Returns:
            Content with environment variables substituted
        """
        env_var_pattern = re.compile(r'\$\{([^}]+)\}')
        
        def replace_var(match):
            var_expr = match.group(1)
            
            # Check for default value syntax
            if ':' in var_expr:
                var_name, default_value = var_expr.split(':', 1)
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
        
        # Perform substitution
        result = env_var_pattern.sub(replace_var, content)
        return result
    
    # New structured configuration methods (HFT-optimized)
    
    def get_exchange_config_struct(self, exchange_name: str) -> ExchangeConfig:
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
            raise ConfigurationError(f"Exchange '{exchange_name}' is not configured", exchange_name)
        return self._exchange_configs[exchange_name]
    
    def get_exchange_credentials_struct(self, exchange_name: str) -> ExchangeCredentials:
        """
        Get exchange credentials as structured object.
        
        Args:
            exchange_name: Name of the exchange (e.g., 'mexc', 'gateio')
        
        Returns:
            ExchangeCredentials struct with API credentials
        
        Raises:
            ConfigurationError: If exchange is not configured
        """
        exchange_config = self.get_exchange_config_struct(exchange_name)
        return exchange_config.credentials
    
    def get_network_config(self) -> NetworkConfig:
        """
        Get network configuration as structured object.
        
        Returns:
            NetworkConfig struct with network settings
        """
        return self._network_config
    
    def get_websocket_config(self) -> WebSocketConfig:
        """
        Get WebSocket configuration as structured object.
        
        Returns:
            WebSocketConfig struct with WebSocket settings
        """
        return self._websocket_config
    
    def get_all_exchange_configs(self) -> Dict[str, ExchangeConfig]:
        """
        Get all configured exchanges as structured objects.
        
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
    
    def get_exchanges_with_credentials(self) -> list[str]:
        """
        Get list of exchanges that have valid credentials configured.
        
        Returns:
            List of exchange names with valid API credentials
        """
        return [
            name for name, config in self._exchange_configs.items() 
            if config.has_credentials()
        ]

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


# Create singleton instance
config = HftConfig()


def get_config() -> HftConfig:
    """
    Get the global configuration instance.
    
    Returns:
        Singleton MexcConfig instance
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

def get_exchange_config_struct(exchange_name: str) -> ExchangeConfig:
    """
    Get exchange configuration as structured object.
    
    Args:
        exchange_name: Name of the exchange (e.g., 'mexc', 'gateio')
    
    Returns:
        ExchangeConfig struct with complete exchange configuration
    """
    return config.get_exchange_config_struct(exchange_name)


def get_exchange_credentials_struct(exchange_name: str) -> ExchangeCredentials:
    """
    Get exchange credentials as structured object.
    
    Args:
        exchange_name: Name of the exchange (e.g., 'mexc', 'gateio')
    
    Returns:
        ExchangeCredentials struct with API credentials
    """
    return config.get_exchange_credentials_struct(exchange_name)


def get_network_config() -> NetworkConfig:
    """
    Get network configuration as structured object.
    
    Returns:
        NetworkConfig struct with network settings
    """
    return config.get_network_config()


def get_websocket_config() -> WebSocketConfig:
    """
    Get WebSocket configuration as structured object.
    
    Returns:
        WebSocketConfig struct with WebSocket settings
    """
    return config.get_websocket_config()

