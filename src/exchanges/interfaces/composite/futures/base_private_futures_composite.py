"""
Private futures exchange interface for futures trading operations.

This interface extends the composite private interface with futures-specific
trading functionality like leverage management, position control, and
futures-specific order types.
"""

from abc import abstractmethod
from typing import Dict, List, Optional, Any
from decimal import Decimal

from exchanges.structs.common import Symbol, Order, Position, SymbolsInfo
from exchanges.interfaces.composite.base_private_composite import BasePrivateComposite
from exchanges.interfaces.composite.types import PrivateRestType, PrivateWebSocketType
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers


class CompositePrivateFuturesExchange(BasePrivateComposite):
    """
    Base interface for private futures exchange operations.
    
    Extends BasePrivateComposite with futures-specific features:
    - Leverage management
    - Futures position control (long/short)
    - Margin management
    - Futures-specific order types
    
    NOTE: Futures exchanges do NOT support withdrawals - use spot exchanges for withdrawals.
    """

    def __init__(self, 
                 config, 
                 rest_client: PrivateRestType,
                 websocket_client: Optional[PrivateWebSocketType] = None,
                 logger: Optional[HFTLoggerInterface] = None,
                 handlers: Optional[PrivateWebsocketHandlers] = None):
        """Initialize private futures exchange interface with dependency injection."""
        super().__init__(config, rest_client, websocket_client, logger, handlers)
        
        # Override tag to indicate futures operations
        self._tag = f'{config.name}_private_futures'

        # Futures-specific private data
        self._leverage_settings: Dict[Symbol, Dict] = {}
        self._margin_info: Dict[Symbol, Dict] = {}
        self._positions: Dict[Symbol, Position] = {}
        
        # Alias for backward compatibility
        self._positions: Dict[Symbol, Position] = self._positions

    # Properties for futures private data (reuse parent implementation pattern)
    
    # @property
    # def leverage_settings(self) -> Dict[Symbol, Dict]:
    #     """Get current leverage settings for all symbols."""
    #     return self._leverage_settings.copy()
    #
    # @property
    # def margin_info(self) -> Dict[Symbol, Dict]:
    #     """Get current margin information for all symbols."""
    #     return self._margin_info.copy()
    #
    # @property
    # def futures_positions(self) -> Dict[Symbol, Position]:
    #     """Get current futures positions."""
    #     return self._futures_positions.copy()

    @property
    def positions(self) -> Dict[Symbol, Position]:
        """Get current positions (alias for futures_positions)."""
        return self._positions.copy()

    # Futures-specific abstract methods (must be implemented by concrete classes)

    # @abstractmethod
    # async def set_leverage(self, symbol: Symbol, leverage: int) -> bool:
    #     """Set leverage for a symbol."""
    #     pass
    #
    # @abstractmethod
    # async def get_leverage(self, symbol: Symbol) -> Dict:
    #     """Get current leverage for a symbol."""
    #     pass



    @abstractmethod
    async def close_position(
        self, 
        symbol: Symbol, 
        quantity: Optional[Decimal] = None
    ) -> List[Order]:
        """Close position (partially or completely)."""
        pass

    # Abstract futures data loading methods

    # @abstractmethod
    # async def _load_leverage_settings(self) -> None:
    #     """Load leverage settings from REST API."""
    #     pass
    #
    # @abstractmethod
    # async def _load_margin_info(self) -> None:
    #     """Load margin information from REST API."""
    #     pass
    #
    # @abstractmethod
    # async def _load_futures_positions(self) -> None:
    #     """Load futures positions from REST API."""
    #     pass

    # Key futures extensions - leverage initialization and WebSocket handlers
    
    async def initialize(self, symbols_info: SymbolsInfo) -> None:
        """Initialize futures exchange with symbols and futures-specific data."""
        # Initialize base private functionality
        await super().initialize(symbols_info)

        try:
            # Load futures-specific private data
            # await self._load_leverage_settings()
            # await self._load_margin_info()
            # await self._load_futures_positions()

            self.logger.info(f"{self._tag} futures private data initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize futures private data for {self._tag}: {e}")
            raise

    def _create_inner_websocket_handlers(self) -> PrivateWebsocketHandlers:
        """
        Extend WebSocket handlers to include position handler for futures.
        
        This is the key extension - adds position_handler to the base implementation.
        """
        return PrivateWebsocketHandlers(
            order_handler=self._order_handler,
            balance_handler=self._balance_handler,
            execution_handler=self._execution_handler,
            position_handler=self._position_handler,  # Futures-specific position handling
        )

    # Futures-specific position event handler (abstract)
    async def _position_handler(self, position: Position) -> None:
        """Handle position updates from WebSocket (futures-specific)."""
        self._positions[position.symbol] = position
        self.logger.debug(f"Updated futures position for {position.symbol}: {position}")


    # Enhanced trading stats with position metrics
    def get_trading_stats(self) -> Dict[str, Any]:
        """Get trading stats including position metrics."""
        base_stats = super().get_trading_stats()
        base_stats['active_positions'] = len(self._positions)
        return base_stats

    async def close_position(
            self,
            symbol: Symbol,
            quantity: Optional[Decimal] = None
    ) -> List[Order]:
        """Close position (partially or completely) for Gate.io futures."""
        try:
            # Get current position
            positions = await self._rest.get_positions(symbol)
            if not positions:
                self.logger.warning(f"No position found for {symbol}")
                return []

            orders = []
            for position in positions:
                if position.quantity == 0:
                    continue

                # Determine close quantity
                close_qty = quantity if quantity else abs(position.quantity)

                # Determine side (opposite of position)
                close_side = 'sell' if position.quantity > 0 else 'buy'

                # Place market order to close position
                order = await self.place_market_order(
                    symbol=symbol,
                    side=close_side,
                    order_type='market',
                    quantity=close_qty,
                    reduce_only=True,
                    close_position=(quantity is None)  # Full close if no quantity specified
                )

                orders.append(order)

            self.logger.info(f"Closed position for {symbol}, orders: {[o.order_id for o in orders]}")
            return orders

        except Exception as e:
            self.logger.error(f"Failed to close position for {symbol}: {e}")
            raise


