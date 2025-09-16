from abc import ABC

from core.config.structs import ExchangeConfig
from core.cex.services.symbol_mapper import get_symbol_mapper

class BaseExchangeWebsocketInterface(ABC):
    def __init__(self, config: ExchangeConfig):
        self.config = config
        self.symbol_mapper = get_symbol_mapper(config.name)
