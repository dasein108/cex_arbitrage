from infrastructure.networking.websocket.structs import PublicWebsocketChannelType

# Default websocket channel configuration
DEFAULT_PUBLIC_WEBSOCKET_CHANNELS = [PublicWebsocketChannelType.BOOK_TICKER,
                                     PublicWebsocketChannelType.ORDERBOOK, PublicWebsocketChannelType.TRADES]
