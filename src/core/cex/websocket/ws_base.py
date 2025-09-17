from abc import ABC

from core.config.structs import ExchangeConfig
from core.cex.services.symbol_mapper import get_symbol_mapper
from logging import getLogger


class BaseExchangeWebsocketInterface(ABC):
    def __init__(self, tag: str, config: ExchangeConfig):
        self.config = config
        self.symbol_mapper = get_symbol_mapper(config.name)
        self.logger = getLogger(f"{config.name}_{tag}_ws")
        self._tag = tag
