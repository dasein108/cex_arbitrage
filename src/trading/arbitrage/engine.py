"""
HFT Arbitrage Engine - Main Orchestrator

Ultra-high-performance arbitrage engine designed for sub-50ms execution cycles
across multiple cryptocurrency exchanges with atomic spot + futures operations.

Architecture:
- Event-driven async/await design for maximum concurrency
- Abstract Factory pattern for exchange integration
- Finite state machine for atomic operation control
- Zero-copy data structures for optimal performance
- HFT-compliant real-time data handling (no caching)

Core Responsibilities:
- Orchestrate all arbitrage operations and components
- Manage engine lifecycle and graceful shutdown
- Coordinate cross-exchange market data aggregation
- Execute atomic spot + futures hedge operations
- Handle partial execution recovery and error management
- Enforce risk limits and circuit breaker functionality
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, AsyncIterator
from weakref import WeakSet

from .structures import (
    ArbitrageConfig,
    ArbitrageOpportunity, 
    ArbitrageState,
    ExecutionResult,
    PositionEntry,
)
from .detector import OpportunityDetector
from .position import PositionManager
from .orchestrator import OrderOrchestrator
from .state import StateController
from .risk import RiskManager
from .balance import BalanceMonitor
from .recovery import RecoveryManager
from .aggregator import MarketDataAggregator

from exchanges.interfaces.composite.spot.base_private_spot_composite import CompositePrivateExchange
from infrastructure.error_handling import TradingErrorHandler, ErrorContext
from infrastructure.exceptions.exchange import ArbitrageEngineError

# HFT Logger Integration
from infrastructure.logging import get_exchange_logger, HFTLoggerInterface


class ArbitrageEngine:
    """
    Main arbitrage engine orchestrating all HFT arbitrage operations.
    
    Coordinates opportunity detection, risk management, order execution,
    and position recovery across multiple exchanges with sub-50ms targets.
    
    HFT Design Principles:
    - Single-threaded async for zero locking overhead
    - Event-driven architecture for maximum responsiveness
    - Zero-copy data structures throughout hot paths
    - Fail-fast error propagation for trading safety
    - No real-time data caching per HFT compliance requirements
    """
    
    def __init__(
        self,
        config: ArbitrageConfig,
        exchanges: Dict[str, CompositePrivateExchange],
        logger: Optional[HFTLoggerInterface] = None,
    ):
        """
        Initialize arbitrage engine with exchange connections and configuration.
        
        Uses unified BasePrivateExchangeInterface that encapsulates both public and private functionality.
        
        TODO: Comprehensive initialization with validation.
        
        Logic Requirements:
        - Validate configuration against available exchanges
        - Initialize all component subsystems
        - Establish exchange connections and health checks
        - Set up event loops and monitoring tasks
        - Configure logging and performance metrics
        
        Questions:
        - Should initialization include warm-up trading to test connectivity?
        - How to handle partial exchange connectivity during startup?
        - Should we pre-load symbol mappings and trading rules?
        
        Performance: Initialization should complete in <5 seconds
        
        Args:
            config: Arbitrage engine configuration
            exchanges: Dictionary of exchange instances (name -> BasePrivateExchangeInterface)
                      Each exchange encapsulates both public and private API functionality
            logger: Optional HFT logger injection
        """
        self.config = config
        self.exchanges = exchanges
        
        # Use injected logger or create arbitrage-specific logger
        if logger is None:
            logger = get_exchange_logger('arbitrage', 'engine')
        
        self.logger = logger
        
        # Core Engine State
        self._state = ArbitrageState.IDLE
        self._shutdown_event = asyncio.Event()
        self._active_opportunities: WeakSet[ArbitrageOpportunity] = WeakSet()
        self._execution_history: List[ExecutionResult] = []
        
        # Component Initialization
        # TODO: Initialize all subsystem components
        self.market_data_aggregator: Optional[MarketDataAggregator] = None
        self.opportunity_detector: Optional[OpportunityDetector] = None
        self.risk_manager: Optional[RiskManager] = None
        self.position_manager: Optional[PositionManager] = None
        self.order_orchestrator: Optional[OrderOrchestrator] = None
        self.state_controller: Optional[StateController] = None
        self.balance_monitor: Optional[BalanceMonitor] = None
        self.recovery_manager: Optional[RecoveryManager] = None
        
        # HFT IMPROVEMENT: Use unified EngineStatistics for consistent state management
        from .types import EngineStatistics
        self.statistics = EngineStatistics()
        
        # HFT IMPROVEMENT: Initialize OpportunityProcessor for callback handling
        from .opportunity_processor import OpportunityProcessor
        self.opportunity_processor = OpportunityProcessor(self.config, self.statistics)
        
        # Initialize composition-based error handler for trading operations
        self._trading_error_handler = TradingErrorHandler(
            logger=self.logger,
            max_retries=2,  # Conservative for trading safety
            base_delay=0.5  # Fast recovery for HFT
        )
        
        # Log comprehensive initialization with structured data
        self.logger.info("ArbitrageEngine initialized",
                        engine_name=config.engine_name,
                        exchange_count=len(exchanges),
                        exchange_names=list(exchanges.keys()),
                        symbols_configured=len(getattr(config, 'symbols', [])),
                        state=self._state.name)
        
        # Track component initialization metrics
        self.logger.metric("arbitrage_engines_initialized", 1,
                          tags={"engine_name": config.engine_name, "exchange_count": str(len(exchanges))})
    
    async def initialize(self) -> None:
        """
        Initialize all engine components and establish connections.
        
        TODO: Complete component initialization and validation.
        
        Logic Requirements:
        - Initialize market data aggregator with exchange connections
        - Set up opportunity detector with enabled strategies
        - Configure risk manager with position limits
        - Initialize position manager with recovery capabilities
        - Set up order orchestrator with exchange routing
        - Initialize state controller with state machine
        - Configure balance monitor with refresh intervals
        - Set up recovery manager with error handling
        
        Error Handling:
        - Validate all exchange connections before proceeding
        - Ensure all components initialized successfully
        - Set up health check monitoring for exchange connections
        - Configure circuit breakers and emergency shutdown procedures
        
        Performance: Complete initialization in <5 seconds
        HFT Critical: All components must be ready for sub-50ms execution
        """
        logger.info("Initializing arbitrage engine components...")
        
        try:
            # Initialize MarketDataAggregator
            logger.info("Initializing market data aggregator...")
            self.market_data_aggregator = MarketDataAggregator(
                config=self.config,
                exchanges=self.exchanges,
                data_update_callback=self.opportunity_processor.handle_market_data_update
            )
            
            # Initialize OpportunityDetector with market data feed
            logger.info("Initializing HFT opportunity detector...")
            self.opportunity_detector = OpportunityDetector(
                config=self.config,
                market_data_aggregator=self.market_data_aggregator,
                opportunity_callback=self._handle_opportunity_detected_via_processor
            )
            
            # TODO: Initialize RiskManager
            # - Load risk limits and circuit breaker configurations
            # - Set up real-time position monitoring
            # - Initialize P&L tracking and exposure calculations
            # - Configure emergency shutdown triggers
            
            # TODO: Initialize PositionManager
            # - Set up position tracking across all exchanges
            # - Configure atomic operation coordination
            # - Initialize hedge ratio calculations
            # - Set up position aging and cleanup
            
            # TODO: Initialize OrderOrchestrator
            # - Set up exchange routing and order placement
            # - Configure decimal precision matching
            # - Initialize execution timing optimization
            # - Set up partial fill handling
            
            # TODO: Initialize StateController
            # - Configure finite state machine transitions
            # - Set up atomic operation state tracking
            # - Initialize recovery state management
            # - Configure state persistence and recovery
            
            # TODO: Initialize BalanceMonitor
            # - Set up real-time balance tracking
            # - Configure balance refresh intervals (HFT compliant)
            # - Initialize cross-exchange balance synchronization
            # - Set up insufficient balance detection
            
            # TODO: Initialize RecoveryManager
            # - Configure partial execution recovery strategies
            # - Set up error handling and retry logic
            # - Initialize position unwinding capabilities
            # - Configure manual intervention alerts
            
            logger.info("All arbitrage engine components initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize arbitrage engine: {e}")
            raise ArbitrageEngineError(f"Engine initialization failed: {e}")
    
    async def start(self) -> None:
        """
        Start the arbitrage engine and begin market monitoring.
        
        TODO: Start all monitoring and execution tasks.
        
        Logic Requirements:
        - Start market data aggregation tasks
        - Begin opportunity detection scanning
        - Start risk monitoring and circuit breaker checks
        - Initialize balance monitoring and refresh
        - Begin position monitoring and aging
        - Start performance metrics collection
        
        Task Management:
        - Create long-running tasks for each component
        - Set up task exception handling and restart logic
        - Configure graceful shutdown coordination
        - Initialize health check monitoring
        
        Performance: Engine should be operational within 1 second of start
        HFT Critical: All monitoring loops must maintain <100ms cycles
        """
        if self._state != ArbitrageState.IDLE:
            raise ArbitrageEngineError(f"Cannot start engine in state: {self._state}")
        
        logger.info("Starting arbitrage engine...")
        
        try:
            # Update engine state
            self._state = ArbitrageState.DETECTING
            
            # TODO: Start market data aggregation
            # - Begin WebSocket connections to all exchanges
            # - Start orderbook synchronization tasks
            # - Initialize price feed aggregation
            # - Set up connection health monitoring
            
            # TODO: Start opportunity detection
            # - Begin cross-exchange price monitoring
            # - Start profit margin calculations
            # - Initialize market depth validation
            # - Set up opportunity alert generation
            
            # TODO: Start risk monitoring
            # - Begin real-time position monitoring
            # - Start P&L tracking and exposure calculations
            # - Initialize circuit breaker monitoring
            # - Set up risk alert generation
            
            # TODO: Start balance monitoring
            # - Begin balance refresh cycles
            # - Start cross-exchange balance synchronization
            # - Initialize balance alert generation
            # - Set up insufficient balance detection
            
            # TODO: Start position monitoring
            # - Begin position aging and health checks
            # - Start hedge ratio monitoring
            # - Initialize stale position detection
            # - Set up position recovery alerts
            
            # TODO: Start performance monitoring
            # - Begin execution time tracking
            # - Start latency measurement
            # - Initialize success rate monitoring
            # - Set up performance degradation alerts
            
            logger.info(f"Arbitrage engine started successfully in {self.config.target_execution_time_ms}ms target mode")
            
        except Exception as e:
            self._state = ArbitrageState.FAILED
            logger.error(f"Failed to start arbitrage engine: {e}")
            raise ArbitrageEngineError(f"Engine start failed: {e}")
    
    async def stop(self) -> None:
        """
        Gracefully stop the arbitrage engine and close all positions.
        
        TODO: Implement graceful shutdown with position safety.
        
        Logic Requirements:
        - Signal shutdown to all running tasks
        - Stop accepting new arbitrage opportunities
        - Complete any in-progress executions
        - Close all open positions safely
        - Disconnect from all exchanges gracefully
        - Persist final state and performance metrics
        
        Safety Requirements:
        - Ensure no positions are left orphaned
        - Complete any pending recovery operations
        - Verify all orders are properly closed
        - Generate final P&L and performance reports
        
        Performance: Complete graceful shutdown within 30 seconds
        HFT Critical: Must not abandon open positions during shutdown
        """
        if self._state in (ArbitrageState.COMPLETED, ArbitrageState.FAILED):
            logger.warning("Engine already stopped")
            return
        
        logger.info("Stopping arbitrage engine...")
        
        try:
            # Signal shutdown to all components
            self._shutdown_event.set()
            
            # TODO: Stop accepting new opportunities
            # - Set state to prevent new opportunity execution
            # - Cancel any pending opportunity detection
            # - Stop market data feeds for new opportunities
            
            # TODO: Complete in-progress executions
            # - Wait for current executions to complete
            # - Force completion of critical execution stages
            # - Handle timeouts and partial executions
            
            # TODO: Close all open positions
            # - Identify all open positions across exchanges
            # - Execute position closing orders
            # - Verify all positions are properly closed
            # - Handle any closing errors or partial fills
            
            # TODO: Shutdown all components
            # - Stop market data aggregation tasks
            # - Shutdown opportunity detection
            # - Stop risk monitoring
            # - Shutdown balance monitoring
            # - Close exchange connections
            
            # TODO: Generate final reports
            # - Calculate total P&L for session
            # - Generate performance metrics summary
            # - Log final position status
            # - Persist execution history
            
            self._state = ArbitrageState.COMPLETED
            logger.info("Arbitrage engine stopped successfully")
            
        except Exception as e:
            self._state = ArbitrageState.FAILED
            logger.error(f"Error during engine shutdown: {e}")
            raise ArbitrageEngineError(f"Engine shutdown failed: {e}")
    
    async def execute_opportunity(self, opportunity: ArbitrageOpportunity) -> ExecutionResult:
        """
        Execute an arbitrage opportunity with atomic spot + futures coordination.
        
        TODO: Implement complete opportunity execution pipeline.
        
        Logic Requirements:
        - Validate opportunity is still profitable and executable
        - Perform pre-execution risk checks and balance validation
        - Execute atomic spot + futures operations
        - Monitor execution progress and handle partial fills
        - Coordinate hedge operations for risk-free execution
        - Handle errors and initiate recovery procedures if needed
        
        Execution Stages:
        1. Pre-execution validation (balances, risk, market conditions)
        2. Atomic order placement (spot purchase + futures hedge)
        3. Order monitoring and fill confirmation
        4. Post-execution validation and position recording
        5. Error handling and recovery if needed
        
        Performance Target: Complete execution in <50ms
        HFT Critical: Atomic operations must not leave unhedged positions
        
        Returns:
            ExecutionResult with complete execution metrics and outcomes
        """
        execution_start_time = asyncio.get_event_loop().time()
        
        logger.info(f"Executing arbitrage opportunity: {opportunity.opportunity_id}")
        
        # Use composition pattern for error handling
        context = ErrorContext(
            operation="execute_arbitrage_opportunity",
            component="arbitrage_engine", 
            metadata={
                "opportunity_id": opportunity.opportunity_id,
                "symbol": f"{opportunity.symbol.base}/{opportunity.symbol.quote}",
                "expected_profit": opportunity.expected_profit_usd,
                "buy_exchange": opportunity.buy_exchange,
                "sell_exchange": opportunity.sell_exchange
            }
        )
        
        async def _execute_arbitrage_operation():
            return await self._execute_arbitrage_core(opportunity, execution_start_time)
        
        return await self._trading_error_handler.handle_with_retry(
            operation=_execute_arbitrage_operation,
            context=context
        )
    
    async def _execute_arbitrage_core(self, opportunity: ArbitrageOpportunity, execution_start_time: float) -> ExecutionResult:
        """Execute arbitrage without error handling - clean business logic"""
        logger = self.logger
        
        # TODO: Pre-execution validation
        # - Verify opportunity is still valid (not stale)
        # - Check real-time prices match opportunity parameters
        # - Validate sufficient balances on both exchanges
        # - Perform risk management checks
        # - Verify market depth is still adequate
        
        # TODO: State management
        # - Update state controller to EXECUTING
        # - Record execution start time and parameters
        # - Set up execution timeout monitoring
        # - Initialize position tracking
        
        # TODO: Atomic order execution
        # - Place spot market order on buy exchange
        # - Simultaneously place futures hedge order (if applicable)
        # - Monitor both orders for fill confirmation
        # - Handle partial fills and order updates
        # - Ensure atomic completion or rollback
        
        # TODO: Execution monitoring
        # - Track execution progress in real-time
        # - Monitor for execution timeouts
        # - Handle partial fills and slippage
        # - Coordinate cross-exchange execution timing
        
        # TODO: Post-execution validation
        # - Verify all orders filled successfully
        # - Confirm hedge ratios are correct
        # - Calculate actual profit vs estimated
        # - Record positions and update tracking
        
        # Placeholder execution result
        execution_time_ms = int((asyncio.get_event_loop().time() - execution_start_time) * 1000)
        
        # TODO: Create comprehensive ExecutionResult
        result = ExecutionResult(
            execution_id=f"exec_{opportunity.opportunity_id}",
            opportunity_id=opportunity.opportunity_id,
            final_state=ArbitrageState.COMPLETED,
            total_execution_time_ms=execution_time_ms,
            detection_to_execution_ms=0,  # TODO: Calculate
            order_placement_time_ms=0,    # TODO: Calculate
            fill_confirmation_time_ms=0,  # TODO: Calculate
            positions_created=[],         # TODO: Populate
            realized_profit=0.0,          # TODO: Calculate
            total_fees_paid=0.0,          # TODO: Calculate
            slippage_cost=0.0,            # TODO: Calculate
            orders_placed=0,              # TODO: Track
            orders_filled=0,              # TODO: Track
            partial_fills=0,              # TODO: Track
            execution_success_rate=100.0, # TODO: Calculate
            errors_encountered=[],        # TODO: Populate
            recovery_actions_taken=[],    # TODO: Populate
            requires_manual_review=False, # TODO: Determine
        )
        
        logger.info(f"Arbitrage opportunity executed successfully in {execution_time_ms}ms")
        return result
    
    @asynccontextmanager
    async def session(self) -> AsyncIterator[ArbitrageEngine]:
        """
        Context manager for complete arbitrage engine session lifecycle.
        
        TODO: Implement comprehensive session management.
        
        Logic Requirements:
        - Initialize engine and all components
        - Start all monitoring and execution tasks
        - Yield operational engine to caller
        - Gracefully shutdown on context exit
        - Handle exceptions and ensure clean shutdown
        
        Usage:
            async with engine.session() as arb_engine:
                # Engine is fully operational
                await arb_engine.execute_opportunity(opportunity)
        
        Safety: Ensures clean shutdown even if exceptions occur
        """
        try:
            await self.initialize()
            await self.start()
            yield self
        finally:
            await self.stop()
    
    # Performance and Monitoring Methods
    
    def get_engine_statistics(self) -> Dict[str, Any]:
        """
        HFT IMPROVEMENT: Get comprehensive engine performance statistics using unified EngineStatistics.
        
        Logic Requirements:
        - Collect performance metrics from all components
        - Calculate aggregated statistics and success rates
        - Include real-time status and health indicators
        - Format data for monitoring dashboards
        
        Statistics to include:
        - Opportunities detected and executed counts
        - Average execution times and success rates
        - Total profit realized and fees paid
        - Risk metrics and circuit breaker status
        - Component health and connection status
        
        Performance: <1ms collection time, cached appropriately
        """
        # HFT IMPROVEMENT: Use unified statistics object for consistency
        stats = self.statistics.to_dict()
        
        # Add engine-specific metrics
        stats.update({
            "engine_state": self._state.name,
            "active_opportunities": len(self._active_opportunities),
            "execution_history_count": len(self._execution_history),
        })
        
        # Add processor statistics
        if hasattr(self, 'opportunity_processor'):
            stats.update(self.opportunity_processor.get_processor_statistics())
        
        return stats
    
    def get_active_positions(self) -> List[PositionEntry]:
        """
        TODO: Get all currently active positions across exchanges.
        
        Logic Requirements:
        - Query position manager for all open positions
        - Include spot and futures positions
        - Filter out closed or expired positions
        - Include position health and aging information
        
        HFT Critical: Real-time position data, no caching
        Performance: <5ms for comprehensive position query
        """
        # TODO: Implement position retrieval from position manager
        return []
    
    def calculate_current_pnl(self) -> float:
        """
        TODO: Calculate current unrealized P&L across all positions.
        
        Logic Requirements:
        - Get current market prices for all position symbols
        - Calculate unrealized P&L for each position
        - Sum total P&L across all exchanges
        - Include fees and slippage in calculations
        
        HFT Critical: Real-time market data required, no caching
        Performance: <10ms for complete P&L calculation
        """
        # TODO: Implement real-time P&L calculation
        return 0.0
    
    @property
    def is_healthy(self) -> bool:
        """
        TODO: Check overall engine health status.
        
        Logic Requirements:
        - Verify all exchange connections are healthy
        - Check all component systems are operational
        - Validate no circuit breakers are triggered
        - Ensure execution performance is within targets
        
        Health Indicators:
        - Exchange connectivity status
        - WebSocket connection health
        - Average execution times within targets
        - Risk manager status
        - Position manager status
        - No critical errors in recent history
        
        Performance: <1ms health check, use cached status where appropriate
        """
        # TODO: Implement comprehensive health check
        return self._state in (ArbitrageState.IDLE, ArbitrageState.DETECTING, ArbitrageState.EXECUTING)
    
    @property
    def current_state(self) -> ArbitrageState:
        """Get current engine state."""
        return self._state
    
    async def _handle_opportunity_detected_via_processor(self, opportunity: ArbitrageOpportunity):
        """
        HFT IMPROVEMENT: Delegate opportunity handling to OpportunityProcessor.
        
        Eliminates code duplication and maintains SOLID principles by using
        dedicated processor component for all callback handling.
        """
        await self.opportunity_processor.handle_opportunity_detected(
            opportunity, 
            execute_callback=self.execute_opportunity
        )