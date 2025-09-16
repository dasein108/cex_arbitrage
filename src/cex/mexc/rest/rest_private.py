"""
MEXC Private REST API Implementation

Focused REST-only client for MEXC private API endpoints.
Optimized for direct trading API calls without WebSocket features.

Key Features:
- Pure REST API implementation for trading operations
- Sub-10ms response times for order management
- MEXC-specific HMAC-SHA256 authentication
- Zero-copy JSON parsing with msgspec
- Unified cex compliance

MEXC Private API Specifications:
- Base URL: https://api.mexc.com  
- Authentication: HMAC-SHA256 with query string parameters
- Rate Limits: 20 requests/second
- Required parameters: recvWindow, timestamp, signature

Threading: Fully async/await compatible, thread-safe
Memory: O(1) per request, optimized for trading operations
"""

import hashlib
import hmac
import urllib.parse
import time
from typing import Dict, List, Optional, Any, Tuple
import msgspec

from cex.mexc.structs.exchange import (
    MexcAccountResponse, MexcOrderResponse
)
from structs.exchange import (
    Symbol, Order, OrderId, OrderType, Side, AssetBalance,
    AssetName, TimeInForce
)
from core.exceptions.exchange import BaseExchangeError
from core.config.structs import ExchangeConfig

from core.cex.rest.spot.base_rest_spot_private import PrivateExchangeSpotRestInterface
from .rest_config import MexcConfig
from .custom_exception_handler import handle_custom_exception
from core.transport.rest.structs import HTTPMethod
from core.cex.services.mapping_factory import ExchangeMappingsFactory


class MexcPrivateSpotRest(PrivateExchangeSpotRestInterface):
    """
    MEXC private REST API client focused on trading operations.
    
    Provides access to authenticated trading endpoints without WebSocket features.
    Optimized for high-frequency trading operations with minimal overhead.
    """

    def __init__(self, config: ExchangeConfig):
        """
        Initialize MEXC private REST client with dependency injection.
        
        Args:
            config: ExchangeConfig with API credentials
        """
        super().__init__(config, MexcConfig.rest_config['default'], handle_custom_exception)

    def generate_auth_signature(self, params: Dict[str, Any]) -> str:
        """
        Generate MEXC HMAC-SHA256 signature for authentication.
        
        Args:
            params: Request parameters including timestamp and recvWindow
            
        Returns:
            HMAC-SHA256 signature string
        """
        # Create query string from parameters
        query_string = urllib.parse.urlencode(params)

        # Generate HMAC-SHA256 signature
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return signature

    async def add_auth(self, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Tuple[Dict[str, Any], Dict[str, str]]:
        # Prepare parameters
        request_params = params.copy() if params else {}

        # Add required MEXC authentication parameters
        request_params['timestamp'] = round(time.time() * 1000)
        request_params['recvWindow'] = 15000

        # Generate signature
        signature = self.generate_auth_signature(request_params)
        request_params['signature'] = signature

        # Prepare headers with API key and required content-type for MEXC
        auth_headers = {
            'X-MEXC-APIKEY': self.api_key,
            'Content-Type': 'application/json'  # MEXC requires this for authenticated requests
        }
        
        # Merge with any existing headers, allowing them to override if needed
        if headers:
            auth_headers.update(headers)

        return request_params, auth_headers

    async def get_account_balance(self) -> List[AssetBalance]:
        """
        Get account balance for all assets.
        
        Returns:
            List of AssetBalance objects with free and locked amounts
            
        Raises:
            ExchangeAPIError: If unable to fetch account balance
        """
        response_data = await self.request(
            HTTPMethod.GET,
            '/api/v3/account',
            config=MexcConfig.rest_config['account'],
            auth=True
        )

        account_data = msgspec.convert(response_data, MexcAccountResponse)

        # Transform to unified format
        balances = []
        for mexc_balance in account_data.balances:
            if float(mexc_balance.free) > 0 or float(mexc_balance.locked) > 0:
                balance = AssetBalance(
                    asset=AssetName(mexc_balance.asset),
                    available=float(mexc_balance.available),
                    free=float(mexc_balance.free),
                    locked=float(mexc_balance.locked)
                )
                balances.append(balance)

        self.logger.debug(f"Retrieved {len(balances)} non-zero balances")
        return balances

    async def get_asset_balance(self, asset: AssetName) -> Optional[AssetBalance]:
        """
        Get balance for a specific asset.
        
        Args:
            asset: Asset name to get balance for
            
        Returns:
            AssetBalance for the asset or None if not found
            
        Raises:
            ExchangeAPIError: If unable to fetch account balance
        """
        all_balances = await self.get_account_balance()

        # Find the specific asset balance
        for balance in all_balances:
            if balance.asset == asset:
                return balance

        # Return None if asset not found or has zero balance
        return None

    async def place_order(
            self,
            symbol: Symbol,
            side: Side,
            order_type: OrderType,
            amount: Optional[float] = None,
            price: Optional[float] = None,
            quote_quantity: Optional[float] = None,
            time_in_force: Optional[TimeInForce] = None,
            stop_price: Optional[float] = None,
            iceberg_qty: Optional[float] = None,
            new_order_resp_type: Optional[str] = None
    ) -> Order:
        """
        Place a new order with comprehensive MEXC API parameters.
        
        Args:
            symbol: Symbol to trade
            side: Order side (BUY/SELL)
            order_type: Order type (MARKET/LIMIT/etc)
            amount: Base asset quantity (optional for MARKET buy orders)
            price: Order price (required for LIMIT orders)
            quote_quantity: Quote asset quantity (for MARKET buy orders)
            time_in_force: Time in force (GTC/IOC/FOK/GTD)
            stop_price: Stop price for STOP orders
            iceberg_qty: Iceberg order quantity
            new_order_resp_type: Response type (ACK/RESULT/FULL)
            
        Returns:
            Order object with details of the placed order
            
        Raises:
            ExchangeAPIError: If unable to place order
            ValueError: If required parameters are missing
        """
        pair = self.symbol_mapper.symbol_to_pair(symbol)

        # Validate required parameters based on order type
        if order_type in [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.STOP_LIMIT]:
            if price is None:
                raise ValueError(f"Price is required for {order_type.name} orders")

        if order_type in [OrderType.STOP_LIMIT, OrderType.STOP_MARKET]:
            if stop_price is None:
                raise ValueError(f"Stop price is required for {order_type.name} orders")

        # For MARKET buy orders, either amount or quote_quantity is required
        if order_type == OrderType.MARKET and side == Side.BUY:
            if amount is None and quote_quantity is None:
                raise ValueError("Either amount or quote_quantity is required for MARKET buy orders")
        elif amount is None:
            raise ValueError("Amount is required for this order type")

        # Prepare cex order parameters
        params = {
            'symbol': pair,
            'side': self._mappings.get_exchange_side(side),
            'type': self._mappings.get_exchange_order_type(order_type)
        }

        # Add quantity parameters
        if amount is not None:
            params['quantity'] = self._mappings.format_quantity(amount)

        if quote_quantity is not None:
            params['quoteOrderQty'] = self._mappings.format_quantity(quote_quantity)

        # Add price parameters
        if price is not None:
            params['price'] = self._mappings.format_price(price)

        if stop_price is not None:
            params['stopPrice'] = self._mappings.format_price(stop_price)

        # Add time in force (default to GTC if not specified for applicable order types)
        if order_type in [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.STOP_LIMIT]:
            tif = time_in_force or TimeInForce.GTC
            params['timeInForce'] = self._mappings.get_exchange_time_in_force(tif)
        elif time_in_force is not None:
            params['timeInForce'] = self._mappings.get_exchange_time_in_force(time_in_force)

        # Add optional parameters
        if iceberg_qty is not None:
            params['icebergQty'] = self._mappings.format_quantity(iceberg_qty)

        if new_order_resp_type is not None:
            params['newOrderRespType'] = new_order_resp_type

        response_data = await self.request(
            HTTPMethod.POST,
            '/api/v3/order',
            params=params,
            config=MexcConfig.rest_config['order'],
            auth=True
        )

        order_response = msgspec.convert(response_data, MexcOrderResponse)

        # Transform to unified format
        unified_order = self._mappings.transform_exchange_order_to_unified(order_response)

        # Log order placement with relevant details
        amount_str = f"{amount} {symbol.base}" if amount else f"{quote_quantity} {symbol.quote}"
        price_str = f"at {price}" if price else "market price"
        self.logger.info(f"Placed {side.name} {order_type.name} order for {amount_str} {price_str}")
        return unified_order

    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """
        Cancel an existing order.
        
        Args:
            symbol: Symbol of the order
            order_id: ID of the order to cancel
            
        Returns:
            Order object with cancellation details
            
        Raises:
            ExchangeAPIError: If unable to cancel order
        """
        pair = self.symbol_mapper.symbol_to_pair(symbol)

        params = {
            'symbol': pair,
            'orderId': str(order_id)
        }

        response_data = await self.request(
            HTTPMethod.DELETE,
            '/api/v3/order',
            params=params,
            config=MexcConfig.rest_config['order'],
            auth=True
        )

        order_response = msgspec.convert(response_data, MexcOrderResponse)

        # Transform to unified format
        unified_order = self._mappings.transform_exchange_order_to_unified(order_response)

        self.logger.info(f"Cancelled order {order_id} for {symbol.base}/{symbol.quote}")
        return unified_order

    async def cancel_all_orders(self, symbol: Symbol) -> List[Order]:
        """
        Cancel all open orders for a symbol.
        
        Args:
            symbol: Symbol to cancel all orders for
            
        Returns:
            List of cancelled Order objects
            
        Raises:
            ExchangeAPIError: If unable to cancel orders
        """
        pair = self.symbol_mapper.symbol_to_pair(symbol)

        params = {'symbol': pair}

        response_data = await self.request(
            HTTPMethod.DELETE,
            '/api/v3/openOrders',
            params=params,
            config=MexcConfig.rest_config['order'],
            auth=True
        )

        order_responses = msgspec.convert(response_data, list[MexcOrderResponse])

        # Transform to unified format
        cancelled_orders = []
        for order_response in order_responses:
            unified_order = self._mappings.transform_exchange_order_to_unified(order_response)
            cancelled_orders.append(unified_order)

        self.logger.info(f"Cancelled {len(cancelled_orders)} orders for {symbol.base}/{symbol.quote}")
        return cancelled_orders

    async def get_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """
        Get order status by ID.
        
        Args:
            symbol: Symbol of the order
            order_id: ID of the order to query
            
        Returns:
            Order object with current status
            
        Raises:
            ExchangeAPIError: If unable to fetch order
        """
        pair = self.symbol_mapper.symbol_to_pair(symbol)

        params = {
            'symbol': pair,
            'orderId': str(order_id)
        }

        response_data = await self.request(
            HTTPMethod.GET,
            '/api/v3/order',
            params=params,
            config=MexcConfig.rest_config['order'],
            auth=True
        )

        order_response = msgspec.convert(response_data, MexcOrderResponse)

        # Transform to unified format
        unified_order = self._mappings.transform_exchange_order_to_unified(order_response)

        self.logger.debug(f"Retrieved order {order_id} status: {unified_order.status}")
        return unified_order

    async def get_open_orders(self, symbol: Optional[Symbol] = None) -> List[Order]:
        """
        Get all open orders, optionally filtered by symbol.
        
        Args:
            symbol: Optional symbol to filter orders
            
        Returns:
            List of open Order objects
            
        Raises:
            ExchangeAPIError: If unable to fetch orders
        """
        params = {}
        if symbol:
            params['symbol'] = self.symbol_mapper.symbol_to_pair(symbol)

        response_data = await self.request(
            HTTPMethod.GET,
            '/api/v3/openOrders',
            params=params,
            config=MexcConfig.rest_config['my_orders'],
            auth=True
        )

        order_responses = msgspec.convert(response_data, list[MexcOrderResponse])

        # Transform to unified format
        open_orders = []
        for order_response in order_responses:
            unified_order = self._mappings.transform_exchange_order_to_unified(order_response)
            open_orders.append(unified_order)

        symbol_str = f" for {symbol.base}/{symbol.quote}" if symbol else ""
        self.logger.debug(f"Retrieved {len(open_orders)} open orders{symbol_str}")
        return open_orders

    # async def modify_order(
    #         self,
    #         symbol: Symbol,
    #         order_id: OrderId,
    #         amount: Optional[float] = None,
    #         price: Optional[float] = None,
    #         quote_quantity: Optional[float] = None,
    #         time_in_force: Optional[TimeInForce] = None,
    #         stop_price: Optional[float] = None
    # ) -> Order:
    #     """
    #     Modify an existing order.
    #
    #     Note: MEXC doesn't support direct order modification.
    #     This method cancels the existing order and places a new one.
    #
    #     Args:
    #         symbol: Symbol of the order
    #         order_id: ID of the order to modify
    #         amount: New order amount (optional)
    #         price: New order price (optional)
    #         quote_quantity: New quote quantity (optional)
    #         time_in_force: New time in force (optional)
    #         stop_price: New stop price (optional)
    #
    #     Returns:
    #         New Order object after modification
    #
    #     Raises:
    #         ExchangeAPIError: If unable to modify order
    #     """
    #     # Get current order details
    #     current_order = await self.get_order(symbol, order_id)
    #
    #     # Cancel existing order
    #     await self.cancel_order(symbol, order_id)
    #
    #     # Place new order with modified parameters
    #     new_amount = amount if amount is not None else current_order.amount
    #     new_price = price if price is not None else current_order.price
    #
    #     new_order = await self.place_order(
    #         symbol=symbol,
    #         side=current_order.side,
    #         order_type=current_order.order_type,
    #         amount=new_amount,
    #         price=new_price,
    #         quote_quantity=quote_quantity,
    #         time_in_force=time_in_force,
    #         stop_price=stop_price
    #     )
    #
    #     self.logger.info(f"Modified order {order_id} -> {new_order.order_id}")
    #     return new_order

    async def create_listen_key(self) -> str:
        """
        Create a new listen key for user data stream.
        
        Returns:
            Listen key string for WebSocket user data stream
            
        Raises:
            ExchangeAPIError: If unable to create listen key
        """
        response_data = await self.request(
            HTTPMethod.POST,
            '/api/v3/userDataStream',
            config=MexcConfig.rest_config['account'],
            auth=True
        )

        listen_key = response_data.get('listenKey')
        if not listen_key:
            raise BaseExchangeError(500, "Failed to create listen key - no key in response")

        self.logger.debug("Created new listen key")
        return listen_key

    async def get_all_listen_keys(self) -> Dict[str, Any]:
        """
        Get all active listen keys.
        
        Returns:
            Dictionary containing active listen keys and their metadata
            
        Raises:
            ExchangeAPIError: If unable to fetch listen keys
        """
        response_data = await self.request(
            HTTPMethod.GET,
            '/api/v3/userDataStream',
            config=MexcConfig.rest_config['account'],
            auth=True
        )

        self.logger.debug("Retrieved all listen keys")
        return response_data

    async def keep_alive_listen_key(self, listen_key: str) -> None:
        """
        Keep a listen key alive to prevent expiration.
        
        Args:
            listen_key: The listen key to keep alive
            
        Raises:
            ExchangeAPIError: If unable to keep alive listen key
        """
        params = {'listenKey': listen_key}

        await self.request(
            HTTPMethod.PUT,
            '/api/v3/userDataStream',
            params=params,
            config=MexcConfig.rest_config['account'],
            auth=True
        )

        self.logger.debug(f"Kept alive listen key: {listen_key[:8]}...")

    async def delete_listen_key(self, listen_key: str) -> None:
        """
        Delete/close a listen key.
        
        Args:
            listen_key: The listen key to delete
            
        Raises:
            ExchangeAPIError: If unable to delete listen key
        """
        params = {'listenKey': listen_key}

        await self.request(
            HTTPMethod.DELETE,
            '/api/v3/userDataStream',
            params=params,
            config=MexcConfig.rest_config['account'],
            auth=True
        )

        self.logger.debug(f"Deleted listen key: {listen_key[:8]}...")