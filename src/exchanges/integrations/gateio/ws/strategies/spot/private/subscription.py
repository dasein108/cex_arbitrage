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
from typing import List, Dict, Any

from infrastructure.networking.websocket.strategies.subscription import SubscriptionStrategy
from infrastructure.networking.websocket.structs import SubscriptionAction
from exchanges.structs.common import Symbol
from exchanges.services import BaseExchangeMapper


class GateioPrivateSubscriptionStrategy(SubscriptionStrategy):
    """
    Gate.io private WebSocket subscription strategy V3.
    
    Creates complete Gate.io-format subscription messages with time/channel/event/payload structure.
    Format: {"time": X, "channel": Y, "event": Z, "payload": ["!all"]}
    """

    def __init__(self, mapper: BaseExchangeMapper):
        super().__init__(mapper)  # Initialize parent with mandatory mapper
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def create_subscription_messages(self, action: SubscriptionAction, **kwargs) -> List[Dict[str, Any]]:
        """
        Create Gate.io private subscription messages.
        
        Format: {"time": X, "channel": Y, "event": Z, "payload": ["!all"]}
        Symbols parameter is ignored for private channels - uses "!all" pattern.
        
        Args:
            action: SUBSCRIBE or UNSUBSCRIBE

        Returns:
            List of messages, one per private channel type
        """
        event = self.mapper.from_subscription_action(action)
        messages = []

        # Private channel definitions using centralized mappings
        from infrastructure.networking.websocket.structs import PrivateWebsocketChannelType
        private_channels = [
            {
                "channel": self.mapper.get_spot_private_channel_name(PrivateWebsocketChannelType.ORDER),
                "payload": ["!all"]  # Subscribe to all order updates
            },
            {
                "channel": self.mapper.get_spot_private_channel_name(PrivateWebsocketChannelType.TRADE),
                "payload": ["!all"]  # Subscribe to all trade updates
            },
            {
                "channel": self.mapper.get_spot_private_channel_name(PrivateWebsocketChannelType.BALANCE),
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
    
    def _convert_symbols_to_exchange_format(self, symbols: List[Symbol]) -> List[str]:
        """Convert symbols to Gate.io private exchange format."""
        if not self.mapper:
            self.logger.error("No symbol mapper available for Gate.io private subscription")
            return []
        
        try:
            return [self.mapper.to_pair(symbol) for symbol in symbols]
        except Exception as e:
            self.logger.error(f"Failed to convert private symbols: {e}")
            return []
