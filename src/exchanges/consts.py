from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType

# Default ws channel configuration
DEFAULT_PUBLIC_WEBSOCKET_CHANNELS = [PublicWebsocketChannelType.BOOK_TICKER,
                                      PublicWebsocketChannelType.PUB_TRADE] # PublicWebsocketChannelType.ORDERBOOK,

DEFAULT_PRIVATE_WEBSOCKET_CHANNELS = [PrivateWebsocketChannelType.EXECUTION, PrivateWebsocketChannelType.ORDER,
                                      PrivateWebsocketChannelType.BALANCE]