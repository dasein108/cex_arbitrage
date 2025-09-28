# WebSocket Refactoring Implementation Guide

## Overview

This document provides detailed implementation guidance for the WebSocket architecture refactoring. It includes specific code examples, interface definitions, and step-by-step implementation instructions.

## Core Interfaces Implementation

### 1. BaseWebSocketInterface

**File:** `/src/infrastructure/networking/websocket/base_interface.py`

```python
"""
Base WebSocket Interface - Core Business Logic
Extracted from WebSocketManager to separate infrastructure from exchange-specific logic.
"""

import asyncio
import time
from typing import Optional, Any, Dict, List
from abc import ABC, abstractmethod
from websockets.client import WebSocketClientProtocol
from websockets.protocol import State as WsState

from .structs import ConnectionState, PerformanceMetrics
from config.structs import WebSocketConfig
from infrastructure.logging import get_logger, LoggingTimer
from infrastructure.exceptions.exchange import ExchangeRestError
import msgspec


class BaseWebSocketInterface(ABC):
    """
    Base interface containing core WebSocket business logic.
    
    Extracted from WebSocketManager to provide clean separation between
    infrastructure concerns and exchange-specific behavior.
    """
    
    def __init__(self, config: WebSocketConfig, handler: Any):
        """
        Initialize base WebSocket interface.
        
        Args:
            config: WebSocket configuration
            handler: Handler implementing required mixins (ConnectionMixin, SubscriptionMixin)
        """
        self.config = config
        self.handler = handler
        
        # Core WebSocket state (extracted from WebSocketManager)
        self._websocket: Optional[WebSocketClientProtocol] = None
        self.connection_state = ConnectionState.DISCONNECTED
        
        # Task management
        self._connection_task: Optional[asyncio.Task] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._processing_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        
        # Control flags
        self._should_reconnect = True
        
        # Performance tracking
        self.metrics = PerformanceMetrics()
        self.start_time = 0.0
        
        # Message processing
        self._message_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        
        # Logger setup
        self.logger = get_logger(f'ws.base.{handler.__class__.__name__}')
        
        self.logger.info("BaseWebSocketInterface initialized",
                        handler_type=handler.__class__.__name__)
    
    # Abstract methods that handlers must implement
    
    @abstractmethod
    async def _handle_message(self, raw_message: Any) -> None:
        """
        Handle incoming WebSocket message.
        
        This method must be implemented by the handler to process
        exchange-specific message formats.
        
        Args:
            raw_message: Raw WebSocket message (str or bytes)
        """
        pass
    
    # Core WebSocket operations
    
    async def initialize(self) -> None:
        """Initialize WebSocket connection and processing tasks."""
        self.start_time = time.perf_counter()
        
        try:
            with LoggingTimer(self.logger, "ws_base_initialization") as timer:
                self.logger.info("Initializing BaseWebSocket interface")
                
                # Start connection loop
                self._should_reconnect = True
                self._connection_task = asyncio.create_task(self._connection_loop())
                
                # Start message processing
                self._processing_task = asyncio.create_task(self._process_messages())
                
                # Start heartbeat if configured
                if self.config.heartbeat_interval and self.config.heartbeat_interval > 0:
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            self.logger.info("BaseWebSocket interface initialized successfully",
                           initialization_time_ms=timer.elapsed_ms)
            
        except Exception as e:
            self.logger.error("Failed to initialize BaseWebSocket interface",
                            error_type=type(e).__name__,
                            error_message=str(e))
            await self.close()
            raise ExchangeRestError(500, f"WebSocket initialization failed: {e}")
    
    async def send_message(self, message: Dict[str, Any]) -> None:
        """Send message through WebSocket connection."""
        if not self._websocket or self.connection_state != ConnectionState.CONNECTED:
            raise ExchangeRestError(503, "WebSocket not connected")
        
        try:
            msg_str = msgspec.json.encode(message).decode("utf-8")
            await self._websocket.send(msg_str)
            
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            raise ExchangeRestError(400, f"Message send failed: {e}")
    
    async def _connection_loop(self) -> None:
        """Main connection loop delegating to handler's ConnectionMixin."""
        reconnection_policy = self.handler.get_reconnection_policy()
        reconnect_attempts = 0
        
        while self._should_reconnect:
            try:
                await self._update_state(ConnectionState.CONNECTING)
                
                # Delegate connection to handler's ConnectionMixin
                self._websocket = await self.handler.connect()
                
                if not self._websocket:
                    raise ExchangeRestError(500, "Handler returned no WebSocket connection")
                
                await self._update_state(ConnectionState.CONNECTED)
                reconnect_attempts = 0
                
                # Delegate authentication to handler
                auth_success = await self.handler.authenticate()
                if not auth_success:
                    self.logger.error("Authentication failed")
                    await self._websocket.close()
                    continue
                
                # Handle resubscription
                if hasattr(self.handler, 'get_resubscription_messages'):
                    resubscription_messages = await self.handler.get_resubscription_messages()
                    for message in resubscription_messages:
                        await self.send_message(message)
                
                # Start message reader
                self._reader_task = asyncio.create_task(self._message_reader())
                
                self.logger.info("WebSocket connection established successfully")
                
                # Wait for connection to close
                await self._reader_task
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                await self._handle_connection_error(e, reconnection_policy, reconnect_attempts)
                reconnect_attempts += 1
        
        await self._update_state(ConnectionState.DISCONNECTED)
    
    async def _message_reader(self) -> None:
        """Read messages from WebSocket and queue for processing."""
        try:
            while True:
                if not self.is_connected():
                    self.logger.debug("WebSocket disconnected, exiting message reader")
                    break
                
                try:
                    raw_message = await self._websocket.recv()
                    await self._on_raw_message(raw_message)
                except Exception as e:
                    await self._on_error(e)
                    break
                    
        except asyncio.CancelledError:
            self.logger.debug("Message reader cancelled")
        except Exception as e:
            self.logger.error(f"Message reader error: {e}")
            await self._on_error(e)
    
    async def _process_messages(self) -> None:
        """Process queued messages using handler's _handle_message."""
        while True:
            try:
                raw_message, queue_time = await self._message_queue.get()
                processing_start = time.perf_counter()
                
                try:
                    # Delegate to handler's _handle_message implementation
                    await self.handler._handle_message(raw_message)
                    
                    processing_time_ms = (time.perf_counter() - processing_start) * 1000
                    self.metrics.update_processing_time(processing_time_ms)
                    self.metrics.messages_processed += 1
                
                except Exception as e:
                    await self._handle_processing_error(e, raw_message)
                
                finally:
                    self._message_queue.task_done()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Error in message processing loop",
                                error_type=type(e).__name__,
                                error_message=str(e))
    
    async def _on_raw_message(self, raw_message: Any) -> None:
        """Queue raw message for processing."""
        start_time = time.perf_counter()
        
        try:
            if self._message_queue.full():
                self.logger.warning("Message queue full, dropping oldest")
                try:
                    self._message_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            
            await self._message_queue.put((raw_message, start_time))
            
        except Exception as e:
            self.metrics.error_count += 1
            self.logger.error("Error queuing message",
                            error_type=type(e).__name__,
                            error_message=str(e))
    
    async def _handle_connection_error(self, error: Exception, policy, attempt: int) -> None:
        """Handle connection errors using handler-specific policies."""
        await self._update_state(ConnectionState.ERROR)
        
        # Delegate reconnection decision to handler
        if not self.handler.should_reconnect(error):
            error_type = self.handler.classify_error(error)
            self.logger.error(f"Handler decided not to reconnect after {error_type} error: {error}")
            self._should_reconnect = False
            return
        
        # Check max attempts
        if attempt >= policy.max_attempts:
            self.logger.error(f"Max reconnection attempts ({policy.max_attempts}) reached")
            self._should_reconnect = False
            return
        
        # Calculate delay with handler policy
        error_type = self.handler.classify_error(error)
        if policy.reset_on_1005 and error_type == "abnormal_closure":
            delay = policy.initial_delay
        else:
            delay = min(
                policy.initial_delay * (policy.backoff_factor ** attempt),
                policy.max_delay
            )
        
        self.logger.warning("Connection error, reconnecting",
                           error_type=error_type,
                           attempt=attempt + 1,
                           delay_seconds=delay)
        
        await self._update_state(ConnectionState.RECONNECTING)
        await asyncio.sleep(delay)
    
    async def _handle_processing_error(self, error: Exception, raw_message: Any) -> None:
        """Handle errors during message processing."""
        self.metrics.error_count += 1
        
        self.logger.error("Error processing message",
                        error_type=type(error).__name__,
                        error_message=str(error))
    
    async def _on_error(self, error: Exception) -> None:
        """Handle WebSocket errors using handler classification."""
        self.metrics.error_count += 1
        
        error_type = self.handler.classify_error(error)
        
        if error_type == "abnormal_closure":
            self.logger.warning("WebSocket error",
                              error_type=error_type,
                              error_message=str(error))
        else:
            self.logger.error("WebSocket error",
                            error_type=error_type,
                            error_message=str(error))
    
    async def _heartbeat_loop(self) -> None:
        """Handler-managed heartbeat loop."""
        try:
            while True:
                await asyncio.sleep(self.config.heartbeat_interval)
                
                if self.config.has_heartbeat and self.is_connected():
                    try:
                        await self.handler.handle_heartbeat()
                    except Exception as e:
                        self.logger.warning("Handler heartbeat failed",
                                          error_message=str(e))
                        
        except asyncio.CancelledError:
            self.logger.debug("Heartbeat loop cancelled")
        except Exception as e:
            self.logger.error("Heartbeat loop error",
                            error_type=type(e).__name__,
                            error_message=str(e))
    
    async def _update_state(self, state: ConnectionState) -> None:
        """Update connection state."""
        previous_state = self.connection_state
        self.connection_state = state
        
        if previous_state != state:
            self.logger.info("Connection state changed",
                           previous_state=previous_state.name,
                           new_state=state.name)
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        if self.connection_state != ConnectionState.CONNECTED or self._websocket is None:
            return False
        
        try:
            return self._websocket.state == WsState.OPEN
        except AttributeError:
            return False
    
    async def close(self) -> None:
        """Close WebSocket interface and cleanup resources."""
        self.logger.info("Closing BaseWebSocket interface...")
        
        try:
            self._should_reconnect = False
            
            # Cancel all tasks
            tasks = [
                self._processing_task,
                self._heartbeat_task,
                self._connection_task,
                self._reader_task
            ]
            
            for task in tasks:
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
                    self.logger.error("Error closing WebSocket",
                                    error_type=type(e).__name__,
                                    error_message=str(e))
                self._websocket = None
            
            # Handler cleanup
            if hasattr(self.handler, 'cleanup'):
                await self.handler.cleanup()
            
            self.connection_state = ConnectionState.DISCONNECTED
            
            self.logger.info("BaseWebSocket interface closed")
            
        except Exception as e:
            self.logger.error("Error closing BaseWebSocket interface",
                            error_type=type(e).__name__,
                            error_message=str(e))
```

### 2. Enhanced Mixin Implementations

#### AuthMixin

**File:** `/src/infrastructure/networking/websocket/mixins/auth_mixin.py`

```python
"""
Authentication Mixin for WebSocket Handlers
Provides authentication behavior override for exchanges requiring WebSocket authentication.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import time
import hmac
import hashlib
import base64

from config.structs import ExchangeConfig
from infrastructure.logging import get_logger


class AuthMixin(ABC):
    """
    Base authentication mixin for WebSocket handlers.
    
    Override authentication behavior for exchanges that require
    WebSocket authentication (like Gate.io).
    """
    
    def __init__(self, config: ExchangeConfig, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = config
        
        if not hasattr(self, 'logger'):
            self.logger = get_logger(f'auth.{self.__class__.__name__}')
    
    @abstractmethod
    async def authenticate(self) -> bool:
        """
        Perform exchange-specific authentication.
        
        Returns:
            True if authentication successful or not required
        """
        pass
    
    @abstractmethod
    def create_auth_message(self) -> Dict[str, Any]:
        """
        Create exchange-specific authentication message.
        
        Returns:
            Authentication message ready for sending
        """
        pass
    
    def requires_authentication(self) -> bool:
        """Override default no-auth behavior."""
        return True
    
    async def _wait_for_auth_confirmation(self, timeout: float = 10.0) -> bool:
        """
        Wait for authentication confirmation.
        
        Args:
            timeout: Maximum time to wait for confirmation
            
        Returns:
            True if authentication confirmed
        """
        # Default implementation - override for exchange-specific logic
        return True


class GateioAuthMixin(AuthMixin):
    """Gate.io specific authentication implementation."""
    
    async def authenticate(self) -> bool:
        """Perform Gate.io WebSocket authentication."""
        if not self.config.has_credentials():
            self.logger.error("Gate.io authentication requires API credentials")
            return False
        
        try:
            auth_message = self.create_auth_message()
            
            # Send authentication message
            await self.send_message(auth_message)
            
            # Wait for authentication confirmation
            auth_success = await self._wait_for_auth_confirmation()
            
            if auth_success:
                self.logger.info("Gate.io WebSocket authentication successful")
            else:
                self.logger.error("Gate.io WebSocket authentication failed")
            
            return auth_success
            
        except Exception as e:
            self.logger.error("Gate.io authentication error",
                            error_type=type(e).__name__,
                            error_message=str(e))
            return False
    
    def create_auth_message(self) -> Dict[str, Any]:
        """Create Gate.io authentication message."""
        timestamp = str(int(time.time()))
        
        # Gate.io authentication signature
        message = f"channel=spot.order&event=subscribe&time={timestamp}"
        signature = hmac.new(
            self.config.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
        
        return {
            "id": int(timestamp),
            "method": "server.sign",
            "params": [
                self.config.api_key,
                signature,
                timestamp
            ]
        }
    
    async def _wait_for_auth_confirmation(self, timeout: float = 10.0) -> bool:
        """Wait for Gate.io authentication confirmation."""
        # Implementation specific to Gate.io response format
        # This would integrate with the message processing pipeline
        # to detect authentication success/failure responses
        
        # For now, return True - actual implementation would
        # wait for specific auth response message
        return True


class NoAuthMixin(AuthMixin):
    """Default no-authentication mixin for public endpoints."""
    
    async def authenticate(self) -> bool:
        """Public endpoints require no authentication."""
        return True
    
    def create_auth_message(self) -> Dict[str, Any]:
        """No auth message needed for public endpoints."""
        return {}
    
    def requires_authentication(self) -> bool:
        """Public endpoints don't require authentication."""
        return False
```

#### Enhanced ConnectionMixin

**File:** `/src/infrastructure/networking/websocket/mixins/connection_mixin.py` (additions)

```python
# Add to existing connection_mixin.py file

class MexcConnectionMixin(ConnectionMixin):
    """MEXC-specific connection behavior overrides."""
    
    def create_connection_context(self) -> ConnectionContext:
        """Create MEXC-specific connection configuration."""
        return ConnectionContext(
            url="wss://stream.mexc.com/ws",
            headers={},  # Minimal headers to avoid blocking
            extra_params={
                "ping_interval": 30,  # MEXC-specific timing
                "ping_timeout": 10,
                "close_timeout": 10,
                "compression": None,  # Disable for CPU optimization
                "max_queue": 512,
                "max_size": 1024 * 1024,  # 1MB
                "write_limit": 2 ** 20  # 1MB write buffer
            }
        )
    
    def get_reconnection_policy(self) -> ReconnectionPolicy:
        """Get MEXC-specific reconnection policy."""
        return ReconnectionPolicy(
            max_attempts=15,  # Aggressive reconnection for MEXC
            initial_delay=0.5,
            backoff_factor=1.5,
            max_delay=30.0,
            reset_on_1005=True  # MEXC frequently sends 1005 errors
        )
    
    def should_reconnect(self, error: Exception) -> bool:
        """MEXC-specific reconnection logic."""
        error_str = str(error).lower()
        
        # Always reconnect on 1005 errors (very common with MEXC)
        if "1005" in error_str or "no status received" in error_str:
            return True
        
        # MEXC-specific network error patterns
        if any(pattern in error_str for pattern in [
            "connection reset", "connection lost", "timeout",
            "network error", "connection refused"
        ]):
            return True
        
        # Don't reconnect on authentication failures
        if "authentication" in error_str or "unauthorized" in error_str:
            return False
        
        # Default: attempt reconnection for MEXC (can be unstable)
        return True
    
    def classify_error(self, error: Exception) -> str:
        """Enhanced error classification for MEXC."""
        error_str = str(error).lower()
        
        if "1005" in error_str or "no status received" in error_str:
            return "abnormal_closure"
        elif "connection refused" in error_str:
            return "connection_refused"
        elif "timeout" in error_str:
            return "timeout"
        elif "connection reset" in error_str:
            return "connection_reset"
        elif "network" in error_str:
            return "network_error"
        else:
            return super().classify_error(error)


class GateioConnectionMixin(ConnectionMixin):
    """Gate.io specific connection behavior."""
    
    def create_connection_context(self) -> ConnectionContext:
        """Create Gate.io connection configuration."""
        return ConnectionContext(
            url=self.config.websocket_url,  # Different for spot vs futures
            headers={
                "User-Agent": "GateIO-HFT-Client/1.0"
            },
            extra_params={
                "ping_interval": 30,
                "ping_timeout": 15,
                "compression": "deflate",  # Gate.io supports compression
                "max_queue": 256
            }
        )
    
    def get_reconnection_policy(self) -> ReconnectionPolicy:
        """Get Gate.io-specific reconnection policy."""
        return ReconnectionPolicy(
            max_attempts=10,
            initial_delay=1.0,
            backoff_factor=2.0,
            max_delay=60.0,
            reset_on_1005=False  # Gate.io has fewer 1005 errors
        )
```

### 3. Message Handler Hierarchy

#### BaseMessageHandler

**File:** `/src/infrastructure/networking/websocket/handlers/base_message_handler.py`

```python
"""
Base Message Handler
Provides template method pattern for WebSocket message processing.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List
import time

from infrastructure.logging import get_logger
from infrastructure.networking.websocket.message_types import WebSocketMessageType


class BaseMessageHandler(ABC):
    """
    Base message handler with common parsing infrastructure.
    
    Implements template method pattern for consistent message processing
    across all exchange handlers.
    """
    
    def __init__(self, exchange_name: str):
        """
        Initialize base message handler.
        
        Args:
            exchange_name: Name of the exchange (e.g., "mexc", "gateio")
        """
        self.exchange_name = exchange_name
        self.logger = get_logger(f'ws.handler.{exchange_name}')
        
        # Performance tracking
        self.message_count = 0
        self.parsing_times = []
        self.error_count = 0
        
        self.logger.info(f"BaseMessageHandler initialized for {exchange_name}")
    
    async def _handle_message(self, raw_message: Any) -> None:
        """
        Template method for message processing.
        
        This method implements the common message processing flow:
        1. Performance tracking setup
        2. Message type detection
        3. Message routing to appropriate handler
        4. Error handling and logging
        
        Args:
            raw_message: Raw WebSocket message (str or bytes)
        """
        start_time = time.perf_counter()
        
        try:
            self.message_count += 1
            
            # Step 1: Detect message type (exchange-specific)
            message_type = await self._detect_message_type(raw_message)
            
            # Step 2: Route to appropriate handler
            await self._route_message(message_type, raw_message)
            
            # Step 3: Performance tracking
            processing_time = (time.perf_counter() - start_time) * 1_000_000  # μs
            self.parsing_times.append(processing_time)
            
            # Step 4: Performance validation (HFT compliance)
            await self._validate_performance(processing_time, message_type)
            
        except Exception as e:
            await self._handle_processing_error(e, raw_message)
        finally:
            # Always track total processing time
            total_time = (time.perf_counter() - start_time) * 1_000_000  # μs
            if len(self.parsing_times) % 1000 == 0:  # Log every 1000 messages
                avg_time = sum(self.parsing_times[-1000:]) / 1000
                self.logger.debug(f"Average processing time (last 1000): {avg_time:.2f}μs")
    
    @abstractmethod
    async def _detect_message_type(self, raw_message: Any) -> WebSocketMessageType:
        """
        Detect the type of incoming message.
        
        Performance requirement: <10μs
        
        Args:
            raw_message: Raw WebSocket message
            
        Returns:
            WebSocketMessageType enum value
        """
        pass
    
    @abstractmethod
    async def _route_message(self, message_type: WebSocketMessageType, raw_message: Any) -> None:
        """
        Route message to appropriate handler based on type.
        
        Args:
            message_type: Detected message type
            raw_message: Raw WebSocket message
        """
        pass
    
    async def _validate_performance(self, processing_time: float, message_type: WebSocketMessageType) -> None:
        """
        Validate processing time against HFT requirements.
        
        Args:
            processing_time: Processing time in microseconds
            message_type: Type of message processed
        """
        # Define performance targets by message type
        targets = {
            WebSocketMessageType.ORDERBOOK: 50.0,  # 50μs
            WebSocketMessageType.TRADE: 30.0,      # 30μs
            WebSocketMessageType.TICKER: 20.0,     # 20μs
            WebSocketMessageType.PING: 10.0,       # 10μs
        }
        
        target = targets.get(message_type, 100.0)  # Default 100μs
        
        if processing_time > target:
            self.logger.warning("Processing time exceeded target",
                              message_type=message_type.name,
                              processing_time_us=processing_time,
                              target_us=target,
                              exchange=self.exchange_name)
    
    async def _handle_processing_error(self, error: Exception, raw_message: Any) -> None:
        """
        Handle errors during message processing.
        
        Args:
            error: Exception that occurred
            raw_message: Raw message that caused the error
        """
        self.error_count += 1
        
        self.logger.error("Error processing message",
                        error_type=type(error).__name__,
                        error_message=str(error),
                        exchange=self.exchange_name,
                        message_preview=str(raw_message)[:100] if raw_message else "None")
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for monitoring."""
        if not self.parsing_times:
            return {
                "exchange": self.exchange_name,
                "message_count": self.message_count,
                "error_count": self.error_count,
                "avg_processing_time_us": 0,
                "max_processing_time_us": 0,
                "error_rate": 0
            }
        
        return {
            "exchange": self.exchange_name,
            "message_count": self.message_count,
            "error_count": self.error_count,
            "avg_processing_time_us": sum(self.parsing_times) / len(self.parsing_times),
            "max_processing_time_us": max(self.parsing_times),
            "min_processing_time_us": min(self.parsing_times),
            "error_rate": self.error_count / max(1, self.message_count),
            "recent_avg_us": sum(self.parsing_times[-100:]) / min(100, len(self.parsing_times))
        }
```

#### PublicMessageHandler

**File:** `/src/infrastructure/networking/websocket/handlers/public_message_handler.py`

```python
"""
Public Message Handler
Specialized handler for public WebSocket messages (market data).
"""

from typing import Any, Optional, List
from .base_message_handler import BaseMessageHandler
from infrastructure.networking.websocket.mixins import PublicWebSocketMixin
from infrastructure.networking.websocket.message_types import WebSocketMessageType
from exchanges.structs.common import OrderBook, Trade, BookTicker


class PublicMessageHandler(BaseMessageHandler):
    """
    Handler for public market data messages.
    
    Processes:
    - Orderbook updates (bids/asks)
    - Trade feeds (executed trades)  
    - Ticker data (24h stats, best bid/ask)
    - Ping/heartbeat messages
    - Subscription confirmations
    """
    
    def __init__(self, exchange_name: str):
        """Initialize public message handler."""
        super().__init__(exchange_name)
        
        # Callback management
        self._orderbook_callbacks = []
        self._trade_callbacks = []
        self._ticker_callbacks = []
        
        self.logger.info(f"PublicMessageHandler initialized for {exchange_name}")
    
    async def _route_message(self, message_type: WebSocketMessageType, raw_message: Any) -> None:
        """Route public messages to appropriate parsers."""
        
        if message_type == WebSocketMessageType.ORDERBOOK:
            orderbook = await self._parse_orderbook_update(raw_message)
            if orderbook:
                await self._notify_orderbook_callbacks(orderbook)
        
        elif message_type == WebSocketMessageType.TRADE:
            trades = await self._parse_trade_message(raw_message)
            if trades:
                for trade in trades:
                    await self._notify_trade_callbacks(trade)
        
        elif message_type == WebSocketMessageType.TICKER:
            ticker = await self._parse_ticker_update(raw_message)
            if ticker:
                await self._notify_ticker_callbacks(ticker)
        
        elif message_type == WebSocketMessageType.PING:
            await self._handle_ping(raw_message)
        
        elif message_type == WebSocketMessageType.SUBSCRIBE:
            await self._handle_subscription_confirmation(raw_message)
        
        elif message_type == WebSocketMessageType.ERROR:
            await self._handle_exchange_error(raw_message)
        
        else:
            self.logger.warning(f"Unhandled public message type: {message_type}")
    
    # Abstract methods that exchange implementations must provide
    
    async def _parse_orderbook_update(self, raw_message: Any) -> Optional[OrderBook]:
        """
        Parse orderbook message from exchange-specific format.
        
        Performance target: <50μs
        
        Args:
            raw_message: Raw WebSocket message
            
        Returns:
            OrderBook object or None if parsing failed
        """
        raise NotImplementedError("Exchange handler must implement _parse_orderbook_update")
    
    async def _parse_trade_message(self, raw_message: Any) -> Optional[List[Trade]]:
        """
        Parse trade message from exchange-specific format.
        
        Performance target: <30μs
        
        Args:
            raw_message: Raw WebSocket message
            
        Returns:
            List of Trade objects or None if parsing failed
        """
        raise NotImplementedError("Exchange handler must implement _parse_trade_message")
    
    async def _parse_ticker_update(self, raw_message: Any) -> Optional[BookTicker]:
        """
        Parse ticker message from exchange-specific format.
        
        Performance target: <20μs
        
        Args:
            raw_message: Raw WebSocket message
            
        Returns:
            BookTicker object or None if parsing failed
        """
        raise NotImplementedError("Exchange handler must implement _parse_ticker_update")
    
    # Protocol-specific handlers
    
    async def _handle_ping(self, raw_message: Any) -> None:
        """Handle ping messages (exchange-specific implementation)."""
        self.logger.debug("Received ping message")
    
    async def _handle_subscription_confirmation(self, raw_message: Any) -> None:
        """Handle subscription confirmation messages."""
        self.logger.debug("Received subscription confirmation")
    
    async def _handle_exchange_error(self, raw_message: Any) -> None:
        """Handle exchange error messages."""
        self.logger.error(f"Exchange error received: {raw_message}")
    
    # Callback management
    
    def add_orderbook_callback(self, callback: callable) -> None:
        """Add callback for orderbook updates."""
        self._orderbook_callbacks.append(callback)
    
    def add_trade_callback(self, callback: callable) -> None:
        """Add callback for trade updates."""
        self._trade_callbacks.append(callback)
    
    def add_ticker_callback(self, callback: callable) -> None:
        """Add callback for ticker updates."""
        self._ticker_callbacks.append(callback)
    
    async def _notify_orderbook_callbacks(self, orderbook: OrderBook) -> None:
        """Notify all registered orderbook callbacks."""
        for callback in self._orderbook_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(orderbook)
                else:
                    callback(orderbook)
            except Exception as e:
                self.logger.error(f"Error in orderbook callback: {e}")
    
    async def _notify_trade_callbacks(self, trade: Trade) -> None:
        """Notify all registered trade callbacks."""
        for callback in self._trade_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(trade)
                else:
                    callback(trade)
            except Exception as e:
                self.logger.error(f"Error in trade callback: {e}")
    
    async def _notify_ticker_callbacks(self, ticker: BookTicker) -> None:
        """Notify all registered ticker callbacks."""
        for callback in self._ticker_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(ticker)
                else:
                    callback(ticker)
            except Exception as e:
                self.logger.error(f"Error in ticker callback: {e}")
```

### 4. Refactored WebSocketManager

**File:** `/src/infrastructure/networking/websocket/ws_manager.py` (refactored)

```python
"""
WebSocket Manager - Refactored to use BaseWebSocketInterface
Thin wrapper maintaining backward compatibility while delegating to new architecture.
"""

from typing import List, Optional, Callable, Any, Dict
from .base_interface import BaseWebSocketInterface
from .structs import WebSocketManagerConfig, ConnectionState
from config.structs import WebSocketConfig
from infrastructure.logging import get_logger, LoggingTimer
from infrastructure.exceptions.exchange import ExchangeRestError


class WebSocketManager:
    """
    Refactored WebSocket manager using BaseWebSocketInterface.
    
    Maintains backward compatibility while delegating core functionality
    to the new mixin-based architecture.
    """
    
    def __init__(
        self,
        config: WebSocketConfig,
        direct_handler: Any,
        connection_handler: Optional[Callable[[ConnectionState], Any]] = None,
        manager_config: Optional[WebSocketManagerConfig] = None,
        logger=None
    ):
        """
        Initialize WebSocket manager with new architecture.
        
        Args:
            config: WebSocket configuration
            direct_handler: Handler implementing required mixins
            connection_handler: Optional connection state callback
            manager_config: Optional manager configuration
            logger: Optional logger instance
        """
        self.logger = logger or get_logger('ws.manager')
        self.connection_handler = connection_handler
        
        # Create BaseWebSocketInterface instance
        self._base_interface = BaseWebSocketInterface(config, direct_handler)
        
        # Maintain backward compatibility properties
        self.config = config
        self.direct_handler = direct_handler
        self.manager_config = manager_config or WebSocketManagerConfig()
        
        self.logger.info("WebSocketManager V7 initialized with BaseWebSocketInterface",
                        handler_type=type(direct_handler).__name__)
    
    async def initialize(self, symbols: Optional[List] = None,
                         default_channels: Optional[List] = None) -> None:
        """Initialize WebSocket manager (delegates to BaseWebSocketInterface)."""
        try:
            with LoggingTimer(self.logger, "ws_manager_v7_initialization") as timer:
                # Set up symbols and channels on handler
                if symbols and hasattr(self.direct_handler, '_active_symbols'):
                    self.direct_handler._active_symbols.update(symbols)
                
                if default_channels and hasattr(self.direct_handler, '_ws_channels'):
                    self.direct_handler._ws_channels = default_channels
                
                # Delegate to BaseWebSocketInterface
                await self._base_interface.initialize()
            
            self.logger.info("WebSocketManager V7 initialized successfully",
                           initialization_time_ms=timer.elapsed_ms)
            
        except Exception as e:
            self.logger.error("Failed to initialize WebSocketManager V7",
                            error_type=type(e).__name__,
                            error_message=str(e))
            raise
    
    async def subscribe(self, symbols: List) -> None:
        """Subscribe to symbols (delegates to handler)."""
        if not self.is_connected():
            raise ExchangeRestError(503, "WebSocket not connected")
        
        try:
            # Use handler's subscription mixin
            messages = await self.direct_handler.subscribe_to_symbols(
                symbols=symbols, 
                channel_types=getattr(self.direct_handler, '_ws_channels', None)
            )
            
            for message in messages:
                await self._base_interface.send_message(message)
            
            self.logger.info(f"Subscribed to {len(symbols)} symbols")
            
        except Exception as e:
            self.logger.error("Subscription failed",
                            error_type=type(e).__name__,
                            error_message=str(e))
            raise ExchangeRestError(400, f"Subscription failed: {e}")
    
    async def unsubscribe(self, symbols: List) -> None:
        """Unsubscribe from symbols (delegates to handler)."""
        if not self.is_connected():
            return
        
        try:
            messages = await self.direct_handler.unsubscribe_from_symbols(symbols)
            
            for message in messages:
                await self._base_interface.send_message(message)
            
            self.logger.info(f"Unsubscribed from {len(symbols)} symbols")
            
        except Exception as e:
            self.logger.error(f"Unsubscription failed: {e}")
    
    async def send_message(self, message: Dict[str, Any]) -> None:
        """Send message through WebSocket connection."""
        await self._base_interface.send_message(message)
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._base_interface.is_connected()
    
    @property
    def connection_state(self) -> ConnectionState:
        """Get current connection state."""
        return self._base_interface.connection_state
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        base_metrics = {
            'connection_state': self.connection_state.name,
            'handler_type': type(self.direct_handler).__name__,
            'architecture_version': 'v7_base_interface'
        }
        
        # Add handler-specific metrics if available
        if hasattr(self.direct_handler, 'get_performance_metrics'):
            handler_metrics = self.direct_handler.get_performance_metrics()
            base_metrics.update(handler_metrics)
        
        return base_metrics
    
    async def close(self) -> None:
        """Close WebSocket manager."""
        self.logger.info("Closing WebSocketManager V7...")
        
        try:
            await self._base_interface.close()
            self.logger.info("WebSocketManager V7 closed successfully")
            
        except Exception as e:
            self.logger.error("Error closing WebSocketManager V7",
                            error_type=type(e).__name__,
                            error_message=str(e))
```

## Implementation Steps

### Step 1: Create Core Infrastructure

1. **Create BaseWebSocketInterface:**
   ```bash
   touch /src/infrastructure/networking/websocket/base_interface.py
   ```

2. **Enhance ConnectionMixin:**
   ```bash
   # Add MexcConnectionMixin and GateioConnectionMixin to existing file
   ```

3. **Create AuthMixin:**
   ```bash
   touch /src/infrastructure/networking/websocket/mixins/auth_mixin.py
   ```

### Step 2: Create Message Handler Hierarchy

1. **Create handlers directory:**
   ```bash
   mkdir /src/infrastructure/networking/websocket/handlers
   touch /src/infrastructure/networking/websocket/handlers/__init__.py
   ```

2. **Create message handlers:**
   ```bash
   touch /src/infrastructure/networking/websocket/handlers/base_message_handler.py
   touch /src/infrastructure/networking/websocket/handlers/public_message_handler.py
   touch /src/infrastructure/networking/websocket/handlers/private_message_handler.py
   ```

### Step 3: Implement Exchange Handlers

1. **Update MEXC handler to use new architecture:**
   - Inherit from `PublicMessageHandler`
   - Use `MexcConnectionMixin`
   - Maintain existing protobuf optimizations

2. **Update Gate.io handlers:**
   - Implement `GateioAuthMixin` for private handlers
   - Use standard `ConnectionMixin` for connection management
   - Support both spot and futures variants

### Step 4: Refactor WebSocketManager

1. **Update WebSocketManager to delegate to BaseWebSocketInterface**
2. **Maintain backward compatibility**
3. **Update factory functions in utils.py**

## Testing Strategy

### Unit Tests

```python
# Test BaseWebSocketInterface
async def test_base_interface_initialization():
    handler = MockHandler()
    config = WebSocketConfig(url="ws://test")
    
    interface = BaseWebSocketInterface(config, handler)
    await interface.initialize()
    
    assert interface.is_connected() == False
    assert interface.connection_state == ConnectionState.DISCONNECTED

# Test AuthMixin
async def test_gateio_auth_mixin():
    config = ExchangeConfig(
        api_key="test_key",
        secret_key="test_secret"
    )
    
    mixin = GateioAuthMixin(config)
    auth_msg = mixin.create_auth_message()
    
    assert "method" in auth_msg
    assert auth_msg["method"] == "server.sign"

# Test message handlers
async def test_public_message_handler():
    handler = PublicMessageHandler("test_exchange")
    
    # Mock message processing
    orderbook_called = False
    
    def orderbook_callback(orderbook):
        nonlocal orderbook_called
        orderbook_called = True
    
    handler.add_orderbook_callback(orderbook_callback)
    
    # Test would send mock message and verify callback
```

### Integration Tests

```python
async def test_end_to_end_mexc_connection():
    # Test complete MEXC WebSocket flow
    config = ExchangeConfig(name="mexc")
    handler = MexcPublicWebSocketHandler(config)
    manager = WebSocketManager(config, handler)
    
    await manager.initialize()
    
    # Verify connection, subscription, message processing
    assert manager.is_connected()
    
    await manager.close()

async def test_gateio_private_with_auth():
    # Test Gate.io private WebSocket with authentication
    config = ExchangeConfig(
        name="gateio",
        api_key="test_key", 
        secret_key="test_secret"
    )
    
    handler = GateioSpotPrivateWebSocketHandler(config)
    manager = WebSocketManager(config, handler)
    
    await manager.initialize()
    
    # Verify authentication was attempted
    assert handler.requires_authentication()
    
    await manager.close()
```

This implementation guide provides the concrete code structure and examples needed to implement the refactored WebSocket architecture while maintaining HFT performance requirements and ensuring clean separation of concerns.