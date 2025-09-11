"""
MEXC Configuration Management Module

Simple YAML-based configuration system for MEXC exchange integration.
Loads configuration from config.yaml file with MEXC-specific settings.

Key Features:
- YAML-based configuration for better readability
- MEXC-focused configuration
- Secure API key management
- Type-safe configuration access
- Clear error messages for missing settings

Usage:
    from common.config import config
    
    # MEXC API credentials
    api_key = config.MEXC_API_KEY
    secret = config.MEXC_SECRET_KEY
    
    # System settings
    timeout = config.REQUEST_TIMEOUT
    debug = config.DEBUG_MODE
"""

import os
import logging
from typing import Dict, Optional, Any
from pathlib import Path
import yaml


class ConfigurationError(Exception):
    """Configuration-specific exception for setup errors."""
    
    def __init__(self, message: str, setting_name: Optional[str] = None):
        self.setting_name = setting_name
        super().__init__(message)


class HftConfig:
    """
    MEXC-focused configuration management with YAML support.
    
    Loads configuration from config.yaml file and provides
    type-safe access to MEXC exchange settings.
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
        
        # Load configuration from YAML
        self._load_yaml_config()
        self._validate_required_settings()
        
        # Mark as initialized
        HftConfig._initialized = True
        self._logger.info(f"MEXC configuration initialized for environment: {self.ENVIRONMENT}")
    
    def _load_yaml_config(self) -> None:
        """Load configuration from YAML file."""
        
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
                        config_data = yaml.safe_load(f)
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
        
        # Extract MEXC settings
        mexc_config = config_data.get('mexc', {})
        self.MEXC_API_KEY = mexc_config.get('api_key', '')
        self.MEXC_SECRET_KEY = mexc_config.get('secret_key', '')
        self.MEXC_BASE_URL = mexc_config.get('base_url', 'https://api.mexc.com')
        self.MEXC_WEBSOCKET_URL = mexc_config.get('websocket_url', 'wss://wbs-api.mexc.com/ws')
        
        # Extract network settings
        network_config = config_data.get('network', {})
        self.REQUEST_TIMEOUT = float(network_config.get('request_timeout', 10.0))
        self.CONNECT_TIMEOUT = float(network_config.get('connect_timeout', 5.0))
        self.MAX_RETRIES = int(network_config.get('max_retries', 3))
        self.RETRY_DELAY = float(network_config.get('retry_delay', 1.0))
        
        # Extract rate limiting settings
        rate_limit_config = config_data.get('rate_limiting', {})
        self.MEXC_RATE_LIMIT_PER_SECOND = int(rate_limit_config.get('mexc_requests_per_second', 18))
        
        # Extract WebSocket settings
        websocket_config = config_data.get('websocket', {})
        self.WS_CONNECT_TIMEOUT = float(websocket_config.get('connect_timeout', 10.0))
        self.WS_HEARTBEAT_INTERVAL = float(websocket_config.get('heartbeat_interval', 30.0))
        self.WS_MAX_RECONNECT_ATTEMPTS = int(websocket_config.get('max_reconnect_attempts', 10))
        self.WS_RECONNECT_DELAY = float(websocket_config.get('reconnect_delay', 5.0))
    
    def _validate_required_settings(self) -> None:
        """Validate that required settings are properly configured."""
        
        # Validate MEXC credentials if provided
        if self.MEXC_API_KEY and not self.MEXC_SECRET_KEY:
            raise ConfigurationError("MEXC_API_KEY configured but MEXC_SECRET_KEY is missing", 'MEXC_SECRET_KEY')
        
        if self.MEXC_SECRET_KEY and not self.MEXC_API_KEY:
            raise ConfigurationError("MEXC_SECRET_KEY configured but MEXC_API_KEY is missing", 'MEXC_API_KEY')
        
        # Validate API key format if provided
        if self.MEXC_API_KEY:
            self._validate_api_key_format('MEXC_API_KEY', self.MEXC_API_KEY)
        
        if self.MEXC_SECRET_KEY:
            self._validate_api_key_format('MEXC_SECRET_KEY', self.MEXC_SECRET_KEY)
        
        # Validate numeric settings
        if self.REQUEST_TIMEOUT <= 0 or self.REQUEST_TIMEOUT > 60:
            raise ConfigurationError(f"REQUEST_TIMEOUT must be between 0 and 60 seconds, got {self.REQUEST_TIMEOUT}", 'REQUEST_TIMEOUT')
        
        if self.MEXC_RATE_LIMIT_PER_SECOND <= 0 or self.MEXC_RATE_LIMIT_PER_SECOND > 100:
            raise ConfigurationError(f"MEXC_RATE_LIMIT_PER_SECOND must be between 1 and 100, got {self.MEXC_RATE_LIMIT_PER_SECOND}", 'MEXC_RATE_LIMIT_PER_SECOND')
        
        # Warn about production settings
        if self.ENVIRONMENT == 'prod':
            if not self.MEXC_API_KEY or not self.MEXC_SECRET_KEY:
                self._logger.warning("Production environment detected but MEXC credentials are not configured")
            
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
    
    def has_mexc_credentials(self) -> bool:
        """
        Check if MEXC credentials are configured.
        
        Returns:
            True if both API key and secret are configured
        """
        return bool(self.MEXC_API_KEY) and bool(self.MEXC_SECRET_KEY)
    
    def get_mexc_config(self) -> Dict[str, Any]:
        """
        Get MEXC-specific configuration dictionary.
        
        Returns:
            Dictionary with MEXC configuration settings
        """
        return {
            'api_key': self.MEXC_API_KEY,
            'secret_key': self.MEXC_SECRET_KEY,
            'base_url': self.MEXC_BASE_URL,
            'websocket_url': self.MEXC_WEBSOCKET_URL,
            'rate_limit_per_second': self.MEXC_RATE_LIMIT_PER_SECOND,
            'request_timeout': self.REQUEST_TIMEOUT,
            'max_retries': self.MAX_RETRIES,
            'retry_delay': self.RETRY_DELAY
        }
    
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
            'request_timeout': self.REQUEST_TIMEOUT,
            'max_retries': self.MAX_RETRIES,
            'mexc_rate_limit': self.MEXC_RATE_LIMIT_PER_SECOND,
            'ws_connect_timeout': self.WS_CONNECT_TIMEOUT,
            'ws_heartbeat_interval': self.WS_HEARTBEAT_INTERVAL
        }


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
    print(f"  Debug mode: {cfg.DEBUG_MODE}")
    print(f"  Request timeout: {cfg.REQUEST_TIMEOUT}s")
    print(f"  Rate limit: {cfg.MEXC_RATE_LIMIT_PER_SECOND} req/s")


# Convenience functions
def is_production() -> bool:
    """Check if running in production environment."""
    return config.ENVIRONMENT == 'prod'


def is_debug_enabled() -> bool:
    """Check if debug mode is enabled."""
    return config.DEBUG_MODE


def get_mexc_credentials() -> Dict[str, str]:
    """
    Get MEXC API credentials.
    
    Returns:
        Dictionary with api_key and secret_key
    """
    return {
        'api_key': config.MEXC_API_KEY,
        'secret_key': config.MEXC_SECRET_KEY
    }


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