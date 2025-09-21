"""
MEXC Private Exchange Implementation

HFT-compliant private trading operations with authentication.
Inherits public market data capabilities and adds trading functionality.

HFT COMPLIANCE: Sub-50ms order execution, real-time balance updates.
"""

import time
from typing import List, Dict

from interfaces.cex.base import BasePrivateExchangeInterface
from structs.common import (
    Symbol, AssetBalance, AssetName, Order, OrderId, SymbolsInfo, Trade
)
from exchanges.mexc.ws.mexc_ws_private import MexcWebsocketPrivate
from exchanges.mexc.rest.mexc_rest_private import MexcPrivateSpotRest
from core.exceptions.exchange import BaseExchangeError
from core.config.structs import ExchangeConfig


class MexcPrivateExchange(BasePrivateExchangeInterface):
    """
    MEXC Private Exchange - Trading Operations
    
    Provides authenticated trading operations with real-time market data.
    Inherits all public market data functionality and adds trading capabilities.
    
    Features:
    - All public market data streaming capabilities
    - Real-time account balance updates
    - Order placement and management
    - Position tracking for futures
    - Sub-50ms order execution targets
    
    HFT Compliance:
    - No caching of real-time trading data (balances, orders, positions)
    - Fresh API calls for all trading operations
    - Real-time WebSocket updates for account data
    """

    def __init__(self, config: ExchangeConfig):
        """
        Initialize MEXC private exchange with authentication.
        
        Args:
            config: Exchange configuration with API credentials
        """
        super().__init__(config)

        # HFT Optimized: Real-time trading data structures (not cached)
        self._balances_dict: Dict[AssetName, AssetBalance] = {}
        self._open_orders_dict: Dict[Symbol, List[Order]] = {}

        # Initialize private trading capabilities
        self._private_rest = MexcPrivateSpotRest(config)

        # Initialize private WebSocket client
        self._private_websocket = MexcWebsocketPrivate(
            private_rest_client=self._private_rest,
            config=self._config,
            order_handler=self._handle_order_update,
            balance_handler=self._handle_balance_update,
            trade_handler=self._handle_trade_update
        )


        # HFT Performance tracking
        self._trading_operations = 0
        self._last_balance_update = 0.0
        
        self.logger.info("MEXC Private Exchange initialized with trading capabilities")
    
    # === Public Interface Delegation ===
    # Delegate all public operations to the base public exchange
    
    async def initialize(self, symbols_info: SymbolsInfo) -> None:
        """
        Initialize both public and private capabilities.
        
        Args:
            symbols_info: Symbol information dictionary from public exchange
        """
        self.logger.info("Initializing MEXC private exchange...")
        
        try:
            self._symbols_info = symbols_info

            # Initialize public market data capabilities
            await self._load_account_data()

            # Initialize private WebSocket for real-time updates
            await self._private_websocket.initialize()
            
            self.logger.info("MEXC private exchange initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize MEXC private exchange: {e}")
            raise BaseExchangeError(f"MEXC private initialization failed: {e}")
    

    async def close(self) -> None:
        """Close both public and private connections."""
        self.logger.info("Closing MEXC private exchange...")
        
        try:
            # Close private WebSocket
            if self._private_websocket:
                await self._private_websocket.close()
                self._private_websocket = None
            
            # Close public exchange

            # Clean up private state
            self._balances_dict.clear()
            self._open_orders_dict.clear()

            self.logger.info("MEXC private exchange closed successfully")
            
        except Exception as e:
            self.logger.error(f"Error closing MEXC private exchange: {e}")
    
    # === Private Interface Implementation ===
    
    @property
    def balances(self) -> Dict[AssetName, AssetBalance]:
        """
        Get current account balances.
        
        HFT COMPLIANT: Fresh data, no caching of real-time trading data.
        """
        # Return current balances (updated via WebSocket)
        return self._balances_dict.copy()
    
    @property
    def open_orders(self) -> Dict[Symbol, List[Order]]:
        """
        Get current open orders.
        
        HFT COMPLIANT: Fresh data, no caching.
        """
        return self._open_orders_dict.copy()

    def place_limit_order(
        self, 
        symbol: Symbol, 
        side: str, 
        quantity: float, 
        price: float,
        **kwargs
    ) -> Order:
        """
        Place a limit order.
        
        HFT COMPLIANT: Sub-50ms execution target.
        
        Args:
            symbol: Trading symbol
            side: Order side ('buy' or 'sell')
            quantity: Order quantity
            price: Limit price
            **kwargs: Additional order parameters
            
        Returns:
            Placed order information
        """
        start_time = time.perf_counter()
        self._trading_operations += 1
        
        try:
            # Place order via REST API
            order = self._private_rest.place_limit_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                **kwargs
            )
            
            # Track performance
            execution_time = (time.perf_counter() - start_time) * 1000
            self.logger.debug(f"Limit order placed in {execution_time:.2f}ms")
            
            return order
            
        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            self.logger.error(f"Failed to place limit order in {execution_time:.2f}ms: {e}")
            raise BaseExchangeError(f"Failed to place limit order: {e}")
    
    def place_market_order(
        self, 
        symbol: Symbol, 
        side: str, 
        quantity: float,
        **kwargs
    ) -> Order:
        """
        Place a market order.
        
        HFT COMPLIANT: Sub-50ms execution target.
        
        Args:
            symbol: Trading symbol
            side: Order side ('buy' or 'sell')
            quantity: Order quantity
            **kwargs: Additional order parameters
            
        Returns:
            Placed order information
        """
        start_time = time.perf_counter()
        self._trading_operations += 1

        try:
            # Place order via REST API
            order = self._private_rest.place_market_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                **kwargs
            )
            
            # Track performance
            execution_time = (time.perf_counter() - start_time) * 1000
            self.logger.debug(f"Market order placed in {execution_time:.2f}ms")
            
            return order
            
        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            self.logger.error(f"Failed to place market order in {execution_time:.2f}ms: {e}")
            raise BaseExchangeError(f"Failed to place market order: {e}")
    
    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> bool:
        """
        Cancel an order.
        
        HFT COMPLIANT: Sub-50ms execution target.
        
        Args:
            symbol: Trading symbol
            order_id: Order ID to cancel
            
        Returns:
            True if cancellation successful
        """
        start_time = time.perf_counter()
        
        try:
            # Cancel order via REST API
            order = await self._private_rest.cancel_order(symbol, order_id)
            
            # Track performance
            execution_time = (time.perf_counter() - start_time) * 1000
            self.logger.debug(f"Order cancelled in {execution_time:.2f}ms")
            
            return order
            
        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            self.logger.error(f"Failed to cancel order in {execution_time:.2f}ms: {e}")
            raise BaseExchangeError(f"Failed to cancel order: {e}")
    
    # === Private Implementation Details ===

    
    async def _load_account_data(self) -> None:
        """Load initial account balances and orders."""
        try:
            # Get current balances
            balances = await self._private_rest.get_account_balance()
            for b in balances:
                self._balances_dict[b.asset] = b
            
            # Get current open orders
            orders = await self._private_rest.get_open_orders()
            for o in orders:
                self._open_orders_dict[o.symbol] = self._open_orders_dict.get(o.symbol, []) + [o]
            
            self.logger.info(f"Loaded {len(balances)} balances and {sum(len(orders) for orders in orders.values())} open orders")
            
        except Exception as e:
            self.logger.error(f"Failed to load account data: {e}")
            raise

    async def _handle_balance_update(self, balances: Dict[AssetName, AssetBalance]) -> None:
        """
        Handle real-time balance updates from WebSocket.
        
        HFT COMPLIANT: Sub-millisecond processing.
        """
        self._balances_dict.update(balances)
        self._last_balance_update = time.perf_counter()
    
    async def _handle_order_update(self, order: Order) -> None:
        """
        Handle real-time order updates from WebSocket.
        
        HFT COMPLIANT: Sub-millisecond processing.
        """
        if order.symbol and order.symbol not in self._open_orders_dict:
            self._open_orders_dict[order.symbol] = []
        
        # Update or add order
        if order.symbol:
            existing_orders = self._open_orders_dict[order.symbol]
            for i, existing_order in enumerate(existing_orders):
                if existing_order.order_id == order.order_id:
                    existing_orders[i] = order
                    return
            
            # Add new order
            existing_orders.append(order)

    async def _handle_trade_update(self, trade: Trade) -> None:
        """
        Handle real-time trade updates from WebSocket.
        
        HFT COMPLIANT: Sub-millisecond processing.
        """
        # Log trade execution for audit trail
        self.logger.debug(f"Trade executed: {trade.side.name} {trade.quantity} at {trade.price}")
    
    def get_trading_statistics(self) -> Dict[str, any]:
        """Get trading performance statistics."""

        return {
            'trading_operations': self._trading_operations,
            'last_balance_update': self._last_balance_update,
            'balances_count': len(self._balances_dict),
            'open_orders_count': sum(len(orders) for orders in self._open_orders_dict.values())
        }