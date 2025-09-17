import logging
from typing import List, Dict, Any, Optional

import msgspec

from core.cex.websocket import SubscriptionStrategy, SubscriptionAction, SubscriptionContext
from structs.exchange import Symbol


class GateioPrivateSubscriptionStrategy(SubscriptionStrategy):
    """Gate.io private WebSocket subscription strategy."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def _get_private_channels(self) -> List[str]:
        """Get Gate.io private channels (single source of truth)."""
        return [
            "spot.balances",        # Account balance updates
            "spot.orders",          # Order status updates  
            "spot.user_trades"      # User trade execution updates
        ]

    def create_subscription_messages(
        self,
        action: SubscriptionAction,
        **kwargs
    ) -> List[str]:
        """Create Gate.io private subscription messages.

        Gate.io private WebSocket requires authentication before subscribing.
        """
        import time
        
        messages = []

        if action == SubscriptionAction.SUBSCRIBE:
            private_channels = self._get_private_channels()

            for channel in private_channels:
                subscription_message = {
                    "method": "SUBSCRIBE",
                    "params": [channel],
                    "id": int(time.time())
                }
                messages.append(msgspec.json.encode(subscription_message).decode())

            self.logger.info(f"Created subscription for {len(private_channels)} private channels")

        elif action == SubscriptionAction.UNSUBSCRIBE:
            private_channels = self._get_private_channels()

            for channel in private_channels:
                unsubscription_message = {
                    "method": "UNSUBSCRIBE", 
                    "params": [channel],
                    "id": int(time.time())
                }
                messages.append(msgspec.json.encode(unsubscription_message).decode())

            self.logger.info(f"Created unsubscription for {len(private_channels)} private channels")

        return messages

    def get_subscription_context(self, symbol: Symbol) -> SubscriptionContext:
        """Get private subscription context."""
        return SubscriptionContext(
            channels=self._get_private_channels(),
            parameters={}
        )

    def parse_channel_from_message(self, message: Dict[str, Any]) -> Optional[str]:
        """Extract channel from private message."""
        return message.get('channel')

    def should_resubscribe_on_reconnect(self) -> bool:
        """Private WebSocket requires resubscription."""
        return True

    def get_symbol_from_channel(self, channel: str) -> Optional[Symbol]:
        """Private channels don't typically contain symbols."""
        return None

    # UNIFIED CHANNEL GENERATION IMPLEMENTATION
    
    def generate_channels(self, **kwargs) -> List[str]:
        """Generate channel names based on parameters (unified method)."""
        return self._get_private_channels()
    
    def format_subscription_messages(self, subscription_data: Dict[str, Any]) -> List[str]:
        """Format channel-based subscription messages for private channels."""
        import time
        
        messages = []
        action = subscription_data.get('action', 'subscribe')
        channels = subscription_data.get('channels', [])
        
        if not channels:
            return []
        
        method = "SUBSCRIBE" if action == 'subscribe' else "UNSUBSCRIBE"
        
        for channel in channels:
            subscription_message = {
                "method": method,
                "params": [channel],
                "id": int(time.time())
            }
            messages.append(msgspec.json.encode(subscription_message).decode())
        
        action_word = "subscription" if action == 'subscribe' else "unsubscription"
        self.logger.debug(f"Created {action_word} for {len(channels)} private channels")
        
        return messages
    
    def extract_symbol_from_channel(self, channel: str) -> Optional[Symbol]:
        """Private channels don't contain symbols."""
        return None