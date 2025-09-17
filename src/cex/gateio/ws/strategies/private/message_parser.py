import logging
from typing import Dict, Any, Optional, List

from core.cex.websocket import MessageParser
from core.cex.services import SymbolMapperInterface
from structs.exchange import Order, AssetBalance, AssetName, Trade, Symbol, Side, OrderStatus, OrderType


class GateioPrivateMessageParser(MessageParser):
    """Gate.io private WebSocket message parser."""

    def __init__(self, symbol_mapper: SymbolMapperInterface):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.symbol_mapper = symbol_mapper

    async def parse_message(self, raw_message: str) -> Optional[Dict[str, Any]]:
        """Parse raw WebSocket message from Gate.io private channels."""
        try:
            import msgspec
            message = msgspec.json.decode(raw_message)
            
            if isinstance(message, dict):
                method = message.get("method")
                
                if method == "SUBSCRIBE":
                    # Subscription confirmation
                    return {"type": "subscription", "data": message}
                elif method == "UPDATE":
                    # Data update message
                    return await self._parse_update_message(message)
                elif method in ["PING", "PONG"]:
                    # Ping/pong messages
                    return {"type": "ping_pong", "data": message}
                elif method == "RESULT":
                    # Authentication result or other results
                    return {"type": "result", "data": message}
                else:
                    return {"type": "other", "data": message}
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to parse Gate.io private message: {e}")
            return None

    async def _parse_update_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Gate.io private update message."""
        params = message.get("params", [])
        if len(params) < 2:
            return {"type": "unknown", "data": message}
        
        channel = params[0]
        update_data = params[1]
        
        if channel == "spot.balances":
            return await self._parse_balance_update(update_data)
        elif channel == "spot.orders":
            return await self._parse_order_update(update_data)
        elif channel == "spot.user_trades":
            return await self._parse_user_trade_update(update_data)
        else:
            return {"type": "unknown", "channel": channel, "data": update_data}

    async def _parse_balance_update(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse Gate.io balance update."""
        try:
            balances = []
            
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
                    available=available,
                    free=available,
                    locked=locked
                )
                balances.append(balance)
            
            return {
                "type": "balance_update",
                "balances": balances
            }
            
        except Exception as e:
            self.logger.error(f"Failed to parse balance update: {e}")
            return {"type": "error", "error": str(e), "data": data}

    async def _parse_order_update(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
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
                    amount=float(order_data.get("amount", "0")),
                    price=float(order_data.get("price", "0")) if order_data.get("price") else None,
                    amount_filled=float(order_data.get("filled_amount", "0")),
                    status=status,
                    timestamp=int(float(order_data.get("create_time", "0")) * 1000)
                )
                orders.append(order)
            
            return {
                "type": "order_update",
                "orders": orders
            }
            
        except Exception as e:
            self.logger.error(f"Failed to parse order update: {e}")
            return {"type": "error", "error": str(e), "data": data}

    async def _parse_user_trade_update(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
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
                    amount=float(trade_data.get("amount", "0")),
                    side=side,
                    timestamp=int(float(trade_data.get("create_time", "0")) * 1000),
                    trade_id=str(trade_data.get("id", "")),
                    is_maker=trade_data.get("role") == "maker",
                    order_id=str(trade_data.get("order_id", ""))
                )
                trades.append(trade)
            
            return {
                "type": "user_trade",
                "trades": trades
            }
            
        except Exception as e:
            self.logger.error(f"Failed to parse user trade update: {e}")
            return {"type": "error", "error": str(e), "data": data}

    def get_supported_message_types(self) -> List[str]:
        """Get list of supported message types."""
        return ["balance_update", "order_update", "user_trade", "subscription", "result", "ping_pong", "other", "error"]