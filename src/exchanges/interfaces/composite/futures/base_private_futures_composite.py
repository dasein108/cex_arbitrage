"""
Private futures exchange interface for futures trading operations.

This interface extends the composite private interface with futures-specific
trading functionality like leverage management, position control, and
futures-specific order types.
"""

from abc import abstractmethod
from typing import Dict, List, Optional, Any

from exchanges.structs import Side
from exchanges.structs.common import Symbol, Order, Position, SymbolsInfo, OrderId, FuturesBalance
from exchanges.interfaces.composite.base_private_composite import BasePrivateComposite
from exchanges.interfaces.rest.interfaces import PrivateFuturesInterface
from exchanges.interfaces.ws.ws_base_private import PrivateBaseWebsocket
from exchanges.interfaces.composite.types import PrivateRestType, PrivateWebsocketType
from infrastructure.logging import HFTLoggerInterface
from infrastructure.networking.websocket.structs import PrivateWebsocketChannelType


class CompositePrivateFuturesExchange(BasePrivateComposite[PrivateFuturesInterface, PrivateBaseWebsocket]):
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
                 logger: Optional[HFTLoggerInterface] = None,
                 balance_sync_interval: Optional[float] = None):
        """Initialize private futures exchange interface with dependency injection."""
        super().__init__(config, rest_client, websocket_client, logger, balance_sync_interval)
        
        # Override tag to indicate futures operations
        self._tag = f'{config.name}_private_futures'

        # Futures-specific private data
        self._positions: Dict[Symbol, Position] = {}
        self._futures_balances: Dict[str, FuturesBalance] = {}  # Asset -> FuturesBalance

    @property
    def positions(self) -> Dict[Symbol, Position]:
        """Get current positions (alias for futures_positions)."""
        return self._positions.copy()
    
    @property
    def futures_balances(self) -> Dict[str, FuturesBalance]:
        """Get current futures balances with margin information."""
        return self._futures_balances.copy()

    # Trading operations - delegate to REST client

    async def get_balances(self) -> List[FuturesBalance]:
        """Get futures account balances with margin information via REST API."""
        return await self._rest.get_balances()

    async def get_positions(self) -> List[Position]:
        """Get current positions via REST API."""
        return await self._rest.get_positions()

    async def get_trading_fees(self, symbol: Symbol) -> Any:
        """Get trading fees for a symbol via REST API."""
        # return await self._rest.get_trading_fees(symbol)
        raise NotImplementedError("get_trading_fees must be implemented by subclass")
    
    # async def get_futures_balance(self, asset: str) -> Optional[FuturesBalance]:
    #     """Get futures balance for a specific asset with margin information."""
    #     return await self._rest.get_asset_balance(asset)
    #
    # def get_cached_futures_balance(self, asset: str) -> Optional[FuturesBalance]:
    #     """Get cached futures balance for a specific asset (WebSocket updated)."""
    #     return self._futures_balances.get(asset)
    #
    def check_available_margin(self, asset: str, required_margin: float) -> bool:
        """Check if there's sufficient available margin for a new position."""
        balance = self._futures_balances.get(asset)
        if not balance:
            return False
        return balance.has_available_margin(required_margin)
    
    def get_margin_utilization(self, asset: str) -> float:
        """Get current margin utilization percentage (0.0 - 1.0)."""
        balance = self._futures_balances.get(asset)
        if not balance:
            return 1.0  # Assume fully utilized if no balance data
        return balance.margin_utilization
    
    def get_account_equity(self, asset: str) -> float:
        """Get account equity (total + unrealized PnL) for an asset."""
        balance = self._futures_balances.get(asset)
        if not balance:
            return 0.0
        return balance.equity

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
        quantity: Optional[float] = None
    ) -> List[Order]:
        """Close position (partially or completely)."""
        raise NotImplementedError(
            "close_position must be implemented by subclass",
        )

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


    # Futures-specific event handlers
    async def _position_handler(self, position: Position) -> None:
        """Handle position updates from WebSocket (futures-specific)."""
        self._positions[position.symbol] = position
        self.logger.debug(f"Updated futures position for {position.symbol}: {position}")
    
    async def _futures_balance_handler(self, balance: FuturesBalance) -> None:
        """Handle futures balance updates from WebSocket with margin information."""
        self._futures_balances[balance.asset] = balance
        self.logger.debug(f"Updated futures balance for {balance.asset}: {balance}")
        
        # Log margin utilization warnings
        if balance.margin_utilization > 0.8:  # >80% margin utilization
            self.logger.warning(
                f"High margin utilization for {balance.asset}: "
                f"{balance.margin_utilization*100:.2f}% "
                f"(Available: {balance.available:.6f}, "
                f"Margin: {balance.locked:.6f})"
            )

        self.publish(PrivateWebsocketChannelType.BALANCE, balance)


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

    def round_base_to_contracts(self, symbol: Symbol, base_quantity: float) -> float:
        """Convert base currency quantity to contract quantity."""
        symbol_info = self._symbols_info.get(symbol)
        if not symbol_info or not symbol_info.quanto_multiplier:
            raise ValueError(f"Symbol info or quanto multiplier not found for {symbol}")

        return max(round(base_quantity / symbol_info.quanto_multiplier), 1)

    async def place_limit_order(self, symbol: Symbol, side: Side, quantity: float, price: float, **kwargs) -> Order:
        # **** CONVERT BASE QUANTITY TO CONTRACTS ****
        # ACTUAL FOR GATE.IO FUTURES
        contracts_count = self.round_base_to_contracts(symbol, quantity)

        return await super().place_market_order(symbol=symbol, side=side,
                                                quantity=contracts_count, price=price,
                                                **kwargs)

    async def place_market_order(self, symbol: Symbol, side: Side,
                                 quantity: Optional[float] = None,
                                 quote_quantity: Optional[float] = None,
                                 price: Optional[float] = None,
                                 ensure: bool = True, **kwargs) -> Order:
        # **** CONVERT BASE QUANTITY TO CONTRACTS ****
        # ACTUAL FOR GATE.IO FUTURES
        contracts_count = self.round_base_to_contracts(symbol, quantity)

        return await super().place_market_order(symbol=symbol, side=side,
                                                quantity=contracts_count,
                                                price=price, ensure=ensure,
                                                **kwargs)






