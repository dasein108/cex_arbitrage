"""
Consolidated WebSocket Base Interface

Unified WebSocket interface that integrates all mixin functionality directly,
eliminating the need for WebSocketManager and providing direct connection management
with built-in authentication, subscriptions, and reconnection handling.

Key Features:
- Direct WebSocket connection management
- Integrated mixin composition (ConnectionMixin, SubscriptionMixin, domain mixins)
- Built-in authentication for private interfaces
- Automatic subscription and resubscription handling
- HFT optimized with sub-millisecond processing targets

Architecture Benefits:
- Single layer architecture (no WebSocketManager)
- Direct message processing
- Performance optimized for HFT trading
- Simplified debugging and maintenance
- Built-in lifecycle management
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Set, Callable, Awaitable
from websockets.client import WebSocketClientProtocol
from websockets.protocol import State as WsState
import websockets

from config.structs import ExchangeConfig
from infrastructure.networking.websocket.mixins import ConnectionMixin, SubscriptionMixin
from infrastructure.networking.websocket.structs import ConnectionState, ConnectionContext
from infrastructure.networking.websocket.mixins.connection_mixin import ReconnectionPolicy
from infrastructure.logging import get_exchange_logger, LoggingTimer
from exchanges.structs.common import Symbol


class ConsolidatedWebSocketInterface(ConnectionMixin, SubscriptionMixin, ABC):
    """
    Consolidated WebSocket interface with integrated mixin functionality.
    
    This class directly manages WebSocket connections without intermediate layers,
    providing a clean, high-performance interface for exchange WebSocket operations.
    
    Features:
    - Direct WebSocket instance management
    - Integrated connection lifecycle with automatic reconnection
    - Built-in subscription management with resubscription on reconnect
    - Authentication handling for private interfaces
    - Performance optimized for HFT requirements
    """
    
    def __init__(
        self,
        config: ExchangeConfig,
        is_private: bool = False,
        connection_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None,
        logger=None
    ):
        """
        Initialize consolidated WebSocket interface.
        
        Args:
            config: Exchange configuration
            is_private: Whether this is a private interface requiring authentication
            connection_handler: Optional callback for connection state changes
            logger: Optional logger instance
        """
        self.config = config
        self.is_private = is_private
        self.connection_handler = connection_handler
        
        # Initialize mixins with config
        super().__init__(config=config)
        
        # Logger setup
        tag = 'private' if is_private else 'public'
        self.logger = logger or get_exchange_logger(config.name, f'ws.{tag}')
        
        # Direct WebSocket management
        self._websocket: Optional[WebSocketClientProtocol] = None
        self._connection_state = ConnectionState.DISCONNECTED
        
        # Task management
        self._connection_task: Optional[asyncio.Task] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        
        # Control flags and state
        self._should_reconnect = True
        self._active_symbols: Set[Symbol] = set()
        self._is_authenticated = False
        
        # Performance tracking
        self._connection_attempts = 0
        self._message_count = 0
        self._start_time = 0.0
        
        self.logger.info("Consolidated WebSocket interface initialized",
                        exchange=config.name,
                        is_private=is_private,
                        mixin_architecture=True)
    
    # Core WebSocket operations
    
    async def start(self, symbols: Optional[List[Symbol]] = None) -> None:
        """
        Start the WebSocket interface with optional initial symbols.
        
        Args:
            symbols: Optional list of symbols to subscribe to initially
        """
        try:
            with LoggingTimer(self.logger, "websocket_start") as timer:
                self._start_time = time.perf_counter()
                
                if symbols:
                    self._active_symbols.update(symbols)
                
                # Start connection loop
                self._should_reconnect = True
                self._connection_task = asyncio.create_task(self._connection_loop())
                
                # Wait for initial connection
                await self._wait_for_connection()
                
                self.logger.info("WebSocket interface started successfully",
                               symbols_count=len(symbols) if symbols else 0,
                               start_time_ms=timer.elapsed_ms)
                
        except Exception as e:
            self.logger.error("Failed to start WebSocket interface",
                            error_type=type(e).__name__,
                            error_message=str(e))
            await self.stop()
            raise
    
    async def stop(self) -> None:
        """Stop the WebSocket interface and clean up resources."""
        try:
            with LoggingTimer(self.logger, "websocket_stop") as timer:
                self._should_reconnect = False
                
                # Cancel all tasks
                for task in [self._connection_task, self._reader_task, self._heartbeat_task]:
                    if task and not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                
                # Close WebSocket connection
                if self._websocket:
                    try:
                        await self._websocket.close()
                    except Exception as e:
                        self.logger.warning("Error closing WebSocket", error=str(e))
                    finally:
                        self._websocket = None
                
                # Clean up state
                await self.cleanup()
                self._connection_state = ConnectionState.DISCONNECTED
                
                self.logger.info("WebSocket interface stopped",
                               stop_time_ms=timer.elapsed_ms)
                
        except Exception as e:
            self.logger.error("Error stopping WebSocket interface",
                            error_type=type(e).__name__,
                            error_message=str(e))
    
    async def send_message(self, message: Dict[str, Any]) -> None:
        """
        Send a message through the WebSocket connection.
        
        Args:
            message: Message to send (will be JSON serialized)
        """
        if not self.is_websocket_connected():
            raise RuntimeError("WebSocket not connected")
        
        try:
            import json
            message_str = json.dumps(message)
            await self._websocket.send(message_str)
            
            self.logger.debug("Message sent",
                            message_type=message.get('method', 'unknown'),
                            message_size=len(message_str))
            
        except Exception as e:
            self.logger.error("Failed to send message",
                            error_type=type(e).__name__,
                            error_message=str(e))
            raise
    
    def is_websocket_connected(self) -> bool:
        """Check if WebSocket is currently connected."""
        return (self._websocket is not None and 
                self._websocket.state == WsState.OPEN and
                self._connection_state == ConnectionState.CONNECTED)
    
    # Subscription management
    
    async def subscribe(self, symbols: List[Symbol]) -> None:
        """
        Subscribe to symbols using integrated subscription logic.
        
        Args:
            symbols: List of symbols to subscribe to
        """
        if not self.is_websocket_connected():
            raise RuntimeError("WebSocket not connected")
        
        try:
            # Get subscription messages using SubscriptionMixin
            channels = []
            for symbol in symbols:
                symbol_channels = self.get_channels_for_symbol(symbol)
                channels.extend(symbol_channels)
            
            if channels:
                message = self.create_subscription_message("subscribe", channels)
                await self.send_message(message)
                
                # Update active symbols
                self._active_symbols.update(symbols)
                
                self.logger.info("Subscribed to symbols",
                               symbols_count=len(symbols),
                               channels_count=len(channels))
            
        except Exception as e:
            self.logger.error("Failed to subscribe to symbols",
                            symbols_count=len(symbols),
                            error_type=type(e).__name__,
                            error_message=str(e))
            raise
    
    async def unsubscribe(self, symbols: List[Symbol]) -> None:
        """
        Unsubscribe from symbols.
        
        Args:
            symbols: List of symbols to unsubscribe from
        """
        if not self.is_websocket_connected():
            return  # Nothing to unsubscribe from
        
        try:
            # Get unsubscription messages
            channels = []
            for symbol in symbols:
                symbol_channels = self.get_channels_for_symbol(symbol)
                channels.extend(symbol_channels)
            
            if channels:
                message = self.create_subscription_message("unsubscribe", channels)
                await self.send_message(message)
                
                # Remove from active symbols
                self._active_symbols.difference_update(symbols)
                
                self.logger.info("Unsubscribed from symbols",
                               symbols_count=len(symbols),
                               channels_count=len(channels))
            
        except Exception as e:
            self.logger.error("Failed to unsubscribe from symbols",
                            symbols_count=len(symbols),
                            error_type=type(e).__name__,
                            error_message=str(e))
            raise
    
    # Internal implementation
    
    async def _connection_loop(self) -> None:
        """Main connection loop with automatic reconnection."""
        policy = self.get_reconnection_policy()
        attempt = 0
        
        while self._should_reconnect:
            try:
                self.logger.info("Attempting WebSocket connection",
                               attempt=attempt + 1,
                               max_attempts=policy.max_attempts)
                
                # Create connection using ConnectionMixin
                context = self.create_connection_context()
                self._websocket = await websockets.connect(
                    context.url,
                    extra_headers=context.headers or {},
                    **context.extra_params or {}
                )
                
                # Update connection state
                self._connection_state = ConnectionState.CONNECTED
                await self._notify_connection_state(ConnectionState.CONNECTED)
                
                # Authenticate if private interface
                if self.is_private:
                    auth_success = await self.authenticate()
                    if not auth_success:
                        self.logger.error("Authentication failed")
                        await self._websocket.close()
                        continue
                    self._is_authenticated = True
                
                # Resubscribe to active symbols
                if self._active_symbols:
                    await self._resubscribe()
                
                # Start message reader
                self._reader_task = asyncio.create_task(self._message_reader())
                
                # Start heartbeat if needed
                if hasattr(self, '_start_heartbeat'):
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                
                # Reset attempt counter on successful connection
                attempt = 0
                
                # Wait for reader to complete (connection lost)
                await self._reader_task
                
            except Exception as e:
                self.logger.error("Connection attempt failed",
                                attempt=attempt + 1,
                                error_type=type(e).__name__,
                                error_message=str(e))
                
                # Clean up failed connection
                if self._websocket:
                    try:
                        await self._websocket.close()
                    except:
                        pass
                    self._websocket = None
                
                self._connection_state = ConnectionState.DISCONNECTED
                await self._notify_connection_state(ConnectionState.DISCONNECTED)
                
                # Check if we should reconnect
                if not self.should_reconnect(e):
                    self.logger.error("Stopping reconnection attempts",
                                    error_type=type(e).__name__)
                    break
                
                attempt += 1
                if attempt >= policy.max_attempts:
                    self.logger.error("Max reconnection attempts reached",
                                    max_attempts=policy.max_attempts)
                    break
                
                # Wait before next attempt
                delay = policy.calculate_delay(attempt)
                self.logger.info("Waiting before reconnection",
                               delay_seconds=delay,
                               attempt=attempt)
                await asyncio.sleep(delay)
    
    async def _message_reader(self) -> None:
        """Read messages from WebSocket and process them directly."""
        try:
            while self.is_websocket_connected():
                raw_message = await self._websocket.recv()
                self._message_count += 1
                
                # Process message directly using abstract method
                await self._handle_message(raw_message)
                
        except Exception as e:
            self.logger.error("Message reader error",
                            error_type=type(e).__name__,
                            error_message=str(e))
            raise
    
    async def _resubscribe(self) -> None:
        """Resubscribe to all active symbols after reconnection."""
        if self._active_symbols:
            try:
                await self.subscribe(list(self._active_symbols))
                self.logger.info("Resubscribed to symbols",
                               symbols_count=len(self._active_symbols))
            except Exception as e:
                self.logger.error("Failed to resubscribe",
                                symbols_count=len(self._active_symbols),
                                error_type=type(e).__name__,
                                error_message=str(e))
    
    async def _wait_for_connection(self, timeout: float = 10.0) -> None:
        """Wait for WebSocket to be connected."""
        start_time = time.time()
        while not self.is_websocket_connected() and time.time() - start_time < timeout:
            await asyncio.sleep(0.1)
        
        if not self.is_websocket_connected():
            raise RuntimeError(f"Failed to connect within {timeout} seconds")
    
    async def _notify_connection_state(self, state: ConnectionState) -> None:
        """Notify connection handler about state changes."""
        if self.connection_handler:
            try:
                await self.connection_handler(state)
            except Exception as e:
                self.logger.warning("Connection handler error",
                                  state=state.value,
                                  error_type=type(e).__name__,
                                  error_message=str(e))
    
    async def _heartbeat_loop(self) -> None:
        """Handle custom heartbeat if required by exchange."""
        try:
            while self.is_websocket_connected():
                await self.handle_heartbeat()
                await asyncio.sleep(30)  # Default heartbeat interval
        except Exception as e:
            self.logger.error("Heartbeat error",
                            error_type=type(e).__name__,
                            error_message=str(e))
    
    # Abstract methods that must be implemented by exchange-specific classes
    
    @abstractmethod
    async def _handle_message(self, raw_message: Any) -> None:
        """
        Handle incoming WebSocket message.
        
        Args:
            raw_message: Raw message from WebSocket
        """
        pass
    
    # Performance and monitoring
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for monitoring."""
        uptime = time.perf_counter() - self._start_time if self._start_time > 0 else 0
        
        return {
            'is_connected': self.is_websocket_connected(),
            'connection_state': self._connection_state.value,
            'is_authenticated': self._is_authenticated,
            'active_symbols_count': len(self._active_symbols),
            'message_count': self._message_count,
            'connection_attempts': self._connection_attempts,
            'uptime_seconds': uptime,
            'exchange': self.config.name,
            'is_private': self.is_private
        }
    
    # Context manager support
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()