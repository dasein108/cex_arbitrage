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

from typing import List, Dict, Any, Optional

from infrastructure.networking.websocket.strategies.subscription import SubscriptionStrategy
from infrastructure.networking.websocket.structs import SubscriptionAction
# BaseExchangeMapper dependency removed - using direct utility functions

# HFT Logger Integration
from infrastructure.logging import get_strategy_logger, HFTLoggerInterface


class MexcPrivateSubscriptionStrategy(SubscriptionStrategy):
    """
    MEXC private WebSocket subscription strategy V3.
    
    Creates complete MEXC-format subscription messages with fixed params (no symbols).
    Format: "spot@private.account.v3.api.pb"
    """
    
    def __init__(self, logger: Optional[HFTLoggerInterface] = None):
        super().__init__(logger)
        
        # Use injected logger or create strategy-specific logger
        if logger is None:
            tags = ['mexc', 'private', 'ws', 'subscription']
            logger = get_strategy_logger('ws.subscription.mexc.private', tags)
        
        self.logger = logger
        
        # Log initialization
        if self.logger:
            self.logger.debug("MexcPrivateSubscriptionStrategy initialized",
                            exchange="mexc",
                            api_type="private")
            
            # Track component initialization
            self.logger.metric("mexc_private_subscription_strategies_initialized", 1,
                              tags={"exchange": "mexc", "api_type": "private"})
        
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
        # Use direct utility functions
        from exchanges.integrations.mexc.utils import from_subscription_action, get_spot_private_channel_name
        method = from_subscription_action(action)

        # Fixed params for private channels (no symbols)
        # Use MEXC mapper to get proper channel names and add .pb suffix for subscription
        from infrastructure.networking.websocket.structs import PrivateWebsocketChannelType
        
        params = [
            get_spot_private_channel_name(PrivateWebsocketChannelType.BALANCE) + ".pb",
            get_spot_private_channel_name(PrivateWebsocketChannelType.TRADE) + ".pb",
            get_spot_private_channel_name(PrivateWebsocketChannelType.ORDER) + ".pb"
        ]
        
        message = {
            "method": method,
            "params": params
        }
        
        if self.logger:
            self.logger.debug(f"Created {method} message with {len(params)} private channels",
                            method=method,
                            channel_count=len(params),
                            exchange="mexc")
            
            self.logger.metric("mexc_private_subscription_messages_created", 1,
                              tags={"exchange": "mexc", "method": method, "api_type": "private"})
        
        return [message]

