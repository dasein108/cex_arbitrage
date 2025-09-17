from abc import ABC

from core.config.structs import ExchangeConfig
from core.cex.websocket.ws_base import BaseExchangeWebsocketInterface

class BaseExchangePrivateWebsocketInterface(BaseExchangeWebsocketInterface, ABC):
    def __init__(self, config: ExchangeConfig):
        super().__init__(config)
