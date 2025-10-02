"""
WebSocket Manager V5 - Mixin-Based Architecture

WebSocket manager supporting mixin-based direct message handling architecture
for optimal HFT performance. Provides unified interface for all exchange
integrations using composition over inheritance.

Key Features:
- Mixin-based composition for flexibility
- Direct message routing without overhead
- Performance monitoring with sub-millisecond targets
- Unified subscription management
- Circuit breaker patterns for error recovery

HFT COMPLIANCE: Sub-millisecond message processing, <100ms reconnection.
"""

import asyncio
import time
import traceback
from typing import Dict, Optional, Callable, Any, Awaitable
from websockets.client import WebSocketClientProtocol
from websockets.protocol import State as WsState

from .structs import (ParsedMessage, WebSocketManagerConfig, PerformanceMetrics, ConnectionState)
from config.structs import WebSocketConfig
from infrastructure.exceptions.exchange import ExchangeRestError
import msgspec

# HFT Logger Integration
from infrastructure.logging import get_logger, LoggingTimer

# Centralized task utilities
from utils.task_utils import (
    TaskManager, 
    cancel_tasks_with_timeout, 
    safe_close_connection,
    drain_message_queue
)

class WebSocketManager:
    """
    Dual-path WebSocket manager supporting both legacy and new architectures.
    
    This version supports both:
    1. Direct message handling (mixin-based composition)
    2. High-performance routing with minimal overhead
    """
    
    def __init__(
        self,
        config: WebSocketConfig,
        connect_method: Optional[Callable[[], Awaitable[WebSocketClientProtocol]]] = None,
        auth_method: Optional[Callable[[], Awaitable[bool]]] = None,
        message_handler: Optional[Callable[[ParsedMessage], Awaitable[None]]] = None,
        connection_handler: Optional[Callable[[ConnectionState], Awaitable[None]]] = None,
        error_handler: Optional[Callable[[Exception], Awaitable[None]]] = None,
        manager_config: Optional[WebSocketManagerConfig] = None,
        logger=None,
    ):
        self.config = config
        self._raw_message_handler = message_handler
        self.connection_handler = connection_handler
        self.error_handler = error_handler
        self.connect_method = connect_method
        self.auth_method = auth_method
        self.manager_config = manager_config or WebSocketManagerConfig()

        # Initialize HFT logger with optional injection
        self.logger = logger or get_logger('ws.manager')
        
        # Direct WebSocket connection management
        self._websocket: Optional[WebSocketClientProtocol] = None
        self.connection_state = ConnectionState.DISCONNECTED
        
        # Centralized task management
        self._task_manager = TaskManager("ws_manager")
        
        # Control flags
        self._should_reconnect = True

        # Performance tracking
        self.metrics = PerformanceMetrics()
        self.start_time = 0.0
        
        # Message processing
        self._message_queue: asyncio.Queue = asyncio.Queue(
            maxsize=self.manager_config.max_pending_messages
        )

    async def initialize(self) -> None:
        """
        Initialize WebSocket connection using direct connection method.
        
        """
        self.start_time = time.perf_counter()

        try:
            with LoggingTimer(self.logger, "ws_manager_initialization") as timer:
                # Start connection loop (handles reconnection with configured policies)
                self._should_reconnect = True
                self._task_manager.create_task(self._connection_loop(), "connection_loop")
                
                # Start message processing
                self._task_manager.create_task(self._process_messages(), "message_processing")


            self.logger.info("WebSocket manager initialized successfully",
                           initialization_time_ms=timer.elapsed_ms)
            
            # Track initialization metrics
            self.logger.metric("ws_manager_initializations", 1,
                             tags={"exchange": "ws"})
            self.logger.metric("ws_initialization_time_ms", timer.elapsed_ms,
                             tags={"exchange": "ws"})
            
        except Exception as e:
            self.logger.error("Failed to initialize WebSocket manager V4",
                            error_type=type(e).__name__,
                            error_message=str(e))
            
            # Track initialization failure metrics
            self.logger.metric("ws_initialization_failures", 1,
                             tags={"exchange": "ws"})
            
            await self.close()
            raise ExchangeRestError(500, f"WebSocket initialization failed: {e}")
    

    async def send_message(self, message: Dict[str, Any]) -> None:
        """Send message through direct WebSocket connection."""
        if not self._websocket or self.connection_state != ConnectionState.CONNECTED:
            raise ExchangeRestError(503, "WebSocket not connected")
        
        try:
            msg_str = msgspec.json.encode(message).decode("utf-8")
            await self._websocket.send(msg_str)
            
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            raise ExchangeRestError(400, f"Message send failed: {e}")
    
    async def _connection_loop(self) -> None:
        """
        Main connection loop with direct connection and reconnection.
        Simplified - relies on while condition for termination.
        """
        reconnect_attempts = 0
        
        while self._should_reconnect:
            try:
                await self._update_state(ConnectionState.CONNECTING)
                self._websocket = await self.connect_method()
                await self._update_state(ConnectionState.CONNECTED)
                
                # Reset reconnection attempts on successful connection
                reconnect_attempts = 0

                # Authenticate if required
                auth_success = await self.auth_method() if self.auth_method else True

                if not auth_success:
                    self.logger.error("Authentication failed")
                    self.logger.metric("ws_auth_failures", 1, tags={"exchange": "ws"})
                    await self._websocket.close()
                    continue
                
                # Track successful connection
                self.logger.metric("ws_connections", 1, tags={"exchange": "ws"})

                # Start message reader
                reader_task = self._task_manager.create_task(self._message_reader(), "message_reader")
                
                self.logger.info("Direct WebSocket connection established successfully")
                
                # Wait for connection to close
                await reader_task
                
            except asyncio.CancelledError:
                self.logger.debug("Connection loop cancelled")
                break
            except Exception as e:
                # Only check flag for early termination in error cases
                if not self._should_reconnect:
                    break
                    
                await self._handle_connection_error(e, reconnect_attempts)
                reconnect_attempts += 1
        
        self.logger.debug("Connection loop terminated")
        await self._update_state(ConnectionState.DISCONNECTED)
    
    async def _message_reader(self) -> None:
        """
        Read messages from WebSocket and queue for processing.
        Simplified - outer loop handles _should_reconnect.
        """
        try:
            while self.is_connected():
                try:
                    raw_message = await self._websocket.recv()
                    await self._on_raw_message(raw_message)
                except Exception as e:
                    await self._on_reader_error(e)
                    break
        except asyncio.CancelledError:
            self.logger.debug("Message reader cancelled")
        except Exception as e:
            self.logger.error(f"Message reader error: {e}")
            await self._on_reader_error(e)

    
    async def _handle_connection_error(self, error: Exception, attempt: int) -> None:
        """Handle connection errors using configured policies."""
        await self._update_state(ConnectionState.ERROR)
        
        # Connection error handling - check if reconnection should continue
        
        # Check max attempts
        if attempt >= self.config.max_reconnect_attempts:
            self.logger.error(f"Max reconnection attempts ({self.config.max_reconnect_attempts}) reached")
            self._should_reconnect = False
            return

        delay = min(
            self.config.reconnect_delay * (self.config.reconnect_backoff ** attempt),
            self.config.max_reconnect_delay
        )
        # Calculate reconnection delay based on error type
        # else:
        #     delay = min(
        #         policy.initial_delay * (policy.backoff_factor ** attempt),
        #         policy.max_delay
        #     )
        
        self.logger.warning("Connection error, reconnecting",
                           attempt=attempt + 1,
                           delay_seconds=delay,
                           error_message=str(error))
        
        # Track reconnection metrics
        self.logger.metric("ws_reconnection_attempts", 1,
                         tags={"exchange": "ws"})
        
        await self._update_state(ConnectionState.RECONNECTING)
        await asyncio.sleep(delay)
    
    async def _update_state(self, state: ConnectionState) -> None:
        """Update connection state and notify handlers."""
        previous_state = self.connection_state
        self.connection_state = state
        
        if previous_state != state:
            self.logger.info("Connection state changed",
                           previous_state=previous_state.name,
                           new_state=state.name)
            
            # Track state change metrics
            self.logger.metric("ws_state_changes", 1,
                             tags={"exchange": "ws",
                                   "from_state": previous_state.name,
                                   "to_state": state.name})
            
            # Notify external handler
            if self.connection_handler:
                try:
                    await self.connection_handler(state)
                except Exception as e:
                    self.logger.error("Error in state change handler",
                                    error_type=type(e).__name__,
                                    error_message=str(e))
    
    async def _on_raw_message(self, raw_message: Any) -> None:
        """Queue raw message for processing."""
        start_time = time.perf_counter()
        try:
            if self._message_queue.full():
                self.logger.warning("Message queue full, dropping oldest",
                                  queue_size=self._message_queue.qsize(),
                                  max_size=self.manager_config.max_pending_messages)
                
                # Track queue overflow metrics
                self.logger.metric("ws_queue_overflows", 1,
                                 tags={"exchange": "ws"})
                
                try:
                    self._message_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            
            await self._message_queue.put((raw_message, start_time))
            
            # Track message queuing metrics
            self.logger.metric("ws_messages_queued", 1,
                             tags={"exchange": "ws"})
            
        except Exception as e:
            self.metrics.error_count += 1
            self.logger.error("Error queuing message",
                            error_type=type(e).__name__,
                            error_message=str(e))
            
            # Track queuing error metrics
            self.logger.metric("ws_queuing_errors", 1,
                             tags={"exchange": "ws"})
    
    async def _process_messages(self) -> None:
        """Process queued messages using dual-path architecture."""
        while self._should_reconnect:
            try:
                # Use short timeout to make the queue get operation responsive to shutdown
                # HFT optimized: 250ms allows fast shutdown while maintaining performance
                raw_message, queue_time = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=0.25
                )
                processing_start = time.perf_counter()
                try:
                    await self._raw_message_handler(raw_message)

                    processing_time_ms = (time.perf_counter() - processing_start) * 1000

                    self.metrics.update_processing_time(processing_time_ms)

                    self.logger.metric("ws_message_processing_time_ms", processing_time_ms)
                except Exception as e:
                    self.metrics.error_count += 1

                    self.logger.error("Error processing message",
                                      error_type=type(e).__name__,
                                      error_message=str(e))

                    # Track message processing error metrics with path identification
                    self.logger.metric("ws_message_processing_errors", 1,
                                       tags={"exchange": "ws"})
                finally:
                    self._message_queue.task_done()

            except asyncio.TimeoutError:
                # Timeout allows checking _should_reconnect flag - this is normal during low activity
                continue
            except asyncio.CancelledError:
                self.logger.debug("Message processing cancelled")
                break
            except Exception as e:
                # Only log if not shutting down to reduce noise during cleanup
                if self._should_reconnect:
                    self.logger.error("Error in message processing loop",
                                    error_type=type(e).__name__,
                                    error_message=str(e))
                    
                    # Track processing loop error metrics
                    self.logger.metric("ws_processing_loop_errors", 1,
                                     tags={"exchange": "ws"})
                    
                    await asyncio.sleep(0.1)

    async def _on_reader_error(self, error: Exception) -> None:
        """Handle WebSocket errors with error classification."""
        self.metrics.error_count += 1
        
        error_type = type(error).__name__
        

        self.logger.error("WebSocket error",
                        error_type=error_type,
                        error_message=str(error))
        
        # Track WebSocket error metrics
        self.logger.metric("ws_errors", 1,
                         tags={"exchange": "ws", "error_type": error_type})
        
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        if self.connection_state != ConnectionState.CONNECTED or self._websocket is None:
            return False
        try:
            return self._websocket.state == WsState.OPEN
        except AttributeError:
            self.logger.error("WebSocket object has no 'state' attribute",
                            websocket_type=type(self._websocket).__name__)
            return False
    
    async def close(self) -> None:
        """Close WebSocket manager and cleanup resources with centralized utilities."""
        self.logger.info("Closing WebSocket manager...")

        try:
            with LoggingTimer(self.logger, "ws_manager_close") as timer:
                self._should_reconnect = False
                
                # Drain pending messages from queue before task cancellation
                drained_count = await drain_message_queue(
                    self._message_queue, 
                    logger=self.logger,
                    max_drain_count=1000
                )
                if drained_count > 0:
                    self.logger.metric("ws_messages_drained", drained_count, tags={"exchange": "ws"})
                
                # Use centralized task cancellation with timeout
                task_success = await self._task_manager.shutdown(timeout=2.0, logger=self.logger)
                if not task_success:
                    self.logger.metric("ws_cancellation_timeouts", 1, tags={"exchange": "ws"})
                
                # Use centralized connection closing with timeout
                connection_success = await safe_close_connection(
                    self._websocket, timeout=1.0, logger=self.logger
                )
                if not connection_success:
                    self.logger.metric("ws_close_timeouts", 1, tags={"exchange": "ws"})
                
                self._websocket = None
                self.connection_state = ConnectionState.DISCONNECTED
            
            self.logger.info("WebSocket manager closed", close_time_ms=timer.elapsed_ms)
            self.logger.metric("ws_manager_closes", 1, tags={"exchange": "ws"})
            self.logger.metric("ws_close_time_ms", timer.elapsed_ms, tags={"exchange": "ws"})
            
        except Exception as e:
            self.logger.error("Error closing WebSocket manager",
                            error_type=type(e).__name__,
                            error_message=str(e))
            self.logger.metric("ws_close_errors", 1, tags={"exchange": "ws"})