"""
Gate.io Public Futures WebSocket Implementation

Clean implementation following the MEXC pattern with direct logic implementation.
Separate exchange implementation treating Gate.io futures as completely independent
from Gate.io spot. Uses dedicated configuration with its own futures endpoints.

Handles public futures WebSocket streams for market data including:
- Futures orderbook depth updates  
- Futures trade stream data
- Real-time futures market information
- Funding rates and mark prices

Features:
- Direct implementation (no strategy dependencies)
- Completely separate from Gate.io spot configuration
- HFT-optimized message processing for futures markets
- Event-driven architecture with structured handlers
- Clean separation from spot exchange operations
- Gate.io futures-specific JSON message parsing

Gate.io Public Futures WebSocket Specifications:
- Primary Endpoint: wss://fx-ws.gateio.ws/v4/ws/usdt/ (USDT perpetual futures)
- Secondary Endpoint: wss://fx-ws.gateio.ws/v4/ws/delivery/ (delivery futures)  
- Protocol: JSON-based message format
- Performance: <80ms latency target for futures operations

Architecture: Direct implementation following MEXC pattern
"""

import time
import msgspec
from typing import List, Optional, Any, Dict, Union
from websockets import connect

from exchanges.structs.common import Symbol, Trade, OrderBook, BookTicker, Ticker, Side, FuturesTicker
from config.structs import ExchangeConfig
from exchanges.interfaces.ws import PublicBaseWebsocket
from infrastructure.networking.websocket.structs import SubscriptionAction, WebsocketChannelType, PublicWebsocketChannelType
from utils import get_current_timestamp
from exchanges.integrations.gateio.utils import (
    from_subscription_action, 
)
from common.orderbook_entry_pool import OrderBookEntryPool
from exchanges.integrations.gateio.ws.gateio_ws_common import GateioBaseWebsocket
from exchanges.integrations.gateio.services.futures_symbol_mapper import GateioFuturesSymbol
_FUTURES_PUBLIC_CHANNEL_MAPPING = {
    WebsocketChannelType.BOOK_TICKER: "futures.book_ticker",
    WebsocketChannelType.ORDERBOOK: "futures.order_book",
    WebsocketChannelType.PUB_TRADE: "futures.trades",
    WebsocketChannelType.HEARTBEAT: "futures.ping",
    WebsocketChannelType.TICKER: "futures.tickers",
}

class GateioPublicFuturesWebsocket(GateioBaseWebsocket, PublicBaseWebsocket):
    """Gate.io public futures WebSocket client inheriting from common base for shared Gate.io logic."""
    PING_CHANNEL = "futures.ping"
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.entry_pool = OrderBookEntryPool(initial_size=200, max_size=500)
        
        self.logger.info("Gate.io public futures WebSocket initialized")

    def _prepare_subscription_message(self, action: SubscriptionAction, symbol: Symbol, 
                                      channel: Union[WebsocketChannelType, List[WebsocketChannelType]], 
                                      **kwargs) -> Dict[str, Any]:
        """Prepare Gate.io futures subscription message format."""
        channels = channel if isinstance(channel, list) else [channel]
        current_time = int(time.time())
        event = from_subscription_action(action)
        
        # Convert symbol to Gate.io futures format
        exchange_symbol = GateioFuturesSymbol.to_pair(symbol)
        
        messages = []
        for ch in channels:
            channel_name = _FUTURES_PUBLIC_CHANNEL_MAPPING.get(ch)
            if not channel_name:
                self.logger.error(f"Unsupported futures channel type: {ch}")
                continue
                
            message = {
                "time": current_time,
                "channel": channel_name,
                "event": event,
                "payload": [exchange_symbol]
            }
            
            # Special handling for different futures channels
            if ch == WebsocketChannelType.ORDERBOOK:
                message["payload"] = [exchange_symbol, "5", "10ms"]  # Level, frequency
            elif ch == WebsocketChannelType.EXECUTION:
                message["payload"] = [exchange_symbol, "10ms"]  # Symbol, frequency
                
            messages.append(message)
            
        if self.logger:
            self.logger.debug(f"Created Gate.io futures {event} messages for {symbol}: {len(messages)} messages",
                            symbol=str(symbol),
                            exchange_symbol=exchange_symbol,
                            exchange=self.exchange_name)
        
        return messages[0] if len(messages) == 1 else messages

    async def _handle_update_message(self, message: Dict[str, Any]) -> None:
        """Handle Gate.io futures update messages."""
        channel = message.get("channel", "")
        result_data = message.get("result", {})
        
        if not result_data:
            return
            
        # Route based on channel type
        if "order_book" in channel or "orderbook" in channel:
            await self._parse_futures_orderbook_update(result_data, channel)
        elif "trades" in channel:
            await self._parse_futures_trades_update(result_data, channel)
        elif "book_ticker" in channel:
            await self._parse_futures_book_ticker_update(result_data, channel)
        elif "tickers" in channel:
            await self._parse_futures_ticker_update(result_data, channel)
        # Futures-specific channels - log but don't process for now
        elif "funding_rate" in channel:
            self.logger.debug(f"Received Gate.io futures funding rate update for channel: {channel}")
        elif "mark_price" in channel:
            self.logger.debug(f"Received Gate.io futures mark price update for channel: {channel}")
        else:
            self.logger.debug(f"Received update for unknown Gate.io futures channel: {channel}")

    async def _parse_futures_orderbook_update(self, data: Dict[str, Any], channel: str) -> None:
        """Parse Gate.io futures orderbook update."""
        try:
            # Extract symbol
            symbol_str = data.get('s') or data.get('currency_pair') or data.get('contract')
            if not symbol_str:
                self.logger.error("Missing symbol in Gate.io futures orderbook update")
                return
                
            symbol = GateioFuturesSymbol.to_symbol(symbol_str)
            
            # Parse bids and asks - futures format uses {"p": price, "s": size}
            bids = []
            asks = []
            
            if 'b' in data and data['b']:
                for bid_data in data['b']:
                    if isinstance(bid_data, dict) and 'p' in bid_data and 's' in bid_data:
                        price = float(bid_data['p'])
                        size = float(bid_data['s'])
                        if size > 0:  # Only include non-zero sizes
                            bids.append(self.entry_pool.get_entry(price=price, size=size))
            
            if 'a' in data and data['a']:
                for ask_data in data['a']:
                    if isinstance(ask_data, dict) and 'p' in ask_data and 's' in ask_data:
                        price = float(ask_data['p'])
                        size = float(ask_data['s'])
                        if size > 0:  # Only include non-zero sizes
                            asks.append(self.entry_pool.get_entry(price=price, size=size))
            
            orderbook = OrderBook(
                symbol=symbol,
                bids=bids,
                asks=asks,
                timestamp=data.get('t', get_current_timestamp()),
                last_update_id=data.get('u', None)
            )
            
            await self._exec_bound_handler(PublicWebsocketChannelType.ORDERBOOK, orderbook)
            
        except Exception as e:
            self.logger.error(f"Error parsing Gate.io futures orderbook update: {e}")

    async def _parse_futures_trades_update(self, data: Any, channel: str) -> None:
        """Parse Gate.io futures trades update."""
        try:
            # Handle both single trade and list of trades
            trade_list = data if isinstance(data, list) else [data]
            
            for trade_data in trade_list:
                if not isinstance(trade_data, dict):
                    continue
                    
                # Extract symbol
                symbol_str = trade_data.get('contract') or trade_data.get('s')
                if not symbol_str:
                    continue
                    
                symbol = GateioFuturesSymbol.to_symbol(symbol_str)
                
                # Handle size field - negative means sell, positive means buy
                size = float(trade_data.get('size', '0'))
                quantity = abs(size)
                side = Side.SELL if size < 0 else Side.BUY
                
                # Use create_time_ms if available, otherwise create_time in seconds
                timestamp = trade_data.get('create_time_ms', 0)
                if not timestamp:
                    create_time = trade_data.get('create_time', 0)
                    timestamp = int(create_time * 1000) if create_time else get_current_timestamp()
                
                trade = Trade(
                    symbol=symbol,
                    price=float(trade_data.get('price', '0')),
                    quantity=quantity,
                    timestamp=int(timestamp),
                    side=side,
                    trade_id=str(trade_data.get('id', ''))
                )
                
                await self._exec_bound_handler(PublicWebsocketChannelType.PUB_TRADE, trade)
                
        except Exception as e:
            self.logger.error(f"Error parsing Gate.io futures trades update: {e}")

    async def _parse_futures_book_ticker_update(self, data: Dict[str, Any], channel: str) -> None:
        """Parse Gate.io futures book ticker update."""
        try:
            # Extract symbol
            symbol_str = data.get('s') or data.get('currency_pair') or data.get('contract')
            if not symbol_str:
                self.logger.error("Missing symbol in Gate.io futures book ticker update")
                return
                
            symbol = GateioFuturesSymbol.to_symbol(symbol_str)
            
            book_ticker = BookTicker(
                symbol=symbol,
                bid_price=float(data.get('b', '0')),
                bid_quantity=float(data.get('B', 0)),  # Futures uses number, not string
                ask_price=float(data.get('a', '0')),
                ask_quantity=float(data.get('A', 0)),  # Futures uses number, not string
                timestamp=int(data.get('t', get_current_timestamp())),
                update_id=data.get('u', 0)
            )
            
            await self._exec_bound_handler(PublicWebsocketChannelType.BOOK_TICKER, book_ticker)
            
        except Exception as e:
            self.logger.error(f"Error parsing Gate.io futures book ticker update: {e}")

    async def _parse_futures_ticker_update(self, data_list: List[Dict[str, Any]], channel: str) -> None:
        """Parse Gate.io futures ticker update."""
        try:
            for data in data_list:
                # Extract symbol
                symbol_str = data.get('s') or data.get('currency_pair') or data.get('contract')
                if not symbol_str:
                    self.logger.error("Missing symbol in Gate.io futures ticker update")
                    return

                symbol = GateioFuturesSymbol.to_symbol(symbol_str)

                # Create futures ticker from data
                ticker = FuturesTicker(
                    symbol=symbol,
                    price=float(data.get('last', '0')),
                    mark_price=float(data.get('mark_price', '0')),
                    index_price=float(data.get('index_price', '0')),
                    funding_rate=float(data.get('funding_rate', '0')),
                    funding_rate_indicative=float(data.get('funding_rate_indicative', '0'))
                )

                # Handle ticker via bound handler
                await self._exec_bound_handler(PublicWebsocketChannelType.TICKER, ticker)

        except Exception as e:
            self.logger.error(f"Error parsing Gate.io futures ticker update: {e}")