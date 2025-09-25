from abc import ABC
from exchanges.interfaces.rest.rest_base import BaseRestInterface
# BaseExchangeMapper dependency removed - using direct utility functions
from config.structs import ExchangeConfig
from exchanges.structs import Symbol


class PublicFuturesRest(BaseRestInterface, ABC):
    """Abstract interface for public futures exchange operations (market data)"""
    
    def __init__(self, config: ExchangeConfig):
        """Initialize public futures interface with transport manager."""
        super().__init__(
            config=config,
            is_private=False  # Public API operations
        )
    
    # TODO: add extended futures-specific methods later

    async def get_funding_rate(self, symbol: Symbol):
        """Get the current funding rate for a futures symbol."""
        raise NotImplementedError("Funding rate retrieval not implemented yet")