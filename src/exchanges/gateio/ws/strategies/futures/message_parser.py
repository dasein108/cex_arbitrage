import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from core.exchanges.websocket import MessageParser, ParsedMessage
from core.exchanges.services import SymbolMapperInterface
from core.transport.websocket.structs import MessageType
from structs.common import Trade, OrderBookEntry, Symbol, Side, BookTicker


class GateioFuturesMessageParser(MessageParser):
    """Gate.io futures WebSocket message parser."""

    def __init__(self, symbol_mapper: SymbolMapperInterface):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.symbol_mapper = symbol_mapper

    async def parse_message(self, raw_message: str) -> Optional[ParsedMessage]:
        """Parse raw WebSocket message from Gate.io futures."""
        try:
            import msgspec
            message = msgspec.json.decode(raw_message)
            
            # Handle different message types based on Gate.io futures format
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
                    self.logger.debug(f"Unknown Gate.io futures message format: {message}")
                    return ParsedMessage(
                        message_type=MessageType.UNKNOWN,
                        raw_data=message
                    )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to parse Gate.io futures message: {e}")
            return None

    async def _parse_subscription_response(self, message: Dict[str, Any]) -> ParsedMessage:
        """Parse Gate.io futures subscription response."""
        # Get channel name from message
        channel = message.get("channel", "")
        
        # Check for errors first
        error = message.get("error")
        if error:
            error_code = error.get("code", "unknown")
            error_msg = error.get("message", "unknown error")
            self.logger.error(f"Gate.io futures subscription error {error_code}: {error_msg}")
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
            self.logger.debug(f"Gate.io futures subscription successful for channel: {channel}")
            return ParsedMessage(
                message_type=MessageType.SUBSCRIPTION_CONFIRM,
                channel=channel,
                data={"action": "subscribe", "status": "success"},
                raw_data=message
            )
        elif status == "fail":
            self.logger.error(f"Gate.io futures subscription failed for channel: {channel}")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                channel=channel,
                data={"action": "subscribe", "status": "fail"},
                raw_data=message
            )
        else:
            self.logger.warning(f"Unknown Gate.io futures subscription status: {status}")
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                channel=channel,
                raw_data=message
            )

    async def _parse_update_message(self, message: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io futures update message."""
        # Gate.io futures update format: {"event": "update", "channel": "futures.order_book", "result": {...}}
        channel = message.get("channel", "")
        result_data = message.get("result", {})
        
        if not channel or not result_data:
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                raw_data=message
            )
        
        if "order_book" in channel:
            return await self._parse_orderbook_update(channel, result_data)
        elif "trades" in channel:
            return await self._parse_trades_update(channel, result_data)
        elif "book_ticker" in channel or "tickers" in channel:
            return await self._parse_book_ticker_update(channel, result_data)
        elif "funding_rate" in channel:
            return await self._parse_funding_rate_update(channel, result_data)
        elif "mark_price" in channel:
            return await self._parse_mark_price_update(channel, result_data)
        else:
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                channel=channel,
                raw_data={"channel": channel, "data": result_data}
            )

    async def _parse_orderbook_update(self, channel: str, data: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io futures orderbook update."""
        try:
            # Get symbol from data field 's' (symbol)
            symbol_str = data.get('s', '')
            if not symbol_str:
                # Fallback: extract from channel if it has symbol suffix
                channel_parts = channel.split('.')
                if len(channel_parts) > 2:
                    symbol_str = channel_parts[-1]
                else:
                    self.logger.error(f"No symbol found in futures orderbook data: {data}")
                    return ParsedMessage(
                        message_type=MessageType.ERROR,
                        channel=channel,
                        raw_data={"error": "No symbol in futures orderbook data", "data": data}
                    )
            
            symbol = self.symbol_mapper.to_symbol(symbol_str)
            
            # Gate.io futures orderbook format is similar to spot:
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
            self.logger.error(f"Failed to parse futures orderbook update: {e}")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                channel=channel,
                raw_data={"error": str(e), "data": data}
            )

    async def _parse_trades_update(self, channel: str, data: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io futures trades update."""
        try:
            # Gate.io futures trades format can be single trade or array
            trades_data = data if isinstance(data, list) else [data]
            trades = []
            symbol = None
            
            for trade_data in trades_data:
                # Extract symbol from trade data
                symbol_str = trade_data.get('s', '')
                if symbol_str and symbol is None:
                    symbol = self.symbol_mapper.to_symbol(symbol_str)
                
                # Gate.io futures trade format:
                # {
                #   "id": trade_id,
                #   "create_time": timestamp,
                #   "create_time_ms": timestamp_ms,
                #   "s": symbol,
                #   "p": price,
                #   "size": amount,
                #   "side": "buy/sell"
                # }
                
                trade_id = str(trade_data.get('id', ''))
                timestamp = int(trade_data.get('create_time_ms', trade_data.get('create_time', 0) * 1000))
                price = float(trade_data.get('p', 0))
                quantity = float(trade_data.get('size', 0))
                side_str = trade_data.get('side', 'buy')
                side = Side.BUY if side_str.lower() == 'buy' else Side.SELL
                
                trade = Trade(
                    trade_id=trade_id,
                    price=price,
                    quantity=quantity,
                    side=side,
                    timestamp=timestamp,
                    is_maker=False  # Gate.io doesn't specify maker/taker in public stream
                )
                trades.append(trade)
            
            if not symbol:
                self.logger.error(f"No symbol found in futures trades data: {data}")
                return ParsedMessage(
                    message_type=MessageType.ERROR,
                    channel=channel,
                    raw_data={"error": "No symbol in futures trades data", "data": data}
                )
            
            return ParsedMessage(
                message_type=MessageType.TRADE,
                symbol=symbol,
                channel=channel,
                data=trades,
                raw_data=data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to parse futures trades update: {e}")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                channel=channel,
                raw_data={"error": str(e), "data": data}
            )

    async def _parse_book_ticker_update(self, channel: str, data: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io futures book ticker update."""
        try:
            symbol_str = data.get('s', '')
            if not symbol_str:
                self.logger.error(f"No symbol found in futures book ticker data: {data}")
                return ParsedMessage(
                    message_type=MessageType.ERROR,
                    channel=channel,
                    raw_data={"error": "No symbol in futures book ticker data", "data": data}
                )
            
            symbol = self.symbol_mapper.to_symbol(symbol_str)
            
            # Gate.io futures book ticker format:
            # {
            #   "s": symbol,
            #   "b": best_bid_price,
            #   "B": best_bid_size,
            #   "a": best_ask_price,  
            #   "A": best_ask_size,
            #   "t": timestamp
            # }
            
            book_ticker = BookTicker(
                symbol=symbol,
                bid_price=float(data.get('b', 0)),
                bid_size=float(data.get('B', 0)),
                ask_price=float(data.get('a', 0)),
                ask_size=float(data.get('A', 0)),
                timestamp=data.get('t', 0)
            )
            
            return ParsedMessage(
                message_type=MessageType.BOOK_TICKER,
                symbol=symbol,
                channel=channel,
                data=book_ticker,
                raw_data=data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to parse futures book ticker update: {e}")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                channel=channel,
                raw_data={"error": str(e), "data": data}
            )

    async def _parse_funding_rate_update(self, channel: str, data: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io futures funding rate update."""
        try:
            # Funding rate is futures-specific data
            symbol_str = data.get('s', '')
            if not symbol_str:
                self.logger.error(f"No symbol found in funding rate data: {data}")
                return ParsedMessage(
                    message_type=MessageType.ERROR,
                    channel=channel,
                    raw_data={"error": "No symbol in funding rate data", "data": data}
                )
            
            symbol = self.symbol_mapper.to_symbol(symbol_str)
            
            # Gate.io funding rate format:
            # {
            #   "s": symbol,
            #   "r": funding_rate,
            #   "t": timestamp
            # }
            
            funding_data = {
                "symbol": symbol,
                "funding_rate": float(data.get('r', 0)),
                "timestamp": data.get('t', 0)
            }
            
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,  # Custom type for funding rate
                symbol=symbol,
                channel=channel,
                data=funding_data,
                raw_data=data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to parse funding rate update: {e}")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                channel=channel,
                raw_data={"error": str(e), "data": data}
            )

    async def _parse_mark_price_update(self, channel: str, data: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io futures mark price update."""
        try:
            # Mark price is futures-specific data
            symbol_str = data.get('s', '')
            if not symbol_str:
                self.logger.error(f"No symbol found in mark price data: {data}")
                return ParsedMessage(
                    message_type=MessageType.ERROR,
                    channel=channel,
                    raw_data={"error": "No symbol in mark price data", "data": data}
                )
            
            symbol = self.symbol_mapper.to_symbol(symbol_str)
            
            # Gate.io mark price format:
            # {
            #   "s": symbol,
            #   "p": mark_price,
            #   "t": timestamp
            # }
            
            mark_price_data = {
                "symbol": symbol,
                "mark_price": float(data.get('p', 0)),
                "timestamp": data.get('t', 0)
            }
            
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,  # Custom type for mark price
                symbol=symbol,
                channel=channel,
                data=mark_price_data,
                raw_data=data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to parse mark price update: {e}")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                channel=channel,
                raw_data={"error": str(e), "data": data}
            )