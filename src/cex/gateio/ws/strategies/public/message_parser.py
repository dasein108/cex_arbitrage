import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from core.cex.websocket import MessageParser, ParsedMessage
from core.cex.services import SymbolMapperInterface
from core.transport.websocket.structs import MessageType
from structs.common import Trade, OrderBookEntry, Symbol, Side, BookTicker


class GateioPublicMessageParser(MessageParser):
    """Gate.io public WebSocket message parser."""

    def __init__(self, symbol_mapper: SymbolMapperInterface):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.symbol_mapper = symbol_mapper

    async def parse_message(self, raw_message: str) -> Optional[ParsedMessage]:
        """Parse raw WebSocket message from Gate.io."""
        try:
            import msgspec
            message = msgspec.json.decode(raw_message)
            
            # Handle different message types based on Gate.io format
            if isinstance(message, dict):
                event = message.get("event")
                
                if event == "subscribe":
                    # Subscription confirmation/error
                    return await self._parse_subscription_response(message)
                elif event == "unsubscribe":
                    # Unsubscription confirmation
                    return ParsedMessage(
                        message_type=MessageType.SUBSCRIPTION_CONFIRM,
                        data={"action": "unsubscribe", "status": message.get("result", {}).get("status")},
                        raw_data=message
                    )
                elif event == "update":
                    # Data update message
                    return await self._parse_update_message(message)
                elif event in ["ping", "pong"]:
                    # Ping/pong messages
                    return ParsedMessage(
                        message_type=MessageType.HEARTBEAT,
                        raw_data=message
                    )
                else:
                    # Other message types or messages without event field
                    self.logger.debug(f"Unknown Gate.io message format: {message}")
                    return ParsedMessage(
                        message_type=MessageType.UNKNOWN,
                        raw_data=message
                    )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to parse Gate.io message: {e}")
            return None

    async def _parse_subscription_response(self, message: Dict[str, Any]) -> ParsedMessage:
        """Parse Gate.io subscription response."""
        # Get channel name from message
        channel = message.get("channel", "")
        
        # Check for errors first
        error = message.get("error")
        if error:
            error_code = error.get("code", "unknown")
            error_msg = error.get("message", "unknown error")
            self.logger.error(f"Gate.io subscription error {error_code}: {error_msg}")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                channel=channel,
                data={"error_code": error_code, "error_message": error_msg},
                raw_data=message
            )
        
        # Check result status
        result = message.get("result", {})
        status = result.get("status")
        
        if status == "success":
            self.logger.debug(f"Gate.io subscription successful for channel: {channel}")
            return ParsedMessage(
                message_type=MessageType.SUBSCRIPTION_CONFIRM,
                channel=channel,
                data={"action": "subscribe", "status": "success"},
                raw_data=message
            )
        elif status == "fail":
            self.logger.error(f"Gate.io subscription failed for channel: {channel}")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                channel=channel,
                data={"action": "subscribe", "status": "fail"},
                raw_data=message
            )
        else:
            self.logger.warning(f"Unknown Gate.io subscription status: {status}")
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                channel=channel,
                raw_data=message
            )

    async def _parse_update_message(self, message: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io update message."""
        # Gate.io update format: {"event": "update", "channel": "spot.book_ticker", "result": {...}}
        channel = message.get("channel", "")
        result_data = message.get("result", {})
        
        if not channel or not result_data:
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                raw_data=message
            )
        
        if "order_book_update" in channel:
            return await self._parse_orderbook_update(channel, result_data)
        elif "trades" in channel:
            return await self._parse_trades_update(channel, result_data)
        elif "book_ticker" in channel:
            return await self._parse_book_ticker_update(channel, result_data)
        else:
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                channel=channel,
                raw_data={"channel": channel, "data": result_data}
            )

    async def _parse_orderbook_update(self, channel: str, data: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io orderbook update."""
        try:
            # Get symbol from data field 's' (symbol)
            symbol_str = data.get('s', '')
            if not symbol_str:
                # Fallback: extract from channel if it has symbol suffix
                channel_parts = channel.split('.')
                if len(channel_parts) > 2:
                    symbol_str = channel_parts[-1]
                else:
                    self.logger.error(f"No symbol found in orderbook data: {data}")
                    return ParsedMessage(
                        message_type=MessageType.ERROR,
                        channel=channel,
                        raw_data={"error": "No symbol in orderbook data", "data": data}
                    )
            
            symbol = self.symbol_mapper.to_symbol(symbol_str)
            
            # Gate.io orderbook format:
            # {
            #   "t": timestamp,
            #   "s": symbol,
            #   "U": first_update_id,
            #   "u": last_update_id,
            #   "b": [["price", "amount"], ...],  # bids
            #   "a": [["price", "amount"], ...]   # asks
            # }
            
            bids = []
            asks = []
            
            # Parse bids
            for bid_data in data.get("b", []):
                if len(bid_data) >= 2:
                    price = float(bid_data[0])
                    size = float(bid_data[1])
                    bids.append(OrderBookEntry(price=price, size=size))
            
            # Parse asks
            for ask_data in data.get("a", []):
                if len(ask_data) >= 2:
                    price = float(ask_data[0])
                    size = float(ask_data[1])
                    asks.append(OrderBookEntry(price=price, size=size))
            
            # Create OrderBook object
            from structs.common import OrderBook
            orderbook = OrderBook(
                bids=bids,
                asks=asks,
                timestamp=data.get("t", 0),
                last_update_id=data.get("u")
            )
            
            return ParsedMessage(
                message_type=MessageType.ORDERBOOK,
                symbol=symbol,
                channel=channel,
                data=orderbook,
                raw_data=data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to parse orderbook update: {e}")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                channel=channel,
                raw_data={"error": str(e), "data": data}
            )

    async def _parse_trades_update(self, channel: str, data: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io trades update."""
        try:
            # Get symbol from data - Gate.io trades use 'currency_pair' field
            symbol_str = ""
            
            # If data is a list, check first trade for symbol
            if isinstance(data, list) and len(data) > 0:
                first_trade = data[0] if isinstance(data[0], dict) else {}
                symbol_str = first_trade.get('currency_pair', '') or first_trade.get('s', '')
            elif isinstance(data, dict):
                symbol_str = data.get('currency_pair', '') or data.get('s', '')
            
            if not symbol_str:
                # Fallback: extract from channel if it has symbol suffix  
                channel_parts = channel.split('.')
                if len(channel_parts) > 2:
                    symbol_str = channel_parts[-1]
                else:
                    self.logger.error(f"No symbol found in trades data: {data}")
                    return ParsedMessage(
                        message_type=MessageType.ERROR,
                        channel=channel,
                        raw_data={"error": "No symbol in trades data", "data": data}
                    )
            
            symbol = self.symbol_mapper.to_symbol(symbol_str)
            
            trades = []
            
            # Gate.io trades format is typically a list of trade objects
            trade_list = data if isinstance(data, list) else [data]
            
            for trade_data in trade_list:
                # Gate.io trade format (from your error message):
                # {
                #   "id": 137857046,
                #   "id_market": 137857046,
                #   "create_time": 1758217512,
                #   "create_time_ms": "1758217512055.423000",
                #   "side": "sell",
                #   "currency_pair": "ETH_USDT",
                #   "amount": "0.5381",
                #   "price": "4605.38",
                #   "range": "137857046-137857046"
                # }
                
                side = Side.BUY if trade_data.get("side") == "buy" else Side.SELL
                
                # Use create_time_ms if available (more precise), otherwise create_time
                timestamp_ms = trade_data.get("create_time_ms")
                if timestamp_ms:
                    # Convert from string with decimal to int milliseconds
                    timestamp = int(float(timestamp_ms))
                else:
                    # Convert seconds to milliseconds
                    timestamp = int(trade_data.get("create_time", 0)) * 1000
                
                trade = Trade(
                    symbol=symbol,
                    price=float(trade_data.get("price", 0)),
                    quantity=float(trade_data.get("amount", 0)),
                    quote_quantity=float(trade_data.get("price", 0)) * float(trade_data.get("amount", 0)),
                    side=side,
                    timestamp=timestamp,
                    trade_id=str(trade_data.get("id", "")),
                    is_maker=False  # Gate.io doesn't typically provide maker info in public trades
                )
                trades.append(trade)
            
            return ParsedMessage(
                message_type=MessageType.TRADE,
                symbol=symbol,
                channel=channel,
                data=trades,
                raw_data=data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to parse trades update: {e}")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                channel=channel,
                raw_data={"error": str(e), "data": data}
            )

    async def _parse_book_ticker_update(self, channel: str, data: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io book ticker update."""
        try:
            # Get symbol from data field 's' (symbol)
            symbol_str = data.get('s', '')
            if not symbol_str:
                # Fallback: extract from channel if not in data
                if '.' in channel:
                    symbol_str = channel.split('.')[-1]
            
            symbol = self.symbol_mapper.to_symbol(symbol_str)
            
            # Gate.io book ticker format (from your example):
            # {
            #   "t": 1758216630308,    // timestamp (ms)
            #   "u": 19575639057,      // update_id
            #   "s": "ETH_USDT",       // symbol
            #   "b": "4604.26",        // bid_price
            #   "B": "7.7763",         // bid_quantity
            #   "a": "4604.27",        // ask_price
            #   "A": "2.9053"          // ask_quantity
            # }
            
            book_ticker = BookTicker(
                symbol=symbol,
                bid_price=float(data.get('b', 0)),
                bid_quantity=float(data.get('B', 0)),
                ask_price=float(data.get('a', 0)),
                ask_quantity=float(data.get('A', 0)),
                timestamp=int(data.get('t', 0)),
                update_id=int(data.get('u', 0))
            )
            
            return ParsedMessage(
                message_type=MessageType.BOOK_TICKER,
                symbol=symbol,
                channel=channel,
                data=book_ticker,
                raw_data=data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to parse Gate.io book ticker: {e}")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                channel=channel,
                raw_data={"error": str(e), "data": data}
            )

    def get_supported_message_types(self) -> List[str]:
        """Get list of supported message types."""
        return ["orderbook", "trades", "book_ticker", "subscription", "ping_pong", "other", "error"]