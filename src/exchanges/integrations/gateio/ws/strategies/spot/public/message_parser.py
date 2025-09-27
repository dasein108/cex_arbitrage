from typing import Dict, Any, Optional, List

from infrastructure.networking.websocket.strategies.message_parser import MessageParser
from infrastructure.networking.websocket.structs import ParsedMessage, MessageType
from exchanges.structs.common import Symbol

# New parsing utilities
from infrastructure.networking.websocket.parsing.message_parsing_utils import MessageParsingUtils
from infrastructure.networking.websocket.parsing.symbol_extraction import (
    UniversalSymbolExtractor, GateioSymbolExtraction
)
from infrastructure.networking.websocket.parsing.error_handling import WebSocketErrorHandler
from infrastructure.networking.websocket.parsing.universal_transformer import (
    create_gateio_transformer, DataType
)

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
        
        # Initialize symbol extraction with Gate.io strategy
        from exchanges.integrations.gateio.utils import to_symbol
        symbol_strategy = GateioSymbolExtraction(to_symbol)
        self.symbol_extractor = UniversalSymbolExtractor(symbol_strategy)
        
        # Initialize error handler
        self.error_handler = WebSocketErrorHandler("gateio", self.logger)
        
        # Initialize universal data transformer (replaces individual parsing methods)
        self.data_transformer = create_gateio_transformer(
            self.symbol_extractor, self.error_handler, self.logger
        )
        
        # Log initialization (at DEBUG per logging spec)
        if self.logger:
            self.logger.debug("GateioPublicMessageParser initialized with common utilities",
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
        
        # Use universal transformer for subscription responses
        return await self.data_transformer.transform_subscription_response(
            message, channel, "Gate.io spot public"
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
        
        if "order_book_update" in channel or "orderbook" in channel:
            return await self.data_transformer.transform_data(
                DataType.ORDERBOOK, result_data, channel, "Gate.io spot public"
            )
        elif "trades" in channel:
            return await self.data_transformer.transform_data(
                DataType.TRADES, result_data, channel, "Gate.io spot public"
            )
        elif "book_ticker" in channel:
            return await self.data_transformer.transform_data(
                DataType.BOOK_TICKER, result_data, channel, "Gate.io spot public"
            )
        else:
            return self.error_handler.handle_unknown_message_type(
                {"channel": channel, "data": result_data}, 
                context=f"Gate.io update with channel: {channel}"
            )

    # Individual parsing methods removed - replaced by Universal Data Transformer
    # All _parse_*_update methods are now handled by self.data_transformer.transform_data()

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
            if "order_book" in channel:
                return MessageType.ORDERBOOK
            elif "trades" in channel:
                return MessageType.TRADE
            elif "book_ticker" in channel:
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
