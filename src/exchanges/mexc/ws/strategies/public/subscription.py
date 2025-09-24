"""
MEXC Public WebSocket Subscription Strategy V3

Direct message-based subscription strategy for MEXC public WebSocket.
Creates complete message objects in MEXC-specific format.

Message Format:
{
    "method": "SUBSCRIPTION",
    "params": [
        "spot@public.aggre.bookTicker.v3.api.pb@100ms@BTCUSDT"
    ]
}
"""

from typing import List, Dict, Any, Optional, Set

from infrastructure.networking.websocket.strategies.subscription import SubscriptionStrategy
from infrastructure.networking.websocket.structs import SubscriptionAction, PublicWebsocketChannelType
from infrastructure.data_structures.common import Symbol
from core.exchanges.services import BaseExchangeMapper
from exchanges.consts import DEFAULT_PUBLIC_WEBSOCKET_CHANNELS

# HFT Logger Integration
from infrastructure.logging import get_strategy_logger, HFTLoggerInterface


class MexcPublicSubscriptionStrategy(SubscriptionStrategy):
    """
    MEXC public WebSocket subscription strategy V3.
    
    Creates complete MEXC-format subscription messages with symbols embedded in params.
    Format: "spot@public.aggre.bookTicker.v3.api.pb@100ms@BTCUSDT"
    """
    
    def __init__(self, mapper: BaseExchangeMapper, logger: Optional[HFTLoggerInterface] = None):
        super().__init__(mapper)  # Initialize parent with mandatory mapper
        
        # Use injected logger or create strategy-specific logger
        if logger is None:
            tags = ['mexc', 'public', 'ws', 'subscription']
            logger = get_strategy_logger('ws.subscription.mexc.public', tags)
        
        self.logger = logger
        
        # Track active subscriptions for reconnection
        self._active_symbols: Set[Symbol] = set()
        
        # Log initialization
        self.logger.info("MexcPublicSubscriptionStrategy initialized",
                        exchange="mexc",
                        api_type="public")
        
        # Track component initialization
        self.logger.metric("mexc_public_subscription_strategies_initialized", 1,
                          tags={"exchange": "mexc", "api_type": "public"})

    async def create_subscription_messages(self, action: SubscriptionAction,
                                           symbols: List[Symbol],
                                           channels: List[PublicWebsocketChannelType] = DEFAULT_PUBLIC_WEBSOCKET_CHANNELS) -> List[Dict[str, Any]]:
        """
        Create MEXC public subscription messages.
        
        Symbol included in params: "spot@public.aggre.bookTicker.v3.api.pb@100ms@BTCUSDT"
        
        Args:
            action: SUBSCRIBE or UNSUBSCRIBE
            symbols: Symbols to subscribe/unsubscribe to/from
            channels: Channel types to subscribe/unsubscribe to/from
        
        Returns:
            Single message with all symbol-specific channels
        """
        if not symbols:
            return []
        
        method = self.mapper.from_subscription_action(action)
        
        # Build params with symbol-specific channels
        if not self.mapper:
            self.logger.error("No symbol mapper available for MEXC subscription")
            return []
            
        messages = []
        for symbol in symbols:
            try:
                # {'code': 0, 'id': 0,
                #  'msg': 'Not Subscribed successfully! '
                #         '[spot@public.increase.depth.v3.api@BTCUSDT,'
                #         'spot@public.aggre.deals.v3.api.pb@BTCUSDT,'
                #         'spot@public.aggre.bookTicker.v3.api.pb@BTCUSDT].  Reason： Blocked! '}
                exchange_symbol = self.mapper.to_pair(symbol)
                params = []  # Reset params for each symbol
                if PublicWebsocketChannelType.BOOK_TICKER in channels:
                    channel_base = self.mapper.get_spot_channel_name(PublicWebsocketChannelType.BOOK_TICKER)
                    params.append(f"{channel_base}@10ms@{exchange_symbol}")

                if PublicWebsocketChannelType.ORDERBOOK in channels:
                    channel_base = self.mapper.get_spot_channel_name(PublicWebsocketChannelType.ORDERBOOK)
                    params.append(f"{channel_base}@10ms@{exchange_symbol}")

                if PublicWebsocketChannelType.TRADES in channels:
                    channel_base = self.mapper.get_spot_channel_name(PublicWebsocketChannelType.TRADES)
                    params.append(f"{channel_base}@10ms@{exchange_symbol}")

                if not len(params):
                    self.logger.warning(f"No valid channels to subscribe for symbol {symbol}")
                    continue

                self.logger.debug(f"Added channels for {symbol}: {exchange_symbol}")

                message = {
                    "method": method,
                    "params": params
                }
                messages.append(message)
            except Exception as e:
                self.logger.error(f"Failed to convert symbol {symbol}: {e}")
                continue
        

        self.logger.info(f"Created {method} {len(messages)}  messages")
        
        return messages