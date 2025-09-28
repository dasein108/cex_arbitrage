from typing import Dict, Any, Optional, List

from infrastructure.networking.websocket.strategies.message_parser import MessageParser
from infrastructure.networking.websocket.structs import ParsedMessage, MessageType
from exchanges.structs.common import FuturesTicker

# New parsing utilities
from infrastructure.networking.websocket.parsing.message_parsing_utils import MessageParsingUtils
from infrastructure.networking.websocket.parsing.error_handling import WebSocketErrorHandler
# Gate.io futures uses direct utility functions - no universal transformer needed

# HFT Logger Integration
from infrastructure.logging import get_strategy_logger, HFTLoggerInterface


class GateioPublicFuturesMessageParser(MessageParser):
    """Gate.io futures WebSocket message parser using common utilities."""

    def __init__(self, logger: Optional[HFTLoggerInterface] = None):
        super().__init__(logger)
        
        # Use injected logger or create strategy-specific logger
        if logger is None:
            tags = ['gateio', 'futures', 'public', 'ws', 'message_parser']
            logger = get_strategy_logger('ws.message_parser.gateio.futures.public', tags)
        
        self.logger = logger
        
        # Initialize utilities
        self.parsing_utils = MessageParsingUtils()
        
        # No symbol extractor needed - use direct utility functions
        
        # Initialize error handler
        self.error_handler = WebSocketErrorHandler("gateio_futures", self.logger)
        
        # Gate.io futures uses direct utility functions - no data transformer needed
        
        # Log initialization
        if self.logger:
            self.logger.debug("GateioPublicFuturesMessageParser initialized with common utilities",
                             exchange="gateio",
                             api_type="futures_public")
            
            # Track component initialization
            self.logger.metric("gateio_futures_public_message_parsers_initialized", 1,
                              tags={"exchange": "gateio", "api_type": "futures_public"})

    async def parse_message(self, raw_message: str) -> Optional[ParsedMessage]:
        """Parse raw WebSocket message from Gate.io futures using common utilities."""
        try:
            # Use common JSON decoding
            message = self.parsing_utils.safe_json_decode(
                raw_message, self.logger, "gateio_futures"
            )
            if not message:
                return None
            
            # Handle different message types based on Gate.io futures format
            if isinstance(message, dict):
                event = message.get("event")
                
                if event == "subscribe":
                    # Subscription confirmation/error
                    return await self._parse_subscription_response(message)
                elif event == "unsubscribe":
                    # Unsubscription confirmation
                    status = message.get("result", {}).get("status", "unknown")
                    return self.parsing_utils.create_subscription_response(
                        channel=message.get("channel", ""),
                        status=status,
                        raw_data=message
                    )
                elif event == "update":
                    # Data update message
                    return await self._parse_update_message(message)
                elif event in ["ping", "pong"]:
                    # Ping/pong messages
                    return self.parsing_utils.create_heartbeat_response(message)
                else:
                    return self.error_handler.handle_unknown_message_type(
                        message, context="Gate.io futures public"
                    )
            
            return None
            
        except Exception as e:
            return self.error_handler.handle_transformation_error(
                message if 'message' in locals() else {}, e, "message_routing", "Gate.io futures public"
            )

    async def _parse_subscription_response(self, message: Dict[str, Any]) -> ParsedMessage:
        """Parse Gate.io futures subscription response directly."""
        channel = message.get("channel", "")
        
        # Handle subscription response directly
        error = message.get("error")
        if error:
            return self.error_handler.handle_subscription_error(
                message, channel, {"error": error}
            )
        
        # Check for success status
        result = message.get("result", {})
        status = result.get("status", "success")  # Gate.io defaults to success
        
        return self.parsing_utils.create_subscription_response(
            channel=channel,
            status="success" if status == "success" else "fail",
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
        
        if "order_book" in channel or "orderbook" in channel:
            return await self._parse_futures_orderbook_update(result_data, channel)
        elif "trades" in channel:
            return await self._parse_futures_trades_update(result_data, channel)
        elif "book_ticker" in channel:
            return await self._parse_futures_book_ticker_update(result_data, channel)
        elif "tickers" in channel:
            return await self._parse_futures_ticker_update(result_data, channel)
        # Futures-specific channels can be handled as basic data for now
        elif "funding_rate" in channel:
            return await self._parse_futures_other_update(result_data, channel, "funding_rate")
        elif "mark_price" in channel:
            return await self._parse_futures_other_update(result_data, channel, "mark_price")
        else:
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                channel=channel,
                raw_data={"channel": channel, "data": result_data}
            )

    # Direct utility function parsing methods for futures
    
    async def _parse_futures_orderbook_update(self, data, channel: str) -> Optional[ParsedMessage]:
        """Parse Gate.io futures orderbook update with direct parsing - no helper functions."""
        try:
            from exchanges.structs.common import OrderBook, OrderBookEntry
            from exchanges.integrations.gateio.utils import to_futures_symbol
            
            # Extract symbol from data fields (Gate.io futures puts symbol in 's' field)
            symbol_str = data.get('s') or data.get('currency_pair') or data.get('contract')
            if not symbol_str:
                return self.error_handler.handle_missing_fields_error(
                    ["s", "currency_pair", "contract"], data, "Gate.io futures orderbook update"
                )
            
            # Direct parsing of Gate.io futures orderbook structure
            bids = []
            asks = []
            
            # Parse bids - objects with {"p": price, "s": size}
            if 'b' in data and data['b']:
                for bid_data in data['b']:
                    if isinstance(bid_data, dict) and 'p' in bid_data and 's' in bid_data:
                        price = float(bid_data['p'])
                        size = float(bid_data['s'])
                        if size > 0:  # Only include non-zero sizes
                            bids.append(OrderBookEntry(price=price, size=size))
            
            # Parse asks - objects with {"p": price, "s": size}
            if 'a' in data and data['a']:
                for ask_data in data['a']:
                    if isinstance(ask_data, dict) and 'p' in ask_data and 's' in ask_data:
                        price = float(ask_data['p'])
                        size = float(ask_data['s'])
                        if size > 0:  # Only include non-zero sizes
                            asks.append(OrderBookEntry(price=price, size=size))
            
            # Create unified orderbook directly
            orderbook = OrderBook(
                symbol=to_futures_symbol(symbol_str),
                bids=bids,
                asks=asks,
                timestamp=data.get('t', 0),
                last_update_id=data.get('u', None)
            )
            
            return self.create_parsed_message(
                message_type=MessageType.ORDERBOOK,
                symbol=orderbook.symbol,
                channel=channel,
                data=orderbook
            )
            
        except Exception as e:
            return self.error_handler.handle_transformation_error(
                data, e, "futures_orderbook_update", "Gate.io futures public"
            )
    
    async def _parse_futures_trades_update(self, data, channel: str) -> Optional[ParsedMessage]:
        """Parse Gate.io futures trades update with direct parsing - no helper functions."""
        try:
            from exchanges.structs.common import Trade, Side
            from exchanges.integrations.gateio.utils import to_futures_symbol
            
            # Gate.io futures trades are typically a list - direct parsing
            trades = []
            trade_list = data if isinstance(data, list) else [data]
            
            for trade_data in trade_list:
                # Direct parsing of Gate.io futures trade format
                symbol = to_futures_symbol(trade_data.get('contract', ''))
                
                # Handle size field - negative means sell, positive means buy
                size = float(trade_data.get('size', '0'))
                quantity = abs(size)
                side = Side.SELL if size < 0 else Side.BUY
                
                # Use create_time_ms if available, otherwise create_time in seconds
                timestamp = trade_data.get('create_time_ms', 0)
                if not timestamp:
                    create_time = trade_data.get('create_time', 0)
                    timestamp = int(create_time * 1000) if create_time else 0
                
                price = float(trade_data.get('price', '0'))
                
                trade = Trade(
                    symbol=symbol,
                    price=price,
                    quantity=quantity,
                    quote_quantity=price * quantity,
                    side=side,
                    timestamp=int(timestamp),
                    trade_id=str(trade_data.get('id', '')),
                    is_maker=trade_data.get('role', '') == 'maker'  # May not be available
                )
                trades.append(trade)
            
            return self.create_parsed_message(
                message_type=MessageType.TRADE,
                symbol=trades[0].symbol if trades else None,
                channel=channel,
                data=trades
            )
            
        except Exception as e:
            return self.error_handler.handle_transformation_error(
                data, e, "futures_trades_update", "Gate.io futures public"
            )
    
    async def _parse_futures_book_ticker_update(self, data, channel: str) -> Optional[ParsedMessage]:
        """Parse Gate.io futures book ticker update with direct parsing - no helper functions."""
        try:
            from exchanges.structs.common import BookTicker
            from exchanges.integrations.gateio.utils import to_futures_symbol
            
            # Extract symbol from data fields (Gate.io futures puts symbol in 's' field)
            symbol_str = data.get('s') or data.get('currency_pair') or data.get('contract')
            if not symbol_str:
                return self.error_handler.handle_missing_fields_error(
                    ["s", "currency_pair", "contract"], data, "Gate.io futures book ticker update"
                )
            
            # Direct parsing of Gate.io futures book ticker format
            book_ticker = BookTicker(
                symbol=to_futures_symbol(symbol_str),
                bid_price=float(data.get('b', '0')),
                bid_quantity=float(data.get('B', 0)),  # Futures uses number, not string
                ask_price=float(data.get('a', '0')),
                ask_quantity=float(data.get('A', 0)),  # Futures uses number, not string
                timestamp=int(data.get('t', 0)),
                update_id=data.get('u', 0)
            )
            
            return self.create_parsed_message(
                message_type=MessageType.BOOK_TICKER,
                symbol=book_ticker.symbol,
                channel=channel,
                data=book_ticker
            )
            
        except Exception as e:
            return self.error_handler.handle_transformation_error(
                data, e, "futures_book_ticker_update", "Gate.io futures public"
            )
    
    async def _parse_futures_ticker_update(self, data, channel: str) -> Optional[ParsedMessage]:
        """Parse Gate.io futures ticker update."""
        try:
            # Extract symbol from data fields (Gate.io futures puts symbol in 's' field)
            symbol_str = data.get('s') or data.get('currency_pair') or data.get('contract')
            # Convert symbol string to unified Symbol using direct utility function
            from exchanges.integrations.gateio.utils import convert_futures_symbol_string
            symbol = convert_futures_symbol_string(symbol_str) if symbol_str else None
            
            # Create futures ticker from data
            from exchanges.structs.common import FuturesTicker
            
            # Gate.io futures ticker format varies, handle basic case
            ticker = FuturesTicker(
                symbol=symbol,
                price=float(data.get('last', '0')),
                change=float(data.get('change_percentage', '0')),
                volume=float(data.get('volume_24h', '0')),
                timestamp=int(data.get('timestamp', 0))
            )
            
            return self.create_parsed_message(
                message_type=MessageType.TICKER,
                symbol=symbol,
                channel=channel,
                data=ticker
            )
            
        except Exception as e:
            return self.error_handler.handle_transformation_error(
                data, e, "futures_ticker_update", "Gate.io futures public"
            )
    
    async def _parse_futures_other_update(self, data, channel: str, data_type: str) -> Optional[ParsedMessage]:
        """Parse Gate.io futures other data (funding rate, mark price, etc.)."""
        try:
            # Extract symbol from data fields (Gate.io futures puts symbol in 's' field)
            symbol_str = data.get('s') or data.get('currency_pair') or data.get('contract')
            # Convert symbol string to unified Symbol using direct utility function
            from exchanges.integrations.gateio.utils import convert_futures_symbol_string
            symbol = convert_futures_symbol_string(symbol_str) if symbol_str else None
            
            return self.create_parsed_message(
                message_type=MessageType.OTHER,
                symbol=symbol,
                channel=channel,
                data={"type": data_type, "data": data}
            )
            
        except Exception as e:
            return self.error_handler.handle_transformation_error(
                data, e, f"futures_{data_type}_update", "Gate.io futures public"
            )

    def get_message_type(self, message: Dict[str, Any]) -> MessageType:
        """Detect Gate.io futures message type from JSON structure."""
        event = message.get("event")
        
        if event in ["ping", "pong"]:
            return MessageType.HEARTBEAT
        elif event == "subscribe":
            return MessageType.SUBSCRIPTION_CONFIRM
        elif event == "unsubscribe":
            return MessageType.SUBSCRIPTION_CONFIRM
        elif event == "update":
            # Check channel for specific type
            channel = message.get("channel", "")
            if "order_book" in channel:
                return MessageType.ORDERBOOK
            elif "trades" in channel:
                return MessageType.TRADE
            elif "book_ticker" in channel:
                return MessageType.BOOK_TICKER
            elif "tickers" in channel:
                return MessageType.TICKER
            return MessageType.UNKNOWN
        else:
            return MessageType.UNKNOWN
    
    def get_supported_message_types(self) -> List[str]:
        """Get list of supported message types for Gate.io futures."""
        return ["orderbook", "trades", "book_ticker", "tickers", "funding_rate", 
                "mark_price", "subscription", "ping_pong", "other", "error"]
    
    # Helper methods for cleaner code organization
    
    def _create_unsubscribe_response(self, message: Dict[str, Any]) -> ParsedMessage:
        """Create unsubscribe response message."""
        return self.parsing_utils.create_subscription_response(
            channel=message.get("channel", ""),
            status=message.get("result", {}).get("status", "unknown"),
            raw_data=message
        )