import logging
from typing import List, Dict, Any, Optional

import msgspec

from core.cex.services import SymbolMapperInterface
from core.cex.websocket import SubscriptionStrategy, SubscriptionAction, SubscriptionContext
from structs.common import Symbol


class GateioPublicSubscriptionStrategy(SubscriptionStrategy):
    """Gate.io public WebSocket subscription strategy."""

    def __init__(self, symbol_mapper: SymbolMapperInterface):
        super().__init__()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.symbol_mapper = symbol_mapper

    def _get_channels_for_symbol(self, symbol: Symbol) -> List[str]:
        """Generate channel list for a symbol (single source of truth).

        Gate.io WebSocket subscription format:
        - spot.order_book_update.{symbol}
        - spot.trades.{symbol}
        """
        symbol_str = self.symbol_mapper.to_pair(symbol).upper()

        return [
            f"spot.order_book_update.{symbol_str}",  # Orderbook updates
            f"spot.trades.{symbol_str}"  # Trade data
        ]

    def create_subscription_messages(
            self,
            action: SubscriptionAction,
            **kwargs
    ) -> List[str]:
        """Create Gate.io subscription messages using correct format."""
        messages = []
        
        # Extract symbols from kwargs for public exchange
        symbols = kwargs.get('symbols', [])

        for symbol in symbols:
            channels = self._get_channels_for_symbol(symbol)

            for channel in channels:
                message = {
                    "method": "SUBSCRIBE" if action == SubscriptionAction.SUBSCRIBE else "UNSUBSCRIBE",
                    "params": [channel],
                    "id": int(time.time())  # Gate.io uses id for request tracking
                }
                messages.append(msgspec.json.encode(message).decode())

        return messages

    def get_subscription_context(self, symbol: Symbol) -> SubscriptionContext:
        """Get subscription context for a symbol."""
        symbol_str = self.symbol_mapper.to_pair(symbol).upper()

        return SubscriptionContext(
            channels=self._get_channels_for_symbol(symbol),
            parameters={"symbol": symbol_str}
        )

    def parse_channel_from_message(self, message: Dict[str, Any]) -> Optional[str]:
        """Extract channel from Gate.io message."""
        return message.get('channel')  # Gate.io uses 'channel' field

    def should_resubscribe_on_reconnect(self) -> bool:
        """Gate.io requires resubscription after reconnection."""
        return True

    def get_symbol_from_channel(self, channel: str) -> Optional[Symbol]:
        """Extract symbol from Gate.io channel name."""
        try:
            # Channel format: spot.order_book_update.BTC_USDT or spot.trades.BTC_USDT
            parts = channel.split('.')
            if len(parts) >= 3:
                symbol_str = parts[2]  # Symbol is at index 2
                return self.symbol_mapper.to_symbol(symbol_str)
        except Exception:
            pass
        return None

    # UNIFIED CHANNEL GENERATION IMPLEMENTATION
    
    def generate_channels(self, **kwargs) -> List[str]:
        """Generate channel names based on parameters (unified method)."""
        symbols = kwargs.get('symbols', [])
        if not symbols:
            return []
        
        channels = []
        for symbol in symbols:
            channels.extend(self._get_channels_for_symbol(symbol))
        return channels
    
    def format_subscription_messages(self, subscription_data: Dict[str, Any]) -> List[str]:
        """Format channel-based subscription messages."""
        import time
        
        messages = []
        action = subscription_data.get('action', 'subscribe')
        channels = subscription_data.get('channels', [])
        
        method = "SUBSCRIBE" if action == 'subscribe' else "UNSUBSCRIBE"
        
        for channel in channels:
            message = {
                "method": method,
                "params": [channel],
                "id": int(time.time())
            }
            messages.append(msgspec.json.encode(message).decode())
        
        return messages
    
    def extract_symbol_from_channel(self, channel: str) -> Optional[Symbol]:
        """Extract symbol from channel name for message routing."""
        try:
            # Channel format: spot.order_book_update.BTC_USDT
            parts = channel.split('.')
            if len(parts) >= 3:
                symbol_str = parts[2]  # Symbol is at index 2
                return self.symbol_mapper.to_symbol(symbol_str)
        except Exception as e:
            self.logger.debug(f"Failed to extract symbol from channel {channel}: {e}")
        return None