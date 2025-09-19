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

from core.transport.websocket.strategies.subscription import SubscriptionStrategy
from core.transport.websocket.structs import SubscriptionAction
from structs.common import Symbol
from core.cex.services import SymbolMapperInterface


class MexcPrivateSubscriptionStrategy(SubscriptionStrategy):
    """
    MEXC private WebSocket subscription strategy V3.
    
    Creates complete MEXC-format subscription messages with fixed params (no symbols).
    Format: "spot@private.account.v3.api.pb"
    """
    
    def __init__(self, mapper: Optional[SymbolMapperInterface] = None):
        super().__init__(mapper)  # Initialize parent with injected mapper
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
    async def create_subscription_messages(
        self,
        action: SubscriptionAction,
        symbols: List[Symbol]  # Ignored for private channels
    ) -> List[Dict[str, Any]]:
        """
        Create MEXC private subscription messages.
        
        No symbol in params: "spot@private.account.v3.api.pb"
        Symbols parameter is ignored for private channels.
        
        Args:
            action: SUBSCRIBE or UNSUBSCRIBE
            symbols: Ignored for private channels
        
        Returns:
            Single message with fixed private channel params
        """
        method = "SUBSCRIPTION" if action == SubscriptionAction.SUBSCRIBE else "UNSUBSCRIPTION"
        
        # Fixed params for private channels (no symbols)
        params = [
            "spot@private.account.v3.api.pb",
            "spot@private.deals.v3.api.pb",
            "spot@private.orders.v3.api.pb"
        ]
        
        message = {
            "method": method,
            "params": params
        }
        
        self.logger.info(f"Created {method} message with {len(params)} private channels")
        
        return [message]

