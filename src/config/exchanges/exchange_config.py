"""
Exchange configuration manager.

Provides specialized configuration management for exchange settings including:
- Exchange-specific configuration
- API endpoint configuration  
- Rate limiting and performance settings
- WebSocket and transport configuration
- Direct credential management from environment variables
"""

import os
import logging
from typing import Dict, Any, List, Optional
from ..structs import (
    ExchangeConfig, ExchangeCredentials, NetworkConfig, RateLimitConfig, 
    WebSocketConfig, RestTransportConfig
)
from exchanges.structs.enums import ExchangeEnum
from exchanges.structs.types import ExchangeName
from infrastructure.exceptions.exchange import ConfigurationError


class ExchangeConfigManager:
    """Manages exchange-specific configuration settings."""
    
    def __init__(self, config_data: Dict[str, Any], network_config: NetworkConfig, websocket_template: Dict[str, Any]):
        self.config_data = config_data
        self.network_config = network_config
        self.websocket_template = websocket_template
        self._exchange_configs: Optional[Dict[str, ExchangeConfig]] = None
        self._logger = logging.getLogger(__name__)
    
    def get_exchange_configs(self) -> Dict[str, ExchangeConfig]:
        """
        Get all exchange configurations.
        
        Returns:
            Dictionary mapping exchange names to ExchangeConfig structs
        """
        if self._exchange_configs is None:
            self._exchange_configs = self._build_exchange_configs()
        return self._exchange_configs
    
    def get_exchange_config(self, exchange_name: str) -> Optional[ExchangeConfig]:
        """
        Get configuration for specific exchange.
        
        Args:
            exchange_name: Exchange name (e.g., 'mexc', 'gateio')
            
        Returns:
            ExchangeConfig struct or None if not configured
        """
        configs = self.get_exchange_configs()
        return configs.get(exchange_name.lower())
    
    def get_all_exchange_configs(self) -> Dict[str, ExchangeConfig]:
        """
        Get all configured exchanges (alias for get_exchange_configs for backward compatibility).
        
        Returns:
            Dictionary mapping exchange names to ExchangeConfig structs
        """
        return self.get_exchange_configs()
    
    def get_configured_exchanges(self) -> List[str]:
        """
        Get list of configured exchange names.
        
        Returns:
            List of exchange names that have been configured
        """
        return list(self.get_exchange_configs().keys())
    
    def _build_exchange_configs(self) -> Dict[str, ExchangeConfig]:
        """Build exchange configurations from config data."""
        exchanges_data = self.config_data.get('exchanges', {})
        configs = {}
        
        if not exchanges_data:
            raise ConfigurationError(
                "No exchanges configured. At least one exchange must be configured.",
                "exchanges"
            )
        
        for exchange_name, exchange_data in exchanges_data.items():
            try:
                config = self._build_single_exchange_config(exchange_name, exchange_data)
                if config:
                    # Store config with the original config name (mexc, gateio) for backward compatibility
                    configs[exchange_name.lower()] = config
            except Exception as e:
                raise ConfigurationError(
                    f"Failed to configure exchange '{exchange_name}': {e}",
                    f"exchanges.{exchange_name}"
                ) from e
        
        return configs
    
    def _build_single_exchange_config(self, exchange_name: str, data: Dict[str, Any]) -> ExchangeConfig:
        """Build configuration for single exchange. Trust config structure, fail fast if wrong."""
        # Trust config structure, let KeyError fail if missing required fields
        credentials = self._extract_credentials_from_config(data)
        
        # Use exchange-specific network config or global fallback - trust it exists
        network_config = data.get('network_config', self.network_config)
        if isinstance(network_config, dict):
            network_config = self._parse_network_config(network_config)
            
        # Extract rate limiting from transport section  
        if 'transport' in data and 'requests_per_second' in data['transport']:
            requests_per_second = data['transport']['requests_per_second']
            rate_limit = self._parse_rate_limit_config({'requests_per_second': requests_per_second})
        else:
            # Fallback to default rate limiting if not specified in transport
            rate_limit = self._parse_rate_limit_config({'requests_per_second': 10.0})

        # Use exchange-specific websocket config or global template
        websocket_config_data = data.get('websocket_config', self.websocket_template)
        websocket_config = self._parse_websocket_config(websocket_config_data)

        # Parse transport config if present
        transport_config = None
        if 'transport' in data:
            transport_config = self._parse_transport_config(data['transport'], exchange_name, is_private=False)

        exchange_config = ExchangeConfig(
            name=ExchangeName(exchange_name.upper()),
            credentials=credentials,
            base_url=data['base_url'],
            websocket_url=data['websocket_url'],
            enabled=data.get('enabled', True),
            network=network_config,
            rate_limit=rate_limit,
            websocket=websocket_config,
            transport=transport_config
        )

        self._logger.debug(f"Configured exchange: {exchange_name} (enabled: {exchange_config.enabled})")
        return exchange_config
    
    def _parse_network_config(self, part_config: Dict[str, Any]) -> NetworkConfig:
        """Parse network configuration from dictionary with comprehensive validation."""
        try:
            return NetworkConfig(
                request_timeout=self._safe_get_config_value(part_config, 'request_timeout', 10.0, float, 'network'),
                connect_timeout=self._safe_get_config_value(part_config, 'connect_timeout', 5.0, float, 'network'),
                max_retries=self._safe_get_config_value(part_config, 'max_retries', 3, int, 'network'),
                retry_delay=self._safe_get_config_value(part_config, 'retry_delay', 1.0, float, 'network')
            )
        except Exception as e:
            raise ConfigurationError(f"Failed to parse network configuration: {e}", "network") from e
    
    def _parse_rate_limit_config(self, part_config: Dict[str, Any]) -> RateLimitConfig:
        """Parse rate limiting configuration. Trust config values, validate HFT requirements."""
        requests_per_second = int(part_config['requests_per_second'])
        
        # Enforce HFT requirements - fail fast
        if requests_per_second <= 0:
            raise ValueError(f"requests_per_second must be positive, got: {requests_per_second}")
        if requests_per_second > 1000:
            raise ValueError(f"requests_per_second {requests_per_second} > 1000 violates HFT requirements")
            
        return RateLimitConfig(requests_per_second=requests_per_second)
    
    def _parse_websocket_config(self, part_config: Dict[str, Any]) -> WebSocketConfig:
        """Parse WebSocket configuration. Allow defaults for optional fields, fail on URL format."""

        return WebSocketConfig(
            connect_timeout=float(part_config.get('connect_timeout', 10.0)),
            ping_interval=float(part_config.get('ping_interval', 20.0)),
            ping_timeout=float(part_config.get('ping_timeout', 10.0)),
            close_timeout=float(part_config.get('close_timeout', 5.0)),
            max_reconnect_attempts=int(part_config.get('max_reconnect_attempts', 10)),
            reconnect_delay=float(part_config.get('reconnect_delay', 1.0)),
            reconnect_backoff=float(part_config.get('reconnect_backoff', 2.0)),
            max_reconnect_delay=float(part_config.get('max_reconnect_delay', 60.0)),
            max_message_size=int(part_config.get('max_message_size', 1048576)),
            max_queue_size=int(part_config.get('max_queue_size', 1000)),
            heartbeat_interval=float(part_config.get('heartbeat_interval', 30.0)),
            enable_compression=bool(part_config.get('enable_compression', True)),
            text_encoding=part_config.get('text_encoding', 'utf-8')
        )
    
    def _parse_transport_config(self, part_config: Dict[str, Any], exchange_name: str, is_private: bool = False) -> RestTransportConfig:
        """Parse REST transport configuration from dictionary with validation."""
        try:
            return RestTransportConfig(
                # Strategy Selection
                exchange_name=exchange_name,
                is_private=is_private,
                
                # Performance Targets
                max_latency_ms=self._safe_get_config_value(part_config, 'max_latency_ms', 50.0, float, 'transport'),
                target_throughput_rps=self._safe_get_config_value(part_config, 'target_throughput_rps', 100.0, float, 'transport'),
                max_retry_attempts=self._safe_get_config_value(part_config, 'max_retry_attempts', 3, int, 'transport'),
                
                # Connection Settings
                connection_timeout_ms=self._safe_get_config_value(part_config, 'connection_timeout_ms', 2000.0, float, 'transport'),
                read_timeout_ms=self._safe_get_config_value(part_config, 'read_timeout_ms', 5000.0, float, 'transport'),
                max_concurrent_requests=self._safe_get_config_value(part_config, 'max_concurrent_requests', 10, int, 'transport'),
                
                # Rate Limiting
                requests_per_second=self._safe_get_config_value(part_config, 'requests_per_second', 20.0, float, 'transport'),
                burst_capacity=self._safe_get_config_value(part_config, 'burst_capacity', 50, int, 'transport'),
                
                # Advanced Settings
                enable_connection_pooling=self._safe_get_config_value(part_config, 'enable_connection_pooling', True, bool, 'transport'),
                enable_compression=self._safe_get_config_value(part_config, 'enable_compression', True, bool, 'transport'),
                user_agent=self._safe_get_config_value(part_config, 'user_agent', "HFTArbitrageEngine/1.0", str, 'transport')
            )
        except Exception as e:
            raise ConfigurationError(f"Failed to parse transport configuration for {exchange_name}: {e}", f"{exchange_name}.transport") from e
    
    def _extract_credentials_from_config(self, data: Dict[str, Any]) -> ExchangeCredentials:
        """
        Extract credentials from exchange configuration data.
        
        This reads from the YAML config data which has already been processed
        with environment variable substitution (e.g., "${MEXC_API_KEY}" -> actual value).
        
        Args:
            data: Exchange configuration data from YAML
            
        Returns:
            ExchangeCredentials with api_key and secret_key (empty strings if not found)
        """
        api_key = data.get('api_key', '')
        secret_key = data.get('secret_key', '')
        
        # Ensure we have strings (environment substitution might return None)
        if api_key is None:
            api_key = ''
        if secret_key is None:
            secret_key = ''
            
        return ExchangeCredentials(api_key=str(api_key), secret_key=str(secret_key))

    def _safe_get_config_value(self, config: Dict[str, Any], key: str, default: Any, value_type: type, config_name: str) -> Any:
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
    
    def validate_exchange_configs(self) -> Dict[str, List[str]]:
        """
        Validate all exchange configurations.
        
        Returns:
            Dictionary mapping exchange names to lists of warning messages
        """
        configs = self.get_exchange_configs()
        validation_results = {}
        
        for exchange_name, config in configs.items():
            warnings = []
            
            try:
                # Use struct validation method
                config.validate()
            except ValueError as e:
                warnings.append(f"Configuration validation failed: {e}")
            
            # HFT-specific validation
            if config.rate_limit and config.rate_limit.requests_per_second < 10:
                warnings.append("Rate limit < 10 may be too restrictive for HFT operations")
            
            if config.network and config.network.request_timeout > 10:
                warnings.append("Request timeout > 10s may cause trading delays")
            
            if not config.has_credentials():
                warnings.append("No credentials configured - trading operations disabled")
            
            if not config.enabled:
                warnings.append("Exchange is disabled")
                
            # Transport-specific validation
            if config.transport:
                if config.transport.max_latency_ms > 100:
                    warnings.append(f"max_latency_ms ({config.transport.max_latency_ms}ms) exceeds HFT requirements")
                
                if config.transport.requests_per_second < 10:
                    warnings.append(f"Transport requests_per_second ({config.transport.requests_per_second}) may be too restrictive")
            
            validation_results[exchange_name] = warnings
        
        return validation_results
    
    def get_enabled_exchanges(self) -> List[str]:
        """
        Get list of enabled exchange names.
        
        Returns:
            List of exchange names that are enabled
        """
        return [name for name, config in self.get_exchange_configs().items() if config.enabled]
    
    def get_trading_ready_exchanges(self) -> List[str]:
        """
        Get list of exchanges ready for trading (enabled + credentials).
        
        Returns:
            List of exchange names ready for trading operations
        """
        return [name for name, config in self.get_exchange_configs().items() if config.is_ready_for_trading()]
    
    def has_trading_exchanges(self) -> bool:
        """
        Check if any exchanges are configured for trading.
        
        Returns:
            True if at least one exchange is ready for trading
        """
        return len(self.get_trading_ready_exchanges()) > 0
    
    # ==== DIAGNOSTIC METHODS FOR CREDENTIALS ====
    # These provide diagnostics for credentials that are now loaded from YAML config
    
    def get_credentials_summary(self) -> Dict[str, Dict[str, Any]]:
        """
        Get summary of credential availability (for diagnostics).
        
        Returns:
            Dictionary with credential availability information
        """
        summary = {}
        
        configs = self.get_exchange_configs()
        
        for exchange_name, config in configs.items():
            credentials = config.credentials
            
            if credentials and credentials.has_private_api:
                summary[exchange_name] = {
                    "available": True,
                    "valid": True,  # If loaded from config, assumed valid
                    "preview": credentials.get_preview(),
                    "has_private_api": credentials.has_private_api
                }
            else:
                summary[exchange_name] = {
                    "available": False,
                    "valid": False,
                    "preview": "Not configured",
                    "has_private_api": False,
                    "note": "Credentials should be set in config.yaml with environment variable substitution (e.g., '${MEXC_API_KEY}')"
                }
        
        return summary