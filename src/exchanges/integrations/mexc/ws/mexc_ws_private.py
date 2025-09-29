"""
MEXC Private WebSocket Implementation

Clean implementation using handler objects for organized message processing.
Handles authenticated WebSocket streams for account data including:
- Order updates via protobuf
- Account balance changes via protobuf  
- Trade confirmations via protobuf

Features:
- Handler object pattern for clean organization
- HFT-optimized message processing
- Event-driven architecture with structured handlers
- Clean separation of concerns
- MEXC-specific protobuf message parsing

MEXC Private WebSocket Specifications:
- Endpoint: wss://wbs-api.mexc.com/ws
- Authentication: Listen key-based (managed by strategy)
- Keep-alive: Every 30 minutes to prevent expiration
- Auto-cleanup: Listen key deletion on disconnect

Architecture: Handler objects with composite class coordination
"""

from typing import Dict, Optional, Any, Union
import asyncio
from exchanges.structs import Order, AssetBalance, Trade, Side, OrderType, OrderStatus
from exchanges.structs.types import AssetName
from exchanges.integrations.mexc.rest.mexc_rest_spot_private import MexcPrivateSpotRest
from config.structs import ExchangeConfig
from exchanges.interfaces.ws import BasePrivateWebsocket
from infrastructure.exceptions.system import InitializationError
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
# ExchangeMapperFactory dependency removed - using direct utility functions
from infrastructure.logging import get_exchange_logger

# MEXC-specific protobuf imports for message parsing
from exchanges.integrations.mexc.structs.protobuf.PrivateAccountV3Api_pb2 import PrivateAccountV3Api
from exchanges.integrations.mexc.structs.protobuf.PrivateOrdersV3Api_pb2 import PrivateOrdersV3Api
from exchanges.integrations.mexc.structs.protobuf.PrivateDealsV3Api_pb2 import PrivateDealsV3Api
from websockets import connect

from infrastructure.networking.websocket.structs import SubscriptionAction, WebsocketChannelType
from utils import safe_cancel_task, get_current_timestamp
from exchanges.integrations.mexc.utils import from_subscription_action
from exchanges.consts import DEFAULT_PRIVATE_WEBSOCKET_CHANNELS
from exchanges.integrations.mexc.ws.protobuf_parser import MexcProtobufParser
from exchanges.integrations.mexc.services.symbol_mapper import MexcSymbol
import msgspec

_PRIVATE_CHANNEL_MAPPING = {
    WebsocketChannelType.ORDER: "spot@private.orders.v3.api.pb",
    WebsocketChannelType.TRADE: "spot@private.deals.v3.api.pb",
    WebsocketChannelType.BALANCE: "spot@private.account.v3.pb"
}

_WS_ORDER_STATUS_MAPPING = {
    1: OrderStatus.NEW,
    2: OrderStatus.FILLED,
    3: OrderStatus.PARTIALLY_FILLED,
    4: OrderStatus.CANCELED,
}

_WS_ORDER_TYPE_MAPPING = {
    1: OrderType.LIMIT,
    2: OrderType.MARKET,
    3: OrderType.STOP_LIMIT,
    4: OrderType.STOP_MARKET,
}

class MexcPrivateSpotWebsocket(BasePrivateWebsocket):
    """MEXC private WebSocket client using dependency injection pattern."""

    def _prepare_subscription_message(self, action: SubscriptionAction, channel: WebsocketChannelType,
                                            **kwargs) -> Dict[str, Any]:

        method = from_subscription_action(action)
        channel_name = _PRIVATE_CHANNEL_MAPPING.get(channel, None)

        if channel_name is None:
            raise ValueError(f"Unsupported private channel type: {channel}")

        message = {
            "method": method,
            "params": [channel_name]
        }

        return message

    async def _create_websocket(self):
        try:
            # Clean up existing listen key if reconnecting
            await self._delete_listen_key()

            if self._keep_alive_task:
                self._keep_alive_task = await safe_cancel_task(self._keep_alive_task)

            # Create listen key via REST API
            self.listen_key = await self.rest_client.create_listen_key()
            self.logger.debug(f"Created MEXC listen key: {self.listen_key[:8]}...")

            # Build WebSocket URL with listen key
            ws_url = f"{self.config.websocket_url}?listenKey={self.listen_key}"

            self.logger.debug(f"Connecting to MEXC private WebSocket: {ws_url[:50]}...")

            # MEXC private connection with minimal headers (same as public)
            _websocket = await connect(
                ws_url,
                # MEXC-specific optimizations
                ping_interval=self.config.websocket.ping_interval,
                ping_timeout=self.config.websocket.ping_timeout,
                max_queue=self.config.websocket.max_queue_size,
                # Disable compression for CPU optimization in HFT
                compression=None,
                max_size=self.config.websocket.max_message_size,
                # Additional performance settings
                write_limit=2 ** 20,  # 1MB write buffer
            )

            # start keep-alive task
            self._keep_alive_task = asyncio.create_task(self._keep_alive_loop())

            self.logger.debug("MEXC private WebSocket connected successfully")
            return _websocket

        except Exception as e:
            self.logger.error(f"Failed to connect to MEXC private WebSocket: {e}")
            # Clean up listen key if connection failed
            if self.listen_key:
                try:
                    await self.rest_client.delete_listen_key(self.listen_key)
                except Exception:
                    pass  # Ignore cleanup errors
                self.listen_key = None
            raise InitializationError(f"MEXC private WebSocket connection failed: {str(e)}")

    def __init__(
        self,
        config: ExchangeConfig,
        handlers: PrivateWebsocketHandlers,
        **kwargs
    ):
        """
        Initialize MEXC private WebSocket with handler objects.
        
        Args:
            config: Exchange configuration
            handlers: PrivateWebsocketHandlers object containing message handlers
            **kwargs: Additional arguments passed to base class
        """
        # Create REST client for MEXC-specific operations (e.g., listen key management)
        rest_logger = get_exchange_logger('mexc', 'rest_private')
        self.rest_client = MexcPrivateSpotRest(
            config=config,
            logger=rest_logger
        )
        
        # Initialize via composite class with handler object
        super().__init__(
            config=config,
            # handlers=handlers,
            **kwargs
        )

        self.listen_key: Optional[str] = None
        self._keep_alive_task: Optional[asyncio.Task] = None
        self.keep_alive_interval = 1800  # 30 minutes in seconds

        self.logger.info("MEXC private WebSocket initialized with handler objects")

    async def initialize(self, **kwargs) -> None:
        await super().initialize()

    async def _keep_alive_loop(self) -> None:
        """Keep the listen key alive with periodic updates."""
        while self.listen_key:
            try:
                # Wait for keep-alive interval (30 minutes)
                await asyncio.sleep(self.keep_alive_interval)

                await self.rest_client.keep_alive_listen_key(self.listen_key)
                self.logger.debug(f"Listen key kept alive: {self.listen_key[:8]}...")

            except asyncio.CancelledError:
                self.logger.debug("Keep-alive task cancelled")
                break
            except Exception as e:
                self.logger.error(f"Failed to keep listen key alive: {e}")
                # Try to regenerate listen key
                await self._regenerate_listen_key()

    async def _delete_listen_key(self) -> None:
        """Delete the current listen key."""
        if self.listen_key:
            try:
                await self.rest_client.delete_listen_key(self.listen_key)
                self.logger.debug(f"Deleted listen key: {self.listen_key[:8]}...")
            except Exception as e:
                self.logger.error(f"Failed to delete listen key: {e}")
            finally:
                self.listen_key = None


    async def _regenerate_listen_key(self) -> None:
        """Regenerate listen key if keep-alive fails."""
        try:
            # Delete old listen key if exists


            # Create new listen key
            self.listen_key = await self.rest_client.create_listen_key()
            self.logger.debug(f"Regenerated listen key: {self.listen_key[:8]}...")

        except Exception as e:
            self.logger.error(f"Failed to regenerate listen key: {e}")
            self.listen_key = None

    async def close(self):
        await super().close()
        # Cancel keep-alive task if running
        self._keep_alive_task = safe_cancel_task(self._keep_alive_task)
        await self._delete_listen_key()

    async def _parse_protobuf_message(self, raw_message: bytes):
        """Unified protobuf message parser for MEXC private messages using MEXC structs."""
        try:
            # Use consolidated protobuf utilities
            wrapper = MexcProtobufParser.parse_wrapper_message(raw_message)

            # Determine message type and extract data
            channel = wrapper.channel if hasattr(wrapper, 'channel') else ""
            symbol = wrapper.symbol if hasattr(wrapper, 'symbol') else ""

            if "account" in channel:
                # Account/balance update - direct protobuf field parsing
                if wrapper.HasField('privateAccount'):
                    account_data = wrapper.privateAccount

                    # Direct parsing from protobuf fields - account_data already has parsed fields
                    balance_amount = float(account_data.balanceAmount) if hasattr(account_data,
                                                                                  'balanceAmount') else 0.0
                    frozen_amount = float(account_data.frozenAmount) if hasattr(account_data, 'frozenAmount') else 0.0

                    balance = AssetBalance(
                        asset=account_data.vcoinName if hasattr(account_data, 'vcoinName') else "",
                        available=balance_amount,
                        locked=frozen_amount,
                    )
                    await self.handle_balance(balance)

            elif "orders" in channel:
                # Order update - direct protobuf field parsing
                if wrapper.HasField('privateOrders'):
                    order_data = wrapper.privateOrders

                    # Direct parsing from protobuf fields - order_data already has parsed fields
                    order_type = _WS_ORDER_TYPE_MAPPING.get(getattr(order_data, 'status', 0),OrderType.LIMIT)
                    order_status_code = getattr(order_data, 'status', 0)
                    status = _WS_ORDER_STATUS_MAPPING.get(order_status_code, OrderStatus.UNKNOWN)
                    order = Order(
                        order_id=order_data.id if hasattr(order_data, 'id') else "",
                        symbol=MexcSymbol.to_symbol(symbol) if symbol else None,
                        side=Side.BUY if getattr(order_data, 'tradeType', 0) == 1 else Side.SELL,
                        order_type=order_type,  # Default to LIMIT
                        quantity=float(order_data.quantity) if hasattr(order_data, 'quantity') else 0.0,
                        price=float(order_data.price) if hasattr(order_data, 'price') else 0.0,
                        filled_quantity=float(order_data.cumulativeQuantity) if hasattr(order_data,
                                                                                        'cumulativeQuantity') else 0.0,
                        status=status,
                        timestamp=int(getattr(order_data, 'time', 0)),
                        client_order_id=None
                    )

                    await self.handle_order(order)

            elif "deals" in channel:
                # Trade/execution update - direct protobuf field parsing
                if wrapper.HasField('privateDeals'):
                    deal_data = wrapper.privateDeals

                    # Direct parsing from protobuf fields - deal_data already has parsed fields
                    order_side = getattr(deal_data, 'tradeType', 0)

                    unified_trade = Trade(
                        symbol=MexcSymbol.to_symbol(symbol) if symbol else None,
                        price=float(deal_data.price) if hasattr(deal_data, 'price') else 0.0,
                        quantity=float(deal_data.quantity) if hasattr(deal_data, 'quantity') else 0.0,
                        timestamp=int(getattr(deal_data, 'time', 0)),
                        side=Side.BUY if order_side == 1 else Side.SELL,
                        trade_id=str(getattr(deal_data, 'time', get_current_timestamp()))  # Use timestamp as trade ID
                    )

                    await self.handle_execution(unified_trade)
            else:
                # Unknown protobuf message type
                self.logger.warning(f"Received unknown protobuf message on channel: {channel}",
                                    exchange="mexc",
                                    channel=channel)

        except Exception as e:
            self.logger.error(f"Error parsing protobuf message: {e}",
                              exchange="mexc",
                              error_type="protobuf_parse_error")


    # async def handle_order(self, order: Order) -> None:
    #     pass
    #
    # async def handle_balance(self, balance: AssetBalance) -> None:
    #     pass
    #
    # async def handle_execution(self, trade: Trade) -> None:
    #     pass

    async def _handle_message(self, raw_message: Union[bytes, str]) -> None:
        try:
            # Check if it's bytes (protobuf) or string/dict (JSON)
            if isinstance(raw_message, bytes):
                # Handle protobuf message - simple approach
                return await self._parse_protobuf_message(raw_message)

            else:
                if isinstance(raw_message, str):
                    message = msgspec.json.decode(raw_message)
                else:
                    # If it's already a dict, use it directly
                    message = raw_message

                self.logger.info(f'Received non-protobuf message on private channel {message}',)

        except Exception as e:
            self.logger.error(f"Error parsing private message: {e}",
                              exchange="mexc",
                              error_type="message_parse_error")

