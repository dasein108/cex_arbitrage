"""
Migration Adapter for Unified Interface Compatibility.

Provides backward compatibility for legacy code expecting unified exchange interface
while using the new composite pattern underneath. This adapter allows gradual
migration without breaking existing systems.
"""

import warnings
from typing import Optional, Dict, List
from exchanges.structs.common import Symbol, OrderBook, BookTicker, AssetBalance, Order, WithdrawalRequest, WithdrawalResponse
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs import Side, OrderType
from exchanges.interfaces.composite.spot.base_public_spot_composite import CompositePublicExchange
from exchanges.interfaces.composite.spot.base_private_spot_composite import CompositePrivateExchange
from infrastructure.logging import HFTLoggerInterface


class UnifiedToCompositeAdapter:
    """
    Adapter to support legacy unified exchange interface during migration.
    
    This adapter wraps composite public and private exchanges to provide
    the unified interface expected by legacy code, enabling gradual migration.
    """
    
    def __init__(self,
                 public_exchange: CompositePublicExchange,
                 private_exchange: Optional[CompositePrivateExchange] = None,
                 logger: Optional[HFTLoggerInterface] = None):
        """
        Initialize adapter with composite exchanges.
        
        Args:
            public_exchange: Public exchange for market data
            private_exchange: Optional private exchange for trading
            logger: Optional logger instance
        """
        self.public = public_exchange
        self.private = private_exchange
        self.logger = logger or getattr(public_exchange, 'logger', None)
        
        # Issue deprecation warning
        warnings.warn(
            "UnifiedToCompositeAdapter is deprecated. "
            "Please migrate to use CompositePublicExchange and CompositePrivateExchange directly.",
            DeprecationWarning,
            stacklevel=2
        )
        
        if self.logger:
            self.logger.warning("Using unified interface adapter - consider migrating to composite pattern")
    
    # Public interface methods (delegate to public exchange)
    
    async def get_orderbook(self, symbol: Symbol, limit: Optional[int] = None) -> OrderBook:
        """Get orderbook for symbol."""
        return await self.public._get_orderbook_snapshot(symbol)
    
    async def get_best_bid_ask(self, symbol: Symbol) -> Optional[BookTicker]:
        """Get best bid/ask for symbol."""
        return self.public.get_best_bid_ask(symbol)
    
    async def get_ticker(self, symbol: Symbol):
        """Get ticker for symbol."""
        if hasattr(self.public, 'get_ticker'):
            return await self.public.get_ticker(symbol)
        raise NotImplementedError("Ticker not available in public exchange")
    
    async def get_exchange_info(self):
        """Get exchange information."""
        return self.public.symbols_info
    
    def get_active_symbols(self):
        """Get active symbols."""
        return self.public.active_symbols
    
    # Private interface methods (delegate to private exchange)
    
    async def place_order(self, 
                         symbol: Symbol, 
                         side: Side, 
                         order_type: OrderType, 
                         quantity: float, 
                         price: Optional[float] = None, 
                         **kwargs) -> Order:
        """Place an order."""
        if not self.private:
            raise RuntimeError("Private exchange not available - trading operations disabled")
        
        if order_type == OrderType.LIMIT:
            if price is None:
                raise ValueError("Price required for limit orders")
            return await self.private.place_limit_order(symbol, side, quantity, price, **kwargs)
        elif order_type == OrderType.MARKET:
            return await self.private.place_market_order(symbol, side, quantity, **kwargs)
        else:
            raise NotImplementedError(f"Order type {order_type} not supported")
    
    async def place_limit_order(self, symbol: Symbol, side: Side, quantity: float, price: float, **kwargs) -> Order:
        """Place a limit order."""
        if not self.private:
            raise RuntimeError("Private exchange not available")
        return await self.private.place_limit_order(symbol, side, quantity, price, **kwargs)
    
    async def place_market_order(self, symbol: Symbol, side: Side, quantity: float, **kwargs) -> Order:
        """Place a market order."""
        if not self.private:
            raise RuntimeError("Private exchange not available")
        return await self.private.place_market_order(symbol, side, quantity, **kwargs)
    
    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> Order:
        """Cancel an order."""
        if not self.private:
            raise RuntimeError("Private exchange not available")
        return await self.private.cancel_order(symbol, order_id)
    
    async def get_order_status(self, symbol: Symbol, order_id: OrderId) -> Order:
        """Get order status."""
        if not self.private:
            raise RuntimeError("Private exchange not available")
        return await self.private.get_order(symbol, order_id)
    
    async def get_order_history(self, symbol: Optional[Symbol] = None, limit: int = 100) -> List[Order]:
        """Get order history."""
        if not self.private:
            raise RuntimeError("Private exchange not available")
        return await self.private.get_order_history(symbol, limit)
    
    async def get_balance(self, asset: AssetName) -> AssetBalance:
        """Get asset balance."""
        if not self.private:
            raise RuntimeError("Private exchange not available")
        balances = self.private.balances
        return balances.get(asset, AssetBalance(asset=asset, available=0.0, locked=0.0, total=0.0))
    
    async def get_balances(self) -> Dict[AssetName, AssetBalance]:
        """Get all balances."""
        if not self.private:
            raise RuntimeError("Private exchange not available")
        return self.private.balances
    
    async def withdraw(self, request: WithdrawalRequest) -> WithdrawalResponse:
        """Submit withdrawal request."""
        if not self.private:
            raise RuntimeError("Private exchange not available")
        return await self.private.withdraw(request)
    
    async def get_withdrawal_status(self, withdrawal_id: str) -> WithdrawalResponse:
        """Get withdrawal status."""
        if not self.private:
            raise RuntimeError("Private exchange not available")
        return await self.private.get_withdrawal_status(withdrawal_id)
    
    async def get_withdrawal_history(self, asset: Optional[AssetName] = None, limit: int = 100) -> List[WithdrawalResponse]:
        """Get withdrawal history."""
        if not self.private:
            raise RuntimeError("Private exchange not available")
        return await self.private.get_withdrawal_history(asset, limit)
    
    # Context manager support
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def close(self):
        """Close both exchanges."""
        close_tasks = []
        
        if self.public:
            close_tasks.append(self.public.close())
        if self.private:
            close_tasks.append(self.private.close())
        
        if close_tasks:
            import asyncio
            await asyncio.gather(*close_tasks, return_exceptions=True)
    
    # Connection and status methods
    
    def is_connected(self) -> bool:
        """Check if exchange is connected."""
        public_connected = self.public.is_connected if self.public else False
        private_connected = self.private.is_connected if self.private else True  # Not required
        return public_connected and private_connected
    
    def get_connection_status(self) -> Dict:
        """Get detailed connection status."""
        return {
            "public_connected": self.public.is_connected if self.public else False,
            "private_connected": self.private.is_connected if self.private else None,
            "has_public": self.public is not None,
            "has_private": self.private is not None
        }
    
    # Legacy compatibility methods
    
    async def initialize(self, symbols: Optional[List[Symbol]] = None):
        """Initialize exchange (legacy compatibility)."""
        # Exchanges should already be initialized by factory
        if self.logger:
            self.logger.info("Adapter initialize called - exchanges already initialized by factory")
    
    @property
    def name(self) -> str:
        """Get exchange name."""
        if hasattr(self.public, '_config'):
            return self.public._config.name
        return "unknown"
    
    @property
    def exchange_type(self) -> str:
        """Get exchange type."""
        if hasattr(self.public, '_config'):
            return getattr(self.public._config, 'exchange_type', 'spot')
        return "spot"
    
    def get_trading_fees(self) -> Dict:
        """Get trading fees (if available)."""
        if self.private and hasattr(self.private, 'get_trading_fees'):
            return self.private.get_trading_fees()
        return {"maker": 0.001, "taker": 0.001}  # Default fallback
    
    def get_performance_stats(self) -> Dict:
        """Get performance statistics."""
        stats = {}
        
        if self.public and hasattr(self.public, 'get_orderbook_stats'):
            stats.update(self.public.get_orderbook_stats())
        
        if self.private and hasattr(self.private, 'get_trading_stats'):
            stats.update(self.private.get_trading_stats())
        
        return stats


class LegacyInterfaceWarning:
    """Helper class for issuing migration warnings."""
    
    @staticmethod
    def warn_unified_interface_usage(component_name: str):
        """Issue warning about unified interface usage."""
        warnings.warn(
            f"{component_name} is using deprecated unified interface. "
            f"Consider migrating to composite pattern (CompositePublicExchange + CompositePrivateExchange)",
            DeprecationWarning,
            stacklevel=3
        )
    
    @staticmethod
    def suggest_migration_path(current_usage: str, suggested_replacement: str):
        """Suggest specific migration path."""
        warnings.warn(
            f"Migration suggestion: Replace '{current_usage}' with '{suggested_replacement}'",
            UserWarning,
            stacklevel=3
        )