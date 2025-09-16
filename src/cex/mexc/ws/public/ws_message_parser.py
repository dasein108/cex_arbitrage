import logging
import time
from typing import Optional, Dict, Any, List, AsyncIterator

import msgspec

from common.orderbook_entry_pool import OrderBookEntryPool
from core.config.config import ExchangeEnum
from core.cex.services import get_symbol_mapper
from core.cex.websocket import MessageParser, ParsedMessage, MessageType
from cex.mexc.ws.protobuf_parser import MexcProtobufParser
from structs.exchange import OrderBook, Trade, Side


class MexcPublicMessageParser(MessageParser):
    """MEXC public WebSocket message parser with HFT optimizations."""

    # Fast message type detection constants (compiled once)
    _JSON_INDICATORS = frozenset({ord('{'), ord('[')})
    _PROTOBUF_MAGIC_BYTES = {
        0x0a: 'deals',    # '\\n' - PublicAggreDealsV3Api field tag
        0x12: 'stream',   # '\\x12' - Stream name field tag
        0x1a: 'symbol',   # '\\x1a' - Symbol field tag
    }
    symbol_mapper = get_symbol_mapper(ExchangeEnum.MEXC)

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.entry_pool = OrderBookEntryPool(initial_size=200, max_size=500)

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
            elif message_bytes and b'spot@public' in message_bytes[:50] and not (message_bytes.startswith(b'{') or message_bytes.startswith(b'[')):
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
        elif 'ping' in message:
            return MessageType.HEARTBEAT
        elif 'code' in message:
            return MessageType.SUBSCRIPTION_CONFIRM

        return MessageType.UNKNOWN

    async def parse_orderbook_message(
        self,
        message: Dict[str, Any]
    ) -> Optional[OrderBook]:
        """Parse orderbook message."""
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

    def supports_batch_parsing(self) -> bool:
        """MEXC parser supports batch processing."""
        return True

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
                symbol = self.symbol_mapper.pair_to_symbol(symbol_str) if symbol_str else None
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
                symbol = self.symbol_mapper.pair_to_symbol(symbol_str) if symbol_str else None
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
            symbol = self.symbol_mapper.pair_to_symbol(symbol_str) if symbol_str else None

            # Process based on message type - check actual MEXC V3 format
            if b'aggre.deals' in data[:50]:
                self.logger.debug(f"Processing trades protobuf for {symbol_str}")
                trades = await self._parse_trades_from_protobuf(data, symbol_str)

                return ParsedMessage(
                    message_type=MessageType.TRADE,
                    symbol=symbol,
                    data=trades
                )

            elif b'aggre.depth' in data[:50]:
                self.logger.debug(f"Processing orderbook protobuf for {symbol_str}")
                orderbook = await self._parse_orderbook_from_protobuf(data, symbol_str)

                return ParsedMessage(
                    message_type=MessageType.ORDERBOOK,
                    symbol=symbol,
                    data=orderbook
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
        """Parse trades from protobuf data using consolidated utilities."""
        try:
            # Use consolidated protobuf utilities
            wrapper = MexcProtobufParser.parse_wrapper_message(data)

            # Check if we have deals data
            if wrapper.HasField('publicAggreDeals'):
                deals_data = wrapper.publicAggreDeals

                # Convert to Trade list
                trades = []

                for deal_item in deals_data.deals:
                    side = Side.BUY if deal_item.tradeType == 1 else Side.SELL

                    trade = Trade(
                        price=float(deal_item.price),
                        amount=float(deal_item.quantity),
                        side=side,
                        timestamp=deal_item.time,
                        is_maker=False
                    )
                    trades.append(trade)

                return trades

            return None

        except Exception as e:
            self.logger.error(f"Error parsing trades from protobuf: {e}")
            return None

    async def _parse_trades_from_json(self, msg: Dict[str, Any]) -> Optional[List[Trade]]:
        """Parse trades from JSON message."""
        try:
            data = msg.get('d', {})
            trades = []

            for deal in data.get('deals', []):
                side = Side.BUY if deal.get('t') == 1 else Side.SELL

                trade = Trade(
                    price=float(deal.get('p', 0)),
                    amount=float(deal.get('q', 0)),
                    side=side,
                    timestamp=int(deal.get('T', time.time() * 1000)),
                    is_maker=False
                )
                trades.append(trade)

            return trades

        except Exception as e:
            self.logger.error(f"Error parsing trades from JSON: {e}")
            return None
