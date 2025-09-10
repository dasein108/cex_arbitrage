import asyncio
import logging
import traceback
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional

import orjson
import websockets
from google.protobuf import json_format
from websockets import connect
from websockets.exceptions import ConnectionClosedError

from core import CoreBase
from exchanges.common import Action
from exchanges.mexc_api.websocket.pb import PushDataV3ApiWrapper_pb2


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

    @property
    def is_connected(self):
        # Check if websocket connection is open
        return self.ws is not None and self.ws.state == websockets.protocol.State.OPEN

    async def stop(self):
        await self.subscribe(list(self.streams), Action.UNSUBSCRIBE)
        self._is_stopped = True
        if self.ws is not None:
            await self.ws.close()

    async def _read_socket(self):
        USE_PROTO = True
        try:
            while not self._is_stopped:
                message = await self.ws.recv()
                try:
                    if isinstance(message, str):
                        for line in str(message).splitlines():
                            await self.on_message(orjson.loads(line))
                    else:
                        result = PushDataV3ApiWrapper_pb2.PushDataV3ApiWrapper()
                        result.ParseFromString(message)
                        data = json_format.MessageToDict(result, preserving_proto_field_name=True)

                        await self.on_message(data)

                except Exception as e:
                    logging.error(e)
                    traceback.print_exc()
        except ConnectionClosedError as e:
            sleep_time = 3
            logging.info(f"WS {self.name} Connection Error: {e}. Sleep {sleep_time}...")
            await asyncio.sleep(sleep_time)
        except Exception as e:
            logging.info(f"WS {self.name} Connection Lost at {datetime.utcnow()}")
            traceback.print_exc()
            # logging.error(add_traceback(e))

    async def _send_message(self, msg: Dict[str, Any]):
        await self.ws.send(orjson.dumps(msg).decode("utf-8"))

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
        if self.ws is not None:
            await self.ws.close()

    async def _subscribe(self, streams: List[str], action: Action = Action.SUBSCRIBE):
        pass

    async def _connect(self):
        pass

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
