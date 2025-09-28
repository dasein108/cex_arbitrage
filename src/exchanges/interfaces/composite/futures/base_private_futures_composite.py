"""
Private futures exchange interface for futures trading operations.

This interface extends the composite private interface with futures-specific
trading functionality like leverage management, position control, and
futures-specific order types.
"""

from abc import abstractmethod
from typing import Dict, List, Optional, Any
from decimal import Decimal

from exchanges.structs import Symbol, Order, Position, SymbolsInfo, ExchangeType
from exchanges.interfaces.composite.base_private_composite import BasePrivateComposite
from exchanges.interfaces import PrivateFuturesRest
from exchanges.interfaces.ws.futures.ws_private_futures import PrivateFuturesWebsocket
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.handlers import PrivateWebsocketHandlers


class CompositePrivateFuturesExchange(BasePrivateComposite[PrivateFuturesRest, PrivateFuturesWebsocket]):
    """
    Base interface for private futures exchange operations.
    
    Extends BasePrivateComposite with futures-specific features:
    - Leverage management
    - Futures position control (long/short)
    - Margin management
    - Futures-specific order types
    
    NOTE: Futures exchanges do NOT support withdrawals - use spot exchanges for withdrawals.
    """

    def __init__(self, config, logger: Optional[HFTLoggerInterface] = None,
                 handlers: Optional[PrivateWebsocketHandlers] = None,
                 rest_client: Optional[PrivateFuturesRest] = None,
                 websocket_client: Optional[PrivateFuturesWebsocket] = None):
        """Initialize private futures exchange interface with direct client injection."""
        super().__init__(config, ExchangeType.FUTURES, logger=logger, handlers=handlers,
                         rest_client=rest_client,
                         websocket_client=websocket_client)

        # Futures-specific private data
        self._leverage_settings: Dict[Symbol, Dict] = {}
        self._margin_info: Dict[Symbol, Dict] = {}
        self._positions: Dict[Symbol, Position] = {}


    @property
    def positions(self) -> Dict[Symbol, Position]:
        """Get current positions (alias for futures_positions)."""
        return self._positions.copy()

    @abstractmethod
    async def close_position(
        self, 
        symbol: Symbol, 
        quantity: Optional[Decimal] = None
    ) -> List[Order]:
        """Close position (partially or completely)."""
        pass

    @abstractmethod
    async def _load_positions(self) -> None:
        """Load current futures positions from exchange."""
        pass

    async def initialize(self, symbols_info: SymbolsInfo) -> None:
        """Initialize futures exchange with symbols and futures-specific data."""
        # Initialize base private functionality
        await super().initialize(symbols_info)

        try:
            # Load futures-specific private data
            # await self._load_leverage_settings()
            # await self._load_margin_info()
            await self._load_positions()

            self.logger.info(f"{self._tag} futures private data initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize futures private data for {self._tag}: {e}")
            raise

    def _get_inner_websocket_handlers(self) -> PrivateWebsocketHandlers:
        """
        Extend WebSocket handlers to include position handler for futures.
        
        This is the key extension - adds position_handler to the base implementation.
        """
        handlers = super()._get_inner_websocket_handlers()
        handlers.position_handler = self._position_handler
        return handlers

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