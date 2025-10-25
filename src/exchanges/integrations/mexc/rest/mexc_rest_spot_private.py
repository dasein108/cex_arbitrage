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

from typing import Dict, List, Optional, Any, Union
import msgspec

from exchanges.integrations.mexc.services.symbol_mapper import MexcSymbol
from exchanges.structs.common import (
    Symbol, Order, AssetBalance, Trade,
    AssetInfo, NetworkInfo, WithdrawalRequest, WithdrawalResponse, DepositResponse, DepositAddress
)
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs.enums import TimeInForce, WithdrawalStatus, DepositStatus
from exchanges.structs import OrderType, Side, Fees
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.http.structs import HTTPMethod
from infrastructure.exceptions.exchange import ExchangeRestError, OrderCancelledOrFilled
from exchanges.interfaces.rest import PrivateSpotRestInterface
from exchanges.interfaces.rest.interfaces import ListenKeyInterface
from exchanges.integrations.mexc.structs.exchange import (MexcAccountResponse, MexcOrderResponse,
                                                          MexcCurrencyInfoResponse, MexcAccountTradeResponse)

# Import direct utility functions
from exchanges.integrations.mexc.utils import (
    from_side, from_order_type, format_quantity, format_price,
    from_time_in_force, to_order_status, rest_to_order, rest_to_withdrawal_status, rest_to_deposit_status, rest_to_trade
)
from utils import get_current_timestamp

# Import the new base REST implementation
from .mexc_base_rest import MexcBaseRestInterface
from exchanges.utils.network_mapping import get_unified_network_name

class MexcPrivateSpotRestInterface(MexcBaseRestInterface, PrivateSpotRestInterface, ListenKeyInterface):
    """
    MEXC private REST API client focused on trading operations.
    
    Provides access to authenticated trading endpoints without WebSocket features.
    Optimized for high-frequency trading operations with minimal overhead.
    """

    def __init__(self, config, logger: Optional[HFTLoggerInterface] = None, **kwargs):
        """
        Initialize MEXC private REST client with constructor injection.

        Args:
            config: ExchangeConfig with MEXC URL and credentials
            rate_limiter: Rate limiter instance (injected)
            logger: HFT logger instance (injected)
            **kwargs: Additional parameters for compatibility
        """
        # Initialize base REST client with constructor injection
        # Note: PrivateSpotRestInterface now inherits from BaseRestClient, so we only need to call super().__init__
        super().__init__(config, logger, is_private=True)

        self.logger.debug("MEXC private spot REST client initialized",
                         exchange="mexc", api_type="private")

    async def modify_order(self, symbol: Symbol, order_id: OrderId, qunatity: Optional[float] = None,
                           price: Optional[float] = None, quote_quantity: Optional[float] = None,
                           time_in_force: Optional[TimeInForce] = None, stop_price: Optional[float] = None) -> Order:
        raise NotImplementedError("MEXC does not support direct order modification via API")

    async def get_balances(self) -> List[AssetBalance]:
        """
        Get account balance for all assets.
        
        Returns:
            List of AssetBalance objects with free and locked amounts
            
        Raises:
            ExchangeAPIError: If unable to fetch account balance
        """
        # Use base class request method (eliminates strategy dispatch overhead)
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
                    available=float(mexc_balance.free),
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
        all_balances = await self.get_balances()

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
            quantity: Optional[float] = None,
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
            quantity: Base asset quantity (optional for MARKET buy orders)
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
        pair = MexcSymbol.to_pair(symbol)

        # Validate required parameters based on order type
        if order_type in [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.STOP_LIMIT]:
            if price is None:
                raise ValueError(f"Price is required for {order_type.name} orders")

        if order_type in [OrderType.STOP_LIMIT, OrderType.STOP_MARKET]:
            if stop_price is None:
                raise ValueError(f"Stop price is required for {order_type.name} orders")

        # For MARKET buy orders, either amount or quote_quantity is required
        # **** COVER IN COMPOSITE LAYER ****

        # if order_type == OrderType.MARKET:
        #
        #     if side == Side.BUY:
        #         if quote_quantity is None:
        #             if price is None:
        #                 raise ValueError("Either quote_quantity or price is required for MARKET buy orders")
        #
        #             quote_quantity = quantity * price if quantity and price else None
        #             quantity = None
        #         # raise ValueError("Either amount or quote_quantity is required for MARKET buy orders")
        #     elif side == Side.SELL:
        #         if quantity is None:
        #             if price is None:
        #                 raise ValueError("Either quantity or price is required for MARKET sell orders")
        #
        #             quantity = quote_quantity / price if quote_quantity and price else None
        #             quote_quantity = None
        #         # raise ValueError(f"Amount is required for this order type {order_type.name}, q: {quantity}, "
        #         #                  f"qq: {quote_quantity}, price: {price}")

        # Prepare exchanges order parameters
        params = {
            'symbol': pair,
            'side': from_side(side),
            'type': from_order_type(order_type)
        }

        # Add quantity parameters
        if quantity is not None:
            params['quantity'] = format_quantity(quantity)

        if quote_quantity is not None:
            params['quoteOrderQty'] = format_quantity(quote_quantity)

        # Add price parameters
        if price is not None:
            params['price'] = format_price(price)

        if stop_price is not None:
            params['stopPrice'] = format_price(stop_price)

        # Add time in force (default to GTC if not specified for applicable order types)
        if order_type in [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.STOP_LIMIT]:
            tif = time_in_force or TimeInForce.GTC
            params['timeInForce'] = from_time_in_force(tif)
        elif time_in_force is not None:
            params['timeInForce'] = from_time_in_force(time_in_force)

        # Add optional parameters
        # if iceberg_qty is not None:
        #     params['icebergQty'] = format_quantity(iceberg_qty)
        #
        # if new_order_resp_type is not None:
        #     params['newOrderRespType'] = new_order_resp_type

        # Use base class request method with direct implementation
        response_data = await self.request(
            HTTPMethod.POST,
            '/api/v3/order',
            params=params
        )

        order_response = msgspec.convert(response_data, MexcOrderResponse)

        # Transform to unified format
        unified_order = rest_to_order(order_response)

        # Log order placement with relevant details
        self.logger.info(f"MEXC SPOT PLACED {unified_order}")
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
        pair = MexcSymbol.to_pair(symbol)

        params = {
            'symbol': pair,
            'orderId': str(order_id)
        }
        try:
            # Use base class request method with direct implementation
            response_data = await self.request(
                HTTPMethod.DELETE,
                '/api/v3/order',
                params=params
            )
        except OrderCancelledOrFilled as e:
            self.logger.warning(f"Order {order_id} for {symbol.base}/{symbol.quote} already cancelled/filled or does not exist")
            # TODO: warning x2 latency costs
            return await self.get_order(symbol, order_id)

        order_response = msgspec.convert(response_data, MexcOrderResponse)

        # Transform to unified format
        unified_order = rest_to_order(order_response)

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
        pair = MexcSymbol.to_pair(symbol)

        params = {'symbol': pair}

        # Use base class request method with direct implementation
        response_data = await self.request(
            HTTPMethod.DELETE,
            '/api/v3/openOrders',
            params=params
        )

        order_responses = msgspec.convert(response_data, list[MexcOrderResponse])

        # Transform to unified format
        cancelled_orders = []
        for order_response in order_responses:
            unified_order = rest_to_order(order_response)
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
        pair = MexcSymbol.to_pair(symbol)

        params = {
            'symbol': pair,
            'orderId': str(order_id)
        }

        # Use base class request method with direct implementation
        response_data = await self.request(
            HTTPMethod.GET,
            '/api/v3/order',
            params=params
        )

        order_response = msgspec.convert(response_data, MexcOrderResponse)

        # Transform to unified format
        unified_order = rest_to_order(order_response)

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
            params['symbol'] = MexcSymbol.to_pair(symbol)

        # Use base class request method with direct implementation
        response_data = await self.request(
            HTTPMethod.GET,
            '/api/v3/openOrders',
            params=params
        )

        order_responses = msgspec.convert(response_data, list[MexcOrderResponse])

        # Transform to unified format
        open_orders = []
        for order_response in order_responses:
            unified_order = rest_to_order(order_response)
            open_orders.append(unified_order)

        self.logger.debug(f"Retrieved {len(open_orders)} open orders for {symbol}")
        return open_orders

    async def get_history_orders(self, symbol: Symbol,
                                 start_time: Optional[int] = None,
                                 end_time: Optional[int] = None,
                                 limit: Optional[int] =None) -> List[Order]:
        """
        Get all open orders, optionally filtered by symbol.

        Args:
            symbol: Optional symbol to filter orders
            start_time: Optional start time in milliseconds
            end_time: Optional end time in milliseconds
            limit: Optional maximum number of orders to return

        Returns:
            List of open Order objects

        Raises:
            ExchangeAPIError: If unable to fetch orders
        """
        params = {'symbol': MexcSymbol.to_pair(symbol)}
        if limit:
            params['limit'] = limit
        if end_time:
            params['endTime'] = end_time
        if start_time:
            params['startTime'] = end_time

        # Use base class request method with direct implementation
        response_data = await self.request(
            HTTPMethod.GET,
            '/api/v3/allOrders',
            params=params
        )

        order_responses = msgspec.convert(response_data, list[MexcOrderResponse])

        # Transform to unified format
        all_orders = []
        for order_response in order_responses:
            unified_order = rest_to_order(order_response)
            all_orders.append(unified_order)

        self.logger.debug(f"Retrieved {len(all_orders)} history orders for {symbol}")
        return all_orders

    async def get_account_trades(self, symbol: Symbol,
                                order_id: Optional[OrderId] = None,
                                start_time: Optional[int] = None,
                                end_time: Optional[int] = None,
                                limit: Optional[int] = None) -> List[Trade]:
        """
        Get account trade history for a specific symbol.
        
        Args:
            symbol: Symbol to get trades for
            order_id: Optional order ID to filter trades
            start_time: Optional start time in milliseconds
            end_time: Optional end time in milliseconds
            limit: Optional maximum number of trades to return (max 100)
            
        Returns:
            List of Trade objects representing account trades
            
        Raises:
            ExchangeAPIError: If unable to fetch trade history
        """
        pair = MexcSymbol.to_pair(symbol)
        
        params = {'symbol': pair}
        
        # Add optional parameters if provided
        if order_id:
            params['orderId'] = str(order_id)
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        if limit:
            # MEXC API max limit is 100
            params['limit'] = min(limit, 100)

        # Use base class request method with direct implementation
        response_data = await self.request(
            HTTPMethod.GET,
            '/api/v3/myTrades',
            params=params
        )

        trade_responses = msgspec.convert(response_data, list[MexcAccountTradeResponse])

        # Transform to unified format
        account_trades = []
        for trade_response in trade_responses:
            unified_trade = rest_to_trade(trade_response)
            account_trades.append(unified_trade)

        self.logger.debug(f"Retrieved {len(account_trades)} account trades for {symbol.base}/{symbol.quote}")
        return account_trades

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
        # Use base class request method with direct implementation
        response_data = await self.request(
            HTTPMethod.POST,
            '/api/v3/userDataStream'
        )

        listen_key = response_data.get('listenKey')
        if not listen_key:
            raise ExchangeRestError(500, "Failed to create listen key - no key in response")

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
        # Use base class request method with direct implementation
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

        # Use base class request method with direct implementation
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

        # Use base class request method with direct implementation
        await self.request(
            HTTPMethod.DELETE,
            '/api/v3/userDataStream',
            params=params
        )

        self.logger.debug(f"Deleted listen key: {listen_key[:8]}...")

    async def get_assets_info(self) -> Dict[AssetName, AssetInfo]:
        """
        Get currency information including deposit/withdrawal status and network details.

        Returns:
            Dictionary mapping AssetName to AssetInfo with network configurations

        Raises:
            ExchangeAPIError: If unable to fetch currency information
        """
        # Use base class request method with direct implementation
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
                network_name = get_unified_network_name(network_data.network)
                network_info = NetworkInfo(
                    network=network_name,
                    deposit_enable=network_data.depositEnable,
                    withdraw_enable=network_data.withdrawEnable,
                    withdraw_fee=float(network_data.withdrawFee),
                    withdraw_min=float(network_data.withdrawMin),
                    withdraw_max=float(network_data.withdrawMax) if network_data.withdrawMax else None,
                    contract_address=network_data.contract,
                    memo=None
                )

                networks[network_name] = network_info

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

        self.logger.debug(f"Retrieved currency info for {len(currency_info_map)} assets")
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
            params['netWork'] = request.network

        # Add memo if provided (for coins that require it)
        if request.memo:
            params['addressTag'] = request.memo

        # Add custom withdrawal order ID if provided
        if request.withdrawal_order_id:
            params['withdrawOrderId'] = request.withdrawal_order_id

        try:
            # Use base class request method with direct implementation
            response_data = await self.request(
                HTTPMethod.POST,
                '/api/v3/capital/withdraw',
                params=params
            )

            # MEXC response format: {"id": "withdrawal_id"}
            withdrawal_id = response_data.get('id', response_data.get('withdrawOrderId', ''))

            if not withdrawal_id:
                raise ExchangeRestError(500, "No withdrawal ID returned from MEXC")

            # Get fee from currency info
            currency_info = await self.get_assets_info()
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
                timestamp=get_current_timestamp(),
                memo=request.memo,
                remark=request.remark
            )

            self.logger.info(f"Submitted withdrawal: {request.amount} {request.asset} to {request.address}")
            return withdrawal_response

        except Exception as e:
            self.logger.error(f"Failed to submit withdrawal: {e}")
            raise ExchangeRestError(500, f"Withdrawal submission failed: {e}")

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

            raise ExchangeRestError(404, f"Withdrawal {withdrawal_id} not found")

        except Exception as e:
            self.logger.error(f"Failed to get withdrawal status: {e}")
            raise ExchangeRestError(500, f"Failed to get withdrawal status: {e}")

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
            # Use base class request method with direct implementation
            response_data = await self.request(
                HTTPMethod.GET,
                '/api/v3/capital/withdraw/history',
                params=params
            )

            withdrawals = []

            # MEXC returns a list of withdrawal records
            for withdrawal_data in response_data:
                # Map MEXC status to our enum (status is integer 1-10)
                mexc_status = withdrawal_data.get('status', 0)
                status = rest_to_withdrawal_status(mexc_status)

                withdrawal = WithdrawalResponse(
                    withdrawal_id=str(withdrawal_data.get('id', withdrawal_data.get('withdrawOrderId', ''))),
                    asset=AssetName(withdrawal_data.get('coin', '')),
                    amount=float(withdrawal_data.get('amount', 0)),
                    fee=float(withdrawal_data.get('transactionFee', 0)),
                    address=withdrawal_data.get('address', ''),
                    network=withdrawal_data.get('network'),
                    status=status,
                    timestamp=int(withdrawal_data.get('applyTime', 0)),
                    memo=withdrawal_data.get('memo'),  # Fixed: MEXC uses 'memo' not 'addressTag'
                    tx_id=withdrawal_data.get('txId'),
                    remark=withdrawal_data.get('remark')
                )
                withdrawals.append(withdrawal)

            self.logger.debug(f"Retrieved {len(withdrawals)} withdrawal records")
            return withdrawals

        except Exception as e:
            self.logger.error(f"Failed to get withdrawal history: {e}")
            raise ExchangeRestError(500, f"Failed to get withdrawal history: {e}")

    async def deposit_history(
        self,
        asset: Optional[AssetName] = None,
        limit: int = 100
    ) -> List[DepositResponse]:
        """
        Get deposit history from MEXC.
        
        Args:
            asset: Optional asset filter
            limit: Maximum number of deposits to return
            
        Returns:
            List of historical deposits
        """
        params = {}
        if asset:
            params['coin'] = asset
        # MEXC supports up to 1000 records
        params['limit'] = min(limit, 1000)

        try:
            # Use base class request method with direct implementation
            response_data = await self.request(
                HTTPMethod.GET,
                '/api/v3/capital/deposit/hisrec',
                params=params
            )

            deposits = []
            # MEXC returns a list of deposit records
            for deposit_data in response_data:
                # Map MEXC status to our enum
                mexc_status = deposit_data.get('status', 0)
                status = rest_to_deposit_status(mexc_status)
                
                deposit = DepositResponse(
                    deposit_id=str(deposit_data.get('id', '')),
                    asset=AssetName(deposit_data.get('coin', '')),
                    amount=float(deposit_data.get('amount', 0)),
                    address=deposit_data.get('address', ''),
                    network=deposit_data.get('network'),
                    status=status,
                    timestamp=int(deposit_data.get('insertTime', 0)),
                    memo=deposit_data.get('memo'),
                    tx_id=deposit_data.get('txId'),
                    confirmations=int(deposit_data.get('confirmTimes', 0)) if deposit_data.get('confirmTimes') else None,
                    unlock_confirmations=int(deposit_data.get('unlockConfirm', 0)) if deposit_data.get('unlockConfirm') else None
                )
                deposits.append(deposit)

            self.logger.debug(f"Retrieved {len(deposits)} deposit records")
            return deposits

        except Exception as e:
            self.logger.error(f"Failed to get deposit history: {e}")
            raise ExchangeRestError(500, f"Failed to get deposit history: {e}")

    async def get_deposit_history(
        self,
        asset: Optional[AssetName] = None,
        limit: int = 100,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> List[DepositResponse]:
        """
        Get deposit history from MEXC with optional time filtering.
        
        Args:
            asset: Optional asset filter
            limit: Maximum number of deposits to return (max 1000)
            start_time: Optional start time in milliseconds since epoch
            end_time: Optional end time in milliseconds since epoch
            
        Returns:
            List of historical deposits
            
        Raises:
            ExchangeAPIError: If unable to fetch deposit history
        """
        params = {}
        if asset:
            params['coin'] = asset
        # MEXC supports up to 1000 records
        params['limit'] = min(limit, 1000)
        
        # Add time filtering if provided
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time

        try:
            # Use base class request method with direct implementation
            response_data = await self.request(
                HTTPMethod.GET,
                '/api/v3/capital/deposit/hisrec',
                params=params
            )

            deposits = []
            # MEXC returns a list of deposit records
            for deposit_data in response_data:
                # Map MEXC status to our enum
                mexc_status = deposit_data.get('status', 0)
                status = rest_to_deposit_status(mexc_status)
                
                deposit = DepositResponse(
                    deposit_id=str(deposit_data.get('id', '')),
                    asset=AssetName(deposit_data.get('coin', '')),
                    amount=float(deposit_data.get('amount', 0)),
                    address=deposit_data.get('address', ''),
                    network=deposit_data.get('network'),
                    status=status,
                    timestamp=int(deposit_data.get('insertTime', 0)),
                    memo=deposit_data.get('memo'),
                    tx_id=deposit_data.get('txId'),
                    confirmations=int(deposit_data.get('confirmTimes', 0)) if deposit_data.get('confirmTimes') else None,
                    unlock_confirmations=int(deposit_data.get('unlockConfirm', 0)) if deposit_data.get('unlockConfirm') else None
                )
                deposits.append(deposit)

            self.logger.debug(f"Retrieved {len(deposits)} deposit records with time filtering")
            return deposits

        except Exception as e:
            self.logger.error(f"Failed to get deposit history: {e}")
            raise ExchangeRestError(500, f"Failed to get deposit history: {e}")

    async def get_deposit_address(
        self,
        asset: AssetName,
        network: Optional[str] = None
    ) -> DepositAddress:
        """
        Get deposit address for the specified asset and network from MEXC.

        Args:
            asset: Asset name to get deposit address for
            network: Optional network/chain specification

        Returns:
            DepositAddress with address and memo information

        Raises:
            ExchangeAPIError: If unable to fetch deposit address
            ValueError: If asset or network not supported
        """
        params = {
            'coin': asset
        }
        
        # Add network if specified
        if network:
            params['network'] = network

        try:
            # Use MEXC deposit address endpoint
            response_data = await self.request(
                HTTPMethod.GET,
                '/api/v3/capital/deposit/address',
                params=params
            )

            # MEXC response format: {"coin": "BTC", "address": "...", "tag": "...", "url": "..."}
            # Handle case where response is a list
            response_data = response_data[0] if isinstance(response_data, list) else response_data

            address = response_data.get('address', '')
            if not address:
                raise ExchangeRestError(500, f"No deposit address returned for {asset}")

            # Extract memo/tag if present
            memo = response_data.get('tag') or response_data.get('memo')
            
            # Get network from response or use provided network
            response_network = response_data.get('network', network or 'default')

            deposit_address = DepositAddress(
                asset=asset,
                address=address,
                network=response_network,
                memo=memo
            )

            self.logger.debug(f"Retrieved deposit address for {asset}: {address}")
            return deposit_address

        except Exception as e:
            self.logger.error(f"Failed to get deposit address for {asset}: {e}")
            raise ExchangeRestError(500, f"Failed to get deposit address for {asset}: {e}")

    async def get_trading_fees(self, symbol: Optional[Symbol] = None) ->  Union[Fees, Dict[Symbol, Fees]]:
        return Fees(maker_fee=0, taker_fee=0.0005)
