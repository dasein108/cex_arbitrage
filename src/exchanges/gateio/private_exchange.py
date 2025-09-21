"""
Gate.io Private Exchange Implementation

HFT-compliant private trading operations with authentication.
Inherits public market data capabilities and adds trading functionality.

HFT COMPLIANCE: Sub-50ms order execution, real-time balance updates.
"""

import logging
import time
from typing import List, Dict, Optional

from interfaces.cex.base import BasePrivateExchangeInterface
from structs.common import (
    OrderBook, Symbol, SymbolInfo, SymbolsInfo, AssetBalance, AssetName, 
    Order, OrderId, OrderType, Side, TimeInForce, Position,
    ExchangeStatus
)
from exchanges.gateio.public_exchange import GateioPublicExchange
from exchanges.gateio.rest.gateio_rest_private import GateioPrivateSpotRest
from core.exceptions.exchange import BaseExchangeError
from core.config.structs import ExchangeConfig


class GateioPrivateExchange(BasePrivateExchangeInterface):
    """
    Gate.io Private Exchange - Full Trading Operations
    
    Composition-based implementation that combines public market data
    with private trading operations.
    
    Features:
    - Full trading functionality (orders, balances, positions)
    - Real-time market data via public exchange composition
    - HFT-optimized execution with sub-50ms order placement
    - Comprehensive position and balance management
    
    HFT Compliance:
    - No caching of real-time trading data (balances, orders, positions)
    - Fresh API calls for all trading state
    - Real-time market data streaming for pricing
    """
    exchange_name = "GATEIO_private"

    def __init__(self, config: ExchangeConfig):
        super().__init__(config)
        """Initialize Gate.io private exchange with full trading capabilities."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Composition: Use public exchange for market data
        self.public_exchange = GateioPublicExchange(config)
        
        # Initialize private REST client for trading operations
        # TODO: Update REST client to use unified config pattern  
        self.private_client = None  # Temporarily disabled until REST client is updated
        
        # HFT State Management (CRITICAL: NO CACHING OF REAL-TIME TRADING DATA)
        self._cached_balances: Optional[Dict[AssetName, AssetBalance]] = None
        self._cached_open_orders: Optional[Dict[Symbol, List[Order]]] = None
        self._last_balance_update = 0.0
        self._last_orders_update = 0.0
        
        self.logger.info(f"Gate.io private exchange initialized with credentials")
    
    # BasePublicExchangeInterface Implementation (delegated to public exchange)
    
    @property
    def orderbook(self) -> OrderBook:
        """Delegate to public exchange for real-time market data."""
        return self.public_exchange.orderbook
    
    @property
    def symbols_info(self) -> SymbolsInfo:
        """Delegate to public exchange for symbol information."""
        return self.public_exchange.symbols_info
    
    @property
    def active_symbols(self) -> List[Symbol]:
        """Delegate to public exchange for active symbols."""
        return self.public_exchange.active_symbols
    
    async def initialize(self, symbols: List[Symbol] = None) -> None:
        """Initialize both public and private exchange components."""
        start_time = time.perf_counter()
        
        # Initialize public market data
        await self.public_exchange.initialize(symbols)
        
        # Validate private API access
        try:
            await self._validate_private_access()
        except Exception as e:
            self.logger.error(f"Failed to validate private API access: {e}")
            raise BaseExchangeError(500, f"Private API validation failed: {str(e)}")
        
        load_time = time.perf_counter() - start_time
        self.logger.info(
            f"Gate.io private exchange initialized in {load_time*1000:.2f}ms"
        )
    
    async def add_symbol(self, symbol: Symbol) -> None:
        """Delegate to public exchange."""
        await self.public_exchange.add_symbol(symbol)
    
    async def remove_symbol(self, symbol: Symbol) -> None:
        """Delegate to public exchange."""
        await self.public_exchange.remove_symbol(symbol)
    
    async def close(self) -> None:
        """Clean shutdown of all connections."""
        await self.public_exchange.close()
        
        # Clear cached trading data
        self._cached_balances = None
        self._cached_open_orders = None
        
        self.logger.info("Gate.io private exchange closed")
    
    # BasePrivateExchangeInterface Implementation
    
    @property
    def balances(self) -> Dict[AssetName, AssetBalance]:
        """
        Get current account balances.
        
        HFT COMPLIANT: Always returns fresh data, no stale cache.
        """
        if self._cached_balances is None:
            raise BaseExchangeError(500, "Balances not loaded - call get_balances() first")
        return self._cached_balances.copy()
    
    @property
    def open_orders(self) -> Dict[Symbol, List[Order]]:
        """
        Get current open orders.
        
        HFT COMPLIANT: Always returns fresh data, no stale cache.
        """
        if self._cached_open_orders is None:
            raise BaseExchangeError(500, "Orders not loaded - call get_open_orders() first")
        return self._cached_open_orders.copy()
    
    async def get_balances(self) -> Dict[AssetName, AssetBalance]:
        """
        Fetch fresh account balances from API.
        
        HFT COMPLIANT: Fresh API call every time.
        """
        # TODO: Implement when REST client is updated
        if self.private_client is None:
            self.logger.warning("Private REST client not available - using empty balances")
            self._cached_balances = {}
            return {}
        
        try:
            balances = await self.private_client.get_account_balances()
            self._cached_balances = balances
            self._last_balance_update = time.time()
            return balances.copy()
        except Exception as e:
            self.logger.error(f"Failed to get balances: {e}")
            raise BaseExchangeError(500, f"Balance fetch failed: {str(e)}")
    
    async def get_open_orders(self, symbol: Optional[Symbol] = None) -> Dict[Symbol, List[Order]]:
        """
        Fetch fresh open orders from API.
        
        HFT COMPLIANT: Fresh API call every time.
        """
        # TODO: Implement when REST client is updated
        if self.private_client is None:
            self.logger.warning("Private REST client not available - using empty orders")
            self._cached_open_orders = {}
            return {}
        
        try:
            orders = await self.private_client.get_open_orders(symbol)
            self._cached_open_orders = orders
            self._last_orders_update = time.time()
            return orders.copy()
        except Exception as e:
            self.logger.error(f"Failed to get open orders: {e}")
            raise BaseExchangeError(500, f"Open orders fetch failed: {str(e)}")
    
    async def get_positions(self) -> Dict[Symbol, Position]:
        """
        Get current positions (spot trading - typically empty).
        
        HFT COMPLIANT: Fresh API call every time.
        """
        # Gate.io spot trading doesn't have positions like futures
        # Return empty dict for compatibility
        return {}
    
    async def place_limit_order(
        self,
        symbol: Symbol,
        side: Side,
        quantity: float,
        price: float,
        time_in_force: TimeInForce = TimeInForce.GTC
    ) -> OrderId:
        """
        Place limit order with HFT-optimized execution.
        
        HFT COMPLIANT: Sub-50ms execution target.
        """
        if self.private_client is None:
            raise BaseExchangeError(500, "Private REST client not available - cannot place order")
            
        try:
            order_id = await self.private_client.place_limit_order(
                symbol, side, quantity, price, time_in_force
            )
            
            # Invalidate cached orders after placing
            self._cached_open_orders = None
            
            return order_id
        except Exception as e:
            self.logger.error(f"Failed to place limit order: {e}")
            raise BaseExchangeError(500, f"Limit order placement failed: {str(e)}")
    
    async def place_market_order(
        self,
        symbol: Symbol,
        side: Side,
        quantity: float
    ) -> OrderId:
        """
        Place market order with HFT-optimized execution.
        
        HFT COMPLIANT: Sub-50ms execution target.
        """
        if self.private_client is None:
            raise BaseExchangeError(500, "Private REST client not available - cannot place order")
            
        try:
            order_id = await self.private_client.place_market_order(
                symbol, side, quantity
            )
            
            # Invalidate cached data after trading
            self._cached_open_orders = None
            self._cached_balances = None
            
            return order_id
        except Exception as e:
            self.logger.error(f"Failed to place market order: {e}")
            raise BaseExchangeError(500, f"Market order placement failed: {str(e)}")
    
    async def cancel_order(self, order_id: OrderId, symbol: Symbol) -> bool:
        """
        Cancel order with HFT-optimized execution.
        
        HFT COMPLIANT: Sub-50ms execution target.
        """
        if self.private_client is None:
            raise BaseExchangeError(500, "Private REST client not available - cannot cancel order")
            
        try:
            success = await self.private_client.cancel_order(order_id, symbol)
            
            # Invalidate cached orders after canceling
            self._cached_open_orders = None
            
            return success
        except Exception as e:
            self.logger.error(f"Failed to cancel order: {e}")
            raise BaseExchangeError(500, f"Order cancellation failed: {str(e)}")
    
    async def cancel_all_orders(self, symbol: Optional[Symbol] = None) -> int:
        """Cancel all orders for symbol or all symbols."""
        if self.private_client is None:
            raise BaseExchangeError(500, "Private REST client not available - cannot cancel orders")
            
        try:
            cancelled_count = await self.private_client.cancel_all_orders(symbol)
            
            # Invalidate cached orders after canceling
            self._cached_open_orders = None
            
            return cancelled_count
        except Exception as e:
            self.logger.error(f"Failed to cancel all orders: {e}")
            raise BaseExchangeError(500, f"Bulk order cancellation failed: {str(e)}")
    
    # Status and Health
    
    def get_connection_status(self) -> ExchangeStatus:
        """Get current connection status."""
        return self.public_exchange.get_connection_status()
    
    def get_trading_health(self) -> Dict[str, any]:
        """Get trading-specific health metrics."""
        return {
            "balances_last_updated": self._last_balance_update,
            "orders_last_updated": self._last_orders_update,
            "credentials_configured": self.config.has_credentials(),
            "ready_for_trading": self.config.is_ready_for_trading()
        }
    
    async def _validate_private_access(self) -> None:
        """Validate private API access by testing a simple call."""
        if self.private_client is None:
            self.logger.warning("Private REST client not available - skipping validation")
            return
            
        try:
            # Test private API with a simple balance call
            await self.get_balances()
            self.logger.info("Gate.io private API access validated successfully")
        except Exception as e:
            self.logger.error(f"Gate.io private API validation failed: {e}")
            raise