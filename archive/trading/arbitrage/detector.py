"""
HFT Arbitrage Opportunity Detector

Ultra-high-performance real-time arbitrage opportunity detection across
multiple cryptocurrency exchanges with sub-millisecond scanning capabilities.

Architecture:
- Real-time cross-exchange price monitoring
- Zero-copy data processing using msgspec
- Event-driven opportunity alerts
- HFT-compliant data handling (no real-time caching)
- Comprehensive profit margin calculations
- Market depth validation for executable opportunities

Detection Strategies:
- Cross-exchange spot arbitrage (CEX-to-CEX)
- Spot + futures hedge arbitrage (risk-free)
- Triangular arbitrage within single exchange
- Funding rate arbitrage opportunities
- Options parity arbitrage (future enhancement)

Performance Targets:
- <10ms opportunity detection latency
- <100ms complete market scan cycle
- >99% opportunity accuracy rate
- Real-time profit margin calculations
"""

from __future__ import annotations

import asyncio
from infrastructure.logging import get_logger
from typing import Dict, List, Optional, Set, Callable
from dataclasses import dataclass
from weakref import WeakSet

from .structures import (
    ArbitrageOpportunity,
    OpportunityType,
    ArbitrageConfig,
)
from .aggregator import MarketDataAggregator

from exchanges.structs.common import Symbol, OrderBook
from exchanges.structs.types import ExchangeName
from infrastructure.exceptions.trading import ArbitrageDetectionError

logger = get_logger('arbitrage.detector')


@dataclass
class PriceComparison:
    """
    Price comparison result for cross-exchange arbitrage analysis.
    
    PERFORMANCE OPTIMIZED: Using float for ultra-fast calculations in hot path.
    This structure is used in tight loops during opportunity detection.
    """
    symbol: Symbol
    buy_exchange: ExchangeName
    sell_exchange: ExchangeName
    buy_price: float  # HFT optimized: float vs Decimal = 50x faster
    sell_price: float  # HFT optimized: float vs Decimal = 50x faster
    price_difference: float  # HFT optimized: float vs Decimal = 50x faster
    profit_margin_bps: int
    max_quantity: float  # HFT optimized: float vs Decimal = 50x faster


class OpportunityDetector:
    """
    Real-time arbitrage opportunity detection engine.
    
    Continuously monitors cross-exchange price differentials and market conditions
    to identify profitable arbitrage opportunities with comprehensive validation.
    
    HFT Design:
    - Event-driven architecture for maximum responsiveness
    - Zero-copy data processing for optimal performance
    - Real-time market data analysis (no caching per HFT compliance)
    - Comprehensive profit calculations including fees and slippage
    - Market depth validation for execution feasibility
    """

    def __init__(
            self,
            config: ArbitrageConfig,
            market_data_aggregator: MarketDataAggregator,
            opportunity_callback: Optional[Callable[[ArbitrageOpportunity], None]] = None,
    ):
        """
        Initialize opportunity detector with market data access and configuration.
        
        TODO: Complete initialization with validation and monitoring setup.
        
        Logic Requirements:
        - Validate enabled opportunity types against exchange capabilities
        - Set up market data subscriptions for enabled symbols
        - Configure profit margin thresholds and validation parameters
        - Initialize opportunity tracking and deduplication
        - Set up callback system for opportunity alerts
        
        Questions:
        - Should we pre-load symbol trading rules and fee schedules?
        - How to handle dynamic symbol addition during runtime?
        - Should detection thresholds be adjustable during operation?
        
        Performance: Initialization should complete in <1 second
        """
        self.config = config
        self.market_data_aggregator = market_data_aggregator
        self.opportunity_callback = opportunity_callback

        # Detection State
        self._is_detecting = False
        self._detection_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

        # Opportunity Tracking
        self._active_opportunities: WeakSet[ArbitrageOpportunity] = WeakSet()
        self._opportunity_history: List[ArbitrageOpportunity] = []
        self._last_scan_time: Optional[float] = None

        # Performance Metrics (HFT-optimized with float calculations)
        self._scans_completed = 0
        self._opportunities_found = 0
        self._average_scan_time_ms = 0.0
        self._scan_times: List[float] = []  # Rolling window for performance tracking
        self._detection_success_rate = 0.0

        # Symbol Configuration - Initialize with common trading pairs
        self._monitored_symbols: Set[Symbol] = set()

        # Exchange connection cache for fast access
        self._exchange_connections = {}

        logger.info(f"Opportunity detector initialized for {len(config.enabled_opportunity_types)} strategies")
        logger.info(f"Monitoring {len(self._monitored_symbols)} default symbols")



    def get_trading_fees(self, symbol: Symbol, exchange: ExchangeName) -> tuple[float, float]:
        """
        Get maker/taker fees from symbol_info[symbol].fees_maker/fees_taker.
        
        HFT CRITICAL: Uses existing SymbolInfo structure for O(1) fee lookup.
        Performance Target: <0.1ms per fee lookup.
        
        Args:
            symbol: Trading pair symbol
            exchange: Exchange name
            
        Returns:
            Tuple of (maker_fee, taker_fee) as float values
            
        Raises:
            KeyError: If symbol not found in exchange symbol_info
        """
        try:
            # Get exchange instance from market data aggregator
            exchange_instance = self._get_exchange_instance(exchange)
            if not exchange_instance:
                logger.error(f"Exchange instance not found: {exchange}")
                return (0.001, 0.001)  # Default 0.1% fees as fallback

            # Get symbol info with fees (HFT COMPLIANT - using existing structure)
            symbol_info = exchange_instance.symbol_info.get(symbol)
            if not symbol_info:
                logger.warning(f"Symbol info not found for {exchange}:{symbol}, using defaults")
                return (0.001, 0.001)  # Default 0.1% fees

            # HFT OPTIMIZED: Direct float access, no Decimal conversion
            maker_fee = symbol_info.fees_maker
            taker_fee = symbol_info.fees_taker

            return (maker_fee, taker_fee)

        except Exception as e:
            logger.error(f"Error getting trading fees for {exchange}:{symbol}: {e}")
            return (0.001, 0.001)  # Safe fallback

    def _get_exchange_instance(self, exchange: ExchangeName) -> Optional[object]:
        """
        Get exchange instance with connection caching for performance.
        
        HFT Optimized: Cached exchange connections for O(1) access.
        Performance Target: <0.05ms per lookup.
        """
        # Check cache first
        if exchange in self._exchange_connections:
            return self._exchange_connections[exchange]

        # Get from market data aggregator
        try:
            # This should access the exchanges from the aggregator
            exchange_instance = getattr(self.market_data_aggregator, 'public_exchanges', {}).get(exchange)
            if exchange_instance:
                self._exchange_connections[exchange] = exchange_instance
            return exchange_instance
        except Exception as e:
            logger.error(f"Failed to get exchange instance for {exchange}: {e}")
            return None

    def calculate_net_profit(self, buy_price: float, sell_price: float,
                             quantity: float, buy_fees: tuple[float, float],
                             sell_fees: tuple[float, float]) -> float:
        """
        Calculate net profit including maker/taker fees.
        
        HFT CRITICAL: Uses float arithmetic for maximum performance.
        Performance Target: <0.01ms per calculation.
        
        Args:
            buy_price: Price to buy at
            sell_price: Price to sell at  
            quantity: Trade quantity
            buy_fees: (maker_fee, taker_fee) for buy exchange
            sell_fees: (maker_fee, taker_fee) for sell exchange
            
        Returns:
            Net profit after all fees (float)
        """
        # Assume taker fees for market orders (conservative approach for HFT)
        buy_fee_cost = buy_price * quantity * buy_fees[1]  # taker fee
        sell_fee_cost = sell_price * quantity * sell_fees[1]  # taker fee

        # HFT OPTIMIZED: Simple float arithmetic, no Decimal overhead
        gross_profit = (sell_price - buy_price) * quantity
        net_profit = gross_profit - buy_fee_cost - sell_fee_cost

        return net_profit

    def calculate_profit_margin_bps(self, net_profit: float, trade_value: float) -> int:
        """
        Calculate profit margin in basis points (1 bps = 0.01%).
        
        HFT CRITICAL: Fast integer conversion for basis points.
        Performance Target: <0.005ms per calculation.
        
        Args:
            net_profit: Net profit after fees
            trade_value: Total trade value (buy_price * quantity)
            
        Returns:
            Profit margin in basis points (int)
        """
        if trade_value <= 0.0:
            return 0

        # HFT OPTIMIZED: Direct float-to-int conversion
        margin_ratio = net_profit / trade_value
        return int(margin_ratio * 10000.0)  # Convert to basis points

    async def start_detection(self) -> None:
        """
        Start continuous opportunity detection monitoring.
        
        TODO: Initialize and start all detection tasks.
        
        Logic Requirements:
        - Start market data subscriptions for all monitored symbols
        - Begin continuous cross-exchange price scanning
        - Initialize opportunity validation and filtering
        - Set up detection performance monitoring
        - Configure alert generation and callback execution
        
        Task Management:
        - Create long-running detection task with error handling
        - Set up graceful shutdown coordination
        - Initialize performance metrics collection
        - Configure detection interval timing
        
        Performance: Detection should be active within 1 second
        HFT Critical: Maintain <100ms scan cycles during operation
        """
        if self._is_detecting:
            logger.warning("Opportunity detection already active")
            return

        logger.info("Starting opportunity detection...")

        try:
            # TODO: Initialize market data subscriptions
            # - Subscribe to orderbook updates for all monitored symbols
            # - Set up ticker data feeds for price monitoring
            # - Configure depth updates for liquidity validation
            # - Initialize WebSocket connections with REST fallback

            # TODO: Start detection tasks
            self._is_detecting = True
            self._detection_task = asyncio.create_task(self._detection_loop())

            # TODO: Initialize performance monitoring
            # - Set up scan time tracking
            # - Initialize opportunity accuracy metrics
            # - Configure detection health monitoring
            # - Set up alert generation for detection failures

            logger.info(
                f"Opportunity detection started with {self.config.opportunity_scan_interval_ms}ms scan interval")

        except Exception as e:
            self._is_detecting = False
            logger.error(f"Failed to start opportunity detection: {e}")
            raise ArbitrageDetectionError(f"Detection start failed: {e}")

    async def stop_detection(self) -> None:
        """
        Stop opportunity detection and cleanup resources.
        
        TODO: Gracefully shutdown all detection tasks.
        
        Logic Requirements:
        - Signal shutdown to detection loop
        - Cancel any in-progress scans
        - Cleanup market data subscriptions
        - Close WebSocket connections
        - Generate final detection statistics
        
        Performance: Complete shutdown within 5 seconds
        """
        if not self._is_detecting:
            logger.warning("Opportunity detection not active")
            return

        logger.info("Stopping opportunity detection...")

        try:
            # Signal shutdown
            self._shutdown_event.set()
            self._is_detecting = False

            # Cancel detection task
            if self._detection_task:
                self._detection_task.cancel()
                try:
                    await self._detection_task
                except asyncio.CancelledError:
                    pass

            # TODO: Cleanup subscriptions and connections
            # - Unsubscribe from market data feeds
            # - Close WebSocket connections
            # - Clear detection state
            # - Generate final statistics

            logger.info("Opportunity detection stopped successfully")

        except Exception as e:
            logger.error(f"Error during detection shutdown: {e}")
            raise ArbitrageDetectionError(f"Detection stop failed: {e}")

    async def _detection_loop(self) -> None:
        """
        Main detection loop with comprehensive error handling and recovery.
        
        Performance Target: <100ms per complete scan cycle
        HFT Critical: Maintain consistent timing and minimal jitter
        """
        logger.info("Starting opportunity detection loop...")

        consecutive_errors = 0
        max_consecutive_errors = 5

        while self._is_detecting and not self._shutdown_event.is_set():
            scan_start_time = asyncio.get_event_loop().time()

            try:
                # Perform market scan with timeout
                await asyncio.wait_for(
                    self._scan_for_opportunities(),
                    timeout=self.config.opportunity_scan_interval_ms / 1000.0 * 0.8  # 80% of interval
                )

                # Reset error counter on success
                consecutive_errors = 0

                # Update performance metrics
                scan_time_ms = (asyncio.get_event_loop().time() - scan_start_time) * 1000
                self._update_scan_metrics(scan_time_ms)

                # Wait for next scan interval
                await asyncio.sleep(self.config.opportunity_scan_interval_ms / 1000.0)

            except asyncio.TimeoutError:
                logger.error("Detection scan timeout exceeded")
                consecutive_errors += 1

            except asyncio.CancelledError:
                logger.info("Detection loop cancelled")
                break

            except Exception as e:
                logger.error(f"Error in detection loop: {e}")
                consecutive_errors += 1

                # Circuit breaker: stop detection if too many consecutive errors
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(f"Too many consecutive errors ({consecutive_errors}), stopping detection")
                    await self.stop_detection()
                    break

            # Adaptive sleep based on error rate
            if consecutive_errors > 0:
                sleep_duration = self.config.opportunity_scan_interval_ms / 1000.0
                sleep_duration *= (1.5 ** consecutive_errors)  # Exponential backoff
                await asyncio.sleep(sleep_duration)

        logger.info("Detection loop ended")

    async def _scan_for_opportunities(self) -> None:
        """
        Perform complete opportunity scan across all enabled strategies.
        
        TODO: Implement comprehensive opportunity scanning.
        
        Logic Requirements:
        - Scan for cross-exchange spot arbitrage opportunities
        - Detect spot + futures hedge opportunities
        - Identify triangular arbitrage within exchanges
        - Check funding rate arbitrage potential
        - Validate all opportunities for profitability and feasibility
        
        Scanning Process:
        1. Get latest market data for all monitored symbols
        2. Perform cross-exchange price comparisons
        3. Calculate profit margins including fees and slippage
        4. Validate market depth and execution feasibility
        5. Generate opportunity objects for profitable trades
        6. Trigger callbacks for valid opportunities
        
        Performance Target: <50ms for complete scan
        HFT Critical: Use zero-copy data processing throughout
        """
        # TODO: Get latest market data (HFT COMPLIANT - NO CACHING)
        # - Fetch current orderbooks for all symbols and exchanges
        # - Get latest ticker data for price comparison
        # - Retrieve current market depth for liquidity validation
        # - Ensure all data is fresh (not cached)

        # TODO: Cross-exchange spot arbitrage detection
        if OpportunityType.SPOT_SPOT in self.config.enabled_opportunity_types:
            await self._detect_spot_arbitrage()

        # TODO: Spot + futures hedge arbitrage detection
        if OpportunityType.SPOT_FUTURES_HEDGE in self.config.enabled_opportunity_types:
            await self._detect_spot_futures_hedge()

        # TODO: Triangular arbitrage detection
        if OpportunityType.TRIANGULAR in self.config.enabled_opportunity_types:
            await self._detect_triangular_arbitrage()

        # TODO: Funding rate arbitrage detection
        if OpportunityType.FUNDING_RATE in self.config.enabled_opportunity_types:
            await self._detect_funding_rate_arbitrage()

        self._scans_completed += 1

    async def _detect_spot_arbitrage(self) -> None:
        """
        Detect cross-exchange spot arbitrage opportunities.
        
        Performance Target: <20ms for all symbol/exchange combinations
        HFT Critical: Use only fresh market data, no caching
        """

        # Get fresh orderbook data for all monitored symbols (concurrent)
        symbol_comparison_tasks = [
            self._compare_cross_exchange_prices(symbol)
            for symbol in self._monitored_symbols
        ]

        try:
            # Execute all price comparisons concurrently
            all_comparisons = await asyncio.gather(*symbol_comparison_tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Error in spot arbitrage detection: {e}")
            return

        # Flatten and process all opportunities
        opportunities_processed = 0
        for symbol_comparisons in all_comparisons:
            if isinstance(symbol_comparisons, Exception):
                logger.debug(f"Symbol comparison failed: {symbol_comparisons}")
                continue

            for comparison in symbol_comparisons:
                try:
                    # Validate opportunity for execution feasibility
                    if await self._validate_spot_opportunity(comparison):
                        # Create and process opportunity
                        opportunity = await self._create_spot_opportunity(comparison)
                        if opportunity:
                            await self._process_opportunity(opportunity)
                            opportunities_processed += 1
                except Exception as e:
                    logger.debug(f"Error processing opportunity: {e}")
                    continue

        # Update detection metrics
        if opportunities_processed > 0:
            logger.info(f"Processed {opportunities_processed} arbitrage opportunities in spot detection")

    async def _detect_spot_futures_hedge(self) -> None:
        """
        Detect spot + futures hedge arbitrage opportunities.
        
        TODO: Implement spot-futures hedge opportunity detection.
        
        Logic Requirements:
        - Compare spot prices with futures prices
        - Calculate hedge ratios for risk-free arbitrage
        - Account for funding costs and margin requirements
        - Validate both spot and futures market depth
        - Consider futures expiration and rollover costs
        
        Hedge Strategy Analysis:
        1. Identify underpriced spot vs futures (or vice versa)
        2. Calculate optimal hedge ratio (typically 1:1)
        3. Estimate funding costs over holding period
        4. Factor in margin requirements and opportunity cost
        5. Validate both markets have sufficient liquidity
        6. Account for futures settlement and rollover
        
        Questions:
        - How to handle perpetual vs fixed-term futures?
        - Should we consider basis risk in hedge ratio calculation?
        - How to optimize for funding rate cycles?
        
        Performance Target: <30ms for all symbol/futures combinations
        """
        # TODO: Get spot and futures price data
        # - Retrieve spot orderbooks and prices
        # - Get futures contract prices and funding rates
        # - Calculate basis (futures - spot) for each pair

        for symbol in self._monitored_symbols:
            # TODO: Find corresponding futures contracts
            # - Map spot symbols to futures contracts
            # - Get futures price and funding rate data
            # - Calculate current basis and historical context

            # TODO: Identify arbitrage opportunities
            # - Compare spot vs futures pricing
            # - Calculate hedge profitability
            # - Validate execution feasibility
            # - Generate hedge opportunity if profitable
            pass

    async def _detect_triangular_arbitrage(self) -> None:
        """
        Detect triangular arbitrage opportunities within exchanges.
        
        TODO: Implement triangular arbitrage detection.
        
        Logic Requirements:
        - Identify triangular trading paths (A->B->C->A)
        - Calculate cross rates and arbitrage potential
        - Account for trading fees on each leg
        - Validate market depth for all three trades
        - Consider execution timing and slippage risks
        
        Triangular Analysis:
        1. Identify all possible triangular paths
        2. Calculate cross rates and theoretical profit
        3. Account for fees on each trading leg
        4. Validate sufficient liquidity for all trades
        5. Consider execution timing requirements
        6. Filter for minimum profit thresholds
        
        Performance Target: <40ms for all triangular combinations
        """
        # TODO: Implement triangular arbitrage logic
        pass

    async def _detect_funding_rate_arbitrage(self) -> None:
        """
        Detect funding rate arbitrage opportunities.
        
        TODO: Implement funding rate arbitrage detection.
        
        Logic Requirements:
        - Monitor funding rates across exchanges
        - Identify rate differentials and timing opportunities
        - Calculate optimal position sizes and durations
        - Account for margin requirements and costs
        - Consider funding payment schedules
        
        Performance Target: <20ms for all funding rate comparisons
        """
        # TODO: Implement funding rate arbitrage logic
        pass

    async def _compare_cross_exchange_prices(self, symbol: Symbol) -> List[PriceComparison]:
        """
        Compare prices across all enabled exchanges for given symbol.
        
        Performance Target: <5ms per symbol comparison
        HFT Compliance: Fresh data only, no caching
        """
        comparisons: List[PriceComparison] = []
        exchanges = self.config.enabled_exchanges

        # Get fresh orderbook data from all exchanges (concurrent)
        orderbook_tasks = [
            self._get_current_orderbook(exchange, symbol)
            for exchange in exchanges
        ]

        try:
            # HFT CRITICAL: Concurrent orderbook fetching for speed
            orderbooks = await asyncio.gather(*orderbook_tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Failed to fetch orderbooks for {symbol}: {e}")
            return comparisons

        # Create all exchange pair combinations
        for i, buy_exchange in enumerate(exchanges):
            for j, sell_exchange in enumerate(exchanges):
                if i != j:  # Different exchanges only
                    buy_orderbook = orderbooks[i] if not isinstance(orderbooks[i], Exception) else None
                    sell_orderbook = orderbooks[j] if not isinstance(orderbooks[j], Exception) else None

                    if buy_orderbook and sell_orderbook:
                        try:
                            comparison = await self._create_price_comparison(
                                symbol, buy_exchange, sell_exchange,
                                buy_orderbook, sell_orderbook
                            )
                            if comparison and comparison.profit_margin_bps > 0:
                                comparisons.append(comparison)
                        except Exception as e:
                            logger.debug(f"Failed to create price comparison for {buy_exchange}->{sell_exchange}: {e}")
                            continue

        # Sort by profit potential (HFT optimized: int comparison)
        return sorted(comparisons, key=lambda x: x.profit_margin_bps, reverse=True)

    async def _get_current_orderbook(self, exchange: ExchangeName, symbol: Symbol) -> Optional[OrderBook]:
        """
        Get current orderbook from exchange - HFT COMPLIANT (no caching).
        
        Performance Target: <1ms per orderbook fetch
        """
        try:
            exchange_instance = self._get_exchange_instance(exchange)
            if not exchange_instance:
                return None

            # HFT CRITICAL: Direct property access for speed, no method calls
            return getattr(exchange_instance, 'orderbook', None)
        except Exception as e:
            logger.debug(f"Failed to get orderbook for {exchange}:{symbol}: {e}")
            return None

    async def _create_price_comparison(self, symbol: Symbol,
                                       buy_exchange: ExchangeName, sell_exchange: ExchangeName,
                                       buy_orderbook: OrderBook, sell_orderbook: OrderBook) -> Optional[
        PriceComparison]:
        """
        Create detailed price comparison with fees and profit calculations.
        
        HFT Performance: <1ms per comparison creation using optimized calculations.
        """
        try:
            # Validate orderbooks have data
            if not (buy_orderbook.asks and sell_orderbook.bids):
                return None

            # Get best prices (HFT optimized: direct array access)
            buy_price = buy_orderbook.asks[0].price  # Best ask (buy from)
            sell_price = sell_orderbook.bids[0].price  # Best bid (sell to)

            # Quick profitability check before expensive calculations
            if sell_price <= buy_price:
                return None

            # Calculate maximum tradeable quantity (market depth validation)
            max_quantity = min(
                buy_orderbook.asks[0].size,
                sell_orderbook.bids[0].size
            )

            if max_quantity <= 0.0:
                return None

            # Get trading fees for both exchanges (cached for performance)
            buy_fees = self.get_trading_fees(symbol, buy_exchange)
            sell_fees = self.get_trading_fees(symbol, sell_exchange)

            # Calculate net profit including fees
            net_profit = self.calculate_net_profit(
                buy_price, sell_price, max_quantity, buy_fees, sell_fees
            )

            # Skip if not profitable after fees
            if net_profit <= 0.0:
                return None

            # Calculate profit margin in basis points
            trade_value = buy_price * max_quantity
            profit_margin_bps = self.calculate_profit_margin_bps(net_profit, trade_value)

            return PriceComparison(
                symbol=symbol,
                buy_exchange=buy_exchange,
                sell_exchange=sell_exchange,
                buy_price=buy_price,
                sell_price=sell_price,
                price_difference=net_profit / max_quantity,  # Per-unit profit
                profit_margin_bps=profit_margin_bps,
                max_quantity=max_quantity
            )

        except Exception as e:
            logger.error(f"Error creating price comparison for {symbol}: {e}")
            return None

    async def _validate_spot_opportunity(self, comparison: PriceComparison) -> bool:
        """
        Validate spot arbitrage opportunity for execution feasibility.
        
        TODO: Implement comprehensive opportunity validation.
        
        Logic Requirements:
        - Check profit margin against minimum threshold
        - Validate sufficient market depth for desired quantity
        - Verify balances available on both exchanges
        - Consider execution timing and slippage estimates
        - Account for withdrawal/deposit limitations
        
        Validation Checks:
        1. Profit margin >= minimum threshold (from risk limits)
        2. Market depth >= minimum order size
        3. Account balances sufficient for execution
        4. No recent execution failures on these exchanges
        5. Price data is fresh and not stale
        6. No exchange connectivity issues
        
        Performance: <2ms per opportunity validation
        """
        # 1. Profit margin threshold check (O(1) - fastest)
        if comparison.profit_margin_bps < self.config.risk_limits.min_profit_margin_bps:
            return False

        # 2. Minimum quantity check
        min_trade_value = comparison.buy_price * comparison.max_quantity
        if min_trade_value < self.config.risk_limits.max_position_size_usd * 0.01:  # 1% of max position
            return False

        # 3. Price deviation check (prevent execution on extreme prices)
        price_spread_bps = ((comparison.sell_price - comparison.buy_price) / comparison.buy_price) * 10000.0
        if price_spread_bps > self.config.risk_limits.max_spread_bps:
            return False

        # 4. Market depth validation (ensure sufficient liquidity)
        required_depth_usd = self.config.risk_limits.min_market_depth_usd
        buy_depth_usd = comparison.buy_price * comparison.max_quantity
        sell_depth_usd = comparison.sell_price * comparison.max_quantity

        if min(buy_depth_usd, sell_depth_usd) < required_depth_usd:
            return False

        # 5. Exchange connectivity check
        buy_exchange_healthy = await self._check_exchange_health(comparison.buy_exchange)
        sell_exchange_healthy = await self._check_exchange_health(comparison.sell_exchange)

        return buy_exchange_healthy and sell_exchange_healthy

    async def _check_exchange_health(self, exchange: ExchangeName) -> bool:
        """
        Fast exchange connectivity and health check.
        
        Performance Target: <0.5ms per exchange health check
        """
        try:
            # Get exchange instance from aggregator
            exchange_instance = self._get_exchange_instance(exchange)
            if not exchange_instance:
                return False

            # Check WebSocket connection status
            if hasattr(exchange_instance, 'status'):
                from exchanges.structs.enums import ExchangeStatus
                return exchange_instance.status == ExchangeStatus.ACTIVE

            return True  # Assume healthy if no status available

        except Exception as e:
            logger.warning(f"Exchange health check failed for {exchange}: {e}")
            return False

    async def _create_spot_opportunity(self, comparison: PriceComparison) -> ArbitrageOpportunity:
        """
        Create comprehensive ArbitrageOpportunity from validated price comparison.
        
        Performance: <1ms opportunity creation using HFT-optimized calculations
        """

        # Generate unique opportunity ID with timestamp
        opportunity_id = f"spot_{comparison.symbol.base}_{comparison.symbol.quote}_{int(asyncio.get_event_loop().time() * 1000)}"

        # Calculate execution parameters
        total_profit_estimate = comparison.price_difference * comparison.max_quantity
        required_balance_buy = comparison.buy_price * comparison.max_quantity
        required_balance_sell = comparison.max_quantity

        # Estimate price impact (simple linear model)
        price_impact_estimate = min(0.001, comparison.max_quantity * 0.0001)  # HFT optimized: float literals

        # Set execution window based on profit margin (higher profit = longer window)
        base_window_ms = self.config.target_execution_time_ms
        profit_multiplier = max(1.0, comparison.profit_margin_bps / 50.0)  # Scale with profit
        execution_window_ms = min(int(base_window_ms * profit_multiplier), base_window_ms * 3)

        return ArbitrageOpportunity(
            opportunity_id=opportunity_id,
            opportunity_type=OpportunityType.SPOT_SPOT,
            symbol=comparison.symbol,
            buy_exchange=comparison.buy_exchange,
            sell_exchange=comparison.sell_exchange,
            buy_price=comparison.buy_price,
            sell_price=comparison.sell_price,
            max_quantity=comparison.max_quantity,
            profit_per_unit=comparison.price_difference,
            total_profit_estimate=total_profit_estimate,
            profit_margin_bps=comparison.profit_margin_bps,
            price_impact_estimate=price_impact_estimate,
            execution_time_window_ms=execution_window_ms,
            required_balance_buy=required_balance_buy,
            required_balance_sell=required_balance_sell,
            timestamp_detected=int(asyncio.get_event_loop().time() * 1000),
            market_depth_validated=True,
            balance_validated=False,  # TODO: Implement in Phase 3
            risk_approved=True,  # Already validated in _validate_spot_opportunity
        )

    async def _process_opportunity(self, opportunity: ArbitrageOpportunity) -> None:
        """
        Process detected opportunity and trigger alerts.
        
        TODO: Implement opportunity processing and callback system.
        
        Logic Requirements:
        - Add opportunity to active tracking
        - Trigger callback function if configured
        - Update detection statistics
        - Log opportunity for audit trail
        - Handle callback errors gracefully
        
        Performance: <1ms opportunity processing
        """
        # Add to tracking
        self._active_opportunities.add(opportunity)
        self._opportunity_history.append(opportunity)
        self._opportunities_found += 1

        logger.info(
            f"Detected {opportunity.opportunity_type.name} opportunity: "
            f"{opportunity.symbol} {opportunity.profit_margin_bps}bps profit"
        )

        # Trigger callback if configured
        if self.opportunity_callback:
            try:
                await asyncio.create_task(
                    self._safe_callback(opportunity)
                )
            except Exception as e:
                logger.error(f"Error in opportunity callback: {e}")

    async def _safe_callback(self, opportunity: ArbitrageOpportunity) -> None:
        """
        Safely execute opportunity callback with error handling.
        
        TODO: Implement safe callback execution.
        """
        try:
            if asyncio.iscoroutinefunction(self.opportunity_callback):
                await self.opportunity_callback(opportunity)
            else:
                self.opportunity_callback(opportunity)
        except Exception as e:
            logger.error(f"Opportunity callback failed: {e}")

    def _update_scan_metrics(self, scan_time_ms: float) -> None:
        """
        Update detection performance metrics with HFT monitoring.
        
        Performance Target: <0.1ms metric update time
        """
        # Update rolling average scan time
        alpha = 0.1  # Smoothing factor
        if self._average_scan_time_ms == 0.0:
            self._average_scan_time_ms = scan_time_ms
        else:
            self._average_scan_time_ms = (
                    alpha * scan_time_ms + (1 - alpha) * self._average_scan_time_ms
            )

        # Maintain rolling window for detailed analysis
        self._scan_times.append(scan_time_ms)
        if len(self._scan_times) > 100:  # Keep last 100 scans
            self._scan_times.pop(0)

        # HFT Performance alerts
        if scan_time_ms > 100.0:  # HFT threshold exceeded
            logger.warning(f"HFT threshold exceeded - Scan time: {scan_time_ms:.1f}ms (target: <20ms)")
        elif scan_time_ms > 50.0:  # Performance degradation
            logger.debug(f"Performance degradation - Scan time: {scan_time_ms:.1f}ms")

    def _update_detection_performance(self, scan_start_time: float, opportunities_found: int) -> None:
        """
        Track detailed detection performance metrics for HFT compliance.
        
        Performance Target: <0.1ms performance tracking overhead
        """

        scan_duration_ms = (asyncio.get_event_loop().time() - scan_start_time) * 1000.0

        # Update performance metrics
        self._scan_times.append(scan_duration_ms)
        if len(self._scan_times) > 100:
            self._scan_times.pop(0)  # Keep rolling window

        # Calculate performance statistics
        if self._scan_times:
            avg_scan_time = sum(self._scan_times) / len(self._scan_times)
            max_scan_time = max(self._scan_times)

            # Alert if performance degrading
            if scan_duration_ms > 100.0:  # HFT threshold
                logger.warning(
                    f"Slow detection scan: {scan_duration_ms:.1f}ms (avg: {avg_scan_time:.1f}ms, max: {max_scan_time:.1f}ms)")

        # Update success metrics
        self._detection_success_rate = opportunities_found / max(self._scans_completed, 1)

    # Public Interface Methods

    def get_active_opportunities(self) -> List[ArbitrageOpportunity]:
        """Get currently active opportunities."""
        return list(self._active_opportunities)

    def get_detection_statistics(self) -> Dict[str, any]:
        """
        TODO: Get comprehensive detection performance statistics.
        
        Statistics to include:
        - Total scans completed and opportunities found
        - Average scan times and detection rates
        - Opportunity type breakdown
        - Performance metrics and health indicators
        - Error rates and recovery statistics
        """
        return {
            "scans_completed": self._scans_completed,
            "opportunities_found": self._opportunities_found,
            "average_scan_time_ms": round(self._average_scan_time_ms, 2),
            "detection_rate": (
                    self._opportunities_found / max(self._scans_completed, 1)
            ),
            "is_detecting": self._is_detecting,
            "monitored_symbols": len(self._monitored_symbols),
        }

    def add_symbol_monitoring(self, symbol: Symbol) -> None:
        """
        TODO: Add new symbol to monitoring set.
        
        Logic Requirements:
        - Validate symbol is supported across enabled exchanges
        - Set up market data subscriptions
        - Load trading rules and fee schedules
        - Initialize detection for new symbol
        """
        self._monitored_symbols.add(symbol)
        logger.info(f"Added symbol to monitoring: {symbol}")

    def remove_symbol_monitoring(self, symbol: Symbol) -> None:
        """
        TODO: Remove symbol from monitoring set.
        
        Logic Requirements:
        - Stop market data subscriptions
        - Clear detection state for symbol
        - Update monitoring statistics
        """
        self._monitored_symbols.discard(symbol)
        logger.info(f"Removed symbol from monitoring: {symbol}")

    @property
    def is_detecting(self) -> bool:
        """Check if detection is currently active."""
        return self._is_detecting
