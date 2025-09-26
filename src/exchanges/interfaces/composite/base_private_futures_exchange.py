"""
Private futures exchange interface for futures trading operations.

This interface extends the composite private interface with futures-specific
trading functionality like leverage management, position control, and
futures-specific order types.
"""

from abc import abstractmethod
from typing import Dict, List, Optional, Any
from decimal import Decimal

from exchanges.structs.common import Symbol, Order, Position
from .base_private_exchange import CompositePrivateExchange
from infrastructure.logging import HFTLoggerInterface
from exchanges.interfaces.base_events import PositionUpdateEvent


class CompositePrivateFuturesExchange(CompositePrivateExchange):
    """
    Base interface for private futures exchange operations.
    
    Combines private trading functionality with futures-specific features:
    - Leverage management
    - Futures position control (long/short)
    - Margin management
    - Futures-specific order types
    - Risk management features
    
    This interface requires authentication and provides full futures
    trading functionality.
    """

    def __init__(self, config, logger: Optional[HFTLoggerInterface] = None):
        """
        Initialize private futures exchange interface.
        
        Args:
            config: Exchange configuration with API credentials
            logger: Optional injected HFT logger (auto-created if not provided)
        """
        super().__init__(config, logger=logger)
        

        # Futures-specific private data (using generic Dict structures for now)
        self._leverage_settings: Dict[Symbol, Dict] = {}
        self._margin_info: Dict[Symbol, Dict] = {}
        self._futures_positions: Dict[Symbol, Position] = {}
        
        # Alias for backward compatibility - map to futures_positions
        self._positions: Dict[Symbol, Position] = self._futures_positions

    # Abstract properties for futures private data

    @property
    @abstractmethod
    def leverage_settings(self) -> Dict[Symbol, Dict]:
        """
        Get current leverage settings for all symbols.
        
        Returns:
            Dictionary mapping symbols to leverage information
        """
        pass

    @property
    @abstractmethod
    def margin_info(self) -> Dict[Symbol, Dict]:
        """
        Get current margin information for all symbols.
        
        Returns:
            Dictionary mapping symbols to margin information
        """
        pass

    @property
    @abstractmethod
    def futures_positions(self) -> Dict[Symbol, Position]:
        """
        Get current futures positions.
        
        Returns:
            Dictionary mapping symbols to position information
        """
        pass

    @property
    def positions(self) -> Dict[Symbol, Position]:
        """
        Get current positions (alias for futures_positions).
        
        Returns:
            Dictionary mapping symbols to position information
        """
        return self._futures_positions.copy()

    # Abstract futures trading operations

    @abstractmethod
    async def set_leverage(self, symbol: Symbol, leverage: int) -> bool:
        """
        Set leverage for a symbol.
        
        Args:
            symbol: Trading symbol
            leverage: Leverage multiplier (e.g., 10 for 10x)
            
        Returns:
            True if leverage set successfully
            
        Raises:
            ExchangeError: If leverage setting fails
        """
        pass

    @abstractmethod
    async def get_leverage(self, symbol: Symbol) -> Dict:
        """
        Get current leverage for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Current leverage information
        """
        pass

    @abstractmethod
    async def place_futures_order(
        self,
        symbol: Symbol,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        reduce_only: bool = False,
        close_position: bool = False,
        **kwargs
    ) -> Order:
        """
        Place a futures order with advanced options.
        
        Args:
            symbol: Trading symbol
            side: Order side ('buy' or 'sell')
            order_type: Order type ('limit', 'market', 'stop', 'take_profit')
            quantity: Order quantity
            price: Order price (for limit orders)
            reduce_only: Whether this order can only reduce position size
            close_position: Whether this order should close the entire position
            **kwargs: Exchange-specific parameters
            
        Returns:
            Order object with order details
            
        Raises:
            ExchangeError: If order placement fails
        """
        pass

    @abstractmethod
    async def close_position(
        self, 
        symbol: Symbol, 
        quantity: Optional[Decimal] = None
    ) -> List[Order]:
        """
        Close position (partially or completely).
        
        Args:
            symbol: Trading symbol
            quantity: Quantity to close (None for entire position)
            
        Returns:
            List of orders created to close the position
            
        Raises:
            ExchangeError: If position closing fails
        """
        pass

    @abstractmethod
    async def set_margin_mode(self, symbol: Symbol, margin_mode: str) -> bool:
        """
        Set margin mode for a symbol (isolated/cross).
        
        Args:
            symbol: Trading symbol
            margin_mode: Margin mode ('isolated' or 'cross')
            
        Returns:
            True if margin mode set successfully
            
        Raises:
            ExchangeError: If margin mode setting fails
        """
        pass

    @abstractmethod
    async def add_margin(self, symbol: Symbol, amount: Decimal) -> bool:
        """
        Add margin to a position.
        
        Args:
            symbol: Trading symbol
            amount: Amount of margin to add
            
        Returns:
            True if margin added successfully
            
        Raises:
            ExchangeError: If margin addition fails
        """
        pass

    @abstractmethod
    async def reduce_margin(self, symbol: Symbol, amount: Decimal) -> bool:
        """
        Reduce margin from a position.
        
        Args:
            symbol: Trading symbol
            amount: Amount of margin to reduce
            
        Returns:
            True if margin reduced successfully
            
        Raises:
            ExchangeError: If margin reduction fails
        """
        pass

    # Abstract futures data loading

    @abstractmethod
    async def _load_leverage_settings(self) -> None:
        """Load leverage settings from REST API."""
        pass

    @abstractmethod
    async def _load_margin_info(self) -> None:
        """Load margin information from REST API."""
        pass

    @abstractmethod
    async def _load_futures_positions(self) -> None:
        """Load futures positions from REST API."""
        pass

    async def _load_positions(self) -> None:
        """
        Load positions from REST API (for margin/futures).
        MOVED FROM: base_private_exchange.py - futures-specific functionality
        """
        if not self._private_rest:
            return
            
        try:
            from infrastructure.utils.logging_timer import LoggingTimer
            
            with LoggingTimer(self.logger, "load_positions") as timer:
                positions_data = await self._private_rest.get_positions()
                
                # Update internal state
                for symbol, position in positions_data.items():
                    self._futures_positions[symbol] = position
                    
            self.logger.info("Positions loaded successfully",
                            position_count=len(positions_data),
                            load_time_ms=timer.elapsed_ms)
                            
        except Exception as e:
            self.logger.error("Failed to load positions", error=str(e))
            from exchanges.errors import BaseExchangeError
            raise BaseExchangeError(f"Positions loading failed: {e}") from e

    # Enhanced initialization for futures

    async def initialize(self, symbols: List[Symbol] = None) -> None:
        """
        Initialize futures exchange with symbols and futures-specific data.
        
        Args:
            symbols: Optional list of symbols to track
        """
        # Initialize composite private functionality
        await super().initialize(symbols)

        try:
            # Load futures-specific private data
            await self._load_leverage_settings()
            await self._load_margin_info()
            await self._load_futures_positions()

            self.logger.info(f"{self._tag} futures private data initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize futures private data for {self._tag}: {e}")
            raise

    # Enhanced data refresh for reconnections

    async def _refresh_exchange_data(self) -> None:
        """
        Refresh all exchange data after reconnection.
        
        Refreshes standard private data plus futures-specific data.
        """
        # Refresh composite private data
        await super()._refresh_exchange_data()

        try:
            # Refresh futures-specific data
            await self._load_leverage_settings()
            await self._load_margin_info()
            await self._load_futures_positions()

            self.logger.info(f"{self._tag} futures private data refreshed")

        except Exception as e:
            self.logger.error(f"Failed to refresh futures private data for {self._tag}: {e}")
            raise

    # Futures data update methods

    def _update_leverage_setting(self, symbol: Symbol, leverage: Dict) -> None:
        """
        Update internal leverage setting state.
        
        Args:
            symbol: Symbol that was updated
            leverage: New leverage information
        """
        self._leverage_settings[symbol] = leverage
        self.logger.debug(f"Updated leverage for {symbol}: {leverage}")

    def _update_margin_info(self, symbol: Symbol, margin_info: Dict) -> None:
        """
        Update internal margin information state.
        
        Args:
            symbol: Symbol that was updated
            margin_info: New margin information
        """
        self._margin_info[symbol] = margin_info
        self.logger.debug(f"Updated margin info for {symbol}: {margin_info}")

    def _update_futures_position(self, position: Position) -> None:
        """
        Update internal futures position state.
        
        Args:
            position: Updated position information
        """
        self._futures_positions[position.symbol] = position
        self.logger.debug(f"Updated futures position for {position.symbol}: {position}")

    def _update_position(self, position: Position) -> None:
        """
        Update internal position state (alias for _update_futures_position).
        MOVED FROM: base_private_exchange.py - futures-specific functionality
        
        Args:
            position: Updated position information
        """
        self._update_futures_position(position)

    async def _handle_position_event(self, event: PositionUpdateEvent) -> None:
        """
        Handle position update events from private WebSocket.
        MOVED FROM: base_private_exchange.py - futures-specific functionality
        """
        try:
            # Update internal position state
            self._update_futures_position(event.position)
            
            self._track_operation("position_update")
            
        except Exception as e:
            self.logger.error("Error handling position event", 
                             symbol=event.symbol, error=str(e))

    # Override WebSocket initialization to include position handler
    
    async def _initialize_private_websocket(self) -> None:
        """
        Initialize private WebSocket with constructor injection including position handler.
        OVERRIDDEN: To include position_handler for futures trading
        """
        if not self.config.has_credentials():
            self.logger.info("No credentials - skipping private WebSocket")
            return
            
        try:
            from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers
            
            # Create handler objects for constructor injection with position handler
            private_handlers = PrivateWebsocketHandlers(
                order_handler=self._handle_order_event,
                balance_handler=self._handle_balance_event,
                position_handler=self._handle_position_event,  # Futures-specific position handling
                execution_handler=self._handle_execution_event,
                connection_handler=self._handle_private_connection_event,
                error_handler=self._handle_error_event
            )
            
            # Use abstract factory method to create client with handlers
            self._private_ws = await self._create_private_ws_with_handlers(private_handlers)
            
            if self._private_ws:
                # Connect and start event processing
                await self._private_ws.connect()
                self._private_ws_connected = self._private_ws.is_connected
                
                self.logger.info("Private WebSocket initialized with position handler",
                                connected=self._private_ws_connected,
                                has_position_handler=private_handlers.position_handler is not None)
                
        except Exception as e:
            self.logger.error("Private WebSocket initialization failed", error=str(e))
            raise

    # Enhanced monitoring for futures

    def get_futures_trading_stats(self) -> Dict[str, Any]:
        """
        Get futures trading statistics for monitoring.
        
        Returns:
            Dictionary with futures trading and account statistics
        """
        base_stats = self.get_trading_stats()
        
        futures_stats = {
            'leverage_settings_count': len(self._leverage_settings),
            'margin_info_count': len(self._margin_info),
            'futures_positions_count': len(self._futures_positions),
            'total_position_value': sum(
                pos.notional_value for pos in self._futures_positions.values()
                if hasattr(pos, 'notional_value')
            ),
        }
        
        return {**base_stats, **futures_stats}

    def get_trading_stats(self) -> Dict[str, Any]:
        """
        Get enhanced trading statistics for monitoring including positions.
        OVERRIDDEN: To include position metrics for futures exchanges
        
        Returns:
            Dictionary with trading and account statistics including positions
        """
        # Get base stats from parent
        base_stats = super().get_trading_stats()
        
        # Add position metrics for backward compatibility
        base_stats['active_positions'] = len(self._futures_positions)
        
        return base_stats

    # Risk management utilities

    def get_position_risk(self, symbol: Symbol) -> Optional[Dict[str, Any]]:
        """
        Calculate position risk metrics.
        
        Args:
            symbol: Symbol to calculate risk for
            
        Returns:
            Dictionary with risk metrics or None if no position
        """
        if symbol not in self._futures_positions:
            return None

        position = self._futures_positions[symbol]
        margin_info = self._margin_info.get(symbol)
        
        if not margin_info:
            return None

        return {
            'symbol': symbol,
            'position_size': position.size,
            'unrealized_pnl': position.unrealized_pnl,
            'margin_ratio': margin_info.margin_ratio,
            'liquidation_price': position.liquidation_price,
            'risk_level': 'high' if margin_info.margin_ratio > 0.8 else 'medium' if margin_info.margin_ratio > 0.5 else 'low'
        }