import time
from typing import Dict, List, Optional, Any

from exchanges.interfaces import PrivateFuturesRest
from exchanges.structs.common import (
    Symbol, Order, AssetBalance, TradingFee, Position
)
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs.enums import TimeInForce
from exchanges.structs import OrderType, Side
from infrastructure.networking.http.structs import HTTPMethod
from infrastructure.exceptions.exchange import ExchangeRestError
# Removed BaseExchangeMapper import - using direct utility functions
from config.structs import ExchangeConfig

# Import direct utility functions
from exchanges.integrations.gateio.utils import (
    from_side, from_order_type, format_quantity, format_price,
    from_time_in_force, to_order_status, rest_spot_to_order,
    reverse_lookup_order_type, to_side
)
from exchanges.integrations.gateio.services.futures_symbol_mapper import GateioFuturesSymbol


class GateioPrivateFuturesRest(PrivateFuturesRest):
    def __init__(self, config: ExchangeConfig, logger=None):
        """
        Args:
            config: ExchangeConfig containing credentials & transport config.
            logger: Optional HFT logger injection
        """
        super().__init__(config, is_private=True)
        
        # Initialize HFT logger
        if logger is None:
            from infrastructure.logging import get_exchange_logger
            logger = get_exchange_logger('gateio_futures', 'rest.private')
        self.logger = logger
        self._logger = logger  # For backward compatibility

    def _handle_gateio_exception(self, status_code: int, message: str) -> ExchangeRestError:
        return ExchangeRestError(f"Gate.io futures error {status_code}: {message}")

    # ---------- Account / Balances ----------

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
                total = float(response.get("total", 0))
                available = float(response.get("available", response.get("free", 0)))
                locked = max(0.0, total - available)
                balances.append(AssetBalance(asset=AssetName("USDT"), available=available, locked=locked))
            elif isinstance(response, list):
                # List of assets: try parse entries
                for item in response:
                    try:
                        asset = AssetName(item.get("currency", item.get("asset", "USDT")))
                        free = float(item.get("available", item.get("free", 0)))
                        locked = float(item.get("locked", item.get("frozen", 0)))
                        if free + locked > 0:
                            balances.append(AssetBalance(asset=asset, available=free, locked=locked))
                    except Exception:
                        continue
            else:
                raise ExchangeRestError(500, "Invalid futures accounts response format")

            self.logger.debug(f"Retrieved futures balances: {balances}")
            return balances

        except Exception as e:
            self.logger.error(f"Failed to get futures account balance: {e}")
            raise ExchangeRestError(500, f"Futures balance fetch failed: {str(e)}")

    # async def get_asset_balance(self, asset: AssetName) -> Optional[AssetBalance]:
    #     try:
    #         balances = await self.get_balances()
    #         for b in balances:
    #             if b.asset == asset:
    #                 return b
    #         return AssetBalance(asset=asset, available=0.0, locked=0.0)
    #     except Exception as e:
    #         self.logger.error(f"Failed to get futures asset balance {asset}: {e}")
    #         raise

    # ---------- Order placement / management ----------
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
        quote_quantity: Optional[float] = None,
        time_in_force: Optional[TimeInForce] = None,
        stop_price: Optional[float] = None,
        iceberg_qty: Optional[float] = None,
        new_order_resp_type: Optional[str] = None
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
            payload: Dict[str, Any] = {"contract": contract, "side": from_side(side)}

            # Map order type to exchange values
            payload["type"] = from_order_type(order_type)
            
            # Set time in force based on order type (following Gate.io API requirements)
            # Note: Futures API uses 'tif' field, not 'time_in_force'
            if order_type == OrderType.LIMIT:
                # Limit orders: default to GTC if not specified
                if time_in_force is None:
                    time_in_force = TimeInForce.GTC
                payload["tif"] = from_time_in_force(time_in_force)
            elif order_type == OrderType.MARKET:
                # Market orders: price of 0 with tif set to ioc represents market order
                # Only IOC and FOK are supported for market orders
                if time_in_force is None:
                    time_in_force = TimeInForce.IOC
                
                if time_in_force in [TimeInForce.IOC, TimeInForce.FOK]:
                    payload["tif"] = from_time_in_force(time_in_force)

            # Amount handling: futures commonly use 'size' field for composite quantity
            if order_type == OrderType.MARKET:
                # Market order: size required (composite units), price of 0
                if quantity is None:
                    if quote_quantity is not None:
                        if price:
                            # Use provided price
                            quantity = quote_quantity / price
                        else:
                            # For market orders without price, we need current market price
                            # This is a limitation - market orders should ideally provide quantity directly
                            raise ValueError("Futures market orders with quote_quantity require current price. Use quantity parameter instead.")
                    else:
                        raise ValueError("Futures market orders require either quantity or quote_quantity with price")
                payload["size"] = format_quantity(quantity)
                payload["price"] = "0"  # Market orders use price of 0 with tif=ioc
            else:
                # Limit-like orders: require amount and price
                if quantity is None or price is None:
                    raise ValueError("Futures limit orders require both amount and price")
                payload["size"] = format_quantity(quantity)
                payload["price"] = format_price(price)

            # Optional flags
            if iceberg_qty:
                payload["iceberg"] = format_quantity(iceberg_qty)
            if stop_price:
                payload["stop"] = format_price(stop_price)

            endpoint = "/futures/usdt/orders"
            response = await self.request(HTTPMethod.POST, endpoint, data=payload)

            # Try to transform using shared mapper; if mapper can't, fall back to manual minimal construct
            try:
                order = rest_spot_to_order(response)
                self.logger.info(f"Placed futures order {order.order_id}")
                return order
            except Exception:
                # Minimal best-effort mapping
                return Order(
                    order_id=OrderId(str(response.get("id", response.get("order_id", "")))),
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    quantity=float(response.get("size", quantity or 0)),
                    client_order_id=response.get("client_oid"),
                    price=float(response.get("price")) if response.get("price") else None,
                    filled_quantity=float(response.get("filled_size", response.get("filled", 0))),
                    remaining_quantity=float(response.get("left", 0)),
                    status=to_order_status(response.get("status", "open")),
                    timestamp=int(float(response.get("create_time_ms", int(time.time() * 1000))))
                )

        except Exception as e:
            self.logger.error(f"Failed to place futures order: {e}")
            raise ExchangeRestError(500, f"Futures order placement failed: {str(e)}")

    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """
        Cancel single futures order. DELETE /futures/usdt/orders/{id}?contract=...
        """
        try:
            contract = GateioFuturesSymbol.to_pair(symbol)
            endpoint = f"/futures/usdt/orders/{order_id}"
            params = {"contract": contract}
            response = await self.request(HTTPMethod.DELETE, endpoint, params=params)

            try:
                return rest_spot_to_order(response)
            except Exception:
                # Best-effort mapping
                return Order(
                    order_id=order_id,
                    symbol=symbol,
                    side=to_side(response.get("side", "buy")),
                    order_type=reverse_lookup_order_type(response.get("type", "limit")),
                    quantity=float(response.get("size", 0)),
                    filled_quantity=float(response.get("filled_size", 0)),
                    remaining_quantity=float(response.get("left", 0)),
                    status=to_order_status(response.get("status", "cancelled")),
                    timestamp=int(float(response.get("create_time_ms", int(time.time() * 1000))))
                )

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
                    try:
                        cancelled.append(rest_spot_to_order(item))
                    except Exception:
                        # best-effort minimal mapping
                        cancelled.append(Order(
                            order_id=OrderId(str(item.get("id", ""))),
                            symbol=symbol,
                            side=to_side(item.get("side", "buy")),
                            order_type=reverse_lookup_order_type(item.get("type", "limit")),
                            quantity=float(item.get("size", 0)),
                            filled_quantity=float(item.get("filled_size", 0)),
                            remaining_quantity=float(item.get("left", 0)),
                            status=to_order_status(item.get("status", "cancelled")),
                            timestamp=int(float(item.get("create_time_ms", int(time.time() * 1000))))
                        ))
            else:
                # single-object response
                try:
                    cancelled.append(rest_spot_to_order(response))
                except Exception:
                    cancelled.append(Order(
                        order_id=OrderId(str(response.get("id", ""))),
                        symbol=symbol,
                        side=to_side(response.get("side", "buy")),
                        order_type=reverse_lookup_order_type(response.get("type", "limit")),
                        quantity=float(response.get("size", 0)),
                        filled_quantity=float(response.get("filled_size", 0)),
                        remaining_quantity=float(response.get("left", 0)),
                        status=to_order_status(response.get("status", "cancelled")),
                        timestamp=int(float(response.get("create_time_ms", int(time.time() * 1000))))
                    ))

            self.logger.info(f"Cancelled {len(cancelled)} futures orders for {symbol}")
            return cancelled

        except Exception as e:
            self.logger.error(f"Failed to cancel all futures orders for {symbol}: {e}")
            raise ExchangeRestError(500, f"Futures mass cancellation failed: {str(e)}")

    async def get_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """
        Query single futures order: GET /futures/usdt/orders/{id}?contract=...
        """
        try:
            contract = GateioFuturesSymbol.to_pair(symbol)
            endpoint = f"/futures/usdt/orders/{order_id}"
            params = {"contract": contract}
            response = await self.request(HTTPMethod.GET, endpoint, params=params)

            try:
                return rest_spot_to_order(response)
            except Exception:
                return Order(
                    order_id=order_id,
                    symbol=symbol,
                    side=to_side(response.get("side", "buy")),
                    order_type=reverse_lookup_order_type(response.get("type", "limit")),
                    quantity=float(response.get("size", 0)),
                    filled_quantity=float(response.get("filled_size", 0)),
                    remaining_quantity=float(response.get("left", 0)),
                    status=to_order_status(response.get("status", "unknown")),
                    timestamp=int(float(response.get("create_time_ms", int(time.time() * 1000))))
                )

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
                self.logger.debug("No symbol provided for get_open_orders - returning empty list (API requires contract)")
                return []

            contract = GateioFuturesSymbol.to_pair(symbol)
            endpoint = "/futures/usdt/orders"
            params = {"status": "open", "contract": contract}
            response = await self.request(HTTPMethod.GET, endpoint, params=params)

            if not isinstance(response, list):
                raise ExchangeRestError(500, "Invalid open orders response format")

            open_orders: List[Order] = []
            for item in response:
                try:
                    open_orders.append(rest_spot_to_order(item))
                except Exception:
                    open_orders.append(Order(
                        order_id=OrderId(str(item.get("id", ""))),
                        symbol=symbol,
                        side=to_side(item.get("side", "buy")),
                        order_type=reverse_lookup_order_type(item.get("type", "limit")),
                        quantity=float(item.get("size", 0)),
                        filled_quantity=float(item.get("filled_size", 0)),
                        remaining_quantity=float(item.get("left", 0)),
                        status=to_order_status(item.get("status", "open")),
                        timestamp=int(float(item.get("create_time_ms", int(time.time() * 1000))))
                    ))

            self.logger.debug(f"Retrieved {len(open_orders)} open futures orders for {symbol}")
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
        stop_price: Optional[float] = None
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
            new_tif = time_in_force if time_in_force is not None else existing.time_in_force

            new_order = await self.place_order(
                symbol=symbol,
                side=existing.side,
                order_type=existing.order_type,
                quantity=new_amount,
                price=new_price,
                quote_quantity=quote_quantity,
                time_in_force=new_tif,
                stop_price=stop_price
            )

            self.logger.info(f"Modified futures order {order_id} -> new order {new_order.order_id}")
            return new_order

        except Exception as e:
            self.logger.error(f"Failed to modify futures order {order_id}: {e}")
            raise ExchangeRestError(500, f"Futures modify order failed: {str(e)}")

    # ---------- Position Management ----------
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

                        # Convert to unified symbol
                        symbol = GateioFuturesSymbol.to_symbol(contract_name)

                        # Parse position size (positive for long, negative for short)
                        size_val = float(pos.get("size", 0))
                        if size_val == 0:
                            continue  # Skip empty positions

                        side = Side.LONG if size_val > 0 else Side.SHORT

                        position = Position(
                            symbol=symbol,
                            side=side,
                            size=abs(size_val),
                            entry_price=float(pos.get("entry_price", 0)),
                            mark_price=float(pos.get("mark_price", 0)),
                            unrealized_pnl=float(pos.get("unrealized_pnl", 0)),
                            realized_pnl=float(pos.get("realized_pnl", 0)),
                            liquidation_price=float(pos.get("liq_price", 0)) if pos.get("liq_price") else None,
                            margin=float(pos.get("margin", 0)) if pos.get("margin") else None,
                            timestamp=int(float(pos.get("update_time", time.time())) * 1000)
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

    # ---------- Fees ----------
    async def get_trading_fees(self, symbol: Optional[Symbol] = None) -> TradingFee:
        """
        Get account-level futures fees. Endpoint (typical): /futures/usdt/fee or /spot/fee fallback.
        Gate.io may return account-level fees only.
        """
        try:
            # Try futures fee endpoint first
            try:
                response = await self.request(HTTPMethod.GET, "/futures/usdt/fee")
            except Exception:
                response = await self.request(HTTPMethod.GET, "/spot/fee")

            if not isinstance(response, dict):
                raise ExchangeRestError(500, "Invalid fee response format")

            maker_rate = float(response.get("maker_fee", response.get("futures_maker", 0.0)))
            taker_rate = float(response.get("taker_fee", response.get("futures_taker", 0.0)))
            point_type = response.get("point_type", response.get("tier", None))

            return TradingFee(
                maker_rate=maker_rate,
                taker_rate=taker_rate,
                futures_maker=maker_rate,
                futures_taker=taker_rate,
                point_type=point_type,
                symbol=symbol
            )

        except Exception as e:
            self.logger.error(f"Failed to fetch futures trading fees: {e}")
            raise ExchangeRestError(500, f"Futures trading fees fetch failed: {str(e)}")

    # mock
    async def get_assets_info(self, **kwargs):
        return {}

    # ---------- Lifecycle ----------
    async def close(self) -> None:
        try:
            self.logger.info("Closed Gate.io private futures REST client")
        except Exception as e:
            self.logger.error(f"Error closing futures private REST client: {e}")

    def __repr__(self) -> str:
        return f"GateioPrivateFuturesRest(base_url={self.base_url})"
