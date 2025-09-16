import asyncio
import logging
from typing import Optional, Any, List, Dict

import msgspec

from core.cex.websocket import ConnectionStrategy, ConnectionContext, SubscriptionStrategy, SubscriptionAction, \
    SubscriptionContext
from core.config.structs import ExchangeConfig
from structs.exchange import Symbol


class MexcPrivateConnectionStrategy(ConnectionStrategy):
    """MEXC private WebSocket connection strategy with listen key management."""

    def __init__(self, config: ExchangeConfig, rest_client=None):
        """
        Initialize MEXC private connection strategy.

        Args:
            config: Exchange configuration
            rest_client: MexcPrivateSpotRest instance for listen key management
        """
        self.config = config
        self.rest_client = rest_client
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Listen key management
        self.listen_key: Optional[str] = None
        self.keep_alive_task: Optional[asyncio.Task] = None
        self.keep_alive_interval = 1800  # 30 minutes in seconds

        # Import REST client if not provided
        if self.rest_client is None:
            from cex.mexc.rest.mexc_private import MexcPrivateSpotRest
            self.rest_client = MexcPrivateSpotRest(config)

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


class MexcPrivateSubscriptionStrategy(SubscriptionStrategy):
    """MEXC private WebSocket subscription strategy."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def _get_private_channels(self) -> List[str]:
        """Get MEXC private channels (single source of truth).
        
        DRY Compliance: Centralized channel definition eliminates code duplication
        between create_subscription_messages() and get_subscription_context().
        """
        return [
            "spot@private.account.v3.api.pb",   # Account balance updates
            "spot@private.deals.v3.api.pb",     # Trade execution updates
            "spot@private.orders.v3.api.pb"     # Order status updates
        ]

    def create_subscription_messages(
        self,
        symbols: List[Symbol],
        action: SubscriptionAction
    ) -> List[str]:
        """Create MEXC private subscription messages.

        MEXC private WebSocket requires explicit subscription to private channels
        after authentication with listen key.
        """
        messages = []

        if action == SubscriptionAction.SUBSCRIBE:
            private_channels = self._get_private_channels()  # Single source of truth

            subscription_message = {
                "method": "SUBSCRIPTION",
                "params": private_channels
            }

            messages.append(msgspec.json.encode(subscription_message).decode())
            self.logger.info(f"Created subscription for {len(private_channels)} private channels")

        elif action == SubscriptionAction.UNSUBSCRIBE:
            private_channels = self._get_private_channels()  # Single source of truth

            unsubscription_message = {
                "method": "UNSUBSCRIPTION",
                "params": private_channels
            }

            messages.append(msgspec.json.encode(unsubscription_message).decode())
            self.logger.info(f"Created unsubscription for {len(private_channels)} private channels")

        return messages

    def get_subscription_context(self, symbol: Symbol) -> SubscriptionContext:
        """Get private subscription context."""
        return SubscriptionContext(
            symbol=symbol,
            channels=self._get_private_channels(),  # Single source of truth
            parameters={}
        )

    def parse_channel_from_message(self, message: Dict[str, Any]) -> Optional[str]:
        """Extract channel from private message."""
        return message.get('c')

    def should_resubscribe_on_reconnect(self) -> bool:
        """Private WebSocket requires resubscription."""
        return True

    def get_symbol_from_channel(self, channel: str) -> Optional[Symbol]:
        """Private channels don't typically contain symbols."""
        return None
