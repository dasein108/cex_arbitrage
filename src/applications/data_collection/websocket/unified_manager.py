"""
Unified WebSocket Manager - Simplified Implementation

Manages WebSocket connections to multiple exchanges with minimal complexity.
Focuses on connection management and message routing without caching responsibilities.
"""

import asyncio
import time
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass

from exchanges.structs import Symbol, BookTicker, Trade, ExchangeEnum
from exchanges.transport_factory import create_websocket_client, PublicWebsocketHandlers
from config.config_manager import get_exchange_config
from infrastructure.logging import get_logger, LoggingTimer
from applications.data_collection.consts import WEBSOCKET_CHANNELS


@dataclass
class ConnectionState:
    """Simple connection state tracking."""
    exchange: ExchangeEnum
    connected: bool = False
    last_message_time: float = 0
    message_count: int = 0
    error_count: int = 0


class UnifiedWebSocketManager:
    """
    Simplified WebSocket manager for multiple exchanges.
    
    Responsibilities:
    - Connection management (initialize, maintain, close)
    - Message routing to handlers
    - Basic health monitoring
    - Symbol subscription management
    """

    def __init__(self, exchanges: List[ExchangeEnum], handlers: Optional[PublicWebsocketHandlers] = None):
        """Initialize WebSocket manager."""
        self.exchanges = exchanges
        self.handlers = handlers or PublicWebsocketHandlers()
        self.logger = get_logger('data_collection.websocket_manager')

        # Connection management
        self._exchange_clients: Dict[ExchangeEnum, Any] = {}
        self._connections: Dict[ExchangeEnum, ConnectionState] = {}
        self._active_symbols: Dict[ExchangeEnum, set] = {}

        # Performance tracking
        self._total_messages = 0
        self._start_time = time.time()

        self.logger.info("UnifiedWebSocketManager initialized", 
                        exchanges=[e.value for e in exchanges])

    async def initialize(self, symbols: List[Symbol]) -> None:
        """Initialize WebSocket connections for all exchanges."""
        try:
            self.logger.info(f"Initializing WebSocket connections for {len(symbols)} symbols")

            for exchange in self.exchanges:
                await self._initialize_exchange(exchange, symbols)

            self.logger.info("All WebSocket connections initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize WebSocket connections: {e}")
            raise

    async def _initialize_exchange(self, exchange: ExchangeEnum, symbols: List[Symbol]) -> None:
        """Initialize WebSocket client for specific exchange."""
        try:
            # Create connection state
            self._connections[exchange] = ConnectionState(exchange=exchange)
            self._active_symbols[exchange] = set()

            # Get exchange configuration
            config = get_exchange_config(exchange.value)

            # Create handlers that route to our main handlers
            exchange_handlers = PublicWebsocketHandlers(
                book_ticker_handler=lambda ticker: self._handle_book_ticker(exchange, ticker),
                trades_handler=lambda trade: self._handle_trade(exchange, trade)
            )

            # Create WebSocket client
            with LoggingTimer(self.logger, "websocket_client_creation") as timer:
                client = create_websocket_client(
                    exchange=exchange,
                    config=config,
                    is_private=False,
                    handlers=exchange_handlers
                )

            self._exchange_clients[exchange] = client

            # Initialize connection
            with LoggingTimer(self.logger, "websocket_connection") as timer:
                await client.initialize(symbols, WEBSOCKET_CHANNELS)
                self._active_symbols[exchange].update(symbols)
                self._connections[exchange].connected = True

            self.logger.info("Exchange WebSocket initialized",
                           exchange=exchange.value,
                           symbols_count=len(symbols),
                           initialization_time_ms=timer.elapsed_ms)

        except Exception as e:
            self.logger.error("Failed to initialize exchange WebSocket",
                            exchange=exchange.value,
                            error=str(e))
            self._connections[exchange].connected = False
            raise

    async def _handle_book_ticker(self, exchange: ExchangeEnum, book_ticker: BookTicker) -> None:
        """Handle book ticker update from any exchange."""
        try:
            # Update connection stats
            connection = self._connections[exchange]
            connection.last_message_time = time.time()
            connection.message_count += 1
            self._total_messages += 1

            # Extract symbol from book ticker
            symbol = getattr(book_ticker, 'symbol', None)
            if symbol is None:
                self.logger.warning("Book ticker received without symbol information")
                return

            # Route to external handler
            if self.handlers.book_ticker_handler:
                await self.handlers.book_ticker_handler(exchange, symbol, book_ticker)

        except Exception as e:
            self.logger.error("Error handling book ticker update",
                            exchange=exchange.value,
                            error=str(e))
            self._connections[exchange].error_count += 1

    async def _handle_trade(self, exchange: ExchangeEnum, trade: Trade) -> None:
        """Handle trade update from any exchange."""
        try:
            # Update connection stats
            connection = self._connections[exchange]
            connection.last_message_time = time.time()
            connection.message_count += 1
            self._total_messages += 1

            # Extract symbol from trade
            symbol = getattr(trade, 'symbol', None)
            if symbol is None:
                self.logger.warning("Trade received without symbol information")
                return

            # Route to external handler
            if self.handlers.trades_handler:
                await self.handlers.trades_handler(exchange, symbol, trade)

        except Exception as e:
            self.logger.error("Error handling trade update",
                            exchange=exchange.value,
                            error=str(e))
            self._connections[exchange].error_count += 1

    async def add_symbols(self, symbols: List[Symbol]) -> None:
        """Add symbols to all active exchanges."""
        if not symbols:
            return

        try:
            for exchange, client in self._exchange_clients.items():
                if self._connections[exchange].connected:
                    await client.add_symbols(symbols)
                    self._active_symbols[exchange].update(symbols)

            self.logger.info(f"Added {len(symbols)} symbols to all exchanges")

        except Exception as e:
            self.logger.error(f"Failed to add symbols: {e}")
            raise

    def get_connection_status(self) -> Dict[str, Dict[str, Any]]:
        """Get current connection status for all exchanges."""
        status = {}
        current_time = time.time()
        
        for exchange, connection in self._connections.items():
            status[exchange.value] = {
                "connected": connection.connected,
                "symbols": len(self._active_symbols.get(exchange, set())),
                "messages_received": connection.message_count,
                "errors": connection.error_count,
                "last_message_ago_seconds": current_time - connection.last_message_time if connection.last_message_time else 0
            }
        
        return status

    def get_statistics(self) -> Dict[str, Any]:
        """Get performance statistics."""
        uptime = time.time() - self._start_time
        messages_per_second = self._total_messages / uptime if uptime > 0 else 0

        return {
            "total_messages": self._total_messages,
            "uptime_seconds": uptime,
            "messages_per_second": messages_per_second,
            "connected_exchanges": sum(1 for conn in self._connections.values() if conn.connected),
            "total_exchanges": len(self._connections)
        }

    async def close(self) -> None:
        """Close all WebSocket connections."""
        try:
            self.logger.info("Closing all WebSocket connections")

            for exchange, client in self._exchange_clients.items():
                try:
                    await client.close()
                    self._connections[exchange].connected = False
                except Exception as e:
                    self.logger.error(f"Error closing {exchange.value} connection: {e}")

            self._exchange_clients.clear()
            self._active_symbols.clear()

            self.logger.info("All WebSocket connections closed")

        except Exception as e:
            self.logger.error(f"Error during WebSocket cleanup: {e}")