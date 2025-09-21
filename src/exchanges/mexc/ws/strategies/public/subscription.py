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

import logging
from typing import List, Dict, Any, Optional, Set

from core.transport.websocket.strategies.subscription import SubscriptionStrategy, WebsocketChannelType
from core.transport.websocket.structs import SubscriptionAction
from structs.common import Symbol
from core.exchanges.services import SymbolMapperInterface
from exchanges.consts import DEFAULT_PUBLIC_WEBSOCKET_CHANNELS


class MexcPublicSubscriptionStrategy(SubscriptionStrategy):
    """
    MEXC public WebSocket subscription strategy V3.
    
    Creates complete MEXC-format subscription messages with symbols embedded in params.
    Format: "spot@public.aggre.bookTicker.v3.api.pb@100ms@BTCUSDT"
    """
    
    def __init__(self, mapper: Optional[SymbolMapperInterface] = None):
        super().__init__(mapper)  # Initialize parent with injected mapper
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Track active subscriptions for reconnection
        self._active_symbols: Set[Symbol] = set()

    async def create_subscription_messages(self, action: SubscriptionAction,
                                           symbols: List[Symbol],
                                           channels: List[WebsocketChannelType] = DEFAULT_PUBLIC_WEBSOCKET_CHANNELS) -> List[Dict[str, Any]]:
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
        
        method = "SUBSCRIPTION" if action == SubscriptionAction.SUBSCRIBE else "UNSUBSCRIPTION"
        
        # Build params with symbol-specific channels
        if not self.mapper:
            self.logger.error("No symbol mapper available for MEXC subscription")
            return []
            
        params = []
        messages = []
        for symbol in symbols:
            try:
                exchange_symbol = self.mapper.to_pair(symbol)
                if WebsocketChannelType.BOOK_TICKER in channels:
                    params.append(f"spot@public.aggre.bookTicker.v3.api.pb@100ms@{exchange_symbol}")

                if WebsocketChannelType.ORDERBOOK in channels:
                    params.append(f"spot@public.aggre.depth.v3.api.pb@10ms@{exchange_symbol}")

                if WebsocketChannelType.TRADES in channels:
                    params.append( f"spot@public.aggre.deals.v3.api.pb@10ms@{exchange_symbol}")

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