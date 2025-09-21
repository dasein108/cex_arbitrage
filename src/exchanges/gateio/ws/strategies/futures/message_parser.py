import logging
import traceback
from typing import Dict, Any, Optional, List
from datetime import datetime

from core.transport.websocket.strategies.message_parser import MessageParser
from core.transport.websocket.structs import ParsedMessage
from core.exchanges.services.symbol_mapper.base_symbol_mapper import SymbolMapperInterface
from core.transport.websocket.structs import MessageType
from structs.common import Trade, OrderBookEntry, Symbol, Side, BookTicker, FuturesTicker


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
            traceback.print_exc()
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
        elif "book_ticker" in channel:
            return await self._parse_book_ticker_update(channel, result_data)
        elif "tickers" in channel:
            return await self._parse_tickers_update(channel, result_data, message)
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
            # Get symbol from data field 's' (symbol) - Gate.io futures uses 'contract' field
            symbol_str = data.get('contract', data.get('s', ''))
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
            
            # Parse bids - filter out zero-size entries
            for bid_data in data.get("b", []):
                if len(bid_data) >= 2:
                    price = float(bid_data[0])
                    size = float(bid_data[1])
                    # Only include non-zero sizes (zero size = removal in orderbook)
                    if size > 0:
                        bids.append(OrderBookEntry(price=price, size=size))
            
            # Parse asks - filter out zero-size entries  
            for ask_data in data.get("a", []):
                if len(ask_data) >= 2:
                    price = float(ask_data[0])
                    size = float(ask_data[1])
                    # Only include non-zero sizes (zero size = removal in orderbook)
                    if size > 0:
                        asks.append(OrderBookEntry(price=price, size=size))
            
            # Validate orderbook has data
            if not bids and not asks:
                self.logger.warning(f"Empty orderbook update for {symbol_str}")
                return ParsedMessage(
                    message_type=MessageType.ERROR,
                    channel=channel,
                    raw_data={"error": "Empty orderbook data", "data": data}
                )
                
            # Create OrderBook object - Gate.io timestamps are in milliseconds
            from structs.common import OrderBook
            timestamp = data.get("t", 0)

            
            orderbook = OrderBook(
                bids=bids,
                asks=asks,
                timestamp=int(timestamp),
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
                symbol_str = trade_data.get('contract', '')
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
                # Gate.io provides timestamp in seconds, convert to milliseconds for consistency
                create_time = trade_data.get('create_time', 0)
                create_time_ms = trade_data.get('create_time_ms', create_time * 1000 if create_time else 0)
                timestamp = int(create_time_ms)
                price = float(trade_data.get('price', 0))
                quantity = float(trade_data.get('size', 0))
                side = Side.BUY if quantity > 0 else Side.SELL
                
                trade = Trade(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                    timestamp=timestamp,
                    trade_id=trade_id,
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
            traceback.print_exc()
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
            #   "contract": symbol,
            #   "b": best_bid_price,
            #   "B": best_bid_size,
            #   "a": best_ask_price,  
            #   "A": best_ask_size,
            #   "t": timestamp
            # }
            
            # Handle timestamp conversion for consistency
            timestamp = data.get('t', 0)

                
            book_ticker = BookTicker(
                symbol=symbol,
                bid_price=float(data.get('b', 0)),
                bid_quantity=float(data.get('B', 0)),
                ask_price=float(data.get('a', 0)),
                ask_quantity=float(data.get('A', 0)),
                timestamp=int(timestamp)
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

    async def _parse_tickers_update(self, channel: str, data: Dict[str, Any], message: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io futures tickers update including funding rate."""
        try:
            # Gate.io futures tickers format - data can be array or single object
            # Example message: {'channel': 'futures.tickers', 'event': 'update', 
            #                   'result': [ticker_data], 'time': 1758452361, 'time_ms': 1758452361778}
            # Example ticker_data: {'change_from': '24h', 'change_percentage': '-0.1046', 'change_price': '-4.67', 
            #                       'contract': 'ETH_USDT', 'funding_rate': '0.0001', 'funding_rate_indicative': '0.0001', 
            #                       'high_24h': '4507.90', 'index_price': '4459.15', 'last': '4457.90', 'low_24h': '4442.05', 
            #                       'mark_price': '4457.90', 'price_type': 'last', 'quanto_base_rate': '', 'total_size': '129041914', 
            #                       'volume_24h': '88582553', 'volume_24h_base': '885825', 'volume_24h_quote': '3948921674', 
            #                       'volume_24h_settle': '3948921674'}]
            
            # Extract timestamp from message level
            message_timestamp = message.get('time_ms', message.get('time', 0) * 1000 if message.get('time') else 0)

            
            tickers_data = data if isinstance(data, list) else [data]
            parsed_tickers = []
            
            for ticker_data in tickers_data:
                symbol_str = ticker_data.get('contract', '')
                if not symbol_str:
                    self.logger.warning(f"No contract found in futures ticker data: {ticker_data}")
                    continue
                
                symbol = self.symbol_mapper.to_symbol(symbol_str)
                
                # Parse ticker data with comprehensive futures information and validation
                try:
                    last_price = float(ticker_data.get('last', 0))
                    
                    # Validate critical price fields before creating struct
                    if last_price <= 0:
                        self.logger.warning(f"Invalid last price for {symbol_str}: {last_price}")
                        continue
                    
                    futures_ticker = FuturesTicker(
                        symbol=symbol,
                        last_price=last_price,
                        mark_price=float(ticker_data.get('mark_price', 0)),
                        index_price=float(ticker_data.get('index_price', 0)),
                        funding_rate=float(ticker_data.get('funding_rate', 0)),
                        funding_rate_indicative=float(ticker_data.get('funding_rate_indicative', 0)),
                        high_24h=float(ticker_data.get('high_24h', 0)),
                        low_24h=float(ticker_data.get('low_24h', 0)),
                        change_price=float(ticker_data.get('change_price', 0)),
                        change_percentage=float(ticker_data.get('change_percentage', 0)),
                        volume_24h=float(ticker_data.get('volume_24h', 0)),
                        volume_24h_base=float(ticker_data.get('volume_24h_base', 0)),
                        volume_24h_quote=float(ticker_data.get('volume_24h_quote', 0)),
                        volume_24h_settle=float(ticker_data.get('volume_24h_settle', 0)),
                        total_size=float(ticker_data.get('total_size', 0)),
                        timestamp=int(message_timestamp),
                        quanto_base_rate=ticker_data.get('quanto_base_rate', ''),
                        price_type=ticker_data.get('price_type', 'last'),
                        change_from=ticker_data.get('change_from', '24h')
                    )
                        
                except (ValueError, TypeError) as e:
                    self.logger.warning(f"Failed to parse ticker values for {symbol_str}: {e}")
                    continue
                
                parsed_tickers.append(futures_ticker)
            
            if not parsed_tickers:
                self.logger.error(f"No valid tickers found in futures data: {data}")
                return ParsedMessage(
                    message_type=MessageType.ERROR,
                    channel=channel,
                    raw_data={"error": "No valid tickers in futures data", "data": data}
                )
            
            # For single ticker, return with symbol; for multiple tickers, return as array
            if len(parsed_tickers) == 1:
                return ParsedMessage(
                    message_type=MessageType.TICKER,
                    symbol=parsed_tickers[0].symbol,
                    channel=channel,
                    data=parsed_tickers[0],
                    raw_data=data
                )
            else:
                return ParsedMessage(
                    message_type=MessageType.TICKER,
                    channel=channel,
                    data=parsed_tickers,
                    raw_data=data
                )
                
        except Exception as e:
            self.logger.error(f"Failed to parse futures tickers update: {e}")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                channel=channel,
                raw_data={"error": str(e), "data": data}
            )

    async def _parse_funding_rate_update(self, channel: str, data: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io futures funding rate update."""
        try:
            # Funding rate is futures-specific data - Gate.io futures uses 'contract' field
            symbol_str = data.get('contract', data.get('s', ''))
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
            
            # Handle timestamp conversion for consistency
            timestamp = data.get('t', 0)

            funding_data = {
                "symbol": symbol,
                "funding_rate": float(data.get('r', 0)),
                "timestamp": int(timestamp)
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
            # Mark price is futures-specific data - Gate.io futures uses 'contract' field
            symbol_str = data.get('contract', data.get('s', ''))
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
            
            # Handle timestamp conversion for consistency
            timestamp = data.get('t', 0)

            mark_price_data = {
                "symbol": symbol,
                "mark_price": float(data.get('p', 0)),
                "timestamp": int(timestamp)
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