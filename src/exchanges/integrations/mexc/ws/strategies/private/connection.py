import asyncio
import logging
from typing import Optional, Any
from websockets import connect
from websockets.client import WebSocketClientProtocol

from exchanges.integrations.mexc.rest import MexcPrivateSpotRest
from exchanges.base.websocket import ConnectionStrategy, ConnectionContext
from infrastructure.networking.websocket.strategies.connection import ReconnectionPolicy
from infrastructure.config.structs import ExchangeConfig
from infrastructure.exceptions.exchange import BaseExchangeError


class MexcPrivateConnectionStrategy(ConnectionStrategy):
    """MEXC private WebSocket connection strategy with listen key management."""

    def __init__(self, config: ExchangeConfig, rest_client: Optional[MexcPrivateSpotRest] = None):
        """
        Initialize MEXC private connection strategy.

        Args:
            config: Exchange configuration
            rest_client: MexcPrivateSpotRest instance for listen key management
        """
        super().__init__(config)  # Initialize parent with _websocket = None
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Listen key management
        self.listen_key: Optional[str] = None
        self.keep_alive_task: Optional[asyncio.Task] = None
        self.keep_alive_interval = 1800  # 30 minutes in seconds
        
        # MEXC private WebSocket settings
        self.base_url = "wss://wbs-api.mexc.com/ws"
        self.ping_interval = 30  # MEXC uses 30s ping interval (built-in only)
        self.ping_timeout = 15   # Increased timeout for better stability
        self.max_queue_size = 512
        self.max_message_size = 1024 * 1024  # 1MB

        # Use injected REST client or create new one if not provided
        if rest_client is not None:
            self.rest_client = rest_client
            self.logger.debug("Using injected REST client for listen key management")
        else:
            # Create REST client with proper mapper injection
            from exchanges.services.exchange_mapper.factory import ExchangeMapperFactory
            from core.utils.exchange_utils import exchange_name_to_enum
            mapper = ExchangeMapperFactory.inject(exchange_name_to_enum(config.name))
            self.rest_client = MexcPrivateSpotRest(config, mapper)
            self.logger.debug("Created new REST client for listen key management")

    async def connect(self) -> WebSocketClientProtocol:
        """
        Establish MEXC private WebSocket connection with listen key authentication.
        
        Creates listen key via REST API and establishes WebSocket connection with
        MEXC-specific optimizations and authentication.
        
        Returns:
            Raw WebSocket ClientProtocol with authentication
            
        Raises:
            BaseExchangeError: If connection or authentication fails
        """
        try:
            # Create listen key via REST API
            self.listen_key = await self.rest_client.create_listen_key()
            self.logger.info(f"Created MEXC listen key: {self.listen_key[:8]}...")

            # Build WebSocket URL with listen key
            ws_url = f"{self.base_url}?listenKey={self.listen_key}"
            
            self.logger.info(f"Connecting to MEXC private WebSocket: {ws_url[:50]}...")
            
            # MEXC private connection with minimal headers (same as public)
            self._websocket = await connect(
                ws_url,
                # MEXC-specific optimizations
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout,
                max_queue=self.max_queue_size,
                # Disable compression for CPU optimization in HFT
                compression=None,
                max_size=self.max_message_size,
                # Additional performance settings
                write_limit=2 ** 20,  # 1MB write buffer
            )
            
            self.logger.info("MEXC private WebSocket connected successfully")
            return self._websocket
            
        except Exception as e:
            self.logger.error(f"Failed to connect to MEXC private WebSocket: {e}")
            # Clean up listen key if connection failed
            if self.listen_key:
                try:
                    await self.rest_client.delete_listen_key(self.listen_key)
                except Exception:
                    pass  # Ignore cleanup errors
                self.listen_key = None
            raise BaseExchangeError(500, f"MEXC private WebSocket connection failed: {str(e)}")
    
    def get_reconnection_policy(self) -> ReconnectionPolicy:
        """Get MEXC private-specific reconnection policy."""
        return ReconnectionPolicy(
            max_attempts=10,
            initial_delay=1.0,
            backoff_factor=2.0,
            max_delay=60.0,
            reset_on_1005=True  # MEXC private also has 1005 errors frequently
        )
    
    async def create_connection_context(self) -> ConnectionContext:
        """Create MEXC private WebSocket connection context (legacy support)."""
        if not self.listen_key:
            self.listen_key = await self.rest_client.create_listen_key()
            
        ws_url = f"{self.base_url}?listenKey={self.listen_key}"
        
        return ConnectionContext(
            url=ws_url,
            headers={},
            auth_required=True,  # Listen key provides authentication
            auth_params={
                'listen_key': self.listen_key
            },
            ping_interval=self.ping_interval,
            ping_timeout=self.ping_timeout,
            max_reconnect_attempts=10,
            reconnect_delay=1.0
        )

    async def authenticate(self) -> bool:
        """
        Authenticate MEXC private WebSocket using internal connection.
        Listen key in URL provides authentication, start keep-alive task.
        """
        if not self.is_connected:
            raise RuntimeError("No WebSocket connection available for authentication")
            
        if not self.listen_key:
            self.logger.error("No listen key available for authentication")
            return False

        # Start keep-alive task to maintain listen key
        if self.keep_alive_task is None or self.keep_alive_task.done():
            self.keep_alive_task = asyncio.create_task(self._keep_alive_loop())
            self.logger.info("Started MEXC listen key keep-alive task")

        return True

    async def handle_heartbeat(self) -> None:
        """Handle MEXC private heartbeat using internal WebSocket - managed by keep_alive_loop."""
        if not self.is_connected:
            raise RuntimeError("No WebSocket connection available for heartbeat")
            
        # MEXC private uses:
        # 1. Built-in WebSocket ping/pong (handled automatically)
        # 2. Listen key keep-alive via REST API (handled by _keep_alive_loop)
        # No additional heartbeat needed in this method
        self.logger.debug("MEXC private heartbeat handled by built-in ping/pong + listen key keep-alive")
        pass

    def should_reconnect(self, error: Exception) -> bool:
        """Determine if reconnection should be attempted for MEXC private errors."""
        # Classify error first
        error_type = self.classify_error(error)
        
        # Always reconnect for WebSocket 1005 errors (common with MEXC private)
        if error_type == "abnormal_closure":
            self.logger.info("MEXC private 1005 error detected - will reconnect and regenerate listen key")
            # Trigger listen key regeneration on reconnect
            asyncio.create_task(self._regenerate_listen_key())
            return True
        
        # Reconnect on network errors but regenerate listen key
        if error_type in ["connection_refused", "timeout"]:
            self.logger.warning(f"MEXC private {error_type} error - will reconnect with new listen key")
            asyncio.create_task(self._regenerate_listen_key())
            return True
        
        # Don't reconnect on authentication failures
        if error_type == "authentication_failure":
            self.logger.error("MEXC private authentication failure - won't reconnect")
            return False
        
        # For unknown errors, try reconnecting with fresh listen key
        self.logger.warning(f"MEXC private unknown error ({error}) - will attempt reconnect with new listen key")
        asyncio.create_task(self._regenerate_listen_key())
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
