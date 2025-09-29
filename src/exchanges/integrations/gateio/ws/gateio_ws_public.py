"""
Gate.io Public WebSocket Implementation

Clean implementation following the MEXC pattern with direct logic implementation.
Handles public WebSocket streams for market data including:
- Orderbook depth updates  
- Trade stream data
- Real-time market information

Features:
- Direct implementation (no strategy dependencies)
- HFT-optimized message processing
- Event-driven architecture with structured handlers
- Clean separation of concerns
- Gate.io-specific JSON message parsing

Gate.io Public WebSocket Specifications:
- Endpoint: wss://api.gateio.ws/ws/v4/
- Protocol: JSON-based message format
- Performance: <50ms latency with optimized processing

Architecture: Direct implementation following MEXC pattern
"""

import time
import msgspec
from typing import List, Optional, Callable, Awaitable, Set, Any, Dict, Union
from websockets import connect

from exchanges.integrations.gateio.services.spot_symbol_mapper import GateioSpotSymbol
from exchanges.structs.common import Symbol, Trade, OrderBook, BookTicker, OrderBookEntry, Side
from config.structs import ExchangeConfig
from exchanges.interfaces.ws import PublicBaseWebsocket
from infrastructure.networking.websocket.structs import SubscriptionAction, WebsocketChannelType
from utils import get_current_timestamp
from exchanges.integrations.gateio.utils import (
    from_subscription_action, 
    to_side
)
from common.orderbook_entry_pool import OrderBookEntryPool
from exchanges.integrations.gateio.ws.gateio_ws_common import GateioBaseWebsocket

_SPOT_PUBLIC_CHANNEL_MAPPING = {
    WebsocketChannelType.BOOK_TICKER: "spot.book_ticker",
    WebsocketChannelType.ORDERBOOK: "spot.order_book",
    WebsocketChannelType.EXECUTION: "spot.trades",
    WebsocketChannelType.HEARTBEAT: "spot.ping",
}

class GateioPublicSpotWebsocketBaseWebsocket(GateioBaseWebsocket, PublicBaseWebsocket):
    """Gate.io public WebSocket client inheriting from common base for shared Gate.io logic."""
    PING_CHANNEL = "spot.ping"
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.entry_pool = OrderBookEntryPool(initial_size=200, max_size=500)
        
        self.logger.info("Gate.io public WebSocket initialized")

    def _prepare_subscription_message(self, action: SubscriptionAction, symbol: Symbol, 
                                      channel: Union[WebsocketChannelType, List[WebsocketChannelType]], 
                                      **kwargs) -> Dict[str, Any]:
        """Prepare Gate.io subscription message format."""
        channels = channel if isinstance(channel, list) else [channel]
        current_time = int(time.time())
        event = from_subscription_action(action)
        
        # Convert symbol to Gate.io format
        exchange_symbol = GateioSpotSymbol.to_symbol(symbol)
        
        messages = []
        for ch in channels:

            channel_name = _SPOT_PUBLIC_CHANNEL_MAPPING.get(ch, None)

            if not channel_name:
                self.logger.warning(f"Unsupported public channel type: {ch}")
                continue
                
            message = {
                "time": current_time,
                "channel": channel_name,
                "event": event,
                "payload": [exchange_symbol]
            }
            
            # Special handling for orderbook subscription
            if ch == WebsocketChannelType.ORDERBOOK:
                message["payload"] = [exchange_symbol, "5", "100ms"]
                
            messages.append(message)
            
        if self.logger:
            self.logger.debug(f"Created Gate.io {event} messages for {symbol}: {len(messages)} messages",
                            symbol=str(symbol),
                            exchange_symbol=exchange_symbol,
                            exchange=self.exchange_name)
        
        return messages[0] if len(messages) == 1 else messages


    async def _handle_update_message(self, message: Dict[str, Any]) -> None:
        """Handle Gate.io update messages."""
        channel = message.get("channel", "")
        result_data = message.get("result", {})
        
        if not result_data:
            return
            
        # Route based on channel type
        if channel in ["spot.order_book_update", "spot.order_book", "spot.obu"]:
            await self._parse_orderbook_update(result_data, channel)
        elif channel in ["spot.trades", "spot.trades_v2"]:
            await self._parse_trades_update(result_data, channel)
        elif channel == "spot.book_ticker":
            await self._parse_book_ticker_update(result_data, channel)
        else:
            self.logger.debug(f"Received update for unknown Gate.io channel: {channel}")

    async def _parse_orderbook_update(self, data: Dict[str, Any], channel: str) -> None:
        """Parse Gate.io orderbook update."""
        try:
            # Extract symbol
            symbol_str = data.get('s') or data.get('currency_pair')
            if not symbol_str:
                self.logger.error("Missing symbol in Gate.io orderbook update")
                return
                
            symbol = GateioSpotSymbol.to_symbol(symbol_str)
            
            # Parse bids and asks
            bids = []
            asks = []
            
            if 'b' in data and data['b']:
                for bid_data in data['b']:
                    if len(bid_data) >= 2:
                        bids.append(self.entry_pool.get_entry(
                            price=float(bid_data[0]),
                            size=float(bid_data[1])
                        ))
            
            if 'a' in data and data['a']:
                for ask_data in data['a']:
                    if len(ask_data) >= 2:
                        asks.append(self.entry_pool.get_entry(
                            price=float(ask_data[0]),
                            size=float(ask_data[1])
                        ))
            
            orderbook = OrderBook(
                symbol=symbol,
                bids=bids,
                asks=asks,
                timestamp=data.get('t', get_current_timestamp()),
                last_update_id=data.get('u', None)
            )
            
            await self.handle_orderbook(orderbook)
            
        except Exception as e:
            self.logger.error(f"Error parsing Gate.io orderbook update: {e}")

    async def _parse_trades_update(self, data: Any, channel: str) -> None:
        """Parse Gate.io trades update."""
        try:
            # Handle both single trade and list of trades
            trade_list = data if isinstance(data, list) else [data]
            
            for trade_data in trade_list:
                if not isinstance(trade_data, dict):
                    continue
                    
                # Extract symbol
                symbol_str = trade_data.get('currency_pair') or trade_data.get('s')
                if not symbol_str:
                    continue
                    
                symbol = GateioSpotSymbol.to_symbol(symbol_str)
                
                # Parse trade data
                create_time = trade_data.get('create_time', 0)
                timestamp = int(create_time * 1000) if create_time else get_current_timestamp()
                
                trade = Trade(
                    symbol=symbol,
                    price=float(trade_data.get('price', '0')),
                    quantity=float(trade_data.get('amount', '0')),
                    timestamp=timestamp,
                    side=to_side(trade_data.get('side', 'buy')),
                    trade_id=str(trade_data.get('id', ''))
                )
                
                await self.handle_trade(trade)
                
        except Exception as e:
            self.logger.error(f"Error parsing Gate.io trades update: {e}")

    async def _parse_book_ticker_update(self, data: Dict[str, Any], channel: str) -> None:
        """Parse Gate.io book ticker update."""
        try:
            # Extract symbol
            symbol_str = data.get('s') or data.get('currency_pair')
            if not symbol_str:
                self.logger.error("Missing symbol in Gate.io book ticker update")
                return
                
            symbol = GateioSpotSymbol.to_symbol(symbol_str)
            
            book_ticker = BookTicker(
                symbol=symbol,
                bid_price=float(data.get('b', '0')),
                bid_quantity=float(data.get('B', '0')),
                ask_price=float(data.get('a', '0')),
                ask_quantity=float(data.get('A', '0')),
                timestamp=int(data.get('t', get_current_timestamp())),
                update_id=data.get('u', 0)
            )
            
            await self.handle_book_ticker(book_ticker)
            
        except Exception as e:
            self.logger.error(f"Error parsing Gate.io book ticker update: {e}")