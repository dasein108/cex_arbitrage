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
from exchanges.interfaces.composite.spot.base_private_spot_composite import CompositePrivateExchange
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers


class CompositePrivateFuturesExchange(CompositePrivateExchange):
    """
    Base interface for private futures exchange operations.
    
    Extends CompositePrivateExchange with futures-specific features:
    - Leverage management
    - Futures position control (long/short)
    - Margin management
    - Futures-specific order types
    
    Reuses most functionality from CompositePrivateExchange for efficiency.
    """

    def __init__(self, config, logger: Optional[HFTLoggerInterface] = None,
                 handlers: Optional[PrivateWebsocketHandlers] = None):
        """Initialize private futures exchange interface."""
        if handlers is None:
            handlers = PrivateWebsocketHandlers()
        super().__init__(config, logger=logger, handlers=handlers)
        
        # Override tag to indicate futures operations
        self._tag = f'{config.name}_private_futures'

        # Futures-specific private data

        # Alias for backward compatibility
        self._positions: Dict[Symbol, Position] = {}


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
    #
    # @abstractmethod
    # async def place_futures_order(
    #     self,
    #     symbol: Symbol,
    #     side: str,
    #     order_type: str,
    #     quantity: Decimal,
    #     price: Optional[Decimal] = None,
    #     reduce_only: bool = False,
    #     close_position: bool = False,
    #     **kwargs
    # ) -> Order:
    #     """Place a futures order with advanced options."""
    #     pass

    @abstractmethod
    async def close_position(
        self, 
        symbol: Symbol, 
        quantity: Optional[Decimal] = None
    ) -> List[Order]:
        """Close position (partially or completely)."""
        pass


    async def initialize(self, symbols_info: SymbolsInfo) -> None:
        """Initialize futures exchange with symbols and futures-specific data."""
        # Initialize base private functionality
        await super().initialize(symbols_info)

        try:
            self.logger.info(f"{self._tag} futures private data initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize futures private data for {self._tag}: {e}")
            raise


    # Futures-specific position event handler (abstract)
    async def _position_handler(self, position: Position) -> None:
        """Handle position updates from WebSocket (futures-specific)."""
        pass

    # Simple position update utility
    def _update_futures_position(self, position: Position) -> None:
        """Update internal futures position state."""
        self._positions[position.symbol] = position
        self.logger.debug(f"Updated futures position for {position.symbol}: {position}")

    # Enhanced trading stats with position metrics
    def get_trading_stats(self) -> Dict[str, Any]:
        """Get trading stats including position metrics."""
        base_stats = super().get_trading_stats()
        base_stats['active_positions'] = len(self._positions)
        return base_stats