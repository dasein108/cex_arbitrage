import asyncio
import logging
import traceback
from typing import Any, Callable, Coroutine, Dict, List, Optional

import orjson
from websockets import connect

from config import MEXC_KEY, MEXC_SECRET
from core import CoreBase
from exchanges.common import Action
from exchanges.common.interfaces.base_ws import WebSocketBase
from exchanges.mexc_api.spot import Spot

WARMUP_TIME = 15

STREAM_URL = f"wss://wbs-api.mexc.com/ws"


class MexcWebSocketBase(WebSocketBase):
    def __init__(
        self,
        name: str,
        on_message: Callable[[Dict[str, Any]], Coroutine],
        timeout: float = 0.0,
        on_connected: Optional[Callable[[], Coroutine]] = None,
        on_restart: Optional[Callable[[], Coroutine]] = None,
        streams: List[str] = [],
    ):
        super().__init__(name, on_message, timeout, on_connected, on_restart, streams)
        # if self.timeout:
        #     self.loop.create_task(self._manage_timeout())

    async def _connect(self):
        while not self._is_stopped:
            try:
                if self.is_connected:
                    logging.warning(f"WS {self.name} Closing")
                    await self.ws.close()

                logging.warning(f"WS {self.name} Connecting")

                listen_key = await Spot(MEXC_KEY, MEXC_SECRET).account.create_listen_key()

                url = f"{STREAM_URL}?listenKey={listen_key}"

                logging.info(f"Connecting to WS:{self.name}")

                self.ws = await connect(
                    url,
                    ping_interval=55.0,
                    max_queue=5000,
                )

                logging.warning(f"WS {self.name} Connected")
                break
            except TimeoutError:
                logging.error(f"WS {self.name} timeout.")
            except Exception as ex:
                logging.error(f"WS {self.name} exception: {ex}")
                traceback.print_exc()
                await asyncio.sleep(1)

    async def _subscribe(self, streams: List[str], action: Action = Action.SUBSCRIBE):
        message = {"method": action.value, "params": streams}
        await self.ws.send(orjson.dumps(message).decode("utf-8"))

    # async def _manage_timeout(self):
    #     while not self._is_stopped:
    #         await asyncio.sleep(self.timeout)
    #         if not self.is_connected:
    #             return
    # now_ = time.time()
    # if now_ - self.time > self.timeout:
    #     try:
    #         self.logger.warning(
    #             f"WS {self.name}  {now_} - {self.time}({now_ - self.time}) "
    #         )
    #         # self.time = now_
    #         await self.restart_ws()
    #     except:
    #         traceback.print_exc()
