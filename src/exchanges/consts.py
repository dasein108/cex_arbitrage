from infrastructure.networking.websocket.structs import PublicWebsocketChannelType

# Default ws channel configuration
DEFAULT_PUBLIC_WEBSOCKET_CHANNELS = [PublicWebsocketChannelType.BOOK_TICKER,
                                     PublicWebsocketChannelType.ORDERBOOK, PublicWebsocketChannelType.TRADES]
