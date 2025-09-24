from abc import ABC, abstractmethod
from typing import List, Dict, Any

from infrastructure.networking.websocket.structs import SubscriptionAction
from exchanges.services import BaseExchangeMapper

class SubscriptionStrategy(ABC):
    """
    Strategy for WebSocket subscription management.
    
    Direct message-based subscription strategy that creates complete WebSocket messages.
    Takes symbols only, generates exchange-specific messages internally.
    
    HFT COMPLIANT: <1μs message formatting.
    """

    def __init__(self, mapper: BaseExchangeMapper):
        """Initialize with mandatory mapper.
        
        Args:
            mapper: Exchange mappings interface containing exchange mapper
        """
        self.mapper = mapper

    @abstractmethod
    async def create_subscription_messages(
        self,
        action: SubscriptionAction,
        *args,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Create complete WebSocket subscription/unsubscription messages.
        
        Args:
            action: SUBSCRIBE or UNSUBSCRIBE
            *args: Positional arguments (symbols, channels, etc.)
            **kwargs: Keyword arguments for flexible parameter passing
            
        Common patterns:
            - Public: action, symbols, channels
            - Private: action (with **kwargs)
        
        Returns:
            List of complete message dictionaries ready for WebSocket sending
        """
        pass
