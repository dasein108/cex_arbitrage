from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Set

from core.transport.websocket.structs import SubscriptionAction, SubscriptionContext
from structs.common import Symbol


class SubscriptionStrategy(ABC):
    """
    Strategy for WebSocket subscription management.

    Handles subscription message formatting and channel management.
    HFT COMPLIANT: <1μs message formatting.
    """

    @abstractmethod
    def create_subscription_messages(
        self,
        action: SubscriptionAction,
        **kwargs
    ) -> List[str]:
        """
        Create subscription/unsubscription messages.

        Args:
            action: Subscribe or unsubscribe action
            **kwargs: Subscription parameters:
                - symbols: List[Symbol] for public exchanges
                - (no params needed for private exchanges)

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

    # UNIFIED CHANNEL GENERATION INTERFACE
    
    @abstractmethod
    def generate_channels(self, **kwargs) -> List[str]:
        """
        Generate channel names based on subscription parameters.
        
        Unified method that handles both symbol-based (public) and fixed (private) channels.
        
        Args:
            **kwargs: Channel generation parameters:
                - For public: symbols=[Symbol, ...]
                - For private: (no parameters needed)
        
        Returns:
            List of channel names
            
        Example for MEXC Public:
            generate_channels(symbols=[Symbol(base=BTC, quote=USDT)])
            returns = [
                "spot@public.aggre.depth.v3.api.pb@10ms@BTCUSDT",
                "spot@public.aggre.deals.v3.api.pb@10ms@BTCUSDT"
            ]
            
        Example for MEXC Private:
            generate_channels()
            returns = [
                "spot@private.account.v3.api.pb",
                "spot@private.deals.v3.api.pb", 
                "spot@private.orders.v3.api.pb"
            ]
        """
        pass
    
    @abstractmethod
    def format_subscription_messages(self, subscription_data: Dict[str, Any]) -> List[str]:
        """
        Format channel-based subscription messages.
        
        Receives channels (not symbols) and formats them into WebSocket messages.
        This enables ws_manager to work with channels only.
        
        Args:
            subscription_data: Channel subscription data:
                {
                    'action': 'subscribe'|'unsubscribe',
                    'channels': [channel_names...]
                }
        
        Returns:
            List of JSON-formatted messages ready to send to WebSocket
        """
        pass
    
    @abstractmethod
    def extract_symbol_from_channel(self, channel: str) -> Optional[Symbol]:
        """
        Extract symbol from channel name for message routing.
        
        Enables message parser to determine which symbol a message belongs to
        based on the channel name.
        
        Args:
            channel: Channel name from WebSocket message
            
        Returns:
            Symbol if channel contains symbol info, None for private channels
            
        Example for MEXC:
            channel = "spot@public.aggre.depth.v3.api.pb@10ms@BTCUSDT"
            returns = Symbol(base=BTC, quote=USDT)
        """
        pass
