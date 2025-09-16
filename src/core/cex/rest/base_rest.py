from abc import ABC
from typing import Callable
import logging

from core.transport.rest.rest_client import RestClient
from core.transport.rest.structs import HTTPMethod, RestConfig
from core.config.structs import ExchangeConfig
from core.cex.services.symbol_mapper.symbol_mapper_factory import get_symbol_mapper


class BaseExchangeRestInterface(ABC):
    """Abstract cex for private exchange operations (trading, account management)"""

    def __init__(self, exchange_tag: str, config: ExchangeConfig, rest_config: RestConfig,
                 custom_exception_handler: Callable):
        self.exchange = config.name
        self.exchange_tag = exchange_tag
        self.api_key = config.credentials.api_key
        self.secret_key = config.credentials.secret_key

        # Initialize REST client (exchange-agnostic)
        self._client = RestClient(
            base_url=config.base_url,
            config=rest_config,
            custom_exception_handler=custom_exception_handler
        )

        self.logger = logging.getLogger(f"{__name__}.{self.exchange_tag}")

        # Symbol mapper injection
        self.symbol_mapper = get_symbol_mapper(config.name)

        self.logger.info(f"Initialized REST client")


    async def _handle_exception(self, exception: Exception):
        raise Exception(f"Error in {self.exchange_tag} REST client: {str(exception)}")

    async def add_auth(self, params: dict = None, headers: dict = None) -> tuple:
        """Add authentication parameters to request"""
        raise NotImplementedError("add_auth must be implemented in subclass")

    async def close(self):
        """Clean up resources and close connections."""
        await self._client.close()

    async def request(self, method: HTTPMethod, endpoint: str, params: dict = None, data: dict = None, headers: dict = None,
                      config: RestConfig = None, auth: bool = False):
        """Make an HTTP request using the REST client."""

        if auth:
            params, headers = await self.add_auth(params=params, headers=headers)

        return await self._client.request(method, endpoint,
                                          params=params, json_data=data, config=config, headers=headers)

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()