import asyncio
import logging
from typing import Optional, Any

from cex.mexc.rest import MexcPrivateSpotRest
from core.cex.websocket import ConnectionStrategy, ConnectionContext
from core.config.structs import ExchangeConfig


class MexcPrivateConnectionStrategy(ConnectionStrategy):
    """MEXC private WebSocket connection strategy with listen key management."""

    def __init__(self, config: ExchangeConfig, rest_client: Optional[MexcPrivateSpotRest] = None):
        """
        Initialize MEXC private connection strategy.

        Args:
            config: Exchange configuration
            rest_client: MexcPrivateSpotRest instance for listen key management
        """
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Listen key management
        self.listen_key: Optional[str] = None
        self.keep_alive_task: Optional[asyncio.Task] = None
        self.keep_alive_interval = 1800  # 30 minutes in seconds

        # Use injected REST client or create new one if not provided
        if rest_client is not None:
            self.rest_client = rest_client
            self.logger.debug("Using injected REST client for listen key management")
        else:
            self.rest_client = MexcPrivateSpotRest(config)
            self.logger.debug("Created new REST client for listen key management")

    async def create_connection_context(self) -> ConnectionContext:
        """Create MEXC private WebSocket connection context with listen key."""
        try:
            # Create listen key via REST API
            self.listen_key = await self.rest_client.create_listen_key()
            self.logger.info(f"Created listen key: {self.listen_key[:8]}...")

            # Build WebSocket URL with listen key
            base_url = "wss://wbs-api.mexc.com/ws"
            ws_url = f"{base_url}?listenKey={self.listen_key}"

            return ConnectionContext(
                url=ws_url,
                headers={},
                auth_required=True,  # Listen key provides authentication
                auth_params={
                    'listen_key': self.listen_key
                },
                ping_interval=30,
                ping_timeout=10,
                max_reconnect_attempts=10,
                reconnect_delay=1.0
            )
        except Exception as e:
            self.logger.error(f"Failed to create listen key: {e}")
            raise

    async def authenticate(self, websocket: Any) -> bool:
        """
        Authenticate MEXC private WebSocket.
        Listen key in URL provides authentication, start keep-alive task.
        """
        if not self.listen_key:
            self.logger.error("No listen key available for authentication")
            return False

        # Start keep-alive task to maintain listen key
        if self.keep_alive_task is None or self.keep_alive_task.done():
            self.keep_alive_task = asyncio.create_task(self._keep_alive_loop())
            self.logger.info("Started listen key keep-alive task")

        return True

    async def handle_keep_alive(self, websocket: Any) -> None:
        """Handle MEXC private keep-alive - managed by keep_alive_task."""
        # Keep-alive is handled by the _keep_alive_loop task
        pass

    def should_reconnect(self, error: Exception) -> bool:
        """Determine if reconnection should be attempted."""
        # Don't reconnect on authentication failures
        if isinstance(error, (PermissionError, ValueError)):
            return False

        # Log error and allow reconnection
        self.logger.warning(f"WebSocket error, will attempt reconnection: {error}")
        return True

    async def _keep_alive_loop(self) -> None:
        """Keep the listen key alive with periodic updates."""
        while self.listen_key:
            try:
                # Wait for keep-alive interval (30 minutes)
                await asyncio.sleep(self.keep_alive_interval)

                if self.listen_key:
                    await self.rest_client.keep_alive_listen_key(self.listen_key)
                    self.logger.debug(f"Listen key kept alive: {self.listen_key[:8]}...")

            except asyncio.CancelledError:
                self.logger.info("Keep-alive task cancelled")
                break
            except Exception as e:
                self.logger.error(f"Failed to keep listen key alive: {e}")
                # Try to regenerate listen key
                await self._regenerate_listen_key()

    async def _regenerate_listen_key(self) -> None:
        """Regenerate listen key if keep-alive fails."""
        try:
            # Delete old listen key if exists
            if self.listen_key:
                try:
                    await self.rest_client.delete_listen_key(self.listen_key)
                    self.logger.info(f"Deleted old listen key: {self.listen_key[:8]}...")
                except Exception:
                    pass  # Ignore delete errors

            # Create new listen key
            self.listen_key = await self.rest_client.create_listen_key()
            self.logger.info(f"Regenerated listen key: {self.listen_key[:8]}...")

        except Exception as e:
            self.logger.error(f"Failed to regenerate listen key: {e}")
            self.listen_key = None

    async def cleanup(self) -> None:
        """Clean up resources including listen key and keep-alive task."""
        try:
            # Cancel keep-alive task
            if self.keep_alive_task and not self.keep_alive_task.done():
                self.keep_alive_task.cancel()
                try:
                    await self.keep_alive_task
                except asyncio.CancelledError:
                    pass
                self.logger.info("Cancelled keep-alive task")

            # Delete listen key
            if self.listen_key and self.rest_client:
                try:
                    await self.rest_client.delete_listen_key(self.listen_key)
                    self.logger.info(f"Deleted listen key: {self.listen_key[:8]}...")
                except Exception as e:
                    self.logger.error(f"Failed to delete listen key: {e}")
                finally:
                    self.listen_key = None

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
