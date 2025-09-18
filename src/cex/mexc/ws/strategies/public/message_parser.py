import logging
import time
from typing import Optional, Dict, Any, List, AsyncIterator

import msgspec

from common.orderbook_entry_pool import OrderBookEntryPool
from common.orderbook_diff_processor import ParsedOrderbookUpdate
from core.cex.services.symbol_mapper import SymbolMapperInterface
from core.cex.websocket import MessageParser, ParsedMessage, MessageType
from cex.mexc.ws.protobuf_parser import MexcProtobufParser
from structs.common import OrderBook, Trade, Side, BookTicker
from cex.mexc.structs.exchange import MexcWSOrderbookMessage, MexcWSTradeMessage, MexcWSTradeEntry
from cex.mexc.services.mapper import MexcMappings


class MexcPublicMessageParser(MessageParser):
    """MEXC public WebSocket message parser with HFT optimizations."""

    # Fast message type detection constants (compiled once)
    _JSON_INDICATORS = frozenset({ord('{'), ord('[')})
    _PROTOBUF_MAGIC_BYTES = {
        0x0a: 'deals',  # '\\n' - PublicAggreDealsV3Api field tag
        0x12: 'stream',  # '\\x12' - Stream name field tag
        0x1a: 'symbol',  # '\\x1a' - Symbol field tag
    }

    def __init__(self, symbol_mapper: SymbolMapperInterface):
        super().__init__(symbol_mapper)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.entry_pool = OrderBookEntryPool(initial_size=200, max_size=500)
        self.mexc_mapper = MexcMappings(symbol_mapper)

    async def parse_message(self, raw_message: str) -> Optional[ParsedMessage]:
        """Parse MEXC WebSocket message with fast type detection."""
        try:
            # Debug: Log incoming message for troubleshooting
            if self.logger.isEnabledFor(logging.DEBUG):
                message_preview = str(raw_message)[:200] + "..." if len(str(raw_message)) > 200 else str(raw_message)
                self.logger.debug(f"Parsing MEXC message: {message_preview}")

            # Handle both string and bytes input
            if isinstance(raw_message, str):
                # Try to parse as JSON first
                if raw_message.startswith('{') or raw_message.startswith('['):
                    self.logger.debug("Detected JSON message format")
                    json_msg = msgspec.json.decode(raw_message)
                    return await self._parse_json_message(json_msg)
                else:
                    # Convert string to bytes for protobuf
                    message_bytes = raw_message.encode('utf-8')
            else:
                # Already bytes - check if it looks like protobuf
                message_bytes = raw_message

            # Protobuf detection - MEXC protobuf messages start with \n (0x0a) followed by channel name
            # First check if it starts with 0x0a (most reliable indicator)
            if message_bytes and message_bytes[0] == 0x0a:
                self.logger.debug("Detected protobuf message format (starts with 0x0a)")
                return await self._parse_protobuf_message(message_bytes, 'mexc_v3')
            # Secondary check for spot@public BUT only if it doesn't look like JSON
            elif message_bytes and b'spot@public' in message_bytes[:50] and not (
                    message_bytes.startswith(b'{') or message_bytes.startswith(b'[')):
                self.logger.debug("Detected protobuf message format (contains spot@public, not JSON)")
                return await self._parse_protobuf_message(message_bytes, 'mexc_v3')
            else:
                self.logger.debug(f"Unknown message format, first bytes: {message_bytes[:10]}")
                return None

        except Exception as e:
            self.logger.error(f"Error parsing message: {e}")
            return None

    def get_message_type(self, message: Dict[str, Any]) -> MessageType:
        """Fast message type detection."""
        if 'c' in message:  # Channel message
            channel = message['c']
            if 'depth' in channel:
                return MessageType.ORDERBOOK
            elif 'deals' in channel:
                return MessageType.TRADE
            elif 'book_ticker' in channel:
                return MessageType.BOOK_TICKER
        elif 'ping' in message:
            return MessageType.HEARTBEAT
        elif 'code' in message:
            return MessageType.SUBSCRIPTION_CONFIRM

        return MessageType.UNKNOWN

    async def parse_orderbook_message(
            self,
            message: Dict[str, Any]
    ) -> Optional[OrderBook]:
        """Parse orderbook message (legacy method for compatibility)."""
        try:
            data = message.get('d', {})
            symbol_str = message.get('s', '')

            if not data or not symbol_str:
                return None

            # Process with object pooling
            bid_data = data.get('bids', [])
            ask_data = data.get('asks', [])

            bids = []
            asks = []

            for bid in bid_data:
                if isinstance(bid, list) and len(bid) >= 2:
                    bids.append(self.entry_pool.get_entry(
                        price=float(bid[0]),
                        size=float(bid[1])
                    ))

            for ask in ask_data:
                if isinstance(ask, list) and len(ask) >= 2:
                    asks.append(self.entry_pool.get_entry(
                        price=float(ask[0]),
                        size=float(ask[1])
                    ))

            return OrderBook(
                bids=bids,
                asks=asks,
                timestamp=time.time()
            )

        except Exception as e:
            self.logger.error(f"Error parsing orderbook: {e}")
            return None

    def parse_orderbook_diff_message(
            self,
            raw_message: Any,
            symbol
    ) -> Optional[ParsedOrderbookUpdate]:
        """
        Parse MEXC orderbook diff message with HFT-optimized processing.

        MEXC JSON Format:
        {
            "c": "spot@public.limit.depth.v3.api@BTCUSDT@20",
            "d": {
                "bids": [["50000", "0.1"], ["49999", "0.0"]], // 0 size = remove
                "asks": [["50001", "0.2"], ["50002", "0.0"]],
                "version": "12345"
            },
            "t": 1672531200000
        }
        """
        try:
            # Handle JSON format
            if isinstance(raw_message, dict):
                return self._parse_json_diff(raw_message, symbol)

            # Handle protobuf format
            elif isinstance(raw_message, bytes):
                return self._parse_protobuf_diff(raw_message, symbol)

            else:
                self.logger.warning(f"Unknown message type: {type(raw_message)}")
                return None

        except Exception as e:
            self.logger.error(f"Error parsing MEXC diff message: {e}")
            return None

    def _parse_json_diff(
            self,
            message: Dict[str, Any],
            symbol
    ) -> Optional[ParsedOrderbookUpdate]:
        """Parse MEXC JSON diff message with HFT optimization using msgspec structs."""
        try:
            # Use msgspec to decode structured message for validation
            from cex.mexc.structs.exchange import MexcWSOrderbookMessage

            # Convert to msgspec struct for fast validation
            ws_message = msgspec.convert(message, MexcWSOrderbookMessage)

            # Extract timestamp (MEXC provides millisecond timestamps)
            timestamp = float(ws_message.t) / 1000.0

            # Extract sequence/version for ordering
            sequence = None
            if ws_message.d.version:
                try:
                    sequence = int(ws_message.d.version)
                except (ValueError, TypeError):
                    pass

            # Parse bid updates with zero-allocation approach
            bid_updates = []
            for bid_item in ws_message.d.bids:
                if len(bid_item) >= 2:
                    try:
                        price = float(bid_item[0])
                        size = float(bid_item[1])
                        bid_updates.append((price, size))
                    except (ValueError, TypeError, IndexError):
                        continue

            # Parse ask updates with zero-allocation approach
            ask_updates = []
            for ask_item in ws_message.d.asks:
                if len(ask_item) >= 2:
                    try:
                        price = float(ask_item[0])
                        size = float(ask_item[1])
                        ask_updates.append((price, size))
                    except (ValueError, TypeError, IndexError):
                        continue

            # Determine if this is a snapshot (based on channel name)
            is_snapshot = 'limit.depth' in ws_message.c  # vs 'increase.depth'

            return ParsedOrderbookUpdate(
                symbol=symbol,
                bid_updates=bid_updates,
                ask_updates=ask_updates,
                timestamp=timestamp,
                sequence=sequence,
                is_snapshot=is_snapshot
            )

        except (msgspec.ValidationError, msgspec.DecodeError, KeyError) as e:
            self.logger.debug(f"Failed to parse as msgspec struct, falling back: {e}")
            # Fallback to original parsing for malformed messages
            return self._parse_json_diff_fallback(message, symbol)

    def _parse_json_diff_fallback(
            self,
            message: Dict[str, Any],
            symbol
    ) -> Optional[ParsedOrderbookUpdate]:
        """Fallback JSON diff parsing for malformed messages."""
        # Fast validation - check for required fields
        data = message.get('d')
        if not data or not isinstance(data, dict):
            return None

        # Extract timestamp (MEXC provides millisecond timestamps)
        timestamp = float(message.get('t', time.time() * 1000)) / 1000.0

        # Extract sequence/version for ordering
        sequence = None
        version_str = data.get('version')
        if version_str:
            try:
                sequence = int(version_str)
            except (ValueError, TypeError):
                pass

        # Parse bid updates with zero-allocation approach
        bid_updates = []
        bids_data = data.get('bids', [])
        for bid_item in bids_data:
            if isinstance(bid_item, list) and len(bid_item) >= 2:
                try:
                    price = float(bid_item[0])
                    size = float(bid_item[1])
                    bid_updates.append((price, size))
                except (ValueError, TypeError, IndexError):
                    continue

        # Parse ask updates with zero-allocation approach
        ask_updates = []
        asks_data = data.get('asks', [])
        for ask_item in asks_data:
            if isinstance(ask_item, list) and len(ask_item) >= 2:
                try:
                    price = float(ask_item[0])
                    size = float(ask_item[1])
                    ask_updates.append((price, size))
                except (ValueError, TypeError, IndexError):
                    continue

        # Determine if this is a snapshot (based on channel name)
        channel = message.get('c', '')
        is_snapshot = 'limit.depth' in channel  # vs 'increase.depth'

        return ParsedOrderbookUpdate(
            symbol=symbol,
            bid_updates=bid_updates,
            ask_updates=ask_updates,
            timestamp=timestamp,
            sequence=sequence,
            is_snapshot=is_snapshot
        )

    def _parse_protobuf_diff(
            self,
            data: bytes,
            symbol
    ) -> Optional[ParsedOrderbookUpdate]:
        """Parse MEXC protobuf diff message."""
        try:
            # Use MEXC protobuf parser utilities
            wrapper = MexcProtobufParser.parse_wrapper_message(data)

            # Check for depth data
            if wrapper.HasField('publicAggreDepths'):
                depth_data = wrapper.publicAggreDepths

                bid_updates = []
                for bid_item in depth_data.bids:
                    price = float(bid_item.price)
                    size = float(bid_item.quantity)
                    bid_updates.append((price, size))

                ask_updates = []
                for ask_item in depth_data.asks:
                    price = float(ask_item.price)
                    size = float(ask_item.quantity)
                    ask_updates.append((price, size))

                return ParsedOrderbookUpdate(
                    symbol=symbol,
                    bid_updates=bid_updates,
                    ask_updates=ask_updates,
                    timestamp=time.time(),  # Protobuf doesn't always include timestamp
                    sequence=None,  # Extract if available in protobuf
                    is_snapshot=True  # Protobuf messages are typically snapshots
                )

        except Exception as e:
            self.logger.error(f"Error parsing MEXC protobuf: {e}")

        return None

    async def parse_batch_messages(
            self,
            raw_messages: List[str]
    ) -> AsyncIterator[ParsedMessage]:
        """Batch parse messages for efficiency."""
        for raw_message in raw_messages:
            parsed = await self.parse_message(raw_message)
            if parsed:
                yield parsed

    async def _parse_json_message(self, msg: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse JSON message."""
        try:
            message_type = self.get_message_type(msg)

            if message_type == MessageType.ORDERBOOK:
                symbol_str = msg.get('s', '')
                symbol = self.symbol_mapper.to_symbol(symbol_str) if symbol_str else None
                orderbook = await self.parse_orderbook_message(msg)

                return ParsedMessage(
                    message_type=MessageType.ORDERBOOK,
                    symbol=symbol,
                    channel=msg.get('c'),
                    data=orderbook,
                    raw_data=msg
                )

            elif message_type == MessageType.TRADE:
                symbol_str = msg.get('s', '')
                symbol = self.symbol_mapper.to_symbol(symbol_str) if symbol_str else None
                trades = await self._parse_trades_from_json(msg)

                return ParsedMessage(
                    message_type=MessageType.TRADE,
                    symbol=symbol,
                    channel=msg.get('c'),
                    data=trades,
                    raw_data=msg
                )

            elif message_type == MessageType.HEARTBEAT:
                return ParsedMessage(
                    message_type=MessageType.HEARTBEAT,
                    raw_data=msg
                )

            elif message_type == MessageType.SUBSCRIPTION_CONFIRM:
                return ParsedMessage(
                    message_type=MessageType.SUBSCRIPTION_CONFIRM,
                    channel=msg.get('c'),  # Include channel if available
                    raw_data=msg
                )

            elif message_type == MessageType.BOOK_TICKER:
                symbol_str = msg.get('s', '')
                symbol = self.symbol_mapper.to_symbol(symbol_str) if symbol_str else None
                book_ticker = await self._parse_book_ticker_from_json(msg)

                return ParsedMessage(
                    message_type=MessageType.BOOK_TICKER,
                    symbol=symbol,
                    channel=msg.get('c'),
                    data=book_ticker,
                    raw_data=msg
                )

            return None

        except Exception as e:
            self.logger.error(f"Error parsing JSON message: {e}")
            return None

    async def _parse_protobuf_message(
            self,
            data: bytes,
            msg_type: str
    ) -> Optional[ParsedMessage]:
        """Parse protobuf message with type hint."""
        try:
            # Extract symbol from protobuf data using consolidated utility
            symbol_str = MexcProtobufParser.extract_symbol_from_protobuf(data)
            symbol = self.symbol_mapper.to_symbol(symbol_str) if symbol_str else None

            # Process based on message type - check actual MEXC V3 format
            if b'aggre.deals' in data[:50]:
                self.logger.debug(f"Processing trades protobuf for {symbol_str}")
                trades = await self._parse_trades_from_protobuf(data, symbol_str)

                return ParsedMessage(
                    message_type=MessageType.TRADE,
                    symbol=symbol,
                    channel=msg_type,  # Include protobuf message type as channel
                    data=trades
                )

            elif b'aggre.depth' in data[:50]:
                self.logger.debug(f"Processing orderbook protobuf for {symbol_str}")
                orderbook = await self._parse_orderbook_from_protobuf(data, symbol_str)

                return ParsedMessage(
                    message_type=MessageType.ORDERBOOK,
                    symbol=symbol,
                    channel=msg_type,  # Include protobuf message type as channel
                    data=orderbook
                )

            elif b'aggre.bookTicker' in data[:50]:
                self.logger.debug(f"Processing book ticker protobuf for {symbol_str}")
                book_ticker = await self._parse_book_ticker_from_protobuf(data, symbol_str)

                return ParsedMessage(
                    message_type=MessageType.BOOK_TICKER,
                    symbol=symbol,
                    channel=msg_type,  # Include protobuf message type as channel
                    data=book_ticker
                )

            else:
                self.logger.debug(f"Unknown protobuf message type for {symbol_str}, data preview: {data[:50]}")
                return None

        except Exception as e:
            self.logger.error(f"Error parsing protobuf message: {e}")
            return None

    async def _parse_orderbook_from_protobuf(
            self,
            data: bytes,
            symbol_str: str
    ) -> Optional[OrderBook]:
        """Parse orderbook from protobuf data using consolidated utilities."""
        try:
            # Use consolidated protobuf utilities
            wrapper = MexcProtobufParser.parse_wrapper_message(data)

            # Check if we have depth data
            if wrapper.HasField('publicAggreDepths'):
                depth_data = wrapper.publicAggreDepths

                # Convert to OrderBook
                bids = []
                asks = []

                for bid_item in depth_data.bids:
                    bids.append(self.entry_pool.get_entry(
                        price=float(bid_item.price),
                        size=float(bid_item.quantity)
                    ))

                for ask_item in depth_data.asks:
                    asks.append(self.entry_pool.get_entry(
                        price=float(ask_item.price),
                        size=float(ask_item.quantity)
                    ))

                return OrderBook(
                    bids=bids,
                    asks=asks,
                    timestamp=time.time()
                )

            return None

        except Exception as e:
            self.logger.error(f"Error parsing orderbook from protobuf: {e}")
            return None

    async def _parse_trades_from_protobuf(
            self,
            data: bytes,
            symbol_str: str
    ) -> Optional[List[Trade]]:
        """Parse trades from protobuf data using MEXC structs and mapper service."""
        try:
            # Use consolidated protobuf utilities
            wrapper = MexcProtobufParser.parse_wrapper_message(data)

            # Check if we have deals data
            if wrapper.HasField('publicAggreDeals'):
                deals_data = wrapper.publicAggreDeals

                # Convert to MEXC trade entries list
                mexc_trades = []

                for deal_item in deals_data.deals:
                    # Create MEXC-specific struct for performance
                    mexc_trade = MexcWSTradeEntry(
                        p=str(deal_item.price),  # Price as string
                        q=str(deal_item.quantity),  # Quantity as string  
                        t=deal_item.tradeType,  # Trade type (1=buy, 2=sell)
                        T=int(deal_item.time)  # Timestamp
                    )
                    mexc_trades.append(mexc_trade)

                # Use mapper service to convert MEXC structs to unified Trade structs
                unified_trades = []
                for mexc_trade in mexc_trades:
                    unified_trade = self.mexc_mapper.transform_ws_trade_to_unified(mexc_trade, symbol_str)
                    unified_trades.append(unified_trade)

                return unified_trades

            return None

        except Exception as e:
            self.logger.error(f"Error parsing trades from protobuf: {e}")
            return None

    async def _parse_trades_from_json(self, msg: Dict[str, Any]) -> Optional[List[Trade]]:
        """Parse trades from JSON message using MEXC structs and mapper service."""
        try:
            data = msg.get('d', {})
            
            # Convert to MEXC trade entries list using msgspec struct
            mexc_trades = []
            
            for deal in data.get('deals', []):
                # Create MEXC-specific struct for performance
                mexc_trade = MexcWSTradeEntry(
                    p=str(deal.get('p', '0')),  # Price as string
                    q=str(deal.get('q', '0')),  # Quantity as string
                    t=int(deal.get('t', 1)),  # Trade type (1=buy, 2=sell)
                    T=int(deal.get('T', time.time() * 1000))  # Timestamp
                )
                mexc_trades.append(mexc_trade)

            # Use mapper service to convert MEXC structs to unified Trade structs
            unified_trades = []
            for mexc_trade in mexc_trades:
                unified_trade = self.mexc_mapper.transform_ws_trade_to_unified(mexc_trade)
                unified_trades.append(unified_trade)

            return unified_trades

        except Exception as e:
            self.logger.error(f"Error parsing trades from JSON: {e}")
            return None

    async def _parse_book_ticker_from_protobuf(
            self,
            data: bytes,
            symbol_str: str
    ) -> Optional[BookTicker]:
        """Parse MEXC protobuf book ticker message."""
        try:
            # Use consolidated protobuf utilities
            wrapper = MexcProtobufParser.parse_wrapper_message(data)

            # Check if we have book ticker data
            if wrapper.HasField('publicAggreBookTicker'):
                book_ticker_data = wrapper.publicAggreBookTicker
                
                # Extract symbol 
                symbol = self.symbol_mapper.to_symbol(symbol_str)
                
                # Parse protobuf book ticker data
                book_ticker = BookTicker(
                    symbol=symbol,
                    bid_price=float(book_ticker_data.bidPrice),
                    bid_quantity=float(book_ticker_data.bidQuantity),
                    ask_price=float(book_ticker_data.askPrice),
                    ask_quantity=float(book_ticker_data.askQuantity),
                    timestamp=int(time.time() * 1000),  # MEXC doesn't provide timestamp
                    update_id=None  # MEXC doesn't provide update_id
                )
                
                return book_ticker

            return None

        except Exception as e:
            self.logger.error(f"Failed to parse MEXC protobuf book ticker: {e}")
            return None

    async def _parse_book_ticker_from_json(self, msg: Dict[str, Any]) -> Optional[BookTicker]:
        """Parse MEXC JSON book ticker message (fallback if JSON format exists)."""
        try:
            data = msg.get('d', {})
            symbol_str = msg.get('s', '')
            
            if not data or not symbol_str:
                return None
            
            # Extract symbol 
            symbol = self.symbol_mapper.to_symbol(symbol_str)
            
            # Parse JSON book ticker data (hypothetical format)
            book_ticker = BookTicker(
                symbol=symbol,
                bid_price=float(data.get('bidPrice', 0)),
                bid_quantity=float(data.get('bidQuantity', 0)),
                ask_price=float(data.get('askPrice', 0)),
                ask_quantity=float(data.get('askQuantity', 0)),
                timestamp=int(msg.get('t', time.time() * 1000)),
                update_id=None  # MEXC doesn't provide update_id
            )
            
            return book_ticker

        except Exception as e:
            self.logger.error(f"Failed to parse MEXC JSON book ticker: {e}")
            return None
