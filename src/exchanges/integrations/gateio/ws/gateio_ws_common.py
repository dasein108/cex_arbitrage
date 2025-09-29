"""
Gate.io WebSocket Common Base Class

Provides shared functionality for all Gate.io WebSocket implementations including:
- Custom heartbeat/ping mechanism for Gate.io's specific requirements
- Common connection setup with Gate.io-specific parameters
- Shared initialization and cleanup logic

This base class is used by both public and private WebSocket implementations
for both spot and futures markets.
"""
from abc import abstractmethod
from exchanges.interfaces.ws import BaseWebsocketInterface
from config.structs import ExchangeConfig
from websockets import connect
import time
import asyncio
from typing import Optional, Dict, Any
from utils import safe_cancel_task
import msgspec


class GateioBaseWebsocket(BaseWebsocketInterface):
    """Gate.io base WebSocket with common functionality for all Gate.io WebSockets."""
    PING_CHANNEL = "ping"
    def __init__(
        self,
        config: ExchangeConfig,
        *args,
        **kwargs
    ):
        """
        Initialize Gate.io base WebSocket with common setup.
        
        Args:
            config: Exchange configuration with WebSocket settings
            *args: Additional arguments passed to base class
            **kwargs: Additional keyword arguments passed to base class
        """
        # Initialize via base class
        super().__init__(
            config=config,
            *args,
            **kwargs
        )
        self.api_key = config.credentials.api_key
        self.secret_key = config.credentials.secret_key

        self._heartbeat_task: Optional[asyncio.Task] = None
        self.logger.info("Gate.io WebSocket base initialized")

    async def _create_websocket(self):
        """
        Create Gate.io WebSocket connection with specific settings.
        
        Returns:
            WebSocket connection configured for Gate.io
        """
        # Stop any existing heartbeat before creating new connection
        await self._stop_heartbeat()
        
        # Create WebSocket with Gate.io-specific settings
        websocket = await connect(
            self.config.websocket_url,
            # Note: Gate.io handles ping/pong internally, we use custom heartbeat
            # ping_interval=config.ping_interval,  # Disabled - using custom heartbeat
            # ping_timeout=config.ping_timeout,    # Disabled - using custom heartbeat
            max_queue=self.config.websocket.max_queue_size,
            compression=None,  # Disable compression for CPU optimization in HFT
            max_size=self.config.websocket.max_message_size,
            write_limit=2 ** 20,  # 1MB write buffer
        )

        # Start Gate.io-specific heartbeat loop
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        return websocket

    async def _heartbeat_loop(self) -> None:
        """
        Gate.io-specific heartbeat loop to keep connection alive.
        
        Gate.io requires periodic ping messages to maintain the connection.
        This is separate from the WebSocket protocol's ping/pong mechanism.
        """
        try:
            while True:
                # Wait for the configured ping interval
                await asyncio.sleep(self.config.websocket.ping_interval)
                
                # Check if connection is still active
                if not self._ws_manager or not self._ws_manager.is_connected():
                    self.logger.debug("WebSocket not connected, skipping heartbeat ping")
                    continue

                # Send Gate.io-specific ping message
                ping_msg = {
                    "time": int(time.time()),
                    "channel": self.PING_CHANNEL,
                    "event": "ping"
                }

                await self._ws_manager.send_message(ping_msg)
                self.logger.debug("Sent Gate.io heartbeat ping", ping_msg=ping_msg)
                
        except asyncio.CancelledError:
            self.logger.debug("Gate.io heartbeat loop cancelled")
        except Exception as e:
            self.logger.error("Gate.io heartbeat loop error",
                              error_type=type(e).__name__,
                              error_message=str(e))

            # Track heartbeat loop error metrics
            self.logger.metric("ws_heartbeat_loop_errors", 1,
                               tags={"exchange": "gateio"})

    async def _stop_heartbeat(self) -> None:
        """Stop the heartbeat task if it's running."""
        if self._heartbeat_task:
            self._heartbeat_task = await safe_cancel_task(self._heartbeat_task)

    async def _auth(self) -> bool:
        """
        Base authentication method.
        
        Returns True for public connections, should be overridden for private.
        """
        # Public WebSockets don't need authentication
        if not self.is_private:
            return True
        
        # Private WebSockets should override this method
        return False

    async def close(self) -> None:
        """
        Close Gate.io WebSocket connection and cleanup.
        
        Ensures heartbeat is stopped before closing the connection.
        """
        await self._stop_heartbeat()
        await super().close()

    async def _handle_subscription_response(self, message: Dict[str, Any]) -> None:
        """Handle Gate.io futures subscription/unsubscription responses."""
        channel = message.get("channel", "")
        result = message.get("result", {})
        status = result.get("status", "unknown")

        if status == "success":
            self.logger.debug(f"Successfully subscribed/unsubscribed to Gate.io private futures channel: {channel}")
        else:
            error_msg = result.get("error", "Unknown error")
            self.logger.error(f"Gate.io private futures subscription error for channel {channel}: {error_msg}")

    async def _handle_auth_response(self, message: Dict[str, Any]) -> None:
        """Handle Gate.io futures authentication response."""
        result = message.get("result", {})
        status = result.get("status", "unknown")

        if status == "success":
            self.logger.debug("Gate.io private futures authentication successful")
        else:
            error_msg = result.get("message", "Authentication failed")
            self.logger.error(f"Gate.io private futures authentication failed: {error_msg}")

    @abstractmethod
    async def _handle_update_message(self, message: Dict[str, Any]) -> None:
        pass

    async def _handle_message(self, raw_message: Any) -> None:
        """Handle incoming Gate.io private futures WebSocket messages."""
        try:
            # Parse JSON message
            if isinstance(raw_message, str):
                message = msgspec.json.decode(raw_message)
            elif isinstance(raw_message, bytes):
                message = msgspec.json.decode(raw_message.decode('utf-8'))
            else:
                message = raw_message

            if not isinstance(message, dict):
                return

            event = message.get("event")

            # Handle different message types
            if event == "pong":
                self.logger.debug("Received pong from Gate.io private futures")
                return
            elif event == "subscribe" or event == "unsubscribe":
                # Handle subscription responses
                await self._handle_subscription_response(message)
                return
            elif event == "update":
                # Handle data updates
                await self._handle_update_message(message)
                return
            elif event == "api":
                # Handle authentication responses
                await self._handle_auth_response(message)
                return
            else:
                # Handle other message types (like authentication results)
                method = message.get("method")
                if method == "RESULT":
                    self.logger.debug("Received authentication result from Gate.io futures")
                else:
                    self.logger.debug(f"Received unknown event type from Gate.io private futures: {event}")

        except Exception as e:
            self.logger.error(f"Error parsing Gate.io private futures message: {e}",
                              exchange="gateio_futures",
                              error_type="message_parse_error")