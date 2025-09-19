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

import time
import logging
from typing import List, Dict, Any, Optional, Set

from core.transport.websocket.strategies.subscription import SubscriptionStrategy
from core.transport.websocket.structs import SubscriptionAction
from structs.common import Symbol
from core.cex.services import SymbolMapperInterface


class MexcPublicSubscriptionStrategy(SubscriptionStrategy):
    """
    MEXC public WebSocket subscription strategy V3.
    
    Creates complete MEXC-format subscription messages with symbols embedded in params.
    Format: "spot@public.aggre.bookTicker.v3.api.pb@100ms@BTCUSDT"
    """
    
    def __init__(self, symbol_mapper: SymbolMapperInterface):
        self.symbol_mapper = symbol_mapper
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Track active subscriptions for reconnection
        self._active_symbols: Set[Symbol] = set()

    async def create_subscription_messages(
        self,
        action: SubscriptionAction,
        symbols: List[Symbol]
    ) -> List[Dict[str, Any]]:
        """
        Create MEXC public subscription messages.
        
        Symbol included in params: "spot@public.aggre.bookTicker.v3.api.pb@100ms@BTCUSDT"
        
        Args:
            action: SUBSCRIBE or UNSUBSCRIBE
            symbols: Symbols to subscribe/unsubscribe to/from
        
        Returns:
            Single message with all symbol-specific channels
        """
        if not symbols:
            return []
        
        method = "SUBSCRIPTION" if action == SubscriptionAction.SUBSCRIBE else "UNSUBSCRIPTION"
        
        # Build params with symbol-specific channels
        params = []
        messages = []
        for symbol in symbols:
            try:
                exchange_symbol = self.symbol_mapper.to_pair(symbol)
                params= [
                    f"spot@public.aggre.depth.v3.api.pb@10ms@{exchange_symbol}",
                    f"spot@public.aggre.deals.v3.api.pb@10ms@{exchange_symbol}",
                    f"spot@public.aggre.bookTicker.v3.api.pb@100ms@{exchange_symbol}"
                ]
                
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