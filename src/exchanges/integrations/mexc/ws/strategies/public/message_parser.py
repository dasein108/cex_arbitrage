import time
import traceback
from typing import Optional, Dict, Any, List

import msgspec

from common.orderbook_entry_pool import OrderBookEntryPool
from common.orderbook_diff_processor import ParsedOrderbookUpdate
from infrastructure.networking.websocket.strategies.message_parser import MessageParser
from infrastructure.networking.websocket.structs import ParsedMessage, MessageType
from exchanges.integrations.mexc.ws.protobuf_parser import MexcProtobufParser
from exchanges.structs.common import OrderBook, Trade, BookTicker
from exchanges.integrations.mexc.structs.exchange import MexcWSTradeEntry
# Use direct utility functions instead of mapper classes
from exchanges.integrations.mexc import utils as mexc_utils
from exchanges.integrations.mexc.services.symbol_mapper import MexcSymbol

# HFT Logger Integration
from infrastructure.logging import get_strategy_logger, HFTLoggerInterface


class MexcPublicMessageParser(MessageParser):
    """MEXC public WebSocket message parser with HFT optimizations."""

    # Fast message type detection constants (compiled once)
    _JSON_INDICATORS = frozenset({ord('{'), ord('[')})
    _PROTOBUF_MAGIC_BYTES = {
        0x0a: 'deals',  # '\\n' - PublicAggreDealsV3Api field tag
        0x12: 'stream',  # '\\x12' - Stream name field tag
        0x1a: 'symbol',  # '\\x1a' - Symbol field tag
    }

    def __init__(self, logger: Optional[HFTLoggerInterface] = None):
        super().__init__(logger)
        
        # Use injected logger or create strategy-specific logger
        if logger is None:
            tags = ['mexc', 'public', 'ws', 'message_parser']
            logger = get_strategy_logger('ws.message_parser.mexc.public', tags)
        
        self.logger = logger
        self.entry_pool = OrderBookEntryPool(initial_size=200, max_size=500)
        
        # Log MEXC-specific initialization
        if self.logger:
            self.logger.info("MexcPublicMessageParser initialized",
                            entry_pool_initial_size=200,
                            entry_pool_max_size=500)
            
            # Track component initialization
            self.logger.metric("mexc_public_message_parsers_initialized", 1,
                              tags={"exchange": "mexc", "api_type": "public"})

    async def parse_message(self, raw_message: str) -> Optional[ParsedMessage]:
        """Parse MEXC WebSocket message with fast type detection."""
        try:
            # Debug: Log incoming message for troubleshooting with structured format
            if self.logger:
                message_preview = str(raw_message)[:200] + "..." if len(str(raw_message)) > 200 else str(raw_message)
                self.logger.debug("Parsing MEXC message",
                                exchange="mexc",
                                message_preview=message_preview,
                                message_length=len(str(raw_message)))

            # Handle both string and bytes input
            if isinstance(raw_message, str):
                # Try to parse as JSON first
                if raw_message.startswith('{') or raw_message.startswith('['):
                    if self.logger:
                        self.logger.debug("Detected JSON message format",
                                        exchange="mexc",
                                        format="json")
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
                if self.logger:
                    self.logger.debug("Detected protobuf message format (starts with 0x0a)",
                                    exchange="mexc",
                                    format="protobuf")
                return await self._parse_protobuf_message(message_bytes, 'mexc_v3')
            # Secondary check for spot@public BUT only if it doesn't look like JSON
            elif message_bytes and b'spot@public' in message_bytes[:50] and not (
                    message_bytes.startswith(b'{') or message_bytes.startswith(b'[')):
                if self.logger:
                    self.logger.debug("Detected protobuf message format (contains spot@public, not JSON)",
                                    exchange="mexc",
                                    format="protobuf")
                return await self._parse_protobuf_message(message_bytes, 'mexc_v3')
            else:
                if self.logger:
                    self.logger.debug("Unknown message format",
                                    exchange="mexc",
                                    first_bytes=message_bytes[:10].hex() if message_bytes else "empty")
                return None

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error parsing MEXC message: {e}",
                                exchange="mexc",
                                error_type=type(e).__name__)
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

    # Removed legacy parse_orderbook_message() method - functionality integrated into _parse_json_message()
    # This eliminates code duplication and uses consistent error handling patterns

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
                if self.logger:
                    self.logger.warning("Unknown message type in diff parsing",
                                      exchange="mexc",
                                      message_type=type(raw_message).__name__)
                return None

        except Exception as e:
            if self.logger:
                self.logger.error("Error parsing MEXC diff message",
                                exchange="mexc",
                                error_type=type(e).__name__,
                                error_message=str(e))
            return None

    def _parse_json_diff(
            self,
            message: Dict[str, Any],
            symbol
    ) -> Optional[ParsedOrderbookUpdate]:
        """Parse MEXC JSON diff message with HFT optimization using msgspec structs."""
        try:
            # Use msgspec to decode structured message for validation
            from exchanges.integrations.mexc.structs.exchange import MexcWSOrderbookMessage

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
            if self.logger:
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
            if self.logger:
                self.logger.error("Error parsing MEXC protobuf",
                                exchange="mexc",
                                error_type=type(e).__name__,
                                error_message=str(e))

        return None

    # Removed redundant batch processing - using inherited implementation from unified MessageParser
    # The composite class provides comprehensive batch processing with metrics tracking and error handling

    async def _parse_json_message(self, msg: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse JSON message."""
        try:
            message_type = self.get_message_type(msg)

            if message_type == MessageType.ORDERBOOK:
                symbol_str = msg.get('s', '')
                symbol = MexcSymbol.to_symbol(symbol_str) if symbol_str else None
                
                # Parse orderbook data inline with object pooling
                data = msg.get('d', {})
                if data:
                    bids = []
                    asks = []
                    
                    for bid in data.get('bids', []):
                        if isinstance(bid, list) and len(bid) >= 2:
                            bids.append(self.entry_pool.get_entry(
                                price=float(bid[0]),
                                size=float(bid[1])
                            ))
                    
                    for ask in data.get('asks', []):
                        if isinstance(ask, list) and len(ask) >= 2:
                            asks.append(self.entry_pool.get_entry(
                                price=float(ask[0]),
                                size=float(ask[1])
                            ))
                    
                    orderbook = OrderBook(
                        bids=bids,
                        asks=asks,
                        timestamp=time.time()
                    )
                else:
                    orderbook = None

                return self.create_parsed_message(
                    message_type=MessageType.ORDERBOOK,
                    symbol=symbol,
                    channel=msg.get('c'),
                    data=orderbook,
                    raw_data=msg
                )

            elif message_type == MessageType.TRADE:
                symbol_str = msg.get('s', '')
                symbol = MexcSymbol.to_symbol(symbol_str) if symbol_str else None
                trades = await self._parse_trades_from_json(msg)

                return self.create_parsed_message(
                    message_type=MessageType.TRADE,
                    symbol=symbol,
                    channel=msg.get('c'),
                    data=trades,
                    raw_data=msg
                )

            elif message_type == MessageType.HEARTBEAT:
                return self.create_heartbeat_response(msg)

            elif message_type == MessageType.SUBSCRIPTION_CONFIRM:
                return self.create_subscription_response(
                    channel=msg.get('c', ''),
                    status="success" if msg.get('code') == 200 else "fail",
                    raw_data=msg
                )

            elif message_type == MessageType.BOOK_TICKER:
                symbol_str = msg.get('s', '')
                symbol = MexcSymbol.to_symbol(symbol_str) if symbol_str else None
                book_ticker = await self._parse_book_ticker_from_json(msg)

                return self.create_parsed_message(
                    message_type=MessageType.BOOK_TICKER,
                    symbol=symbol,
                    channel=msg.get('c'),
                    data=book_ticker,
                    raw_data=msg
                )

            return None

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error parsing JSON message: {e}",
                                exchange="mexc",
                                error_type=type(e).__name__)
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
            symbol = MexcSymbol.to_symbol(symbol_str) if symbol_str else None

            # Process based on message type - check actual MEXC V3 format
            if b'aggre.deals' in data[:50]:
                if self.logger:
                    self.logger.debug("Processing trades protobuf",
                                    exchange="mexc",
                                    symbol=symbol_str,
                                    format="protobuf",
                                    message_type="trades")
                trades = await self._parse_trades_from_protobuf(data, symbol_str)

                return self.create_parsed_message(
                    message_type=MessageType.TRADE,
                    symbol=symbol,
                    channel=msg_type,  # Include protobuf message type as channel
                    data=trades
                )

            elif b'aggre.depth' in data[:50]:
                if self.logger:
                    self.logger.debug("Processing orderbook protobuf",
                                    exchange="mexc",
                                    symbol=symbol_str,
                                    format="protobuf",
                                    message_type="orderbook")
                orderbook = await self._parse_orderbook_from_protobuf(data, symbol_str)

                return self.create_parsed_message(
                    message_type=MessageType.ORDERBOOK,
                    symbol=symbol,
                    channel=msg_type,  # Include protobuf message type as channel
                    data=orderbook
                )

            elif b'aggre.bookTicker' in data[:50]:
                if self.logger:
                    self.logger.debug("Processing book ticker protobuf",
                                    exchange="mexc",
                                    symbol=symbol_str,
                                    format="protobuf",
                                    message_type="book_ticker")
                book_ticker = await self._parse_book_ticker_from_protobuf(data, symbol_str)

                return self.create_parsed_message(
                    message_type=MessageType.BOOK_TICKER,
                    symbol=symbol,
                    channel=msg_type,  # Include protobuf message type as channel
                    data=book_ticker
                )

            else:
                if self.logger:
                    self.logger.debug("Unknown protobuf message type",
                                    exchange="mexc",
                                    symbol=symbol_str,
                                    format="protobuf",
                                    data_preview=data[:50].hex())
                return None

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error parsing protobuf message: {e}",
                                exchange="mexc",
                                error_type=type(e).__name__)
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
                    symbol=MexcSymbol.to_symbol(symbol_str),
                    bids=bids,
                    asks=asks,
                    timestamp=int(time.time())
                )

            return None

        except Exception as e:
            if self.logger:
                self.logger.error("Error parsing orderbook from protobuf",
                                exchange="mexc",
                                error_type=type(e).__name__,
                                error_message=str(e))
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
                unified_trades = []

                for deal_item in deals_data.deals:
                    # Create MEXC-specific struct for performance
                    unified_trade = mexc_utils.ws_to_trade(deal_item, symbol_str)
                    unified_trades.append(unified_trade)

                return unified_trades

            return None

        except Exception as e:
            if self.logger:
                self.logger.error("Error parsing trades from protobuf",
                                exchange="mexc",
                                error_type=type(e).__name__,
                                error_message=str(e))
            traceback.print_exc()
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
                unified_trade = mexc_utils.ws_to_trade(mexc_trade)
                unified_trades.append(unified_trade)

            return unified_trades

        except Exception as e:
            if self.logger:
                self.logger.error("Error parsing trades from JSON",
                                exchange="mexc",
                                error_type=type(e).__name__,
                                error_message=str(e))
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
                symbol = MexcSymbol.to_symbol(symbol_str)
                
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
            if self.logger:
                self.logger.error("Failed to parse MEXC protobuf book ticker",
                                exchange="mexc",
                                error_type=type(e).__name__,
                                error_message=str(e))
            return None

    async def _parse_book_ticker_from_json(self, msg: Dict[str, Any]) -> Optional[BookTicker]:
        """Parse MEXC JSON book ticker message (fallback if JSON format exists)."""
        try:
            data = msg.get('d', {})
            symbol_str = msg.get('s', '')
            
            if not data or not symbol_str:
                return None
            
            # Extract symbol 
            symbol = MexcSymbol.to_symbol(symbol_str)
            
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
            if self.logger:
                self.logger.error("Failed to parse MEXC JSON book ticker",
                                exchange="mexc",
                                error_type=type(e).__name__,
                                error_message=str(e))
            return None
