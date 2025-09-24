import logging
from typing import Optional, Dict, Any

import msgspec

from infrastructure.networking.websocket.strategies.message_parser import MessageParser
from infrastructure.networking.websocket.structs import ParsedMessage, MessageType
from core.exchanges.services import BaseExchangeMapper
from exchanges.mexc.ws.protobuf_parser import MexcProtobufParser
from exchanges.mexc.structs.exchange import (
    MexcWSPrivateOrderData, MexcWSPrivateBalanceData, MexcWSPrivateTradeData
)
from infrastructure.data_structures.common import OrderBook


class MexcPrivateMessageParser(MessageParser):
    """MEXC private WebSocket message parser."""

    def __init__(self, mapper: BaseExchangeMapper, logger):
        super().__init__(mapper, logger)
        self.mexc_mapper = mapper  # Use the injected mapper directly

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
        """Unified protobuf message parser for MEXC private messages using MEXC structs."""
        try:
            # Use consolidated protobuf utilities
            wrapper = MexcProtobufParser.parse_wrapper_message(raw_message)

            # Determine message type and extract data
            channel = wrapper.channel if hasattr(wrapper, 'channel') else ""
            symbol = wrapper.symbol if hasattr(wrapper, 'symbol') else ""

            if "account" in channel:
                # Account/balance update - create MEXC struct then convert to unified
                if wrapper.HasField('privateAccount'):
                    account_data = wrapper.privateAccount
                    # Create MEXC-specific balance data struct
                    mexc_balance = MexcWSPrivateBalanceData(
                        asset=account_data.vcoinName if hasattr(account_data, 'vcoinName') else "",
                        free=str(float(account_data.balanceAmount) - float(account_data.frozenAmount)) if hasattr(account_data, 'balanceAmount') and hasattr(account_data, 'frozenAmount') else "0.0",
                        locked=str(account_data.frozenAmount) if hasattr(account_data, 'frozenAmount') else "0.0",
                        total=str(account_data.balanceAmount) if hasattr(account_data, 'balanceAmount') else "0.0"
                    )
                    
                    # Use mapper to convert MEXC struct to unified AssetBalance
                    unified_balance = self.mexc_mapper.ws_to_balance(mexc_balance)
                    
                    return ParsedMessage(
                        message_type=MessageType.BALANCE,
                        channel=channel,
                        data=unified_balance,  # Return unified type
                        raw_data={"channel": channel, "symbol": symbol, "type": "account"}
                    )

            elif "orders" in channel:
                # Order update - create MEXC struct then convert to unified
                if wrapper.HasField('privateOrders'):
                    order_data = wrapper.privateOrders
                    # Create MEXC-specific order data struct
                    mexc_order = MexcWSPrivateOrderData(
                        order_id=order_data.id if hasattr(order_data, 'id') else "",
                        symbol=symbol,
                        side="BUY" if getattr(order_data, 'tradeType', 0) == 1 else "SELL",
                        status=getattr(order_data, 'status', 0),
                        orderType=1,  # Default to LIMIT if not available
                        price=str(order_data.price) if hasattr(order_data, 'price') else "0.0",
                        quantity=str(order_data.quantity) if hasattr(order_data, 'quantity') else "0.0",
                        filled_qty=str(order_data.cumulativeQuantity) if hasattr(order_data, 'cumulativeQuantity') else "0.0",
                        updateTime=int(getattr(order_data, 'time', 0))
                    )
                    
                    # Use mapper to convert MEXC struct to unified Order
                    unified_order = self.mexc_mapper.ws_to_order(mexc_order)
                    
                    return ParsedMessage(
                        message_type=MessageType.ORDER,
                        channel=channel,
                        data=unified_order,  # Return unified type
                        raw_data={"channel": channel, "symbol": symbol, "type": "order"}
                    )

            elif "deals" in channel:
                # Trade/execution update - create MEXC struct then convert to unified
                if wrapper.HasField('privateDeals'):
                    deal_data = wrapper.privateDeals
                    # Create MEXC-specific trade data struct
                    mexc_trade = MexcWSPrivateTradeData(
                        symbol=symbol,
                        side="BUY" if getattr(deal_data, 'tradeType', 0) == 1 else "SELL",
                        price=str(deal_data.price) if hasattr(deal_data, 'price') else "0.0",
                        quantity=str(deal_data.quantity) if hasattr(deal_data, 'quantity') else "0.0",
                        timestamp=int(getattr(deal_data, 'time', 0)),
                        is_maker=getattr(deal_data, 'isMaker', False)
                    )
                    
                    # Use mapper to convert MEXC struct to unified Trade
                    unified_trade = self.mexc_mapper.ws_to_trade(mexc_trade, symbol)
                    
                    return ParsedMessage(
                        message_type=MessageType.TRADE,
                        channel=channel,
                        data=unified_trade,  # Return unified type
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

