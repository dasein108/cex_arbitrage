from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from core.transport.websocket.structs import SubscriptionAction, SubscriptionContext
from structs.exchange import Symbol


class SubscriptionStrategy(ABC):
    """
    Strategy for WebSocket subscription management.

    Handles subscription message formatting and channel management.
    HFT COMPLIANT: <1μs message formatting.
    """

    @abstractmethod
    def create_subscription_messages(
        self,
        symbols: List[Symbol],
        action: SubscriptionAction
    ) -> List[str]:
        """
        Create subscription/unsubscription messages.

        Args:
            symbols: Symbols to subscribe/unsubscribe
            action: Subscribe or unsubscribe action

        Returns:
            List of JSON-formatted subscription messages
        """
        pass

    @abstractmethod
    def get_subscription_context(self, symbol: Symbol) -> SubscriptionContext:
        """
        Get subscription configuration for a symbol.

        Args:
            symbol: Symbol to get context for

        Returns:
            SubscriptionContext with channels and parameters
        """
        pass

    @abstractmethod
    def parse_channel_from_message(self, message: Dict[str, Any]) -> Optional[str]:
        """
        Extract channel information from message.

        Args:
            message: Parsed message dictionary

        Returns:
            Channel name if found, None otherwise
        """
        pass

    @abstractmethod
    def should_resubscribe_on_reconnect(self) -> bool:
        """
        Determine if subscriptions should be renewed on reconnect.

        Returns:
            True if resubscription required
        """
        pass

    @abstractmethod
    def get_symbol_from_channel(self, channel: str) -> Optional[Symbol]:
        """
        Extract symbol from channel name.

        Args:
            channel: Channel name

        Returns:
            Symbol if parseable, None otherwise
        """
        pass
