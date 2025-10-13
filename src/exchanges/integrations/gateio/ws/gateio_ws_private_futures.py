"""
Gate.io Private Futures WebSocket Implementation

Clean implementation following the MEXC pattern with direct logic implementation.
Separate exchange implementation treating Gate.io futures private operations as completely 
independent from Gate.io spot. Uses dedicated configuration with its own futures endpoints.

Handles private futures WebSocket streams for account data including:
- Futures order updates via JSON
- Futures account balance changes via JSON  
- Futures trade confirmations via JSON
- Futures position updates
- Futures margin updates

Features:
- Direct implementation (no strategy dependencies)
- Completely separate from Gate.io spot configuration
- HFT-optimized message processing for futures trading
- Event-driven architecture with structured handlers
- Clean separation from spot exchange operations
- Gate.io futures-specific JSON message parsing

Gate.io Private Futures WebSocket Specifications:
- Endpoint: wss://fx-ws.gateio.ws/v4/ws/usdt/ (USDT perpetual futures)
- Authentication: API key signature-based (HMAC-SHA512)
- Message Format: JSON with channel-based subscriptions
- Channels: futures.orders, futures.balances, futures.user_trades, futures.positions

Architecture: Direct implementation following MEXC pattern
"""

import time
import hashlib
import hmac
from typing import Dict, Optional, Any, List, Union

from exchanges.structs.common import Order, AssetBalance, FuturesBalance, OrderId, Trade, OrderStatus, OrderType, Side, Position
from exchanges.structs.types import AssetName
from exchanges.interfaces.ws import PrivateBaseWebsocket
from infrastructure.networking.websocket.structs import SubscriptionAction, WebsocketChannelType, PrivateWebsocketChannelType
from exchanges.integrations.gateio.services.futures_symbol_mapper import GateioFuturesSymbol

from exchanges.integrations.gateio.utils import (
    from_subscription_action,
    to_order_type,
    to_order_status,
    to_side,
)
from exchanges.integrations.gateio.ws.gateio_ws_common import GateioBaseWebsocket

# Private futures channel mapping for Gate.io
_PRIVATE_FUTURES_CHANNEL_MAPPING = {
    WebsocketChannelType.ORDER: "futures.orders",
    WebsocketChannelType.TICKER: "futures.tickers",
    WebsocketChannelType.EXECUTION: "futures.usertrades",
    WebsocketChannelType.BALANCE: "futures.balances",
    WebsocketChannelType.POSITION: "futures.positions",
    WebsocketChannelType.HEARTBEAT: "futures.ping",
}


class GateioPrivateFuturesWebsocket(GateioBaseWebsocket, PrivateBaseWebsocket):
    """Gate.io private futures WebSocket client inheriting from common base for shared Gate.io logic."""
    PING_CHANNEL = "futures.ping"

    def _prepare_subscription_message(self, action: SubscriptionAction,
                                      channel: WebsocketChannelType, **kwargs) -> Dict[str, Any]:
        """Prepare Gate.io private futures subscription message format."""
        event = from_subscription_action(action)
        channel_name = _PRIVATE_FUTURES_CHANNEL_MAPPING.get(channel, None)
        
        if channel_name is None:
            raise ValueError(f"Unsupported private futures channel type: {channel}")
            
        timestamp = int(time.time())
        message = {
            "id": int(time.time() * 1e6),
            "time": timestamp,
            "channel": channel_name,
            "event": event
        }
        
        if channel in [WebsocketChannelType.TICKER]:
            raise NotImplementedError("TODO: Implement ticker subscription for futures if needed")

        # Add payload for channels that require it based on Gate.io futures documentation
        if channel == WebsocketChannelType.BALANCE:
            # futures.balances requires only user_id in payload: ["user_id"]
            # #kwargs.get('user_id', "20011")  # Default user_id
            user_id = '11789588' #TODO: hardcoded move to .env
            message["payload"] = [user_id]
        elif channel in [WebsocketChannelType.ORDER, WebsocketChannelType.POSITION]:
            # futures.orders and futures.positions accept ["!all"] to subscribe to all updates
            message["payload"] = ["!all"]  # Subscribe to all updates
        elif channel == WebsocketChannelType.EXECUTION:
            # futures.usertrades requires specific contract format like ["user_id", "BTC_USD"]
            # Get user_id and contracts from kwargs or use defaults
            # user_id = kwargs.get('user_id', "20011")  # Default user_id
            # contracts = kwargs.get('contracts', ["BTC_USD", "ETH_USD"])
            # # For usertrades, we need [user_id, contract] format
            # contract = contracts[0] if isinstance(contracts, list) else contracts
            # message["payload"] = [user_id, contract]
            message["payload"] = ["!all"]  # Subscribe to all updates

        # Add authentication for private channels
        message["auth"] = self._generate_signature(channel_name, event, timestamp)
            
        self.logger.info(f"Created Gate.io private futures {event} message for channel: {channel_name}",
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

    async def _generate_auth_message(self) -> Optional[Dict[str, Any]]:
        """Generate Gate.io futures WebSocket authentication message."""
        timestamp = int(time.time())
        timestamp_ms = int(time.time() * 1000)
        req_id = f"{timestamp_ms}-1"
        
        # Gate.io futures WebSocket authentication signature format
        channel = "futures.login"  # Futures-specific login channel
        request_param_bytes = b""  # Empty for login request
        
        key = f"api\n{channel}\n{request_param_bytes.decode()}\n{timestamp}"
        
        # Create HMAC SHA512 signature
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            key.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
        
        auth_message = {
            "time": timestamp,
            "channel": channel,
            "event": "api",
            "payload": {
                "api_key": self.api_key,
                "signature": signature,
                "timestamp": str(timestamp),
                "req_id": req_id
            }
        }
        
        return auth_message

    async def _handle_update_message(self, message: Dict[str, Any]) -> None:
        """Handle Gate.io private futures update messages."""
        channel = message.get("channel", "")
        result_data = message.get("result", [])
        
        if not result_data:
            return

        if channel == "futures.tickers":
            # {
            #     "contract": "BTC_USD",
            #     "last": "118.4",
            #     "change_percentage": "0.77",
            #     "funding_rate": "-0.000114",
            #     "funding_rate_indicative": "0.01875",
            #     "mark_price": "118.35",
            #     "index_price": "118.36",
            #     "total_size": "73648",
            #     "volume_24h": "745487577",
            #     "volume_24h_btc": "117",
            #     "volume_24h_usd": "419950",
            #     "quanto_base_rate": "",
            #     "volume_24h_quote": "1665006",
            #     "volume_24h_settle": "178",
            #     "volume_24h_base": "5526",
            #     "low_24h": "99.2",
            #     "high_24h": "132.5"
            # }
            self.logger.error(f"TODO: implement ticker handling for Gate.io futures: {result_data}")
            return
        # Route based on channel type
        elif channel == "futures.balances":
            await self._parse_futures_balance_update(result_data)
        elif channel in ["futures.orders", "futures.orders_v2"]:
            await self._parse_futures_order_update(result_data)
        elif channel in ["futures.usertrades", "futures.usertrades_v2"]:
            await self._parse_futures_user_trade_update(result_data)
        elif channel in ["futures.positions", "futures.position"]:
            await self._parse_futures_position_update(result_data)
        else:
            self.logger.debug(f"Received update for unknown Gate.io private futures channel: {channel}")

    async def _parse_futures_balance_update(self, data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> None:
        """Parse Gate.io futures balance update with full margin information."""
        try:
            balance_list = data if isinstance(data, list) else [data]
            
            for balance_data in balance_list:
                # Parse comprehensive Gate.io futures balance data
                asset = AssetName(balance_data.get('currency', balance_data.get('asset', 'USDT')))
                
                # Gate.io futures balance fields mapping
                total = float(balance_data.get('total', balance_data.get('balance', '0')))
                available = float(balance_data.get('available', '0'))
                unrealized_pnl = float(balance_data.get('unrealized_pnl', balance_data.get('unrealised_pnl', '0')))
                position_margin = float(balance_data.get('position_margin', '0'))
                order_margin = float(balance_data.get('order_margin', '0'))
                
                # Optional cross margin fields for advanced margin modes
                cross_wallet_balance = balance_data.get('cross_wallet_balance')
                cross_unrealized_pnl = balance_data.get('cross_unrealized_pnl')
                
                # Create comprehensive futures balance
                futures_balance = FuturesBalance(
                    asset=asset,
                    total=total,
                    available=available,
                    unrealized_pnl=unrealized_pnl,
                    position_margin=position_margin,
                    order_margin=order_margin,
                    cross_wallet_balance=float(cross_wallet_balance) if cross_wallet_balance is not None else None,
                    cross_unrealized_pnl=float(cross_unrealized_pnl) if cross_unrealized_pnl is not None else None
                )
                
                await self._exec_bound_handler(PrivateWebsocketChannelType.BALANCE, futures_balance)
                
        except Exception as e:
            self.logger.error(f"Error parsing Gate.io futures balance update: {e}")

    async def _parse_futures_order_update(self, data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> None:
        """Parse Gate.io futures order update."""
        try:
            order_list = data if isinstance(data, list) else [data]
            
            for order_data in order_list:
                # Convert Gate.io futures order to unified format
                symbol = GateioFuturesSymbol.to_symbol(order_data.get('contract', ''))

                # Convert create_time to milliseconds if needed
                create_time = order_data.get('create_time', 0)
                timestamp = int(create_time * 1000) if create_time and create_time < 1e10 else int(create_time or 0)

                order = Order(
                    order_id=OrderId(str(order_data.get('id', ''))),
                    symbol=symbol,
                    side=to_side(order_data.get('side', 'buy')),
                    order_type=to_order_type(order_data.get('type', 'limit')),
                    quantity=float(order_data.get('size', '0')),  # Futures uses 'size'
                    price=float(order_data.get('price', '0')) if order_data.get('price') else None,
                    filled_quantity=float(order_data.get('filled_size', '0')),
                    remaining_quantity=float(order_data.get('left', '0')),
                    status=to_order_status(order_data.get('status', 'open')),
                    timestamp=timestamp
                )
                await self._exec_bound_handler(PrivateWebsocketChannelType.ORDER, order)
                
        except Exception as e:
            self.logger.error(f"Error parsing Gate.io futures order update: {e}")

    async def _parse_futures_user_trade_update(self, data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> None:
        """Parse Gate.io futures user trade update."""
        try:
            trade_list = data if isinstance(data, list) else [data]
            
            for trade_data in trade_list:
                # Convert Gate.io futures trade to unified format
                symbol = GateioFuturesSymbol.to_symbol(trade_data.get('contract', ''))

                # Handle size field - negative means sell, positive means buy
                size = float(trade_data.get('size', '0'))
                quantity = abs(size)
                side = Side.SELL if size < 0 else Side.BUY

                # Use create_time_ms if available, otherwise create_time in seconds
                timestamp = trade_data.get('create_time_ms', 0)
                if not timestamp:
                    create_time = trade_data.get('create_time', 0)
                    timestamp = int(create_time * 1000) if create_time else 0

                price = float(trade_data.get('price', '0'))

                trade = Trade(
                    symbol=symbol,
                    price=price,
                    quantity=quantity,
                    quote_quantity=price * quantity,
                    side=side,
                    timestamp=int(timestamp),
                    is_maker=trade_data.get('role', '') == 'maker'  # May not be available
                )

                await self._exec_bound_handler(PrivateWebsocketChannelType.EXECUTION, trade)
                
        except Exception as e:
            self.logger.error(f"Error parsing Gate.io futures user trade update: {e}")

    async def _parse_futures_position_update(self, data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> None:
        """Parse Gate.io futures position update."""
        try:
            position_list = data if isinstance(data, list) else [data]
            
            for position_data in position_list:
                # Convert Gate.io futures position to unified format
                symbol = GateioFuturesSymbol.to_symbol(position_data.get('contract', ''))
                
                # Handle position size - positive means long, negative means short
                size = float(position_data.get('size', '0'))
                abs_size = abs(size)
                side = Side.BUY if size >= 0 else Side.SELL
                
                # Parse timestamps - prefer time_ms if available
                timestamp = position_data.get('time_ms', 0)
                if not timestamp:
                    time_sec = position_data.get('time', 0)
                    timestamp = int(time_sec * 1000) if time_sec else 0
                
                # Parse entry price
                entry_price = float(position_data.get('entry_price', '0'))
                
                # Parse PnL fields
                realized_pnl = float(position_data.get('realised_pnl', '0'))
                # Gate.io doesn't provide unrealized PnL directly in position updates
                
                # Parse margin and liquidation price
                margin = float(position_data.get('margin', '0')) if position_data.get('margin') else None
                liquidation_price = float(position_data.get('liq_price', '0')) if position_data.get('liq_price') else None
                
                position = Position(
                    symbol=symbol,
                    side=side,
                    size=abs_size,
                    entry_price=entry_price,
                    mark_price=None,  # Not provided in position updates
                    unrealized_pnl=None,  # Not provided in position updates
                    realized_pnl=realized_pnl,
                    liquidation_price=liquidation_price,
                    margin=margin,
                    timestamp=int(timestamp)
                )
                
                await self._exec_bound_handler(PrivateWebsocketChannelType.POSITION, position)
                
        except Exception as e:
            self.logger.error(f"Error parsing Gate.io futures position update: {e}")