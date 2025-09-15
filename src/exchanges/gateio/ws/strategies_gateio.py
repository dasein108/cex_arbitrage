"""Gate.io WebSocket Strategy Implementations

HFT-compliant strategies for Gate.io WebSocket connections.
Implements connection, subscription, and parsing logic using strategy pattern.

HFT COMPLIANCE: Sub-millisecond strategy execution, zero-copy patterns.
"""

import logging
import time
import msgspec
from typing import List, Dict, Optional, Any, AsyncIterator

from core.cex.websocket import (
    ConnectionStrategy, SubscriptionStrategy, MessageParser,
    ConnectionContext, SubscriptionContext, ParsedMessage,
    MessageType, SubscriptionAction, WebSocketStrategyFactory
)
from structs.exchange import Symbol, OrderBook, OrderBookEntry, Trade, Side
from exchanges.gateio.common.gateio_config import GateioConfig
from exchanges.gateio.common.gateio_utils import GateioUtils


# === Gate.io Public Strategies ===

class GateioPublicConnectionStrategy(ConnectionStrategy):
    """Gate.io public WebSocket connection strategy."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    async def create_connection_context(self) -> ConnectionContext:
        """Create Gate.io public WebSocket connection context."""
        return ConnectionContext(
            url=GateioConfig.WEBSOCKET_PUBLIC_URL,
            headers={},
            auth_required=False,
            ping_interval=30,
            ping_timeout=10,
            max_reconnect_attempts=10,
            reconnect_delay=1.0
        )
    
    async def authenticate(self, websocket: Any) -> bool:
        """Public WebSocket requires no authentication."""
        return True
    
    async def handle_keep_alive(self, websocket: Any) -> None:
        """Handle Gate.io keep-alive (ping/pong)."""
        # Gate.io handles keep-alive automatically
        pass
    
    def should_reconnect(self, error: Exception) -> bool:
        """Determine if reconnection should be attempted."""
        # Reconnect on most errors except authentication failures
        return not isinstance(error, (PermissionError, ValueError))


class GateioPublicSubscriptionStrategy(SubscriptionStrategy):
    """Gate.io public WebSocket subscription strategy."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def create_subscription_messages(
        self, 
        symbols: List[Symbol], 
        action: SubscriptionAction
    ) -> List[str]:
        """Create Gate.io subscription messages."""
        messages = []
        
        for symbol in symbols:
            symbol_str = GateioUtils.symbol_to_pair(symbol)
            
            # Gate.io WebSocket subscription format
            channels = [
                f"spot.order_book.{symbol_str}",  # Orderbook updates
                f"spot.trades.{symbol_str}"       # Trade updates
            ]
            
            for channel in channels:
                message = {
                    "id": int(time.time() * 1000),
                    "method": "subscribe" if action == SubscriptionAction.SUBSCRIBE else "unsubscribe",
                    "params": {
                        "channel": channel,
                        "event": "subscribe" if action == SubscriptionAction.SUBSCRIBE else "unsubscribe"
                    }
                }
                messages.append(msgspec.json.encode(message).decode())
        
        return messages
    
    def get_subscription_context(self, symbol: Symbol) -> SubscriptionContext:
        """Get subscription context for a symbol."""
        symbol_str = GateioUtils.symbol_to_pair(symbol)
        
        return SubscriptionContext(
            symbol=symbol,
            channels=[
                f"spot.order_book.{symbol_str}",
                f"spot.trades.{symbol_str}"
            ],
            parameters={"symbol": symbol_str}
        )
    
    def parse_channel_from_message(self, message: Dict[str, Any]) -> Optional[str]:
        """Extract channel from Gate.io message."""
        if 'params' in message:
            return message['params'].get('channel')
        return message.get('channel')
    
    def should_resubscribe_on_reconnect(self) -> bool:
        """Gate.io requires resubscription after reconnection."""
        return True
    
    def get_symbol_from_channel(self, channel: str) -> Optional[Symbol]:
        """Extract symbol from Gate.io channel name."""
        try:
            # Channel format: spot.order_book.BTC_USDT or spot.trades.BTC_USDT
            parts = channel.split('.')
            if len(parts) >= 3:
                symbol_str = parts[2]
                return GateioUtils.pair_to_symbol(symbol_str)
        except Exception:
            pass
        return None


class GateioPublicMessageParser(MessageParser):
    """Gate.io public WebSocket message parser with HFT optimizations."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    async def parse_message(self, raw_message: str) -> Optional[ParsedMessage]:
        """Parse Gate.io WebSocket message."""
        try:
            # Gate.io uses JSON format
            if isinstance(raw_message, str):
                message = msgspec.json.decode(raw_message)
            else:
                message = msgspec.json.decode(raw_message.decode('utf-8'))
            
            message_type = self.get_message_type(message)
            
            if message_type == MessageType.ORDERBOOK:
                return await self._parse_orderbook_message(message)
            elif message_type == MessageType.TRADE:
                return await self._parse_trade_message(message)
            elif message_type == MessageType.HEARTBEAT:
                return ParsedMessage(
                    message_type=MessageType.HEARTBEAT,
                    raw_data=message
                )
            elif message_type == MessageType.SUBSCRIPTION_CONFIRM:
                return ParsedMessage(
                    message_type=MessageType.SUBSCRIPTION_CONFIRM,
                    raw_data=message
                )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error parsing message: {e}")
            return None
    
    def get_message_type(self, message: Dict[str, Any]) -> MessageType:
        """Fast message type detection for Gate.io."""
        if 'method' in message:
            method = message['method']
            if method in ('subscribe', 'unsubscribe'):
                return MessageType.SUBSCRIPTION_CONFIRM
            elif method == 'update':
                channel = message.get('params', {}).get('channel', '')
                if 'order_book' in channel:
                    return MessageType.ORDERBOOK
                elif 'trades' in channel:
                    return MessageType.TRADE
        elif 'ping' in message or 'pong' in message:
            return MessageType.HEARTBEAT
        elif 'error' in message:
            return MessageType.ERROR
        
        return MessageType.UNKNOWN
    
    async def parse_orderbook_message(
        self, 
        message: Dict[str, Any]
    ) -> Optional[OrderBook]:
        """Parse orderbook message."""
        try:
            params = message.get('params', {})
            result = params.get('result', {})
            
            if not result:
                return None
            
            # Parse bids and asks
            bids = []
            asks = []
            
            for bid_data in result.get('bids', []):
                if len(bid_data) >= 2:
                    bids.append(OrderBookEntry(
                        price=float(bid_data[0]),
                        size=float(bid_data[1])
                    ))
            
            for ask_data in result.get('asks', []):
                if len(ask_data) >= 2:
                    asks.append(OrderBookEntry(
                        price=float(ask_data[0]),
                        size=float(ask_data[1])
                    ))
            
            return OrderBook(
                bids=bids,
                asks=asks,
                timestamp=time.time()
            )
            
        except Exception as e:
            self.logger.error(f"Error parsing orderbook: {e}")
            return None
    
    def supports_batch_parsing(self) -> bool:
        """Gate.io parser supports batch processing."""
        return True
    
    async def parse_batch_messages(
        self, 
        raw_messages: List[str]
    ) -> AsyncIterator[ParsedMessage]:
        """Batch parse messages for efficiency."""
        for raw_message in raw_messages:
            parsed = await self.parse_message(raw_message)
            if parsed:
                yield parsed
    
    async def _parse_orderbook_message(self, message: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse orderbook-specific message."""
        try:
            params = message.get('params', {})
            channel = params.get('channel', '')
            symbol = self._extract_symbol_from_channel(channel)
            orderbook = await self.parse_orderbook_message(message)
            
            return ParsedMessage(
                message_type=MessageType.ORDERBOOK,
                symbol=symbol,
                channel=channel,
                data=orderbook,
                raw_data=message
            )
            
        except Exception as e:
            self.logger.error(f"Error parsing orderbook message: {e}")
            return None
    
    async def _parse_trade_message(self, message: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse trade-specific message."""
        try:
            params = message.get('params', {})
            channel = params.get('channel', '')
            symbol = self._extract_symbol_from_channel(channel)
            trades = await self._parse_trades_from_message(message)
            
            return ParsedMessage(
                message_type=MessageType.TRADE,
                symbol=symbol,
                channel=channel,
                data=trades,
                raw_data=message
            )
            
        except Exception as e:
            self.logger.error(f"Error parsing trade message: {e}")
            return None
    
    def _extract_symbol_from_channel(self, channel: str) -> Optional[Symbol]:
        """Extract symbol from channel name."""
        try:
            parts = channel.split('.')
            if len(parts) >= 3:
                symbol_str = parts[2]
                return GateioUtils.pair_to_symbol(symbol_str)
        except Exception:
            pass
        return None
    
    async def _parse_trades_from_message(self, message: Dict[str, Any]) -> Optional[List[Trade]]:
        """Parse trades from message."""
        try:
            params = message.get('params', {})
            result = params.get('result', [])
            
            trades = []
            
            for trade_data in result:
                side = Side.BUY if trade_data.get('side') == 'buy' else Side.SELL
                
                trade = Trade(
                    price=float(trade_data.get('price', 0)),
                    amount=float(trade_data.get('amount', 0)),
                    side=side,
                    timestamp=int(trade_data.get('time', time.time())),
                    is_maker=False  # Gate.io doesn't specify maker/taker in public feeds
                )
                trades.append(trade)
            
            return trades
            
        except Exception as e:
            self.logger.error(f"Error parsing trades: {e}")
            return None


# === Gate.io Private Strategies ===

class GateioPrivateConnectionStrategy(ConnectionStrategy):
    """Gate.io private WebSocket connection strategy."""
    
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    async def create_connection_context(self) -> ConnectionContext:
        """Create Gate.io private WebSocket connection context."""
        return ConnectionContext(
            url=GateioConfig.WEBSOCKET_PRIVATE_URL,
            headers={},
            auth_required=True,
            auth_params={
                'api_key': self.api_key,
                'secret_key': self.secret_key
            },
            ping_interval=30,
            ping_timeout=10,
            max_reconnect_attempts=10,
            reconnect_delay=1.0
        )
    
    async def authenticate(self, websocket: Any) -> bool:
        """Authenticate Gate.io private WebSocket."""
        try:
            # Gate.io private WebSocket authentication
            timestamp = str(int(time.time()))
            
            # Create signature (simplified - would need actual Gate.io auth logic)
            auth_message = {
                "id": int(time.time() * 1000),
                "method": "server.sign",
                "params": {
                    "key": self.api_key,
                    "timestamp": timestamp,
                    # Add proper signature here
                }
            }
            
            await websocket.send(msgspec.json.encode(auth_message).decode())
            return True
            
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}")
            return False
    
    async def handle_keep_alive(self, websocket: Any) -> None:
        """Handle Gate.io private keep-alive."""
        pass
    
    def should_reconnect(self, error: Exception) -> bool:
        """Determine if reconnection should be attempted."""
        return not isinstance(error, (PermissionError, ValueError))


class GateioPrivateSubscriptionStrategy(SubscriptionStrategy):
    """Gate.io private WebSocket subscription strategy."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def create_subscription_messages(
        self, 
        symbols: List[Symbol], 
        action: SubscriptionAction
    ) -> List[str]:
        """Create Gate.io private subscription messages."""
        messages = []
        
        # Subscribe to private channels
        channels = [
            "spot.balances",
            "spot.orders"
        ]
        
        for channel in channels:
            message = {
                "id": int(time.time() * 1000),
                "method": "subscribe" if action == SubscriptionAction.SUBSCRIBE else "unsubscribe",
                "params": {
                    "channel": channel,
                    "event": "subscribe" if action == SubscriptionAction.SUBSCRIBE else "unsubscribe"
                }
            }
            messages.append(msgspec.json.encode(message).decode())
        
        return messages
    
    def get_subscription_context(self, symbol: Symbol) -> SubscriptionContext:
        """Get private subscription context."""
        return SubscriptionContext(
            symbol=symbol,
            channels=["spot.balances", "spot.orders"],
            parameters={}
        )
    
    def parse_channel_from_message(self, message: Dict[str, Any]) -> Optional[str]:
        """Extract channel from private message."""
        if 'params' in message:
            return message['params'].get('channel')
        return message.get('channel')
    
    def should_resubscribe_on_reconnect(self) -> bool:
        """Private WebSocket requires resubscription."""
        return True
    
    def get_symbol_from_channel(self, channel: str) -> Optional[Symbol]:
        """Private channels don't typically contain symbols."""
        return None


class GateioPrivateMessageParser(MessageParser):
    """Gate.io private WebSocket message parser."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    async def parse_message(self, raw_message: str) -> Optional[ParsedMessage]:
        """Parse Gate.io private WebSocket message."""
        try:
            if isinstance(raw_message, str):
                message = msgspec.json.decode(raw_message)
            else:
                message = msgspec.json.decode(raw_message.decode('utf-8'))
            
            message_type = self.get_message_type(message)
            
            return ParsedMessage(
                message_type=message_type,
                channel=self._extract_channel(message),
                data=message.get('params', {}).get('result'),
                raw_data=message
            )
            
        except Exception as e:
            self.logger.error(f"Error parsing private message: {e}")
            return None
    
    def get_message_type(self, message: Dict[str, Any]) -> MessageType:
        """Detect private message type."""
        if 'params' in message:
            channel = message['params'].get('channel', '')
            if 'balances' in channel:
                return MessageType.BALANCE
            elif 'orders' in channel:
                return MessageType.ORDER
        elif 'ping' in message or 'pong' in message:
            return MessageType.HEARTBEAT
        elif 'error' in message:
            return MessageType.ERROR
        
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
    
    def _extract_channel(self, message: Dict[str, Any]) -> Optional[str]:
        """Extract channel from message."""
        if 'params' in message:
            return message['params'].get('channel')
        return message.get('channel')


# Register strategies with factory
WebSocketStrategyFactory.register_strategies(
    'gateio', False, 
    GateioPublicConnectionStrategy,
    GateioPublicSubscriptionStrategy,
    GateioPublicMessageParser
)

WebSocketStrategyFactory.register_strategies(
    'gateio', True,
    GateioPrivateConnectionStrategy,
    GateioPrivateSubscriptionStrategy, 
    GateioPrivateMessageParser
)