from exchanges.interface.websocket.base_ws import BaseExchangeWebsocketInterface
from structs.exchange import Symbol,  Trade
from exchanges.mexc.common.mexc_config import MexcConfig
from exchanges.mexc.common.mexc_utils import MexcUtils
from common.ws_client import SubscriptionAction
from typing import List, Any

class MexcWebsocketPublic(BaseExchangeWebsocketInterface):
    """Mexc public websocket interface for market data streaming"""

    def __init__(self, config):
        super().__init__(MexcConfig.EXCHANGE_NAME, config)
        self.orderbook = None  # Placeholder for orderbook data structure

    async def _create_subscriptions(self, symbol: Symbol, action: SubscriptionAction, id: int = 1):
        """Prepare the connections for subscriptions specific symbol."""
        # Example subscription message format for Mexc
        symbol_str = MexcUtils.symbol_to_pair(symbol)

        subscriptions = [
                f"spot@public.aggre.deals.v3.api.pb@10ms{symbol_str}@depth",
                f"spot@public.limit.depth.v3.api.pb@{symbol_str}@5"
            ]
        # spot@public.aggre.deals.v3.api.pb@(100ms|10ms)@<symbol>
        #
        # spot@public.limit.depth.v3.api.pb@<symbol>@<level> with level 5
        return subscriptions

    async def _on_message(self, message):
        """Handle incoming messages from the websocket."""
        # TODO: deserialize message based on type use protobuf definitions
        print(f"Received message: {message}")
        # Process the message and update orderbook or other data structures as needed

    async def on_error(self, error):
        """Handle errors from the websocket."""
        print(f"WebSocket error: {error}")

    async def on_orderbook_diff(self, diff: Any):
        # TODO: should remove diff decoded message in msgspec, add spec
        raise NotImplementedError("on_message must be implemented in subclass")

    async def on_trade(self, trades: List[Trade]):
        # TODO: should remove trade decoded message in msgspec
        raise NotImplementedError("on_message must be implemented in subclass")