from typing import Optional
import time

from infrastructure.networking.http import HTTPMethod, RestManager

from config.structs import ExchangeConfig

# HFT Logger Integration
from infrastructure.logging import HFTLoggerInterface, LoggingTimer

class BaseRestInterface:
    """
    Abstract composite for exchange REST operations using the new transport system.
    
    Provides unified interface for both public and private exchange operations
    with automatic strategy selection, authentication, and rate limiting.
    """


    def __init__(self, rest_manager: RestManager, config: ExchangeConfig, logger: Optional[HFTLoggerInterface]):
        # Direct injection - no lazy initialization
        self._rest: RestManager = rest_manager
        
        # Store configuration for child implementations
        self.config = config
        self.exchange_name = config.name
        # Setup logging
        self.logger = logger
        
        # Log initialization
        self.logger.info("BaseRestInterface initialized", exchange=config.name)
        self.logger.metric("rest_base_interfaces_initialized", 1, tags={"exchange": config.name})


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