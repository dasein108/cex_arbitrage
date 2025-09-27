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
from typing import List, Dict, Any, Optional

from infrastructure.networking.websocket.strategies.subscription import SubscriptionStrategy
from infrastructure.networking.websocket.structs import SubscriptionAction
from exchanges.structs.common import Symbol
# BaseExchangeMapper dependency removed - using direct utility functions

# HFT Logger Integration
from infrastructure.logging import get_strategy_logger, HFTLoggerInterface


class GateioPrivateSubscriptionStrategy(SubscriptionStrategy):
    """
    Gate.io private WebSocket subscription strategy V3.
    
    Creates complete Gate.io-format subscription messages with time/channel/event/payload structure.
    Format: {"time": X, "channel": Y, "event": Z, "payload": ["!all"]}
    """

    def __init__(self, logger: Optional[HFTLoggerInterface] = None):
        super().__init__(logger)
        
        # Use injected logger or create strategy-specific logger
        if logger is None:
            tags = ['gateio', 'spot', 'private', 'ws', 'subscription']
            logger = get_strategy_logger('ws.subscription.gateio.spot.private', tags)
        
        self.logger = logger
        
        # Log initialization
        if self.logger:
            self.logger.debug("GateioPrivateSubscriptionStrategy initialized",
                            exchange="gateio",
                            api_type="spot_private")
            
            # Track component initialization
            self.logger.metric("gateio_spot_private_subscription_strategies_initialized", 1,
                              tags={"exchange": "gateio", "api_type": "spot_private"})

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
        # Use direct utility functions
        from exchanges.integrations.gateio.utils import from_subscription_action, get_spot_private_channel_name, to_pair
        event = from_subscription_action(action)
        messages = []

        # Private channel definitions using centralized mappings
        from infrastructure.networking.websocket.structs import PrivateWebsocketChannelType
        private_channels = [
            {
                "channel": get_spot_private_channel_name(PrivateWebsocketChannelType.ORDER),
                "payload": ["!all"]  # Subscribe to all order updates
            },
            {
                "channel": get_spot_private_channel_name(PrivateWebsocketChannelType.TRADE),
                "payload": ["!all"]  # Subscribe to all trade updates
            },
            {
                "channel": get_spot_private_channel_name(PrivateWebsocketChannelType.BALANCE),
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

            if self.logger:
                self.logger.debug(f"Created {event} message for {channel_config['channel']}",
                                exchange="gateio",
                                channel=channel_config['channel'],
                                event=event,
                                api_type="spot_private")

        if self.logger:
            self.logger.debug(f"Created {len(messages)} private {event} messages",
                            exchange="gateio",
                            message_count=len(messages),
                            event=event,
                            api_type="spot_private")
            
            self.logger.metric("gateio_spot_private_subscription_messages_created", len(messages),
                              tags={"exchange": "gateio", "event": event, "api_type": "spot_private"})

        return messages
    
    def _convert_symbols_to_exchange_format(self, symbols: List[Symbol]) -> List[str]:
        """Convert symbols to Gate.io private exchange format."""
        try:
            return [to_pair(symbol) for symbol in symbols]
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to convert private symbols: {e}",
                                exchange="gateio",
                                error=str(e),
                                api_type="spot_private")
            return []
