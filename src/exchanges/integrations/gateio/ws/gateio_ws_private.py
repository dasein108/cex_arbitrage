"""
Gate.io Private WebSocket Implementation

Clean implementation following the MEXC pattern with direct logic implementation.
Handles authenticated WebSocket streams for account data including:
- Order updates via JSON
- Account balance changes via JSON  
- Trade confirmations via JSON

Features:
- Direct implementation (no strategy dependencies)
- HFT-optimized message processing
- Event-driven architecture with structured handlers
- Clean separation of concerns
- Gate.io-specific JSON message parsing

Gate.io Private WebSocket Specifications:
- Endpoint: wss://api.gateio.ws/ws/v4/
- Authentication: API key signature-based (HMAC-SHA512)
- Message Format: JSON with channel-based subscriptions
- Channels: spot.orders, spot.balances, spot.user_trades

Architecture: Direct implementation following MEXC pattern
"""

import time
import hashlib
import hmac
import asyncio
import msgspec
from typing import Dict, Optional, Any, List, Union
from websockets import connect

from exchanges.integrations.gateio.services.spot_symbol_mapper import GateioSpotSymbol
from exchanges.structs import OrderStatus, ExchangeEnum
from exchanges.structs.common import Order, AssetBalance, Trade, OrderId
from exchanges.structs.types import AssetName
from config.structs import ExchangeConfig
from exchanges.interfaces.ws import PrivateBaseWebsocket
from infrastructure.networking.websocket.structs import SubscriptionAction, WebsocketChannelType, PrivateWebsocketChannelType
from exchanges.integrations.gateio.utils import (
    from_subscription_action,
    to_symbol,
    to_side,
    to_order_type,
    to_order_status,
)
from exchanges.integrations.gateio.ws.gateio_ws_common import GateioBaseWebsocket

# Private channel mapping for Gate.io
_PRIVATE_CHANNEL_MAPPING = {
    WebsocketChannelType.ORDER: "spot.orders",
    WebsocketChannelType.EXECUTION: "spot.usertrades",
    WebsocketChannelType.BALANCE: "spot.balances",
    WebsocketChannelType.HEARTBEAT: "spot.ping",
}


class GateioPrivateSpotWebsocket(GateioBaseWebsocket, PrivateBaseWebsocket):
    """Gate.io private WebSocket client inheriting from common base for shared Gate.io logic."""
    PING_CHANNEL = "spot.ping"

    def _prepare_subscription_message(self, action: SubscriptionAction,
                                      channel: WebsocketChannelType, **kwargs) -> Dict[str, Any]:
        """Prepare Gate.io private subscription message format."""
        event = from_subscription_action(action)
        channel_name = _PRIVATE_CHANNEL_MAPPING.get(channel, None)

        if channel_name is None:
            raise ValueError(f"Unsupported private channel type: {channel}")

        timestamp = int(time.time())
        message = {
            "id": int(time.time() * 1e6),
            "time": timestamp,
            "channel": channel_name,
            "event": event
        }

        # Add payload for channels that require it
        # spot.orders accepts ["!all"] to subscribe to all updates
        if channel == WebsocketChannelType.ORDER:
            message["payload"] = ["!all"]  # Subscribe to all order updates
        # spot.usertrades requires specific currency pairs like ["BTC_USDT"]
        elif channel == WebsocketChannelType.EXECUTION:
            # Get symbols from kwargs or use default trading pairs
            # symbols = kwargs.get('symbols', ["BTC_USDT", "ETH_USDT", "BNB_USDT"])
            # message["payload"] = symbols
            message["payload"] = ["!all"]  # Subscribe to all order updates


        # Add authentication for private channels
        message["auth"] = self._generate_signature(channel_name, event, timestamp)

        self.logger.info(f"Created Gate.io private {event} message for channel: {channel_name}",
                          channel=channel_name,
                          event=event,
                          payload=message.get("payload"),
                          exchange=self.exchange_name)

        return message

    def _generate_signature(self, channel: str, event: str, timestamp: int) -> Dict[str, str]:
        """Generate Gate.io authentication signature for WebSocket messages.

        According to Gate.io WebSocket docs, signature string format is:
        channel=<channel>&event=<event>&time=<time>
        """
        # Gate.io signature format: channel=<channel>&event=<event>&time=<time>
        signature_string = f"channel={channel}&event={event}&time={timestamp}"

        # Create HMAC-SHA512 signature
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            signature_string.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()

        return {
            "method": "api_key",
            "KEY": self.api_key,
            "SIGN": signature
        }

    async def _handle_update_message(self, message: Dict[str, Any]) -> None:
        """Handle Gate.io private update messages."""
        channel = message.get("channel", "")
        result_data = message.get("result", [])

        if not result_data:
            return

        # Route based on channel type
        if channel == "spot.balances":
            await self._parse_balance_update(result_data)
        elif channel in ["spot.orders", "spot.orders_v2"]:
            await self._parse_order_update(result_data)
        elif channel in ["spot.usertrades", "spot.usertrades_v2"]:
            await self._parse_user_trade_update(result_data)
        else:
            self.logger.debug(f"Received update for unknown Gate.io private channel: {channel}")

    async def _parse_balance_update(self, data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> None:
        """Parse Gate.io balance update."""
        try:
            balance_list = data if isinstance(data, list) else [data]

            for balance_data in balance_list:
                # Convert Gate.io balance to unified format
                balance = AssetBalance(
                    asset=AssetName(balance_data.get('currency', '')),
                    available=float(balance_data.get('available', '0')),
                    locked=float(balance_data.get('locked', '0'))
                )
                await self._exec_bound_handler(PrivateWebsocketChannelType.BALANCE, balance)

        except Exception as e:
            self.logger.error(f"Error parsing Gate.io balance update: {e}")

    async def _parse_order_update(self, data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> None:
        """Parse Gate.io order update."""
        order_list = data if isinstance(data, list) else [data]

        for order_data in order_list:
            # Convert Gate.io order to unified format
            order_status = None
            remaining_quantity = float(order_data.get('left', '0'))
            filled_quantity = float(order_data.get('filled_amount', '0'))
            # _GATEIO_ORDER_STATUS_MAP = {
            #     'open': OrderStatus.NEW,
            #     'closed': OrderStatus.FILLED,
            #     'cancelled': OrderStatus.CANCELED,
            #     'partial': OrderStatus.PARTIALLY_FILLED,
            #     'filled': OrderStatus.FILLED,
            #     'new': OrderStatus.NEW,
            #     'active': OrderStatus.NEW,
            #     'inactive': OrderStatus.CANCELED,
            # }
            if remaining_quantity == 0:
                order_status = OrderStatus.FILLED
            elif order_data.get('event') == 'put':
                order_status = OrderStatus.NEW
            elif order_data.get('event') == 'update':
                order_status = OrderStatus.PARTIALLY_FILLED
            else: # order_data.get('event') == 'finish':
                order_status = OrderStatus.CANCELED if filled_quantity == 0 else OrderStatus.PARTIALLY_CANCELED

            order = Order(
                order_id=OrderId(order_data.get('id', '')),
                symbol=to_symbol(order_data.get('currency_pair', '')),
                side=to_side(order_data.get('side', 'buy')),
                order_type=to_order_type(order_data.get('type', 'limit')),
                quantity=float(order_data.get('amount', '0')),
                price=float(order_data.get('price', '0')) if order_data.get('price') else None,
                filled_quantity=filled_quantity,
                remaining_quantity=remaining_quantity,
                status=order_status,
                timestamp=int(float(order_data.get('create_time', '0')) * 1000),
                exchange=ExchangeEnum.GATEIO
            )
            await self._exec_bound_handler(PrivateWebsocketChannelType.ORDER, order)

    async def _parse_user_trade_update(self, data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> None:
        """Parse Gate.io user trade update."""
        trade_list = data if isinstance(data, list) else [data]

        for trade_data in trade_list:
            # Convert Gate.io trade to unified format
            symbol = GateioSpotSymbol.to_symbol(trade_data['currency_pair']) if 'currency_pair' in trade_data else None

            # Gate.io provides create_time in seconds, convert to milliseconds
            create_time = trade_data.get('create_time', 0)
            timestamp = int(create_time * 1000) if create_time else 0

            price = float(trade_data.get('price', '0'))
            quantity = float(trade_data.get('amount', '0'))

            trade =  Trade(
                symbol=symbol,
                price=price,
                quantity=quantity,
                quote_quantity=price * quantity,
                side=to_side(trade_data.get('side', 'buy')),
                timestamp=timestamp,
                is_maker=trade_data.get('role', '') == 'maker'  # May not be available in public trades
            )

            await self._exec_bound_handler(PrivateWebsocketChannelType.EXECUTION, trade)
