from typing import Dict, Any, Optional, List

from infrastructure.networking.websocket.strategies.message_parser import MessageParser
from infrastructure.networking.websocket.structs import ParsedMessage, MessageType
from exchanges.structs.common import FuturesTicker

# New parsing utilities
from infrastructure.networking.websocket.parsing.message_parsing_utils import MessageParsingUtils
from infrastructure.networking.websocket.parsing.symbol_extraction import (
    UniversalSymbolExtractor, GateioSymbolExtraction
)
from infrastructure.networking.websocket.parsing.error_handling import WebSocketErrorHandler
from infrastructure.networking.websocket.parsing.universal_transformer import (
    create_gateio_futures_transformer, DataType
)

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
        
        # Initialize symbol extraction with Gate.io strategy
        from exchanges.integrations.gateio.utils import to_futures_symbol
        symbol_strategy = GateioSymbolExtraction(to_futures_symbol)
        self.symbol_extractor = UniversalSymbolExtractor(symbol_strategy)
        
        # Initialize error handler
        self.error_handler = WebSocketErrorHandler("gateio_futures", self.logger)
        
        # Initialize universal data transformer (replaces individual parsing methods)
        self.data_transformer = create_gateio_futures_transformer(
            self.symbol_extractor, self.error_handler, self.logger
        )
        
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
        """Parse Gate.io futures subscription response using universal transformer."""
        channel = message.get("channel", "")
        return await self.data_transformer.transform_subscription_response(
            message, channel, "Gate.io futures public"
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
            return await self.data_transformer.transform_data(
                DataType.ORDERBOOK, result_data, channel, "Gate.io futures public"
            )
        elif "trades" in channel:
            return await self.data_transformer.transform_data(
                DataType.TRADES, result_data, channel, "Gate.io futures public"
            )
        elif "book_ticker" in channel:
            return await self.data_transformer.transform_data(
                DataType.BOOK_TICKER, result_data, channel, "Gate.io futures public"
            )
        elif "tickers" in channel:
            return await self.data_transformer.transform_data(
                DataType.TICKER, result_data, channel, "Gate.io futures public"
            )
        # Futures-specific channels can be handled as OTHER type for now
        elif "funding_rate" in channel:
            return await self.data_transformer.transform_data(
                DataType.OTHER, result_data, channel, "Gate.io futures public"
            )
        elif "mark_price" in channel:
            return await self.data_transformer.transform_data(
                DataType.OTHER, result_data, channel, "Gate.io futures public"
            )
        else:
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                channel=channel,
                raw_data={"channel": channel, "data": result_data}
            )

    # Individual parsing methods removed - replaced by Universal Data Transformer
    # All _parse_*_update methods are now handled by self.data_transformer.transform_data()

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