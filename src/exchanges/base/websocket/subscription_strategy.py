"""
WebSocket Subscription Strategy Base Class - Refactored

Clean, flexible subscription strategy interface that allows exchange-specific
message formats without assumptions.

HFT COMPLIANCE: Strategy pattern for exchange-specific optimizations.
"""

from abc import ABC, abstractmethod
from typing import List, Any, Set
from enum import IntEnum


class SubscriptionAction(IntEnum):
    """Subscription action types."""
    SUBSCRIBE = 1
    UNSUBSCRIBE = 2
    MODIFY = 3


class SubscriptionStrategy(ABC):
    """
    Abstract base class for WebSocket subscription strategies.
    
    Responsible for:
    - Creating exchange-specific subscription messages
    - Tracking active subscriptions (if needed)
    - Handling subscription restoration after reconnection
    
    NOT responsible for:
    - Sending messages (handled by manager)
    - Connection management (handled by manager)
    """
    
    def __init__(self, mapper=None):
        """Initialize subscription strategy."""
        # Subclasses can maintain their own subscription state if needed
        self._active_subscriptions: Set[str] = set()
        self.mapper = mapper
    
    @abstractmethod
    async def create_subscription_messages(
        self,
        action: SubscriptionAction,
        **context
    ) -> List[Any]:
        """
        Create subscription messages in exchange-specific format.
        
        This is the main method that replaces the old channel-based approach.
        Each exchange can format messages however they need.
        
        Args:
            action: Subscribe, unsubscribe, or modify
            **context: Subscription context
                - symbols: List[Symbol] for public subscriptions
                - channels: List[str] for specific channels
                - Other exchange-specific parameters
        
        Returns:
            List of messages ready to send (can be dicts, strings, or bytes)
        
        Example for Gate.io:
            [
                {
                    "time": 123456789,
                    "channel": "spot.order_book_update",
                    "event": "subscribe",
                    "payload": ["BTC_USDT", "ETH_USDT", "100ms"]
                }
            ]
        
        Example for MEXC:
            [
                binary_protobuf_message_1,
                binary_protobuf_message_2
            ]
        """
        pass
    
    async def track_subscriptions(
        self,
        action: SubscriptionAction,
        **context
    ) -> None:
        """
        Track subscription state for restoration.
        
        Called after messages are sent to update internal state.
        
        Args:
            action: What action was performed
            **context: Same context as create_subscription_messages
        """
        # Default implementation - subclasses can override
        if action == SubscriptionAction.SUBSCRIBE:
            # Track what we subscribed to (implementation-specific)
            pass
        elif action == SubscriptionAction.UNSUBSCRIBE:
            # Track what we unsubscribed from
            pass

    
    def should_resubscribe_on_reconnect(self) -> bool:
        """
        Whether to restore subscriptions after reconnection.
        
        Returns:
            True if subscriptions should be restored (default: True)
        """
        return True
    
    # Optional helper methods for specific use cases
    
    def get_active_subscriptions(self) -> Set[str]:
        """
        Get current active subscriptions.
        
        Returns:
            Set of active subscription identifiers
        """
        return self._active_subscriptions.copy()
    
    def clear_subscriptions(self) -> None:
        """Clear all tracked subscriptions."""
        self._active_subscriptions.clear()