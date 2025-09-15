from abc import ABC
from core.cex.rest.common.base_rest import BaseExchangeRestInterface

class PublicExchangeFuturesRestInterface(BaseExchangeRestInterface, ABC):
    """Abstract cex for public exchange operations (market data)"""
    # TODO: add extended futures-specific methods later
    pass
