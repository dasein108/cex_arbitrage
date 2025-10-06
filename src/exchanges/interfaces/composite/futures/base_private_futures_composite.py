"""
Private futures exchange interface for futures trading operations.

This interface extends the composite private interface with futures-specific
trading functionality like leverage management, position control, and
futures-specific order types.
"""

from abc import abstractmethod
from typing import Dict, List, Optional, Any
from decimal import Decimal

from exchanges.structs import Side
from exchanges.structs.common import Symbol, Order, Position, SymbolsInfo, OrderId
from exchanges.interfaces.composite.base_private_composite import BasePrivateComposite
from exchanges.interfaces.composite.types import PrivateRestType, PrivateWebsocketType
from infrastructure.logging import HFTLoggerInterface
from infrastructure.exceptions.exchange import ExchangeRestError, OrderNotFoundError


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

    # Trading operations - delegate to REST client

    async def get_balances(self) -> List[Any]:
        """Get account balances via REST API."""
        return await self._rest.get_balances()

    async def get_positions(self) -> List[Position]:
        """Get current positions via REST API."""
        return await self._rest.get_positions()

    async def get_trading_fees(self, symbol: Symbol) -> Any:
        """Get trading fees for a symbol via REST API."""
        return await self._rest.get_trading_fees(symbol)

    # async def place_order(self, symbol: Symbol, side, order_type, quantity: Optional[float] = None,
    #                      price: Optional[float] = None, **kwargs) -> Order:
    #     """Place an order via REST API."""
    #     quanto_multiplier = self._symbols_info[symbol].quanto_multiplier
    #     if quanto_multiplier:
    #         adjusted_quantity = quantity / self._symbols_info[symbol].quanto_multiplier
    #     else:
    #         adjusted_quantity = quantity
    #     return await self._rest.place_order(symbol, side, order_type, adjusted_quantity, price, **kwargs)

    # async def cancel_order(self, symbol: Symbol, order_id) -> Order:
    #     """Cancel an order via REST API."""
    #     try:
    #         return await self._rest.cancel_order(symbol, order_id)
    #     except OrderNotFoundError:
    #         self.logger.warning(f"Order {order_id} not found for cancellation on {self._tag}")
    #         raise


    async def close_position(
        self,
        symbol: Symbol,
        quantity: Optional[Decimal] = None
    ) -> List[Order]:
        """Close position (partially or completely)."""
        #TODO: implement
        raise NotImplemented("close_position must be implemented by subclass")

    # Key futures extensions - WebSocket handlers
    
    async def initialize(self, symbols_info: SymbolsInfo = None, channels: List[PrivateWebsocketType]=None) -> None:
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

    def contracts_to_base_quantity(self, symbol: Symbol, contracts: float) -> float:
        """Convert contract quantity to base currency quantity."""
        symbol_info = self._symbols_info.get(symbol)
        if not symbol_info or not symbol_info.quanto_multiplier:
            raise ValueError(f"Symbol info or quanto multiplier not found for {symbol}")
        return contracts * symbol_info.quanto_multiplier

    async def _update_order(self, order: Order | None, order_id: OrderId | None = None) -> Order | None:
        """
        Override to adjust order quantities from contracts to base currency.
        This is necessary for futures exchanges where orders are often specified
        in contract units rather than base currency units.
        :param order:
        :return:
        """
        if order:
            order.filled_quantity = self.contracts_to_base_quantity(order.symbol, order.filled_quantity)
            order.quantity = self.contracts_to_base_quantity(order.symbol, order.quantity)
            order.remaining_quantity = self.contracts_to_base_quantity(order.symbol, order.remaining_quantity)

        # call base implementation to handle side effects properly
        return await super()._update_order(order, order_id)






