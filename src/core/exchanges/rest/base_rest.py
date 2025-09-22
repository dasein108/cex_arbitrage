from abc import ABC
from typing import Callable
import logging

from core.transport.rest.utils import create_rest_transport_manager
from core.transport.rest.structs import HTTPMethod
from core.config.structs import ExchangeConfig
from core.exchanges.services import BaseExchangeMapper

class BaseExchangeRestInterface(ABC):
    """
    Abstract base for exchange REST operations using the new transport system.
    
    Provides unified interface for both public and private exchange operations
    with automatic strategy selection, authentication, and rate limiting.
    """


    def __init__(self, config: ExchangeConfig, mapper: BaseExchangeMapper, is_private: bool = False):
        self.exchange_name = config.name
        tag = '_private' if is_private else '_public'

        self.exchange_tag = f'{self.exchange_name}{tag}'

        # Initialize REST transport manager using factory
        self._rest = create_rest_transport_manager(
            exchange_config=config,
            is_private=is_private,
        )

        self.logger = logging.getLogger(f"{__name__}.{self.exchange_tag}")

        # Inject mapper via dependency injection
        self._mapper = mapper

        self.logger.info(f"Initialized REST transport manager for {config.name} with injected mapper")

    async def close(self):
        """Clean up resources and close connections."""
        await self._rest.close()

    async def request(self, method: HTTPMethod, endpoint: str, params: dict = None, data: dict = None, headers: dict = None):
        """Make an HTTP request using the REST transport manager."""
        # The new transport system handles authentication automatically based on configuration
        return await self._rest.request(method, endpoint, params=params, json_data=data, headers=headers)

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()