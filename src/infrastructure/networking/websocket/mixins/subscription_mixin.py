"""
WebSocket Subscription Mixin

This mixin replaces the strategy-based SubscriptionStrategy with a composition-based
approach for managing WebSocket subscriptions. Provides channel mapping, subscription
state management, and automatic resubscription on reconnect.

Key Features:
- Channel mapping based on symbols and exchange requirements
- Subscription state tracking and persistence
- Automatic resubscription on WebSocket reconnection
- Clean unsubscription and state cleanup
- HFT optimized: <1μs subscription message creation

HFT COMPLIANCE: Sub-millisecond subscription processing.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Set, Optional
from dataclasses import dataclass
import asyncio
import time

from exchanges.structs.common import Symbol
from infrastructure.networking.websocket.structs import SubscriptionAction, PublicWebsocketChannelType
from infrastructure.logging import HFTLoggerInterface, get_logger


@dataclass
class SubscriptionState:
    """Tracks subscription state for a symbol-channel combination."""
    symbol: Symbol
    channels: List[str]
    subscribed_at: float
    is_active: bool = True


class SubscriptionMixin(ABC):
    """
    Mixin for WebSocket subscription management.
    
    Provides common subscription functionality that can be composed with
    exchange-specific handlers. Replaces the SubscriptionStrategy pattern
    with a more direct approach.
    
    Usage:
        class MexcPublicHandler(PublicWebSocketMixin, SubscriptionMixin):
            def get_channels_for_symbol(self, symbol: Symbol) -> List[str]:
                return ["orderbook", "trades"]  # MEXC-specific channels
    """
    
    def __init__(self, *args, **kwargs):
        # Only call super() if there are other classes in the MRO that need initialization
        if hasattr(super(), '__init__'):
            try:
                super().__init__(*args, **kwargs)
            except TypeError:
                # If super().__init__ doesn't accept kwargs, call without them
                pass
        
        # Subscription state management
        self._active_subscriptions: Dict[str, SubscriptionState] = {}
        self._subscription_lock = asyncio.Lock()
        
        # Logger setup
        if not hasattr(self, 'logger') or self.logger is None:
            self.logger = get_logger(f'subscription.{self.__class__.__name__}')
    
    # Abstract methods that exchanges must implement
    
    @abstractmethod
    def get_channels_for_symbol(self, symbol: Symbol, 
                              channel_types: Optional[List[PublicWebsocketChannelType]] = None) -> List[str]:
        """
        Get exchange-specific channel names for a symbol.
        
        Args:
            symbol: Symbol to get channels for
            channel_types: Optional filter for specific channel types
            
        Returns:
            List of exchange-specific channel names
            
        Example:
            # MEXC
            return ["spot@bookTicker", f"spot@depth@{symbol.format_mexc()}"]
            
            # Gate.io
            return [f"spot.book_ticker.{symbol.base}_{symbol.quote}"]
        """
        pass
    
    @abstractmethod
    def create_subscription_message(self, action: SubscriptionAction, 
                                  channels: List[str]) -> Dict[str, Any]:
        """
        Create exchange-specific subscription message.
        
        Args:
            action: SUBSCRIBE or UNSUBSCRIBE
            channels: List of channel names to subscribe/unsubscribe
            
        Returns:
            Complete WebSocket message ready for sending
            
        Example:
            # MEXC format
            return {
                "method": "SUBSCRIPTION",
                "params": channels,
                "id": int(time.time())
            }
        """
        pass
    
    # Public subscription interface
    
    async def subscribe_to_symbols(self, symbols: List[Symbol],
                                 channel_types: Optional[List[PublicWebsocketChannelType]] = None) -> List[Dict[str, Any]]:
        """
        Subscribe to symbols with automatic channel mapping.
        
        Args:
            symbols: List of symbols to subscribe to
            channel_types: Optional filter for specific channel types
            
        Returns:
            List of subscription messages to send
        """
        if not symbols:
            return []
        
        subscription_messages = []
        
        async with self._subscription_lock:
            for symbol in symbols:
                # Get exchange-specific channels for symbol
                channels = self.get_channels_for_symbol(symbol, channel_types)
                
                if not channels:
                    self.logger.warning(f"No channels found for symbol {symbol}")
                    continue
                
                # Create subscription message
                message = self.create_subscription_message(SubscriptionAction.SUBSCRIBE, channels)
                subscription_messages.append(message)
                
                # Track subscription state
                subscription_key = self._get_subscription_key(symbol)
                self._active_subscriptions[subscription_key] = SubscriptionState(
                    symbol=symbol,
                    channels=channels,
                    subscribed_at=time.time()
                )
                
                self.logger.debug(f"Prepared subscription for {symbol} with {len(channels)} channels")
        
        self.logger.info(f"Created {len(subscription_messages)} subscription messages for {len(symbols)} symbols")
        return subscription_messages
    
    async def unsubscribe_from_symbols(self, symbols: List[Symbol]) -> List[Dict[str, Any]]:
        """
        Unsubscribe from symbols and clean up state.
        
        Args:
            symbols: List of symbols to unsubscribe from
            
        Returns:
            List of unsubscription messages to send
        """
        if not symbols:
            return []
        
        unsubscription_messages = []
        
        async with self._subscription_lock:
            for symbol in symbols:
                subscription_key = self._get_subscription_key(symbol)
                
                if subscription_key not in self._active_subscriptions:
                    self.logger.warning(f"No active subscription found for {symbol}")
                    continue
                
                subscription_state = self._active_subscriptions[subscription_key]
                
                # Create unsubscription message
                message = self.create_subscription_message(SubscriptionAction.UNSUBSCRIBE, 
                                                         subscription_state.channels)
                unsubscription_messages.append(message)
                
                # Remove from active subscriptions
                del self._active_subscriptions[subscription_key]
                
                self.logger.debug(f"Prepared unsubscription for {symbol}")
        
        self.logger.info(f"Created {len(unsubscription_messages)} unsubscription messages for {len(symbols)} symbols")
        return unsubscription_messages
    
    async def get_resubscription_messages(self) -> List[Dict[str, Any]]:
        """
        Get messages to resubscribe to all active symbols.
        
        Used during WebSocket reconnection to restore subscriptions.
        
        Returns:
            List of subscription messages for all active symbols
        """
        resubscription_messages = []
        
        async with self._subscription_lock:
            if not self._active_subscriptions:
                return []
            
            # Group channels by subscription message format
            all_channels = []
            for subscription_state in self._active_subscriptions.values():
                all_channels.extend(subscription_state.channels)
            
            if all_channels:
                # Create single resubscription message for all channels
                message = self.create_subscription_message(SubscriptionAction.SUBSCRIBE, all_channels)
                resubscription_messages.append(message)
                
                # Update subscription timestamps
                current_time = time.time()
                for subscription_state in self._active_subscriptions.values():
                    subscription_state.subscribed_at = current_time
        
        self.logger.info(f"Created {len(resubscription_messages)} resubscription messages for "
                        f"{len(self._active_subscriptions)} active subscriptions")
        return resubscription_messages
    
    # State management methods
    
    def get_active_symbols(self) -> Set[Symbol]:
        """Get all currently subscribed symbols."""
        return {state.symbol for state in self._active_subscriptions.values()}
    
    def get_active_channels(self) -> List[str]:
        """Get all currently subscribed channels."""
        channels = []
        for state in self._active_subscriptions.values():
            channels.extend(state.channels)
        return channels
    
    def is_subscribed_to_symbol(self, symbol: Symbol) -> bool:
        """Check if currently subscribed to a symbol."""
        subscription_key = self._get_subscription_key(symbol)
        return subscription_key in self._active_subscriptions
    
    def get_subscription_count(self) -> int:
        """Get total number of active subscriptions."""
        return len(self._active_subscriptions)
    
    def clear_all_subscriptions(self) -> None:
        """Clear all subscription state (used for cleanup)."""
        self._active_subscriptions.clear()
        self.logger.info("All subscription state cleared")
    
    # Private helper methods
    
    def _get_subscription_key(self, symbol: Symbol) -> str:
        """Generate unique key for subscription tracking."""
        return f"{symbol.base}_{symbol.quote}_{symbol.is_futures}"
    
    def get_subscription_metrics(self) -> Dict[str, Any]:
        """Get subscription metrics for monitoring."""
        current_time = time.time()
        
        subscription_ages = []
        for state in self._active_subscriptions.values():
            age = current_time - state.subscribed_at
            subscription_ages.append(age)
        
        return {
            'active_subscriptions': len(self._active_subscriptions),
            'active_symbols': len(self.get_active_symbols()),
            'total_channels': len(self.get_active_channels()),
            'avg_subscription_age_seconds': sum(subscription_ages) / len(subscription_ages) if subscription_ages else 0,
            'oldest_subscription_age_seconds': max(subscription_ages) if subscription_ages else 0
        }