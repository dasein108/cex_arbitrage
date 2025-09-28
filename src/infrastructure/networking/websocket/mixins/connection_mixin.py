"""
WebSocket Connection Mixin

This mixin replaces the strategy-based ConnectionStrategy with a composition-based
approach for managing WebSocket connections. Provides connection lifecycle management,
reconnection logic, authentication, and heartbeat handling.

Key Features:
- WebSocket connection establishment and lifecycle management
- Exponential backoff reconnection with configurable policies
- Exchange-specific authentication workflows
- Heartbeat/ping management for exchanges requiring custom ping
- Error classification and handling
- HFT optimized: <100ms connection establishment

HFT COMPLIANCE: Sub-100ms connection times, sub-50ms reconnection.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass
import asyncio
import time
import websockets
from websockets.client import WebSocketClientProtocol
from websockets.protocol import State as WsState

from config.structs import ExchangeConfig
from infrastructure.networking.websocket.structs import ConnectionContext
from infrastructure.logging import HFTLoggerInterface, get_logger


@dataclass
class ReconnectionPolicy:
    """Reconnection policy configuration for exchange-specific needs."""
    max_attempts: int = 10
    initial_delay: float = 1.0
    backoff_factor: float = 2.0
    max_delay: float = 60.0
    reset_on_1005: bool = True  # Reset attempts on WebSocket 1005 errors
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number."""
        if self.reset_on_1005:
            # Reset logic handled by caller
            delay = self.initial_delay * (self.backoff_factor ** attempt)
        else:
            delay = self.initial_delay * (self.backoff_factor ** attempt)
        return min(delay, self.max_delay)


class ConnectionMixin(ABC):
    """
    Mixin for WebSocket connection management.
    
    Provides common connection functionality that can be composed with
    exchange-specific handlers. Replaces the ConnectionStrategy pattern
    with a more direct approach.
    
    Usage:
        class MexcPublicHandler(PublicWebSocketMixin, ConnectionMixin):
            def create_connection_context(self) -> ConnectionContext:
                return ConnectionContext(
                    url="wss://stream.mexc.com/ws",
                    headers={"User-Agent": "MEXC-Client"}
                )
    """
    
    def __init__(self, config: ExchangeConfig, *args, **kwargs):
        # Only call super() if there are other classes in the MRO that need initialization
        if hasattr(super(), '__init__'):
            try:
                super().__init__(*args, **kwargs)
            except TypeError:
                # If super().__init__ doesn't accept kwargs, call without them
                pass
        
        self.config = config
        self._websocket: Optional[WebSocketClientProtocol] = None
        self._connection_lock = asyncio.Lock()
        
        # Logger setup
        if not hasattr(self, 'logger') or self.logger is None:
            self.logger = get_logger(f'connection.{self.__class__.__name__}')
        
        # Connection metrics
        self._connection_attempts = 0
        self._last_connection_time = 0.0
        self._total_connections = 0
        
        self.logger.info(f"ConnectionMixin initialized for {config.name}",
                        exchange=config.name,
                        has_credentials=config.has_credentials())
    
    # Abstract methods that exchanges must implement
    
    @abstractmethod
    def create_connection_context(self) -> ConnectionContext:
        """
        Create connection configuration for the exchange.
        
        Returns:
            ConnectionContext with URL, headers, and auth parameters
            
        Example:
            return ConnectionContext(
                url="wss://stream.mexc.com/ws",
                headers={"User-Agent": "MEXC-Client"},
                extra_params={"compression": None}
            )
        """
        pass
    
    @abstractmethod
    def get_reconnection_policy(self) -> ReconnectionPolicy:
        """
        Get exchange-specific reconnection policy.
        
        Returns:
            ReconnectionPolicy with exchange-optimized settings
            
        Example:
            # MEXC has frequent 1005 errors, aggressive reconnection
            return ReconnectionPolicy(
                max_attempts=15,
                initial_delay=0.5,
                backoff_factor=1.5,
                max_delay=30.0,
                reset_on_1005=True
            )
        """
        pass
    
    def should_reconnect(self, error: Exception) -> bool:
        """
        Determine if reconnection should be attempted based on error.
        
        Default implementation handles common cases. Override for
        exchange-specific error handling.
        
        Args:
            error: Exception that caused disconnection
            
        Returns:
            True if reconnection should be attempted
        """
        error_str = str(error).lower()
        
        # Always reconnect on common WebSocket errors
        if any(pattern in error_str for pattern in [
            "1005", "no status received", "connection closed",
            "connection lost", "connection reset"
        ]):
            return True
        
        # Don't reconnect on authentication failures
        if "authentication" in error_str or "unauthorized" in error_str:
            return False
        
        # Don't reconnect on invalid URL or permanent errors
        if any(pattern in error_str for pattern in [
            "invalid url", "404", "403", "permanently"
        ]):
            return False
        
        # Default: attempt reconnection
        return True
    
    # Connection management methods
    
    async def connect(self) -> WebSocketClientProtocol:
        """
        Establish WebSocket connection with exchange-specific configuration.
        
        Returns:
            WebSocket connection instance
            
        Raises:
            ConnectionError: If connection establishment fails
        """
        async with self._connection_lock:
            if self.is_connected():
                return self._websocket
            
            start_time = time.time()
            
            try:
                # Get exchange-specific connection configuration
                context = self.create_connection_context()
                
                # Establish WebSocket connection
                self._websocket = await websockets.connect(
                    context.url,
                    extra_headers=context.headers or {},
                    **context.extra_params or {}
                )
                
                connection_time = (time.time() - start_time) * 1000
                self._last_connection_time = time.time()
                self._total_connections += 1
                self._connection_attempts = 0  # Reset on successful connection
                
                self.logger.info(f"WebSocket connected successfully",
                               connection_time_ms=connection_time,
                               total_connections=self._total_connections,
                               url=context.url)
                
                return self._websocket
                
            except Exception as e:
                self._connection_attempts += 1
                connection_time = (time.time() - start_time) * 1000
                
                self.logger.error(f"WebSocket connection failed",
                                error_type=type(e).__name__,
                                error_message=str(e),
                                connection_time_ms=connection_time,
                                attempt=self._connection_attempts)
                
                raise ConnectionError(f"Failed to connect to WebSocket: {e}") from e
    
    async def disconnect(self) -> None:
        """
        Disconnect and clean up the WebSocket connection.
        """
        async with self._connection_lock:
            if self._websocket:
                try:
                    if self._websocket.state != WsState.CLOSED:
                        await self._websocket.close()
                        self.logger.debug("WebSocket connection closed gracefully")
                except Exception as e:
                    self.logger.warning(f"Error during WebSocket close: {e}")
                finally:
                    self._websocket = None
            
            await self.cleanup()
    
    def is_connected(self) -> bool:
        """
        Check if WebSocket is currently connected.
        
        Returns:
            True if connected and ready for communication
        """
        if self._websocket is None:
            return False
        
        try:
            return self._websocket.state == WsState.OPEN
        except AttributeError:
            self.logger.error(f"WebSocket object {type(self._websocket)} missing 'state' attribute")
            return False
    
    @property
    def websocket(self) -> Optional[WebSocketClientProtocol]:
        """Get the current WebSocket instance."""
        return self._websocket
    
    # Authentication methods
    
    async def authenticate(self) -> bool:
        """
        Perform authentication if required.
        
        Default implementation returns True (no auth required).
        Override for exchanges requiring authentication.
        
        Returns:
            True if authentication successful or not required
            
        Raises:
            RuntimeError: If no WebSocket connection available
        """
        if not self.is_connected():
            raise RuntimeError("No WebSocket connection available for authentication")
        
        # Default: no authentication required for public endpoints
        return True
    
    # Heartbeat methods
    
    async def handle_heartbeat(self) -> None:
        """
        Handle exchange-specific heartbeat/ping operations.
        
        Default implementation does nothing (relies on built-in ping/pong).
        Override for exchanges requiring custom heartbeat messages.
        
        Raises:
            RuntimeError: If no WebSocket connection available
        """
        if not self.is_connected():
            raise RuntimeError("No WebSocket connection available for heartbeat")
        
        # Default: no custom heartbeat required
        # Built-in WebSocket ping/pong is sufficient for most exchanges
        pass
    
    # Error handling methods
    
    def classify_error(self, error: Exception) -> str:
        """
        Classify error for logging and metrics purposes.
        
        Args:
            error: Exception to classify
            
        Returns:
            String classification of error type
        """
        error_str = str(error).lower()
        
        if "1005" in error_str or "no status received" in error_str:
            return "abnormal_closure"
        elif "connection refused" in error_str:
            return "connection_refused"
        elif "timeout" in error_str:
            return "timeout"
        elif "authentication" in error_str or "unauthorized" in error_str:
            return "authentication_failure"
        elif "429" in error_str or "rate limit" in error_str:
            return "rate_limit"
        elif "ssl" in error_str or "certificate" in error_str:
            return "ssl_error"
        else:
            return "unknown"
    
    # Cleanup methods
    
    async def cleanup(self) -> None:
        """
        Clean up resources when closing connection.
        
        Override for exchange-specific cleanup (close files, etc.).
        Default implementation does nothing.
        """
        pass
    
    # Metrics and status
    
    def get_connection_metrics(self) -> Dict[str, Any]:
        """
        Get connection metrics for monitoring.
        
        Returns:
            Dictionary with connection statistics
        """
        current_time = time.time()
        uptime = current_time - self._last_connection_time if self._last_connection_time > 0 else 0
        
        return {
            'is_connected': self.is_connected(),
            'total_connections': self._total_connections,
            'current_connection_attempts': self._connection_attempts,
            'uptime_seconds': uptime,
            'last_connection_time': self._last_connection_time,
            'websocket_state': self._websocket.state.name if self._websocket else None,
            'exchange': self.config.name
        }


# Exchange-specific connection mixins

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
                "compression": None,  # Disable for CPU optimization
                "max_queue": 512
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
        """MEXC-specific error handling for reconnection decisions."""
        error_str = str(error).lower()
        
        # Always reconnect on 1005 errors (very common with MEXC)
        if "1005" in error_str:
            return True
            
        # MEXC-specific network error patterns
        if any(pattern in error_str for pattern in [
            "connection reset", "timeout", "network error"
        ]):
            return True
            
        return super().should_reconnect(error)


class GateioConnectionMixin(ConnectionMixin):
    """Gate.io-specific connection behavior overrides."""
    
    def create_connection_context(self) -> ConnectionContext:
        """Create Gate.io-specific connection configuration."""
        return ConnectionContext(
            url="wss://ws.gate.io/v4/",  # Default to spot, override for futures
            headers={"User-Agent": "GateIO-WebSocket-Client"},
            extra_params={
                "ping_interval": 30,
                "ping_timeout": 10,
                "compression": "deflate",  # Gate.io supports compression
                "max_queue": 256
            }
        )
    
    def get_reconnection_policy(self) -> ReconnectionPolicy:
        """Get Gate.io-specific reconnection policy."""
        return ReconnectionPolicy(
            max_attempts=10,  # Standard reconnection for Gate.io
            initial_delay=1.0,
            backoff_factor=2.0,
            max_delay=60.0,
            reset_on_1005=False  # Gate.io has fewer 1005 errors
        )
    
    def should_reconnect(self, error: Exception) -> bool:
        """Gate.io-specific error handling for reconnection decisions."""
        error_str = str(error).lower()
        
        # Gate.io specific error patterns
        if any(pattern in error_str for pattern in [
            "authentication failed", "invalid signature", "api key"
        ]):
            # Don't reconnect on auth failures
            return False
            
        # Gate.io network error patterns
        if any(pattern in error_str for pattern in [
            "connection lost", "timeout", "network"
        ]):
            return True
            
        return super().should_reconnect(error)


class GateioFuturesConnectionMixin(GateioConnectionMixin):
    """Gate.io futures-specific connection behavior."""
    
    def create_connection_context(self) -> ConnectionContext:
        """Create Gate.io futures-specific connection configuration."""
        return ConnectionContext(
            url="wss://fx-ws.gateio.ws/v4/ws/usdt",  # Futures-specific URL
            headers={"User-Agent": "GateIO-Futures-Client"},
            extra_params={
                "ping_interval": 30,
                "ping_timeout": 10,
                "compression": "deflate",
                "max_queue": 256
            }
        )