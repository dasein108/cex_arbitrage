"""
Gate.io Private Futures Exchange Implementation

Comprehensive futures trading implementation with separated domain architecture.
Provides complete position tracking, leverage management, and risk control
for Gate.io futures trading with both USDT and BTC settlement support.

Key Features:
- Complete position tracking with real-time WebSocket updates
- Leverage and margin management 
- Settlement currency support (USDT/BTC)
- HFT-compliant with sub-50ms execution targets
- Constructor injection pattern with dependency injection
- Separated domain architecture (no inheritance from public)

Architecture:
- Direct implementation following CompositePrivateFuturesExchange interface
- Constructor injection of REST and WebSocket clients
- Event-driven position updates via WebSocket binding
- HFT performance compliance with zero caching of real-time data
"""

import time
from typing import Dict, List, Optional, Any
from decimal import Decimal

from exchanges.structs.common import Symbol, Position, SymbolsInfo, Order
from exchanges.structs.types import SettleCurrency, OrderId
from exchanges.interfaces.composite.futures.base_private_futures_composite import CompositePrivateFuturesExchange
from exchanges.interfaces.composite.types import PrivateRestType, PrivateWebsocketType
from infrastructure.networking.websocket.structs import PrivateWebsocketChannelType, WebsocketChannelType
from config.structs import ExchangeConfig
from infrastructure.logging import HFTLoggerInterface

from .rest.gateio_rest_futures_private import GateioPrivateFuturesRestInterface
from .ws.gateio_ws_private_futures import GateioPrivateFuturesWebsocket


class GateioPrivateFuturesExchange(CompositePrivateFuturesExchange):
    """
    Gate.io private futures exchange implementation with separated domain architecture.
    
    Provides futures-specific trading operations:
    - Position management and tracking with real-time updates
    - Leverage and margin control
    - Risk management and position limits
    - Support for both USDT and BTC settlement currencies
    - WebSocket position updates with automatic cache synchronization
    
    HFT Compliance:
    - Sub-50ms position query targets
    - Zero caching of real-time position data (always fresh API calls)
    - Event-driven position updates with microsecond-level processing
    - Constructor injection for optimal performance
    """
    
    def __init__(self,
                 config: ExchangeConfig,
                 rest_client: Optional[PrivateRestType] = None,
                 websocket_client: Optional[PrivateWebsocketType] = None,
                 logger: Optional[HFTLoggerInterface] = None,
                 settle: SettleCurrency = "usdt"):
        """
        Initialize Gate.io private futures exchange with constructor injection.
        
        Args:
            config: Exchange configuration with credentials and endpoints
            rest_client: Optional injected REST client (created if None)
            websocket_client: Optional injected WebSocket client (created if None)  
            logger: Optional injected logger (created if None)
            settle: Settlement currency ('usdt' or 'btc')
        """
        self.settle = settle.lower()
        
        # Validate settlement currency
        if self.settle not in ['usdt', 'btc']:
            raise ValueError(f"Unsupported settlement currency: {settle}. Supported: usdt, btc")
        
        # Create logger if not injected
        if logger is None:
            from infrastructure.logging import get_exchange_logger
            logger = get_exchange_logger('gateio', f'private.futures.{self.settle}')
        
        # Create REST client if not injected
        if rest_client is None:
            rest_client = GateioPrivateFuturesRestInterface(config, logger)
        
        # Create WebSocket client if not injected
        if websocket_client is None:
            websocket_client = GateioPrivateFuturesWebsocket(config, logger)
        
        # Initialize base composite interface with injected dependencies
        super().__init__(config, rest_client, websocket_client, logger)
        
        # Override tag to include settlement currency
        self._tag = f'{config.name}_private_futures_{self.settle}'
        
        # Bind WebSocket position handler if WebSocket client available
        if self.websocket_client:
            # Bind position handler to receive position updates
            self.websocket_client.bind(PrivateWebsocketChannelType.POSITION, self._position_handler)
            
        self.logger.info(f"Initialized {self._tag} with settlement currency: {self.settle}")
    
    # Core position management methods (HFT compliant - no caching)
    
    async def get_positions(self) -> List[Position]:
        """
        Get all current positions via REST API.
        
        HFT COMPLIANT: Always fetches fresh data from API, never cached.
        Target latency: <50ms for complete position retrieval.
        
        Returns:
            List of Position objects for all open positions
        """
        start_time = time.perf_counter()
        
        try:
            positions = await self._rest.get_positions()
            
            # Performance tracking
            latency_ms = (time.perf_counter() - start_time) * 1000
            self.logger.metric("gateio_futures_get_positions_latency_ms", latency_ms,
                              tags={"settle": self.settle})
            
            self.logger.debug(f"Retrieved {len(positions)} futures positions in {latency_ms:.2f}ms")
            return positions
            
        except Exception as e:
            self.logger.error(f"Failed to get positions for {self._tag}: {e}")
            raise
    
    async def get_position(self, symbol: Symbol) -> Optional[Position]:
        """
        Get single position by symbol via REST API.
        
        HFT COMPLIANT: Always fetches fresh data, no caching.
        
        Args:
            symbol: Trading symbol to get position for
            
        Returns:
            Position object if found, None otherwise
        """
        try:
            return await self._rest.get_position(symbol)
        except Exception as e:
            self.logger.error(f"Failed to get position for {symbol} on {self._tag}: {e}")
            return None
    
    async def update_position_margin(self, symbol: Symbol, change: Decimal) -> Position:
        """
        Update position margin for risk management.
        
        Args:
            symbol: Trading symbol
            change: Margin change amount (positive to add, negative to reduce)
            
        Returns:
            Updated Position object
            
        Raises:
            ExchangeRestError: If margin update fails
        """
        try:
            position = await self._rest.update_position_margin(symbol, change)
            
            # Update internal position cache
            self._positions[symbol] = position
            
            self.logger.info(f"Updated margin for {symbol} by {change} on {self._tag}")
            return position
            
        except Exception as e:
            self.logger.error(f"Failed to update margin for {symbol}: {e}")
            raise
    
    async def update_position_leverage(self, symbol: Symbol, leverage: Decimal) -> Position:
        """
        Update position leverage for risk management.
        
        Args:
            symbol: Trading symbol
            leverage: New leverage ratio (e.g., 10 for 10x leverage)
            
        Returns:
            Updated Position object
            
        Raises:
            ExchangeRestError: If leverage update fails
        """
        try:
            position = await self._rest.update_position_leverage(symbol, leverage)
            
            # Update internal position cache
            self._positions[symbol] = position
            
            self.logger.info(f"Updated leverage for {symbol} to {leverage}x on {self._tag}")
            return position
            
        except Exception as e:
            self.logger.error(f"Failed to update leverage for {symbol}: {e}")
            raise
    
    async def close_position(self, symbol: Symbol, quantity: Optional[Decimal] = None) -> List[Order]:
        """
        Close position (partially or completely).
        
        Implementation Note:
        Gate.io doesn't have a direct "close position" endpoint.
        This is implemented by placing a market order in the opposite direction.
        
        Args:
            symbol: Trading symbol
            quantity: Optional quantity to close (None = close all)
            
        Returns:
            List of orders placed to close the position
            
        Raises:
            NotImplementedError: Requires order management integration
        """
        # This requires integration with order management system
        # Implementation would:
        # 1. Get current position
        # 2. Determine close quantity (all or partial)
        # 3. Place opposite side market order
        # 4. Return list of orders
        
        raise NotImplementedError(
            "Position closing requires order management integration. "
            "Use place_order() with opposite side to close positions manually."
        )
    
    # WebSocket subscription management
    
    async def subscribe_position_updates(self, symbols: Optional[List[Symbol]] = None) -> None:
        """
        Subscribe to real-time position updates via WebSocket.
        
        Args:
            symbols: List of symbols to track (None = all positions)
        """
        if not self._websocket:
            self.logger.warning("WebSocket client not available for position subscriptions")
            return
        
        try:
            # Subscribe to futures position updates
            await self._websocket.subscribe(WebsocketChannelType.POSITION, symbols)
            
            self.logger.info(f"Subscribed to position updates for {len(symbols) if symbols else 'all'} symbols")
            
        except Exception as e:
            self.logger.error(f"Failed to subscribe to position updates: {e}")
            raise
    
    async def unsubscribe_position_updates(self, symbols: Optional[List[Symbol]] = None) -> None:
        """
        Unsubscribe from position updates.
        
        Args:
            symbols: List of symbols to unsubscribe (None = all)
        """
        if not self._websocket:
            return
        
        try:
            await self._websocket.unsubscribe(WebsocketChannelType.POSITION, symbols)
            self.logger.info("Unsubscribed from position updates")
        except Exception as e:
            self.logger.error(f"Failed to unsubscribe from position updates: {e}")
    
    # Initialization and lifecycle management
    
    async def initialize(self, symbols_info: Optional[SymbolsInfo] = None, channels: Optional[List[str]] = None) -> None:
        """
        Initialize futures exchange with position tracking.
        
        Loads initial positions and sets up WebSocket subscriptions for real-time updates.
        
        Args:
            symbols_info: Optional symbol information mapping
            channels: Optional list of WebSocket channels to subscribe to
        """
        try:
            # Initialize base composite functionality
            await super().initialize(symbols_info, channels)
            
            # Load initial positions (HFT compliant - fresh data only)
            self.logger.info(f"Loading initial positions for {self._tag}")
            positions = await self.get_positions()
            
            # Update internal position tracking
            for position in positions:
                self._positions[position.symbol] = position
            
            # Subscribe to position updates if WebSocket available
            if self.websocket_client and positions:
                symbols = [pos.symbol for pos in positions]
                await self.subscribe_position_updates(symbols)
            
            self.logger.info(
                f"{self._tag} initialized successfully with {len(positions)} existing positions"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to initialize {self._tag}: {e}")
            raise
    
    async def close(self) -> None:
        """Close futures exchange and cleanup resources."""
        try:
            # Unsubscribe from position updates
            if self._websocket:
                await self.unsubscribe_position_updates()
            
            # Close base composite
            await super().close()
            
            self.logger.info(f"Closed {self._tag} successfully")
            
        except Exception as e:
            self.logger.error(f"Error closing {self._tag}: {e}")
    
    # Position event handlers
    
    async def _position_handler(self, position: Position) -> None:
        """
        Handle position updates from WebSocket.
        
        Updates internal position cache and triggers any registered handlers.
        Overrides base implementation to add futures-specific logging and metrics.
        
        Args:
            position: Updated position object
        """
        # Call base implementation first
        await super()._position_handler(position)
        
        # Add futures-specific metrics and logging
        self.logger.metric("gateio_futures_position_updates_received", 1,
                          tags={"symbol": str(position.symbol), "side": position.side.value, "settle": self.settle})
        
        self.logger.debug(
            f"Position update for {position.symbol}: {position.side.value} {position.size} @ {position.entry_price}",
            symbol=str(position.symbol),
            side=position.side.value,
            size=position.size,
            entry_price=position.entry_price,
            unrealized_pnl=position.unrealized_pnl,
            settle=self.settle
        )
    
    # Performance and diagnostics
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive performance metrics for the futures exchange.
        
        Returns:
            Dictionary with performance statistics and trading metrics
        """
        base_metrics = super().get_performance_stats() if hasattr(super(), 'get_performance_stats') else {}
        
        futures_metrics = {
            "exchange": "gateio",
            "market_type": "futures", 
            "settlement_currency": self.settle,
            "active_positions": len(self._positions),
            "position_symbols": [str(symbol) for symbol in self._positions.keys()],
            "websocket_connected": self._websocket.is_connected if self._websocket else False,
            "tag": self._tag
        }
        
        return {**base_metrics, **futures_metrics}
    
    def __repr__(self) -> str:
        """String representation of the futures exchange."""
        return f"GateioPrivateFuturesExchange(settle={self.settle}, positions={len(self._positions)})"