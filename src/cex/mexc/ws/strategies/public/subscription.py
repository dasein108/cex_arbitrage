import logging
from typing import List, Dict, Any, Optional

import msgspec

from core.cex.services import SymbolMapperInterface
from core.cex.websocket import SubscriptionStrategy, SubscriptionAction, SubscriptionContext
from structs.exchange import Symbol


class MexcPublicSubscriptionStrategy(SubscriptionStrategy):
    """MEXC public WebSocket subscription strategy."""

    def __init__(self, symbol_mapper: SymbolMapperInterface):
        super().__init__()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.symbol_mapper = symbol_mapper
    def _get_channels_for_symbol(self, symbol: Symbol) -> List[str]:
        """Generate channel list for a symbol (single source of truth).

        DRY Compliance: Centralized channel generation eliminates code duplication
        between create_subscription_messages() and get_subscription_context().
        """
        symbol_str = self.symbol_mapper.symbol_to_pair(symbol).upper()

        # MEXC WebSocket subscription format from documentation
        # Format: spot@public.aggre.depth.v3.api.pb@10ms@SYMBOL
        return [
            f"spot@public.aggre.depth.v3.api.pb@10ms@{symbol_str}",  # Depth orderbook
            f"spot@public.aggre.deals.v3.api.pb@10ms@{symbol_str}"  # Trade deals
        ]

    def create_subscription_messages(
            self,
            symbols: List[Symbol],
            action: SubscriptionAction
    ) -> List[str]:
        """Create MEXC subscription messages using correct format from documentation."""
        messages = []

        for symbol in symbols:
            channels = self._get_channels_for_symbol(symbol)  # Single source of truth

            for channel in channels:
                message = {
                    "method": "SUBSCRIPTION" if action == SubscriptionAction.SUBSCRIBE else "UNSUBSCRIPTION",
                    "params": [channel]
                }
                messages.append(msgspec.json.encode(message).decode())

        return messages

    def get_subscription_context(self, symbol: Symbol) -> SubscriptionContext:
        """Get subscription context for a symbol."""
        symbol_str = self.symbol_mapper.symbol_to_pair(symbol).upper()

        return SubscriptionContext(
            channels=self._get_channels_for_symbol(symbol),  # Single source of truth
            parameters={"symbol": symbol_str, "update_frequency": "10ms"}
        )

    def parse_channel_from_message(self, message: Dict[str, Any]) -> Optional[str]:
        """Extract channel from MEXC message."""
        return message.get('c')  # MEXC uses 'c' for channel

    def should_resubscribe_on_reconnect(self) -> bool:
        """MEXC requires resubscription after reconnection."""
        return True

    def get_symbol_from_channel(self, channel: str) -> Optional[Symbol]:
        """Extract symbol from MEXC channel name."""
        try:
            # Channel format: spot@public.aggre.depth.v3.api.pb@100ms@BTCUSDT
            parts = channel.split('@')
            if len(parts) >= 4:
                symbol_str = parts[3]  # Symbol is now at index 3
                return self.symbol_mapper.pair_to_symbol(symbol_str)
        except Exception:
            pass
        return None
