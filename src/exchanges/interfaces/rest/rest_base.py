from abc import ABC
from typing import Callable, Optional

from infrastructure.networking.http.utils import create_rest_transport_manager
from infrastructure.networking.http.structs import HTTPMethod
from infrastructure.config.structs import ExchangeConfig
from exchanges.services import BaseExchangeMapper

# HFT Logger Integration
from infrastructure.logging import get_exchange_logger, HFTLoggerInterface, LoggingTimer

class BaseExchangeRestInterface(ABC):
    """
    Abstract composite for exchange REST operations using the new transport system.
    
    Provides unified interface for both public and private exchange operations
    with automatic strategy selection, authentication, and rate limiting.
    """


    def __init__(self, config: ExchangeConfig, mapper: BaseExchangeMapper, is_private: bool = False, logger: Optional[HFTLoggerInterface] = None):
        self.exchange_name = config.name
        api_type = 'private' if is_private else 'public'
        self.exchange_tag = f'{self.exchange_name}_{api_type}'

        # Use injected logger or create exchange-specific logger
        component_name = f'rest.composite.{api_type}'
        self.logger = logger or get_exchange_logger(config.name, component_name)

        # Initialize REST transport manager using factory
        self._rest = create_rest_transport_manager(
            exchange_config=config,
            is_private=is_private,
        )

        # Inject mapper via dependency injection
        self._mapper = mapper

        # Log initialization with structured data
        self.logger.info("BaseExchangeRestInterface initialized",
                        exchange=config.name,
                        api_type=api_type,
                        has_mapper=mapper is not None)
        
        # Track component initialization metrics
        self.logger.metric("rest_base_interfaces_initialized", 1,
                          tags={"exchange": config.name, "api_type": api_type})

    async def close(self):
        """Clean up resources and close connections."""
        self.logger.debug("Closing BaseExchangeRestInterface",
                         exchange=self.exchange_name)
        
        try:
            await self._rest.close()
            self.logger.info("BaseExchangeRestInterface closed successfully",
                           exchange=self.exchange_name)
        except Exception as e:
            self.logger.error("Error closing BaseExchangeRestInterface",
                            exchange=self.exchange_name,
                            error_type=type(e).__name__,
                            error_message=str(e))
            raise

    async def request(self, method: HTTPMethod, endpoint: str, params: dict = None, data: dict = None, headers: dict = None):
        """Make an HTTP request using the REST transport manager with performance tracking."""
        # Track request performance and metrics
        with LoggingTimer(self.logger, "rest_base_request") as timer:
            self.logger.debug("Making REST request",
                            exchange=self.exchange_name,
                            method=method.value,
                            endpoint=endpoint,
                            has_params=params is not None,
                            has_data=data is not None)
            
            try:
                # The new transport system handles authentication automatically based on configuration
                result = await self._rest.request(method, endpoint, params=params, json_data=data, headers=headers)
                
                # Track successful request metrics
                self.logger.metric("rest_base_requests_completed", 1,
                                  tags={"exchange": self.exchange_name, 
                                       "method": method.value,
                                       "endpoint": endpoint,
                                       "status": "success"})
                
                self.logger.metric("rest_base_request_duration_ms", timer.elapsed_ms,
                                  tags={"exchange": self.exchange_name,
                                       "method": method.value,
                                       "endpoint": endpoint})
                
                return result
                
            except Exception as e:
                # Track failed request metrics
                error_type = type(e).__name__
                self.logger.error("REST request failed",
                                exchange=self.exchange_name,
                                method=method.value,
                                endpoint=endpoint,
                                error_type=error_type,
                                error_message=str(e),
                                duration_ms=timer.elapsed_ms)
                
                self.logger.metric("rest_base_requests_completed", 1,
                                  tags={"exchange": self.exchange_name,
                                       "method": method.value,
                                       "endpoint": endpoint,
                                       "status": "error",
                                       "error_type": error_type})
                
                raise

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()