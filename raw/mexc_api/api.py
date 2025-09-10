import asyncio
import hashlib
import hmac
import logging
import time
import traceback
from typing import Any, Optional

import orjson

from core import CoreBase
from exchanges.common.enums import Method
from exchanges.common.exceptions import ExchangeAPIError, RateLimitError


def get_timestamp() -> int:
    """Returns the current timestamp in milliseconds."""
    return round(time.time() * 1000)


class RateLimiter:
    def __init__(self, max_calls: int, interval: float):
        self._max_calls = max_calls
        self._interval = interval
        self._semaphore = asyncio.Semaphore(max_calls)
        self._call_count = 0  # Track calls within the interval
        self._last_reset = time.monotonic()  # Track time for interval reset

    async def acquire(self):
        """Acquire a slot if within the rate limit, else wait for the interval reset."""
        current_time = time.monotonic()

        # Check if the interval has passed to reset
        if current_time - self._last_reset >= self._interval:
            self._last_reset = current_time  # Update the last reset time
            self._call_count = 0  # Reset the call count
            # Release any excess holds on the semaphore, back to max_calls
            self._semaphore = asyncio.Semaphore(self._max_calls)
            # print(f"reset call count: {self._call_count} {current_time}")

        # Check if within allowed calls for the interval
        if self._call_count < self._max_calls:
            await self._semaphore.acquire()
            self._call_count += 1
            # print(f"call count: {self._call_count}")
        else:
            # Wait until the interval resets
            await asyncio.sleep(self._interval - (current_time - self._last_reset))
            await self.acquire()  # Reattempt acquisition after waiting

    def release(self):
        """Release a slot, allowing another task to proceed."""
        self._semaphore.release()


class Api:
    """Defines a core API class."""

    rate_limiter = RateLimiter(max_calls=20, interval=1)

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://api.mexc.com",
        recv_window: int = 15000,
        timeout: int = 5,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.recv_window = recv_window
        self.loop = loop or asyncio.get_event_loop()  # Injected loop or default loop

    def get_query(self, params: dict) -> str:
        """Returns a query string of all given parameters."""
        return "&".join(f"{key}={value}" for key, value in params.items())

    def get_signature(self, query: str) -> str:
        """Returns the signature based on the API secret and the query."""
        return hmac.new(self.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()

    def remove_none_params(self, params: dict) -> dict:
        """Returns a dict without empty parameter values."""
        return {k: v for k, v in params.items() if v is not None}

    async def send_request(self, method: Method, endpoint: str, params: dict, sign: bool = False) -> Any:
        """
        Sends a request with the given method to the given endpoint.
        RecvWindow, timestamp, and signature are added to the parameters.

        Raises a MexcAPIError if the response has an error.
        Returns the JSON-encoded content of the response.
        """
        content_ = ""
        try:
            await self.rate_limiter.acquire()

            params = self.remove_none_params(params)

            if sign:
                params["recvWindow"] = self.recv_window
                params["timestamp"] = get_timestamp()
                params["signature"] = self.get_signature(self.get_query(params))

            url = self.base_url + endpoint
            resp = await CoreBase.get_request().request(url, method, params=params)
            content_ = await resp.content.read()
            try:
                content = orjson.loads(content_)
            except orjson.JSONDecodeError:
                content = content_.decode()
                raise ExchangeAPIError(resp.status, content)

            if resp.status != 200:
                if content.get("code") in [429, 418]:
                    # get response headers
                    retry_after = resp.headers.get("Retry-After", None)
                    logging.error(
                        f"Rate limit error: {content} r/a: {resp.headers.get('Retry-After', '-')} "
                        f"{method} {endpoint}"
                    )
                    time.sleep(1)
                    raise RateLimitError(resp.status, content.get("msg"), content.get("code", None), retry_after)
                logging.error(f"API error params: {params}")
                code = content.get("code", None)
                raise ExchangeAPIError(resp.status, content.get("msg"), code)
                # raise MexcAPIError(resp.status, content.get("msg"), content.get("code", None))

            return content
        except Exception as e:
            raise e
        finally:
            self.rate_limiter.release()
