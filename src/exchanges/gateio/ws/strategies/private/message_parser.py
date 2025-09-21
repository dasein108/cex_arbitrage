import logging
from typing import Dict, Any, Optional, List

from core.exchanges.websocket import MessageParser, ParsedMessage
from core.exchanges.services.unified_mapper.exchange_mappings import ExchangeMappingsInterface
from core.transport.websocket.structs import MessageType
from structs.common import Order, AssetBalance, AssetName, Trade, Symbol, Side, OrderStatus, OrderType


class GateioPrivateMessageParser(MessageParser):
    """Gate.io private WebSocket message parser."""

    def __init__(self, mapper: ExchangeMappingsInterface):
        super().__init__(mapper)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.mapper = mapper
        # Maintain backward compatibility
        self.symbol_mapper = mapper._symbol_mapper if mapper else None

    async def parse_message(self, raw_message: str) -> Optional[ParsedMessage]:
        """Parse raw WebSocket message from Gate.io private channels."""
        try:
            import msgspec
            message = msgspec.json.decode(raw_message)
            
            if isinstance(message, dict):
                event = message.get("event")
                
                if event == "subscribe":
                    # Subscription confirmation/error
                    return await self._parse_subscription_response(message)
                elif event == "unsubscribe":
                    # Unsubscription confirmation
                    return ParsedMessage(
                        message_type=MessageType.SUBSCRIPTION_CONFIRM,
                        data={"action": "unsubscribe", "status": message.get("result", {}).get("status")},
                        raw_data=message
                    )
                elif event == "update":
                    # Data update message
                    return await self._parse_update_message(message)
                elif event in ["ping", "pong"]:
                    # Ping/pong messages
                    return ParsedMessage(
                        message_type=MessageType.HEARTBEAT,
                        raw_data=message
                    )
                else:
                    # Handle messages without event field or unknown events
                    # Could be authentication responses or other formats
                    method = message.get("method")
                    if method == "RESULT":
                        # Authentication result or other results
                        return ParsedMessage(
                            message_type=MessageType.SUBSCRIPTION_CONFIRM,
                            raw_data=message
                        )
                    else:
                        self.logger.debug(f"Unknown Gate.io private message format: {message}")
                        return ParsedMessage(
                            message_type=MessageType.UNKNOWN,
                            raw_data=message
                        )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to parse Gate.io private message: {e}")
            return None

    async def _parse_subscription_response(self, message: Dict[str, Any]) -> ParsedMessage:
        """Parse Gate.io private subscription response."""
        # Get channel name from message
        channel = message.get("channel", "")
        
        # Check for errors first
        error = message.get("error")
        if error:
            error_code = error.get("code", "unknown")
            error_msg = error.get("message", "unknown error")
            self.logger.error(f"Gate.io private subscription error {error_code}: {error_msg}")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                channel=channel,
                data={"error_code": error_code, "error_message": error_msg},
                raw_data=message
            )
        
        # Check result status
        result = message.get("result", {})
        status = result.get("status")
        
        if status == "success":
            self.logger.debug(f"Gate.io private subscription successful for channel: {channel}")
            return ParsedMessage(
                message_type=MessageType.SUBSCRIPTION_CONFIRM,
                channel=channel,
                data={"action": "subscribe", "status": "success"},
                raw_data=message
            )
        elif status == "fail":
            self.logger.error(f"Gate.io private subscription failed for channel: {channel}")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                channel=channel,
                data={"action": "subscribe", "status": "fail"},
                raw_data=message
            )
        else:
            self.logger.warning(f"Unknown Gate.io private subscription status: {status}")
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                channel=channel,
                raw_data=message
            )

    async def _parse_update_message(self, message: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse Gate.io private update message."""
        # Gate.io private update format: {"event": "update", "channel": "spot.balances", "result": [...]}
        channel = message.get("channel", "")
        result_data = message.get("result", [])
        
        if not channel:
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                raw_data=message
            )
        
        if channel == "spot.balances":
            return await self._parse_balance_update(result_data)
        elif channel == "spot.orders":
            return await self._parse_order_update(result_data)
        elif channel == "spot.user_trades":
            return await self._parse_user_trade_update(result_data)
        else:
            return ParsedMessage(
                message_type=MessageType.UNKNOWN,
                channel=channel,
                raw_data={"channel": channel, "data": result_data}
            )

    async def _parse_balance_update(self, data: List[Dict[str, Any]]) -> Optional[ParsedMessage]:
        """Parse Gate.io balance update."""
        try:
            balances = {}
            
            # Gate.io balance update format:
            # [
            #   {
            #     "currency": "USDT",
            #     "available": "1000.0",
            #     "locked": "0.0"
            #   }, ...
            # ]
            
            balance_list = data if isinstance(data, list) else [data]
            
            for balance_data in balance_list:
                asset = AssetName(balance_data.get("currency", ""))
                available = float(balance_data.get("available", "0"))
                locked = float(balance_data.get("locked", "0"))
                
                balance = AssetBalance(
                    asset=asset,
                    free=available,
                    locked=locked
                )
                balances[asset] = balance
            
            return ParsedMessage(
                message_type=MessageType.BALANCE,
                data=balances,
                raw_data=data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to parse balance update: {e}")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                raw_data={"error": str(e), "data": data}
            )

    async def _parse_order_update(self, data: List[Dict[str, Any]]) -> Optional[ParsedMessage]:
        """Parse Gate.io order update."""
        try:
            orders = []
            
            # Gate.io order update format similar to REST API
            order_list = data if isinstance(data, list) else [data]
            
            for order_data in order_list:
                symbol_str = order_data.get("currency_pair", "")
                symbol = self.symbol_mapper.to_symbol(symbol_str)
                
                # Map Gate.io status to unified status
                status_map = {
                    "open": OrderStatus.NEW,
                    "closed": OrderStatus.FILLED,
                    "cancelled": OrderStatus.CANCELED
                }
                status = status_map.get(order_data.get("status", ""), OrderStatus.UNKNOWN)
                
                # Map side
                side = Side.BUY if order_data.get("side") == "buy" else Side.SELL
                
                # Map order type
                order_type = OrderType.LIMIT if order_data.get("type") == "limit" else OrderType.MARKET
                
                order = Order(
                    order_id=str(order_data.get("id", "")),
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    quantity=float(order_data.get("amount", "0")),
                    price=float(order_data.get("price", "0")) if order_data.get("price") else None,
                    filled_quantity=float(order_data.get("filled_amount", "0")),
                    status=status,
                    timestamp=int(float(order_data.get("create_time", "0")) * 1000)
                )
                orders.append(order)
            
            return ParsedMessage(
                message_type=MessageType.ORDER,
                data=orders,
                raw_data=data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to parse order update: {e}")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                raw_data={"error": str(e), "data": data}
            )

    async def _parse_user_trade_update(self, data: List[Dict[str, Any]]) -> Optional[ParsedMessage]:
        """Parse Gate.io user trade update."""
        try:
            trades = []
            
            # Gate.io user trade format
            trade_list = data if isinstance(data, list) else [data]
            
            for trade_data in trade_list:
                symbol_str = trade_data.get("currency_pair", "")
                symbol = self.symbol_mapper.to_symbol(symbol_str)
                
                side = Side.BUY if trade_data.get("side") == "buy" else Side.SELL
                
                trade = Trade(
                    symbol=symbol,
                    price=float(trade_data.get("price", "0")),
                    quantity=float(trade_data.get("amount", "0")),
                    quote_quantity=float(trade_data.get("price", "0")) * float(trade_data.get("amount", "0")),
                    side=side,
                    timestamp=int(float(trade_data.get("create_time", "0")) * 1000),
                    trade_id=str(trade_data.get("id", "")),
                    is_maker=trade_data.get("role") == "maker",
                    order_id=str(trade_data.get("order_id", ""))
                )
                trades.append(trade)
            
            return ParsedMessage(
                message_type=MessageType.TRADE,
                data=trades,
                raw_data=data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to parse user trade update: {e}")
            return ParsedMessage(
                message_type=MessageType.ERROR,
                raw_data={"error": str(e), "data": data}
            )

    def get_supported_message_types(self) -> List[str]:
        """Get list of supported message types."""
        return ["balance_update", "order_update", "user_trade", "subscription", "result", "ping_pong", "other", "error"]