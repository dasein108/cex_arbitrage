import asyncio
import traceback
from typing import Callable, Coroutine, Dict, Optional, Any, List

import logging

from exchanges.base.base_ws import WebSocketBase
from config import GATEIO_KEY, GATEIO_SECRET
import websockets

from core import CoreBase
from exchanges.common.enums import Action
import hashlib
import hmac
import time

WARMUP_TIME = 15

GATEIO_WS_URL = f"wss://api.gateio.ws/ws/v4/"


class GateioWebSocketBase(WebSocketBase):
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


    async def _request(self, channel, event=None, payload=None, auth_required=True):
        current_time = int(time.time())
        data = {
            "time": current_time,
            "channel": channel,
            "event": event,
            "payload": payload,
        }
        if auth_required:
            message = 'channel=%s&event=%s&time=%d' % (channel, event, current_time)
            data['auth'] = {
                "method": "api_key",
                "KEY": GATEIO_KEY,
                "SIGN": self.get_sign(message),
            }

        await self._send_message(data)

    def get_sign(self, message):
        h = hmac.new(GATEIO_SECRET.encode("utf8"), message.encode("utf8"), hashlib.sha512)
        return h.hexdigest()

    async def _connect(self):
        while not self._is_stopped:
            try:
                if self.is_connected:
                    logging.warning(f"WS {self.name} Closing")
                    await self.ws.close()

                logging.warning(f"WS {self.name} Connecting")

                logging.info(f"Connecting to WS:{self.name}")

                self.ws = await websockets.connect(
                    GATEIO_WS_URL,
                    ping_interval=5.0,
                    loop=CoreBase.get_loop(),
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
        for s in streams:
            event = "subscribe" if action == Action.SUBSCRIBE else "unsubscribe"
            payload = s.split("@")
            channel = payload.pop(0)
            await self._request(channel,event,payload)

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
