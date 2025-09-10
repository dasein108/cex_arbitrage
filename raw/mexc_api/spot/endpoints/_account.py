"""Defines the _Account class."""

from typing import Any, Coroutine

from exchanges.common import Method, OrderType, Side
from exchanges.mexc_api.api import Api


class _Account:
    """Defines all Account endpoints."""

    def __init__(self, api: Api) -> None:
        self.api = api

    async def test_new_order(
        self,
        symbol: str,
        side: Side,
        order_type: OrderType,
        quantity: str | None = None,
        quote_order_quantity: str | None = None,
        price: str | None = None,
        client_order_id: str | None = None,
    ) -> Coroutine[Any, Any, dict]:
        """Creates a test order."""
        params = {
            "symbol": symbol.upper(),
            "side": side.value,
            "quantity": quantity,
            "price": price,
            "type": order_type.value,
            "quoteOrderQty": quote_order_quantity,
            "newClientOrderId": client_order_id,
        }
        return await self.api.send_request(Method.POST, "/api/v3/order/test", params, True)

    async def new_order(
        self,
        symbol: str,
        side: Side,
        order_type: OrderType,
        quantity: str | None = None,
        quote_order_quantity: str | None = None,
        price: str | None = None,
        client_order_id: str | None = None,
    ) -> Coroutine[Any, Any, dict]:
        """Creates a new order."""
        params = {
            "symbol": symbol.upper(),
            "side": side.value,
            "quantity": quantity,
            "price": price,
            "type": order_type.value,
            "quoteOrderQty": quote_order_quantity,
            "newClientOrderId": client_order_id,
        }
        return await self.api.send_request(Method.POST, "/api/v3/order", params, True)

    def batch_order(self) -> dict:
        """Creates multiple orders."""
        raise NotImplementedError

    async def cancel_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> Coroutine[Any, Any, dict]:
        """Cancels an order based on the order id or client order id."""
        params = {
            "symbol": symbol.upper(),
            "orderId": order_id,
            "origClientOrderId": client_order_id,
        }

        return await self.api.send_request(Method.DELETE, "/api/v3/order", params, True)

    async def cancel_open_orders(self, symbol: str) -> Coroutine[Any, Any, list]:
        """Cancels all open orders."""
        params = {
            "symbol": symbol.upper(),
        }
        return await self.api.send_request(Method.DELETE, "/api/v3/openOrders", params, True)

    async def get_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> Coroutine[Any, Any, dict]:
        """Returns an order for a symbol based on the order id or client order id."""
        params = {
            "symbol": symbol.upper(),
            "orderId": order_id,
            "origClientOrderId": client_order_id,
        }
        return await self.api.send_request(Method.GET, "/api/v3/order", params, True)

    async def get_open_orders(self, symbol: str) -> Coroutine[Any, Any, list]:
        """Returns all open orders for a symbol."""
        params = {
            "symbol": symbol.upper(),
        }
        return await self.api.send_request(Method.GET, "/api/v3/openOrders", params, True)

    async def get_orders(
        self,
        symbol: str,
        start_ms: int | None = None,
        end_ms: int | None = None,
        timestamp: int | None = None,
        limit: int | None = None,
    ) -> Coroutine[Any, Any, list]:
        """Returns all orders for a symbol within the optional start and end timestamps."""
        params = {
            "symbol": symbol.upper(),
            "limit": limit,
            "startTime": start_ms,
            "timestamp": timestamp,
            "endTime": end_ms,
        }
        return await self.api.send_request(Method.GET, "/api/v3/allOrders", params, True)

    async def get_account_info(self) -> Coroutine[Any, Any, dict]:
        """Returns the account info."""
        return await self.api.send_request(Method.GET, "/api/v3/account", {}, True)

    async def get_trades(
        self,
        symbol: str,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int | None = None,
    ) -> Coroutine[Any, Any, list]:
        """Returns all trades for a symbol within the optional start and end timestamps."""
        params = {
            "symbol": symbol.upper(),
            "limit": limit,
            "startTime": start_ms,
            "endTime": end_ms,
        }
        return await self.api.send_request(Method.GET, "/api/v3/myTrades", params, True)

    async def enable_mx_deduct(self, is_enabled: bool) -> Coroutine[Any, Any, dict]:
        """Enables mx deduct."""
        params = dict(mxDeductEnable=is_enabled)
        return await self.api.send_request(Method.POST, "/api/v3/mxDeduct/enable", params, True)

    async def get_mx_deduct(self) -> Coroutine[Any, Any, dict]:
        """Returns the mx deduct status."""
        return await self.api.send_request(Method.GET, "/api/v3/mxDeduct/enable", {}, True)

    async def create_listen_key(self) -> Coroutine[Any, Any, str]:
        """Returns a listen key"""
        response = await self.api.send_request(Method.POST, "/api/v3/userDataStream", {}, True)
        return response["listenKey"]

    async def get_all_listen_keys(self) -> Coroutine[Any, Any, dict]:
        """Returns a listen key."""
        return await self.api.send_request(Method.GET, "/api/v3/userDataStream", {}, True)

    async def keep_alive_listen_key(self, listen_key: str) -> Coroutine[Any, Any, None]:
        """Keeps the listen key alive."""
        params = {"listenKey": listen_key}
        return await self.api.send_request(Method.PUT, "/api/v3/userDataStream", params, True)

    async def delete_listen_key(self, listen_key: str) -> Coroutine[Any, Any, None]:
        """deletes a listen key."""
        params = {"listenKey": listen_key}
        return await self.api.send_request(Method.DELETE, "/api/v3/userDataStream", params, True)
