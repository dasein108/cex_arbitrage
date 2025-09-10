import asyncio
import logging
import time
import traceback
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

import orjson
import websockets
from websockets import connect

from config import MEXC_KEY, MEXC_SECRET
from core import CoreBase
from exchanges.mexc_api.common import Action, StreamInterval
from exchanges.mexc_api.spot import Spot

WARMUP_TIME = 15

STREAM_URL = f"wss://wbs.mexc.com/ws"


async def connect_private():
    listen_key = await Spot(MEXC_KEY, MEXC_SECRET).account.create_listen_key()

    logging.info(f"Connecting to {STREAM_URL} private")
    conn = await connect(
        f"{STREAM_URL}?listenKey={listen_key}",
        ping_interval=55.0,
        loop=CoreBase.get_loop(),
        max_queue=5000,
    )
    return conn


async def connect_public():
    logging.info(f"Connecting to {STREAM_URL} public")
    conn = await connect(
        STREAM_URL,
        ping_interval=55.0,
        loop=CoreBase.get_loop(),
        max_queue=5000,
    )
    return conn


# class WsMode(Enum):
#     PUBLIC = "public"
#     PRIVATE = "private"


class WebSocketBase:
    def __init__(
        self,
        name: str,
        on_message: Callable[[Dict[str, Any]], Coroutine],
        timeout: float = 0.0,
        on_connected: Optional[Callable[[], Coroutine]] = None,
        on_restart: Optional[Callable[[], Coroutine]] = None,
        streams: List[str] = [],
    ):
        self.on_message = on_message
        self.on_restart = on_restart
        self.name = name
        self.ws = None
        self.timeout = timeout
        # self.time = float(time.time() + WARMUP_TIME)
        self.on_connected = on_connected
        self.loop = CoreBase.get_loop()
        self.streams: set[str] = set(streams)
        self._is_stopped = False

        self.loop.create_task(self.run())
        if self.timeout:
            self.loop.create_task(self.manage_timeout())

    @property
    def is_connected(self):
        # return self.ws is not None
        return self.ws and self.ws.open

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

    async def stop(self):
        await self.subscribe(list(self.streams), Action.UNSUBSCRIBE)
        self._is_stopped = True
        await self.ws.close()

    async def _read_socket(self):
        try:
            while not self._is_stopped:
                message = await self.ws.recv()
                try:
                    for line in str(message).splitlines():
                        await self.on_message(orjson.loads(line))
                except Exception as e:
                    logging.error(e)
                    traceback.print_exc()
        except websockets.ConnectionClosedError as e:
            sleep_time = 3
            logging.info(f"WS {self.name} Connection Error: {e}. Sleep {sleep_time}...")
            await asyncio.sleep(sleep_time)
        except Exception as e:
            logging.info(f"WS {self.name} Connection Lost at {datetime.utcnow()}")
            traceback.print_exc()
            # logging.error(add_traceback(e))

    async def _send_message(self, msg: Dict[str, Any]):
        await self.ws.send(orjson.dumps(msg).decode("utf-8"))

    async def subscribe(self, streams: List[str], action: Action = Action.SUBSCRIBE) -> None:
        """Subscribes to or unsubscribes from stream."""
        for stream in streams:
            if action == Action.UNSUBSCRIBE:
                self.streams.remove(stream)
            else:
                self.streams.add(stream)

        if self.is_connected:
            logging.info(f"WS {self.name} Subscribing to {streams}")
            await self._subscribe(streams, action)

    async def _subscribe(self, streams: List[str], action: Action = Action.SUBSCRIBE):
        message = {"method": action.value, "params": streams}
        await self.ws.send(orjson.dumps(message).decode("utf-8"))

    async def run(self):
        while not self._is_stopped:
            await self._connect()

            if len(self.streams) > 0:
                await self._subscribe(list(self.streams), Action.SUBSCRIBE)

            self.on_connected and await self.on_connected()

            await self._read_socket()
            if self.on_restart:
                await self.on_restart()

    async def restart(self):
        await self.ws.close()

    async def manage_timeout(self):
        while not self._is_stopped:
            await asyncio.sleep(self.timeout)
            if not self.is_connected:
                return
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
