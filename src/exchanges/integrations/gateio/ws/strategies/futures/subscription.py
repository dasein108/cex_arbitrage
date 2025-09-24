"""
Gate.io Futures WebSocket Subscription Strategy

Direct message-based subscription strategy for Gate.io futures WebSocket.
Creates complete message objects in Gate.io futures-specific format.

Message Format:
{
    "time": 1234567890,
    "channel": "futures.order_book",
    "event": "subscribe",
    "payload": ["BTC_USDT"]
}
"""

import time
import logging
from typing import List, Dict, Any, Optional, Set

from infrastructure.networking.websocket.strategies.subscription import SubscriptionStrategy
from infrastructure.networking.websocket.structs import SubscriptionAction, PublicWebsocketChannelType
from infrastructure.data_structures.common import Symbol
from exchanges.services import BaseExchangeMapper
from exchanges.consts import DEFAULT_PUBLIC_WEBSOCKET_CHANNELS
from exchanges.integrations.gateio.services.gateio_mappings import GateioMappings


class GateioFuturesSubscriptionStrategy(SubscriptionStrategy):
    """
    Gate.io futures WebSocket subscription strategy.
    
    Creates complete Gate.io futures-format subscription messages with time/channel/event/payload structure.
    Format: {"time": X, "channel": Y, "event": Z, "payload": ["BTC_USDT"]}
    """
    
    def __init__(self, mapper: BaseExchangeMapper):
        super().__init__(mapper)  # Initialize parent with mandatory mapper
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Track active subscriptions for reconnection
        self._active_symbols: Set[Symbol] = set()
    
    async def create_subscription_messages(self, action: SubscriptionAction,
                                           symbols: List[Symbol],
                                           channels: List[PublicWebsocketChannelType] = DEFAULT_PUBLIC_WEBSOCKET_CHANNELS) -> List[Dict[str, Any]]:
        """
        Create Gate.io futures subscription messages.
        
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
        event = self.mapper.from_subscription_action(action)
        messages = []
        
        # Convert symbols to Gate.io futures format
        if not self.mapper:
            self.logger.error("No symbol mapper available for Gate.io futures subscription")
            return []
            
        try:
            symbol_pairs = []
            for symbol in symbols:
                # For futures, we might need to handle contract symbols differently
                exchange_symbol = self.mapper.to_pair(symbol)
                symbol_pairs.append(exchange_symbol)
                self.logger.debug(f"Converted futures symbol {symbol} to {exchange_symbol}")
                
        except Exception as e:
            self.logger.error(f"Failed to convert futures symbols: {e}")
            return []
        
        if not symbol_pairs:
            self.logger.warning("No valid futures symbols to subscribe to")
            return []
        
        # Create separate message for each futures channel type
        channel_types = {
            "futures.tickers": PublicWebsocketChannelType.TICKER,  # Futures book ticker
            "futures.book_ticker": PublicWebsocketChannelType.BOOK_TICKER,  # Futures book ticker
            "futures.trades": PublicWebsocketChannelType.TRADES,        # Futures trades
            # "futures.order_book_update": WebsocketChannelType.ORDERBOOK, # Futures orderbook
        }

        i = 0
        for channel in channel_types.keys():
            if channel_types[channel] not in channels:
                continue

            message = {
                "time": current_time + i,  # Slightly different timestamps
                "channel": channel,
                "event": event,
                "payload": symbol_pairs
            }
            messages.append(message)
            i += 1

            self.logger.debug(f"Created Gate.io futures {event} message for {channel}: {symbol_pairs}")
        
        # Update active symbols tracking
        if action == SubscriptionAction.SUBSCRIBE:
            self._active_symbols.update(symbols)
        else:
            self._active_symbols.difference_update(symbols)
        
        return messages
    
    async def create_resubscription_messages(self) -> List[Dict[str, Any]]:
        """
        Create resubscription messages for Gate.io futures after reconnection.
        
        Returns:
            List of subscription messages for all currently active symbols
        """
        if not self._active_symbols:
            self.logger.info("No active futures symbols to resubscribe to")
            return []
        
        self.logger.info(f"Creating resubscription messages for {len(self._active_symbols)} futures symbols")
        return await self.create_subscription_messages(
            action=SubscriptionAction.SUBSCRIBE,
            symbols=list(self._active_symbols),
            channels=DEFAULT_PUBLIC_WEBSOCKET_CHANNELS
        )
    
    def get_active_symbols(self) -> Set[Symbol]:
        """Get currently active futures symbols."""
        return self._active_symbols.copy()
    
    def is_subscription_message(self, message: Dict[str, Any]) -> bool:
        """Check if message is a subscription-related message."""
        return message.get("event") in [GateioMappings.EventType.SUBSCRIBE.value, GateioMappings.EventType.UNSUBSCRIBE.value]
    
    def extract_channel_from_message(self, message: Dict[str, Any]) -> Optional[str]:
        """Extract channel name from Gate.io futures message."""
        return message.get("channel")
    
    def extract_symbol_from_message(self, message: Dict[str, Any]) -> Optional[Symbol]:
        """Extract symbol from Gate.io futures message."""
        if not self.mapper:
            return None
            
        try:
            # Try to get symbol from result data first
            result = message.get("result", {})
            if isinstance(result, dict):
                symbol_str = result.get("s")
                if symbol_str:
                    return self.mapper.to_symbol(symbol_str)
            
            # Fallback: try to extract from channel
            channel = message.get("channel", "")
            if "." in channel:
                parts = channel.split(".")
                if len(parts) > 2:
                    symbol_str = parts[-1]
                    return self.mapper.to_symbol(symbol_str)
            
            return None
        except Exception as e:
            self.logger.error(f"Failed to extract futures symbol from message: {e}")
            return None
    
    async def get_subscription_status_for_symbols(self, symbols: List[Symbol]) -> Dict[Symbol, bool]:
        """
        Get subscription status for futures symbols.
        
        Args:
            symbols: List of symbols to check
            
        Returns:
            Dict mapping Symbol to subscription status (True if subscribed)
        """
        return {symbol: symbol in self._active_symbols for symbol in symbols}
    
    def get_supported_channels(self) -> List[PublicWebsocketChannelType]:
        """Get list of supported futures channel types."""
        return [
            PublicWebsocketChannelType.BOOK_TICKER,
            PublicWebsocketChannelType.TRADES,
            PublicWebsocketChannelType.ORDERBOOK
        ]
    
    
    async def create_single_symbol_subscription(self, action: SubscriptionAction,
                                                symbol: Symbol,
                                                channel_type: PublicWebsocketChannelType) -> Optional[Dict[str, Any]]:
        """
        Create subscription message for single futures symbol and channel.
        
        Args:
            action: SUBSCRIBE or UNSUBSCRIBE
            symbol: Symbol to subscribe/unsubscribe
            channel_type: Channel type
            
        Returns:
            Subscription message or None if not supported
        """
        channel_name = self.mapper.get_futures_channel_name(channel_type)
        if not channel_name or not self.mapper:
            return None
        
        try:
            exchange_symbol = self.mapper.to_pair(symbol)
            event = self.mapper.from_subscription_action(action)
            
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
        """Convert symbols to Gate.io futures exchange format."""
        if not self.mapper:
            self.logger.error("No symbol mapper available for Gate.io futures subscription")
            return []
            
        try:
            return [self.mapper.to_pair(symbol) for symbol in symbols]
        except Exception as e:
            self.logger.error(f"Failed to convert futures symbols: {e}")
            return []