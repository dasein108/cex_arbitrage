from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from core.transport.websocket.structs import SubscriptionAction, WebsocketChannelType
from structs.common import Symbol
from core.cex.services import SymbolMapperInterface

class SubscriptionStrategy(ABC):
    """
    Strategy for WebSocket subscription management.
    
    Direct message-based subscription strategy that creates complete WebSocket messages.
    Takes symbols only, generates exchange-specific messages internally.
    
    HFT COMPLIANT: <1μs message formatting.
    """

    def __init__(self, mapper: Optional[SymbolMapperInterface] = None):
        """Initialize with optional symbol mapper."""
        self.mapper = mapper
        pass

    @abstractmethod
    async def create_subscription_messages(
        self,
        action: SubscriptionAction,
        symbols: List[Symbol],
        channels: Optional[List[WebsocketChannelType]]
    ) -> List[Dict[str, Any]]:
        """
        Create complete WebSocket subscription/unsubscription messages.
        
        Args:
            action: SUBSCRIBE or UNSUBSCRIBE
            symbols: Symbols to subscribe/unsubscribe to/from
            channels: Channel types to subscribe/unsubscribe to/from
        
        Returns:
            List of complete message dictionaries ready for WebSocket sending
        """
        pass
