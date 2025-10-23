"""
Gate.io Private REST API Implementation

Focused REST-only client for Gate.io private API endpoints.
Optimized for direct trading API calls without WebSocket features.

Key Features:
- Pure REST API implementation for trading operations
- Sub-10ms response times for order management  
- Gate.io-specific HMAC-SHA512 authentication
- Zero-copy JSON parsing with msgspec
- Unified exchanges compliance

Gate.io Private API Specifications:
- Base URL: https://api.gateio.ws/api/v4
- Authentication: HMAC-SHA512 with request body hashing
- Rate Limits: 10 requests/second for spot trading
- Required headers: KEY, SIGN, Timestamp, Content-Type

Threading: Fully async/await compatible, thread-safe
Memory: O(1) per request, optimized for trading operations
"""

from typing import Dict, List, Optional
import msgspec

from exchanges.structs.common import (
    Symbol, Order, AssetBalance,
    AssetInfo, NetworkInfo, TradingFee,
    WithdrawalRequest, WithdrawalResponse, DepositResponse, DepositAddress
)
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs.enums import TimeInForce, WithdrawalStatus, DepositStatus
from exchanges.structs import OrderType, Side
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.http.structs import HTTPMethod
from exchanges.interfaces.rest import PrivateSpotRestInterface
from config.structs import ExchangeConfig
from infrastructure.exceptions.exchange import ExchangeRestError, OrderCancelledOrFilled, OrderNotFoundError

# Import direct utility functions
from exchanges.integrations.gateio.utils import (
    from_side, from_order_type, format_quantity, format_price,
    from_time_in_force, rest_spot_to_order, to_withdrawal_status, to_deposit_status
)
from exchanges.integrations.gateio.structs.exchange import GateioCurrencyResponse, GateioWithdrawStatusResponse
from utils import get_current_timestamp
from exchanges.integrations.gateio.services.spot_symbol_mapper import GateioSpotSymbol

from .gateio_base_spot_rest import GateioBaseSpotRestInterface
from exchanges.utils.network_mapping import get_unified_network_name

class GateioPrivateSpotRestInterface(GateioBaseSpotRestInterface, PrivateSpotRestInterface):
    """
    Gate.io private REST API client focused on trading operations.
    
    Provides access to authenticated trading endpoints without WebSocket features.
    Optimized for high-frequency trading operations with minimal overhead.
    """
    @property
    def asset_info(self) -> Dict[AssetName, AssetInfo]:
        return self._asset_info

    def __init__(self, config: ExchangeConfig, logger: HFTLoggerInterface = None, **kwargs):
        """
        Initialize Gate.io private spot REST client with unified constructor.
        
        Args:
            config: ExchangeConfig with Gate.io URL and credentials
            logger: HFT logger instance (injected)
            **kwargs: Additional parameters for compatibility
        """
        # Initialize base REST client (rate_limiter created internally)
        super().__init__(config, logger, is_private=True)
        self._asset_info: Dict[AssetName, AssetInfo] = {}

        # Initialize HFT logger if not provided
        if logger is None:
            from infrastructure.logging import get_exchange_logger
            logger = get_exchange_logger('gateio', 'rest.private')
        self.logger = logger

    async def get_assets_info(self) -> Dict[AssetName, AssetInfo]:
        """
        Get currency information including deposit/withdrawal status and network details.

        For Gate.io, this method delegates to get_currency_info() which already
        implements the same functionality.

        Returns:
            Dictionary mapping AssetName to AssetInfo with network configurations

        Raises:
            ExchangeAPIError: If unable to fetch currency information
        """
        return await self.get_currency_info()

    async def get_balances(self) -> List[AssetBalance]:
        """
        Get account balance for all assets.
        
        HFT COMPLIANT: Never caches balance data - always fresh API call.
        
        Returns:
            List of AssetBalance objects for all assets with non-zero balances
            
        Raises:
            ExchangeAPIError: If unable to fetch balance data
        """
        try:
            endpoint = '/spot/accounts'
            
            response_data = await self.request(
                HTTPMethod.GET,
                endpoint
            )
            
            # Gate.io accounts response format:
            # [
            #   {
            #     "currency": "USDT"
            #     "available": "1000.0"
            #     "locked": "0.0"
            #   }, ...
            # ]
            
            if not isinstance(response_data, list):
                raise ExchangeRestError(500, "Invalid balance response format")
            
            balances = []
            for balance_data in response_data:
                balance = AssetBalance(
                                asset=AssetName(balance_data['currency']),
                                available=float(balance_data['available']),
                                locked=float(balance_data['locked'])
                            )
                # Only include assets with non-zero total balance
                if balance.total > 0:
                    balances.append(balance)
            
            self.logger.debug(f"Retrieved {len(balances)} account balances")
            return balances
            
        except Exception as e:
            self.logger.error(f"Failed to get account balance: {e}")
            raise ExchangeRestError(500, f"Balance fetch failed: {str(e)}")
    
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
            balances = await self.get_balances()
            
            for balance in balances:
                if balance.asset == asset:
                    return balance
            
            # Return zero balance if asset not found
            return AssetBalance(
                asset=asset,
                available=0.0,
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
        quantity: Optional[float] = None,
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
            quantity: Order quantity in exchanges asset
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
    
        pair = GateioSpotSymbol.to_pair(symbol)
        
        # Validate required parameters based on order type
        if order_type in [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.STOP_LIMIT]:
            if price is None:
                raise ValueError(f"Price is required for {order_type.name} orders")

        if order_type in [OrderType.STOP_LIMIT, OrderType.STOP_MARKET]:
            if stop_price is None:
                raise ValueError(f"Stop price is required for {order_type.name} orders")

        # For MARKET buy orders, either amount or quote_quantity is required
        if order_type == OrderType.MARKET and side == Side.BUY:
            if quantity is None and quote_quantity is None:
                raise ValueError("Either amount or quote_quantity is required for MARKET buy orders")
        elif quantity is None:
            raise ValueError("Amount is required for this order type")

        # Build order payload
        payload = {
            'currency_pair': pair,
            'side': from_side(side),
            'type': from_order_type(order_type)
        }
        
        # Set time in force (only for limit orders - Gate.io market orders don't support time_in_force)
        if order_type == OrderType.LIMIT:
            if time_in_force is None:
                time_in_force = TimeInForce.GTC
            payload['time_in_force'] = from_time_in_force(time_in_force)
        elif order_type == OrderType.MARKET:
            # Market orders only support IOC and FOK, and only when explicitly specified
            if time_in_force is None:
                time_in_force = TimeInForce.IOC

            if time_in_force in [TimeInForce.IOC, TimeInForce.FOK]:
                payload['time_in_force'] = from_time_in_force(time_in_force)

        # Handle different order configurations
        if order_type == OrderType.MARKET:
            if side == Side.BUY:
                # Market buy: specify quote quantity
                if quote_quantity is None:
                    raise ValueError("Market buy orders require quote_quantity")
                    # if quantity is None or price is None:
                    #     raise ValueError("Market buy orders require quote_quantity or (quantity + price)")
                    # quote_quantity = quantity * price
                payload['amount'] = str(quote_quantity) # format_quantity(quote_quantity)
            else:
                # Market sell: specify exchanges quantity
                if quantity is None:
                    raise ValueError("Market sell orders require quantity")
                payload['amount'] = str(quantity) # format_quantity(quantity)
        else:
            # Limit order: require both price and amount
            if price is None or quantity is None:
                raise ValueError("Limit orders require both price and amount")
            
            payload['price'] = str(price) # format_price(price)
            payload['amount'] = str(quantity) # format_quantity(quantity)
        
        # Make authenticated request
        endpoint = '/spot/orders'
        
        response_data = await self.request(
            HTTPMethod.POST,
            endpoint,
            data=payload
        )
        
        # Transform Gate.io response to unified Order
        order = rest_spot_to_order(response_data)
        
        self.logger.info(f"Placed {side.name} order: {order.order_id}")
        return order
    
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
        pair = GateioSpotSymbol.to_pair(symbol)
        
        params = {
            'currency_pair': pair, 
        }
        try:
            response_data = await self.request(
                HTTPMethod.DELETE,
                f'/spot/orders/{order_id}',
                params=params
            )
        except OrderCancelledOrFilled as e:
            self.logger.warning(f"Order {order_id} for {symbol.base}/{symbol.quote} already cancelled/filled or does not exist")
            # TODO: warning x2 latency costs
            return await self.get_order(symbol, order_id)

        order = rest_spot_to_order(response_data)
        
        self.logger.info(f"Cancelled order: {order_id}")
        return order
    
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
            pair = GateioSpotSymbol.to_pair(symbol)
            endpoint = '/spot/orders'
            
            params = {'currency_pair': pair}
            
            response_data = await self.request(
                HTTPMethod.DELETE,
                endpoint,
                params=params
            )
            
            # Gate.io returns list of cancelled orders
            if not isinstance(response_data, list):
                raise ExchangeRestError(500, "Invalid cancel all orders response format")
            
            cancelled_orders = []
            for order_data in response_data:
                order = rest_spot_to_order(order_data)
                cancelled_orders.append(order)
            
            self.logger.info(f"Cancelled {len(cancelled_orders)} orders for {symbol}")
            return cancelled_orders
            
        except Exception as e:
            self.logger.error(f"Failed to cancel all orders for {symbol}: {e}")
            raise ExchangeRestError(500, f"Mass order cancellation failed: {str(e)}")
    
    async def get_order(self, symbol: Symbol, order_id: OrderId) -> Order | None:
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
            pair = GateioSpotSymbol.to_pair(symbol)
            endpoint = f'/spot/orders/{order_id}'
            
            params = {'currency_pair': pair}
            
            response_data = await self.request(
                HTTPMethod.GET,
                endpoint,
                params=params
            )
            
            # Transform Gate.io response to unified Order
            order = rest_spot_to_order(response_data)
            
            self.logger.debug(f"Retrieved order status: {order_id}")
            return order
        except OrderNotFoundError as e:
            self.logger.error(e.message)
            return None
        except Exception as e:
            self.logger.error(f"Failed to get order {order_id}: {e}")
            raise ExchangeRestError(500, f"Order query failed: {str(e)}")
    
    async def get_open_orders(self, symbol: Optional[Symbol] = None) -> List[Order]:
        """
        Get open orders for a specific symbol.
        
        Note: Gate.io requires currency_pair parameter. If no symbol is provided
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
            
            endpoint = '/spot/orders'
            params = {
                'status': 'open',
                'currency_pair': GateioSpotSymbol.to_pair(symbol),
                'limit': 100    # Maximum limit for open orders
            }
            
            response_data = await self.request(
                HTTPMethod.GET,
                endpoint,
                params=params
            )
            
            # Gate.io returns list of orders
            if not isinstance(response_data, list):
                raise ExchangeRestError(500, "Invalid open orders response format")
            
            open_orders = []
            for order_data in response_data:
                order = rest_spot_to_order(order_data)
                open_orders.append(order)
            
            symbol_str = f" for {symbol}" if symbol else ""
            self.logger.debug(f"Retrieved {len(open_orders)} open orders{symbol_str}")
            return open_orders
            
        except Exception as e:
            symbol_str = f" for {symbol}" if symbol else ""
            self.logger.error(f"Failed to get open orders{symbol_str}: {e}")
            raise ExchangeRestError(500, f"Open orders retrieval failed: {str(e)}")
    
    async def modify_order(
        self,
        symbol: Symbol,
        order_id: OrderId,
        qunatity: Optional[float] = None,
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
            qunatity: New order amount
            price: New order price
            quote_quantity: New quote quantity
            time_in_force: New time in force
            stop_price: New stop price (not used)
            
        Returns:
            New Order object
            
        Raises:
            ExchangeAPIError: If modification fails
        """
        # TODO: implement modify order with single call
        # https://www.gate.com/docs/developers/apiv4/en/#amend-single-order

    async def get_currency_info(self) -> Dict[AssetName, AssetInfo]:
        """
        Get currency information including deposit/withdrawal status and network details.

        Combines data from Gate.io's `/spot/currencies` and `/wallet/withdraw_status` endpoints
        to provide complete asset information including withdrawal fees and minimums.
        """
        try:
            # Fetch currency information (network details, deposit/withdraw status)
            currencies_response = await self.request(
                HTTPMethod.GET,
                "/spot/currencies"
            )
            currencies_data = msgspec.convert(currencies_response, list[GateioCurrencyResponse])

            # Fetch withdrawal status (fees and limits)
            withdraw_status_response = await self.request(
                HTTPMethod.GET,
                "/wallet/withdraw_status"
            )
            withdraw_status_data = msgspec.convert(withdraw_status_response, list[GateioWithdrawStatusResponse])

            # Create lookup map for withdrawal status
            withdraw_status_map = {item.currency: item for item in withdraw_status_data}

            currency_info_map: Dict[AssetName, AssetInfo] = {}

            for currency_data in currencies_data:
                asset_name = AssetName(currency_data.currency)

                if currency_data.delisted:
                    continue

                # Get withdrawal status for this currency
                withdraw_status = withdraw_status_map.get(currency_data.currency)

                networks: Dict[str, NetworkInfo] = {}
                overall_deposit_enable = False
                overall_withdraw_enable = False

                # Check if chains data exists
                if currency_data.chains:
                    for chain in currency_data.chains:
                        # Determine deposit/withdraw status based on disabled flags
                        deposit_enable = not chain.deposit_disabled if chain.deposit_disabled is not None else True
                        withdraw_enable = not chain.withdraw_disabled if chain.withdraw_disabled is not None else True
                        
                        # Consider withdraw_delayed as disabling withdrawals if needed
                        if chain.withdraw_delayed:
                            withdraw_enable = False

                        # Get withdrawal fee for this specific chain
                        withdraw_fee = 0.0
                        withdraw_min = 0.0
                        withdraw_max = None

                        if withdraw_status:
                            # Try to get chain-specific fee first
                            if withdraw_status.withdraw_fix_on_chains and chain.name in withdraw_status.withdraw_fix_on_chains:
                                try:
                                    withdraw_fee = float(withdraw_status.withdraw_fix_on_chains[chain.name])
                                except (ValueError, TypeError):
                                    withdraw_fee = 0.0
                            # Fallback to default fee
                            elif withdraw_status.withdraw_fix:
                                try:
                                    withdraw_fee = float(withdraw_status.withdraw_fix)
                                except (ValueError, TypeError):
                                    withdraw_fee = 0.0

                            # Get minimum withdrawal amount
                            if withdraw_status.withdraw_amount_mini:
                                try:
                                    withdraw_min = float(withdraw_status.withdraw_amount_mini)
                                except (ValueError, TypeError):
                                    withdraw_min = 0.0

                            # Get maximum withdrawal amount
                            if withdraw_status.withdraw_eachtime_limit:
                                try:
                                    withdraw_max = float(withdraw_status.withdraw_eachtime_limit)
                                except (ValueError, TypeError):
                                    withdraw_max = None
                            
                        network_info = NetworkInfo(
                            network=get_unified_network_name(chain.name),  # Use name as the network identifier
                            deposit_enable=deposit_enable,
                            withdraw_enable=withdraw_enable,
                            withdraw_fee=withdraw_fee,
                            withdraw_min=withdraw_min,
                            withdraw_max=withdraw_max,
                            min_confirmations=None,  # Not available in /spot/currencies
                            address=chain.addr,  # Store contract address
                            memo=None
                        )

                        networks[chain.name] = network_info

                        if deposit_enable:
                            overall_deposit_enable = True
                        if withdraw_enable:
                            overall_withdraw_enable = True

                # Check global deposit/withdrawal disable flags
                if currency_data.deposit_disabled:
                    overall_deposit_enable = False
                if currency_data.withdraw_disabled or currency_data.withdraw_delayed:
                    overall_withdraw_enable = False

                asset_info = AssetInfo(
                    asset=asset_name,
                    name=currency_data.currency,
                    deposit_enable=overall_deposit_enable,
                    withdraw_enable=overall_withdraw_enable,
                    networks=networks
                )

                currency_info_map[asset_name] = asset_info

            self.logger.debug(f"Retrieved currency info for {len(currency_info_map)} assets")

            self._asset_info = currency_info_map

            return currency_info_map

        except Exception as e:
            self.logger.error(f"Failed to get currency information: {e}")
            raise ExchangeRestError(500, f"Currency info fetch failed: {str(e)}")

    
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
            exchanges compatibility but Gate.io will always return account-level rates.
        """
        try:
            # Log the request details
            if symbol:
                self.logger.debug(f"Retrieving trading fees for symbol {symbol.base}/{symbol.quote}")
                self.logger.warning(f"Gate.io API limitation: Symbol-specific fees not supported, returning account-level fees")
            else:
                self.logger.debug("Retrieving account-level trading fees")
            
            endpoint = '/spot/fee'
            
            response_data = await self.request(
                HTTPMethod.GET,
                endpoint
            )
            
            # Gate.io fee response format based on API docs:
            # {
            #   "user_id": 10003
            #   "taker_fee": "0.002"
            #   "maker_fee": "0.002"
            #   "gt_discount": false
            #   "gt_taker_fee": "0.0015"
            #   "gt_maker_fee": "0.0015"
            #   "loan_fee": "0.18"
            #   "point_type": "0" // fee tier
            # }
            
            if not isinstance(response_data, dict):
                raise ExchangeRestError(500, "Invalid trading fees response format")
            
            # Extract fee rates - Gate.io returns string values
            maker_rate = float(response_data.get('maker_fee', '0.002'))
            taker_rate = float(response_data.get('taker_fee', '0.002'))
            point_type = response_data.get('point_type', '0')
            
            # Gate.io doesn't provide 30-day volume in fee response
            # Could be fetched separately if needed
            
            trading_fee = TradingFee(
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
            raise ExchangeRestError(500, f"Trading fees fetch failed: {str(e)}")

    # Withdrawal operations

    async def submit_withdrawal(self, request: WithdrawalRequest) -> WithdrawalResponse:
        """
        Submit a withdrawal request to Gate.io.

        Args:
            request: Withdrawal request parameters

        Returns:
            WithdrawalResponse with withdrawal details

        Raises:
            ExchangeAPIError: If withdrawal submission fails
        """
        # Validate request before submission
        await self.validate_withdrawal_request(request)

        # Prepare Gate.io API parameters
        payload = {
            'currency': request.asset,
            'amount': str(request.amount),
            'address': request.address
        }

        # Add chain if specified (required for multi-chain assets)
        if request.network:
            payload['chain'] = request.network

        # Add memo if provided (for coins that require it)
        if request.memo:
            payload['memo'] = request.memo

        try:
            response_data = await self.request(
                HTTPMethod.POST,
                '/withdrawals',
                data=payload
            )

            # Gate.io response format: {"id": "withdrawal_id"}
            withdrawal_id = response_data.get('id', '')

            if not withdrawal_id:
                raise ExchangeRestError(500, "No withdrawal ID returned from Gate.io")

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
        Cancel a pending withdrawal on Gate.io.

        Args:
            withdrawal_id: Exchange withdrawal ID to cancel

        Returns:
            True if cancellation successful, False otherwise

        Raises:
            ExchangeAPIError: If cancellation fails
        """
        try:
            response_data = await self.request(
                HTTPMethod.DELETE,
                f'/withdrawals/{withdrawal_id}'
            )

            # Gate.io returns the cancelled withdrawal details
            # Success is indicated by receiving the withdrawal data without error
            self.logger.info(f"Cancelled withdrawal {withdrawal_id}: {response_data}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to cancel withdrawal {withdrawal_id}: {e}")
            # Check if it's a 404 (withdrawal not found) or other error
            if "404" in str(e) or "not found" in str(e).lower():
                return False
            raise ExchangeRestError(500, f"Withdrawal cancellation failed: {e}")

    async def get_withdrawal_status(self, withdrawal_id: str) -> WithdrawalResponse:
        """
        Get current status of a withdrawal on Gate.io.

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
        Get withdrawal history from Gate.io.

        Args:
            asset: Optional asset filter
            limit: Maximum number of withdrawals to return

        Returns:
            List of historical withdrawals
        """
        params = {}

        if asset:
            params['currency'] = asset

        # Gate.io supports up to 1000 records
        params['limit'] = min(limit, 1000)

        try:
            response_data = await self.request(
                HTTPMethod.GET,
                '/withdrawals',
                params=params
            )

            withdrawals = []

            # Gate.io returns a list of withdrawal records
            for withdrawal_data in response_data:
                # Map Gate.io status to our enum
                gateio_status = withdrawal_data.get('status', '')
                status = to_withdrawal_status(gateio_status)

                withdrawal = WithdrawalResponse(
                    withdrawal_id=str(withdrawal_data.get('id', '')),
                    asset=AssetName(withdrawal_data.get('currency', '')),
                    amount=float(withdrawal_data.get('amount', 0)),
                    fee=float(withdrawal_data.get('fee', 0)),
                    address=withdrawal_data.get('address', ''),
                    network=withdrawal_data.get('chain'),
                    status=status,
                    timestamp=int(withdrawal_data.get('timestamp', 0) * 1000),  # Gate.io uses seconds
                    memo=withdrawal_data.get('memo'),
                    tx_id=withdrawal_data.get('txid')
                )
                withdrawals.append(withdrawal)

            self.logger.info(f"Retrieved {len(withdrawals)} withdrawal records")
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
        Get deposit history from Gate.io.
        
        Args:
            asset: Optional asset filter
            limit: Maximum number of deposits to return
            
        Returns:
            List of historical deposits
        """
        params = {}
        
        if asset:
            params['currency'] = asset
            
        # Gate.io supports up to 500 records  
        params['limit'] = min(limit, 500)
        
        try:
            response_data = await self.request(
                HTTPMethod.GET,
                '/deposits',
                params=params
            )
            
            deposits = []
            
            # Gate.io returns a list of deposit records
            for deposit_data in response_data:
                # Map Gate.io status to our enum
                gateio_status = deposit_data.get('status', '')
                status = to_deposit_status(gateio_status)
                
                deposit = DepositResponse(
                    deposit_id=str(deposit_data.get('id', '')),
                    asset=AssetName(deposit_data.get('currency', '')),
                    amount=float(deposit_data.get('amount', 0)),
                    address=deposit_data.get('address', ''),
                    network=deposit_data.get('chain'),
                    status=status,
                    timestamp=int(deposit_data.get('timestamp', 0) * 1000),  # Gate.io uses seconds
                    memo=deposit_data.get('memo'),
                    tx_id=deposit_data.get('txid')
                )
                deposits.append(deposit)
                
            self.logger.info(f"Retrieved {len(deposits)} deposit records")
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
        Get deposit history from Gate.io with optional time filtering.
        
        Args:
            asset: Optional asset filter
            limit: Maximum number of deposits to return (max 500)
            start_time: Optional start time in milliseconds since epoch
            end_time: Optional end time in milliseconds since epoch
            
        Returns:
            List of historical deposits
            
        Raises:
            ExchangeAPIError: If unable to fetch deposit history
        """
        params = {}
        
        if asset:
            params['currency'] = asset
            
        # Gate.io supports up to 500 records  
        params['limit'] = min(limit, 500)
        
        # Add time filtering if provided (Gate.io uses seconds)
        if start_time:
            params['from'] = start_time // 1000  # Convert milliseconds to seconds
        if end_time:
            params['to'] = end_time // 1000  # Convert milliseconds to seconds
        
        try:
            response_data = await self.request(
                HTTPMethod.GET,
                '/deposits',
                params=params
            )
            
            deposits = []
            
            # Gate.io returns a list of deposit records
            for deposit_data in response_data:
                # Map Gate.io status to our enum
                gateio_status = deposit_data.get('status', '')
                status = to_deposit_status(gateio_status)
                
                deposit = DepositResponse(
                    deposit_id=str(deposit_data.get('id', '')),
                    asset=AssetName(deposit_data.get('currency', '')),
                    amount=float(deposit_data.get('amount', 0)),
                    address=deposit_data.get('address', ''),
                    network=deposit_data.get('chain'),
                    status=status,
                    timestamp=int(deposit_data.get('timestamp', 0) * 1000),  # Gate.io uses seconds
                    memo=deposit_data.get('memo'),
                    tx_id=deposit_data.get('txid')
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
        Get deposit address for the specified asset and network from Gate.io.

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
            'currency': asset
        }
        
        # Add chain if specified
        if network:
            params['chain'] = network

        try:
            # Use Gate.io deposit address endpoint
            response_data = await self.request(
                HTTPMethod.GET,
                '/wallet/deposit_address',
                params=params
            )

            # Gate.io response format: {"currency": "BTC", "address": "...", "multichain_addresses": [...]}
            address = response_data.get('address', '')
            if not address:
                raise ExchangeRestError(500, f"No deposit address returned for {asset}")

            # Extract memo if present (Gate.io doesn't typically use memos in this endpoint)
            memo = response_data.get('memo') or response_data.get('tag')
            
            # Get chain from response or use provided network
            response_network = response_data.get('chain', network or 'default')

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

    async def close(self) -> None:
        """Close the REST client and clean up resources."""
        try:
            # Transport manager handles cleanup automatically
            self.logger.info("Closed Gate.io private REST client")
        except Exception as e:
            self.logger.error(f"Error closing private REST client: {e}")
