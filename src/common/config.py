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
    
    # Exchange API credentials (new unified approach)
    mexc_credentials = config.get_exchange_credentials('mexc')
    gateio_credentials = config.get_exchange_credentials('gateio')
    
    # Exchange configuration
    mexc_config = config.get_exchange_config('mexc')
    gateio_config = config.get_exchange_config('gateio')
    
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


class ConfigurationError(Exception):
    """Configuration-specific exception for setup errors."""
    
    def __init__(self, message: str, setting_name: Optional[str] = None):
        self.setting_name = setting_name
        super().__init__(message)


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
        self._validate_required_settings()
        
        # Mark as initialized
        HftConfig._initialized = True
        self._logger.info(f"HFT configuration initialized for environment: {self.ENVIRONMENT}")
    
    def _load_env_file(self) -> None:
        """
        Load environment variables from .env file in project root.
        
        Tries multiple locations to find the .env file:
        1. Project root (preferred)
        2. Parent directories
        3. Current working directory
        """

        # Try multiple locations for .env file
        env_paths = [
            Path(__file__).parent.parent.parent / '.env',  # Project root
            Path(__file__).parent.parent / '.env',         # src directory
            Path.cwd() / '.env',                            # Current working directory
            Path.home() / '.env',                           # User home directory (fallback)
        ]
        
        env_loaded = False
        for env_path in env_paths:
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
        
        # Look for config.yaml in multiple locations
        config_paths = [
            Path(__file__).parent.parent.parent / 'config.yaml',  # Project root
            Path(__file__).parent.parent / 'config.yaml',         # src directory
            Path(__file__).parent / 'config.yaml',                # common directory
            Path.cwd() / 'config.yaml'                            # Current working directory
        ]
        
        config_data = None
        config_file_path = None
        
        for config_path in config_paths:
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
                    self._logger.warning(f"Failed to load config from {config_path}: {e}")
                    continue
        
        if config_data is None:
            raise ConfigurationError(
                f"No valid config.yaml found. Searched paths: {[str(p) for p in config_paths]}"
            )
        
        self._logger.info(f"Configuration loaded from: {config_file_path}")
        
        # Extract environment settings
        env_config = config_data.get('environment', {})
        self.ENVIRONMENT = env_config.get('name', 'dev')
        self.DEBUG_MODE = env_config.get('debug', True if self.ENVIRONMENT == 'dev' else False)
        self.LOG_LEVEL = env_config.get('log_level', 'DEBUG' if self.DEBUG_MODE else 'INFO')
        
        # Extract exchanges settings as dictionary
        self.exchanges = config_data.get('exchanges', {})
        
        # Legacy compatibility - add individual properties for backward compatibility during transition
        mexc_config = self.exchanges.get('mexc', {})
        self.MEXC_API_KEY = mexc_config.get('api_key', '')
        self.MEXC_SECRET_KEY = mexc_config.get('secret_key', '')
        self.MEXC_BASE_URL = mexc_config.get('base_url', 'https://api.mexc.com')
        self.MEXC_WEBSOCKET_URL = mexc_config.get('websocket_url', 'wss://wbs-api.mexc.com/ws')
        
        gateio_config = self.exchanges.get('gateio', {})
        self.GATEIO_API_KEY = gateio_config.get('api_key', '')
        self.GATEIO_SECRET_KEY = gateio_config.get('secret_key', '')
        self.GATEIO_BASE_URL = gateio_config.get('base_url', 'https://api.gateio.ws/api/v4')
        self.GATEIO_WEBSOCKET_URL = gateio_config.get('websocket_url', 'wss://api.gateio.ws/ws/v4/')
        self.GATEIO_TESTNET_BASE_URL = gateio_config.get('testnet_base_url', 'https://api-testnet.gateapi.io/api/v4')
        self.GATEIO_TESTNET_WEBSOCKET_URL = gateio_config.get('testnet_websocket_url', 'wss://ws-testnet.gate.com/v4/ws/spot')
        
        # Extract network settings
        network_config = config_data.get('network', {})
        self.REQUEST_TIMEOUT = float(network_config.get('request_timeout', 10.0))
        self.CONNECT_TIMEOUT = float(network_config.get('connect_timeout', 5.0))
        self.MAX_RETRIES = int(network_config.get('max_retries', 3))
        self.RETRY_DELAY = float(network_config.get('retry_delay', 1.0))
        
        # Extract rate limiting settings
        rate_limit_config = config_data.get('rate_limiting', {})
        self.MEXC_RATE_LIMIT_PER_SECOND = int(rate_limit_config.get('mexc_requests_per_second', 18))
        self.GATEIO_RATE_LIMIT_PER_SECOND = int(rate_limit_config.get('gateio_requests_per_second', 15))
        
        # Extract WebSocket settings
        websocket_config = config_data.get('websocket', {})
        self.WS_CONNECT_TIMEOUT = float(websocket_config.get('connect_timeout', 10.0))
        self.WS_HEARTBEAT_INTERVAL = float(websocket_config.get('heartbeat_interval', 30.0))
        self.WS_MAX_RECONNECT_ATTEMPTS = int(websocket_config.get('max_reconnect_attempts', 10))
        self.WS_RECONNECT_DELAY = float(websocket_config.get('reconnect_delay', 5.0))
        
        # Store complete config data for arbitrage access
        self._config_data = config_data
    
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
    
    def _validate_required_settings(self) -> None:
        """Validate that required settings are properly configured."""
        
        # Validate exchange credentials
        for exchange_name, exchange_config in self.exchanges.items():
            api_key = exchange_config.get('api_key', '')
            secret_key = exchange_config.get('secret_key', '')
            
            # Validate paired credentials
            if api_key and not secret_key:
                raise ConfigurationError(f"{exchange_name.upper()}_API_KEY configured but {exchange_name.upper()}_SECRET_KEY is missing", f'{exchange_name.upper()}_SECRET_KEY')
            
            if secret_key and not api_key:
                raise ConfigurationError(f"{exchange_name.upper()}_SECRET_KEY configured but {exchange_name.upper()}_API_KEY is missing", f'{exchange_name.upper()}_API_KEY')
            
            # Validate API key format if provided
            if api_key:
                self._validate_api_key_format(f'{exchange_name.upper()}_API_KEY', api_key)
            
            if secret_key:
                self._validate_api_key_format(f'{exchange_name.upper()}_SECRET_KEY', secret_key)
        
        # Validate numeric settings
        if self.REQUEST_TIMEOUT <= 0 or self.REQUEST_TIMEOUT > 60:
            raise ConfigurationError(f"REQUEST_TIMEOUT must be between 0 and 60 seconds, got {self.REQUEST_TIMEOUT}", 'REQUEST_TIMEOUT')
        
        if self.MEXC_RATE_LIMIT_PER_SECOND <= 0 or self.MEXC_RATE_LIMIT_PER_SECOND > 100:
            raise ConfigurationError(f"MEXC_RATE_LIMIT_PER_SECOND must be between 1 and 100, got {self.MEXC_RATE_LIMIT_PER_SECOND}", 'MEXC_RATE_LIMIT_PER_SECOND')
        
        if self.GATEIO_RATE_LIMIT_PER_SECOND <= 0 or self.GATEIO_RATE_LIMIT_PER_SECOND > 100:
            raise ConfigurationError(f"GATEIO_RATE_LIMIT_PER_SECOND must be between 1 and 100, got {self.GATEIO_RATE_LIMIT_PER_SECOND}", 'GATEIO_RATE_LIMIT_PER_SECOND')
        
        # Warn about production settings
        if self.ENVIRONMENT == 'prod':
            for exchange_name in self.exchanges.keys():
                if not self.has_exchange_credentials(exchange_name):
                    self._logger.warning(f"Production environment detected but {exchange_name.upper()} credentials are not configured")
            
            if self.DEBUG_MODE:
                self._logger.warning("DEBUG_MODE is enabled in production environment")
    
    def _validate_api_key_format(self, key_name: str, key_value: str) -> None:
        """
        Validate API key format without logging sensitive data.
        
        Args:
            key_name: Name of the configuration key
            key_value: API key value to validate
        """
        if not key_value:
            return  # Empty keys are allowed
        
        # Basic format validation without exposing the key
        if len(key_value) < 10:
            raise ConfigurationError(f"{key_name} appears to be too short (minimum 10 characters)", key_name)
        
        if ' ' in key_value:
            raise ConfigurationError(f"{key_name} contains invalid whitespace characters", key_name)
        
        # Log successful validation without exposing key
        key_preview = f"{key_value[:4]}...{key_value[-4:]}" if len(key_value) > 8 else "***"
        self._logger.debug(f"{key_name} format validation passed: {key_preview}")
    
    def has_exchange_credentials(self, exchange_name: str) -> bool:
        """
        Check if exchange credentials are configured.
        
        Args:
            exchange_name: Name of the exchange (e.g., 'mexc', 'gateio')
        
        Returns:
            True if both API key and secret are configured for the exchange
        """
        exchange_config = self.exchanges.get(exchange_name.lower(), {})
        api_key = exchange_config.get('api_key', '')
        secret_key = exchange_config.get('secret_key', '')
        return bool(api_key) and bool(secret_key)
    
    def has_mexc_credentials(self) -> bool:
        """
        Check if MEXC credentials are configured.
        
        Returns:
            True if both API key and secret are configured
        """
        return self.has_exchange_credentials('mexc')
    
    def has_gateio_credentials(self) -> bool:
        """
        Check if Gate.io credentials are configured.
        
        Returns:
            True if both API key and secret are configured
        """
        return self.has_exchange_credentials('gateio')
    
    def get_exchange_config(self, exchange_name: str) -> Dict[str, Any]:
        """
        Get exchange-specific configuration dictionary.
        
        Args:
            exchange_name: Name of the exchange (e.g., 'mexc', 'gateio')
        
        Returns:
            Dictionary with exchange configuration settings
        """
        exchange_config = self.exchanges.get(exchange_name.lower(), {}).copy()
        
        # Add common network settings
        exchange_config.update({
            'request_timeout': self.REQUEST_TIMEOUT,
            'max_retries': self.MAX_RETRIES,
            'retry_delay': self.RETRY_DELAY
        })
        
        # Add exchange-specific rate limits
        if exchange_name.lower() == 'mexc':
            exchange_config['rate_limit_per_second'] = self.MEXC_RATE_LIMIT_PER_SECOND
        elif exchange_name.lower() == 'gateio':
            exchange_config['rate_limit_per_second'] = self.GATEIO_RATE_LIMIT_PER_SECOND
        
        return exchange_config
    
    def get_exchange_credentials(self, exchange_name: str) -> Dict[str, str]:
        """
        Get exchange credentials.
        
        Args:
            exchange_name: Name of the exchange (e.g., 'mexc', 'gateio')
        
        Returns:
            Dictionary with api_key and secret_key
        """
        exchange_config = self.exchanges.get(exchange_name.lower(), {})
        return {
            'api_key': exchange_config.get('api_key', ''),
            'secret_key': exchange_config.get('secret_key', '')
        }
    
    def get_mexc_config(self) -> Dict[str, Any]:
        """
        Get MEXC-specific configuration dictionary.
        
        Returns:
            Dictionary with MEXC configuration settings
        """
        return self.get_exchange_config('mexc')
    
    def get_gateio_config(self) -> Dict[str, Any]:
        """
        Get Gate.io-specific configuration dictionary.
        
        Returns:
            Dictionary with Gate.io configuration settings
        """
        return self.get_exchange_config('gateio')
    
    def get_safe_summary(self) -> Dict[str, Any]:
        """
        Get configuration summary without sensitive data.
        
        Returns:
            Dictionary with non-sensitive configuration values
        """
        return {
            'environment': self.ENVIRONMENT,
            'debug_mode': self.DEBUG_MODE,
            'log_level': self.LOG_LEVEL,
            'mexc_base_url': self.MEXC_BASE_URL,
            'mexc_websocket_url': self.MEXC_WEBSOCKET_URL,
            'mexc_credentials_configured': self.has_mexc_credentials(),
            'gateio_base_url': self.GATEIO_BASE_URL,
            'gateio_websocket_url': self.GATEIO_WEBSOCKET_URL,
            'gateio_credentials_configured': self.has_gateio_credentials(),
            'request_timeout': self.REQUEST_TIMEOUT,
            'max_retries': self.MAX_RETRIES,
            'mexc_rate_limit': self.MEXC_RATE_LIMIT_PER_SECOND,
            'gateio_rate_limit': self.GATEIO_RATE_LIMIT_PER_SECOND,
            'ws_connect_timeout': self.WS_CONNECT_TIMEOUT,
            'ws_heartbeat_interval': self.WS_HEARTBEAT_INTERVAL
        }
    
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


# Create singleton instance
config = HftConfig()


def get_config() -> HftConfig:
    """
    Get the global configuration instance.
    
    Returns:
        Singleton MexcConfig instance
    """
    return config


def validate_configuration() -> None:
    """
    Validate that the configuration is properly set up.
    
    Raises:
        ConfigurationError: If critical settings are missing or invalid
    """
    # This will trigger validation through the singleton pattern
    cfg = get_config()
    
    print(f"Configuration validation passed:")
    print(f"  Environment: {cfg.ENVIRONMENT}")
    print(f"  MEXC credentials: {'✓' if cfg.has_mexc_credentials() else '✗'}")
    print(f"  Gate.io credentials: {'✓' if cfg.has_gateio_credentials() else '✗'}")
    print(f"  Debug mode: {cfg.DEBUG_MODE}")
    print(f"  Request timeout: {cfg.REQUEST_TIMEOUT}s")
    print(f"  MEXC rate limit: {cfg.MEXC_RATE_LIMIT_PER_SECOND} req/s")
    print(f"  Gate.io rate limit: {cfg.GATEIO_RATE_LIMIT_PER_SECOND} req/s")
    print(f"  Arbitrage config: {'✓' if cfg.has_arbitrage_config() else '✗'}")
    
    if cfg.has_arbitrage_config():
        arb_config = cfg.get_arbitrage_config()
        risk_limits = cfg.get_arbitrage_risk_limits()
        print(f"  Arbitrage engine: {arb_config.get('engine_name', 'Not configured')}")
        print(f"  Dry run mode: {arb_config.get('enable_dry_run', 'Not configured')}")
        print(f"  Max position size: ${risk_limits.get('max_position_size_usd', 'Not configured')}")
        print(f"  Min profit margin: {risk_limits.get('min_profit_margin_bps', 'Not configured')} bps")


# Convenience functions
def is_production() -> bool:
    """Check if running in production environment."""
    return config.ENVIRONMENT == 'prod'


def is_debug_enabled() -> bool:
    """Check if debug mode is enabled."""
    return config.DEBUG_MODE


def get_exchange_credentials(exchange_name: str) -> Dict[str, str]:
    """
    Get exchange API credentials.
    
    Args:
        exchange_name: Name of the exchange (e.g., 'mexc', 'gateio')
    
    Returns:
        Dictionary with api_key and secret_key
    """
    return config.get_exchange_credentials(exchange_name)


def get_mexc_credentials() -> Dict[str, str]:
    """
    Get MEXC API credentials.
    
    Returns:
        Dictionary with api_key and secret_key
    """
    return get_exchange_credentials('mexc')


def get_gateio_credentials() -> Dict[str, str]:
    """
    Get Gate.io API credentials.
    
    Returns:
        Dictionary with api_key and secret_key
    """
    return get_exchange_credentials('gateio')


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


if __name__ == "__main__":
    """Configuration validation and testing."""
    try:
        validate_configuration()
        safe_summary = config.get_safe_summary()
        print("\nConfiguration Summary:")
        for key, value in safe_summary.items():
            print(f"  {key}: {value}")
    except ConfigurationError as e:
        print(f"Configuration Error: {e}")
        if e.setting_name:
            print(f"Setting: {e.setting_name}")
    except Exception as e:
        print(f"Unexpected error during configuration validation: {e}")