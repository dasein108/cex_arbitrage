"""
CEX Exchange Factory

Centralized factory for creating CEX exchange instances with proper dependency injection
and configuration. Provides consistent creation patterns across all supported exchanges.

Implements Factory Pattern with:
- Type-safe exchange selection via ExchangeEnum
- Automatic dependency injection and service registration
- Exchange-specific configuration and optimization
- Error handling and validation
- SOLID principles compliance

All created exchange instances are properly configured with:
- REST and WebSocket clients
- Symbol mappers and service mappings
- Authentication configuration (for private exchanges)
- Rate limiting and performance optimization
"""

import logging
from typing import List, Optional, Type, Union

from core.config.structs import ExchangeConfig
from structs.common import Symbol
from .. import ExchangeEnum
from ..interfaces import PublicExchangeInterface, PrivateExchangeInterface

logger = logging.getLogger(__name__)


class ExchangeFactory:
    """
    Factory for creating CEX exchange instances with proper configuration.
    
    Provides consistent creation patterns across all supported centralized exchanges
    with automatic dependency injection, service registration, and configuration.
    """
    
    @classmethod
    def create_public_exchange(
        cls,
        exchange: ExchangeEnum,
        symbols: Optional[List[Union[str, Symbol]]] = None
    ) -> PublicExchangeInterface:
        """
        Create a public exchange instance for market data operations.
        
        Args:
            exchange: Exchange type to create
            symbols: Optional list of symbols to initialize
            
        Returns:
            Configured public exchange instance
            
        Raises:
            ValueError: If exchange type is not supported
            ImportError: If exchange implementation is not available
        """
        try:
            if exchange == ExchangeEnum.MEXC:
                from ..mexc import MexcPublicExchange
                return MexcPublicExchange(symbols=symbols or [])
                
            elif exchange == ExchangeEnum.GATEIO:
                from ..gateio import GateioPublicExchange
                return GateioPublicExchange(symbols=symbols or [])
                
            else:
                raise ValueError(f"Unsupported exchange: {exchange}")
                
        except ImportError as e:
            logger.error(f"Failed to import {exchange.value} exchange: {e}")
            raise ImportError(f"Exchange {exchange.value} implementation not available") from e
    
    @classmethod
    def create_private_exchange(
        cls,
        exchange: ExchangeEnum,
        config: ExchangeConfig,
        symbols: Optional[List[Union[str, Symbol]]] = None
    ) -> PrivateExchangeInterface:
        """
        Create a private exchange instance for trading operations.
        
        Args:
            exchange: Exchange type to create
            config: Exchange configuration including credentials
            symbols: Optional list of symbols to initialize
            
        Returns:
            Configured private exchange instance
            
        Raises:
            ValueError: If exchange type is not supported or config is invalid
            ImportError: If exchange implementation is not available
        """
        if not config.credentials.is_configured():
            raise ValueError(f"Exchange {exchange.value} requires valid credentials for private operations")
            
        try:
            if exchange == ExchangeEnum.MEXC:
                from ..mexc import MexcPrivateExchange
                return MexcPrivateExchange(config=config, symbols=symbols or [])
                
            elif exchange == ExchangeEnum.GATEIO:
                from ..gateio import GateioPrivateExchange
                return GateioPrivateExchange(config=config, symbols=symbols or [])
                
            else:
                raise ValueError(f"Unsupported exchange: {exchange}")
                
        except ImportError as e:
            logger.error(f"Failed to import {exchange.value} private exchange: {e}")
            raise ImportError(f"Private exchange {exchange.value} implementation not available") from e
    
    @classmethod
    def get_supported_exchanges(cls) -> List[ExchangeEnum]:
        """
        Get list of all supported exchange types.
        
        Returns:
            List of supported exchange enums
        """
        return list(ExchangeEnum)
    
    @classmethod
    def is_exchange_supported(cls, exchange: ExchangeEnum) -> bool:
        """
        Check if an exchange type is supported.
        
        Args:
            exchange: Exchange type to check
            
        Returns:
            True if exchange is supported, False otherwise
        """
        return exchange in ExchangeEnum
    
    @classmethod
    def validate_exchange_availability(cls, exchange: ExchangeEnum) -> bool:
        """
        Validate that an exchange implementation is available for import.
        
        Args:
            exchange: Exchange type to validate
            
        Returns:
            True if exchange implementation is available, False otherwise
        """
        try:
            if exchange == ExchangeEnum.MEXC:
                from ..mexc import MexcPublicExchange, MexcPrivateExchange
                return True
                
            elif exchange == ExchangeEnum.GATEIO:
                from ..gateio import GateioPublicExchange, GateioPrivateExchange
                return True
                
            else:
                return False
                
        except ImportError:
            logger.warning(f"Exchange {exchange.value} implementation not available")
            return False