import logging
from typing import Dict, Any, Optional, List
import msgspec

from infrastructure.networking.websocket.strategies.message_parser import MessageParser
from infrastructure.networking.websocket.structs import ParsedMessage, MessageType
from exchanges.services import BaseExchangeMapper
from infrastructure.data_structures.common import Symbol


class GateioPublicMessageParser(MessageParser):
    """Gate.io public WebSocket message parser with integrated parsing utilities."""
    
    @staticmethod
    def _safe_extract_symbol(
        data: Dict[str, Any], 
        mapper: BaseExchangeMapper,
        symbol_fields: List[str] = None,
        channel: str = "",
        logger: logging.Logger = None
    ) -> Optional[Symbol]:
        """Safely extract symbol from message data with multiple fallback strategies."""
        if symbol_fields is None:
            symbol_fields = ['s', 'symbol', 'currency_pair', 'pair']
            
        # Try each symbol field
        for field in symbol_fields:
            symbol_str = data.get(field)
            if symbol_str:
                try:
                    return mapper.to_symbol(symbol_str)
                except Exception as e:
                    if logger:
                        logger.debug(f"Failed to convert symbol '{symbol_str}' from field '{field}': {e}")
                    continue
        
        # Fallback: extract from channel if it contains symbol
        if channel and '.' in channel:
            channel_parts = channel.split('.')
            if len(channel_parts) > 2:
                symbol_str = channel_parts[-1]
                try:
                    return mapper.to_symbol(symbol_str)
                except Exception as e:
                    if logger:
                        logger.debug(f"Failed to convert symbol '{symbol_str}' from channel '{channel}': {e}")
        
        return None
    
    @staticmethod
    def _safe_json_decode(raw_message: str, logger: logging.Logger = None) -> Optional[Dict[str, Any]]:
        """Safely decode JSON message with error handling."""
        try:
            return msgspec.json.decode(raw_message)
        except (msgspec.DecodeError, ValueError) as e:
            if logger:
                logger.error(f"Failed to decode JSON message: {e}")
                logger.debug(f"Raw message: {raw_message[:200]}...")
            return None
    
    @staticmethod
    def _log_parsing_context(
        logger: logging.Logger,
        exchange: str,
        message_type: str,
        raw_message: Any,
        max_length: int = 200
    ) -> None:
        """Log parsing context for debugging with length limit."""
        if logger.isEnabledFor(logging.DEBUG):
            message_str = str(raw_message)
            if len(message_str) > max_length:
                message_str = message_str[:max_length] + "..."
            logger.debug(f"Parsing {exchange} {message_type}: {message_str}")

    def __init__(self, mapper: BaseExchangeMapper, logger):
        super().__init__(mapper, logger)
        self.mapper = mapper

    async def parse_message(self, raw_message: str) -> Optional[ParsedMessage]:
        """Parse raw WebSocket message from Gate.io."""
        try:
            # Safely decode JSON message
            message = self._safe_json_decode(raw_message, self.logger)
            if not message:
                return None
            
            # Log parsing context for debugging
            self._log_parsing_context(
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
                    return self._create_heartbeat_response(message)
                else:
                    # Other message types or messages without event field
                    self.logger.debug(f"Unknown Gate.io message format: {message}")
                    return ParsedMessage(
                        message_type=MessageType.UNKNOWN,
                        raw_data=message
                    )
            
            return None
            
        except Exception as e:
            return self.error_handler.handle_parsing_exception(
                exception=e,
                context="Gate.io message parsing",
                raw_data={"raw_message": raw_message}
            )

    async def _parse_subscription_response(self, message: Dict[str, Any]) -> ParsedMessage:
        """Parse Gate.io subscription response."""
        # Get channel name from message
        channel = message.get("channel", "")
        
        # Check for errors first using unified error handler
        error = message.get("error")
        if error:
            return self.error_handler.handle_subscription_error(message, channel)
        
        # Check result status
        result = message.get("result", {})
        status = result.get("status")
        is_success = self.mapper.is_subscription_successful(status)
        
        if is_success:
            self.logger.debug(f"Gate.io subscription successful for channel: {channel}")
            return self.create_subscription_response(
                channel=channel,
                status="success",
                raw_data=message
            )
        elif status == "fail":
            return self.error_handler.handle_subscription_error(message, channel)
        else:
            self.logger.warning(f"Unknown Gate.io subscription status: {status}")
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                channel=channel,
                raw_data=message
            )

    async def _parse_update_message(self, message: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io update message."""
        # Gate.io update format: {"event": "update", "channel": "spot.book_ticker", "result": {...}}
        channel = message.get("channel", "")
        result_data = message.get("result", {})
        
        if not channel or not result_data:
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                raw_data=message
            )
        
        if "order_book_update" in channel:
            return await self._parse_orderbook_update(channel, result_data)
        elif "trades" in channel:
            return await self._parse_trades_update(channel, result_data)
        elif "book_ticker" in channel:
            return await self._parse_book_ticker_update(channel, result_data)
        else:
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                channel=channel,
                raw_data={"channel": channel, "data": result_data}
            )

    async def _parse_orderbook_update(self, channel: str, data: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io orderbook update."""
        try:
            # Extract symbol from data
            symbol = self._safe_extract_symbol(
                data, self.mapper, ['s', 'symbol'], channel, self.logger
            )
            
            if not symbol:
                self.logger.error(f"No symbol found in orderbook data: {data}")
                return ParsedMessage(
                    message_type=MessageType.ERROR,
                    channel=channel,
                    raw_data={"error": "No symbol in orderbook data", "data": data}
                )
            
            # Use mapper for transformation  
            symbol_str = data.get('s', '') or channel.split('.')[-1] if '.' in channel else ''
            orderbook = self.mapper.ws_to_orderbook(data, symbol_str)
            
            return ParsedMessage(
                message_type=MessageType.ORDERBOOK,
                symbol=symbol,
                channel=channel,
                data=orderbook,
                raw_data=data
            )
            
        except Exception as e:
            return self.error_handler.handle_parsing_exception(
                exception=e,
                context="orderbook update",
                channel=channel,
                raw_data={"data": data}
            )

    async def _parse_trades_update(self, channel: str, data: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io trades update."""
        try:
            # Get symbol from data - Gate.io trades use 'currency_pair' field
            symbol_str = ""
            
            # If data is a list, check first trade for symbol
            if isinstance(data, list) and len(data) > 0:
                first_trade = data[0] if isinstance(data[0], dict) else {}
                symbol_str = first_trade.get('currency_pair', '') or first_trade.get('s', '')
            elif isinstance(data, dict):
                symbol_str = data.get('currency_pair', '') or data.get('s', '')
            
            if not symbol_str:
                # Fallback: extract from channel if it has symbol suffix  
                channel_parts = channel.split('.')
                if len(channel_parts) > 2:
                    symbol_str = channel_parts[-1]
                else:
                    self.logger.error(f"No symbol found in trades data: {data}")
                    return ParsedMessage(
                        message_type=MessageType.ERROR,
                        channel=channel,
                        raw_data={"error": "No symbol in trades data", "data": data}
                    )
            
            symbol = self.mapper.to_symbol(symbol_str)
            
            trades = []
            
            # Gate.io trades format is typically a list of trade objects
            trade_list = data if isinstance(data, list) else [data]
            
            for trade_data in trade_list:
                # Use mapper for transformation
                trade = self.mapper.ws_to_trade(trade_data, symbol_str)
                trades.append(trade)
            
            return ParsedMessage(
                message_type=MessageType.TRADE,
                symbol=trades[0].symbol if trades else None,
                channel=channel,
                data=trades,
                raw_data=data
            )
            
        except Exception as e:
            return self.error_handler.handle_parsing_exception(
                exception=e,
                context="trades update",
                channel=channel,
                raw_data={"data": data}
            )

    async def _parse_book_ticker_update(self, channel: str, data: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io book ticker update."""
        try:
            # Get symbol from data field 's' (symbol)
            symbol_str = data.get('s', '')
            if not symbol_str:
                # Fallback: extract from channel if not in data
                if '.' in channel:
                    symbol_str = channel.split('.')[-1]
            
            # Use mapper for transformation
            book_ticker = self.mapper.ws_to_book_ticker(data, symbol_str)
            
            return ParsedMessage(
                message_type=MessageType.BOOK_TICKER,
                symbol=book_ticker.symbol,
                channel=channel,
                data=book_ticker,
                raw_data=data
            )
            
        except Exception as e:
            return self.error_handler.handle_parsing_exception(
                exception=e,
                context="book ticker update",
                channel=channel,
                raw_data={"data": data}
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
        return self.create_subscription_response(
            channel=message.get("channel", ""),
            status=message.get("result", {}).get("status", "unknown"),
            raw_data=message
        )
    
    def _create_heartbeat_response(self, message: Dict[str, Any]) -> ParsedMessage:
        """Create heartbeat response message using base class method."""
        return self.create_heartbeat_response(message)
