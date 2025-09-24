"""
MEXC Private REST API Implementation

Focused REST-only client for MEXC private API endpoints.
Optimized for direct trading API calls without WebSocket features.

Key Features:
- Pure REST API implementation for trading operations
- Sub-10ms response times for order management
- MEXC-specific HMAC-SHA256 authentication
- Zero-copy JSON parsing with msgspec
- Unified exchanges compliance

MEXC Private API Specifications:
- Base URL: https://api.mexc.com  
- Authentication: HMAC-SHA256 with query string parameters
- Rate Limits: 20 requests/second
- Required parameters: recvWindow, timestamp, signature

Threading: Fully async/await compatible, thread-safe
Memory: O(1) per request, optimized for trading operations
"""

from typing import Dict, List, Optional, Any
import msgspec

from infrastructure.data_structures.common import (
    Symbol, Order, OrderId, OrderType, Side, AssetBalance,
    AssetName, AssetInfo, NetworkInfo, TimeInForce,
    WithdrawalRequest, WithdrawalResponse, WithdrawalStatus
)
from infrastructure.networking.http.structs import HTTPMethod
from infrastructure.exceptions.exchange import BaseExchangeError
from exchanges.interfaces.rest.spot.rest_spot_private import PrivateSpotRest



class MexcPrivateSpotRest(PrivateSpotRest):
    """
    MEXC private REST API client focused on trading operations.
    
    Provides access to authenticated trading endpoints without WebSocket features.
    Optimized for high-frequency trading operations with minimal overhead.
    """

    async def modify_order(self, symbol: Symbol, order_id: OrderId, amount: Optional[float] = None,
                           price: Optional[float] = None, quote_quantity: Optional[float] = None,
                           time_in_force: Optional[TimeInForce] = None, stop_price: Optional[float] = None) -> Order:
        raise NotImplementedError("MEXC does not support direct order modification via API")

    # Authentication is now handled automatically by the transport system

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
            '/api/v3/account'
        )

        account_data = msgspec.convert(response_data, MexcAccountResponse)

        # Transform to unified format
        balances = []
        for mexc_balance in account_data.balances:
            if float(mexc_balance.free) > 0 or float(mexc_balance.locked) > 0:
                balance = AssetBalance(
                    asset=AssetName(mexc_balance.asset),
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
        pair = self._mapper.to_pair(symbol)

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

        # Prepare exchanges order parameters
        params = {
            'symbol': pair,
            'side': self._mapper.from_side(side),
            'type': self._mapper.from_order_type(order_type)
        }

        # Add quantity parameters
        if amount is not None:
            params['quantity'] = self._mapper.format_quantity(amount)

        if quote_quantity is not None:
            params['quoteOrderQty'] = self._mapper.format_quantity(quote_quantity)

        # Add price parameters
        if price is not None:
            params['price'] = self._mapper.format_price(price)

        if stop_price is not None:
            params['stopPrice'] = self._mapper.format_price(stop_price)

        # Add time in force (default to GTC if not specified for applicable order types)
        if order_type in [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.STOP_LIMIT]:
            tif = time_in_force or TimeInForce.GTC
            params['timeInForce'] = self._mapper.from_time_in_force(tif)
        elif time_in_force is not None:
            params['timeInForce'] = self._mapper.from_time_in_force(time_in_force)

        # Add optional parameters
        if iceberg_qty is not None:
            params['icebergQty'] = self._mapper.format_quantity(iceberg_qty)

        if new_order_resp_type is not None:
            params['newOrderRespType'] = new_order_resp_type

        response_data = await self.request(
            HTTPMethod.POST,
            '/api/v3/order',
            params=params
        )

        order_response = msgspec.convert(response_data, MexcOrderResponse)

        # Transform to unified format
        unified_order = self._mapper.rest_to_order(order_response)

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
        pair = self._mapper.to_pair(symbol)

        params = {
            'symbol': pair,
            'orderId': str(order_id)
        }

        response_data = await self.request(
            HTTPMethod.DELETE,
            '/api/v3/order',
            params=params
        )

        order_response = msgspec.convert(response_data, MexcOrderResponse)

        # Transform to unified format
        unified_order = self._mapper.rest_to_order(order_response)

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
        pair = self._mapper.to_pair(symbol)

        params = {'symbol': pair}

        response_data = await self.request(
            HTTPMethod.DELETE,
            '/api/v3/openOrders',
            params=params
        )

        order_responses = msgspec.convert(response_data, list[MexcOrderResponse])

        # Transform to unified format
        cancelled_orders = []
        for order_response in order_responses:
            unified_order = self._mapper.rest_to_order(order_response)
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
        pair = self._mapper.to_pair(symbol)

        params = {
            'symbol': pair,
            'orderId': str(order_id)
        }

        response_data = await self.request(
            HTTPMethod.GET,
            '/api/v3/order',
            params=params
        )

        order_response = msgspec.convert(response_data, MexcOrderResponse)

        # Transform to unified format
        unified_order = self._mapper.rest_to_order(order_response)

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
            params['symbol'] = self._mapper.to_pair(symbol)

        response_data = await self.request(
            HTTPMethod.GET,
            '/api/v3/openOrders',
            params=params
        )

        order_responses = msgspec.convert(response_data, list[MexcOrderResponse])

        # Transform to unified format
        open_orders = []
        for order_response in order_responses:
            unified_order = self._mapper.rest_to_order(order_response)
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
            '/api/v3/userDataStream'
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
            '/api/v3/userDataStream'
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
            params=params
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
            params=params
        )

        self.logger.debug(f"Deleted listen key: {listen_key[:8]}...")

    async def get_currency_info(self) -> Dict[AssetName, AssetInfo]:
        """
        Get currency information including deposit/withdrawal status and network details.

        Returns:
            Dictionary mapping AssetName to AssetInfo with network configurations

        Raises:
            ExchangeAPIError: If unable to fetch currency information
        """
        response_data = await self.request(
            HTTPMethod.GET,
            '/api/v3/capital/config/getall'
        )

        currency_responses = msgspec.convert(response_data, list[MexcCurrencyInfoResponse])

        currency_info_map: Dict[AssetName, AssetInfo] = {}

        for currency_data in currency_responses:
            asset_name = AssetName(currency_data.coin)

            networks: Dict[str, NetworkInfo] = {}
            overall_deposit_enable = False
            overall_withdraw_enable = False

            for network_data in currency_data.networkList:
                network_info = NetworkInfo(
                    network=network_data.network,
                    deposit_enable=network_data.depositEnable,
                    withdraw_enable=network_data.withdrawEnable,
                    withdraw_fee=float(network_data.withdrawFee),
                    withdraw_min=float(network_data.withdrawMin),
                    withdraw_max=float(network_data.withdrawMax) if network_data.withdrawMax else None,
                    confirmations=network_data.minConfirm,
                    contract_address=network_data.contract,
                    memo_required=None  # MEXC doesn't provide this info
                )

                networks[network_data.network] = network_info

                if network_data.depositEnable:
                    overall_deposit_enable = True
                if network_data.withdrawEnable:
                    overall_withdraw_enable = True

            asset_info = AssetInfo(
                asset=asset_name,
                name=currency_data.name,
                deposit_enable=overall_deposit_enable,
                withdraw_enable=overall_withdraw_enable,
                networks=networks
            )

            currency_info_map[asset_name] = asset_info

        self.logger.info(f"Retrieved currency info for {len(currency_info_map)} assets")
        return currency_info_map

    # Withdrawal operations

    async def submit_withdrawal(self, request: WithdrawalRequest) -> WithdrawalResponse:
        """
        Submit a withdrawal request to MEXC.

        Args:
            request: Withdrawal request parameters

        Returns:
            WithdrawalResponse with withdrawal details

        Raises:
            ExchangeAPIError: If withdrawal submission fails
        """
        # Validate request before submission
        await self.validate_withdrawal_request(request)

        # Prepare MEXC API parameters
        params = {
            'coin': request.asset,
            'amount': str(request.amount),
            'address': request.address
        }

        # Add network if specified (required for multi-chain assets)
        if request.network:
            params['network'] = request.network

        # Add memo if provided (for coins that require it)
        if request.memo:
            params['addressTag'] = request.memo

        # Add custom withdrawal order ID if provided
        if request.withdrawal_order_id:
            params['withdrawOrderId'] = request.withdrawal_order_id

        try:
            response_data = await self.request(
                HTTPMethod.POST,
                '/api/v3/capital/withdraw',
                params=params
            )

            # MEXC response format: {"id": "withdrawal_id"}
            withdrawal_id = response_data.get('id', response_data.get('withdrawOrderId', ''))

            if not withdrawal_id:
                raise BaseExchangeError(500, "No withdrawal ID returned from MEXC")

            # Get fee from currency info
            currency_info = await self.get_currency_info()
            asset_info = currency_info.get(request.asset)
            fee = 0.0

            if asset_info and request.network:
                network_info = asset_info.networks.get(request.network)
                if network_info:
                    fee = network_info.withdraw_fee

            withdrawal_response = WithdrawalResponse(
                withdrawal_id=str(withdrawal_id),
                asset=request.asset,
                amount=request.amount,
                fee=fee,
                address=request.address,
                network=request.network,
                status=WithdrawalStatus.PENDING,
                timestamp=int(self._get_current_timestamp()),
                memo=request.memo,
                remark=request.remark
            )

            self.logger.info(f"Submitted withdrawal: {request.amount} {request.asset} to {request.address}")
            return withdrawal_response

        except Exception as e:
            self.logger.error(f"Failed to submit withdrawal: {e}")
            raise BaseExchangeError(500, f"Withdrawal submission failed: {e}")

    async def cancel_withdrawal(self, withdrawal_id: str) -> bool:
        """
        Cancel a pending withdrawal on MEXC.

        Note: MEXC API doesn't provide a direct withdrawal cancellation endpoint.
        This method will always return False as cancellation is not supported.

        Args:
            withdrawal_id: Exchange withdrawal ID to cancel

        Returns:
            False (MEXC doesn't support withdrawal cancellation via API)
        """
        self.logger.warning(f"MEXC does not support withdrawal cancellation via API for ID: {withdrawal_id}")
        return False

    async def get_withdrawal_status(self, withdrawal_id: str) -> WithdrawalResponse:
        """
        Get current status of a withdrawal on MEXC.

        Args:
            withdrawal_id: Exchange withdrawal ID

        Returns:
            WithdrawalResponse with current status

        Raises:
            ExchangeAPIError: If withdrawal not found
        """
        try:
            # Get recent withdrawal history to find the specific withdrawal
            history = await self.get_withdrawal_history(limit=1000)

            for withdrawal in history:
                if withdrawal.withdrawal_id == withdrawal_id:
                    return withdrawal

            raise BaseExchangeError(404, f"Withdrawal {withdrawal_id} not found")

        except Exception as e:
            self.logger.error(f"Failed to get withdrawal status: {e}")
            raise BaseExchangeError(500, f"Failed to get withdrawal status: {e}")

    async def get_withdrawal_history(
        self,
        asset: Optional[AssetName] = None,
        limit: int = 100
    ) -> List[WithdrawalResponse]:
        """
        Get withdrawal history from MEXC.

        Args:
            asset: Optional asset filter
            limit: Maximum number of withdrawals to return

        Returns:
            List of historical withdrawals
        """
        params = {}

        if asset:
            params['coin'] = asset

        # MEXC supports up to 1000 records
        params['limit'] = min(limit, 1000)

        try:
            response_data = await self.request(
                HTTPMethod.GET,
                '/api/v3/capital/withdraw/history',
                params=params
            )

            withdrawals = []

            # MEXC returns a list of withdrawal records
            for withdrawal_data in response_data:
                # Map MEXC status to our enum
                mexc_status = withdrawal_data.get('status', 0)
                status = map_mexc_withdrawal_status(mexc_status)

                withdrawal = WithdrawalResponse(
                    withdrawal_id=str(withdrawal_data.get('id', withdrawal_data.get('withdrawOrderId', ''))),
                    asset=AssetName(withdrawal_data.get('coin', '')),
                    amount=float(withdrawal_data.get('amount', 0)),
                    fee=float(withdrawal_data.get('transactionFee', 0)),
                    address=withdrawal_data.get('address', ''),
                    network=withdrawal_data.get('network'),
                    status=status,
                    timestamp=int(withdrawal_data.get('applyTime', 0)),
                    memo=withdrawal_data.get('addressTag'),
                    tx_id=withdrawal_data.get('txId')
                )
                withdrawals.append(withdrawal)

            self.logger.info(f"Retrieved {len(withdrawals)} withdrawal records")
            return withdrawals

        except Exception as e:
            self.logger.error(f"Failed to get withdrawal history: {e}")
            raise BaseExchangeError(500, f"Failed to get withdrawal history: {e}")


    def _get_current_timestamp(self) -> int:
        """Get current timestamp in milliseconds."""
        import time
        return int(time.time() * 1000)