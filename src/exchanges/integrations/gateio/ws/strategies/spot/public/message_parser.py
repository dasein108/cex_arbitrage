from typing import Dict, Any, Optional, List

from infrastructure.networking.websocket.strategies.message_parser import MessageParser
from infrastructure.networking.websocket.structs import ParsedMessage, MessageType
from exchanges.structs.common import Symbol

# New parsing utilities
from infrastructure.networking.websocket.parsing.message_parsing_utils import MessageParsingUtils
from infrastructure.networking.websocket.parsing.error_handling import WebSocketErrorHandler
# Gate.io uses direct utility functions - no universal transformer needed

# HFT Logger Integration
from infrastructure.logging import get_strategy_logger, HFTLoggerInterface


class GateioPublicMessageParser(MessageParser):
    """Gate.io public WebSocket message parser using common utilities."""

    def __init__(self, logger: Optional[HFTLoggerInterface] = None):
        super().__init__(logger)
        
        # Use injected logger or create strategy-specific logger
        if logger is None:
            tags = ['gateio', 'spot', 'public', 'ws', 'message_parser']
            logger = get_strategy_logger('ws.message_parser.gateio.spot.public', tags)
        
        self.logger = logger
        
        # Initialize utilities
        self.parsing_utils = MessageParsingUtils()
        
        # No symbol extractor needed - use direct utility functions
        
        # Initialize error handler
        self.error_handler = WebSocketErrorHandler("gateio", self.logger)
        
        # Gate.io uses direct utility functions - no data transformer needed
        
        # Log initialization
        if self.logger:
            self.logger.info("GateioPublicMessageParser initialized with common utilities",
                            exchange="gateio",
                            api_type="spot_public")
            
            # Track component initialization
            self.logger.metric("gateio_spot_public_message_parsers_initialized", 1,
                              tags={"exchange": "gateio", "api_type": "spot_public"})

    async def parse_message(self, raw_message: str) -> Optional[ParsedMessage]:
        """Parse raw WebSocket message from Gate.io using common utilities."""
        try:
            # Use common JSON decoding
            message = self.parsing_utils.safe_json_decode(
                raw_message, self.logger, "gateio"
            )
            if not message:
                return None
            
            # Log parsing context
            self.parsing_utils.log_parsing_context(
                self.logger, "Gate.io", "WebSocket", raw_message
            )
            
            # Handle different message types based on Gate.io format
            if isinstance(message, dict):
                event = message.get("event")
                
                if event == "subscribe":
                    return await self._parse_subscription_response(message)
                elif event == "unsubscribe":
                    return self._create_unsubscribe_response(message)
                elif event == "update":
                    return await self._parse_update_message(message)
                elif event in ["ping", "pong"]:
                    return self.parsing_utils.create_heartbeat_response(message)
                else:
                    return self.error_handler.handle_unknown_message_type(
                        message, context="Gate.io spot public"
                    )
            
            return None
            
        except Exception as e:
            return self.error_handler.handle_transformation_error(
                message if 'message' in locals() else {}, e, "message_routing", "Gate.io spot public"
            )

    async def _parse_subscription_response(self, message: Dict[str, Any]) -> ParsedMessage:
        """Parse Gate.io subscription response."""
        # Get channel name from message
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
        """Parse Gate.io update message."""
        # Gate.io update format: {"event": "update", "channel": "spot.book_ticker", "result": {...}}
        channel = message.get("channel", "")
        result_data = message.get("result", {})
        
        # Validate required fields
        validation_error = self.parsing_utils.validate_required_fields(
            message, ["channel", "result"], "Gate.io update message"
        )
        if validation_error:
            return self.error_handler.handle_missing_fields_error(
                ["channel", "result"], message, "Gate.io update message"
            )
        
        if channel in ["spot.order_book_update", "spot.order_book", "spot.obu"]:
            return await self._parse_orderbook_update(result_data, channel)
        elif channel in ["spot.trades", "spot.trades_v2"]:
            return await self._parse_trades_update(result_data, channel)
        elif channel == "spot.book_ticker":
            return await self._parse_book_ticker_update(result_data, channel)
        else:
            return self.error_handler.handle_unknown_message_type(
                {"channel": channel, "data": result_data}, 
                context=f"Gate.io update with channel: {channel}"
            )

    # Direct utility function parsing methods
    
    async def _parse_orderbook_update(self, data, channel: str) -> Optional[ParsedMessage]:
        """Parse Gate.io orderbook update with direct parsing - no helper functions."""
        try:
            from exchanges.structs.common import OrderBook, OrderBookEntry
            from exchanges.integrations.gateio.utils import to_symbol
            
            # Extract symbol from data fields (Gate.io puts symbol in 's' field)
            symbol_str = data.get('s') or data.get('currency_pair')
            if not symbol_str:
                return self.error_handler.handle_missing_fields_error(
                    ["s", "currency_pair"], data, "Gate.io orderbook update"
                )
            
            # Direct parsing of Gate.io orderbook structure
            bids = []
            asks = []
            
            # Parse bids - arrays of [price, amount]
            if 'b' in data and data['b']:
                for bid_data in data['b']:
                    if len(bid_data) >= 2:
                        price = float(bid_data[0])
                        size = float(bid_data[1])
                        bids.append(OrderBookEntry(price=price, size=size))
            
            # Parse asks - arrays of [price, amount]  
            if 'a' in data and data['a']:
                for ask_data in data['a']:
                    if len(ask_data) >= 2:
                        price = float(ask_data[0])
                        size = float(ask_data[1])
                        asks.append(OrderBookEntry(price=price, size=size))
            
            # Create unified orderbook directly
            orderbook = OrderBook(
                symbol=to_symbol(symbol_str),
                bids=bids,
                asks=asks,
                timestamp=data.get('t', 0),  # Gate.io uses 't' for timestamp
                last_update_id=data.get('u', None)  # Gate.io uses 'u' for last update ID
            )
            
            return self.create_parsed_message(
                message_type=MessageType.ORDERBOOK,
                symbol=orderbook.symbol,
                channel=channel,
                data=orderbook
            )
            
        except Exception as e:
            return self.error_handler.handle_transformation_error(
                data, e, "orderbook_update", "Gate.io spot public"
            )
    
    async def _parse_trades_update(self, data, channel: str) -> Optional[ParsedMessage]:
        """Parse Gate.io trades update with direct parsing - no helper functions."""
        try:
            from exchanges.structs.common import Trade
            from exchanges.integrations.gateio.utils import to_symbol, to_side
            
            # Extract symbol from data fields (Gate.io puts symbol in 'currency_pair' field for trades)
            symbol_str = None
            if isinstance(data, list) and len(data) > 0:
                # For trades, data is typically a list, get symbol from first trade
                symbol_str = data[0].get('currency_pair') or data[0].get('s')
            elif isinstance(data, dict):
                # For single trade data
                symbol_str = data.get('currency_pair') or data.get('s')
            
            if not symbol_str:
                return self.error_handler.handle_missing_fields_error(
                    ["currency_pair", "s"], data, "Gate.io trades update"
                )
            
            # Gate.io trades are typically a list - direct parsing
            trades = []
            trade_list = data if isinstance(data, list) else [data]
            symbol = to_symbol(symbol_str)
            
            for trade_data in trade_list:
                # Direct parsing of Gate.io trade format
                create_time = trade_data.get('create_time', 0)
                timestamp = int(create_time * 1000) if create_time else 0
                
                price = float(trade_data.get('price', '0'))
                quantity = float(trade_data.get('amount', '0'))
                
                trade = Trade(
                    symbol=symbol,
                    price=price,
                    quantity=quantity,
                    quote_quantity=price * quantity,
                    side=to_side(trade_data.get('side', 'buy')),
                    timestamp=timestamp,
                    trade_id=str(trade_data.get('id', '')),
                    is_maker=trade_data.get('role', '') == 'maker'  # May not be available in public trades
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
                data, e, "trades_update", "Gate.io spot public"
            )
    
    async def _parse_book_ticker_update(self, data, channel: str) -> Optional[ParsedMessage]:
        """Parse Gate.io book ticker update with direct parsing - no helper functions."""
        try:
            from exchanges.structs.common import BookTicker
            from exchanges.integrations.gateio.utils import to_symbol
            
            # Extract symbol from data fields (Gate.io puts symbol in 's' field for book ticker)
            symbol_str = data.get('s') or data.get('currency_pair')
            if not symbol_str:
                return self.error_handler.handle_missing_fields_error(
                    ["s", "currency_pair"], data, "Gate.io book ticker update"
                )
            
            # Direct parsing of Gate.io book ticker format
            book_ticker = BookTicker(
                symbol=to_symbol(symbol_str),
                bid_price=float(data.get('b', '0')),
                bid_quantity=float(data.get('B', '0')),
                ask_price=float(data.get('a', '0')),
                ask_quantity=float(data.get('A', '0')),
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
                data, e, "book_ticker_update", "Gate.io spot public"
            )

    def get_message_type(self, message: Dict[str, Any]) -> MessageType:
        """Detect Gate.io message type from JSON structure."""
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
            if channel in ["spot.order_book_update", "spot.order_book", "spot.obu"]:
                return MessageType.ORDERBOOK
            elif channel in ["spot.trades", "spot.trades_v2"]:
                return MessageType.TRADE
            elif channel == "spot.book_ticker":
                return MessageType.BOOK_TICKER
            return MessageType.UNKNOWN
        else:
            return MessageType.UNKNOWN
    
    def get_supported_message_types(self) -> List[str]:
        """Get list of supported message types."""
        return ["orderbook", "trades", "book_ticker", "subscription", "ping_pong", "other", "error"]
    
    # Helper methods for cleaner code organization
    
    def _create_unsubscribe_response(self, message: Dict[str, Any]) -> ParsedMessage:
        """Create unsubscribe response message."""
        return self.parsing_utils.create_subscription_response(
            channel=message.get("channel", ""),
            status=message.get("result", {}).get("status", "unknown"),
            raw_data=message
        )
