"""
Unified Exchange Registration System

Consolidates all exchange implementation registrations based on config.yaml.
Handles REST, WebSocket, mappers, and services with graceful error handling.

Key Features:
- Config-driven exchange discovery
- Credential-aware registration (private only if credentials exist)
- Graceful degradation (skip missing implementations)
- On-demand loading for runtime performance
- Comprehensive error logging without validation failures

HFT COMPLIANT: Lazy loading, minimal startup overhead, runtime optimization.
"""

import importlib
from typing import Dict, Optional, Type
from pathlib import Path
import yaml

from exchanges.structs import ExchangeEnum
from config.structs import ExchangeConfig
from infrastructure.logging import get_logger
from exchanges.transport_factory import (
    register_rest_public, 
    register_rest_private,
    register_ws_public,
    register_ws_private
)

logger = get_logger('exchanges.registry')


class ExchangeRegistry:
    """
    Unified registry for all exchange implementations.
    
    Manages registration of REST, WebSocket, mappers, and services
    for all configured exchanges with graceful error handling.
    """
    
    # Track registration status for each exchange
    _registration_status: Dict[str, Dict[str, bool]] = {}
    _registered_exchanges: set = set()
    
    @classmethod
    def register_all_from_config(cls, config_path: str = "config/config.yaml") -> Dict[str, Dict[str, bool]]:
        """
        Register all exchange implementations based on config.yaml.
        
        Args:
            config_path: Path to config.yaml file
            
        Returns:
            Dictionary of registration results for each exchange
        """
        try:
            # Load config
            config_data = cls._load_config(config_path)
            if not config_data:
                logger.error(f"Failed to load config from {config_path}")
                return {}
            
            # Get exchanges from config
            exchanges_config = config_data.get('exchanges', {})
            if not exchanges_config:
                logger.warning("No exchanges found in config")
                return {}
            
            results = {}
            
            # Register each exchange
            for exchange_name, exchange_config in exchanges_config.items():
                logger.info(f"Processing registration for {exchange_name}")
                
                # Convert config dict to ExchangeConfig
                config_obj = cls._create_exchange_config(exchange_name, exchange_config)
                if not config_obj:
                    logger.error(f"Failed to create config for {exchange_name}")
                    continue
                
                # Register this exchange
                result = cls.register_exchange(exchange_name, config_obj)
                results[exchange_name] = result
                
                # Log summary
                successful = [k for k, v in result.items() if v]
                failed = [k for k, v in result.items() if not v]
                
                if successful:
                    logger.info(f"{exchange_name} registered: {', '.join(successful)}")
                if failed:
                    logger.warning(f"{exchange_name} failed: {', '.join(failed)}")
            
            cls._registration_status = results
            return results
            
        except Exception as e:
            logger.error(f"Failed to register exchanges from config: {e}")
            return {}
    
    @classmethod
    def register_exchange(cls, exchange_name: str, config: ExchangeConfig) -> Dict[str, bool]:
        """
        Register all implementations for a single exchange.
        
        Args:
            exchange_name: Name of the exchange (e.g., 'mexc', 'gateio')
            config: Exchange configuration object
            
        Returns:
            Dictionary showing what was successfully registered
        """
        result = {
            "symbol_mapper": False,
            "exchange_mapper": False,
            "rest_public": False,
            "rest_private": False,
            "ws_public": False,
            "ws_private": False
        }
        
        # Check if already registered
        if exchange_name in cls._registered_exchanges:
            logger.debug(f"{exchange_name} already registered, skipping")
            return cls._registration_status.get(exchange_name, result)
        
        # Determine exchange enum
        exchange_enum = cls._get_exchange_enum(exchange_name)
        if not exchange_enum:
            logger.error(f"Unknown exchange: {exchange_name}")
            return result
        
        # Check for credentials
        has_credentials = config.has_credentials()
        logger.info(f"{exchange_name} credentials: {'found' if has_credentials else 'not found'}")
        
        # Register mappers (required for REST)
        result["symbol_mapper"] = cls._register_symbol_mapper(exchange_name, exchange_enum)
        result["exchange_mapper"] = cls._register_exchange_mapper(exchange_name, exchange_enum)
        
        # Register REST implementations
        result["rest_public"] = cls._register_rest_public(exchange_name, exchange_enum)
        if has_credentials:
            result["rest_private"] = cls._register_rest_private(exchange_name, exchange_enum)
        else:
            logger.info(f"Skipping {exchange_name} private REST (no credentials)")
        
        # Register WebSocket implementations
        result["ws_public"] = cls._register_ws_public(exchange_name, exchange_enum)
        if has_credentials:
            result["ws_private"] = cls._register_ws_private(exchange_name, exchange_enum)
        else:
            logger.info(f"Skipping {exchange_name} private WebSocket (no credentials)")
        
        # Mark as registered
        cls._registered_exchanges.add(exchange_name)
        cls._registration_status[exchange_name] = result
        
        return result
    
    @classmethod
    def _load_config(cls, config_path: str) -> Optional[Dict]:
        """Load config.yaml file."""
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                # Try relative to project root
                config_file = Path(__file__).parent.parent.parent / config_path
            
            if not config_file.exists():
                logger.error(f"Config file not found: {config_path}")
                return None
            
            with open(config_file, 'r') as f:
                return yaml.safe_load(f)
                
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return None
    
    @classmethod
    def _create_exchange_config(cls, exchange_name: str, config_dict: Dict) -> Optional[ExchangeConfig]:
        """Create ExchangeConfig from config dictionary."""
        try:
            from config.structs import ExchangeConfig, ExchangeCredentials
            
            # Extract credentials if present
            creds = None
            if 'api_key' in config_dict and 'secret_key' in config_dict:
                creds = ExchangeCredentials(
                    api_key=config_dict.get('api_key', ''),
                    secret_key=config_dict.get('secret_key', '')
                )
            else:
                creds = ExchangeCredentials(api_key='', secret_key='')
            
            # Create config
            return ExchangeConfig(
                name=exchange_name,
                base_url=config_dict.get('base_url', ''),
                websocket_url=config_dict.get('websocket_url', ''),
                credentials=creds
            )
            
        except Exception as e:
            logger.error(f"Failed to create config for {exchange_name}: {e}")
            return None
    
    @classmethod
    def _get_exchange_enum(cls, exchange_name: str) -> Optional[ExchangeEnum]:
        """Get ExchangeEnum from exchange name."""
        try:
            # Map exchange names to enums
            mapping = {
                'mexc': ExchangeEnum.MEXC_SPOT,
                'mexc_spot': ExchangeEnum.MEXC_SPOT,
                'gateio': ExchangeEnum.GATEIO_SPOT,
                'gateio_spot': ExchangeEnum.GATEIO_SPOT,
                'gateio_futures': ExchangeEnum.GATEIO_FUTURES,
            }
            return mapping.get(exchange_name.lower())
            
        except Exception as e:
            logger.error(f"Failed to get enum for {exchange_name}: {e}")
            return None
    
    @classmethod
    def _try_import_class(cls, module_path: str, class_name: str) -> Optional[Type]:
        """Safely import a class, return None if fails."""
        try:
            module = importlib.import_module(module_path)
            return getattr(module, class_name)
        except ImportError as e:
            logger.error(f"Failed to import module {module_path}: {e}")
            return None
        except AttributeError as e:
            logger.error(f"Class {class_name} not found in {module_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error importing {module_path}.{class_name}: {e}")
            return None
    
    @classmethod
    def _register_symbol_mapper(cls, exchange_name: str, exchange_enum: ExchangeEnum) -> bool:
        """Register symbol mapper for exchange - now using global singletons."""
        try:
            # Import singleton mappers directly - they're already instantiated globally
            if 'mexc' in exchange_name.lower():
                from exchanges.integrations.mexc.services.symbol_mapper import MEXC_SYMBOL_MAPPER
                logger.debug(f"Using MEXC symbol mapper singleton for {exchange_name}")
                return True
            elif 'gateio' in exchange_name.lower():
                if 'futures' in exchange_name.lower():
                    from exchanges.integrations.gateio.services.futures_symbol_mapper import GATEIO_FUTURES_SYMBOL_MAPPER
                    logger.debug(f"Using Gate.io futures symbol mapper singleton for {exchange_name}")
                else:
                    from exchanges.integrations.gateio.services.spot_symbol_mapper import GATEIO_SPOT_SYMBOL_MAPPER
                    logger.debug(f"Using Gate.io spot symbol mapper singleton for {exchange_name}")
                return True
            else:
                logger.warning(f"Unknown exchange for symbol mapper: {exchange_name}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to import symbol mapper singleton for {exchange_name}: {e}")
            return False
    
    @classmethod
    def _register_exchange_mapper(cls, exchange_name: str, exchange_enum: ExchangeEnum) -> bool:
        """Register exchange mapper."""
        try:
            # Determine module path based on exchange
            if 'mexc' in exchange_name.lower():
                module_path = "exchanges.integrations.mexc.services.mexc_mapper"
                class_name = "MexcMappings"
            elif 'gateio' in exchange_name.lower():
                if 'futures' in exchange_name.lower():
                    module_path = "exchanges.integrations.gateio.services.gateio_funtures_mappings"
                    class_name = "GateioFuturesMappings"
                else:
                    module_path = "exchanges.integrations.gateio.services.gateio_mapper"
                    class_name = "GateioMappings"
            else:
                logger.warning(f"Unknown exchange for mapper: {exchange_name}")
                return False
            
            # ExchangeMapperFactory removed - exchanges use direct utility functions now
            logger.debug(f"Exchange mapper registration skipped for {exchange_name} (using direct utils)")
            return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to register exchange mapper for {exchange_name}: {e}")
            return False
    
    @classmethod
    def _register_rest_public(cls, exchange_name: str, exchange_enum: ExchangeEnum) -> bool:
        """Register public REST implementation."""
        try:
            # Determine module path and class name
            if 'mexc' in exchange_name.lower():
                module_path = "exchanges.integrations.mexc.rest.mexc_rest_public"
                class_name = "MexcPublicSpotRest"
            elif 'gateio' in exchange_name.lower():
                if 'futures' in exchange_name.lower():
                    module_path = "exchanges.integrations.gateio.rest.gateio_futures_public"
                    class_name = "GateioPublicFuturesRest"
                else:
                    module_path = "exchanges.integrations.gateio.rest.gateio_rest_public"
                    class_name = "GateioPublicSpotRest"
            else:
                logger.warning(f"Unknown exchange for public REST: {exchange_name}")
                return False
            
            # Import and register
            rest_class = cls._try_import_class(module_path, class_name)
            if rest_class:
                register_rest_public(exchange_enum, rest_class)
                logger.debug(f"Registered public REST for {exchange_name}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to register public REST for {exchange_name}: {e}")
            return False
    
    @classmethod
    def _register_rest_private(cls, exchange_name: str, exchange_enum: ExchangeEnum) -> bool:
        """Register private REST implementation."""
        try:
            # Determine module path and class name
            if 'mexc' in exchange_name.lower():
                module_path = "exchanges.integrations.mexc.rest.mexc_rest_private"
                class_name = "MexcPrivateSpotRest"
            elif 'gateio' in exchange_name.lower():
                if 'futures' in exchange_name.lower():
                    module_path = "exchanges.integrations.gateio.rest.gateio_futures_private"
                    class_name = "GateioPrivateFuturesRest"
                else:
                    module_path = "exchanges.integrations.gateio.rest.gateio_rest_private"
                    class_name = "GateioPrivateSpotRest"
            else:
                logger.warning(f"Unknown exchange for private REST: {exchange_name}")
                return False
            
            # Import and register
            rest_class = cls._try_import_class(module_path, class_name)
            if rest_class:
                register_rest_private(exchange_enum, rest_class)
                logger.debug(f"Registered private REST for {exchange_name}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to register private REST for {exchange_name}: {e}")
            return False
    
    @classmethod
    def _register_ws_public(cls, exchange_name: str, exchange_enum: ExchangeEnum) -> bool:
        """Register public WebSocket implementation."""
        try:
            # Determine module path and class name
            if 'mexc' in exchange_name.lower():
                module_path = "exchanges.integrations.mexc.ws.mexc_ws_public"
                class_name = "MexcPublicWS"
            elif 'gateio' in exchange_name.lower():
                if 'futures' in exchange_name.lower():
                    module_path = "exchanges.integrations.gateio.ws.gateio_ws_public_futures"
                    class_name = "GateioPublicFuturesWS"
                else:
                    module_path = "exchanges.integrations.gateio.ws.gateio_ws_public"
                    class_name = "GateioPublicWS"
            else:
                logger.warning(f"Unknown exchange for public WebSocket: {exchange_name}")
                return False
            
            # Import and register
            ws_class = cls._try_import_class(module_path, class_name)
            if ws_class:
                register_ws_public(exchange_enum, ws_class)
                logger.debug(f"Registered public WebSocket for {exchange_name}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to register public WebSocket for {exchange_name}: {e}")
            return False
    
    @classmethod
    def _register_ws_private(cls, exchange_name: str, exchange_enum: ExchangeEnum) -> bool:
        """Register private WebSocket implementation."""
        try:
            # Determine module path and class name
            if 'mexc' in exchange_name.lower():
                module_path = "exchanges.integrations.mexc.ws.mexc_ws_private"
                class_name = "MexcPrivateWS"
            elif 'gateio' in exchange_name.lower():
                if 'futures' in exchange_name.lower():
                    module_path = "exchanges.integrations.gateio.ws.gateio_ws_private_futures"
                    class_name = "GateioPrivateFuturesWS"
                else:
                    module_path = "exchanges.integrations.gateio.ws.gateio_ws_private"
                    class_name = "GateioPrivateWS"
            else:
                logger.warning(f"Unknown exchange for private WebSocket: {exchange_name}")
                return False
            
            # Import and register
            ws_class = cls._try_import_class(module_path, class_name)
            if ws_class:
                register_ws_private(exchange_enum, ws_class)
                logger.debug(f"Registered private WebSocket for {exchange_name}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to register private WebSocket for {exchange_name}: {e}")
            return False
    
    @classmethod
    def get_registration_status(cls) -> Dict[str, Dict[str, bool]]:
        """Get current registration status for all exchanges."""
        return cls._registration_status.copy()
    
    @classmethod
    def is_registered(cls, exchange_name: str, component: str = None) -> bool:
        """
        Check if an exchange or specific component is registered.
        
        Args:
            exchange_name: Name of the exchange
            component: Optional specific component (e.g., 'rest_public', 'ws_private')
            
        Returns:
            True if registered, False otherwise
        """
        if exchange_name not in cls._registration_status:
            return False
        
        if component:
            return cls._registration_status.get(exchange_name, {}).get(component, False)
        
        # Check if any component is registered
        return any(cls._registration_status.get(exchange_name, {}).values())


# Convenience function for one-line registration
def register_all_exchanges(config_path: str = "config/config.yaml") -> Dict[str, Dict[str, bool]]:
    """
    Register all exchanges from config.yaml.
    
    This is the main entry point for registering all exchange implementations.
    
    Args:
        config_path: Path to config.yaml file
        
    Returns:
        Dictionary of registration results for each exchange
    """
    return ExchangeRegistry.register_all_from_config(config_path)


# Auto-register on import if needed (can be disabled by setting env var)
import os
if os.getenv('AUTO_REGISTER_EXCHANGES', 'false').lower() == 'true':
    register_all_exchanges()