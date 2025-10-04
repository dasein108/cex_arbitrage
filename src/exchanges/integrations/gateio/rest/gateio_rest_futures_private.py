import time
from typing import Dict, List, Optional, Any

from exchanges.interfaces import PrivateFuturesRestInterface
from exchanges.structs.common import Symbol, Order, AssetBalance, TradingFee, Position
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs.enums import TimeInForce
from exchanges.structs import OrderType, Side
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.http.structs import HTTPMethod
from infrastructure.exceptions.exchange import ExchangeRestError, OrderNotFoundError

from config.structs import ExchangeConfig

# Import direct utility functions
from exchanges.integrations.gateio.utils import (
    format_quantity,
    format_price,
    from_time_in_force,
    rest_futures_to_order,
    futures_balance_entry,
    detect_side_from_size,
)
from exchanges.integrations.gateio.services.futures_symbol_mapper import (
    GateioFuturesSymbol,
)


from .gateio_base_futures_rest import GateioBaseFuturesRestInterface


class GateioPrivateFuturesRestInterface(
    GateioBaseFuturesRestInterface, PrivateFuturesRestInterface
):
    def __init__(
        self, config: ExchangeConfig, logger: HFTLoggerInterface = None, **kwargs
    ):
        """
        Initialize Gate.io private futures REST client with simplified constructor.

        Args:
            config: ExchangeConfig containing credentials & transport config
            logger: HFT logger instance (injected)
            **kwargs: Additional parameters for compatibility
        """
        # Initialize base REST client (rate_limiter created internally)
        super().__init__(config, logger, is_private=True)

    async def get_balances(self) -> List[AssetBalance]:
        """
        Get futures (margin) account balance. Returns list (usually single USDT entry).
        Endpoint (typical): /futures/usdt/accounts
        """
        try:
            endpoint = "/futures/usdt/accounts"
            response = await self.request(HTTPMethod.GET, endpoint)

            balances: List[AssetBalance] = []

            # Support both dict (single account summary) and list formats
            if isinstance(response, dict):
                # Common fields: total, available
                balances = [futures_balance_entry(response)]

            elif isinstance(response, list):
                # List of assets: try parse entries
                balances = [futures_balance_entry(item) for item in response]
            else:
                raise ExchangeRestError(500, "Invalid futures accounts response format")

            self.logger.debug(f"Retrieved futures balances: {balances}")
            return balances

        except Exception as e:
            self.logger.error(f"Failed to get futures account balance: {e}")
            raise ExchangeRestError(500, f"Futures balance fetch failed: {str(e)}")

    async def get_asset_balance(self, asset: AssetName) -> Optional[AssetBalance]:
        try:
            balances = await self.get_balances()
            for b in balances:
                if b.asset == asset:
                    return b
            return AssetBalance(asset=asset, available=0.0, locked=0.0)
        except Exception as e:
            self.logger.error(f"Failed to get futures asset balance {asset}: {e}")
            raise

    async def place_order(
        self,
        symbol: Symbol,
        side: Side,
        order_type: OrderType,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        time_in_force: Optional[float] = None,
        quote_quantity: Optional[float] = None,
        stop_price: Optional[float] = None,
        iceberg_qty: Optional[float] = None,
        stp_act: Optional[str] = None,
    ) -> Order:
        """
        Place a futures order. Uses /futures/usdt/orders.   
        Notes:
          - Uses self._mapper to convert symbol <-> contract and types/sides.
          - For MARKET orders, prefer 'amount' as size (composite units). If quote_quantity given
            and price provided, compute size = quote_quantity / price.
        """
        try:
            contract = GateioFuturesSymbol.to_pair(symbol)
            payload: dict[str, Any] = {"contract": contract}

            if quantity is not None:
                base_qty = float(quantity)
            elif quote_quantity is not None:
                if price is None:
                    self.logger.error("Quote_quantity requires price to compute quantity")
                    raise ExchangeRestError(400, "Quote_quantity requires price to compute quantity")
                base_qty = float(quote_quantity) / float(price)
            else:
                self.logger.error("Either quantity or quote_quantity must be provided")
                raise ExchangeRestError(400, "Either quantity or quote_quantity must be provided")

            signed_qty = base_qty if side == Side.BUY else -abs(base_qty)
            payload["size"] = int(signed_qty)  # API expects integer

            if order_type in (OrderType.MARKET, OrderType.STOP_MARKET):
                payload["price"] = "0"
            else:
                if price is None:
                    self.logger.error(f"{order_type.name} requires price")
                    raise ExchangeRestError(400, f"{order_type.name} requires price")
                payload["price"] = format_price(price)

            if order_type in (OrderType.STOP_LIMIT, OrderType.STOP_MARKET) and stop_price is None:
                self.logger.error(f"{order_type.name} requires stop_price")
                raise ExchangeRestError(400, f"{order_type.name} requires stop_price")
            if stop_price is not None:
                payload["stop"] = format_price(stop_price)

            payload["tif"] = from_time_in_force(time_in_force)

            if iceberg_qty is not None:
                payload["iceberg"] = format_quantity(iceberg_qty)
            if stp_act:
                payload["stp_act"] = stp_act

            endpoint = "/futures/usdt/orders"
            response = await self.request(HTTPMethod.POST, endpoint, data=payload)
            order = rest_futures_to_order(response)
            self.logger.info(f"Placed futures order {order.order_id}")
            return order

        except Exception as e:
            self.logger.error(f"Failed to place futures order. {str(e)}")
            raise ExchangeRestError(500, f"Futures order placement failed: {str(e)}")

    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> Order | None:
        """
        Cancel single futures order. DELETE /futures/usdt/orders/{id}?contract=...
        """
        try:
            contract = GateioFuturesSymbol.to_pair(symbol)
            endpoint = f"/futures/usdt/orders/{order_id}"
            params = {"contract": contract}
            response = await self.request(HTTPMethod.DELETE, endpoint, params=params)

            return rest_futures_to_order(response)
        except OrderNotFoundError as e:
            self.logger.error(e)
            return None
        except Exception as e:
            self.logger.error(f"Failed to cancel futures order {order_id}: {e}")
            raise ExchangeRestError(500, f"Futures order cancellation failed: {str(e)}")

    async def cancel_all_orders(self, symbol: Symbol) -> List[Order]:
        """
        Cancel all open futures orders for a contract.
        Endpoint: DELETE /futures/usdt/orders?contract=...
        """
        try:
            contract = GateioFuturesSymbol.to_pair(symbol)
            endpoint = "/futures/usdt/orders"
            params = {"contract": contract}
            response = await self.request(HTTPMethod.DELETE, endpoint, params=params)

            cancelled: List[Order] = []
            if isinstance(response, list):
                for item in response:
                    cancelled.append(rest_futures_to_order(item))
            else:
                cancelled.append(rest_futures_to_order(response))

            self.logger.info(f"Cancelled {len(cancelled)} futures orders for {symbol}")
            return cancelled

        except Exception as e:
            self.logger.error(f"Failed to cancel all futures orders for {symbol}: {e}")
            raise ExchangeRestError(500, f"Futures mass cancellation failed: {str(e)}")

    async def get_order(self, symbol: Symbol, order_id: OrderId) -> Order | None:
        """
        Query single futures order: GET /futures/usdt/orders/{id}?contract=...
        """
        try:
            contract = GateioFuturesSymbol.to_pair(symbol)
            endpoint = f"/futures/usdt/orders/{order_id}"
            params = {"contract": contract}
            response = await self.request(HTTPMethod.GET, endpoint, params=params)

            return rest_futures_to_order(response)
        except OrderNotFoundError as e:
            self.logger.error(e)
            return None
        except Exception as e:
            self.logger.error(f"Failed to get futures order {order_id}: {e}")
            raise ExchangeRestError(500, f"Futures order query failed: {str(e)}")

    async def get_open_orders(self, symbol: Optional[Symbol] = None) -> List[Order]:
        """
        Get open futures orders. If symbol is None, returns empty list (to mirror spot behavior),
        because Gate.io generally requires contract filter for listing.
        """
        try:
            if symbol is None:
                self.logger.debug(
                    "No symbol provided for get_open_orders - returning empty list (API requires contract)"
                )
                return []

            contract = GateioFuturesSymbol.to_pair(symbol)
            endpoint = "/futures/usdt/orders"
            params = {"status": "open", "contract": contract}
            response = await self.request(HTTPMethod.GET, endpoint, params=params)

            if not isinstance(response, list):
                raise ExchangeRestError(500, "Invalid open orders response format")

            open_orders: List[Order] = []
            for item in response:
                open_orders.append(rest_futures_to_order(item))

            self.logger.debug(
                f"Retrieved {len(open_orders)} open futures orders for {symbol}"
            )
            return open_orders

        except Exception as e:
            self.logger.error(f"Failed to get open futures orders for {symbol}: {e}")
            raise ExchangeRestError(500, f"Futures open orders fetch failed: {str(e)}")

    async def modify_order(
        self,
        symbol: Symbol,
        order_id: OrderId,
        qunatity: Optional[float] = None,
        price: Optional[float] = None,
        quote_quantity: Optional[float] = None,
        time_in_force: Optional[TimeInForce] = None,
        stop_price: Optional[float] = None,
    ) -> Order:
        """
        Modify order: Gate.io historically lacks universal amend for every contract.
        Implement as cancel + place new (safe fallback), consistent with Spot implementation approach.
        """
        try:
            # Get existing order to preserve some fields
            existing = await self.get_order(symbol, order_id)

            # Cancel original
            await self.cancel_order(symbol, order_id)

            # Build new order parameters: prefer caller-provided, otherwise reuse existing
            new_amount = qunatity if qunatity is not None else existing.quantity
            new_price = price if price is not None else existing.price
            new_tif = (
                time_in_force if time_in_force is not None else existing.time_in_force
            )

            new_order = await self.place_order(
                symbol=symbol,
                side=existing.side,
                order_type=existing.order_type,
                quantity=new_amount,
                price=new_price,
                quote_quantity=quote_quantity,
                time_in_force=new_tif,
                stop_price=stop_price,
            )

            self.logger.info(
                f"Modified futures order {order_id} -> new order {new_order.order_id}"
            )
            return new_order

        except Exception as e:
            self.logger.error(f"Failed to modify futures order {order_id}: {e}")
            raise ExchangeRestError(500, f"Futures modify order failed: {str(e)}")

    async def get_positions(self) -> List[Position]:
        """
        Get all open positions for futures trading.
        Endpoint: /futures/usdt/positions
        """
        try:
            endpoint = "/futures/usdt/positions"
            response = await self.request(HTTPMethod.GET, endpoint)

            positions: List[Position] = []
            if isinstance(response, list):
                for pos in response:
                    try:
                        # Parse contract identifier
                        contract_name = pos.get("contract", "")
                        if not contract_name:
                            continue

                        symbol = GateioFuturesSymbol.to_symbol(contract_name)
                        size = int(pos.get("size", 0))
                        if size == 0:
                            continue  # Skip empty positions

                        position = Position(
                            symbol=symbol,
                            side=detect_side_from_size(size),
                            size=abs(size),
                            entry_price=float(pos.get("entry_price", 0)),
                            mark_price=float(pos.get("mark_price", 0)),
                            unrealized_pnl=float(pos.get("unrealised_pnl", 0)),
                            realized_pnl=float(pos.get("realised_pnl", 0)),
                            liquidation_price=(
                                float(pos.get("liq_price", 0))
                                if pos.get("liq_price")
                                else None
                            ),
                            margin=(
                                float(pos.get("margin", 0))
                                if pos.get("margin")
                                else None
                            ),
                            timestamp=int(
                                float(pos.get("update_time", time.time())) * 1000
                            ),
                        )
                        positions.append(position)
                    except Exception as e:
                        self.logger.debug(f"Failed to parse position: {e}")
                        continue

            self.logger.debug(f"Retrieved {len(positions)} futures positions")
            return positions

        except Exception as e:
            self.logger.error(f"Failed to get positions: {e}")
            raise ExchangeRestError(500, f"Positions fetch failed: {str(e)}")

    async def get_position(self, symbol: Symbol) -> Optional[Position]:
        """
        Get position for a specific symbol.
        """
        try:
            positions = await self.get_positions()
            for pos in positions:
                if pos.symbol == symbol:
                    return pos
            return None
        except Exception as e:
            self.logger.error(f"Failed to get position for {symbol}: {e}")
            raise

    async def get_trading_fees(self, symbol: Optional[Symbol] = None) -> TradingFee:
        """
        Get account-level futures fees.
        Gate.io may return account-level fees only.
        """
        try:
            response = await self.request(HTTPMethod.GET, "/futures/usdt/fee")
            point_type = response.get("point_type", response.get("tier", None))

            return TradingFee(
                symbol=symbol,
                maker_rate=float(response.get("maker_fee", 0.0)),
                taker_rate=float(response.get("taker_fee", 0.0)),
                futures_maker=float(response.get("futures_maker_fee", 0.0)),
                futures_taker=float(response.get("futures_taker_fee", 0.0)),
                point_type=point_type,
            )

        except Exception as e:
            self.logger.error(f"Failed to fetch futures trading fees: {e}")
            raise ExchangeRestError(500, f"Futures trading fees fetch failed: {str(e)}")

    async def close(self) -> None:
        try:
            self.logger.info("Closed Gate.io private futures REST client")
        except Exception as e:
            self.logger.error(f"Error closing futures private REST client: {e}")

    def __repr__(self) -> str:
        return f"GateioPrivateFuturesRest(base_url={self.base_url})"
