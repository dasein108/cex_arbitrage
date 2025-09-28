"""
Gate.io Public WebSocket Subscription Strategy V3

Direct message-based subscription strategy for Gate.io public WebSocket.
Creates complete message objects in Gate.io-specific format.

Message Format:
{
    "time": 1234567890,
    "channel": "spot.orders_v2",
    "event": "subscribe",
    "payload": ["BTC_USDT"]
}
"""

import time
from typing import List, Dict, Any, Optional, Set

from infrastructure.networking.websocket.strategies.subscription import SubscriptionStrategy
from infrastructure.networking.websocket.structs import SubscriptionAction, PublicWebsocketChannelType
from exchanges.structs.common import Symbol
# BaseExchangeMapper dependency removed - using direct utility functions
from exchanges.consts import DEFAULT_PUBLIC_WEBSOCKET_CHANNELS
from exchanges.integrations.gateio.utils import from_subscription_action, get_spot_channel_name, to_pair, to_symbol, \
    EventType

# HFT Logger Integration
from infrastructure.logging import get_strategy_logger, HFTLoggerInterface


class GateioPublicSubscriptionStrategy(SubscriptionStrategy):
    """
    Gate.io public WebSocket subscription strategy V3.
    
    Creates complete Gate.io-format subscription messages with time/channel/event/payload structure.
    Format: {"time": X, "channel": Y, "event": Z, "payload": ["BTC_USDT"]}
    """
    
    def __init__(self, logger: Optional[HFTLoggerInterface] = None):
        super().__init__(logger)
        
        # Use injected logger or create strategy-specific logger
        if logger is None:
            tags = ['gateio', 'spot', 'public', 'ws', 'subscription']
            logger = get_strategy_logger('ws.subscription.gateio.spot.public', tags)
        
        self.logger = logger
        
        # Track active subscriptions for reconnection
        self._active_symbols: Set[Symbol] = set()
        
        # Log initialization
        if self.logger:
            self.logger.debug("GateioPublicSubscriptionStrategy initialized",
                             exchange="gateio",
                             api_type="spot_public")
            
            # Track component initialization
            self.logger.metric("gateio_spot_public_subscription_strategies_initialized", 1,
                              tags={"exchange": "gateio", "api_type": "spot_public"})
    
    async def create_subscription_messages(self, action: SubscriptionAction,
                                           symbols: List[Symbol],
                                           channels: List[PublicWebsocketChannelType] = DEFAULT_PUBLIC_WEBSOCKET_CHANNELS) -> List[Dict[str, Any]]:
        """
        Create Gate.io public subscription messages.
        
        Format: {"time": X, "channel": Y, "event": Z, "payload": ["BTC_USDT"]}
        Creates separate message for each channel type.
        
        Args:
            action: SUBSCRIBE or UNSUBSCRIBE
            symbols: Symbols to subscribe/unsubscribe to/from
            channels: Channel types to subscribe/unsubscribe to/from
        
        Returns:
            List of messages, one per channel type
        """
        if not symbols:
            return []
        
        current_time = int(time.time())
        # Use direct utility functions
        event = from_subscription_action(action)
        messages = []
        
        # Convert symbols to Gate.io format
        symbol_pairs = self._convert_symbols_to_exchange_format(symbols)
        if not symbol_pairs:
            return []
        
        # Create separate message for each channel type using Gate.io mapper
        i = 0
        for channel_type in channels:
            channel_name = get_spot_channel_name(channel_type)
            if not channel_name:
                continue

            message = {
                "time": current_time + i,  # Slightly different timestamps
                "channel": channel_name,
                "event": event,
                "payload": symbol_pairs.copy()
            }
            messages.append(message)
            i += 1
            
            if self.logger:
                self.logger.debug(f"Created Gate.io {event} message for {channel_name}: {symbol_pairs}",
                                exchange="gateio",
                                channel_name=channel_name,
                                event=event,
                                symbol_count=len(symbol_pairs))

        if PublicWebsocketChannelType.ORDERBOOK in channels:
            # Orderbook update is symbol specific
            orderbook_channel = get_spot_channel_name(PublicWebsocketChannelType.ORDERBOOK)
            for pair in symbol_pairs:
                message = {
                    "time": current_time + i,  # Slightly different timestamps
                    "channel": orderbook_channel,
                    "event": event,
                    "payload": [pair, "100ms", "5"]
                }
                i += 1
                messages.append(message)
        
        # Update active symbols tracking
        if action == SubscriptionAction.SUBSCRIBE:
            self._active_symbols.update(symbols)
        else:
            self._active_symbols.difference_update(symbols)
        
        if self.logger:
            self.logger.debug(f"Created {len(messages)} {event} messages for {len(symbols)} symbols",
                             exchange="gateio",
                             message_count=len(messages),
                             event=event,
                             symbol_count=len(symbols))
            
            self.logger.metric("gateio_spot_public_subscription_messages_created", len(messages),
                              tags={"exchange": "gateio", "event": event, "api_type": "spot_public"})
        
        return messages
    
    async def create_resubscription_messages(self) -> List[Dict[str, Any]]:
        """
        Create resubscription messages for Gate.io public after reconnection.
        
        Returns:
            List of subscription messages for all currently active symbols
        """
        if not self._active_symbols:
            if self.logger:
                self.logger.debug("No active symbols to resubscribe to",
                                 exchange="gateio",
                                 api_type="spot_public")
            return []
        
        if self.logger:
            self.logger.debug(f"Creating resubscription messages for {len(self._active_symbols)} symbols",
                             exchange="gateio",
                             active_symbol_count=len(self._active_symbols),
                             api_type="spot_public")
        return await self.create_subscription_messages(
            action=SubscriptionAction.SUBSCRIBE,
            symbols=list(self._active_symbols),
            channels=DEFAULT_PUBLIC_WEBSOCKET_CHANNELS
        )
    
    def get_active_symbols(self) -> Set[Symbol]:
        """Get currently active symbols."""
        return self._active_symbols.copy()
    
    def is_subscription_message(self, message: Dict[str, Any]) -> bool:
        """Check if message is a subscription-related message."""
        return message.get("event") in [EventType.SUBSCRIBE.value, EventType.UNSUBSCRIBE.value]
    
    def extract_channel_from_message(self, message: Dict[str, Any]) -> Optional[str]:
        """Extract channel name from Gate.io message."""
        return message.get("channel")
    
    def extract_symbol_from_message(self, message: Dict[str, Any]) -> Optional[Symbol]:
        """Extract symbol from Gate.io message."""
        
        # Try to get symbol from result data first
        result = message.get("result", {})
        if isinstance(result, dict):
            symbol_str = result.get("s")
            if symbol_str:
                try:
                    return to_symbol(symbol_str)
                except Exception:
                    pass
        
        # Fallback: try to extract from channel
        channel = message.get("channel", "")
        if "." in channel:
            parts = channel.split(".")
            if len(parts) > 2:
                symbol_str = parts[-1]
                try:
                    return to_symbol(symbol_str)
                except Exception:
                    pass
        
        return None
    
    async def get_subscription_status_for_symbols(self, symbols: List[Symbol]) -> Dict[Symbol, bool]:
        """
        Get subscription status for symbols.
        
        Args:
            symbols: List of symbols to check
            
        Returns:
            Dict mapping Symbol to subscription status (True if subscribed)
        """
        return {symbol: symbol in self._active_symbols for symbol in symbols}
    
    def get_supported_channels(self) -> List[PublicWebsocketChannelType]:
        """Get list of supported channel types."""
        return [
            PublicWebsocketChannelType.BOOK_TICKER,
            PublicWebsocketChannelType.TRADES,
            PublicWebsocketChannelType.ORDERBOOK
        ]

    async def create_single_symbol_subscription(self, action: SubscriptionAction,
                                                symbol: Symbol,
                                                channel_type: PublicWebsocketChannelType) -> Optional[Dict[str, Any]]:
        """
        Create subscription message for single symbol and channel.
        
        Args:
            action: SUBSCRIBE or UNSUBSCRIBE
            symbol: Symbol to subscribe/unsubscribe
            channel_type: Channel type
            
        Returns:
            Subscription message or None if not supported
        """
        channel_name = get_spot_channel_name(channel_type)
        if not channel_name:
            return None
        
        try:
            exchange_symbol = to_pair(symbol)
            event = from_subscription_action(action)
            
            message = {
                "time": int(time.time()),
                "channel": channel_name,
                "event": event,
                "payload": [exchange_symbol]
            }
            
            # Update tracking
            if action == SubscriptionAction.SUBSCRIBE:
                self._active_symbols.add(symbol)
            else:
                self._active_symbols.discard(symbol)
            
            return message
            
        except Exception:
            return None
    
    def _convert_symbols_to_exchange_format(self, symbols: List[Symbol]) -> List[str]:
        """Convert symbols to Gate.io exchange format."""
        try:
            from exchanges.integrations.gateio.utils import to_pair
            return [to_pair(symbol) for symbol in symbols]
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to convert symbols: {e}",
                                exchange="gateio",
                                error=str(e),
                                api_type="spot_public")
            return []

