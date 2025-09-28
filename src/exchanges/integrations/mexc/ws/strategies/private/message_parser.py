from typing import Optional, Dict, Any

import msgspec

from infrastructure.networking.websocket.strategies.message_parser import MessageParser
from infrastructure.networking.websocket.structs import ParsedMessage, MessageType
# Direct protobuf field parsing - no utility functions needed
from exchanges.integrations.mexc.ws.protobuf_parser import MexcProtobufParser
from exchanges.integrations.mexc.services.symbol_mapper import MexcSymbol
from exchanges.structs.common import Order, AssetBalance, Trade
from exchanges.structs import Side, OrderType, OrderStatus

# HFT Logger Integration
from infrastructure.logging import get_strategy_logger, HFTLoggerInterface
import time


class MexcPrivateMessageParser(MessageParser):
    """MEXC private WebSocket message parser."""

    def __init__(self, logger: Optional[HFTLoggerInterface] = None):
        super().__init__(logger)
        
        # Use injected logger or create strategy-specific logger
        if logger is None:
            tags = ['mexc', 'private', 'ws', 'message_parser']
            logger = get_strategy_logger('ws.message_parser.mexc.private', tags)
        
        self.logger = logger
        
        # Log initialization
        if self.logger:
            self.logger.info("MexcPrivateMessageParser initialized",
                            exchange="mexc",
                            api_type="private")
            
            # Track component initialization
            self.logger.metric("mexc_private_message_parsers_initialized", 1,
                              tags={"exchange": "mexc", "api_type": "private"})

    async def parse_message(self, raw_message: str) -> Optional[ParsedMessage]:
        """Parse MEXC private WebSocket message.

        MEXC private WebSocket can send both JSON and Protocol Buffer messages.
        """
        try:
            # First, log the raw message for debugging
            if self.logger:
                preview = str(raw_message)[:200] + "..." if len(str(raw_message)) > 200 else str(raw_message)
                self.logger.debug(f"Parsing private message: {preview}",
                                exchange="mexc",
                                message_type="private")

            # Check if it's bytes (protobuf) or string/dict (JSON)
            if isinstance(raw_message, bytes):
                # Handle protobuf message - simple approach
                return await self._parse_protobuf_message(raw_message)

            else:
                # Try to parse as JSON
                try:
                    if isinstance(raw_message, str):
                        message = msgspec.json.decode(raw_message)
                    else:
                        # If it's already a dict, use it directly
                        message = raw_message

                    message_type = self.get_message_type(message)

                    return ParsedMessage(
                        message_type=message_type,
                        channel=message.get('c'),
                        data=message.get('d'),
                        raw_data=message
                    )

                except (msgspec.DecodeError, ValueError) as e:
                    if self.logger:
                        self.logger.error(f"Failed to parse JSON message: {e}",
                                        exchange="mexc",
                                        error_type="json_parse_error")
                    return None

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error parsing private message: {e}",
                                exchange="mexc",
                                error_type="message_parse_error")
            return None

    async def _parse_protobuf_message(self, raw_message: bytes) -> Optional[ParsedMessage]:
        """Unified protobuf message parser for MEXC private messages using MEXC structs."""
        try:
            # Use consolidated protobuf utilities
            wrapper = MexcProtobufParser.parse_wrapper_message(raw_message)

            # Determine message type and extract data
            channel = wrapper.channel if hasattr(wrapper, 'channel') else ""
            symbol = wrapper.symbol if hasattr(wrapper, 'symbol') else ""

            if "account" in channel:
                # Account/balance update - direct protobuf field parsing
                if wrapper.HasField('privateAccount'):
                    account_data = wrapper.privateAccount
                    
                    # Direct parsing from protobuf fields - account_data already has parsed fields
                    balance_amount = float(account_data.balanceAmount) if hasattr(account_data, 'balanceAmount') else 0.0
                    frozen_amount = float(account_data.frozenAmount) if hasattr(account_data, 'frozenAmount') else 0.0
                    
                    unified_balance = AssetBalance(
                        asset=account_data.vcoinName if hasattr(account_data, 'vcoinName') else "",
                        available=balance_amount,
                        locked=frozen_amount,
                    )
                    
                    return ParsedMessage(
                        message_type=MessageType.BALANCE,
                        channel=channel,
                        data=unified_balance,
                        raw_data={"channel": channel, "symbol": symbol, "type": "account"}
                    )

            elif "orders" in channel:
                # Order update - direct protobuf field parsing
                if wrapper.HasField('privateOrders'):
                    order_data = wrapper.privateOrders
                    
                    # Direct parsing from protobuf fields - order_data already has parsed fields
                    trade_type = getattr(order_data, 'tradeType', 0)
                    order_status = getattr(order_data, 'status', 0)
                    
                    # Map MEXC status codes to unified OrderStatus
                    if order_status == 1:
                        status = OrderStatus.NEW
                    elif order_status == 2:
                        status = OrderStatus.FILLED
                    elif order_status == 3:
                        status = OrderStatus.PARTIALLY_FILLED
                    elif order_status == 4:
                        status = OrderStatus.CANCELED
                    else:
                        status = OrderStatus.NEW  # Default
                    
                    unified_order = Order(
                        order_id=order_data.id if hasattr(order_data, 'id') else "",
                        symbol=MexcSymbol.to_symbol(symbol) if symbol else None,
                        side=Side.BUY if trade_type == 1 else Side.SELL,
                        order_type=OrderType.LIMIT,  # Default to LIMIT
                        quantity=float(order_data.quantity) if hasattr(order_data, 'quantity') else 0.0,
                        price=float(order_data.price) if hasattr(order_data, 'price') else 0.0,
                        filled_quantity=float(order_data.cumulativeQuantity) if hasattr(order_data, 'cumulativeQuantity') else 0.0,
                        status=status,
                        timestamp=int(getattr(order_data, 'time', 0)),
                        client_order_id=None
                    )
                    
                    return ParsedMessage(
                        message_type=MessageType.ORDER,
                        channel=channel,
                        data=unified_order,
                        raw_data={"channel": channel, "symbol": symbol, "type": "order"}
                    )

            elif "deals" in channel:
                # Trade/execution update - direct protobuf field parsing
                if wrapper.HasField('privateDeals'):
                    deal_data = wrapper.privateDeals
                    
                    # Direct parsing from protobuf fields - deal_data already has parsed fields
                    trade_type = getattr(deal_data, 'tradeType', 0)
                    
                    unified_trade = Trade(
                        symbol=MexcSymbol.to_symbol(symbol) if symbol else None,
                        price=float(deal_data.price) if hasattr(deal_data, 'price') else 0.0,
                        quantity=float(deal_data.quantity) if hasattr(deal_data, 'quantity') else 0.0,
                        timestamp=int(getattr(deal_data, 'time', 0)),
                        side=Side.BUY if trade_type == 1 else Side.SELL,
                        trade_id=str(getattr(deal_data, 'time', int(time.time() * 1000)))  # Use timestamp as trade ID
                    )
                    
                    return ParsedMessage(
                        message_type=MessageType.TRADE,
                        channel=channel,
                        data=unified_trade,
                        raw_data={"channel": channel, "symbol": symbol, "type": "deal"}
                    )

            # Fallback for unrecognized protobuf messages
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                channel=channel,
                data={"channel": channel, "symbol": symbol, "raw_bytes": len(raw_message)},
                raw_data={"channel": channel, "symbol": symbol, "type": "unknown_protobuf"}
            )

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error parsing protobuf message: {e}",
                                exchange="mexc",
                                error_type="protobuf_parse_error")
            # Return a basic unknown message so processing continues
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                channel="protobuf_error",
                data={"error": str(e), "raw_bytes": len(raw_message)},
                raw_data={"type": "protobuf_parse_error", "error": str(e)}
            )

    def get_message_type(self, message: Dict[str, Any]) -> MessageType:
        """Detect private message type."""
        channel = message.get('c', '')

        if 'account' in channel:
            return MessageType.BALANCE
        elif 'orders' in channel:
            return MessageType.ORDER
        elif 'ping' in message:
            return MessageType.HEARTBEAT

        return MessageType.UNKNOWN

