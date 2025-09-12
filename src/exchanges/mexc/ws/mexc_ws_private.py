"""
MEXC Private WebSocket Implementation

Handles authenticated WebSocket streams for account data including:
- Order updates (executionReport)
- Account balance changes (outboundAccountPosition)
- Trade confirmations (trade)

Features:
- Automatic listen key management (create, keep-alive, cleanup)
- HFT-optimized message processing with fast type detection
- Comprehensive error handling and auto-reconnection
- Event-driven architecture with dependency injection handlers

MEXC Private WebSocket Specifications:
- Endpoint: wss://wbs.mexc.com/ws
- Authentication: Listen key-based (no per-symbol subscriptions)
- Keep-alive: Every 30 minutes to prevent expiration
- Auto-cleanup: Listen key deletion on disconnect

Threading: Fully async/await compatible, thread-safe
Memory: Optimized for high-frequency account updates
"""

import asyncio
import logging
import time
import msgspec
from typing import List, Any, Dict, Optional, Callable, Awaitable
from exchanges.interface.websocket.base_ws import BaseExchangeWebsocketInterface
from structs.exchange import Symbol, Order, AssetBalance, Trade, Side, OrderStatus
from exchanges.mexc.common.mexc_config import MexcConfig
from exchanges.mexc.rest.mexc_private import MexcPrivateExchange
from common.ws_client import SubscriptionAction, WebSocketConfig
from common.exceptions import ExchangeAPIError
from exchanges.mexc.common.mexc_utils import MexcUtils

class MexcWebsocketPrivate(BaseExchangeWebsocketInterface):
    """MEXC private websocket interface for account data streaming"""

    def __init__(
        self, 
        private_client: MexcPrivateExchange,
        config: WebSocketConfig,
        # Event handlers for different private stream events
        order_handler: Optional[Callable[[Order], Awaitable[None]]] = None,
        balance_handler: Optional[Callable[[List[AssetBalance]], Awaitable[None]]] = None,
        trade_handler: Optional[Callable[[Trade], Awaitable[None]]] = None,
        # Keep-alive interval in seconds (MEXC recommends 30 minutes = 1800s)
        keep_alive_interval: int = 1800
    ):
        # Modify config for private endpoint
        private_config =WebSocketConfig(
            name=MexcConfig.EXCHANGE_NAME + "_private",
            url=None, # Should use get_connect_url
            timeout=config.timeout,
            max_reconnect_attempts=config.max_reconnect_attempts,
            reconnect_delay=config.reconnect_delay,
            ping_interval=config.ping_interval,
            ping_timeout=config.ping_timeout
        )
        super().__init__(MexcConfig.EXCHANGE_NAME, private_config,
                         get_connect_url=self.get_connect_url)
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.private_client = private_client
        
        # Event handlers
        self.order_handler = order_handler
        self.balance_handler = balance_handler
        self.trade_handler = trade_handler
        
        # Listen key management
        self.listen_key: Optional[str] = None
        self.keep_alive_task: Optional[asyncio.Task] = None
        self.keep_alive_interval = keep_alive_interval
        
        # Performance optimizations
        self._JSON_INDICATORS = frozenset({ord('{'), ord('[')})
        
    async  def get_connect_url(self):
        """Override connect to set private URL dynamically."""
        self.logger.info("Creating listen key for private stream authentication")
        self.listen_key = await self.private_client.create_listen_key()
        self.logger.info(f"Listen key created: {self.listen_key[:8]}...")

        return MexcConfig.WEBSOCKET_URL + f"?listenKey={self.listen_key}"


    async def init(self, symbols: List[Symbol] = None):
        """
        Initialize private WebSocket connection with listen key management.
        
        Note: Private streams don't use symbols for subscription - they use listen keys
        for authentication and receive ALL account events.
        """
        try:
            # Step 1: Listen key is created in get_connect_url() before connection
            
            # Step 2: Start WebSocket connection (this calls get_connect_url())
            await self.ws_client.start()
            
            # Step 3: Subscribe to private stream using listen key
            private_streams = ["spot@private.account.v3.api.pb",
                               "spot@private.deals.v3.api.pb",
                              "spot@private.orders.v3.api.pb"]

            await self.ws_client.subscribe(private_streams)
                # self.logger.info(f"Subscribed to private stream with listen key: {self.listen_key[:8]}...")
            
            # Step 4: Start keep-alive task to prevent listen key expiration
            self.keep_alive_task = asyncio.create_task(self._keep_alive_loop())
            self.logger.info("Private WebSocket initialized with listen key authentication")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize private WebSocket: {e}")
            await self._cleanup_listen_key()
            raise ExchangeAPIError(500, f"Private WebSocket initialization failed: {e}")

    def _create_subscriptions(self, symbol: Symbol, action: SubscriptionAction) -> List[str]:
        """
        Private streams don't use per-symbol subscriptions.
        They use listen keys and receive all account events.
        """
        # Return listen key to subscribe to private stream
        # MEXC requires subscription message even with listen key in URL
        if self.listen_key:
            return [self.listen_key]
        return []

    async def start_symbol(self, symbol: Symbol):
        """Private streams don't support per-symbol start - all account events are received."""
        self.logger.debug(f"Private streams receive all account events - symbol {symbol} already included")

    async def stop_symbol(self, symbol: Symbol):
        """Private streams don't support per-symbol stop - all account events are received."""
        self.logger.debug(f"Private streams receive all account events - cannot stop individual symbol {symbol}")

    async def stop(self):
        """Stop private WebSocket and cleanup listen key."""
        self.logger.info("Stopping private WebSocket connection")
        
        # Cancel keep-alive task
        if self.keep_alive_task and not self.keep_alive_task.done():
            self.keep_alive_task.cancel()
            try:
                await self.keep_alive_task
            except asyncio.CancelledError:
                pass
        
        # Cleanup listen key
        await self._cleanup_listen_key()
        
        # Stop base WebSocket
        if hasattr(self.ws_client, 'stop'):
            await self.ws_client.stop()
        
        self.logger.info("Private WebSocket stopped and listen key cleaned up")

    async def _keep_alive_loop(self):
        """Background task to keep listen key alive."""
        self.logger.info(f"Starting listen key keep-alive loop (interval: {self.keep_alive_interval}s)")
        
        try:
            while not asyncio.current_task().cancelled():
                await asyncio.sleep(self.keep_alive_interval)
                
                if self.listen_key:
                    try:
                        await self.private_client.keep_alive_listen_key(self.listen_key)
                        self.logger.debug(f"Listen key kept alive: {self.listen_key[:8]}...")
                    except Exception as e:
                        self.logger.error(f"Failed to keep listen key alive: {e}")
                        # Try to regenerate listen key on failure
                        await self._regenerate_listen_key()
                        
        except asyncio.CancelledError:
            self.logger.info("Keep-alive loop cancelled")
            raise
        except Exception as e:
            self.logger.error(f"Keep-alive loop error: {e}")

    async def _regenerate_listen_key(self):
        """Regenerate listen key on authentication errors."""
        try:
            self.logger.info("Regenerating listen key due to authentication error")
            
            # Clean up old listen key
            if self.listen_key:
                try:
                    await self.private_client.delete_listen_key(self.listen_key)
                except:
                    pass  # Ignore errors - key might already be invalid
            
            # Create new listen key
            self.listen_key = await self.private_client.create_listen_key()
            self.logger.info(f"New listen key created: {self.listen_key[:8]}...")
            
            # Resubscribe with new listen key
            await self.ws_client.subscribe([self.listen_key])
            
        except Exception as e:
            self.logger.error(f"Failed to regenerate listen key: {e}")
            raise ExchangeAPIError(500, f"Listen key regeneration failed: {e}")

    async def _cleanup_listen_key(self):
        """Clean up listen key on disconnect."""
        if self.listen_key:
            try:
                await self.private_client.delete_listen_key(self.listen_key)
                self.logger.info(f"Listen key deleted: {self.listen_key[:8]}...")
            except Exception as e:
                self.logger.warning(f"Failed to delete listen key: {e}")
            finally:
                self.listen_key = None

    async def _on_message(self, message):
        """Ultra-optimized private message handling with fast type detection."""
        try:
            if isinstance(message, bytes):
                # Fast binary pattern detection
                if message and message[0] in self._JSON_INDICATORS:
                    json_msg = msgspec.json.decode(message)
                    await self._handle_json_message(json_msg)
                else:
                    # Private streams use protobuf - handle binary messages
                    await self._handle_protobuf_message(message)
                    
            elif isinstance(message, str):
                # Try JSON first
                try:
                    message_bytes = message.encode('utf-8')
                    json_msg = msgspec.json.decode(message_bytes)
                    await self._handle_json_message(json_msg)
                except:
                    # If not JSON, might be base64 encoded protobuf
                    self.logger.debug(f"Received string message: {message[:100]}")
                
            elif isinstance(message, dict):
                await self._handle_json_message(message)
                
        except Exception as e:
            self.logger.error(f"Error processing private message: {e}")
            await self.on_error(e)

    async def _handle_json_message(self, msg: dict):
        """Handle JSON formatted private messages from MEXC."""
        try:
            # Check message type
            if 'code' in msg:
                # Subscription response
                if msg['code'] == 0:
                    self.logger.info("Private stream subscription confirmed")
                else:
                    self.logger.warning(f"Private stream subscription error: {msg}")
                    
                    # Check for authentication errors
                    if 'Blocked' in msg.get('msg', '') or 'unauthorized' in msg.get('msg', '').lower():
                        self.logger.error("Authentication error - regenerating listen key")
                        await self._regenerate_listen_key()
                        
            elif 'e' in msg:
                # Event type message (private stream events)
                event_type = msg.get('e')
                
                if event_type == 'executionReport':
                    await self._handle_order_update(msg)
                elif event_type == 'outboundAccountPosition':
                    await self._handle_balance_update(msg)
                elif event_type == 'trade':
                    await self._handle_trade_update(msg)
                else:
                    self.logger.debug(f"Unknown private event type: {event_type}")
                    
            elif 'ping' in msg:
                # Handle ping/pong for connection health
                pass
                
            else:
                self.logger.debug(f"Unhandled private message: {msg}")
                
        except Exception as e:
            self.logger.error(f"Error handling private JSON message: {e}")

    async def _handle_protobuf_message(self, data: bytes):
        """Handle protobuf formatted private messages from MEXC."""
        try:
            # Import protobuf definitions for private streams (correct names)
            from exchanges.mexc.protobuf.PushDataV3ApiWrapper_pb2 import PushDataV3ApiWrapper
            from exchanges.mexc.protobuf.PrivateAccountV3Api_pb2 import PrivateAccountV3Api
            from exchanges.mexc.protobuf.PrivateDealsV3Api_pb2 import PrivateDealsV3Api
            from exchanges.mexc.protobuf.PrivateOrdersV3Api_pb2 import PrivateOrdersV3Api
            
            # Parse wrapper to determine message type
            wrapper = PushDataV3ApiWrapper()
            wrapper.ParseFromString(data)
            
            # Debug: Log available fields
            available_fields = [field.name for field in wrapper.DESCRIPTOR.fields]
            self.logger.debug(f"Protobuf wrapper fields: {available_fields}")
            
            # Check channel name to route to correct handler  
            channel_name = wrapper.channel if hasattr(wrapper, 'channel') else ''
            symbol_str = wrapper.symbol if hasattr(wrapper, 'symbol') else ''
            self.logger.debug(f"Channel: '{channel_name}', Symbol: '{symbol_str}'")
            
            if 'private.account' in channel_name:
                # Account balance update
                if wrapper.HasField('privateAccount'):
                    await self._handle_protobuf_balance_update(wrapper.privateAccount, symbol_str)
            elif 'private.deals' in channel_name:
                # Trade execution
                if wrapper.HasField('privateDeals'):
                    await self._handle_protobuf_trade_update(wrapper.privateDeals, symbol_str)
            elif 'private.orders' in channel_name:
                # Order update
                if wrapper.HasField('privateOrders'):
                    await self._handle_protobuf_order_update(wrapper.privateOrders, symbol_str)
            else:
                self.logger.debug(f"Unknown private channel: {channel_name}")
                
        except Exception as e:
            self.logger.error(f"Error handling protobuf private message: {e}")
            # Log first bytes for debugging
            if data and len(data) > 0:
                self.logger.debug(f"Protobuf first 50 bytes: {data[:50].hex()}")

    async def _handle_protobuf_balance_update(self, account_data, symbol_str: str):
        """Handle protobuf account balance updates."""
        try:
            # Parse single asset balance from protobuf (MEXC sends individual asset updates)
            asset_balance = AssetBalance(
                asset=account_data.vcoinName,  # Asset name (e.g., "USDT")
                free=float(account_data.balanceAmount) - float(account_data.frozenAmount),  # Available = total - frozen
                locked=float(account_data.frozenAmount)  # Locked amount
            )
            
            # Log the balance change details
            balance_change = float(account_data.balanceAmountChange) if hasattr(account_data, 'balanceAmountChange') else 0
            frozen_change = float(account_data.frozenAmountChange) if hasattr(account_data, 'frozenAmountChange') else 0
            update_type = account_data.type if hasattr(account_data, 'type') else 'UNKNOWN'
            
            self.logger.info(f"Balance update: {asset_balance.asset} - Free: {asset_balance.free}, Locked: {asset_balance.locked} (Change: {balance_change}, Type: {update_type})")
            
            # Pass as list to maintain interface compatibility
            balances = [asset_balance]
            
            if self.balance_handler:
                await self.balance_handler(balances)
            else:
                await self.on_balance_update(balances)
                    
        except Exception as e:
            self.logger.error(f"Error handling protobuf balance update: {e}")
            # Log the actual structure for debugging
            self.logger.debug(f"Account data fields: {dir(account_data)}")

    async def _handle_protobuf_trade_update(self, deals_data, symbol_str: str):
        """Handle protobuf trade execution updates."""
        try:
            # Parse single trade from protobuf (MEXC sends individual trade updates)
            # tradeType: 1=BUY, 2=SELL based on MEXC convention
            side = Side.BUY if deals_data.tradeType == 1 else Side.SELL
            
            trade = Trade(
                price=float(deals_data.price),        # "0.002439"
                amount=float(deals_data.quantity),    # "2519.06" 
                side=side,                           # Derived from tradeType: 2 = SELL
                timestamp=deals_data.time,           # 1757660267480
                is_maker=deals_data.isMaker          # true
            )
            
            # Log detailed trade information
            trade_id = deals_data.tradeId if hasattr(deals_data, 'tradeId') else 'N/A'
            order_id = deals_data.orderId if hasattr(deals_data, 'orderId') else 'N/A'
            fee_amount = float(deals_data.feeAmount) if hasattr(deals_data, 'feeAmount') else 0
            fee_currency = deals_data.feeCurrency if hasattr(deals_data, 'feeCurrency') else 'N/A'
            total_amount = float(deals_data.amount) if hasattr(deals_data, 'amount') else (trade.price * trade.amount)
            
            self.logger.info(f"Trade executed: {trade.side.name} {trade.amount} @ {trade.price} ({'Maker' if trade.is_maker else 'Taker'}) - Total: {total_amount} - Fee: {fee_amount} {fee_currency} - Trade ID: {trade_id}")
            
            if self.trade_handler:
                await self.trade_handler(trade)
            else:
                await self.on_trade_update(trade)
                    
        except Exception as e:
            self.logger.error(f"Error handling protobuf trade update: {e}")
            # Log the actual structure for debugging
            self.logger.debug(f"Deals data fields: {dir(deals_data)}")

    async def _handle_protobuf_order_update(self, orders_data, symbol_str: str):
        """Handle protobuf order updates."""
        try:
            # Map protobuf order status to our enum (status is numeric)
            status = self._parse_protobuf_order_status_numeric(orders_data.status)
            
            # Parse side from tradeType (1=BUY, 2=SELL based on MEXC convention)
            side = Side.BUY if orders_data.tradeType == 1 else Side.SELL
            
            # Parse order type from orderType field
            order_type = self._parse_protobuf_order_type_numeric(orders_data.orderType)
            
            # Create order object with available fields
            order = Order(
                order_id=orders_data.id,
                client_order_id=orders_data.clientId if hasattr(orders_data, 'clientId') else '',
                symbol=MexcUtils.pair_to_symbol(symbol_str) if symbol_str else None,
                side=side,
                order_type=order_type,
                amount=float(orders_data.quantity),  # Original quantity
                price=float(orders_data.price),  # Order price
                amount_filled=float(orders_data.cumulativeQuantity),
                status=status,
                timestamp=orders_data.createTime
            )
            
            self.logger.info(f"Protobuf order update: {order.order_id} - {order.status.name} - {order.side.name} {order.amount} @ {order.price} - Filled: {order.amount_filled}")
            
            if self.order_handler:
                await self.order_handler(order)
            else:
                await self.on_order_update(order)
                    
        except Exception as e:
            self.logger.error(f"Error handling protobuf order update: {e}")
            # Log the actual structure for debugging
            self.logger.debug(f"Orders data fields: {dir(orders_data)}")

    def _parse_protobuf_order_status_numeric(self, status_num: int) -> OrderStatus:
        """Parse protobuf numeric order status to unified enum."""
        # Map MEXC protobuf numeric status values
        # Based on the example: status: 4
        status_mapping = {
            1: OrderStatus.NEW,
            2: OrderStatus.PARTIALLY_FILLED, 
            3: OrderStatus.FILLED,
            4: OrderStatus.CANCELED,  # Status 4 in your example
            5: OrderStatus.PARTIALLY_CANCELED,  # Using correct enum name
            6: OrderStatus.REJECTED,
            7: OrderStatus.EXPIRED
        }
        return status_mapping.get(status_num, OrderStatus.UNKNOWN)

    def _parse_protobuf_order_status(self, status_str: str) -> OrderStatus:
        """Parse protobuf order status to unified enum."""
        # Map MEXC protobuf status values
        status_mapping = {
            'NEW': OrderStatus.NEW,
            'PARTIALLY_FILLED': OrderStatus.PARTIALLY_FILLED,
            'FILLED': OrderStatus.FILLED,
            'CANCELED': OrderStatus.CANCELED,
            'PENDING_CANCEL': OrderStatus.PENDING_CANCEL,
            'REJECTED': OrderStatus.REJECTED,
            'EXPIRED': OrderStatus.EXPIRED
        }
        return status_mapping.get(status_str, OrderStatus.NEW)

    def _parse_protobuf_order_type_numeric(self, type_num: int):
        """Parse protobuf numeric order type to unified enum."""
        from structs.exchange import OrderType
        # Map MEXC protobuf numeric order type values
        type_mapping = {
            1: OrderType.LIMIT,
            2: OrderType.MARKET,
            3: OrderType.LIMIT_MAKER,
            4: OrderType.IMMEDIATE_OR_CANCEL,
            5: OrderType.FILL_OR_KILL,
            6: OrderType.STOP_LIMIT,
            7: OrderType.STOP_MARKET
        }
        return type_mapping.get(type_num, OrderType.LIMIT)

    def _parse_protobuf_order_type(self, type_str: str):
        """Parse protobuf order type to unified enum."""
        from structs.exchange import OrderType
        type_mapping = {
            'LIMIT': OrderType.LIMIT,
            'MARKET': OrderType.MARKET,
            'STOP_LOSS': OrderType.STOP_MARKET,
            'STOP_LOSS_LIMIT': OrderType.STOP_LIMIT,
            'TAKE_PROFIT': OrderType.STOP_MARKET,
            'TAKE_PROFIT_LIMIT': OrderType.STOP_LIMIT,
            'LIMIT_MAKER': OrderType.LIMIT_MAKER
        }
        return type_mapping.get(type_str, OrderType.MARKET)

    async def _handle_order_update(self, msg: dict):
        """Handle order execution reports."""
        try:
            # Extract order data from MEXC execution report
            # MEXC execution report format based on Binance-compatible structure
            
            order = Order(
                order_id=msg.get('i', ''),  # Order ID
                client_order_id=msg.get('c', ''),  # Client order ID
                symbol=MexcUtils.pair_to_symbol(pair_str),
                side=Side.BUY if msg.get('S') == 'BUY' else Side.SELL,
                order_type=self._parse_order_type(msg.get('o', '')),
                amount=float(msg.get('q', 0)),  # Original quantity
                price=float(msg.get('p', 0)),  # Price
                filled_amount=float(msg.get('z', 0)),  # Filled quantity
                remaining_amount=float(msg.get('q', 0)) - float(msg.get('z', 0)),
                status=self._parse_order_status(msg.get('X', '')),
                timestamp=int(msg.get('T', time.time() * 1000)),
                average_fill_price=float(msg.get('Z', 0)) / float(msg.get('z', 1)) if float(msg.get('z', 0)) > 0 else 0
            )
            
            self.logger.debug(f"Order update: {order.order_id} - {order.status}")
            
            # Call handler if provided
            if self.order_handler:
                await self.order_handler(order)
            else:
                await self.on_order_update(order)
                
        except Exception as e:
            self.logger.error(f"Error handling order update: {e}")

    async def _handle_balance_update(self, msg: dict):
        """Handle account balance updates."""
        try:
            # Extract balance changes from outboundAccountPosition
            balances = []
            
            # MEXC sends balance updates in 'B' array
            balance_data = msg.get('B', [])
            
            for balance_item in balance_data:
                asset_balance = AssetBalance(
                    asset=balance_item.get('a', ''),  # Asset name
                    free=float(balance_item.get('f', 0)),  # Free balance
                    locked=float(balance_item.get('l', 0))  # Locked balance
                )
                balances.append(asset_balance)
            
            if balances:
                self.logger.debug(f"Balance update: {len(balances)} assets")
                
                # Call handler if provided
                if self.balance_handler:
                    await self.balance_handler(balances)
                else:
                    await self.on_balance_update(balances)
                    
        except Exception as e:
            self.logger.error(f"Error handling balance update: {e}")

    async def _handle_trade_update(self, msg: dict):
        """Handle trade execution confirmations."""
        try:
            # Extract trade data from trade event
            trade = Trade(
                price=float(msg.get('p', 0)),
                amount=float(msg.get('q', 0)),
                side=Side.BUY if msg.get('S') == 'BUY' else Side.SELL,
                timestamp=int(msg.get('T', time.time() * 1000)),
                is_maker=msg.get('m', False)  # True if maker, False if taker
            )
            
            self.logger.debug(f"Trade update: {trade.amount} at {trade.price}")
            
            # Call handler if provided
            if self.trade_handler:
                await self.trade_handler(trade)
            else:
                await self.on_trade_update(trade)
                
        except Exception as e:
            self.logger.error(f"Error handling trade update: {e}")

    def _parse_order_type(self, type_str: str):
        """Parse MEXC order type string to unified enum."""
        from structs.exchange import OrderType
        type_mapping = {
            'LIMIT': OrderType.LIMIT,
            'MARKET': OrderType.MARKET,
            'STOP_LOSS': OrderType.STOP_MARKET,
            'STOP_LOSS_LIMIT': OrderType.STOP_LIMIT,
            'TAKE_PROFIT': OrderType.STOP_MARKET,
            'TAKE_PROFIT_LIMIT': OrderType.STOP_LIMIT,
            'LIMIT_MAKER': OrderType.LIMIT_MAKER
        }
        return type_mapping.get(type_str, OrderType.MARKET)

    def _parse_order_status(self, status_str: str) -> OrderStatus:
        """Parse MEXC order status string to unified enum."""
        status_mapping = {
            'NEW': OrderStatus.NEW,
            'PARTIALLY_FILLED': OrderStatus.PARTIALLY_FILLED,
            'FILLED': OrderStatus.FILLED,
            'CANCELED': OrderStatus.CANCELED,
            'PENDING_CANCEL': OrderStatus.PENDING_CANCEL,
            'REJECTED': OrderStatus.REJECTED,
            'EXPIRED': OrderStatus.EXPIRED
        }
        return status_mapping.get(status_str, OrderStatus.NEW)

    async def on_error(self, error: Exception):
        """Handle errors from the websocket."""
        self.logger.error(f"Private WebSocket error: {error}")
        
        # Check if this is an authentication error
        if 'unauthorized' in str(error).lower() or 'blocked' in str(error).lower():
            self.logger.error("Authentication error detected - regenerating listen key")
            try:
                await self._regenerate_listen_key()
            except Exception as regen_error:
                self.logger.error(f"Failed to regenerate listen key: {regen_error}")

    # Default event handlers (can be overridden by dependency injection)
    
    async def on_order_update(self, order: Order):
        """Default order update handler."""
        self.logger.info(f"Order update: {order.order_id} - {order.status} - {order.filled_amount}/{order.amount}")

    async def on_balance_update(self, balances: List[AssetBalance]):
        """Default balance update handler."""
        non_zero_balances = [b for b in balances if b.free > 0 or b.locked > 0]
        self.logger.info(f"Balance update: {len(non_zero_balances)} assets with non-zero balances")

    async def on_trade_update(self, trade: Trade):
        """Default trade update handler."""
        self.logger.info(f"Trade executed: {trade.side.name} {trade.amount} at {trade.price} ({'maker' if trade.is_maker else 'taker'})")