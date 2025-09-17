import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from core.cex.websocket import MessageParser
from core.cex.services import SymbolMapperInterface
from structs.exchange import Trade, OrderBookEntry, Symbol, Side


class GateioPublicMessageParser(MessageParser):
    """Gate.io public WebSocket message parser."""

    def __init__(self, symbol_mapper: SymbolMapperInterface):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.symbol_mapper = symbol_mapper

    async def parse_message(self, raw_message: str) -> Optional[Dict[str, Any]]:
        """Parse raw WebSocket message from Gate.io."""
        try:
            import msgspec
            message = msgspec.json.decode(raw_message)
            
            # Handle different message types
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
                else:
                    # Other message types
                    return {"type": "other", "data": message}
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to parse Gate.io message: {e}")
            return None

    async def _parse_update_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Gate.io update message."""
        params = message.get("params", [])
        if len(params) < 2:
            return {"type": "unknown", "data": message}
        
        channel = params[0]
        update_data = params[1]
        
        if "order_book_update" in channel:
            return await self._parse_orderbook_update(channel, update_data)
        elif "trades" in channel:
            return await self._parse_trades_update(channel, update_data)
        else:
            return {"type": "unknown", "channel": channel, "data": update_data}

    async def _parse_orderbook_update(self, channel: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Gate.io orderbook update."""
        try:
            # Extract symbol from channel: spot.order_book_update.BTC_USDT
            symbol_str = channel.split('.')[-1]
            symbol = self.symbol_mapper.to_symbol(symbol_str)
            
            # Gate.io orderbook format:
            # {
            #   "t": timestamp,
            #   "s": symbol,
            #   "U": first_update_id,
            #   "u": last_update_id,
            #   "b": [["price", "amount"], ...],  # bids
            #   "a": [["price", "amount"], ...]   # asks
            # }
            
            bids = []
            asks = []
            
            # Parse bids
            for bid_data in data.get("b", []):
                if len(bid_data) >= 2:
                    price = float(bid_data[0])
                    size = float(bid_data[1])
                    bids.append(OrderBookEntry(price=price, size=size))
            
            # Parse asks
            for ask_data in data.get("a", []):
                if len(ask_data) >= 2:
                    price = float(ask_data[0])
                    size = float(ask_data[1])
                    asks.append(OrderBookEntry(price=price, size=size))
            
            return {
                "type": "orderbook",
                "symbol": symbol,
                "bids": bids,
                "asks": asks,
                "timestamp": data.get("t", 0),
                "channel": channel
            }
            
        except Exception as e:
            self.logger.error(f"Failed to parse orderbook update: {e}")
            return {"type": "error", "error": str(e), "data": data}

    async def _parse_trades_update(self, channel: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Gate.io trades update."""
        try:
            # Extract symbol from channel: spot.trades.BTC_USDT
            symbol_str = channel.split('.')[-1]
            symbol = self.symbol_mapper.to_symbol(symbol_str)
            
            trades = []
            
            # Gate.io trades format is typically a list of trade objects
            trade_list = data if isinstance(data, list) else [data]
            
            for trade_data in trade_list:
                # Gate.io trade format:
                # {
                #   "id": trade_id,
                #   "create_time": timestamp,
                #   "side": "buy"|"sell",
                #   "amount": "amount",
                #   "price": "price"
                # }
                
                side = Side.BUY if trade_data.get("side") == "buy" else Side.SELL
                
                trade = Trade(
                    symbol=symbol,
                    price=float(trade_data.get("price", 0)),
                    amount=float(trade_data.get("amount", 0)),
                    side=side,
                    timestamp=int(trade_data.get("create_time", 0)),
                    trade_id=str(trade_data.get("id", "")),
                    is_maker=False  # Gate.io doesn't typically provide maker info in public trades
                )
                trades.append(trade)
            
            return {
                "type": "trades",
                "symbol": symbol,
                "trades": trades,
                "channel": channel
            }
            
        except Exception as e:
            self.logger.error(f"Failed to parse trades update: {e}")
            return {"type": "error", "error": str(e), "data": data}

    def get_supported_message_types(self) -> List[str]:
        """Get list of supported message types."""
        return ["orderbook", "trades", "subscription", "ping_pong", "other", "error"]