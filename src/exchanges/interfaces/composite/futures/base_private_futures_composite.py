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
from exchanges.interfaces.composite.types import PrivateRestType, PrivateWebsocketType
from infrastructure.logging import HFTLoggerInterface


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
                 websocket_client: Optional[PrivateWebsocketType] = None,
                 logger: Optional[HFTLoggerInterface] = None):
        """Initialize private futures exchange interface with dependency injection."""
        super().__init__(config, rest_client, websocket_client, logger)
        
        # Override tag to indicate futures operations
        self._tag = f'{config.name}_private_futures'

        # Futures-specific private data
        self._positions: Dict[Symbol, Position] = {}

    @property
    def positions(self) -> Dict[Symbol, Position]:
        """Get current positions (alias for futures_positions)."""
        return self._positions.copy()

    # Futures-specific abstract methods (must be implemented by concrete classes)

    async def close_position(
        self, 
        symbol: Symbol, 
        quantity: Optional[Decimal] = None
    ) -> List[Order]:
        """Close position (partially or completely)."""
        #TODO: implement
        raise NotImplemented("close_position must be implemented by subclass")

    # Key futures extensions - WebSocket handlers
    
    async def initialize(self, symbols_info: SymbolsInfo, channels: List[PrivateWebsocketType]=None) -> None:
        """Initialize futures exchange with symbols and futures-specific data."""
        # Initialize base private functionality
        await super().initialize(symbols_info, channels)

        try:
            # Load futures-specific private data
            # await self._load_leverage_settings()
            # await self._load_margin_info()
            # await self._load_futures_positions()

            self.logger.info(f"{self._tag} futures private data initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize futures private data for {self._tag}: {e}")
            raise


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



