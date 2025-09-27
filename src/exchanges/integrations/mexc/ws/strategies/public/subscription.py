"""
MEXC Public WebSocket Subscription Strategy V3

Direct message-based subscription strategy for MEXC public WebSocket.
Creates complete message objects in MEXC-specific format.

Message Format:
{
    "method": "SUBSCRIPTION",
    "params": [
        "spot@public.aggre.bookTicker.v3.api.pb@100ms@BTCUSDT"
    ]
}
"""

from typing import List, Dict, Any, Optional, Set

from infrastructure.networking.websocket.strategies.subscription import SubscriptionStrategy
from infrastructure.networking.websocket.structs import SubscriptionAction, PublicWebsocketChannelType
from exchanges.structs.common import Symbol
# BaseExchangeMapper dependency removed - using direct utility functions
from exchanges.consts import DEFAULT_PUBLIC_WEBSOCKET_CHANNELS

# HFT Logger Integration
from infrastructure.logging import get_strategy_logger, HFTLoggerInterface


class MexcPublicSubscriptionStrategy(SubscriptionStrategy):
    """
    MEXC public WebSocket subscription strategy V3.
    
    Creates complete MEXC-format subscription messages with symbols embedded in params.
    Format: "spot@public.aggre.bookTicker.v3.api.pb@100ms@BTCUSDT"
    """
    
    def __init__(self, logger: Optional[HFTLoggerInterface] = None):
        super().__init__(logger)
        
        # Use injected logger or create strategy-specific logger
        if logger is None:
            tags = ['mexc', 'public', 'ws', 'subscription']
            logger = get_strategy_logger('ws.subscription.mexc.public', tags)
        
        self.logger = logger
        
        # Track active subscriptions for reconnection
        self._active_symbols: Set[Symbol] = set()
        
        # Log initialization (move to DEBUG per logging spec)
        if self.logger:
            self.logger.debug("MexcPublicSubscriptionStrategy initialized",
                             exchange="mexc",
                             api_type="public")
            
            # Track component initialization
            self.logger.metric("mexc_public_subscription_strategies_initialized", 1,
                              tags={"exchange": "mexc", "api_type": "public"})

    async def create_subscription_messages(self, action: SubscriptionAction,
                                           symbols: List[Symbol],
                                           channels: List[PublicWebsocketChannelType] = DEFAULT_PUBLIC_WEBSOCKET_CHANNELS) -> List[Dict[str, Any]]:
        """
        Create MEXC public subscription messages.
        
        Symbol included in params: "spot@public.aggre.bookTicker.v3.api.pb@100ms@BTCUSDT"
        
        Args:
            action: SUBSCRIBE or UNSUBSCRIBE
            symbols: Symbols to subscribe/unsubscribe to/from
            channels: Channel types to subscribe/unsubscribe to/from
        
        Returns:
            Single message with all symbol-specific channels
        """
        if not symbols:
            return []
        
        # Use direct utility functions
        from exchanges.integrations.mexc.utils import from_subscription_action, to_pair, get_spot_channel_name
        method = from_subscription_action(action)
        
        # Build params with symbol-specific channels
            
        messages = []
        for symbol in symbols:
            try:
                # {'code': 0, 'id': 0,
                #  'msg': 'Not Subscribed successfully! '
                #         '[spot@public.increase.depth.v3.api@BTCUSDT,'
                #         'spot@public.aggre.deals.v3.api.pb@BTCUSDT,'
                #         'spot@public.aggre.bookTicker.v3.api.pb@BTCUSDT].  Reason： Blocked! '}
                exchange_symbol = to_pair(symbol)
                params = []  # Reset params for each symbol
                if PublicWebsocketChannelType.BOOK_TICKER in channels:
                    channel_base = get_spot_channel_name(PublicWebsocketChannelType.BOOK_TICKER)
                    params.append(f"{channel_base}@10ms@{exchange_symbol}")

                if PublicWebsocketChannelType.ORDERBOOK in channels:
                    channel_base = get_spot_channel_name(PublicWebsocketChannelType.ORDERBOOK)
                    params.append(f"{channel_base}@10ms@{exchange_symbol}")

                if PublicWebsocketChannelType.TRADES in channels:
                    channel_base = get_spot_channel_name(PublicWebsocketChannelType.TRADES)
                    params.append(f"{channel_base}@10ms@{exchange_symbol}")

                if not len(params):
                    if self.logger:
                        self.logger.warning(f"No valid channels to subscribe for symbol {symbol}",
                                          symbol=str(symbol),
                                          exchange="mexc")
                    continue

                if self.logger:
                    self.logger.debug(f"Added channels for {symbol}: {exchange_symbol}",
                                    symbol=str(symbol),
                                    exchange_symbol=exchange_symbol,
                                    exchange="mexc")

                message = {
                    "method": method,
                    "params": params
                }
                messages.append(message)
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Failed to convert symbol {symbol}: {e}",
                                    symbol=str(symbol),
                                    error=str(e),
                                    exchange="mexc")
                continue
        

        if self.logger:
            self.logger.debug(f"Created {method} {len(messages)} messages",
                            method=method,
                            message_count=len(messages),
                            exchange="mexc")
            
            self.logger.metric("mexc_public_subscription_messages_created", len(messages),
                              tags={"exchange": "mexc", "method": method, "api_type": "public"})
        
        return messages