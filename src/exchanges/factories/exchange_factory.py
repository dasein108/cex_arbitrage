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

from typing import List, Optional, Union

from core.config.structs import ExchangeConfig
from core.structs.common import Symbol
from core.structs.common import ExchangeEnum
from ..interfaces import PublicExchangeInterface, PrivateExchangeInterface

# HFT Logger Integration
from core.logging import get_exchange_logger, HFTLoggerInterface, LoggingTimer


class ExchangeFactory:
    """
    Factory for creating CEX exchange instances with proper configuration.
    
    Provides consistent creation patterns across all supported centralized exchanges
    with automatic dependency injection, service registration, and configuration.
    """
    
    # Factory-level HFT logger
    _logger = get_exchange_logger('factory', 'exchange_factory')
    
    # Track factory initialization
    _logger.info("ExchangeFactory initialized")
    _logger.metric("exchange_factories_initialized", 1, tags={"component": "factory"})
    
    @classmethod
    def create_public_exchange(
        cls,
        exchange: ExchangeEnum,
        symbols: Optional[List[Union[str, Symbol]]] = None,
        logger: Optional[HFTLoggerInterface] = None
    ) -> PublicExchangeInterface:
        """
        Create a public exchange instance for market data operations.
        
        Args:
            exchange: Exchange type to create
            symbols: Optional list of symbols to initialize
            logger: Optional HFT logger to inject into exchange
            
        Returns:
            Configured public exchange instance
            
        Raises:
            ValueError: If exchange type is not supported
            ImportError: If exchange implementation is not available
        """
        # Track factory operation performance
        with LoggingTimer(cls._logger, "public_exchange_creation") as timer:
            cls._logger.info("Creating public exchange",
                           exchange=exchange.value,
                           symbol_count=len(symbols) if symbols else 0,
                           has_injected_logger=logger is not None)
            
            # Create exchange-specific logger if not provided
            if logger is None:
                logger = get_exchange_logger(exchange.value, 'public_exchange')
            
            try:
                if exchange == ExchangeEnum.MEXC:
                    from ..mexc import MexcPublicExchange
                    instance = MexcPublicExchange(symbols=symbols or [], logger=logger)
                    
                elif exchange == ExchangeEnum.GATEIO:
                    from ..gateio import GateioPublicExchange
                    instance = GateioPublicExchange(symbols=symbols or [], logger=logger)
                    
                elif exchange == ExchangeEnum.GATEIO_FUTURES:
                    from ..gateio import GateioPublicFuturesExchange
                    instance = GateioPublicFuturesExchange(symbols=symbols or [], logger=logger)
                    
                else:
                    cls._logger.error("Unsupported exchange type",
                                    exchange=exchange.value,
                                    api_type="public")
                    
                    # Track failed creation
                    cls._logger.metric("public_exchange_creations", 1,
                                      tags={"exchange": exchange.value, "status": "unsupported"})
                    
                    raise ValueError(f"Unsupported exchange: {exchange}")
                
                # Track successful creation
                cls._logger.info("Public exchange created successfully",
                               exchange=exchange.value,
                               creation_time_ms=timer.elapsed_ms)
                
                cls._logger.metric("public_exchange_creations", 1,
                                  tags={"exchange": exchange.value, "status": "success"})
                
                cls._logger.metric("public_exchange_creation_duration_ms", timer.elapsed_ms,
                                  tags={"exchange": exchange.value})
                
                return instance
                
            except ImportError as e:
                cls._logger.error("Failed to import exchange implementation",
                                exchange=exchange.value,
                                api_type="public",
                                error_type=type(e).__name__,
                                error_message=str(e),
                                creation_time_ms=timer.elapsed_ms)
                
                # Track import failure
                cls._logger.metric("public_exchange_creations", 1,
                                  tags={"exchange": exchange.value, "status": "import_failed"})
                
                raise ImportError(f"Exchange {exchange.value} implementation not available") from e
    
    @classmethod
    def create_private_exchange(
        cls,
        exchange: ExchangeEnum,
        config: ExchangeConfig,
        symbols: Optional[List[Union[str, Symbol]]] = None,
        logger: Optional[HFTLoggerInterface] = None
    ) -> PrivateExchangeInterface:
        """
        Create a private exchange instance for trading operations.
        
        Args:
            exchange: Exchange type to create
            config: Exchange configuration including credentials
            symbols: Optional list of symbols to initialize
            logger: Optional HFT logger to inject into exchange
            
        Returns:
            Configured private exchange instance
            
        Raises:
            ValueError: If exchange type is not supported or config is invalid
            ImportError: If exchange implementation is not available
        """
        # Validate credentials before creation
        if not config.credentials.is_configured():
            cls._logger.error("Missing credentials for private exchange",
                            exchange=exchange.value,
                            api_type="private")
            
            # Track credential validation failure
            cls._logger.metric("private_exchange_creations", 1,
                              tags={"exchange": exchange.value, "status": "invalid_credentials"})
            
            raise ValueError(f"Exchange {exchange.value} requires valid credentials for private operations")
        
        # Track factory operation performance
        with LoggingTimer(cls._logger, "private_exchange_creation") as timer:
            cls._logger.info("Creating private exchange",
                           exchange=exchange.value,
                           symbol_count=len(symbols) if symbols else 0,
                           has_injected_logger=logger is not None,
                           has_credentials=config.credentials.is_configured())
            
            # Create exchange-specific logger if not provided
            if logger is None:
                logger = get_exchange_logger(exchange.value, 'private_exchange')
            
            try:
                if exchange == ExchangeEnum.MEXC:
                    from ..mexc import MexcPrivateExchange
                    instance = MexcPrivateExchange(config=config, symbols=symbols or [], logger=logger)
                    
                elif exchange == ExchangeEnum.GATEIO:
                    from ..gateio import GateioPrivateExchange
                    instance = GateioPrivateExchange(config=config, symbols=symbols or [], logger=logger)
                    
                elif exchange == ExchangeEnum.GATEIO_FUTURES:
                    from ..gateio import GateioPrivateFuturesExchange
                    instance = GateioPrivateFuturesExchange(config=config, symbols=symbols or [], logger=logger)
                    
                else:
                    cls._logger.error("Unsupported exchange type",
                                    exchange=exchange.value,
                                    api_type="private")
                    
                    # Track failed creation
                    cls._logger.metric("private_exchange_creations", 1,
                                      tags={"exchange": exchange.value, "status": "unsupported"})
                    
                    raise ValueError(f"Unsupported exchange: {exchange}")
                
                # Track successful creation
                cls._logger.info("Private exchange created successfully",
                               exchange=exchange.value,
                               creation_time_ms=timer.elapsed_ms)
                
                cls._logger.metric("private_exchange_creations", 1,
                                  tags={"exchange": exchange.value, "status": "success"})
                
                cls._logger.metric("private_exchange_creation_duration_ms", timer.elapsed_ms,
                                  tags={"exchange": exchange.value})
                
                return instance
                
            except ImportError as e:
                cls._logger.error("Failed to import private exchange implementation",
                                exchange=exchange.value,
                                api_type="private",
                                error_type=type(e).__name__,
                                error_message=str(e),
                                creation_time_ms=timer.elapsed_ms)
                
                # Track import failure
                cls._logger.metric("private_exchange_creations", 1,
                                  tags={"exchange": exchange.value, "status": "import_failed"})
                
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
                
            elif exchange == ExchangeEnum.GATEIO_FUTURES:
                from ..gateio import GateioPublicFuturesExchange, GateioPrivateFuturesExchange
                return True
                
            else:
                return False
                
        except ImportError:
            cls._logger.warning("Exchange implementation not available",
                              exchange=exchange.value)
            return False