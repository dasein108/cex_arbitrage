"""
MEXC Consolidated Public WebSocket Interface

Example implementation of the consolidated WebSocket architecture for MEXC public
market data. Shows how to implement exchange-specific functionality using the
new consolidated interface pattern.

Features:
- Direct MEXC WebSocket connection management
- Integrated protobuf and JSON message processing
- Built-in subscription management with MEXC-specific channels
- Automatic reconnection with MEXC-optimized policies
- HFT performance targets: <50μs orderbooks, <30μs trades, <20μs tickers
"""

import time
from typing import Any, Dict, List, Optional
import msgspec

from config.structs import ExchangeConfig
from exchanges.interfaces.ws.consolidated_interfaces import ConsolidatedPublicWebSocketInterface
from infrastructure.networking.websocket.structs import ConnectionContext
from infrastructure.networking.websocket.mixins.connection_mixin import ReconnectionPolicy
from infrastructure.networking.websocket.message_types import WebSocketMessageType
from exchanges.structs.common import Symbol, OrderBook, OrderBookEntry, Trade, BookTicker
from exchanges.structs.enums import Side
from exchanges.integrations.mexc.services.symbol_mapper import MexcSymbol
from exchanges.integrations.mexc.ws.protobuf_parser import MexcProtobufParser


class MexcConsolidatedPublicWebSocket(ConsolidatedPublicWebSocketInterface):
    """
    MEXC public WebSocket interface using consolidated architecture.
    
    Direct implementation without WebSocketManager or strategy layers.
    Provides market data streaming with protobuf optimization and
    HFT-compliant performance.
    
    Performance Specifications:
    - Orderbook updates: <50μs requirement
    - Trade messages: <30μs requirement  
    - Ticker updates: <20μs requirement
    - Connection time: <100ms for HFT compliance
    - Protobuf parsing: 15-25μs improvement over JSON
    """
    
    # MEXC message type detection for protobuf content
    _MEXC_PROTOBUF_TYPES = {
        b'orderbook': WebSocketMessageType.ORDERBOOK,
        b'trade': WebSocketMessageType.TRADE,
        b'ticker': WebSocketMessageType.TICKER,
    }
    
    # MEXC JSON message type detection
    _MEXC_JSON_TYPES = {
        'orderbook': WebSocketMessageType.ORDERBOOK,
        'trade': WebSocketMessageType.TRADE,
        'ticker': WebSocketMessageType.TICKER,
    }
    
    def __init__(self, config: ExchangeConfig, connection_handler=None):
        """
        Initialize MEXC consolidated public WebSocket interface.
        
        Args:
            config: Exchange configuration
            connection_handler: Optional connection state handler
        """
        super().__init__(config=config, connection_handler=connection_handler)
        
        # MEXC-specific initialization
        self.exchange_name = "mexc"
        
        # Performance tracking
        self._protobuf_messages = 0
        self._json_messages = 0
        self._parsing_times = []
        
        self.logger.info("MEXC consolidated public WebSocket initialized",
                        protobuf_optimization=True,
                        architecture="consolidated")
    
    # Required abstract methods from consolidated base
    
    def create_connection_context(self) -> ConnectionContext:
        """
        Create MEXC-specific connection configuration.
        
        Returns:
            ConnectionContext optimized for MEXC public WebSocket
        """
        return ConnectionContext(
            url="wss://stream.mexc.com/ws",
            headers={
                "User-Agent": "MEXC-Consolidated-Client",
                "Accept": "application/json"
            },
            extra_params={
                "compression": None,
                "ping_interval": 30,
                "ping_timeout": 10,
                "close_timeout": 10
            }
        )
    
    def get_reconnection_policy(self) -> ReconnectionPolicy:
        """
        Get MEXC-optimized reconnection policy.
        
        MEXC has frequent 1005 errors, so we use aggressive reconnection
        with reset on 1005 errors for optimal uptime.
        
        Returns:
            ReconnectionPolicy optimized for MEXC characteristics
        """
        return ReconnectionPolicy(
            max_attempts=15,  # MEXC needs more attempts due to 1005 errors
            initial_delay=0.5,
            backoff_factor=1.5,
            max_delay=30.0,
            reset_on_1005=True  # Reset attempts on MEXC's frequent 1005 errors
        )
    
    def get_channels_for_symbol(self, symbol: Symbol, channel_types: Optional[List[str]] = None) -> List[str]:
        """
        Get MEXC-specific channel names for a symbol.
        
        Args:
            symbol: Trading symbol
            channel_types: List of channel types (orderbook, trades, ticker)
            
        Returns:
            List of MEXC channel names
        """
        mexc_symbol = MexcSymbol.format_for_mexc(symbol)
        channels = []
        
        # Default to orderbook and trades if none specified
        if not channel_types:
            channel_types = ["orderbook", "trades"]
        
        for channel_type in channel_types:
            if channel_type == "orderbook":
                channels.append(f"spot@public.book.{mexc_symbol}")
            elif channel_type == "trades":
                channels.append(f"spot@public.deals.{mexc_symbol}")
            elif channel_type == "ticker":
                channels.append(f"spot@public.ticker.{mexc_symbol}")
        
        return channels
    
    def create_subscription_message(self, action: str, channels: List[str]) -> Dict[str, Any]:
        """
        Create MEXC subscription message.
        
        Args:
            action: "subscribe" or "unsubscribe"
            channels: List of channel names
            
        Returns:
            MEXC subscription message
        """
        # Map action to MEXC format
        mexc_action = "SUBSCRIPTION" if action == "subscribe" else "UNSUBSCRIPTION"
        
        return {
            "method": mexc_action,
            "params": channels,
            "id": int(time.time() * 1000)
        }
    
    # Message processing implementation
    
    async def _handle_message(self, raw_message: Any) -> None:
        """
        Process incoming MEXC WebSocket message with protobuf optimization.
        
        Args:
            raw_message: Raw message from WebSocket (bytes or str)
        """
        processing_start = time.perf_counter()
        
        try:
            # Detect message type and format
            message_type = await self._detect_message_type(raw_message)
            
            if message_type == WebSocketMessageType.ORDERBOOK:
                orderbook = await self._parse_orderbook_update(raw_message)
                if orderbook:
                    await self._on_orderbook_update(orderbook)
                    
            elif message_type == WebSocketMessageType.TRADE:
                trades = await self._parse_trade_message(raw_message)
                if trades:
                    for trade in trades:
                        await self._on_trade_update(trade)
                        
            elif message_type == WebSocketMessageType.TICKER:
                ticker = await self._parse_ticker_update(raw_message)
                if ticker:
                    await self._on_ticker_update(ticker)
                    
            elif message_type == WebSocketMessageType.PING:
                await self._handle_ping(raw_message)
                
            # Track processing performance
            processing_time = (time.perf_counter() - processing_start) * 1_000_000  # μs
            self._parsing_times.append(processing_time)
            
            # Alert if exceeding HFT targets
            if processing_time > 50:  # 50μs threshold for orderbooks
                self.logger.warning("Message processing exceeded HFT target",
                                  processing_time_us=processing_time,
                                  message_type=message_type.value)
            
        except Exception as e:
            self.logger.error("Error processing MEXC message",
                            error_type=type(e).__name__,
                            error_message=str(e))
    
    async def _detect_message_type(self, raw_message: Any) -> WebSocketMessageType:
        """
        Fast message type detection for MEXC messages.
        
        Performance target: <10μs
        
        Args:
            raw_message: Raw WebSocket message
            
        Returns:
            WebSocketMessageType enum value
        """
        try:
            # Handle bytes messages (protobuf)
            if isinstance(raw_message, bytes):
                if raw_message and raw_message[0] == 0x0a:  # Protobuf magic byte
                    self._protobuf_messages += 1
                    # Fast protobuf content detection
                    for content, msg_type in self._MEXC_PROTOBUF_TYPES.items():
                        if content in raw_message[:60]:  # Check first 60 bytes
                            return msg_type
                    return WebSocketMessageType.UNKNOWN
            
            # Handle string messages (JSON)
            elif isinstance(raw_message, str):
                self._json_messages += 1
                if raw_message.startswith('{'):
                    # Fast JSON channel detection
                    for keyword, msg_type in self._MEXC_JSON_TYPES.items():
                        if keyword in raw_message[:200]:  # Check first 200 chars
                            return msg_type
                    
                    # Check for ping/pong
                    if 'ping' in raw_message[:50]:
                        return WebSocketMessageType.PING
                    
                    return WebSocketMessageType.UNKNOWN
            
            return WebSocketMessageType.UNKNOWN
            
        except Exception as e:
            self.logger.warning("Error in message type detection", error=str(e))
            return WebSocketMessageType.UNKNOWN
    
    async def _parse_orderbook_update(self, raw_message: Any) -> Optional[OrderBook]:
        """
        Parse MEXC orderbook update with protobuf optimization.
        
        Performance target: <50μs
        
        Args:
            raw_message: Raw WebSocket message
            
        Returns:
            OrderBook object or None if parsing failed
        """
        try:
            # Handle protobuf format (primary path)
            if isinstance(raw_message, bytes):
                return await self._parse_orderbook_protobuf(raw_message)
            
            # Handle JSON format (fallback)
            elif isinstance(raw_message, str):
                return await self._parse_orderbook_json(raw_message)
            
            return None
            
        except Exception as e:
            self.logger.error("Error parsing orderbook update", error=str(e))
            return None
    
    async def _parse_orderbook_protobuf(self, data: bytes) -> Optional[OrderBook]:
        """Parse orderbook from protobuf using existing optimization."""
        try:
            # Extract symbol using existing protobuf parser
            symbol_str = MexcProtobufParser.extract_symbol_from_protobuf(data)
            wrapper = MexcProtobufParser.parse_wrapper_message(data)
            
            if not wrapper.HasField('publicOrderbook'):
                return None
            
            orderbook_data = wrapper.publicOrderbook
            
            # Parse bids and asks directly
            bids = []
            asks = []
            
            # Direct field access for performance
            for bid in orderbook_data.bids:
                bids.append(OrderBookEntry(
                    price=float(bid.price),
                    size=float(bid.quantity)
                ))
            
            for ask in orderbook_data.asks:
                asks.append(OrderBookEntry(
                    price=float(ask.price),
                    size=float(ask.quantity)
                ))
            
            return OrderBook(
                symbol=MexcSymbol.to_symbol(symbol_str) if symbol_str else None,
                bids=bids,
                asks=asks,
                timestamp=int(getattr(orderbook_data, 'timestamp', 0)),
                last_update_id=getattr(orderbook_data, 'lastUpdateId', None)
            )
            
        except Exception as e:
            self.logger.error("Error parsing protobuf orderbook", error=str(e))
            return None
    
    async def _parse_orderbook_json(self, raw_message: str) -> Optional[OrderBook]:
        """Parse orderbook from JSON (fallback path)."""
        try:
            message = msgspec.json.decode(raw_message)
            # Implement JSON parsing logic
            # ... (similar to existing implementations)
            return None  # Placeholder
            
        except Exception as e:
            self.logger.error("Error parsing JSON orderbook", error=str(e))
            return None
    
    async def _parse_trade_message(self, raw_message: Any) -> Optional[List[Trade]]:
        """
        Parse MEXC trade message.
        
        Performance target: <30μs
        """
        # Implementation similar to orderbook parsing
        # ... (protobuf and JSON paths)
        return []  # Placeholder
    
    async def _parse_ticker_update(self, raw_message: Any) -> Optional[BookTicker]:
        """
        Parse MEXC ticker update.
        
        Performance target: <20μs
        """
        # Implementation similar to other parsers
        # ... (protobuf and JSON paths)
        return None  # Placeholder
    
    async def _handle_ping(self, raw_message: Any) -> None:
        """Handle MEXC ping messages."""
        try:
            # MEXC ping handling logic
            self.logger.debug("Received ping message")
            # Send pong if required
        except Exception as e:
            self.logger.warning("Error handling ping", error=str(e))
    
    # Performance monitoring
    
    def get_mexc_performance_stats(self) -> Dict[str, Any]:
        """Get MEXC-specific performance statistics."""
        base_stats = self.get_performance_metrics()
        
        avg_parsing_time = (
            sum(self._parsing_times) / len(self._parsing_times)
            if self._parsing_times else 0
        )
        
        mexc_stats = {
            'protobuf_messages': self._protobuf_messages,
            'json_messages': self._json_messages,
            'avg_parsing_time_us': avg_parsing_time,
            'max_parsing_time_us': max(self._parsing_times) if self._parsing_times else 0,
            'protobuf_ratio': (
                self._protobuf_messages / (self._protobuf_messages + self._json_messages)
                if (self._protobuf_messages + self._json_messages) > 0 else 0
            ),
            'hft_compliance': {
                'orderbook_target_met': avg_parsing_time < 50,
                'trade_target_met': avg_parsing_time < 30,
                'ticker_target_met': avg_parsing_time < 20,
            }
        }
        
        base_stats.update(mexc_stats)
        return base_stats