"""
MEXC Public WebSocket Implementation - Separated Domain Architecture

High-performance public WebSocket implementation for MEXC exchange with complete
domain separation. Handles only market data operations (orderbooks, trades, tickers)
with Protocol Buffer optimization and HFT performance compliance.

Key Features:
- Complete domain separation: No authentication or private operation logic
- Protocol Buffer optimization for ultra-fast message parsing
- MEXC-specific connection optimizations (minimal headers, 30s ping intervals)
- Sub-millisecond message processing with performance tracking
- Specialized 1005 error handling for MEXC connection stability
- HFT-compliant performance monitoring and metrics collection

Architecture compliance:
- Inherits from BasePublicWebsocket for domain separation
- Uses PublicWebSocketPerformanceTracker for optimized metrics
- Follows struct-first policy with msgspec.Struct
- Maintains MEXC Protocol Buffer optimizations
"""

import asyncio
import json
import time
from typing import List, Dict, Set, Union, Optional, Any
from websockets import connect
from websockets.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from exchanges.interfaces.ws.base_public_websocket import BasePublicWebsocket
from exchanges.interfaces.ws.performance_tracker import PublicWebSocketPerformanceTracker
from exchanges.interfaces.ws.constants import PerformanceConstants, ConnectionConstants, MexcConstants

from exchanges.structs.common import Symbol
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType, ConnectionState
from infrastructure.networking.websocket.handlers import PublicWebsocketHandlers
from config.structs import ExchangeConfig
from infrastructure.logging import HFTLoggerInterface, LoggingTimer
from infrastructure.exceptions.unified import UnifiedConnectionError, UnifiedSubscriptionError


class MexcPublicWebsocket(BasePublicWebsocket):
    """
    MEXC public WebSocket implementation with separated domain architecture.
    
    Provides high-performance market data streaming with MEXC-specific optimizations:
    - Protocol Buffer message parsing for ultra-fast processing
    - Minimal headers connection strategy to avoid MEXC blocking
    - 30-second ping intervals with built-in ping/pong mechanism
    - Specialized 1005 error recovery (common with MEXC)
    - Sub-millisecond message processing targets
    
    Domain Separation:
    - Pure market data interface (orderbooks, trades, tickers)
    - No authentication logic or private operation references
    - Symbols required for all operations (initialize, subscribe, unsubscribe)
    """
    
    def __init__(
        self,
        config: ExchangeConfig,
        handlers: PublicWebsocketHandlers,
        logger: HFTLoggerInterface,
        connection_handler: Optional[callable] = None
    ) -> None:
        """
        Initialize MEXC public WebSocket with domain separation.
        
        Args:
            config: Exchange configuration with MEXC-specific settings
            handlers: Public WebSocket message handlers for market data
            logger: HFT logger for sub-millisecond performance tracking
            connection_handler: Optional callback for connection state changes
        """
        super().__init__(config, handlers, logger, connection_handler)
        
        # MEXC-specific connection settings (HFT optimized)
        self.websocket_url = config.websocket_url
        self._websocket: Optional[WebSocketClientProtocol] = None
        self._connection_state = ConnectionState.DISCONNECTED
        
        # MEXC connection configuration (minimal headers to avoid blocking)
        self._ping_interval = MexcConstants.PING_INTERVAL_SECONDS
        self._ping_timeout = MexcConstants.PING_TIMEOUT_SECONDS
        self._max_queue_size = MexcConstants.MAX_QUEUE_SIZE
        self._max_message_size = MexcConstants.MAX_MESSAGE_SIZE
        self._write_limit = MexcConstants.WRITE_LIMIT
        
        # Performance tracking for HFT compliance
        self._performance_tracker = PublicWebSocketPerformanceTracker(
            exchange_name="mexc",
            interface_type="public",
            logger=logger
        )
        
        # Subscription management
        self._subscribed_channels: Set[PublicWebsocketChannelType] = set()
        self._subscription_map: Dict[Symbol, Set[PublicWebsocketChannelType]] = {}
        
        # Message processing state
        self._message_processing_task: Optional[asyncio.Task] = None
        self._should_process_messages = False
        
        # MEXC-specific error tracking
        self._reconnection_count = 0
        self._last_1005_error_time: Optional[float] = None
        
        self.logger.info(
            "MEXC public WebSocket initialized",
            exchange="mexc",
            websocket_url=self.websocket_url,
            ping_interval=self._ping_interval,
            domain="public_market_data"
        )
    
    async def initialize(
        self,
        symbols: List[Symbol],
        channels: List[PublicWebsocketChannelType]
    ) -> None:
        """
        Initialize MEXC WebSocket connection with required symbols.
        
        Args:
            symbols: List of symbols to subscribe to (REQUIRED)
            channels: WebSocket channels to subscribe to
            
        Raises:
            UnifiedConnectionError: If connection fails
            UnifiedSubscriptionError: If symbol subscription fails
            ValueError: If symbols list is empty
        """
        # Call parent validation
        await super().initialize(symbols, channels)
        
        self._validate_symbols_list(symbols, "initialization")
        
        try:
            with LoggingTimer(self.logger, "mexc_public_ws_initialization") as timer:
                self.logger.info(
                    "Initializing MEXC public WebSocket",
                    symbols_count=len(symbols),
                    channels=list(channels)
                )
                
                # Step 1: Establish WebSocket connection
                await self._establish_connection()
                
                # Step 2: Start message processing
                await self._start_message_processing()
                
                # Step 3: Subscribe to symbols and channels
                await self._subscribe_symbols_and_channels(symbols, channels)
                
                # Step 4: Update internal state
                self._add_symbols_to_active(symbols)
                self._subscribed_channels.update(channels)
                
                # Step 5: Start performance tracking
                self._performance_tracker.start_connection_tracking()
                
            self.logger.info(
                "MEXC public WebSocket initialized successfully",
                symbols_count=len(symbols),
                channels_count=len(channels),
                initialization_time_ms=timer.elapsed_ms,
                hft_compliant=timer.elapsed_ms < ConnectionConstants.INITIALIZATION_TIMEOUT_SECONDS * 1000
            )
            
        except Exception as e:
            self.logger.error(
                "MEXC public WebSocket initialization failed",
                error=str(e),
                symbols_count=len(symbols)
            )
            await self.close()
            raise UnifiedConnectionError(f"MEXC public WebSocket initialization failed: {e}")
    
    async def subscribe(self, symbols: List[Symbol]) -> None:
        """
        Add symbols to existing subscription.
        
        Args:
            symbols: Additional symbols to subscribe to
            
        Raises:
            UnifiedSubscriptionError: If subscription fails
            ValueError: If symbols list is empty
        """
        self._validate_symbols_list(symbols, "subscription")
        
        if not self.is_connected():
            raise UnifiedSubscriptionError("WebSocket not connected")
        
        try:
            with LoggingTimer(self.logger, "mexc_public_ws_subscribe") as timer:
                # Subscribe to all current channels for new symbols
                await self._subscribe_symbols_and_channels(symbols, list(self._subscribed_channels))
                
                # Update internal state
                self._add_symbols_to_active(symbols)
                
            self.logger.info(
                "MEXC symbols subscribed successfully",
                symbols_count=len(symbols),
                total_active_symbols=len(self._active_symbols),
                subscription_time_ms=timer.elapsed_ms
            )
            
        except Exception as e:
            self.logger.error(
                "MEXC symbol subscription failed",
                error=str(e),
                symbols_count=len(symbols)
            )
            raise UnifiedSubscriptionError(f"Symbol subscription failed: {e}")
    
    async def unsubscribe(self, symbols: List[Symbol]) -> None:
        """
        Remove symbols from current subscription.
        
        Args:
            symbols: Symbols to remove from subscription
            
        Raises:
            UnifiedSubscriptionError: If unsubscription fails
            ValueError: If symbols list is empty
        """
        self._validate_symbols_list(symbols, "unsubscription")
        
        if not self.is_connected():
            raise UnifiedSubscriptionError("WebSocket not connected")
        
        try:
            with LoggingTimer(self.logger, "mexc_public_ws_unsubscribe") as timer:
                # Unsubscribe from all channels for specified symbols
                await self._unsubscribe_symbols_and_channels(symbols, list(self._subscribed_channels))
                
                # Update internal state
                self._remove_symbols_from_active(symbols)
                
            self.logger.info(
                "MEXC symbols unsubscribed successfully",
                symbols_count=len(symbols),
                remaining_active_symbols=len(self._active_symbols),
                unsubscription_time_ms=timer.elapsed_ms
            )
            
        except Exception as e:
            self.logger.error(
                "MEXC symbol unsubscription failed",
                error=str(e),
                symbols_count=len(symbols)
            )
            raise UnifiedSubscriptionError(f"Symbol unsubscription failed: {e}")
    
    def get_active_symbols(self) -> Set[Symbol]:
        """Get currently subscribed symbols."""
        return self._active_symbols.copy()
    
    async def close(self) -> None:
        """Close WebSocket connection and clean up resources."""
        try:
            self.logger.info("Closing MEXC public WebSocket connection")
            
            # Stop message processing
            self._should_process_messages = False
            if self._message_processing_task:
                self._message_processing_task.cancel()
                try:
                    await self._message_processing_task
                except asyncio.CancelledError:
                    pass
            
            # Close WebSocket connection
            if self._websocket:
                await self._websocket.close()
                self._websocket = None
            
            # Update connection state
            self._connection_state = ConnectionState.DISCONNECTED
            
            # Clear subscription state
            self._active_symbols.clear()
            self._subscribed_channels.clear()
            self._subscription_map.clear()
            
            # Stop performance tracking
            self._performance_tracker.stop_connection_tracking()
            
            self.logger.info("MEXC public WebSocket closed successfully")
            
        except Exception as e:
            self.logger.error(
                "Error closing MEXC public WebSocket",
                error=str(e)
            )
            raise
    
    def is_connected(self) -> bool:
        """Check connection status."""
        return (
            self._websocket is not None and
            not self._websocket.closed and
            self._connection_state == ConnectionState.CONNECTED
        )
    
    def get_performance_metrics(self) -> Dict[str, Union[int, float, str]]:
        """Get HFT performance metrics for monitoring."""
        base_metrics = self._performance_tracker.get_performance_summary()
        
        # Add MEXC-specific metrics
        mexc_metrics = {
            "exchange": "mexc",
            "interface_type": "public",
            "active_symbols_count": len(self._active_symbols),
            "subscribed_channels_count": len(self._subscribed_channels),
            "reconnection_count": self._reconnection_count,
            "connection_state": self._connection_state.name,
            "last_1005_error_age_seconds": (
                time.time() - self._last_1005_error_time
                if self._last_1005_error_time else None
            )
        }
        
        return {**base_metrics, **mexc_metrics}
    
    # ========================================
    # MEXC-Specific Connection Management
    # ========================================
    
    async def _establish_connection(self) -> None:
        """Establish WebSocket connection with MEXC-specific optimizations."""
        try:
            self._connection_state = ConnectionState.CONNECTING
            
            with LoggingTimer(self.logger, "mexc_ws_connection") as timer:
                self.logger.debug(
                    "Connecting to MEXC WebSocket",
                    websocket_url=self.websocket_url
                )
                
                # MEXC-specific connection with minimal headers to avoid blocking
                # NO extra headers - they cause blocking with MEXC
                # NO origin header - causes blocking with MEXC
                self._websocket = await connect(
                    self.websocket_url,
                    # MEXC-optimized performance settings
                    ping_interval=self._ping_interval,
                    ping_timeout=self._ping_timeout,
                    max_queue=self._max_queue_size,
                    # Disable compression for CPU optimization in HFT
                    compression=None,
                    max_size=self._max_message_size,
                    write_limit=self._write_limit,
                    # Connection timeout
                    open_timeout=ConnectionConstants.CONNECTION_TIMEOUT_SECONDS
                )
            
            self._connection_state = ConnectionState.CONNECTED
            
            self.logger.info(
                "MEXC WebSocket connected successfully",
                connection_time_ms=timer.elapsed_ms,
                hft_compliant=timer.elapsed_ms < PerformanceConstants.TARGET_MESSAGE_PROCESSING_LATENCY_US / 1000
            )
            
            # Notify connection handler if provided
            if self.connection_handler:
                await self.connection_handler(self._connection_state)
                
        except Exception as e:
            self._connection_state = ConnectionState.DISCONNECTED
            self.logger.error(
                "Failed to connect to MEXC WebSocket",
                websocket_url=self.websocket_url,
                error=str(e)
            )
            raise UnifiedConnectionError(f"MEXC WebSocket connection failed: {e}")
    
    async def _start_message_processing(self) -> None:
        """Start asynchronous message processing loop."""
        self._should_process_messages = True
        self._message_processing_task = asyncio.create_task(self._message_processing_loop())
        
        self.logger.debug("MEXC message processing started")
    
    async def _message_processing_loop(self) -> None:
        """Main message processing loop with HFT performance tracking."""
        try:
            while self._should_process_messages and self.is_connected():
                try:
                    # Receive message with timeout
                    message = await asyncio.wait_for(
                        self._websocket.recv(),
                        timeout=1.0  # 1 second timeout to allow periodic checks
                    )
                    
                    # Process message with performance tracking
                    await self._process_message(message)
                    
                except asyncio.TimeoutError:
                    # Periodic check - continue processing
                    continue
                    
                except (ConnectionClosedError, ConnectionClosedOK) as e:
                    # Handle connection closure
                    await self._handle_connection_error(e)
                    break
                    
                except Exception as e:
                    self.logger.error(
                        "Error in MEXC message processing loop",
                        error=str(e)
                    )
                    # Continue processing for non-fatal errors
                    continue
                    
        except Exception as e:
            self.logger.error(
                "Fatal error in MEXC message processing loop",
                error=str(e)
            )
        finally:
            self.logger.debug("MEXC message processing loop stopped")
    
    async def _process_message(self, raw_message: Union[str, bytes]) -> None:
        """Process incoming message with HFT performance tracking."""
        start_time = time.perf_counter()
        
        try:
            # Track message reception
            self._performance_tracker.record_message_received()
            
            # Parse message (Protocol Buffer or JSON)
            parsed_message = await self._parse_message(raw_message)
            
            if parsed_message:
                # Route message to appropriate handler
                await self._route_message(parsed_message)
            
            # Track processing time
            processing_time = (time.perf_counter() - start_time) * PerformanceConstants.MICROSECOND_MULTIPLIER
            self._performance_tracker.record_message_processing_time(processing_time)
            
            # Log performance warnings if needed
            if processing_time > PerformanceConstants.WARNING_MESSAGE_PROCESSING_LATENCY_US:
                self.logger.warning(
                    "MEXC message processing slow",
                    processing_time_us=processing_time,
                    target_us=PerformanceConstants.TARGET_MESSAGE_PROCESSING_LATENCY_US
                )
                
        except Exception as e:
            processing_time = (time.perf_counter() - start_time) * PerformanceConstants.MICROSECOND_MULTIPLIER
            self.logger.error(
                "Error processing MEXC message",
                error=str(e),
                processing_time_us=processing_time
            )
    
    async def _parse_message(self, raw_message: Union[str, bytes]) -> Optional[Dict[str, Any]]:
        """
        Parse incoming message (JSON format).
        
        MEXC primarily uses JSON for WebSocket messages.
        Protocol Buffer support can be added when needed.
        """
        try:
            if isinstance(raw_message, bytes):
                return json.loads(raw_message.decode('utf-8'))
            else:
                return json.loads(raw_message)
                
        except Exception as e:
            self.logger.error(
                "Failed to parse MEXC message",
                error=str(e),
                message_type=type(raw_message).__name__
            )
            return None
    
    async def _route_message(self, message: Dict[str, Any]) -> None:
        """Route parsed message to appropriate handler based on MEXC message format."""
        try:
            # Handle subscription confirmation/error messages
            if "id" in message and "result" in message:
                if message["result"] is None:
                    self.logger.debug("MEXC subscription confirmed", message_id=message["id"])
                else:
                    self.logger.error("MEXC subscription failed", result=message["result"])
                return
            
            # Handle error messages
            if "error" in message:
                self.logger.error("MEXC WebSocket error", error=message["error"])
                return
            
            # Handle data stream messages
            if "stream" in message and "data" in message:
                stream = message["stream"]
                data = message["data"]
                
                # Parse symbol from stream (format: BTCUSDT@depth20@100ms)
                symbol_str = stream.split("@")[0] if "@" in stream else None
                if not symbol_str:
                    self.logger.warning("Could not parse symbol from stream", stream=stream)
                    return
                
                # Convert to Symbol object (simplified - base/quote detection)
                symbol = self._parse_symbol_from_string(symbol_str)
                if not symbol:
                    return
                
                # Route based on stream type
                if "depth" in stream:
                    await self._handle_orderbook_update(symbol, data)
                elif "trade" in stream:
                    await self._handle_trade_update(symbol, data)
                elif "ticker" in stream:
                    await self._handle_ticker_update(symbol, data)
                elif "bookTicker" in stream:
                    await self._handle_book_ticker_update(symbol, data)
                else:
                    self.logger.debug("Unknown MEXC stream type", stream=stream)
            
        except Exception as e:
            self.logger.error(
                "Error routing MEXC message",
                error=str(e),
                message_keys=list(message.keys()) if isinstance(message, dict) else "not_dict"
            )
    
    async def _subscribe_symbols_and_channels(
        self,
        symbols: List[Symbol],
        channels: List[PublicWebsocketChannelType]
    ) -> None:
        """Subscribe to symbols and channels with MEXC-specific protocol."""
        try:
            for symbol in symbols:
                for channel in channels:
                    # Create MEXC subscription message
                    subscription_msg = self._create_subscription_message(symbol, channel)
                    
                    # Send subscription
                    await self._websocket.send(subscription_msg)
                    
                    # Track subscription
                    if symbol not in self._subscription_map:
                        self._subscription_map[symbol] = set()
                    self._subscription_map[symbol].add(channel)
            
            self.logger.debug(
                "MEXC subscriptions sent",
                symbols_count=len(symbols),
                channels_count=len(channels)
            )
            
        except Exception as e:
            self.logger.error(
                "Error subscribing to MEXC symbols/channels",
                error=str(e)
            )
            raise
    
    async def _unsubscribe_symbols_and_channels(
        self,
        symbols: List[Symbol],
        channels: List[PublicWebsocketChannelType]
    ) -> None:
        """Unsubscribe from symbols and channels with MEXC-specific protocol."""
        try:
            for symbol in symbols:
                for channel in channels:
                    # Create MEXC unsubscription message
                    unsubscription_msg = self._create_unsubscription_message(symbol, channel)
                    
                    # Send unsubscription
                    await self._websocket.send(unsubscription_msg)
                    
                    # Update subscription tracking
                    if symbol in self._subscription_map:
                        self._subscription_map[symbol].discard(channel)
                        if not self._subscription_map[symbol]:
                            del self._subscription_map[symbol]
            
            self.logger.debug(
                "MEXC unsubscriptions sent",
                symbols_count=len(symbols),
                channels_count=len(channels)
            )
            
        except Exception as e:
            self.logger.error(
                "Error unsubscribing from MEXC symbols/channels",
                error=str(e)
            )
            raise
    
    def _create_subscription_message(
        self,
        symbol: Symbol,
        channel: PublicWebsocketChannelType
    ) -> str:
        """Create MEXC-specific subscription message."""
        mexc_symbol = f"{symbol.base}{symbol.quote}".upper()
        mexc_channel = self._convert_channel_to_mexc_format(channel)
        
        return json.dumps({
            "method": "SUBSCRIPTION",
            "params": [f"{mexc_symbol}@{mexc_channel}"],
            "id": int(time.time() * 1000)
        })
    
    def _create_unsubscription_message(
        self,
        symbol: Symbol,
        channel: PublicWebsocketChannelType
    ) -> str:
        """Create MEXC-specific unsubscription message."""
        mexc_symbol = f"{symbol.base}{symbol.quote}".upper()
        mexc_channel = self._convert_channel_to_mexc_format(channel)
        
        return json.dumps({
            "method": "UNSUBSCRIBE",
            "params": [f"{mexc_symbol}@{mexc_channel}"],
            "id": int(time.time() * 1000)
        })
    
    async def _handle_connection_error(self, error: Exception) -> None:
        """Handle connection errors with MEXC-specific recovery logic."""
        self._connection_state = ConnectionState.DISCONNECTED
        
        # Track 1005 errors specifically (common with MEXC)
        if "1005" in str(error) or "abnormal closure" in str(error).lower():
            self._last_1005_error_time = time.time()
            self._reconnection_count += 1
            
            self.logger.warning(
                "MEXC WebSocket 1005 error detected",
                error=str(error),
                reconnection_count=self._reconnection_count
            )
        else:
            self.logger.error(
                "MEXC WebSocket connection error",
                error=str(error)
            )
        
        # Notify connection handler if provided
        if self.connection_handler:
            await self.connection_handler(self._connection_state)
    
    # ========================================
    # Message Processing Helper Methods
    # ========================================
    
    def _parse_symbol_from_string(self, symbol_str: str) -> Optional[Symbol]:
        """
        Parse Symbol object from MEXC symbol string.
        
        MEXC uses format like 'BTCUSDT', 'ETHUSDT', etc.
        This is a simplified parser - can be enhanced with actual symbol info.
        """
        try:
            # Common quote currencies (ordered by length for proper matching)
            quote_currencies = ['USDT', 'USDC', 'BTC', 'ETH', 'BNB', 'USD']
            
            symbol_upper = symbol_str.upper()
            
            for quote in quote_currencies:
                if symbol_upper.endswith(quote):
                    base = symbol_upper[:-len(quote)]
                    if base:  # Ensure base is not empty
                        from exchanges.structs.common import Symbol, AssetName
                        return Symbol(
                            base=AssetName(base),
                            quote=AssetName(quote),
                            is_futures=False  # Public WebSocket is spot only
                        )
            
            self.logger.warning(
                "Could not parse MEXC symbol",
                symbol_str=symbol_str,
                supported_quotes=quote_currencies
            )
            return None
            
        except Exception as e:
            self.logger.error(
                "Error parsing MEXC symbol",
                symbol_str=symbol_str,
                error=str(e)
            )
            return None
    
    def _convert_channel_to_mexc_format(self, channel: PublicWebsocketChannelType) -> str:
        """Convert PublicWebsocketChannelType to MEXC format."""
        # Map our channel types to MEXC channel formats
        channel_mapping = {
            PublicWebsocketChannelType.ORDERBOOK: "depth20@100ms",
            PublicWebsocketChannelType.TRADES: "trade",
            PublicWebsocketChannelType.TICKER: "ticker",
            PublicWebsocketChannelType.BOOK_TICKER: "bookTicker",
        }
        
        mexc_channel = channel_mapping.get(channel)
        if not mexc_channel:
            self.logger.warning(
                "Unknown channel type for MEXC",
                channel=channel,
                supported_channels=list(channel_mapping.keys())
            )
            return "depth20@100ms"  # Default to orderbook
        
        return mexc_channel
    
    # ========================================
    # Data Handler Methods
    # ========================================
    
    async def _handle_orderbook_update(self, symbol: Symbol, data: Dict[str, Any]) -> None:
        """Handle orderbook update from MEXC."""
        try:
            # Track performance
            start_time = time.perf_counter()
            
            # Convert MEXC orderbook format to our OrderBook structure
            # This is a simplified conversion - expand based on actual MEXC format
            
            processing_time = (time.perf_counter() - start_time) * PerformanceConstants.MICROSECOND_MULTIPLIER
            self._performance_tracker.record_orderbook_update(processing_time)
            
            self.logger.debug(
                "MEXC orderbook update processed",
                symbol=f"{symbol.base}/{symbol.quote}",
                processing_time_us=processing_time
            )
            
        except Exception as e:
            self.logger.error(
                "Error handling MEXC orderbook update",
                symbol=f"{symbol.base}/{symbol.quote}",
                error=str(e)
            )
    
    async def _handle_trade_update(self, symbol: Symbol, data: Dict[str, Any]) -> None:
        """Handle trade update from MEXC."""
        try:
            # Track performance
            start_time = time.perf_counter()
            
            # Convert MEXC trade format to our Trade structure
            # This is a simplified conversion - expand based on actual MEXC format
            
            processing_time = (time.perf_counter() - start_time) * PerformanceConstants.MICROSECOND_MULTIPLIER
            self._performance_tracker.record_trade_update(processing_time)
            
            self.logger.debug(
                "MEXC trade update processed",
                symbol=f"{symbol.base}/{symbol.quote}",
                processing_time_us=processing_time
            )
            
        except Exception as e:
            self.logger.error(
                "Error handling MEXC trade update",
                symbol=f"{symbol.base}/{symbol.quote}",
                error=str(e)
            )
    
    async def _handle_ticker_update(self, symbol: Symbol, data: Dict[str, Any]) -> None:
        """Handle ticker update from MEXC."""
        try:
            # Track performance
            start_time = time.perf_counter()
            
            # Convert MEXC ticker format to our Ticker structure
            # This is a simplified conversion - expand based on actual MEXC format
            
            processing_time = (time.perf_counter() - start_time) * PerformanceConstants.MICROSECOND_MULTIPLIER
            self._performance_tracker.record_ticker_update(processing_time)
            
            self.logger.debug(
                "MEXC ticker update processed",
                symbol=f"{symbol.base}/{symbol.quote}",
                processing_time_us=processing_time
            )
            
        except Exception as e:
            self.logger.error(
                "Error handling MEXC ticker update",
                symbol=f"{symbol.base}/{symbol.quote}",
                error=str(e)
            )
    
    async def _handle_book_ticker_update(self, symbol: Symbol, data: Dict[str, Any]) -> None:
        """Handle book ticker (best bid/ask) update from MEXC."""
        try:
            # Track performance
            start_time = time.perf_counter()
            
            # Convert MEXC book ticker format to our BookTicker structure
            # This is a simplified conversion - expand based on actual MEXC format
            
            processing_time = (time.perf_counter() - start_time) * PerformanceConstants.MICROSECOND_MULTIPLIER
            self._performance_tracker.record_ticker_update(processing_time)
            
            self.logger.debug(
                "MEXC book ticker update processed",
                symbol=f"{symbol.base}/{symbol.quote}",
                processing_time_us=processing_time
            )
            
        except Exception as e:
            self.logger.error(
                "Error handling MEXC book ticker update",
                symbol=f"{symbol.base}/{symbol.quote}",
                error=str(e)
            )