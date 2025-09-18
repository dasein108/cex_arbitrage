"""
HFT Arbitrage Market Data Aggregator

Real-time market data synchronization and aggregation across multiple
cex with sub-millisecond data processing and HFT compliance.

Architecture:
- Real-time cross-exchange data synchronization
- Zero-copy data processing with msgspec
- WebSocket primary with REST fallback
- HFT-compliant data handling (no real-time caching)
- Event-driven data distribution
- Sub-millisecond data aggregation

Data Sources:
- Real-time orderbook updates via WebSocket
- Ticker data for price monitoring
- Trade data for market activity analysis
- Symbol information and trading rules
- Exchange status and connectivity monitoring

Performance Targets:
- <10ms cross-exchange data synchronization
- <1ms data processing and aggregation
- <5ms data distribution to subscribers
- >99.9% data accuracy and freshness
- Sub-second failover to backup data sources
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional, Set, Callable, Any
from dataclasses import dataclass
from weakref import WeakSet

from .structures import ArbitrageConfig

from structs.common import (
    Symbol,
    OrderBook,
    Ticker,
    Trade,
    SymbolInfo,
)
from interfaces.cex.base import BasePublicExchangeInterface
from structs.common import ExchangeName
from core.exceptions.exchange import BaseExchangeError as MarketDataError


logger = logging.getLogger(__name__)


@dataclass
class MarketDataSnapshot:
    """
    Cross-exchange market data snapshot for arbitrage analysis.
    
    HFT Design: Immutable snapshot with microsecond timestamps
    for precise cross-exchange timing analysis.
    """
    symbol: Symbol
    exchange_data: Dict[ExchangeName, 'ExchangeDataSnapshot']
    aggregated_timestamp: int  # Microseconds since epoch
    data_age_ms: float  # Age of oldest data in snapshot
    is_synchronized: bool  # True if all cex have fresh data


@dataclass
class ExchangeDataSnapshot:
    """
    Single exchange data snapshot with comprehensive market information.
    
    Contains all market data needed for arbitrage opportunity detection
    with precise timing and freshness validation.
    """
    exchange: ExchangeName
    orderbook: Optional[OrderBook]
    ticker: Optional[Ticker]
    recent_trades: List[Trade]
    symbol_info: Optional[SymbolInfo]
    timestamp: int  # Microseconds since epoch
    websocket_connected: bool
    data_latency_ms: float


class MarketDataAggregator:
    """
    Real-time market data aggregation system for arbitrage operations.
    
    Aggregates and synchronizes market data across multiple cex
    with HFT-compliant data processing and distribution.
    
    HFT Design:
    - Real-time data aggregation without caching (HFT compliant)
    - Sub-millisecond cross-exchange synchronization
    - Event-driven data distribution to subscribers
    - Automatic failover between WebSocket and REST
    - Comprehensive data quality monitoring
    """
    
    def __init__(
        self,
        config: ArbitrageConfig,
        exchanges: Dict[ExchangeName, BasePublicExchangeInterface],
        data_update_callback: Optional[Callable[[MarketDataSnapshot], None]] = None,
    ):
        """
        Initialize market data aggregator with exchange connections.
        
        TODO: Complete initialization with data aggregation setup.
        
        Logic Requirements:
        - Set up data subscriptions for all cex
        - Initialize cross-exchange data synchronization
        - Configure WebSocket connections with REST fallback
        - Set up data quality monitoring and validation
        - Initialize event-driven data distribution system
        
        Questions:
        - Should we maintain separate data streams per symbol?
        - How to handle cex with different update frequencies?
        - Should we implement data compression for high-frequency updates?
        
        Performance: Initialization should complete in <2 seconds
        """
        self.config = config
        self.public_exchanges = exchanges
        self.data_update_callback = data_update_callback
        
        # Data Aggregation State
        self._latest_snapshots: Dict[Symbol, MarketDataSnapshot] = {}
        self._exchange_snapshots: Dict[ExchangeName, Dict[Symbol, ExchangeDataSnapshot]] = {}
        self._aggregation_active = False
        
        # Data Subscriptions
        self._subscribed_symbols: Set[Symbol] = set()
        self._data_subscribers: WeakSet = WeakSet()
        self._aggregation_lock = asyncio.Lock()
        
        # Connection Management
        self._websocket_tasks: Dict[ExchangeName, asyncio.Task] = {}
        self._rest_fallback_tasks: Dict[ExchangeName, asyncio.Task] = {}
        self._shutdown_event = asyncio.Event()
        
        # Performance Metrics
        self._data_updates_processed = 0
        self._cross_exchange_syncs = 0
        self._websocket_reconnections = 0
        self._rest_fallback_activations = 0
        self._average_aggregation_time_ms = 0.0
        
        # Data Quality Monitoring
        self._stale_data_alerts = 0
        self._data_synchronization_failures = 0
        self._exchange_connectivity_issues = {}
        
        logger.info(f"Market data aggregator initialized for {len(exchanges)} cex")
    
    async def start_aggregation(self, symbols: Set[Symbol]) -> None:
        """
        Start real-time market data aggregation for specified symbols.
        
        TODO: Initialize data aggregation with WebSocket connections.
        
        Logic Requirements:
        - Establish WebSocket connections to all cex
        - Subscribe to orderbook, ticker, and trade data
        - Set up REST fallback connections
        - Initialize cross-exchange data synchronization
        - Start data quality monitoring and alerting
        
        Connection Management:
        - Primary: WebSocket connections for real-time data
        - Fallback: REST polling for reliability
        - Health monitoring: Connection status and data freshness
        - Automatic failover: WebSocket to REST when needed
        - Recovery: Automatic reconnection and resynchronization
        
        Performance: Aggregation should be active within 5 seconds
        HFT Critical: Maintain sub-10ms data latency targets
        """
        if self._aggregation_active:
            logger.warning("Market data aggregation already active")
            return
        
        logger.info(f"Starting market data aggregation for {len(symbols)} symbols...")
        
        try:
            self._subscribed_symbols = symbols.copy()
            self._aggregation_active = True
            
            # Initialize exchange data tracking
            for exchange_name in self.public_exchanges:
                self._exchange_snapshots[exchange_name] = {}
                self._exchange_connectivity_issues[exchange_name] = 0
            
            # TODO: Start WebSocket connections for each exchange
            for exchange_name, exchange_client in self.public_exchanges.items():
                websocket_task = asyncio.create_task(
                    self._websocket_connection_manager(exchange_name, exchange_client, symbols)
                )
                self._websocket_tasks[exchange_name] = websocket_task
                
                # Start REST fallback monitoring
                rest_task = asyncio.create_task(
                    self._rest_fallback_manager(exchange_name, exchange_client, symbols)
                )
                self._rest_fallback_tasks[exchange_name] = rest_task
            
            # Start cross-exchange data synchronization
            sync_task = asyncio.create_task(self._data_synchronization_loop())
            self._websocket_tasks["sync"] = sync_task
            
            logger.info(f"Market data aggregation started for {len(self.public_exchanges)} cex")
            
        except Exception as e:
            self._aggregation_active = False
            logger.error(f"Failed to start market data aggregation: {e}")
            raise MarketDataError(f"Aggregation start failed: {e}")
    
    async def stop_aggregation(self) -> None:
        """
        Stop market data aggregation and cleanup connections.
        
        TODO: Gracefully shutdown aggregation with connection cleanup.
        
        Logic Requirements:
        - Signal shutdown to all connection tasks
        - Close WebSocket connections gracefully
        - Cancel REST polling tasks
        - Clear data subscriptions and state
        - Generate final aggregation statistics
        
        Performance: Complete shutdown within 10 seconds
        """
        if not self._aggregation_active:
            logger.warning("Market data aggregation not active")
            return
        
        logger.info("Stopping market data aggregation...")
        
        try:
            self._shutdown_event.set()
            self._aggregation_active = False
            
            # Cancel all connection tasks
            all_tasks = {**self._websocket_tasks, **self._rest_fallback_tasks}
            for task in all_tasks.values():
                task.cancel()
            
            # Wait for tasks to complete
            await asyncio.gather(
                *all_tasks.values(),
                return_exceptions=True
            )
            
            # Clear state
            self._websocket_tasks.clear()
            self._rest_fallback_tasks.clear()
            self._latest_snapshots.clear()
            self._exchange_snapshots.clear()
            
            logger.info("Market data aggregation stopped successfully")
            
        except Exception as e:
            logger.error(f"Error during aggregation shutdown: {e}")
            raise MarketDataError(f"Aggregation stop failed: {e}")
    
    # HFT IMPROVEMENT: Add cex methods for SimpleArbitrageEngine compatibility
    
    async def initialize(self, symbols: Set[Symbol]) -> None:
        """
        Initialize market data aggregator with symbols.
        
        HFT COMPLIANT: Wrapper method for SimpleArbitrageEngine compatibility.
        Delegates to start_aggregation() for actual implementation.
        
        Args:
            symbols: Set of trading symbols to monitor
        
        Performance: <100ms initialization time
        """
        await self.start_aggregation(symbols)
    
    async def stop(self) -> None:
        """
        Stop market data aggregator.
        
        HFT COMPLIANT: Wrapper method for SimpleArbitrageEngine compatibility.
        Delegates to stop_aggregation() for actual implementation.
        
        Performance: <10s graceful shutdown
        """
        await self.stop_aggregation()
    
    async def _websocket_connection_manager(
        self,
        exchange_name: ExchangeName,
        exchange_client: BasePublicExchangeInterface,
        symbols: Set[Symbol],
    ) -> None:
        """
        Manage WebSocket connections for exchange data feeds.
        
        TODO: Implement WebSocket connection management with auto-reconnection.
        
        Logic Requirements:
        - Establish WebSocket connection to exchange
        - Subscribe to orderbook, ticker, and trade streams
        - Handle connection failures and reconnections
        - Process incoming data and update snapshots
        - Monitor connection health and data freshness
        
        Data Processing:
        - Real-time orderbook updates
        - Ticker price updates
        - Trade data for market activity
        - Connection status monitoring
        - Data quality validation
        
        Performance Target: <5ms data processing per update
        HFT Critical: Maintain consistent data flow and minimal latency
        """
        logger.info(f"Starting WebSocket connection manager for {exchange_name}")
        
        while self._aggregation_active and not self._shutdown_event.is_set():
            try:
                # TODO: Establish WebSocket connection
                # - Connect to exchange WebSocket endpoints
                # - Subscribe to required data streams
                # - Set up message handling and parsing
                # - Monitor connection health
                
                # TODO: Process WebSocket messages
                # - Parse incoming market data messages
                # - Update exchange data snapshots
                # - Trigger cross-exchange synchronization
                # - Handle connection errors and reconnection
                
                # Placeholder: simulate WebSocket data processing
                await asyncio.sleep(0.1)  # 100ms update cycle
                
                # TODO: Update exchange data snapshots
                await self._update_exchange_data(exchange_name, symbols)
                
            except asyncio.CancelledError:
                logger.info(f"WebSocket connection manager cancelled for {exchange_name}")
                break
            except Exception as e:
                self._exchange_connectivity_issues[exchange_name] += 1
                logger.error(f"WebSocket error for {exchange_name}: {e}")
                
                # Wait before reconnection attempt
                await asyncio.sleep(5.0)
                self._websocket_reconnections += 1
    
    async def _rest_fallback_manager(
        self,
        exchange_name: ExchangeName,
        exchange_client: BasePublicExchangeInterface,
        symbols: Set[Symbol],
    ) -> None:
        """
        Manage REST API fallback for when WebSocket connections fail.
        
        TODO: Implement REST fallback with intelligent polling.
        
        Logic Requirements:
        - Monitor WebSocket connection health
        - Activate REST polling when WebSocket fails
        - Fetch orderbook, ticker, and trade data via REST
        - Optimize polling frequency based on data freshness
        - Switch back to WebSocket when connection recovers
        
        Fallback Strategy:
        - Monitor WebSocket data timestamps
        - Activate REST when data becomes stale
        - Use aggressive polling during fallback
        - Automatically resume WebSocket when available
        - Maintain data continuity during transitions
        
        Performance Target: <100ms REST polling cycle during fallback
        """
        logger.info(f"Starting REST fallback manager for {exchange_name}")
        
        while self._aggregation_active and not self._shutdown_event.is_set():
            try:
                # TODO: Monitor WebSocket health
                websocket_healthy = await self._check_websocket_health(exchange_name)
                
                if not websocket_healthy:
                    # Activate REST fallback
                    if exchange_name not in self._exchange_connectivity_issues or \
                       self._exchange_connectivity_issues[exchange_name] == 1:
                        logger.warning(f"Activating REST fallback for {exchange_name}")
                        self._rest_fallback_activations += 1
                    
                    # TODO: Fetch data via REST API
                    await self._fetch_rest_data(exchange_name, exchange_client, symbols)
                
                # Wait before next health check
                await asyncio.sleep(1.0)  # 1 second health check cycle
                
            except asyncio.CancelledError:
                logger.info(f"REST fallback manager cancelled for {exchange_name}")
                break
            except Exception as e:
                logger.error(f"REST fallback error for {exchange_name}: {e}")
                await asyncio.sleep(5.0)
    
    async def _data_synchronization_loop(self) -> None:
        """
        Cross-exchange data synchronization and aggregation loop.
        
        TODO: Implement cross-exchange data synchronization.
        
        Logic Requirements:
        - Synchronize data timestamps across cex
        - Create aggregated market data snapshots
        - Detect arbitrage-relevant price differences
        - Validate data quality and consistency
        - Distribute updates to subscribers
        
        Synchronization Process:
        1. Collect latest data from all cex
        2. Validate data freshness and quality
        3. Create synchronized snapshots by symbol
        4. Calculate cross-exchange metrics
        5. Distribute updates to subscribers
        6. Monitor synchronization performance
        
        Performance Target: <10ms synchronization cycle
        HFT Critical: Maintain consistent cross-exchange view
        """
        logger.info("Starting cross-exchange data synchronization loop")
        
        while self._aggregation_active and not self._shutdown_event.is_set():
            sync_start_time = asyncio.get_event_loop().time()
            
            try:
                # TODO: Synchronize data across cex
                for symbol in self._subscribed_symbols:
                    await self._create_synchronized_snapshot(symbol)
                
                # Update performance metrics
                sync_time_ms = (asyncio.get_event_loop().time() - sync_start_time) * 1000
                self._update_sync_metrics(sync_time_ms)
                
                # Wait for next synchronization cycle
                await asyncio.sleep(0.01)  # 10ms synchronization cycle
                
            except asyncio.CancelledError:
                logger.info("Data synchronization loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in data synchronization loop: {e}")
                self._data_synchronization_failures += 1
                await asyncio.sleep(0.1)  # Brief pause before retry
    
    async def _update_exchange_data(
        self,
        exchange_name: ExchangeName,
        symbols: Set[Symbol],
    ) -> None:
        """
        Update exchange data snapshots with latest market data.
        
        TODO: Implement exchange data snapshot updates.
        
        Logic Requirements:
        - Fetch latest orderbook data from exchange
        - Get current ticker information
        - Retrieve recent trade data
        - Update exchange data snapshots
        - Validate data quality and freshness
        
        HFT CRITICAL: This data is NEVER cached - always fresh from exchange
        Performance Target: <50ms data update per exchange
        """
        for symbol in symbols:
            try:
                # TODO: Fetch fresh market data (HFT COMPLIANT - NO CACHING)
                # - Get orderbook data
                # - Fetch ticker information
                # - Retrieve recent trades
                # - Update exchange snapshot
                
                # Create exchange data snapshot
                snapshot = ExchangeDataSnapshot(
                    exchange=exchange_name,
                    orderbook=None,  # TODO: Fetch orderbook
                    ticker=None,     # TODO: Fetch ticker
                    recent_trades=[], # TODO: Fetch trades
                    symbol_info=None, # TODO: Get symbol info
                    timestamp=int(asyncio.get_event_loop().time() * 1000000),  # Microseconds
                    websocket_connected=True,  # TODO: Check actual connection status
                    data_latency_ms=0.0,  # TODO: Calculate actual latency
                )
                
                # Update exchange snapshots
                async with self._aggregation_lock:
                    if exchange_name not in self._exchange_snapshots:
                        self._exchange_snapshots[exchange_name] = {}
                    self._exchange_snapshots[exchange_name][symbol] = snapshot
                
                self._data_updates_processed += 1
                
            except Exception as e:
                logger.error(f"Failed to update data for {exchange_name} {symbol}: {e}")
    
    async def _create_synchronized_snapshot(self, symbol: Symbol) -> None:
        """
        Create synchronized market data snapshot across all cex.
        
        TODO: Implement cross-exchange data synchronization.
        
        Logic Requirements:
        - Collect data from all cex for symbol
        - Validate data freshness and synchronization
        - Create aggregated snapshot with timing information
        - Calculate cross-exchange metrics and differences
        - Trigger data distribution callbacks
        
        Synchronization Validation:
        - Check data timestamps for synchronization
        - Validate data quality and completeness
        - Handle missing or stale data from cex
        - Calculate data age and synchronization metrics
        
        Performance Target: <5ms snapshot creation
        """
        async with self._aggregation_lock:
            exchange_data = {}
            current_time = int(asyncio.get_event_loop().time() * 1000000)  # Microseconds
            oldest_data_age_ms = 0.0
            is_synchronized = True
            
            # Collect data from all cex
            for exchange_name in self.public_exchanges:
                if (exchange_name in self._exchange_snapshots and 
                    symbol in self._exchange_snapshots[exchange_name]):
                    
                    exchange_snapshot = self._exchange_snapshots[exchange_name][symbol]
                    exchange_data[exchange_name] = exchange_snapshot
                    
                    # Calculate data age
                    data_age_ms = (current_time - exchange_snapshot.timestamp) / 1000.0
                    oldest_data_age_ms = max(oldest_data_age_ms, data_age_ms)
                    
                    # Check synchronization (data older than threshold)
                    if data_age_ms > self.config.market_data_staleness_ms:
                        is_synchronized = False
                else:
                    is_synchronized = False
            
            # Create synchronized snapshot
            if exchange_data:  # Only create if we have data from at least one exchange
                snapshot = MarketDataSnapshot(
                    symbol=symbol,
                    exchange_data=exchange_data,
                    aggregated_timestamp=current_time,
                    data_age_ms=oldest_data_age_ms,
                    is_synchronized=is_synchronized,
                )
                
                self._latest_snapshots[symbol] = snapshot
                self._cross_exchange_syncs += 1
                
                # Trigger data update callback
                if self.data_update_callback:
                    try:
                        await asyncio.create_task(
                            self._safe_data_callback(snapshot)
                        )
                    except Exception as e:
                        logger.error(f"Data update callback failed: {e}")
    
    async def _check_websocket_health(self, exchange_name: ExchangeName) -> bool:
        """
        Check WebSocket connection health for exchange.
        
        TODO: Implement WebSocket health monitoring.
        
        Logic Requirements:
        - Check connection status and responsiveness
        - Validate data freshness and update frequency
        - Monitor for connection errors and timeouts
        - Return health status for fallback decisions
        """
        # TODO: Implement actual WebSocket health check
        # - Check connection status
        # - Validate data timestamps
        # - Monitor update frequency
        # - Detect connection issues
        
        return True  # Placeholder
    
    async def _fetch_rest_data(
        self,
        exchange_name: ExchangeName,
        exchange_client: BasePublicExchangeInterface,
        symbols: Set[Symbol],
    ) -> None:
        """
        Fetch market data via REST API during WebSocket fallback.
        
        TODO: Implement REST data fetching with optimized polling.
        
        Logic Requirements:
        - Fetch orderbook data via REST API
        - Get ticker information for all symbols
        - Retrieve recent trade data
        - Update exchange data snapshots
        - Optimize polling frequency based on data freshness
        
        Performance Target: <200ms REST data fetch per exchange
        """
        try:
            for symbol in symbols:
                # TODO: Fetch data via REST API (HFT COMPLIANT - NO CACHING)
                # - Get orderbook
                # - Fetch ticker
                # - Get recent trades
                # - Update snapshots
                
                # Placeholder: simulate REST data fetch
                await self._update_exchange_data(exchange_name, {symbol})
                
        except Exception as e:
            logger.error(f"Failed to fetch REST data for {exchange_name}: {e}")
    
    async def _safe_data_callback(self, snapshot: MarketDataSnapshot) -> None:
        """Safely execute data update callback."""
        try:
            if asyncio.iscoroutinefunction(self.data_update_callback):
                await self.data_update_callback(snapshot)
            else:
                self.data_update_callback(snapshot)
        except Exception as e:
            logger.error(f"Data update callback error: {e}")
    
    def _update_sync_metrics(self, sync_time_ms: float) -> None:
        """Update synchronization performance metrics."""
        alpha = 0.1
        if self._average_aggregation_time_ms == 0:
            self._average_aggregation_time_ms = sync_time_ms
        else:
            self._average_aggregation_time_ms = (
                alpha * sync_time_ms + (1 - alpha) * self._average_aggregation_time_ms
            )
    
    # Public Interface Methods
    
    def get_latest_snapshot(self, symbol: Symbol) -> Optional[MarketDataSnapshot]:
        """
        Get latest synchronized market data snapshot for symbol.
        
        TODO: Implement snapshot retrieval with freshness validation.
        
        Performance Target: <1ms snapshot retrieval
        HFT Critical: Return only fresh, synchronized data
        """
        return self._latest_snapshots.get(symbol)
    
    def get_all_snapshots(self) -> Dict[Symbol, MarketDataSnapshot]:
        """Get all latest market data snapshots."""
        return self._latest_snapshots.copy()
    
    def add_symbol_subscription(self, symbol: Symbol) -> None:
        """
        Add new symbol to market data subscriptions.
        
        TODO: Implement dynamic symbol subscription.
        
        Logic Requirements:
        - Add symbol to subscription set
        - Update exchange data subscriptions
        - Initialize data tracking for symbol
        - Start data collection and synchronization
        """
        self._subscribed_symbols.add(symbol)
        logger.info(f"Added symbol subscription: {symbol}")
    
    def remove_symbol_subscription(self, symbol: Symbol) -> None:
        """
        Remove symbol from market data subscriptions.
        
        TODO: Implement symbol subscription removal.
        
        Logic Requirements:
        - Remove symbol from subscription set
        - Clean up data tracking for symbol
        - Update exchange subscriptions
        - Clear snapshot data
        """
        self._subscribed_symbols.discard(symbol)
        self._latest_snapshots.pop(symbol, None)
        
        # Clear from exchange snapshots
        for exchange_snapshots in self._exchange_snapshots.values():
            exchange_snapshots.pop(symbol, None)
        
        logger.info(f"Removed symbol subscription: {symbol}")
    
    def get_aggregation_statistics(self) -> Dict[str, Any]:
        """Get comprehensive market data aggregation statistics."""
        return {
            "data_updates_processed": self._data_updates_processed,
            "cross_exchange_syncs": self._cross_exchange_syncs,
            "websocket_reconnections": self._websocket_reconnections,
            "rest_fallback_activations": self._rest_fallback_activations,
            "average_aggregation_time_ms": round(self._average_aggregation_time_ms, 2),
            "stale_data_alerts": self._stale_data_alerts,
            "data_sync_failures": self._data_synchronization_failures,
            "subscribed_symbols": len(self._subscribed_symbols),
            "active_snapshots": len(self._latest_snapshots),
            "aggregation_active": self._aggregation_active,
            "connectivity_issues": dict(self._exchange_connectivity_issues),
        }
    
    @property
    def is_aggregating(self) -> bool:
        """Check if market data aggregation is active."""
        return self._aggregation_active
    
    @property
    def subscribed_symbols(self) -> Set[Symbol]:
        """Get set of currently subscribed symbols."""
        return self._subscribed_symbols.copy()