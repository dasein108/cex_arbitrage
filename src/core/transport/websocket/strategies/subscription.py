from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from core.transport.websocket.structs import SubscriptionAction
from structs.common import Symbol


class SubscriptionStrategy(ABC):
    """
    Strategy for WebSocket subscription management.
    
    Direct message-based subscription strategy that creates complete WebSocket messages.
    Takes symbols only, generates exchange-specific messages internally.
    
    HFT COMPLIANT: <1μs message formatting.
    """

    @abstractmethod
    async def create_subscription_messages(
        self,
        action: SubscriptionAction,
        symbols: List[Symbol]
    ) -> List[Dict[str, Any]]:
        """
        Create complete WebSocket subscription/unsubscription messages.
        
        Args:
            action: SUBSCRIBE or UNSUBSCRIBE
            symbols: Symbols to subscribe/unsubscribe to/from
        
        Returns:
            List of complete message dictionaries ready for WebSocket sending
        """
        pass
