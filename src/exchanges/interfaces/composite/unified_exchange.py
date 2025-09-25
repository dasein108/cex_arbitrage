"""
Unified Composite Exchange Interface

Combines public and private exchange functionality into a single, coherent interface
that handles both market data observation and trade execution for arbitrage operations.

The unified design eliminates interface duplication and provides a clear separation:
- Market data operations (public) for orderbook construction and price observation
- Trading operations (private) for order execution and account management
- Combined functionality for arbitrage strategies that need both capabilities
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, AsyncIterator
from contextlib import asynccontextmanager

from exchanges.structs.common import (
    Symbol, AssetBalance, Order, Position, Trade, OrderBook, Ticker, Kline,
    WithdrawalRequest, WithdrawalResponse, SymbolsInfo
)
from exchanges.structs.types import AssetName, OrderId
from exchanges.structs import Side, OrderType, TimeInForce
from config.structs import ExchangeConfig
from infrastructure.logging import HFTLoggerInterface, get_exchange_logger


class UnifiedCompositeExchange(ABC):
    """
    Unified exchange interface combining public and private functionality.
    
    This interface serves as the single point of integration for exchanges,
    providing both market data capabilities and trading operations in one
    coherent interface optimized for arbitrage trading.
    
    Key Design Principles:
    1. **Single Interface**: One interface per exchange eliminates complexity
    2. **Market Data + Trading**: Combined functionality for arbitrage strategies
    3. **HFT Optimized**: Sub-50ms execution targets throughout
    4. **Resource Management**: Proper async context manager support
    5. **Performance Tracking**: Built-in metrics for all operations
    """
    
    def __init__(self, 
                 config: ExchangeConfig, 
                 symbols: Optional[List[Symbol]] = None,
                 logger: Optional[HFTLoggerInterface] = None):
        """
        Initialize unified exchange.
        
        Args:
            config: Exchange configuration with credentials
            symbols: Symbols to initialize for trading/market data
            logger: Optional logger instance
        """
        self.config = config
        self.symbols = symbols or []
        self.logger = logger or get_exchange_logger(config.name.lower(), 'unified')
        
        # State management
        self._initialized = False
        self._connected = False
        
        # Performance metrics
        self._operation_count = 0
        self._last_operation_time = 0.0
        
        self.logger.info("Unified exchange initialized",
                        exchange=config.name,
                        symbol_count=len(self.symbols),
                        has_credentials=config.has_credentials())
    
    # ========================================
    # Lifecycle Management
    # ========================================
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize exchange connections and load initial data.
        
        This method should:
        1. Establish REST and WebSocket connections
        2. Load symbols info and trading rules
        3. Subscribe to required market data streams
        4. Load account data if credentials are provided
        5. Set up any required background tasks
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close all connections and clean up resources.
        
        Should ensure proper cleanup of:
        - REST client sessions
        - WebSocket connections
        - Background tasks
        - Cached data
        """
        pass
    
    async def __aenter__(self) -> 'UnifiedCompositeExchange':
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
    
    @asynccontextmanager
    async def trading_session(self) -> AsyncIterator['UnifiedCompositeExchange']:
        """
        Context manager for trading sessions.
        
        Usage:
            async with exchange.trading_session() as ex:
                # Exchange is fully initialized and ready
                orderbook = ex.get_orderbook(symbol)
                order = await ex.place_limit_order(...)
        """
        try:
            await self.initialize()
            yield self
        finally:
            await self.close()
    
    # ========================================
    # Market Data Operations (Public)
    # ========================================
    
    @property
    @abstractmethod
    def symbols_info(self) -> SymbolsInfo:
        """Get symbols information and trading rules."""
        pass
    
    @property
    @abstractmethod
    def active_symbols(self) -> List[Symbol]:
        """Get currently active symbols for market data."""
        pass
    
    @abstractmethod
    def get_orderbook(self, symbol: Symbol) -> Optional[OrderBook]:
        """
        Get current orderbook for symbol.
        
        Returns cached orderbook data from WebSocket streams.
        HFT COMPLIANT: <1ms access time.
        """
        pass
    
    @abstractmethod
    def get_ticker(self, symbol: Symbol) -> Optional[Ticker]:
        """Get 24hr ticker statistics for symbol."""
        pass
    
    @abstractmethod
    async def get_klines(self, 
                        symbol: Symbol, 
                        interval: str, 
                        limit: int = 500) -> List[Kline]:
        """Get historical klines/candlestick data."""
        pass
    
    @abstractmethod
    async def get_recent_trades(self, symbol: Symbol, limit: int = 100) -> List[Trade]:
        """Get recent trade history for symbol."""
        pass
    
    # Market data streaming
    @abstractmethod
    async def add_symbols(self, symbols: List[Symbol]) -> None:
        """Add symbols for market data streaming."""
        pass
    
    @abstractmethod
    async def remove_symbols(self, symbols: List[Symbol]) -> None:
        """Remove symbols from market data streaming.""" 
        pass
    
    # ========================================
    # Trading Operations (Private)
    # ========================================
    
    # REMOVED: Properties that encourage caching of real-time trading data
    # These have been replaced with async methods that enforce fresh API calls
    # 
    # HFT SAFETY RULE: Never cache real-time trading data (balances, orders, positions)
    # All trading data must be fetched fresh from API to prevent execution on stale data
    
    # Trading Data Access (HFT SAFE - Fresh API calls only)
    @abstractmethod
    async def get_balances(self) -> Dict[str, AssetBalance]:
        """
        Get current account balances with fresh API call.
        
        HFT COMPLIANT: Always fetches from API, never returns cached data.
        """
        pass
    
    @abstractmethod
    async def get_open_orders(self, symbol: Optional[Symbol] = None) -> Dict[Symbol, List[Order]]:
        """
        Get current open orders with fresh API call.
        
        HFT COMPLIANT: Always fetches from API, never returns cached data.
        """
        pass
    
    @abstractmethod
    async def get_positions(self) -> Dict[Symbol, Position]:
        """
        Get current positions with fresh API call (futures/margin only).
        
        HFT COMPLIANT: Always fetches from API, never returns cached data.
        """
        pass
    
    # Order management
    @abstractmethod
    async def place_limit_order(self,
                              symbol: Symbol,
                              side: Side,
                              quantity: float,
                              price: float,
                              time_in_force: TimeInForce = TimeInForce.GTC,
                              **kwargs) -> Order:
        """
        Place a limit order.
        
        HFT TARGET: <50ms execution time.
        """
        pass
    
    @abstractmethod
    async def place_market_order(self,
                               symbol: Symbol,
                               side: Side,
                               quantity: float,
                               **kwargs) -> Order:
        """
        Place a market order.
        
        HFT TARGET: <50ms execution time.
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, symbol: Symbol, order_id: OrderId) -> bool:
        """
        Cancel an order.
        
        HFT TARGET: <50ms execution time.
        """
        pass
    
    @abstractmethod
    async def cancel_all_orders(self, symbol: Optional[Symbol] = None) -> List[bool]:
        """Cancel all orders for symbol (or all symbols)."""
        pass
    
    @abstractmethod
    async def get_order(self, order_id: OrderId, symbol: Symbol) -> Optional[Order]:
        """Get order details."""
        pass
    
    @abstractmethod
    async def get_order_history(self, 
                               symbol: Optional[Symbol] = None,
                               limit: int = 100) -> List[Order]:
        """Get historical orders."""
        pass
    
    # Batch operations for efficiency
    @abstractmethod
    async def place_multiple_orders(self, orders: List[Dict[str, Any]]) -> List[Order]:
        """Place multiple orders in batch for efficiency."""
        pass
    
    @abstractmethod
    async def cancel_multiple_orders(self, 
                                   order_cancellations: List[Dict[str, Any]]) -> List[bool]:
        """Cancel multiple orders in batch."""
        pass
    
    # ========================================
    # Withdrawal Operations
    # ========================================
    
    @abstractmethod
    async def withdraw(self, request: WithdrawalRequest) -> WithdrawalResponse:
        """Submit withdrawal request.""" 
        pass
    
    @abstractmethod
    async def cancel_withdrawal(self, withdrawal_id: str) -> bool:
        """Cancel pending withdrawal."""
        pass
    
    @abstractmethod
    async def get_withdrawal_status(self, withdrawal_id: str) -> WithdrawalResponse:
        """Get withdrawal status."""
        pass
    
    @abstractmethod
    async def get_withdrawal_history(self,
                                   asset: Optional[AssetName] = None,
                                   limit: int = 100) -> List[WithdrawalResponse]:
        """Get withdrawal history."""
        pass
    
    @abstractmethod
    async def validate_withdrawal_address(self,
                                        asset: AssetName,
                                        address: str,
                                        network: Optional[str] = None) -> bool:
        """Validate withdrawal address."""
        pass
    
    @abstractmethod
    async def get_withdrawal_limits(self,
                                  asset: AssetName,
                                  network: Optional[str] = None) -> Dict[str, float]:
        """Get withdrawal limits."""
        pass
    
    # ========================================
    # Health and Performance Monitoring
    # ========================================
    
    @property
    def is_connected(self) -> bool:
        """Check if exchange is connected and operational."""
        return self._connected
    
    @property
    def is_initialized(self) -> bool:
        """Check if exchange is initialized."""
        return self._initialized
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive performance statistics.
        
        Returns:
            Dict with operation counts, latency stats, success rates, etc.
        """
        return {
            "exchange": self.config.name,
            "connected": self.is_connected,
            "initialized": self.is_initialized,
            "total_operations": self._operation_count,
            "active_symbols": len(self.active_symbols),
            "has_credentials": self.config.has_credentials(),
            "last_operation_time": self._last_operation_time
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get detailed health status for monitoring.
        
        Returns:
            Dict with connection status, data freshness, error rates, etc.
        """
        return {
            "healthy": self.is_connected and self.is_initialized,
            "connections": {
                "rest": True,  # Should be implemented by subclasses
                "websocket": True  # Should be implemented by subclasses  
            },
            "data_freshness": {
                "orderbooks": True,  # Should be implemented by subclasses
                "balances": True,    # Should be implemented by subclasses
                "orders": True       # Should be implemented by subclasses
            }
        }
    
    # ========================================
    # Event Handlers (Optional Override)  
    # ========================================
    
    async def on_orderbook_update(self, symbol: Symbol, orderbook: OrderBook) -> None:
        """Handle orderbook update events."""
        pass
    
    async def on_trade_update(self, symbol: Symbol, trade: Trade) -> None:
        """Handle new trade events."""
        pass
    
    async def on_order_update(self, order: Order) -> None:
        """Handle order status updates."""
        pass
    
    async def on_balance_update(self, asset: str, balance: AssetBalance) -> None:
        """Handle balance updates."""
        pass
    
    # ========================================
    # Utility Methods
    # ========================================
    
    def _track_operation(self, operation_name: str) -> None:
        """Track operation for performance monitoring."""
        import time
        self._operation_count += 1
        self._last_operation_time = time.time()
        
        self.logger.debug("Operation tracked",
                         operation=operation_name,
                         count=self._operation_count)


# ========================================
# Exchange Factory Interface
# ========================================

class UnifiedExchangeFactory:
    """
    Simplified factory for creating unified exchange instances.
    
    Eliminates the complexity of multiple factory interfaces by providing
    a single, straightforward factory for exchange creation.
    """
    
    def __init__(self):
        self._supported_exchanges = {
            'mexc': 'exchanges.integrations.mexc.mexc_unified_exchange.MexcUnifiedExchange',
            'gateio': 'exchanges.integrations.gateio.gateio_unified_exchange.GateioUnifiedExchange'
        }
        self._active_exchanges: Dict[str, UnifiedCompositeExchange] = {}
    
    async def create_exchange(self,
                            exchange_name: str,
                            symbols: Optional[List[Symbol]] = None,
                            config: Optional[ExchangeConfig] = None) -> UnifiedCompositeExchange:
        """
        Create a unified exchange instance using config_manager pattern.
        
        Args:
            exchange_name: Exchange name (mexc, gateio, etc.)
            symbols: Optional symbols to initialize
            config: Optional exchange configuration (if not provided, loads from config_manager)
            
        Returns:
            Initialized exchange instance
        """
        if exchange_name.lower() not in self._supported_exchanges:
            raise ValueError(f"Unsupported exchange: {exchange_name}")
        
        # Get config from config_manager if not provided
        if config is None:
            from config.config_manager import get_exchange_config
            config = get_exchange_config(exchange_name.lower())
        
        # Dynamic import to avoid circular dependencies
        module_path = self._supported_exchanges[exchange_name.lower()]
        module_name, class_name = module_path.rsplit('.', 1)
        
        try:
            import importlib
            module = importlib.import_module(module_name)
            exchange_class = getattr(module, class_name)
            
            # Create and initialize exchange
            exchange = exchange_class(config=config, symbols=symbols)
            await exchange.initialize()
            
            # Track for cleanup
            self._active_exchanges[exchange_name.lower()] = exchange
            
            return exchange
            
        except ImportError as e:
            raise ImportError(f"Failed to import {exchange_name} exchange: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to create {exchange_name} exchange: {e}")
    
    async def create_multiple_exchanges(self,
                                      exchange_names: List[str],
                                      symbols: Optional[List[Symbol]] = None,
                                      exchange_configs: Optional[Dict[str, ExchangeConfig]] = None) -> Dict[str, UnifiedCompositeExchange]:
        """
        Create multiple exchanges concurrently.
        
        Args:
            exchange_names: List of exchange names to create
            symbols: Optional symbols for all exchanges
            exchange_configs: Optional dict mapping exchange names to configs (loads from config_manager if not provided)
            
        Returns:
            Dict mapping exchange names to initialized exchanges
        """
        import asyncio
        
        async def create_single(name: str) -> tuple[str, UnifiedCompositeExchange]:
            try:
                config = exchange_configs.get(name) if exchange_configs else None
                exchange = await self.create_exchange(name, symbols, config)
                return name, exchange
            except Exception as e:
                logger = get_exchange_logger('factory', 'unified')
                logger.error(f"Failed to create {name} exchange: {e}")
                return name, None
        
        # Create all exchanges concurrently
        tasks = [create_single(name) for name in exchange_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Build result dict, filtering out failed exchanges
        exchanges = {}
        for result in results:
            if isinstance(result, tuple) and result[1] is not None:
                name, exchange = result
                exchanges[name] = exchange
        
        return exchanges
    
    async def close_all(self) -> None:
        """Close all managed exchanges."""
        for exchange in self._active_exchanges.values():
            try:
                await exchange.close()
            except Exception as e:
                logger = get_exchange_logger('factory', 'unified')
                logger.error(f"Error closing exchange: {e}")
        
        self._active_exchanges.clear()
    
    def get_supported_exchanges(self) -> List[str]:
        """Get list of supported exchange names."""
        return list(self._supported_exchanges.keys())
    
    @property
    def active_exchanges(self) -> Dict[str, UnifiedCompositeExchange]:
        """Get currently active exchanges."""
        return self._active_exchanges.copy()