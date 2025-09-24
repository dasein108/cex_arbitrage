"""
MEXC Private WebSocket Subscription Strategy V3

Direct message-based subscription strategy for MEXC private WebSocket.
Creates complete message objects in MEXC-specific format.

Message Format:
{
    "method": "SUBSCRIPTION",
    "params": [
        "spot@private.account.v3.api.pb"
    ]
}
"""

import logging
from typing import List, Dict, Any, Optional

from infrastructure.networking.websocket.strategies.subscription import SubscriptionStrategy
from infrastructure.networking.websocket.structs import SubscriptionAction
from exchanges.services import BaseExchangeMapper
from exchanges.integrations.mexc.services.mexc_mappings import MexcUnifiedMappings


class MexcPrivateSubscriptionStrategy(SubscriptionStrategy):
    """
    MEXC private WebSocket subscription strategy V3.
    
    Creates complete MEXC-format subscription messages with fixed params (no symbols).
    Format: "spot@private.account.v3.api.pb"
    """
    
    def __init__(self, mapper: BaseExchangeMapper):
        super().__init__(mapper)  # Initialize parent with mandatory mapper
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
    async def create_subscription_messages(self, action: SubscriptionAction, **kwargs) -> List[Dict[str, Any]]:
        """
        Create MEXC private subscription messages.
        
        No symbol in params: "spot@private.account.v3.api.pb"
        Symbols parameter is ignored for private channels.
        
        Args:
            action: SUBSCRIBE or UNSUBSCRIBE

        Returns:
            Single message with fixed private channel params
        """
        method = self.mapper.from_subscription_action(action)

        # Fixed params for private channels (no symbols)
        # Use mapper to get proper channel names and add .pb suffix for subscription
        from infrastructure.networking.websocket.structs import PrivateWebsocketChannelType
        
        params = [
            self.mapper.get_spot_private_channel_name(PrivateWebsocketChannelType.BALANCE) + ".pb",
            self.mapper.get_spot_private_channel_name(PrivateWebsocketChannelType.TRADE) + ".pb",
            self.mapper.get_spot_private_channel_name(PrivateWebsocketChannelType.ORDER) + ".pb"
        ]
        
        message = {
            "method": method,
            "params": params
        }
        
        self.logger.info(f"Created {method} message with {len(params)} private channels")
        
        return [message]

