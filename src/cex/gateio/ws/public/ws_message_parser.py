"""
Gate.io Public WebSocket Message Parser

HFT-optimized message parsing for Gate.io public WebSocket streams.
Handles JSON-based messages with efficient diff processing for orderbook updates.

Key Features:
- JSON message parsing with fast type detection
- HFT-optimized orderbook diff parsing
- ParsedOrderbookUpdate generation for OrderbookManager integration
- Object pooling for reduced allocation overhead
- Zero-copy parsing patterns where possible

Performance Targets:
- <50μs per message parsing
- <1ms for complex orderbook diff processing
- Zero allocation in steady state operations
"""

import logging
import time
import json
from typing import Optional, Dict, Any, List, AsyncIterator

from common.orderbook_entry_pool import OrderBookEntryPool
from common.orderbook_diff_processor import ParsedOrderbookUpdate
from core.cex.services.symbol_mapper import SymbolMapperInterface
from core.cex.websocket import MessageParser, ParsedMessage, MessageType
from structs.exchange import OrderBook, Trade, Side


class GateioPublicMessageParser(MessageParser):
    """Gate.io public WebSocket message parser with HFT optimizations."""

    def __init__(self, symbol_mapper: SymbolMapperInterface):
        super().__init__(symbol_mapper)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.entry_pool = OrderBookEntryPool(initial_size=200, max_size=500)

    async def parse_message(self, raw_message: str) -> Optional[ParsedMessage]:
        """Parse Gate.io WebSocket message with fast type detection."""
        try:
            # Gate.io uses JSON format exclusively
            if not isinstance(raw_message, str):
                self.logger.warning(f"Expected string message, got {type(raw_message)}")
                return None

            # Parse JSON message
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError as e:
                self.logger.warning(f"Failed to parse JSON message: {e}")
                return None

            # Process message based on structure
            return await self._parse_json_message(message)

        except Exception as e:
            self.logger.error(f"Error parsing Gate.io message: {e}")
            return None

    def get_message_type(self, message: Dict[str, Any]) -> MessageType:
        """Fast message type detection for Gate.io messages."""
        # Gate.io message structure: {"time": ..., "channel": ..., "event": ..., "result": ...}
        channel = message.get('channel', '')
        event = message.get('event', '')

        if event != 'update':
            if event == 'subscribe':
                return MessageType.SUBSCRIPTION_CONFIRM
            else:
                return MessageType.UNKNOWN

        # Channel-based routing for update messages
        if 'order_book_update' in channel:
            return MessageType.ORDERBOOK
        elif 'trades' in channel:
            return MessageType.TRADE
        else:
            return MessageType.UNKNOWN

    async def parse_orderbook_message(
        self,
        message: Dict[str, Any]
    ) -> Optional[OrderBook]:
        """Parse orderbook message (legacy method for compatibility)."""
        try:
            result = message.get('result', {})
            if not result:
                return None

            # Extract timestamp (Gate.io provides multiple timestamps)
            timestamp = float(result.get('E', time.time() * 1000)) / 1000.0

            # Process bids and asks updates
            bids_data = result.get('b', [])
            asks_data = result.get('a', [])

            # Transform to unified format using object pool
            bids = []
            for bid_data in bids_data:
                if isinstance(bid_data, list) and len(bid_data) >= 2:
                    price = float(bid_data[0])
                    size = float(bid_data[1])
                    if size > 0:  # Only include non-zero sizes
                        entry = self.entry_pool.get_entry(price, size)
                        bids.append(entry)

            asks = []
            for ask_data in asks_data:
                if isinstance(ask_data, list) and len(ask_data) >= 2:
                    price = float(ask_data[0])
                    size = float(ask_data[1])
                    if size > 0:  # Only include non-zero sizes
                        entry = self.entry_pool.get_entry(price, size)
                        asks.append(entry)

            return OrderBook(
                bids=bids,
                asks=asks,
                timestamp=timestamp
            )

        except Exception as e:
            self.logger.error(f"Error parsing Gate.io orderbook: {e}")
            return None

    def parse_orderbook_diff_message(
        self, 
        raw_message: Any, 
        symbol
    ) -> Optional[ParsedOrderbookUpdate]:
        """
        Parse Gate.io orderbook diff message with HFT-optimized processing using msgspec structs.
        
        Gate.io Format:
        {
            "time": 1234567890,
            "channel": "spot.order_book_update",
            "event": "update",
            "result": {
                "t": 1234567890123,
                "e": "depthUpdate",
                "E": 1234567890456,
                "s": "BTC_USDT",
                "U": 157,
                "u": 160,
                "b": [["50000", "0.001"], ["49999", "0.0"]],  # 0 size = remove
                "a": [["50001", "0.002"], ["50002", "0.0"]]
            }
        }
        """
        try:
            if not isinstance(raw_message, dict):
                return None

            # Skip non-update events
            if raw_message.get('event') != 'update':
                return None

            # Use msgspec to decode structured message for validation
            from cex.gateio.structs.exchange import GateioWSOrderbookMessage
            
            try:
                # Convert to msgspec struct for fast validation
                ws_message = msgspec.convert(raw_message, GateioWSOrderbookMessage)
                
                # Extract timestamp (Gate.io provides multiple timestamps)
                timestamp = float(ws_message.result.E) / 1000.0

                # Extract sequence numbers for ordering
                sequence = ws_message.result.u if ws_message.result.u else None

                # Parse bid updates with zero-allocation approach
                bid_updates = []
                for bid_item in ws_message.result.b:
                    if len(bid_item) >= 2:
                        try:
                            price = float(bid_item[0])
                            size = float(bid_item[1])
                            bid_updates.append((price, size))  # Include zero sizes for removal
                        except (ValueError, TypeError, IndexError):
                            continue

                # Parse ask updates with zero-allocation approach
                ask_updates = []
                for ask_item in ws_message.result.a:
                    if len(ask_item) >= 2:
                        try:
                            price = float(ask_item[0])
                            size = float(ask_item[1])
                            ask_updates.append((price, size))  # Include zero sizes for removal
                        except (ValueError, TypeError, IndexError):
                            continue

                return ParsedOrderbookUpdate(
                    symbol=symbol,
                    bid_updates=bid_updates,
                    ask_updates=ask_updates,
                    timestamp=timestamp,
                    sequence=sequence,
                    is_snapshot=False  # Gate.io sends incremental updates
                )
                
            except (msgspec.ValidationError, msgspec.DecodeError, KeyError) as e:
                self.logger.debug(f"Failed to parse as msgspec struct, falling back: {e}")
                # Fallback to original parsing for malformed messages
                return self._parse_orderbook_diff_fallback(raw_message, symbol)

        except Exception as e:
            self.logger.error(f"Error parsing Gate.io diff message: {e}")
            return None

    def _parse_orderbook_diff_fallback(
        self, 
        raw_message: Dict[str, Any], 
        symbol
    ) -> Optional[ParsedOrderbookUpdate]:
        """Fallback orderbook diff parsing for malformed messages."""
        result = raw_message.get('result', {})
        if not result:
            return None

        # Extract timestamp (Gate.io provides multiple timestamps)
        timestamp = float(result.get('E', time.time() * 1000)) / 1000.0

        # Extract sequence numbers for ordering
        sequence = result.get('u')

        # Parse bid updates with zero-allocation approach
        bid_updates = []
        bids_data = result.get('b', [])
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
        asks_data = result.get('a', [])
        for ask_item in asks_data:
            if isinstance(ask_item, list) and len(ask_item) >= 2:
                try:
                    price = float(ask_item[0])
                    size = float(ask_item[1])
                    ask_updates.append((price, size))
                except (ValueError, TypeError, IndexError):
                    continue

        return ParsedOrderbookUpdate(
            symbol=symbol,
            bid_updates=bid_updates,
            ask_updates=ask_updates,
            timestamp=timestamp,
            sequence=sequence,
            is_snapshot=False  # Gate.io sends incremental updates
        )

    def supports_batch_parsing(self) -> bool:
        """Gate.io parser supports batch processing."""
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

    async def _parse_json_message(self, message: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io JSON message."""
        try:
            message_type = self.get_message_type(message)

            if message_type == MessageType.ORDERBOOK:
                symbol_str = message.get('result', {}).get('s', '')
                symbol = None
                if symbol_str and self.symbol_mapper:
                    # Convert Gate.io pair format (BTC_USDT) to Symbol
                    try:
                        from cex.gateio.services.gateio_utils import GateioUtils
                        symbol = GateioUtils.pair_to_symbol(symbol_str)
                    except ImportError:
                        # Fallback if utils not available
                        symbol = self.symbol_mapper.to_symbol(symbol_str)

                orderbook = await self.parse_orderbook_message(message)

                return ParsedMessage(
                    message_type=MessageType.ORDERBOOK,
                    symbol=symbol,
                    channel=message.get('channel'),
                    data=orderbook,
                    raw_data=message
                )

            elif message_type == MessageType.TRADE:
                symbol_str = ''
                result = message.get('result', [])
                if result and isinstance(result, list) and len(result) > 0:
                    symbol_str = result[0].get('currency_pair', '')

                symbol = None
                if symbol_str and self.symbol_mapper:
                    try:
                        from cex.gateio.services.gateio_utils import GateioUtils
                        symbol = GateioUtils.pair_to_symbol(symbol_str)
                    except ImportError:
                        symbol = self.symbol_mapper.to_symbol(symbol_str)

                trades = await self._parse_trades_from_json(message)

                return ParsedMessage(
                    message_type=MessageType.TRADE,
                    symbol=symbol,
                    channel=message.get('channel'),
                    data=trades,
                    raw_data=message
                )

            elif message_type == MessageType.SUBSCRIPTION_CONFIRM:
                return ParsedMessage(
                    message_type=MessageType.SUBSCRIPTION_CONFIRM,
                    raw_data=message
                )

            return None

        except Exception as e:
            self.logger.error(f"Error parsing Gate.io JSON message: {e}")
            return None

    async def _parse_trades_from_json(self, message: Dict[str, Any]) -> Optional[List[Trade]]:
        """Parse trades from Gate.io JSON message."""
        try:
            result = message.get('result', [])
            if not isinstance(result, list):
                return None

            trades = []
            for trade_data in result:
                if not isinstance(trade_data, dict):
                    continue

                # Parse trade side
                side_str = trade_data.get('side', 'buy')
                side = Side.BUY if side_str == 'buy' else Side.SELL

                trade = Trade(
                    price=float(trade_data.get('price', '0')),
                    amount=float(trade_data.get('amount', '0')),
                    side=side,
                    timestamp=int(trade_data.get('create_time', '0')),
                    is_maker=False  # Gate.io doesn't provide maker/taker info in public stream
                )
                trades.append(trade)

            return trades

        except Exception as e:
            self.logger.error(f"Error parsing Gate.io trades: {e}")
            return None