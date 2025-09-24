import logging
import msgspec
from typing import Dict, Any, List, Optional
from decimal import Decimal

from infrastructure.networking.websocket.strategies.message_parser import MessageParser
from exchanges.services import BaseExchangeMapper
from infrastructure.data_structures.common import (
    Symbol, Order, Trade, AssetBalance, AssetName,
    OrderStatus, OrderType, OrderSide, Side
)
from infrastructure.networking.websocket.structs import ParsedMessage, MessageType


class GateioPrivateFuturesMessageParser(MessageParser):
    """Gate.io private futures WebSocket message parser."""

    def __init__(self, mapper: BaseExchangeMapper, logger):
        super().__init__(mapper, logger)

    async def parse_message(self, raw_message: str) -> Optional[ParsedMessage]:
        """Parse Gate.io private futures WebSocket message."""
        try:
            # Parse JSON message
            message = msgspec.json.decode(raw_message)
            
            # Skip ping/pong and subscription confirmations
            if self._is_system_message(message):
                return None
            
            # Route message by channel
            channel = message.get("channel", "")
            
            if channel == "futures.orders":
                return await self._parse_order_message(message)
            elif channel == "futures.balances":
                return await self._parse_balance_message(message)
            elif channel == "futures.usertrades":
                return await self._parse_trade_message(message)
            elif channel == "futures.positions":
                return await self._parse_position_message(message)
            else:
                self.logger.debug(f"Unknown Gate.io private futures channel: {channel}")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to parse Gate.io private futures message: {e}")
            return None

    def _is_system_message(self, message: Dict[str, Any]) -> bool:
        """Check if message is a system message (ping/pong, subscriptions, etc.)."""
        event = message.get("event", "")
        channel = message.get("channel", "")
        
        # System events
        if event in ["ping", "pong", "subscribe", "unsubscribe"]:
            return True
        
        # System channels
        if channel in ["futures.ping", "futures.login"]:
            return True
        
        return False

    async def _parse_order_message(self, message: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io private futures order update message."""
        try:
            result = message.get("result", [])
            if not result:
                return None
            
            # Gate.io sends order updates as array
            orders = []
            for order_data in result:
                order = self._create_order_from_data(order_data)
                if order:
                    orders.append(order)
            
            if orders:
                return ParsedMessage(
                    message_type=MessageType.ORDER,
                    symbol=orders[0].symbol,  # Use first order's symbol
                    data=orders[0] if len(orders) == 1 else orders,
                    timestamp=message.get("time", 0),
                    raw_message=message
                )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to parse Gate.io private futures order message: {e}")
            return None

    async def _parse_balance_message(self, message: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io private futures balance update message."""
        try:
            result = message.get("result", [])
            if not result:
                return None
            
            # Parse balances
            balances = {}
            for balance_data in result:
                asset_name = AssetName(balance_data.get("currency", ""))
                if not asset_name:
                    continue
                
                balance = AssetBalance(
                    asset=asset_name,
                    free=float(balance_data.get("available", 0)),
                    locked=float(balance_data.get("freeze", 0)),
                    total=float(balance_data.get("total", 0))
                )
                balances[asset_name] = balance
            
            if balances:
                return ParsedMessage(
                    message_type=MessageType.BALANCE,
                    symbol=None,  # Balance updates are not symbol-specific
                    data=balances,
                    timestamp=message.get("time", 0),
                    raw_message=message
                )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to parse Gate.io private futures balance message: {e}")
            return None

    async def _parse_trade_message(self, message: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io private futures user trade message."""
        try:
            result = message.get("result", [])
            if not result:
                return None
            
            # Parse trades
            trades = []
            for trade_data in result:
                trade = self._create_trade_from_data(trade_data)
                if trade:
                    trades.append(trade)
            
            if trades:
                return ParsedMessage(
                    message_type=MessageType.TRADE,
                    symbol=trades[0].symbol,  # Use first trade's symbol
                    data=trades[0] if len(trades) == 1 else trades,
                    timestamp=message.get("time", 0),
                    raw_message=message
                )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to parse Gate.io private futures trade message: {e}")
            return None

    async def _parse_position_message(self, message: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io private futures position update message."""
        try:
            result = message.get("result", [])
            if not result:
                return None
            
            # Parse positions (custom message type for futures)
            positions = []
            for position_data in result:
                symbol = self._parse_symbol_from_contract(position_data.get("contract", ""))
                if symbol:
                    positions.append({
                        "symbol": symbol,
                        "size": float(position_data.get("size", 0)),
                        "side": position_data.get("mode", "unknown"),
                        "unrealized_pnl": float(position_data.get("unrealised_pnl", 0)),
                        "margin": float(position_data.get("margin", 0)),
                        "leverage": float(position_data.get("leverage", 1)),
                        "entry_price": float(position_data.get("entry_price", 0)),
                        "mark_price": float(position_data.get("mark_price", 0))
                    })
            
            if positions:
                # Use custom message type for positions
                return ParsedMessage(
                    message_type=MessageType.HEARTBEAT,  # Reuse heartbeat type for positions
                    symbol=positions[0]["symbol"],
                    data=positions[0] if len(positions) == 1 else positions,
                    timestamp=message.get("time", 0),
                    raw_message=message
                )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to parse Gate.io private futures position message: {e}")
            return None

    def _create_order_from_data(self, order_data: Dict[str, Any]) -> Optional[Order]:
        """Create Order object from Gate.io private futures order data."""
        try:
            # Parse symbol from contract
            symbol = self._parse_symbol_from_contract(order_data.get("contract", ""))
            if not symbol:
                return None
            
            # Map Gate.io order status to our enum
            status_map = {
                "open": OrderStatus.NEW,
                "finished": OrderStatus.FILLED,
                "cancelled": OrderStatus.CANCELED
            }
            
            # Map Gate.io order type
            type_map = {
                "limit": OrderType.LIMIT,
                "market": OrderType.MARKET
            }
            
            # Map Gate.io order side
            side = OrderSide.BUY if order_data.get("size", 0) > 0 else OrderSide.SELL
            
            order = Order(
                symbol=symbol,
                order_id=str(order_data.get("id", "")),
                side=side,
                order_type=type_map.get(order_data.get("type", ""), OrderType.LIMIT),
                quantity=abs(float(order_data.get("size", 0))),
                price=float(order_data.get("price", 0)),
                filled_quantity=abs(float(order_data.get("filled", 0))),
                status=status_map.get(order_data.get("status", ""), OrderStatus.UNKNOWN),
                timestamp=int(order_data.get("create_time", 0))
            )
            
            return order
            
        except Exception as e:
            self.logger.error(f"Failed to create order from Gate.io private futures data: {e}")
            return None

    def _create_trade_from_data(self, trade_data: Dict[str, Any]) -> Optional[Trade]:
        """Create Trade object from Gate.io private futures trade data."""
        try:
            # Parse symbol from contract
            symbol = self._parse_symbol_from_contract(trade_data.get("contract", ""))
            if not symbol:
                return None
            
            # Map Gate.io trade side
            side = Side.BUY if trade_data.get("size", 0) > 0 else Side.SELL
            
            trade = Trade(
                symbol=symbol,
                side=side,
                quantity=abs(float(trade_data.get("size", 0))),
                price=float(trade_data.get("price", 0)),
                timestamp=int(trade_data.get("create_time", 0)),
                trade_id=str(trade_data.get("id", "")),
                order_id=str(trade_data.get("order_id", "")),
                is_maker=trade_data.get("role", "") == "maker"
            )
            
            return trade
            
        except Exception as e:
            self.logger.error(f"Failed to create trade from Gate.io private futures data: {e}")
            return None

    def _parse_symbol_from_contract(self, contract: str) -> Optional[Symbol]:
        """Parse symbol from Gate.io futures contract string."""
        try:
            if not contract or "_" not in contract:
                return None
            
            # Gate.io futures contracts are in format "BTC_USDT"
            parts = contract.split("_")
            if len(parts) >= 2:
                base = parts[0]
                quote = parts[1]
                return Symbol(base=AssetName(base), quote=AssetName(quote), is_futures=True)
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Could not parse symbol from contract {contract}: {e}")
            return None

    def format_message_for_logging(self, message: Dict[str, Any]) -> str:
        """Format message for logging (remove sensitive data)."""
        # Create a copy for logging without sensitive information
        safe_message = message.copy()
        
        # Remove any sensitive authentication data
        if "payload" in safe_message and isinstance(safe_message["payload"], dict):
            payload = safe_message["payload"].copy()
            if "api_key" in payload:
                payload["api_key"] = "***"
            if "signature" in payload:
                payload["signature"] = "***"
            safe_message["payload"] = payload
        
        return msgspec.json.encode(safe_message).decode()

    def get_supported_channels(self) -> List[str]:
        """Get list of supported Gate.io private futures channels."""
        return [
            "futures.orders",
            "futures.balances", 
            "futures.usertrades",
            "futures.positions"
        ]

    def is_error_message(self, message: Dict[str, Any]) -> bool:
        """Check if message contains an error."""
        return "error" in message and message["error"] is not None

    def get_error_info(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract error information from message."""
        error = message.get("error")
        if error:
            return {
                "code": error.get("code", "unknown"),
                "message": error.get("message", "Unknown error"),
                "channel": message.get("channel", "unknown")
            }
        return None

    def get_message_type(self, message: Dict[str, Any]) -> MessageType:
        """Detect Gate.io private futures message type from JSON structure."""
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
            if channel == "futures.orders":
                return MessageType.ORDER
            elif channel == "futures.balances":
                return MessageType.BALANCE
            elif channel == "futures.usertrades":
                return MessageType.TRADE
            elif channel == "futures.positions":
                return MessageType.HEARTBEAT  # Reusing heartbeat type for positions
            return MessageType.UNKNOWN
        else:
            return MessageType.UNKNOWN