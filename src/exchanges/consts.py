from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, PrivateWebsocketChannelType

# Default ws channel configuration

# PublicWebsocketChannelType.ORDERBOOK,
DEFAULT_PUBLIC_WEBSOCKET_CHANNELS = [PublicWebsocketChannelType.BOOK_TICKER, PublicWebsocketChannelType.PUB_TRADE]

# PrivateWebsocketChannelType.EXECUTION,
DEFAULT_PRIVATE_WEBSOCKET_CHANNELS = [PrivateWebsocketChannelType.ORDER, PrivateWebsocketChannelType.BALANCE]