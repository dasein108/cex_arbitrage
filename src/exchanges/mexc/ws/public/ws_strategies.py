import logging
from typing import Any, List, Dict, Optional

import msgspec

from config import ExchangeEnum
from core.cex.services import get_symbol_mapper

from core.cex.websocket import ConnectionStrategy, ConnectionContext, SubscriptionStrategy, SubscriptionAction, \
    SubscriptionContext
from structs.config import ExchangeConfig
from structs.exchange import Symbol


class MexcPublicConnectionStrategy(ConnectionStrategy):
    """MEXC public WebSocket connection strategy."""

    def __init__(self, config: ExchangeConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def create_connection_context(self) -> ConnectionContext:
        """Create MEXC public WebSocket connection context."""
        # Use the correct MEXC WebSocket URL from documentation
        websocket_url = self.config.websocket_url
        return ConnectionContext(
            url=websocket_url,
            headers={},
            auth_required=False,
            ping_interval=30,
            ping_timeout=10,
            max_reconnect_attempts=10,
            reconnect_delay=1.0
        )

    async def authenticate(self, websocket: Any) -> bool:
        """Public WebSocket requires no authentication."""
        return True

    async def handle_keep_alive(self, websocket: Any) -> None:
        """Handle MEXC keep-alive (ping/pong)."""
        # MEXC handles keep-alive automatically
        pass

    def should_reconnect(self, error: Exception) -> bool:
        """Determine if reconnection should be attempted."""
        # Reconnect on most errors except authentication failures
        return not isinstance(error, (PermissionError, ValueError))

    async def cleanup(self) -> None:
        """Clean up resources - no specific cleanup needed for public WebSocket."""
        pass


class MexcPublicSubscriptionStrategy(SubscriptionStrategy):
    """MEXC public WebSocket subscription strategy."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.symbol_mapper = get_symbol_mapper(ExchangeEnum.MEXC)

    def create_subscription_messages(
        self,
        symbols: List[Symbol],
        action: SubscriptionAction
    ) -> List[str]:
        """Create MEXC subscription messages using correct format from documentation."""
        messages = []

        for symbol in symbols:
            symbol_str = self.symbol_mapper.symbol_to_pair(symbol).upper()

            # MEXC WebSocket subscription format from documentation
            # Format: spot@public.aggre.depth.v3.api.pb@100ms@SYMBOL
            subscriptions = [
                f"spot@public.aggre.depth.v3.api.pb@10ms@{symbol_str}",    # Depth orderbook
                f"spot@public.aggre.deals.v3.api.pb@10ms@{symbol_str}"     # Trade deals
            ]

            for sub in subscriptions:
                message = {
                    "method": "SUBSCRIPTION" if action == SubscriptionAction.SUBSCRIBE else "UNSUBSCRIPTION",
                    "params": [sub]
                }
                messages.append(msgspec.json.encode(message).decode())

        return messages

    def get_subscription_context(self, symbol: Symbol) -> SubscriptionContext:
        """Get subscription context for a symbol."""
        symbol_str = self.symbol_mapper.symbol_to_pair(symbol).upper()

        return SubscriptionContext(
            symbol=symbol,
            channels=[
                f"spot@public.aggre.depth.v3.api.pb@100ms@{symbol_str}",
                f"spot@public.aggre.deals.v3.api.pb@100ms@{symbol_str}"
            ],
            parameters={"symbol": symbol_str, "update_frequency": "100ms"}
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
