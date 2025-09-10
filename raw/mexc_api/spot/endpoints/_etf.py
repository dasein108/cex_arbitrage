"""Defines the _Etf class."""

from typing import Any, Coroutine

from exchanges.common import Method
from exchanges.mexc_api.api import Api


class _Etf:
    """Defines all etf endpoints."""

    def __init__(self, api: Api) -> None:
        self.api = api

    async def info(self, etf_symbol: str) -> Coroutine[Any, Any, dict]:
        """Returns etf info."""
        params = {"symbol": etf_symbol.upper()}
        return await self.api.send_request(Method.GET, "/api/v3/etf/info", params)
