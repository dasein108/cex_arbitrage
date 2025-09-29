
from exchanges.interfaces import BaseWebsocketInterface
from config.structs import ExchangeConfig
from websockets import connect
import time
import asyncio

from utils import safe_cancel_task


class GateioBaseWebsocket(BaseWebsocketInterface):
    """Gate.io private WebSocket client using dependency injection pattern."""

    async def _create_websocket(self):
        await self._stop_heartbeat()
        websocket = await connect(
            self.config.websocket_url,
            # ping_interval=config.ping_interval,
            # ping_timeout=config.ping_timeout,
            max_queue=self.config.websocket.max_queue_size,
            compression=None,  # Disable compression for CPU optimization in HFT
            max_size=self.config.websocket.max_message_size,
            write_limit=2 ** 20,  # 1MB write buffer
        )

        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        return websocket

    async def _auth(self) -> bool:
        # Gate.io private WebSocket authentication logic
        if not self.is_private:
            return True


    def __init__(
        self,
        config: ExchangeConfig,
        *args,
        **kwargs
    ):
        if not config.websocket:
            raise ValueError("Gate.io exchange configuration missing WebSocket settings")
        
        # Initialize via composite class with handler object
        super().__init__(
            config=config,
            *args,
            **kwargs
        )

        self._heartbeat_task: asyncio.Task | None = None

        self.logger.info("Gate.io private WebSocket initialized with handler objects")

    async def _heartbeat_loop(self) -> None:
        """Strategy-managed heartbeat loop."""
        try:
            while True:
                if not self._ws_manager or not self._ws_manager.is_connected():
                    self.logger.debug("WebSocket not connected, skipping heartbeat ping")
                    continue
                await asyncio.sleep(self.config.websocket.ping_interval)

                import msgspec

                ping_msg = {
                    "time": int(time.time()),
                    "channel": "spot.ping",
                    "event": "ping"
                }

                await self._ws_manager.send_message(ping_msg)
                self.logger.debug("sending ping message", ping_msg=ping_msg)
        except asyncio.CancelledError:
            self.logger.debug("Strategy heartbeat loop cancelled")
        except Exception as e:
            self.logger.error("Strategy heartbeat loop error",
                              error_type=type(e).__name__,
                              error_message=str(e))

            # Track heartbeat loop error metrics
            self.logger.metric("ws_heartbeat_loop_errors", 1,
                               tags={"exchange": "ws"})

    async def _stop_heartbeat(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task = safe_cancel_task(self._heartbeat_task)

    async def close(self) -> None:
        await self._stop_heartbeat()
        await super().close()
