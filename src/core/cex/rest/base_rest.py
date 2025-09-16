from abc import ABC
from typing import Callable
import logging

from core.transport.rest.rest_client import create_transport_from_config
from core.transport.rest.structs import HTTPMethod
from core.config.structs import ExchangeConfig
from core.cex.services.symbol_mapper.symbol_mapper_factory import get_symbol_mapper
from core.cex.services import ExchangeMappingsFactory

class BaseExchangeRestInterface(ABC):
    """
    Abstract base for exchange REST operations using the new transport system.
    
    Provides unified interface for both public and private exchange operations
    with automatic strategy selection, authentication, and rate limiting.
    """

    def __init__(self, exchange_tag: str, config: ExchangeConfig, is_private: bool = False):
        self.exchange = config.name
        self.exchange_tag = exchange_tag
        self.api_key = config.credentials.api_key
        self.secret_key = config.credentials.secret_key

        # Initialize REST transport manager using factory
        self._transport = create_transport_from_config(
            exchange_config=config,
            is_private=is_private,
        )

        self.logger = logging.getLogger(f"{__name__}.{self.exchange_tag}")

        # Symbol mapper injection
        self.symbol_mapper = get_symbol_mapper(config.name)
        # Create exchange-agnostic mappings service using factory - FIX: use actual exchange name
        self._mappings = ExchangeMappingsFactory.create_mappings(str(config.name), self.symbol_mapper)

        self.logger.info(f"Initialized REST transport manager for {config.name}")


    async def _handle_exception(self, exception: Exception):
        raise Exception(f"Error in {self.exchange_tag} REST transport: {str(exception)}")

    async def close(self):
        """Clean up resources and close connections."""
        await self._transport.close()

    async def request(self, method: HTTPMethod, endpoint: str, params: dict = None, data: dict = None, headers: dict = None):
        """Make an HTTP request using the REST transport manager."""
        # The new transport system handles authentication automatically based on configuration
        return await self._transport.request(method, endpoint, params=params, json_data=data, headers=headers)

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()