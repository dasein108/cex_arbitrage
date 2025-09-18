"""
Gate.io Private WebSocket Subscription Strategy V3

Direct message-based subscription strategy for Gate.io private WebSocket.
Creates complete message objects in Gate.io-specific format.

Message Format:
{
    "time": 1234567890,
    "channel": "spot.usertrades_v2",
    "event": "subscribe",
    "payload": ["!all"]
}
"""

import time
import logging
from typing import List, Dict, Any, Optional, Set

from core.transport.websocket.strategies.subscription import SubscriptionStrategy
from core.transport.websocket.structs import SubscriptionAction
from structs.common import Symbol
from core.cex.services import SymbolMapperInterface


class GateioPrivateSubscriptionStrategy(SubscriptionStrategy):
    """
    Gate.io private WebSocket subscription strategy V3.
    
    Creates complete Gate.io-format subscription messages with time/channel/event/payload structure.
    Format: {"time": X, "channel": Y, "event": Z, "payload": ["!all"]}
    """

    def __init__(self, symbol_mapper: SymbolMapperInterface):
        self.symbol_mapper = symbol_mapper
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def create_subscription_messages(
            self,
            action: SubscriptionAction,
            symbols: List[Symbol]  # Ignored for private channels
    ) -> List[Dict[str, Any]]:
        """
        Create Gate.io private subscription messages.
        
        Format: {"time": X, "channel": Y, "event": Z, "payload": ["!all"]}
        Symbols parameter is ignored for private channels - uses "!all" pattern.
        
        Args:
            action: SUBSCRIBE or UNSUBSCRIBE
            symbols: Ignored for private channels
        
        Returns:
            List of messages, one per private channel type
        """
        event = "subscribe" if action == SubscriptionAction.SUBSCRIBE else "unsubscribe"
        messages = []

        # Private channel definitions
        private_channels = [
            {
                "channel": "spot.orders_v2",
                "payload": ["!all"]  # Subscribe to all order updates
            },
            {
                "channel": "spot.usertrades_v2",
                "payload": ["!all"]  # Subscribe to all trade updates
            },
            {
                "channel": "spot.balances",
            }
        ]

        for channel_config in private_channels:
            message = {
                "time": int(time.time()),  # Slightly different timestamps
                "channel": channel_config["channel"],
                "event": event,
            }

            if "payload" in channel_config:
                message["payload"] = channel_config["payload"]

            messages.append(message)

            self.logger.debug(f"Created {event} message for {channel_config['channel']}")

        self.logger.info(f"Created {len(messages)} private {event} messages")

        return messages
