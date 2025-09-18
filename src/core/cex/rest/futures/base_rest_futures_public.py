from abc import ABC
from typing import Callable
from core.cex.rest.base_rest import BaseExchangeRestInterface
from core.config.structs import ExchangeConfig
from structs import Symbol


class PublicExchangeFuturesRestInterface(BaseExchangeRestInterface, ABC):
    """Abstract interface for public futures exchange operations (market data)"""
    
    def __init__(self, config: ExchangeConfig, custom_exception_handler: Callable):
        """Initialize public futures interface with transport manager."""
        super().__init__(
            exchange_tag=f"{config.name}_futures_public",
            config=config,
            custom_exception_handler=custom_exception_handler,
            is_private=False  # Public API operations
        )
    
    # TODO: add extended futures-specific methods later

    async def get_funding_rate(self, symbol: Symbol):
        """Get the current funding rate for a futures symbol."""
        raise NotImplementedError("Funding rate retrieval not implemented yet")