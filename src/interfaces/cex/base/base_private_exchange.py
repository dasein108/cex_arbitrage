"""
Private exchange interface for trading operations.

This interface handles authenticated operations including order management,
balance tracking, and position monitoring. It inherits from the public
interface to also provide market data functionality.
"""

from abc import abstractmethod
from typing import Dict, List, Optional, Any
from structs.common import (
    Symbol, SymbolsInfo, AssetBalance, Order, OrderBook, Position
)
from core.config.structs import ExchangeConfig
from .base_public_exchange import BasePublicExchangeInterface


class BasePrivateExchangeInterface(BasePublicExchangeInterface):
    """
    Base interface for private exchange operations (trading + market data).
    
    Handles:
    - All public exchange functionality (inherits from BasePublicExchangeInterface)
    - Account balance tracking
    - Order management (place, cancel, status)
    - Position monitoring (for margin/futures trading)
    - Authenticated data streaming via WebSocket
    
    This interface requires valid API credentials and provides full trading
    functionality on top of market data operations.
    """

    def __init__(self, config: ExchangeConfig):
        """
        Initialize private exchange interface.
        
        Args:
            config: Exchange configuration with API credentials
        """
        super().__init__(config)
        
        # Override tag to indicate private operations
        self._tag = f'{config.name}_private'
        
        # Private data state
        self._balances: Dict[Symbol, AssetBalance] = {}
        self._open_orders: Dict[Symbol, List[Order]] = {}
        self._positions: Dict[Symbol, Position] = {}

        # Authentication validation
        if not config.has_credentials():
            self.logger.warning("No API credentials provided - trading operations will fail")

    # Abstract properties for private data

    @property
    @abstractmethod
    def balances(self) -> Dict[Symbol, AssetBalance]:
        """
        Get current account balances.
        
        Returns:
            Dictionary mapping asset symbols to balance information
        """
        pass

    @property
    @abstractmethod
    def open_orders(self) -> Dict[Symbol, List[Order]]:
        """
        Get current open orders.
        
        Returns:
            Dictionary mapping symbols to lists of open orders
        """
        pass

    @property
    @abstractmethod
    def positions(self) -> Dict[Symbol, Position]:
        """
        Get current positions (for margin/futures trading).
        
        Returns:
            Dictionary mapping symbols to position information
        """
        pass

    # Abstract trading operations

    @abstractmethod
    async def place_limit_order(
        self, 
        symbol: Symbol, 
        side: str, 
        quantity: float, 
        price: float, 
        **kwargs
    ) -> Order:
        """
        Place a limit order.
        
        Args:
            symbol: Trading symbol
            side: Order side ('buy' or 'sell')
            quantity: Order quantity
            price: Limit price
            **kwargs: Exchange-specific parameters
            
        Returns:
            Order object with order details
            
        Raises:
            ExchangeError: If order placement fails
        """
        pass

    @abstractmethod
    async def place_market_order(
        self, 
        symbol: Symbol, 
        side: str, 
        quantity: float, 
        **kwargs
    ) -> Order:
        """
        Place a market order.
        
        Args:
            symbol: Trading symbol
            side: Order side ('buy' or 'sell')
            quantity: Order quantity
            **kwargs: Exchange-specific parameters
            
        Returns:
            Order object with order details
            
        Raises:
            ExchangeError: If order placement fails
        """
        pass

    @abstractmethod
    async def cancel_order(self, symbol: Symbol, order_id: str) -> bool:
        """
        Cancel an existing order.
        
        Args:
            symbol: Trading symbol
            order_id: Exchange order ID to cancel
            
        Returns:
            True if cancellation successful, False otherwise
            
        Raises:
            ExchangeError: If cancellation fails
        """
        pass

    @abstractmethod
    async def get_order_status(self, symbol: Symbol, order_id: str) -> Order:
        """
        Get current status of an order.
        
        Args:
            symbol: Trading symbol
            order_id: Exchange order ID
            
        Returns:
            Order object with current status
            
        Raises:
            ExchangeError: If order not found or query fails
        """
        pass

    @abstractmethod
    async def get_order_history(
        self, 
        symbol: Optional[Symbol] = None, 
        limit: int = 100
    ) -> List[Order]:
        """
        Get order history.
        
        Args:
            symbol: Optional symbol filter
            limit: Maximum number of orders to return
            
        Returns:
            List of historical orders
        """
        pass

    # Abstract private data loading

    @abstractmethod
    async def _load_balances(self) -> None:
        """Load account balances from REST API."""
        pass

    @abstractmethod
    async def _load_open_orders(self) -> None:
        """Load open orders from REST API."""
        pass

    @abstractmethod
    async def _load_positions(self) -> None:
        """Load positions from REST API (for margin/futures).""" 
        pass

    # Initialization override for private exchanges

    async def initialize(self, symbols: List[Symbol] = None) -> None:
        """
        Initialize private exchange with symbols and private data.
        
        Args:
            symbols: Optional list of symbols to track
        """
        # First initialize public functionality
        await super().initialize(symbols)

        try:
            # Load private data
            await self._load_balances()
            await self._load_open_orders()
            
            # Load positions if supported (futures/margin trading)
            try:
                await self._load_positions()
            except NotImplementedError:
                # Positions not supported on this exchange (spot-only)
                pass

            self.logger.info(f"{self._tag} private data initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize private data for {self._tag}: {e}")
            raise

    # Data refresh implementation for reconnections

    async def _refresh_exchange_data(self) -> None:
        """
        Refresh all exchange data after reconnection.
        
        Refreshes both public data (orderbooks, symbols) and private data
        (balances, orders, positions).
        """
        try:
            # Refresh public data first
            if self._active_symbols:
                await self._initialize_orderbooks_from_rest(self._active_symbols)

            # Refresh private data
            await self._load_balances()
            await self._load_open_orders()
            
            try:
                await self._load_positions()
            except NotImplementedError:
                pass

            self.logger.info(f"{self._tag} all data refreshed after reconnection")

        except Exception as e:
            self.logger.error(f"Failed to refresh data for {self._tag}: {e}")
            raise

    # Utility methods for private data management

    def _update_balance(self, asset: Symbol, balance: AssetBalance) -> None:
        """
        Update internal balance state.
        
        Args:
            asset: Asset symbol
            balance: New balance information
        """
        self._balances[asset] = balance
        self.logger.debug(f"Updated balance for {asset}: {balance}")

    def _update_order(self, order: Order) -> None:
        """
        Update internal order state.
        
        Args:
            order: Updated order information
        """
        symbol = order.symbol
        if symbol not in self._open_orders:
            self._open_orders[symbol] = []

        # Update existing order or add new one
        existing_orders = self._open_orders[symbol]
        for i, existing_order in enumerate(existing_orders):
            if existing_order.order_id == order.order_id:
                if order.status in ['filled', 'canceled', 'expired']:
                    # Remove completed orders
                    existing_orders.pop(i)
                else:
                    # Update existing order
                    existing_orders[i] = order
                return

        # Add new order if it's still open
        if order.status not in ['filled', 'canceled', 'expired']:
            existing_orders.append(order)

    def _update_position(self, position: Position) -> None:
        """
        Update internal position state.
        
        Args:
            position: Updated position information
        """
        self._positions[position.symbol] = position
        self.logger.debug(f"Updated position for {position.symbol}: {position}")

    # Monitoring and diagnostics

    def get_trading_stats(self) -> Dict[str, Any]:
        """
        Get trading statistics for monitoring.
        
        Returns:
            Dictionary with trading and account statistics
        """
        base_stats = self.get_orderbook_stats()
        
        trading_stats = {
            'total_balances': len(self._balances),
            'open_orders_count': sum(len(orders) for orders in self._open_orders.values()),
            'active_positions': len(self._positions),
            'has_credentials': self._config.has_credentials(),
        }
        
        return {**base_stats, **trading_stats}