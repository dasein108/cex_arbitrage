import msgspec
from typing import Dict, Any, List, Optional

from infrastructure.networking.websocket.strategies.message_parser import MessageParser
from exchanges.structs.common import (
    Symbol, Order, Trade, AssetBalance
)
from infrastructure.networking.websocket.structs import ParsedMessage, MessageType

# HFT Logger Integration
from infrastructure.logging import get_strategy_logger, HFTLoggerInterface


class GateioPrivateFuturesMessageParser(MessageParser):
    """Gate.io private futures WebSocket message parser."""

    def __init__(self, logger: Optional[HFTLoggerInterface] = None):
        super().__init__(logger)
        
        # Use injected logger or create strategy-specific logger
        if logger is None:
            tags = ['gateio', 'futures', 'private', 'ws', 'message_parser']
            logger = get_strategy_logger('ws.message_parser.gateio.futures.private', tags)
        
        self.logger = logger
        
        # Log initialization
        if self.logger:
            self.logger.info("GateioPrivateFuturesMessageParser initialized",
                            exchange="gateio",
                            api_type="futures_private")
            
            # Track component initialization
            self.logger.metric("gateio_futures_private_message_parsers_initialized", 1,
                              tags={"exchange": "gateio", "api_type": "futures_private"})

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
                from exchanges.integrations.gateio.utils import futures_ws_to_order
                order = futures_ws_to_order(order_data)
                if order:
                    orders.append(order)
            
            if orders:
                return ParsedMessage(
                    message_type=MessageType.ORDER,
                    symbol=orders[0].symbol,  # Use first order's symbol
                    data=orders[0] if len(orders) == 1 else orders,
                    timestamp=message.get("time", 0),
                    raw_data=message
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
            
            # Parse balances using mapper
            balances = {}
            for balance_data in result:
                from exchanges.integrations.gateio.utils import futures_ws_to_balance
                balance = futures_ws_to_balance(balance_data)
                if balance and balance.asset:
                    balances[balance.asset] = balance
            
            if balances:
                return ParsedMessage(
                    message_type=MessageType.BALANCE,
                    symbol=None,  # Balance updates are not symbol-specific
                    data=balances,
                    timestamp=message.get("time", 0),
                    raw_data=message
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
            
            # Parse trades using mapper
            trades = []
            for trade_data in result:
                from exchanges.integrations.gateio.utils import futures_ws_to_trade
                trade = futures_ws_to_trade(trade_data)
                if trade:
                    trades.append(trade)
            
            if trades:
                return ParsedMessage(
                    message_type=MessageType.TRADE,
                    symbol=trades[0].symbol,  # Use first trade's symbol
                    data=trades[0] if len(trades) == 1 else trades,
                    timestamp=message.get("time", 0),
                    raw_data=message
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
                from exchanges.integrations.gateio.utils import to_futures_symbol
                symbol = to_futures_symbol(position_data.get("contract", ""))
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
                    raw_data=message
                )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to parse Gate.io private futures position message: {e}")
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