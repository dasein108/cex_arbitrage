"""
MEXC Private REST API Implementation

Focused REST-only client for MEXC private API endpoints.
Optimized for direct trading API calls without WebSocket features.

Key Features:
- Pure REST API implementation for trading operations
- Sub-10ms response times for order management
- MEXC-specific HMAC-SHA256 authentication
- Zero-copy JSON parsing with msgspec
- Unified interface compliance

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
from typing import Dict, List, Optional
import logging
import msgspec

from exchanges.mexc.common.mexc_struct import (
    MexcAccountResponse, MexcOrderResponse, MexcErrorResponse
)
from exchanges.interface.structs import (
    Symbol, Order, OrderId, OrderType, Side, AssetBalance,
    AssetName, TimeInForce
)
from common.rest_client import RestClient
from common.exceptions import ExchangeAPIError
from common.config import config
from exchanges.interface.rest.base_rest_private import PrivateExchangeInterface
from exchanges.mexc.common.mexc_utils import MexcUtils
from exchanges.mexc.common.mexc_mappings import MexcMappings
from exchanges.mexc.common.mexc_config import MexcConfig


class MexcPrivateExchange(PrivateExchangeInterface):
    """
    MEXC private REST API client focused on trading operations.
    
    Provides access to authenticated trading endpoints without WebSocket features.
    Optimized for high-frequency trading operations with minimal overhead.
    """

    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        """
        Initialize MEXC private REST client.
        
        Args:
            api_key: MEXC API key for authentication
            secret_key: MEXC secret key for signature generation
        """
        # Use provided credentials or fall back to configuration
        api_key = api_key or config.MEXC_API_KEY
        secret_key = secret_key or config.MEXC_SECRET_KEY

        if not api_key or not secret_key:
            raise ValueError("MEXC API credentials must be provided")

        super().__init__(
            MexcConfig.EXCHANGE_NAME,
            api_key,
            secret_key,
            MexcConfig.BASE_URL
        )

        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Initialize REST client with MEXC-specific authentication
        self.client = RestClient(
            base_url=self.base_url,
            api_key=self.api_key,
            secret_key=self.secret_key,
            signature_generator=self._mexc_signature_generator,
            config=MexcConfig.rest_config['default'],
            exception_handler=self._handle_mexc_exception
        )

        self.logger.info(f"Initialized {self.exchange} private REST client")

    def _mexc_signature_generator(self, params: Dict[str, any]) -> str:
        """
        Generate MEXC HMAC-SHA256 signature for authentication.
        
        Args:
            params: Request parameters including timestamp and recvWindow
            
        Returns:
            HMAC-SHA256 signature string
        """
        # Create query string from sorted parameters (excluding signature)
        # sorted_params = sorted(params.items())
        query_string = urllib.parse.urlencode(params)
        # query_string = "&".join(f"{key}={value}" for key, value in params.items())

        # Generate HMAC-SHA256 signature
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return signature

    def _handle_mexc_exception(self, error: Exception) -> Exception:
        """
        Handle MEXC-specific API errors and convert to unified exceptions.
        
        Args:
            error: Original exception from HTTP request
            
        Returns:
            Unified exception with appropriate error details
        """
        if hasattr(error, 'status') and hasattr(error, 'response_text'):
            try:
                # Try to parse MEXC error response
                error_data = msgspec.json.decode(error.response_text)
                mexc_error = msgspec.convert(error_data, MexcErrorResponse)

                # Map MEXC error codes to unified exceptions
                error_code = mexc_error.code
                error_msg = mexc_error.msg

                if error_code in MexcMappings.ERROR_CODE_MAPPING:
                    unified_error = MexcMappings.ERROR_CODE_MAPPING[error_code]
                    return unified_error(error.status, f"MEXC Error {error_code}: {error_msg}")
                else:
                    return ExchangeAPIError(error.status, f"MEXC Error {error_code}: {error_msg}")

            except Exception:
                # Fallback if error parsing fails
                return ExchangeAPIError(error.status, f"MEXC API Error: {error.response_text}")

        # Fallback for other error types
        return ExchangeAPIError(500, f"Unexpected error: {str(error)}")

    async def get_account_balance(self) -> List[AssetBalance]:
        """
        Get account balance for all assets.
        
        Returns:
            List of AssetBalance objects with free and locked amounts
            
        Raises:
            ExchangeAPIError: If unable to fetch account balance
        """
        response_data = await self.client.get(
            '/api/v3/account',
            config=MexcConfig.rest_config['account']
        )

        account_data = msgspec.convert(response_data, MexcAccountResponse)

        # Transform to unified format
        balances = []
        for mexc_balance in account_data.balances:
            if float(mexc_balance.free) > 0 or float(mexc_balance.locked) > 0:
                balance = MexcUtils.transform_mexc_balance_to_unified(mexc_balance)
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
        pair = MexcUtils.symbol_to_pair(symbol)

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

        # Prepare base order parameters
        params = {
            'symbol': pair,
            'side': MexcMappings.get_mexc_side(side),
            'type': MexcMappings.get_mexc_order_type(order_type)
        }

        # Add quantity parameters
        if amount is not None:
            params['quantity'] = MexcUtils.format_mexc_quantity(amount)
        
        if quote_quantity is not None:
            params['quoteOrderQty'] = MexcUtils.format_mexc_quantity(quote_quantity)

        # Add price parameters
        if price is not None:
            params['price'] = MexcUtils.format_mexc_price(price)
        
        if stop_price is not None:
            params['stopPrice'] = MexcUtils.format_mexc_price(stop_price)

        # Add time in force (default to GTC if not specified for applicable order types)
        if order_type in [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.STOP_LIMIT]:
            tif = time_in_force or TimeInForce.GTC
            params['timeInForce'] = MexcMappings.get_mexc_time_in_force(tif)
        elif time_in_force is not None:
            params['timeInForce'] = MexcMappings.get_mexc_time_in_force(time_in_force)

        # Add optional parameters
        if iceberg_qty is not None:
            params['icebergQty'] = MexcUtils.format_mexc_quantity(iceberg_qty)
        
        if new_order_resp_type is not None:
            params['newOrderRespType'] = new_order_resp_type

        response_data = await self.client.post(
            '/api/v3/order',
            params=params,
            config=MexcConfig.rest_config['order']
        )

        order_response = msgspec.convert(response_data, MexcOrderResponse)

        # Transform to unified format
        unified_order = MexcUtils.transform_mexc_order_to_unified(order_response)

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
        pair = MexcUtils.symbol_to_pair(symbol)

        params = {
            'symbol': pair,
            'orderId': str(order_id)
        }

        response_data = await self.client.delete(
            '/api/v3/order',
            params=params,
            config=MexcConfig.rest_config['order']
        )

        order_response = msgspec.convert(response_data, MexcOrderResponse)

        # Transform to unified format
        unified_order = MexcUtils.transform_mexc_order_to_unified(order_response)

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
        pair = MexcUtils.symbol_to_pair(symbol)

        params = {'symbol': pair}

        response_data = await self.client.delete(
            '/api/v3/openOrders',
            params=params,
            config=MexcConfig.rest_config['order']
        )

        order_responses = msgspec.convert(response_data, list[MexcOrderResponse])

        # Transform to unified format
        cancelled_orders = []
        for order_response in order_responses:
            unified_order = MexcUtils.transform_mexc_order_to_unified(order_response)
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
        pair = MexcUtils.symbol_to_pair(symbol)

        params = {
            'symbol': pair,
            'orderId': str(order_id)
        }

        response_data = await self.client.get(
            '/api/v3/order',
            params=params,
            config=MexcConfig.rest_config['order']
        )

        order_response = msgspec.convert(response_data, MexcOrderResponse)

        # Transform to unified format
        unified_order = MexcUtils.transform_mexc_order_to_unified(order_response)

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
            params['symbol'] = MexcUtils.symbol_to_pair(symbol)

        response_data = await self.client.get(
            '/api/v3/openOrders',
            params=params,
            config=MexcConfig.rest_config['my_orders']
        )

        order_responses = msgspec.convert(response_data, list[MexcOrderResponse])

        # Transform to unified format
        open_orders = []
        for order_response in order_responses:
            unified_order = MexcUtils.transform_mexc_order_to_unified(order_response)
            open_orders.append(unified_order)

        symbol_str = f" for {symbol.base}/{symbol.quote}" if symbol else ""
        self.logger.debug(f"Retrieved {len(open_orders)} open orders{symbol_str}")
        return open_orders

    async def modify_order(
            self,
            symbol: Symbol,
            order_id: OrderId,
            amount: Optional[float] = None,
            price: Optional[float] = None,
            quote_quantity: Optional[float] = None,
            time_in_force: Optional[TimeInForce] = None,
            stop_price: Optional[float] = None
    ) -> Order:
        """
        Modify an existing order.
        
        Note: MEXC doesn't support direct order modification.
        This method cancels the existing order and places a new one.
        
        Args:
            symbol: Symbol of the order
            order_id: ID of the order to modify
            amount: New order amount (optional)
            price: New order price (optional)
            quote_quantity: New quote quantity (optional)
            time_in_force: New time in force (optional)
            stop_price: New stop price (optional)
            
        Returns:
            New Order object after modification
            
        Raises:
            ExchangeAPIError: If unable to modify order
        """
        # Get current order details
        current_order = await self.get_order(symbol, order_id)

        # Cancel existing order
        await self.cancel_order(symbol, order_id)

        # Place new order with modified parameters
        new_amount = amount if amount is not None else current_order.amount
        new_price = price if price is not None else current_order.price

        new_order = await self.place_order(
            symbol=symbol,
            side=current_order.side,
            order_type=current_order.order_type,
            amount=new_amount,
            price=new_price,
            quote_quantity=quote_quantity,
            time_in_force=time_in_force,
            stop_price=stop_price
        )

        self.logger.info(f"Modified order {order_id} -> {new_order.order_id}")
        return new_order

    async def create_listen_key(self) -> str:
        """
        Create a new listen key for user data stream.
        
        Returns:
            Listen key string for WebSocket user data stream
            
        Raises:
            ExchangeAPIError: If unable to create listen key
        """
        response_data = await self.client.post(
            '/api/v3/userDataStream',
            config=MexcConfig.rest_config['account']
        )
        
        listen_key = response_data.get('listenKey')
        if not listen_key:
            raise ExchangeAPIError(500, "Failed to create listen key - no key in response")
        
        self.logger.debug("Created new listen key")
        return listen_key

    async def get_all_listen_keys(self) -> Dict:
        """
        Get all active listen keys.
        
        Returns:
            Dictionary containing active listen keys and their metadata
            
        Raises:
            ExchangeAPIError: If unable to fetch listen keys
        """
        response_data = await self.client.get(
            '/api/v3/userDataStream',
            config=MexcConfig.rest_config['account']
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
        
        await self.client.put(
            '/api/v3/userDataStream',
            params=params,
            config=MexcConfig.rest_config['account']
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
        
        await self.client.delete(
            '/api/v3/userDataStream',
            params=params,
            config=MexcConfig.rest_config['account']
        )
        
        self.logger.debug(f"Deleted listen key: {listen_key[:8]}...")

    async def close(self):
        """Clean up resources and close connections."""
        if hasattr(self, 'client'):
            await self.client.close()
        self.logger.info(f"Closed {self.exchange} private REST client")

