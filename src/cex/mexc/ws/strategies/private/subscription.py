import logging
from typing import List, Dict, Any, Optional

import msgspec

from core.cex.websocket import SubscriptionStrategy, SubscriptionAction, SubscriptionContext
from structs.exchange import Symbol


class MexcPrivateSubscriptionStrategy(SubscriptionStrategy):
    """MEXC private WebSocket subscription strategy."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def _get_private_channels(self) -> List[str]:
        """Get MEXC private channels (single source of truth).

        DRY Compliance: Centralized channel definition eliminates code duplication
        between create_subscription_messages() and get_subscription_context().
        """
        return [
            "spot@private.account.v3.api.pb",   # Account balance updates
            "spot@private.deals.v3.api.pb",     # Trade execution updates
            "spot@private.orders.v3.api.pb"     # Order status updates
        ]

    def create_subscription_messages(
        self,
        symbols: List[Symbol],
        action: SubscriptionAction
    ) -> List[str]:
        """Create MEXC private subscription messages.

        MEXC private WebSocket requires explicit subscription to private channels
        after authentication with listen key.
        """
        messages = []

        if action == SubscriptionAction.SUBSCRIBE:
            private_channels = self._get_private_channels()  # Single source of truth

            subscription_message = {
                "method": "SUBSCRIPTION",
                "params": private_channels
            }

            messages.append(msgspec.json.encode(subscription_message).decode())
            self.logger.info(f"Created subscription for {len(private_channels)} private channels")

        elif action == SubscriptionAction.UNSUBSCRIBE:
            private_channels = self._get_private_channels()  # Single source of truth

            unsubscription_message = {
                "method": "UNSUBSCRIPTION",
                "params": private_channels
            }

            messages.append(msgspec.json.encode(unsubscription_message).decode())
            self.logger.info(f"Created unsubscription for {len(private_channels)} private channels")

        return messages

    def get_subscription_context(self, symbol: Symbol) -> SubscriptionContext:
        """Get private subscription context."""
        return SubscriptionContext(
            channels=self._get_private_channels(),  # Single source of truth
            parameters={}
        )

    def parse_channel_from_message(self, message: Dict[str, Any]) -> Optional[str]:
        """Extract channel from private message."""
        return message.get('c')

    def should_resubscribe_on_reconnect(self) -> bool:
        """Private WebSocket requires resubscription."""
        return True

    def get_symbol_from_channel(self, channel: str) -> Optional[Symbol]:
        """Private channels don't typically contain symbols."""
        return None
