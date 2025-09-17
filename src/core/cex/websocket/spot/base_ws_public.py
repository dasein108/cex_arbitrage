from abc import ABC
from typing import Callable, Optional, Awaitable, List
from core.config.structs import ExchangeConfig
from structs.exchange import Symbol, Trade
from core.transport.websocket.structs import ConnectionState
from core.cex.websocket.ws_base import BaseExchangeWebsocketInterface


class BaseExchangePublicWebsocketInterface(BaseExchangeWebsocketInterface, ABC):
    def __init__(self, config: ExchangeConfig,
                 orderbook_diff_handler: Optional[Callable[[any, Symbol], Awaitable[None]]] = None,
                 trades_handler: Optional[Callable[[Symbol, List[Trade]], Awaitable[None]]] = None,
                 state_change_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None
                 ):
        super().__init__("public", config)
        self.orderbook_diff_handler = orderbook_diff_handler
        self.trades_handler = trades_handler
        self.state_change_handler = state_change_handler