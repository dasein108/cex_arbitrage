import logging
from typing import Optional, Dict, Any

import msgspec

from core.cex.websocket import MessageParser, ParsedMessage, MessageType
from cex.mexc.ws.protobuf_parser import MexcProtobufParser
from structs.exchange import OrderBook


class MexcPrivateMessageParser(MessageParser):
    """MEXC private WebSocket message parser."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def parse_message(self, raw_message: str) -> Optional[ParsedMessage]:
        """Parse MEXC private WebSocket message.

        MEXC private WebSocket can send both JSON and Protocol Buffer messages.
        """
        try:
            # First, log the raw message for debugging
            if self.logger.isEnabledFor(logging.DEBUG):
                preview = str(raw_message)[:200] + "..." if len(str(raw_message)) > 200 else str(raw_message)
                self.logger.debug(f"Parsing private message: {preview}")

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
                    self.logger.error(f"Failed to parse JSON message: {e}")
                    return None

        except Exception as e:
            self.logger.error(f"Error parsing private message: {e}")
            return None

    async def _parse_protobuf_message(self, raw_message: bytes) -> Optional[ParsedMessage]:
        """Unified protobuf message parser for MEXC private messages."""
        try:
            # Use consolidated protobuf utilities
            wrapper = MexcProtobufParser.parse_wrapper_message(raw_message)

            # Determine message type and extract data
            channel = wrapper.channel if hasattr(wrapper, 'channel') else ""
            symbol = wrapper.symbol if hasattr(wrapper, 'symbol') else ""

            if "account" in channel:
                # Account/balance update
                if wrapper.HasField('privateAccount'):
                    account_data = wrapper.privateAccount
                    return ParsedMessage(
                        message_type=MessageType.BALANCE,
                        channel=channel,
                        data={
                            "asset": account_data.vcoinName if hasattr(account_data, 'vcoinName') else "",
                            "free": float(account_data.balanceAmount) - float(account_data.frozenAmount) if hasattr(account_data, 'balanceAmount') and hasattr(account_data, 'frozenAmount') else 0.0,
                            "locked": float(account_data.frozenAmount) if hasattr(account_data, 'frozenAmount') else 0.0,
                            "symbol": symbol
                        },
                        raw_data={"channel": channel, "symbol": symbol, "type": "account"}
                    )

            elif "orders" in channel:
                # Order update
                if wrapper.HasField('privateOrders'):
                    order_data = wrapper.privateOrders
                    return ParsedMessage(
                        message_type=MessageType.ORDER,
                        channel=channel,
                        data={
                            "order_id": order_data.id if hasattr(order_data, 'id') else "",
                            "symbol": symbol,
                            "side": "BUY" if getattr(order_data, 'tradeType', 0) == 1 else "SELL",
                            "status": getattr(order_data, 'status', 0),
                            "price": float(order_data.price) if hasattr(order_data, 'price') else 0.0,
                            "quantity": float(order_data.quantity) if hasattr(order_data, 'quantity') else 0.0,
                            "filled_qty": float(order_data.cumulativeQuantity) if hasattr(order_data, 'cumulativeQuantity') else 0.0
                        },
                        raw_data={"channel": channel, "symbol": symbol, "type": "order"}
                    )

            elif "deals" in channel:
                # Trade/execution update
                if wrapper.HasField('privateDeals'):
                    deal_data = wrapper.privateDeals
                    return ParsedMessage(
                        message_type=MessageType.TRADE,
                        channel=channel,
                        data={
                            "symbol": symbol,
                            "side": "BUY" if getattr(deal_data, 'tradeType', 0) == 1 else "SELL",
                            "price": float(deal_data.price) if hasattr(deal_data, 'price') else 0.0,
                            "quantity": float(deal_data.quantity) if hasattr(deal_data, 'quantity') else 0.0,
                            "timestamp": getattr(deal_data, 'time', 0),
                            "is_maker": getattr(deal_data, 'isMaker', False)
                        },
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
            self.logger.error(f"Error parsing protobuf message: {e}")
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

    async def parse_orderbook_message(
        self,
        message: Dict[str, Any]
    ) -> Optional[OrderBook]:
        """Private messages don't contain orderbook data."""
        return None

    def supports_batch_parsing(self) -> bool:
        """Private parser supports batch processing."""
        return True
