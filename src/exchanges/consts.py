from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType

# Default ws channel configuration
DEFAULT_PUBLIC_WEBSOCKET_CHANNELS = [PublicWebsocketChannelType.BOOK_TICKER,
                                     PublicWebsocketChannelType.ORDERBOOK, PublicWebsocketChannelType.PUB_TRADE]

DEFAULT_PRIVATE_WEBSOCKET_CHANNELS = [PrivateWebsocketChannelType.EXECUTION, PrivateWebsocketChannelType.ORDER,
                                      PrivateWebsocketChannelType.BALANCE]