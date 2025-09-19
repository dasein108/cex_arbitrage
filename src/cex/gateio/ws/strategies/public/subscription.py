"""
Gate.io Public WebSocket Subscription Strategy V3

Direct message-based subscription strategy for Gate.io public WebSocket.
Creates complete message objects in Gate.io-specific format.

Message Format:
{
    "time": 1234567890,
    "channel": "spot.orders_v2",
    "event": "subscribe",
    "payload": ["BTC_USDT"]
}
"""

import time
import logging
from typing import List, Dict, Any, Optional, Set

from core.transport.websocket.strategies.subscription import SubscriptionStrategy
from core.transport.websocket.structs import SubscriptionAction
from structs.common import Symbol
from core.cex.services import SymbolMapperInterface


class GateioPublicSubscriptionStrategy(SubscriptionStrategy):
    """
    Gate.io public WebSocket subscription strategy V3.
    
    Creates complete Gate.io-format subscription messages with time/channel/event/payload structure.
    Format: {"time": X, "channel": Y, "event": Z, "payload": ["BTC_USDT"]}
    """
    
    def __init__(self, mapper: Optional[SymbolMapperInterface] = None):
        super().__init__(mapper)  # Initialize parent with injected mapper
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Track active subscriptions for reconnection
        self._active_symbols: Set[Symbol] = set()
    
    async def create_subscription_messages(
        self,
        action: SubscriptionAction,
        symbols: List[Symbol]
    ) -> List[Dict[str, Any]]:
        """
        Create Gate.io public subscription messages.
        
        Format: {"time": X, "channel": Y, "event": Z, "payload": ["BTC_USDT"]}
        Creates separate message for each channel type.
        
        Args:
            action: SUBSCRIBE or UNSUBSCRIBE
            symbols: Symbols to subscribe/unsubscribe to/from
        
        Returns:
            List of messages, one per channel type
        """
        if not symbols:
            return []
        
        current_time = int(time.time())
        event = "subscribe" if action == SubscriptionAction.SUBSCRIBE else "unsubscribe"
        messages = []
        
        # Convert symbols to Gate.io format
        if not self.mapper:
            self.logger.error("No symbol mapper available for Gate.io subscription")
            return []
            
        try:
            symbol_pairs = []
            for symbol in symbols:
                exchange_symbol = self.mapper.to_pair(symbol)
                symbol_pairs.append(exchange_symbol)
                self.logger.debug(f"Converted {symbol} to {exchange_symbol}")
                
        except Exception as e:
            self.logger.error(f"Failed to convert symbols: {e}")
            return []
        
        if not symbol_pairs:
            self.logger.warning("No valid symbols to subscribe to")
            return []
        
        # Create separate message for each channel type
        channel_types = [
            "spot.book_ticker",
            "spot.trades"
        ]

        i = 0
        for channel in channel_types:
            message = {
                "time": current_time + i,  # Slightly different timestamps
                "channel": channel,
                "event": event,
                "payload": symbol_pairs.copy()
            }
            messages.append(message)
            i+=1
            
            self.logger.debug(f"Created {event} message for {channel} with {len(symbol_pairs)} symbols")

        # Orderbook update is symbol specific
        for pair in symbol_pairs:
            message = {
                "time": current_time + i,  # Slightly different timestamps
                "channel": "spot.order_book_update",
                "event": event,
                "payload": [pair, "20ms"]
            }
            i += 1
            messages.append(message)

        self.logger.info(f"Created {len(messages)} {event} messages for {len(symbols)} symbols")
        
        return messages

