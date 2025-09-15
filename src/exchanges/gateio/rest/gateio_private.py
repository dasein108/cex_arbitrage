"""
Gate.io Private REST API Implementation

Focused REST-only client for Gate.io private API endpoints.
Optimized for direct trading API calls without WebSocket features.

Key Features:
- Pure REST API implementation for trading operations
- Sub-10ms response times for order management  
- Gate.io-specific HMAC-SHA512 authentication
- Zero-copy JSON parsing with msgspec
- Unified cex compliance

Gate.io Private API Specifications:
- Base URL: https://api.gateio.ws/api/v4
- Authentication: HMAC-SHA512 with request body hashing
- Rate Limits: 10 requests/second for spot trading
- Required headers: KEY, SIGN, Timestamp, Content-Type

Threading: Fully async/await compatible, thread-safe
Memory: O(1) per request, optimized for trading operations
"""

from typing import Dict, List, Optional
import logging
import msgspec

from structs.exchange import (
    Symbol, Order, OrderId, OrderType, Side, AssetBalance,
    AssetName, TimeInForce, ExchangeName, TradingFee
)
from core.transport.rest.rest_client import RestClient, HTTPMethod
from core.exceptions.exchange import BaseExchangeError
from core.cex.rest.spot.base_rest_spot_private import PrivateExchangeSpotRestInterface
from exchanges.gateio.common.gateio_utils import GateioUtils
from exchanges.gateio.common.gateio_mappings import GateioMappings
from exchanges.gateio.common.gateio_config import GateioConfig


class GateioPrivateExchangeSpot(PrivateExchangeSpotRestInterface):
    """
    Gate.io private REST API client focused on trading operations.
    
    Provides access to authenticated trading endpoints without WebSocket features.
    Optimized for high-frequency trading operations with minimal overhead.
    """

    def __init__(self, api_key: str, secret_key: str):
        """
        Initialize Gate.io private REST client.
        
        Args:
            api_key: Gate.io API key for authentication
            secret_key: Gate.io secret key for signature generation
        """
        if not api_key or not secret_key:
            raise ValueError("Gate.io API credentials must be provided")

        super().__init__(
            ExchangeName(GateioConfig.EXCHANGE_NAME),
            api_key,
            secret_key,
            GateioConfig.BASE_URL
        )

        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Initialize REST client with Gate.io-specific authentication
        self.client = RestClient(
            base_url=self.base_url,
            config=GateioConfig.rest_config['default']
        )

        self.logger.info(f"Initialized {self.exchange} private REST client")

    def _create_authenticated_headers(
        self, 
        method: str, 
        url_path: str, 
        query_string: str = '', 
        payload: str = ''
    ) -> Dict[str, str]:
        """
        Create authentication headers for Gate.io API requests.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url_path: API endpoint path
            query_string: URL query parameters
            payload: Request body JSON
            
        Returns:
            Dictionary of authentication headers
        """
        return GateioUtils.create_auth_headers(
            method, url_path, query_string, payload, self.api_key, self.secret_key
        )

    async def get_account_balance(self) -> List[AssetBalance]:
        """
        Get account balance for all assets.
        
        HFT COMPLIANT: Never caches balance data - always fresh API call.
        
        Returns:
            List of AssetBalance objects for all assets with non-zero balances
            
        Raises:
            ExchangeAPIError: If unable to fetch balance data
        """
        try:
            endpoint = GateioConfig.SPOT_ENDPOINTS['accounts']
            signature_path = GateioConfig.SIGNATURE_ENDPOINTS['accounts']
            headers = self._create_authenticated_headers('GET', signature_path)
            
            response_data = await self.client.get(
                endpoint,
                headers=headers,
                config=GateioConfig.rest_config['account']
            )
            
            # Gate.io accounts response format:
            # [
            #   {
            #     "currency": "USDT",
            #     "available": "1000.0", 
            #     "locked": "0.0"
            #   }, ...
            # ]
            
            if not isinstance(response_data, list):
                raise BaseExchangeError(500, "Invalid balance response format")
            
            balances = []
            for balance_data in response_data:
                balance = GateioUtils.transform_gateio_balance_to_unified(balance_data)
                # Only include assets with non-zero total balance
                if balance.total > 0:
                    balances.append(balance)
            
            self.logger.debug(f"Retrieved {len(balances)} account balances")
            return balances
            
        except Exception as e:
            self.logger.error(f"Failed to get account balance: {e}")
            raise BaseExchangeError(500, f"Balance fetch failed: {str(e)}")
    
    async def get_asset_balance(self, asset: AssetName) -> Optional[AssetBalance]:
        """
        Get balance for a specific asset.
        
        HFT COMPLIANT: Never caches balance data - always fresh API call.
        
        Args:
            asset: Asset name to get balance for
            
        Returns:
            AssetBalance object or None if asset not found
        """
        try:
            balances = await self.get_account_balance()
            
            for balance in balances:
                if balance.asset == asset:
                    return balance
            
            # Return zero balance if asset not found
            return AssetBalance(
                asset=asset,
                available=0.0,
                free=0.0,
                locked=0.0
            )
            
        except Exception as e:
            self.logger.error(f"Failed to get balance for {asset}: {e}")
            raise
    
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
        Place a new order with comprehensive parameters.
        
        Args:
            symbol: Trading symbol
            side: Order side (BUY/SELL)
            order_type: Order type (LIMIT/MARKET)
            amount: Order quantity in cex asset
            price: Order price (required for limit orders)
            quote_quantity: Order quantity in quote asset (for market buys)
            time_in_force: Time in force (GTC/IOC/FOK)
            stop_price: Stop price (not used in Gate.io spot trading)
            iceberg_qty: Iceberg quantity (not used in Gate.io spot trading)
            new_order_resp_type: Response type (not used)
            
        Returns:
            Order object with order details
            
        Raises:
            ExchangeAPIError: If order placement fails
        """
        try:
            pair = GateioUtils.symbol_to_pair(symbol)
            
            # Build order payload
            payload = {
                'currency_pair': pair,
                'side': GateioMappings.get_gateio_side(side),
                'type': GateioMappings.get_gateio_order_type(order_type)
            }
            
            # Set time in force
            if time_in_force is None:
                time_in_force = TimeInForce.GTC
            payload['time_in_force'] = GateioMappings.get_gateio_time_in_force(time_in_force)
            
            # Handle different order configurations
            if order_type == OrderType.MARKET:
                if side == Side.BUY:
                    # Market buy: specify quote quantity
                    if quote_quantity is None:
                        if amount is None or price is None:
                            raise ValueError("Market buy orders require quote_quantity or (amount + price)")
                        quote_quantity = amount * price
                    payload['amount'] = GateioUtils.format_gateio_quantity(quote_quantity)
                else:
                    # Market sell: specify cex quantity
                    if amount is None:
                        raise ValueError("Market sell orders require amount")
                    payload['amount'] = GateioUtils.format_gateio_quantity(amount)
            else:
                # Limit order: require both price and amount
                if price is None or amount is None:
                    raise ValueError("Limit orders require both price and amount")
                
                payload['price'] = GateioUtils.format_gateio_price(price)
                payload['amount'] = GateioUtils.format_gateio_quantity(amount)
            
            # Add special parameters for specific order types
            order_params = GateioMappings.get_order_params(order_type, time_in_force)
            payload.update(order_params)
            
            # Make authenticated request
            endpoint = GateioConfig.SPOT_ENDPOINTS['orders']
            signature_path = GateioConfig.SIGNATURE_ENDPOINTS['orders']
            
            # Use msgspec to ensure identical JSON for signature and request body
            payload_json_bytes = msgspec.json.encode(payload)
            payload_json = payload_json_bytes.decode('utf-8')
            headers = self._create_authenticated_headers('POST', signature_path, '', payload_json)
            
            self.logger.debug(f"Order payload for signature: {payload_json}")
            self.logger.debug(f"Signature path: {signature_path}")
            
            # Set Content-Type to match signature
            headers['Content-Type'] = 'application/json'
            
            # Use the RestClient's low-level request method to pass raw JSON string
            response_data = await self.client.request(
                HTTPMethod.POST,
                endpoint,
                params=None,
                json_data=payload,  # Pass the dict - RestClient will use msgspec encoder which produces same JSON
                headers=headers,
                config=GateioConfig.rest_config['order']
            )
            
            # Transform Gate.io response to unified Order
            order = GateioUtils.transform_gateio_order_to_unified(response_data)
            
            self.logger.info(f"Placed {side.name} order: {order.order_id}")
            return order
            
        except Exception as e:
            import traceback
            self.logger.error(f"Failed to place order: {e}")
            self.logger.error(f"Full traceback: {traceback.format_exc()}")
            raise BaseExchangeError(500, f"Order placement failed: {str(e)}")
    
    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """
        Cancel an active order.
        
        Args:
            symbol: Trading symbol
            order_id: Order ID to cancel
            
        Returns:
            Cancelled Order object
            
        Raises:
            ExchangeAPIError: If order cancellation fails
        """
        try:
            pair = GateioUtils.symbol_to_pair(symbol)
            endpoint = GateioConfig.SPOT_ENDPOINTS['cancel_order'].format(order_id=order_id)
            signature_path = GateioConfig.SIGNATURE_ENDPOINTS['cancel_order'].format(order_id=order_id)
            
            params = {'currency_pair': pair}
            query_string = '&'.join(f"{k}={v}" for k, v in params.items())
            
            headers = self._create_authenticated_headers('DELETE', signature_path, query_string)
            
            response_data = await self.client.delete(
                endpoint,
                params=params,
                headers=headers,
                config=GateioConfig.rest_config['order']
            )
            
            # Transform Gate.io response to unified Order
            order = GateioUtils.transform_gateio_order_to_unified(response_data)
            
            self.logger.info(f"Cancelled order: {order_id}")
            return order
            
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {e}")
            raise BaseExchangeError(500, f"Order cancellation failed: {str(e)}")
    
    async def cancel_all_orders(self, symbol: Symbol) -> List[Order]:
        """
        Cancel all open orders for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            List of cancelled Order objects
            
        Raises:
            ExchangeAPIError: If mass cancellation fails
        """
        try:
            pair = GateioUtils.symbol_to_pair(symbol)
            endpoint = GateioConfig.SPOT_ENDPOINTS['cancel_orders']
            signature_path = GateioConfig.SIGNATURE_ENDPOINTS['cancel_orders']
            
            params = {'currency_pair': pair}
            query_string = '&'.join(f"{k}={v}" for k, v in params.items())
            headers = self._create_authenticated_headers('DELETE', signature_path, query_string, '')
            
            response_data = await self.client.delete(
                endpoint,
                params=params,
                headers=headers,
                config=GateioConfig.rest_config['order']
            )
            
            # Gate.io returns list of cancelled orders
            if not isinstance(response_data, list):
                raise BaseExchangeError(500, "Invalid cancel all orders response format")
            
            cancelled_orders = []
            for order_data in response_data:
                order = GateioUtils.transform_gateio_order_to_unified(order_data)
                cancelled_orders.append(order)
            
            self.logger.info(f"Cancelled {len(cancelled_orders)} orders for {symbol}")
            return cancelled_orders
            
        except Exception as e:
            self.logger.error(f"Failed to cancel all orders for {symbol}: {e}")
            raise BaseExchangeError(500, f"Mass order cancellation failed: {str(e)}")
    
    async def get_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """
        Query order status.
        
        HFT COMPLIANT: Never caches order data - always fresh API call.
        
        Args:
            symbol: Trading symbol
            order_id: Order ID to query
            
        Returns:
            Order object with current status
            
        Raises:
            ExchangeAPIError: If order query fails
        """
        try:
            pair = GateioUtils.symbol_to_pair(symbol)
            endpoint = GateioConfig.SPOT_ENDPOINTS['cancel_order'].format(order_id=order_id)  # Same path for GET
            signature_path = GateioConfig.SIGNATURE_ENDPOINTS['cancel_order'].format(order_id=order_id)
            
            params = {'currency_pair': pair}
            query_string = '&'.join(f"{k}={v}" for k, v in params.items())
            
            headers = self._create_authenticated_headers('GET', signature_path, query_string)
            
            response_data = await self.client.get(
                endpoint,
                params=params,
                headers=headers,
                config=GateioConfig.rest_config['my_orders']
            )
            
            # Transform Gate.io response to unified Order
            order = GateioUtils.transform_gateio_order_to_unified(response_data)
            
            self.logger.debug(f"Retrieved order status: {order_id}")
            return order
            
        except Exception as e:
            self.logger.error(f"Failed to get order {order_id}: {e}")
            raise BaseExchangeError(500, f"Order query failed: {str(e)}")
    
    async def get_open_orders(self, symbol: Optional[Symbol] = None) -> List[Order]:
        """
        Get open orders for a specific symbol.
        
        Note: Gate.io requires currency_pair parameter. If no symbol is provided,
        this method will return an empty list instead of making an API call.
        
        HFT COMPLIANT: Never caches order data - always fresh API call.
        
        Args:
            symbol: Trading symbol (None will return empty list due to Gate.io API requirements)
            
        Returns:
            List of open Order objects for the specified symbol, or empty list if no symbol
            
        Raises:
            ExchangeAPIError: If order retrieval fails
        """
        try:
            # Gate.io requires currency_pair parameter - return empty list if no symbol provided
            if symbol is None:
                self.logger.debug("No symbol provided for get_open_orders - returning empty list (Gate.io API requirement)")
                return []
            
            endpoint = GateioConfig.SPOT_ENDPOINTS['orders']
            signature_path = GateioConfig.SIGNATURE_ENDPOINTS['orders']
            params = {
                'status': 'open',
                'currency_pair': GateioUtils.symbol_to_pair(symbol)
            }
            
            query_string = '&'.join(f"{k}={v}" for k, v in params.items())
            headers = self._create_authenticated_headers('GET', signature_path, query_string)
            
            response_data = await self.client.get(
                endpoint,
                params=params,
                headers=headers,
                config=GateioConfig.rest_config['my_orders']
            )
            
            # Gate.io returns list of orders
            if not isinstance(response_data, list):
                raise BaseExchangeError(500, "Invalid open orders response format")
            
            open_orders = []
            for order_data in response_data:
                order = GateioUtils.transform_gateio_order_to_unified(order_data)
                open_orders.append(order)
            
            symbol_str = f" for {symbol}" if symbol else ""
            self.logger.debug(f"Retrieved {len(open_orders)} open orders{symbol_str}")
            return open_orders
            
        except Exception as e:
            symbol_str = f" for {symbol}" if symbol else ""
            self.logger.error(f"Failed to get open orders{symbol_str}: {e}")
            raise BaseExchangeError(500, f"Open orders retrieval failed: {str(e)}")
    
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
        Modify an existing order (if supported).
        
        Note: Gate.io doesn't support order modification directly.
        This method cancels the original order and places a new one.
        
        Args:
            symbol: Trading symbol
            order_id: Order ID to modify
            amount: New order amount
            price: New order price
            quote_quantity: New quote quantity
            time_in_force: New time in force
            stop_price: New stop price (not used)
            
        Returns:
            New Order object
            
        Raises:
            ExchangeAPIError: If modification fails
        """
        try:
            # Get current order details
            current_order = await self.get_order(symbol, order_id)
            
            # Cancel existing order
            await self.cancel_order(symbol, order_id)
            
            # Place new order with modified parameters
            new_order = await self.place_order(
                symbol=symbol,
                side=current_order.side,
                order_type=current_order.order_type,
                amount=amount or current_order.amount,
                price=price or current_order.price,
                quote_quantity=quote_quantity,
                time_in_force=time_in_force or TimeInForce.GTC
            )
            
            self.logger.info(f"Modified order {order_id} -> {new_order.order_id}")
            return new_order
            
        except Exception as e:
            self.logger.error(f"Failed to modify order {order_id}: {e}")
            raise BaseExchangeError(500, f"Order modification failed: {str(e)}")
    
    # Gate.io doesn't have listen key endpoints like Binance
    # These methods are required by cex but not applicable
    
    async def create_listen_key(self) -> str:
        """Gate.io doesn't use listen keys - returns empty string."""
        return ""
    
    async def get_all_listen_keys(self) -> Dict:
        """Gate.io doesn't use listen keys - returns empty dict.""" 
        return {}
    
    async def keep_alive_listen_key(self, listen_key: str) -> None:
        """Gate.io doesn't use listen keys - no-op."""
        pass
    
    async def delete_listen_key(self, listen_key: str) -> None:
        """Gate.io doesn't use listen keys - no-op."""
        pass
    
    async def get_trading_fees(self, symbol: Optional[Symbol] = None) -> TradingFee:
        """
        Get personal trading fees for the account or a specific symbol.
        
        HFT COMPLIANT: Never caches fee data - always fresh API call.
        
        Args:
            symbol: Optional trading symbol to get specific fees for.
                   Note: Gate.io API limitation - only returns account-level fees
                   regardless of symbol parameter.
        
        Returns:
            TradingFee object with maker and taker rates
            
        Raises:
            ExchangeAPIError: If unable to fetch fee data
            
        Note:
            Gate.io API Limitation: The /spot/fee endpoint only supports account-level
            fees, not symbol-specific fees. The symbol parameter is accepted for
            cex compatibility but Gate.io will always return account-level rates.
        """
        try:
            # Log the request details
            if symbol:
                self.logger.debug(f"Retrieving trading fees for symbol {symbol.base}/{symbol.quote}")
                self.logger.warning(f"Gate.io API limitation: Symbol-specific fees not supported, returning account-level fees")
            else:
                self.logger.debug("Retrieving account-level trading fees")
            
            endpoint = GateioConfig.SPOT_ENDPOINTS['fee']
            signature_path = GateioConfig.SIGNATURE_ENDPOINTS['fee']
            headers = self._create_authenticated_headers('GET', signature_path)
            
            response_data = await self.client.get(
                endpoint,
                headers=headers,
                config=GateioConfig.rest_config['account']
            )
            
            # Gate.io fee response format based on API docs:
            # {
            #   "user_id": 10003,
            #   "taker_fee": "0.002",
            #   "maker_fee": "0.002",
            #   "gt_discount": false,
            #   "gt_taker_fee": "0.0015", 
            #   "gt_maker_fee": "0.0015",
            #   "loan_fee": "0.18",
            #   "point_type": "0" // fee tier
            # }
            
            if not isinstance(response_data, dict):
                raise BaseExchangeError(500, "Invalid trading fees response format")
            
            # Extract fee rates - Gate.io returns string values
            maker_rate = float(response_data.get('maker_fee', '0.002'))
            taker_rate = float(response_data.get('taker_fee', '0.002'))
            point_type = response_data.get('point_type', '0')
            
            # Gate.io doesn't provide 30-day volume in fee response
            # Could be fetched separately if needed
            
            trading_fee = TradingFee(
                exchange=self.exchange,
                maker_rate=maker_rate,
                taker_rate=taker_rate,
                spot_maker=maker_rate,
                spot_taker=taker_rate,
                point_type=point_type,
                symbol=symbol  # Include symbol in response (None for account-level)
            )
            
            if symbol:
                self.logger.debug(f"Retrieved trading fees for {symbol.base}/{symbol.quote}: maker {maker_rate*100:.3f}%, taker {taker_rate*100:.3f}%")
            else:
                self.logger.debug(f"Retrieved account-level trading fees: maker {maker_rate*100:.3f}%, taker {taker_rate*100:.3f}%")
            return trading_fee
            
        except Exception as e:
            self.logger.error(f"Failed to get trading fees: {e}")
            raise BaseExchangeError(500, f"Trading fees fetch failed: {str(e)}")

    async def close(self) -> None:
        """Close the REST client and clean up resources."""
        try:
            await self.client.close()
            self.logger.info("Closed Gate.io private REST client")
        except Exception as e:
            self.logger.error(f"Error closing private REST client: {e}")
    
    def __repr__(self) -> str:
        return f"GateioPrivateExchange(base_url={self.base_url})"