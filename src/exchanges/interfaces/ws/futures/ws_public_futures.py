from typing import List

from exchanges.consts import DEFAULT_PUBLIC_WEBSOCKET_CHANNELS
from exchanges.interfaces.ws.spot.ws_spot_public import PublicSpotWebsocket
from exchanges.structs.common import Symbol
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType
from exchanges.utils.exchange_utils import to_futures_symbols

class PublicFuturesWebsocket(PublicSpotWebsocket):
    async def initialize(self, symbols: List[Symbol],
                         channels: List[PublicWebsocketChannelType]=DEFAULT_PUBLIC_WEBSOCKET_CHANNELS) -> None:
        await super().initialize(to_futures_symbols(symbols), channels)

    async def subscribe(self, symbols: List[Symbol]) -> None:
        await super().subscribe(to_futures_symbols(symbols))

    async def unsubscribe(self, symbols: List[Symbol]) -> None:
        await super().unsubscribe(to_futures_symbols(symbols))