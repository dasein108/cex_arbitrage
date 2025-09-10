"""Defines the _Market class."""

from typing import Any, Coroutine

from exchanges.common import Interval, Method
from exchanges.mexc_api.api import Api


class _Market:
    """Defines all Market endpoints."""

    def __init__(self, api: Api) -> None:
        self.api = api

    async def test(self) -> Coroutine[Any, Any, None]:
        """Tests connectivity to the Rest API."""
        return await self.api.send_request(Method.GET, "/api/v3/ping", {})

    async def server_time(self) -> Coroutine[Any, Any, int]:
        """Returns the server time."""
        response = await self.api.send_request(Method.GET, "/api/v3/time", {})
        return response["serverTime"]

    async def default_symbols(self) -> Coroutine[Any, Any, list[str]]:
        """Returns all symbols."""
        response = await self.api.send_request(Method.GET, "/api/v3/defaultSymbols", {})
        return response["data"]

    async def exchange_info(
        self, symbol: str | None = None, symbols: list[str] | None = None
    ) -> Coroutine[Any, Any, dict]:
        """
        Returns the rules and symbol info of the given symbol(s).
        All symbols will be returned when no parameter is given.
        """

        if symbol:
            symbol.upper()
        elif symbols:
            symbols = [symbol.upper() for symbol in symbols]

        params = {"symbol": symbol, "symbols": symbols}
        return await self.api.send_request(Method.GET, "/api/v3/exchangeInfo", params)

    async def order_book(self, symbol: str, limit: int | None = None) -> Coroutine[Any, Any, dict]:
        """Returns the bids and asks of symbol."""
        params = {"symbol": symbol.upper(), "limit": limit}
        return await self.api.send_request(Method.GET, "/api/v3/depth", params)

    async def trades(
        self, symbol: str, limit: int | None = None, end_timestamp: int | None = None
    ) -> Coroutine[Any, Any, list]:
        """Returns the recent trades of symbol."""
        params = {"symbol": symbol.upper(), "limit": limit, "endTime": end_timestamp}
        return await self.api.send_request(Method.GET, "/api/v3/trades", params)

    async def agg_trades(
        self,
        symbol: str,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int | None = None,
    ) -> Coroutine[Any, Any, list]:
        """Returns the aggregate trades of symbol."""
        params = {
            "symbol": symbol.upper(),
            "limit": limit,
            "startTime": start_ms,
            "endTime": end_ms,
        }
        return await self.api.send_request(Method.GET, "/api/v3/aggTrades", params)

    async def klines(
        self,
        symbol: str,
        interval: Interval,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int | None = None,
    ) -> Coroutine[Any, Any, list]:
        """
        Returns the klines of a symbol on the given interval
        between the optional start and end timestamps.
        """
        params = {
            "symbol": symbol.upper(),
            "interval": interval.value,
            "limit": limit,
            "startTime": start_ms,
            "endTime": end_ms,
        }
        return await self.api.send_request(Method.GET, "/api/v3/klines", params, True)

    async def avg_price(self, symbol: str) -> Coroutine[Any, Any, dict]:
        """Returns the average price of a symbol."""
        params = {
            "symbol": symbol.upper(),
        }
        return await self.api.send_request(Method.GET, "/api/v3/avgPrice", params)

    async def ticker_24h(self, symbol: str | None = None) -> Coroutine[Any, Any, list]:
        """
        Returns ticker data from the last 24 hours.
        Data for all symbols will be sent if symbol was not given.
        """
        if symbol:
            symbol.upper()

        params = {
            "symbol": symbol,
        }
        response = await self.api.send_request(Method.GET, "/api/v3/ticker/24hr", params)
        return [response] if isinstance(response, dict) else response

    async def ticker_price(self, symbol: str | None = None) -> Coroutine[Any, Any, list]:
        """
        Returns the ticker price of a symbol.
        Prices of all symbols will be send if symbol was not given.
        """
        if symbol:
            symbol.upper()

        params = {
            "symbol": symbol,
        }
        response = await self.api.send_request(Method.GET, "/api/v3/ticker/price", params)
        return [response] if isinstance(response, dict) else response

    async def ticker_book_price(self, symbol: str | None = None) -> Coroutine[Any, Any, list]:
        """
        Returns the best price/qty on the order book for a symbol.
        Data for all symbols will be sent if symbol was not given.
        """
        if symbol:
            symbol.upper()

        params = {
            "symbol": symbol,
        }
        response = await self.api.send_request(Method.GET, "/api/v3/ticker/bookTicker", params)
        return [response] if isinstance(response, dict) else response
