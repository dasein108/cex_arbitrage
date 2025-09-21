from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from core.transport.websocket.structs import SubscriptionAction, PublicWebsocketChannelType
from structs.common import Symbol

if TYPE_CHECKING:
    from core.exchanges.services.unified_mapper.exchange_mappings import ExchangeMappingsInterface

class SubscriptionStrategy(ABC):
    """
    Strategy for WebSocket subscription management.
    
    Direct message-based subscription strategy that creates complete WebSocket messages.
    Takes symbols only, generates exchange-specific messages internally.
    
    HFT COMPLIANT: <1μs message formatting.
    """

    def __init__(self, mapper: Optional["ExchangeMappingsInterface"] = None):
        """Initialize with optional mapper injection.
        
        Args:
            mapper: Exchange mappings interface containing symbol_mapper and channel name methods
        """
        self.mapper = mapper
        # Maintain backward compatibility with symbol_mapper property
        self.symbol_mapper = mapper._symbol_mapper if mapper else None

    @abstractmethod
    async def create_subscription_messages(
        self,
        action: SubscriptionAction,
        symbols: List[Symbol],
        channels: Optional[List[PublicWebsocketChannelType]]
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
