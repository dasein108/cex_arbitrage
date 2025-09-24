from abc import ABC
from exchanges.base.rest.base_rest import BaseExchangeRestInterface
from exchanges.services import BaseExchangeMapper
from infrastructure.config.structs import ExchangeConfig
from infrastructure.data_structures import Symbol


class PublicExchangeFuturesRestInterface(BaseExchangeRestInterface, ABC):
    """Abstract interface for public futures exchange operations (market data)"""
    
    def __init__(self, config: ExchangeConfig, mapper: BaseExchangeMapper):
        """Initialize public futures interface with transport manager and mapper."""
        super().__init__(
            config=config,
            mapper=mapper,
            is_private=False  # Public API operations
        )
    
    # TODO: add extended futures-specific methods later

    async def get_funding_rate(self, symbol: Symbol):
        """Get the current funding rate for a futures symbol."""
        raise NotImplementedError("Funding rate retrieval not implemented yet")