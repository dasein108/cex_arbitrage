import asyncio
import logging
import traceback
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Callable, Coroutine

import orjson
import websockets
from websockets import connect
from websockets.exceptions import ConnectionClosedError

from common.exceptions import ExchangeAPIError
from structs.exchange import (
    AssetBalance,
    AssetName,
    Order,
    Side,
    OrderStatus,
    OrderType,
    ExchangeName
)

# Import protobuf classes for private streams
from exchanges.mexc.pb.PushDataV3ApiWrapper_pb2 import PushDataV3ApiWrapper
from exchanges.mexc.pb.PrivateAccountV3Api_pb2 import PrivateAccountV3Api
from exchanges.mexc.pb.PrivateOrdersV3Api_pb2 import PrivateOrdersV3Api


class MexcWebSocketPrivateStream:
    """MEXC WebSocket stream for private account and order data
    
    Handles private WebSocket streams including:
    - Account balance updates
    - Order status updates  
    - Trade notifications
    
    Requires listen key from MEXC private exchange for authentication.
    """
    
    __slots__ = (
        'exchange_name', 'base_url', '_ws', '_is_stopped', 'on_message',
        'on_connected', 'on_restart', '_listen_key', 'timeout', '_loop',
        '_connection_retries', '_max_retries', 'logger'
    )
    
    def __init__(
        self,
        exchange_name: ExchangeName,
        listen_key: str,
        on_message: Callable[[Dict[str, Any]], Coroutine],
        timeout: float = 30.0,
        on_connected: Optional[Callable[[], Coroutine]] = None,
        on_restart: Optional[Callable[[], Coroutine]] = None,
        max_retries: int = 10
    ):
        self.exchange_name = exchange_name
        self.base_url = "wss://wbs-api.mexc.com/ws"
        self._ws: Optional[websockets.WebSocketServerProtocol] = None
        self._is_stopped = False
        self._listen_key = listen_key
        
        self.on_message = on_message
        self.on_connected = on_connected
        self.on_restart = on_restart
        self.timeout = timeout
        self._max_retries = max_retries
        self._connection_retries = 0
        
        self._loop = asyncio.get_event_loop()
        self.logger = logging.getLogger(f"mexc_ws_private_{exchange_name}")
        
        # Start the WebSocket task
        self._loop.create_task(self.run())

    @property 
    def is_connected(self) -> bool:
        """Check if WebSocket connection is open"""
        return (
            self._ws is not None and 
            self._ws.state == websockets.protocol.State.OPEN
        )

    async def run(self):
        """Main WebSocket event loop with automatic reconnection"""
        while not self._is_stopped:
            try:
                await self._connect()
                
                # Subscribe to private streams after connection
                await self._subscribe_private_streams()
                
                # Call connected callback
                if self.on_connected:
                    await self.on_connected()
                
                # Reset retry counter on successful connection
                self._connection_retries = 0
                
                # Start reading messages
                await self._read_socket()
                
            except Exception as e:
                self.logger.error(f"Private WebSocket error: {e}")
                await self._handle_connection_error(e)
                
            # Call restart callback
            if self.on_restart and not self._is_stopped:
                await self.on_restart()

    async def _connect(self):
        """Establish WebSocket connection with listen key authentication"""
        if self._connection_retries >= self._max_retries:
            raise ExchangeAPIError(
                500, 
                f"Max reconnection attempts ({self._max_retries}) exceeded"
            )
            
        try:
            if self._ws and not self._ws.closed:
                await self._ws.close()
                
            # Use listen key for private stream authentication
            private_url = f"{self.base_url}?listenKey={self._listen_key}"
            self.logger.info(f"Connecting to private stream: {private_url}")
            
            self._ws = await connect(
                private_url,
                ping_interval=20.0,
                ping_timeout=10.0,
                max_queue=5000,
                compression=None,  # Disable compression for speed
                max_size=10**7    # 10MB max message size
            )
            
            self.logger.info("Private WebSocket connected successfully")
            
        except Exception as e:
            self._connection_retries += 1
            raise ExchangeAPIError(500, f"Private connection failed: {e}")

    async def _handle_connection_error(self, error: Exception):
        """Handle connection errors with exponential backoff"""
        if self._is_stopped:
            return
            
        self._connection_retries += 1
        backoff_time = min(2 ** self._connection_retries, 30)  # Max 30s backoff
        
        self.logger.warning(
            f"Private connection error (attempt {self._connection_retries}/{self._max_retries}). "
            f"Reconnecting in {backoff_time}s: {error}"
        )
        
        await asyncio.sleep(backoff_time)

    async def _subscribe_private_streams(self):
        """Subscribe to private data streams"""
        if not self.is_connected:
            self.logger.warning("Cannot subscribe - not connected")
            return
            
        # Private streams are automatically subscribed when using listen key
        # MEXC private streams: spot@private.account.v3.api.pb and spot@private.orders.v3.api.pb
        self.logger.info("Private streams auto-subscribed with listen key")

    async def _read_socket(self):
        """Read messages from private WebSocket"""
        try:
            while not self._is_stopped and self.is_connected:
                message = await asyncio.wait_for(
                    self._ws.recv(), 
                    timeout=self.timeout
                )
                
                parsed_message = await self._parse_private_message(message)
                if parsed_message:
                    await self.on_message(parsed_message)
                    
        except asyncio.TimeoutError:
            self.logger.warning("Private WebSocket read timeout")
            raise ExchangeAPIError(408, "Private WebSocket read timeout")
        except ConnectionClosedError as e:
            self.logger.info(f"Private WebSocket connection closed: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Error reading private socket: {e}")
            traceback.print_exc()
            raise

    async def _parse_private_message(self, raw_message: Union[str, bytes]) -> Optional[Dict[str, Any]]:
        """Parse raw private WebSocket message"""
        try:
            if isinstance(raw_message, str):
                # JSON format
                stripped = raw_message.strip()
                if not stripped:
                    return None
                return orjson.loads(stripped)
            else:
                # Protobuf format for private streams
                return await self._parse_private_protobuf(raw_message)
                
        except Exception as e:
            self.logger.debug(f"Failed to parse private message: {e}")
            return None
    
    async def _parse_private_protobuf(self, message_bytes: bytes) -> Optional[Dict[str, Any]]:
        """Parse private protobuf messages"""
        try:
            wrapper = PushDataV3ApiWrapper()
            wrapper.ParseFromString(message_bytes)
            
            # Handle private account updates
            if wrapper.HasField('privateAccount'):
                return self._extract_account_data(wrapper.privateAccount)
            
            # Handle private order updates  
            elif wrapper.HasField('privateOrders'):
                return self._extract_order_data(wrapper.privateOrders)
            
            # Generic message
            return {'channel': wrapper.channel}
            
        except Exception as e:
            self.logger.debug(f"Failed to parse private protobuf: {e}")
            return None
    
    def _extract_account_data(self, account_data: PrivateAccountV3Api) -> Dict[str, Any]:
        """Extract account balance data from protobuf"""
        return {
            'type': 'account_update',
            'data': {
                'asset': account_data.vcoinName,
                'balance': float(account_data.balanceAmount),
                'balance_change': float(account_data.balanceAmountChange),
                'frozen': float(account_data.frozenAmount),
                'frozen_change': float(account_data.frozenAmountChange),
                'update_type': account_data.type,
                'timestamp': account_data.time
            }
        }
    
    def _extract_order_data(self, order_data: PrivateOrdersV3Api) -> Dict[str, Any]:
        """Extract order update data from protobuf"""
        return {
            'type': 'order_update',
            'data': {
                'order_id': order_data.id,
                'client_order_id': order_data.clientId,
                'symbol': order_data.market if order_data.HasField('market') else None,
                'price': float(order_data.price),
                'quantity': float(order_data.quantity),
                'amount': float(order_data.amount),
                'avg_price': float(order_data.avgPrice),
                'order_type': order_data.orderType,
                'trade_type': order_data.tradeType,
                'is_maker': order_data.isMaker,
                'remain_amount': float(order_data.remainAmount),
                'remain_quantity': float(order_data.remainQuantity),
                'cumulative_quantity': float(order_data.cumulativeQuantity),
                'cumulative_amount': float(order_data.cumulativeAmount),
                'status': order_data.status,
                'create_time': order_data.createTime,
                'state': order_data.state if order_data.HasField('state') else None
            }
        }

    def update_listen_key(self, new_listen_key: str):
        """Update listen key for authentication"""
        self._listen_key = new_listen_key
        self.logger.info("Listen key updated")

    async def stop(self):
        """Stop private WebSocket connection"""
        self._is_stopped = True
        
        if self._ws and not self._ws.closed:
            await self._ws.close()
            
        self.logger.info("Private WebSocket stopped")

    def get_health_status(self) -> Dict[str, Any]:
        """Get private connection health status"""
        return {
            'exchange': self.exchange_name,
            'stream_type': 'private',
            'is_connected': self.is_connected,
            'connection_retries': self._connection_retries,
            'max_retries': self._max_retries,
            'listen_key_length': len(self._listen_key) if self._listen_key else 0
        }