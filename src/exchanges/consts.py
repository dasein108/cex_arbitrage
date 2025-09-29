from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType

# Default ws channel configuration
DEFAULT_PUBLIC_WEBSOCKET_CHANNELS = [PublicWebsocketChannelType.BOOK_TICKER,
                                     PublicWebsocketChannelType.ORDERBOOK, PublicWebsocketChannelType.TRADES]

DEFAULT_PRIVATE_WEBSOCKET_CHANNELS = [PrivateWebsocketChannelType.TRADE, PrivateWebsocketChannelType.ORDER,
                                      PrivateWebsocketChannelType.BALANCE]