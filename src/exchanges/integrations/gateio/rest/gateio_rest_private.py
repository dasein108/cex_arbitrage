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

from infrastructure.data_structures.common import (
    Symbol, Order, OrderId, OrderType, Side, AssetBalance,
    AssetName, AssetInfo, NetworkInfo, TimeInForce, TradingFee,
    WithdrawalRequest, WithdrawalResponse, WithdrawalStatus
)
from exchanges.base.rest.spot.base_rest_spot_private import PrivateExchangeSpotRestInterface
from infrastructure.config.structs import ExchangeConfig
from exchanges.services import BaseExchangeMapper
from infrastructure.exceptions.exchange import BaseExchangeError


class GateioPrivateSpotRest(PrivateExchangeSpotRestInterface):
    """
    Gate.io private REST API client focused on trading operations.
    
    Provides access to authenticated trading endpoints without WebSocket features.
    Optimized for high-frequency trading operations with minimal overhead.
    """

    def __init__(self, config: ExchangeConfig, mapper: BaseExchangeMapper, logger=None):
        """
        Initialize Gate.io private REST client.
        
        Args:
            config: ExchangeConfig with Gate.io configuration and credentials
            mapper: BaseExchangeMapper for data transformations
            logger: Optional HFT logger injection
        """
        super().__init__(config, mapper)
        
        # Initialize HFT logger
        if logger is None:
            from infrastructure.logging import get_exchange_logger
            logger = get_exchange_logger('gateio', 'rest.private')
        self.logger = logger

    
    def _handle_gateio_exception(self, status_code: int, message: str) -> BaseExchangeError:
        """Handle Gate.io specific exceptions."""
        return BaseExchangeError(f"Gate.io error {status_code}: {message}")

    # Authentication is now handled automatically by the transport system

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
            endpoint = "/spot/accounts"
            
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
                raise BaseExchangeError(500, "Invalid balance response format")
            
            balances = []
            for balance_data in response_data:
                balance = self._mapper.rest_to_balance(balance_data)
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
            amount: Order quantity in exchanges asset
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
            pair = self._mapper.to_pair(symbol)
            
            # Build order payload
            payload = {
                'currency_pair': pair,
                'side': self._mapper.from_side(side),
                'type': self._mapper.from_order_type(order_type)
            }
            
            # Set time in force
            if time_in_force is None:
                time_in_force = TimeInForce.GTC
            payload['time_in_force'] = self._mapper.from_time_in_force(time_in_force)
            
            # Handle different order configurations
            if order_type == OrderType.MARKET:
                if side == Side.BUY:
                    # Market buy: specify quote quantity
                    if quote_quantity is None:
                        if amount is None or price is None:
                            raise ValueError("Market buy orders require quote_quantity or (amount + price)")
                        quote_quantity = amount * price
                    payload['amount'] = self._mapper.format_quantity(quote_quantity)
                else:
                    # Market sell: specify exchanges quantity
                    if amount is None:
                        raise ValueError("Market sell orders require amount")
                    payload['amount'] = self._mapper.format_quantity(amount)
            else:
                # Limit order: require both price and amount
                if price is None or amount is None:
                    raise ValueError("Limit orders require both price and amount")
                
                payload['price'] = self._mapper.format_price(price)
                payload['amount'] = self._mapper.format_quantity(amount)
            
            # Add special parameters for specific order types
            # TODO: fix or remove !
            # order_params = self._mapper.get_order_params(order_type, time_in_force)
            # payload.update(order_params)
            #
            # Make authenticated request
            endpoint = '/spot/orders'
            
            response_data = await self.request(
                HTTPMethod.POST,
                endpoint,
                data=payload
            )
            
            # Transform Gate.io response to unified Order
            order = self._mapper.rest_to_order(response_data)
            
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
            pair = self._mapper.to_pair(symbol)
            endpoint = f'/spot/orders/{order_id}'
            
            params = {'currency_pair': pair}
            
            response_data = await self.request(
                HTTPMethod.DELETE,
                endpoint,
                params=params
            )
            
            # Transform Gate.io response to unified Order
            order = self._mapper.rest_to_order(response_data)
            
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
            pair = self._mapper.to_pair(symbol)
            endpoint = '/spot/orders'
            
            params = {'currency_pair': pair}
            
            response_data = await self.request(
                HTTPMethod.DELETE,
                endpoint,
                params=params
            )
            
            # Gate.io returns list of cancelled orders
            if not isinstance(response_data, list):
                raise BaseExchangeError(500, "Invalid cancel all orders response format")
            
            cancelled_orders = []
            for order_data in response_data:
                order = self._mapper.rest_to_order(order_data)
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
            pair = self._mapper.to_pair(symbol)
            endpoint = f'/spot/orders/{order_id}'
            
            params = {'currency_pair': pair}
            
            response_data = await self.request(
                HTTPMethod.GET,
                endpoint,
                params=params
            )
            
            # Transform Gate.io response to unified Order
            order = self._mapper.rest_to_order(response_data)
            
            self.logger.debug(f"Retrieved order status: {order_id}")
            return order
            
        except Exception as e:
            self.logger.error(f"Failed to get order {order_id}: {e}")
            raise BaseExchangeError(500, f"Order query failed: {str(e)}")
    
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
                'currency_pair': self._mapper.to_pair(symbol)
            }
            
            response_data = await self.request(
                HTTPMethod.GET,
                endpoint,
                params=params
            )
            
            # Gate.io returns list of orders
            if not isinstance(response_data, list):
                raise BaseExchangeError(500, "Invalid open orders response format")
            
            open_orders = []
            for order_data in response_data:
                order = self._mapper.rest_to_order(order_data)
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
        # TODO: implement modify order with single call
        # https://www.gate.com/docs/developers/apiv4/en/#amend-single-order

    # Gate.io doesn't have listen key endpoints like Binance
    # These methods are required by exchanges but not applicable
    
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

    async def get_currency_info(self) -> Dict[AssetName, AssetInfo]:
        """
        Get currency information including deposit/withdrawal status and network details.

        Uses only Gate.io's `/spot/currencies` endpoint.
        """
        try:

            currencies_response = await self.request(
                HTTPMethod.GET,
                "/spot/currencies"
            )
            currencies_data = msgspec.convert(currencies_response, list[GateioCurrencyResponse])

            currency_info_map: Dict[AssetName, AssetInfo] = {}

            for currency_data in currencies_data:
                asset_name = AssetName(currency_data.currency)

                if currency_data.delisted:
                    continue

                networks: Dict[str, NetworkInfo] = {}
                overall_deposit_enable = False
                overall_withdraw_enable = False

                
                for chain in currency_data.chains:
                    network_info = NetworkInfo(
                        network=chain.chain,
                        deposit_enable=chain.deposit,
                        withdraw_enable=chain.withdraw,
                        withdraw_fee=float(chain.withdraw_fee or 0),
                        withdraw_min=float(chain.min_withdraw or 0),
                        withdraw_max=float(chain.max_withdraw) if chain.max_withdraw else None,
                        min_confirmations=chain.confirmation,
                        address=None,
                        memo=None
                    )

                    networks[chain.chain] = network_info

                    
                    if chain.deposit:
                        overall_deposit_enable = True
                    if chain.withdraw:
                        overall_withdraw_enable = True

                
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

            self.logger.info(f"Retrieved currency info for {len(currency_info_map)} assets")
            return currency_info_map

        except Exception as e:
            self.logger.error(f"Failed to get currency information: {e}")
            raise BaseExchangeError(500, f"Currency info fetch failed: {str(e)}")

    
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
                raise BaseExchangeError(500, "No withdrawal ID returned from Gate.io")

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
            raise BaseExchangeError(500, f"Withdrawal cancellation failed: {e}")

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
                status = map_gateio_withdrawal_status(gateio_status)

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
            raise BaseExchangeError(500, f"Failed to get withdrawal history: {e}")


    def _get_current_timestamp(self) -> int:
        """Get current timestamp in milliseconds."""
        import time
        return int(time.time() * 1000)

    async def close(self) -> None:
        """Close the REST client and clean up resources."""
        try:
            # Transport manager handles cleanup automatically
            self.logger.info("Closed Gate.io private REST client")
        except Exception as e:
            self.logger.error(f"Error closing private REST client: {e}")

    def __repr__(self) -> str:
        return f"GateioPrivateExchange(base_url={self.base_url})"