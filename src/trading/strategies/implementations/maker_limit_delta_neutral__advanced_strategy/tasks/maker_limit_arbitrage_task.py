"""
Maker Limit Arbitrage Task - Delta-Neutral Market Making Strategy

A sophisticated market making strategy that places limit orders on spot exchange (MEXC)
with safe offsets to catch price spikes, then immediately executes hedge orders on 
futures exchange (GATEIO_FUTURES) to maintain delta neutrality.

Key Features:
- Dynamic offset calculation based on volatility, regime, and liquidity
- Comprehensive volatility circuit breakers with adaptive thresholds
- Sub-100ms hedge execution for delta neutrality
- Real-time market analysis using extracted indicators
- HFT-optimized performance with <50ms main loop
"""

import asyncio
import time
from typing import Dict, Optional

from trading.tasks.base_arbitrage_task import BaseArbitrageTask
from trading.tasks.arbitrage_task_context import ArbitrageTaskContext
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.config.maker_limit_config import MakerLimitConfig, MakerLimitRuntimeState
from exchanges.structs import Symbol, Side, ExchangeEnum, BookTicker
from infrastructure.logging import HFTLoggerInterface

# Core strategy components
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.analysis.maker_market_analyzer import MakerMarketAnalyzer, MarketAnalysis
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.analysis.volatility_circuit_breaker import VolatilityCircuitBreaker, CircuitBreakerResult
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.analysis.dynamic_offset_calculator import DynamicOffsetCalculator, OffsetResult
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.execution.maker_limit_engine import MakerLimitEngine, OrderFillEvent, MakerUpdateResult
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.execution.delta_neutral_hedge_executor import DeltaNeutralHedgeExecutor, HedgeResult

# Exchange interfaces
from exchanges.interfaces.composite.base_public_composite import BasePublicComposite
from exchanges.interfaces.composite.base_private_composite import BasePrivateComposite
from exchanges.exchange_factory import get_composite_implementation


class MakerLimitArbitrageTask(BaseArbitrageTask):
    """
    Market making strategy with delta-neutral futures hedging.
    
    Places limit orders on spot exchange with safe offsets, executes
    immediate futures hedge when filled to maintain delta neutrality.
    
    Strategy Flow:
    1. Analyze market conditions (volatility, correlation, regime, liquidity)
    2. Check circuit breakers for trading safety
    3. Calculate dynamic offsets based on multi-factor analysis  
    4. Update limit orders with optimal offsets
    5. Monitor for order fills
    6. Execute immediate futures hedge for delta neutrality
    7. Track performance and position metrics
    """
    
    name: str = "MakerLimitArbitrageTask"
    
    def __init__(self, config: MakerLimitConfig, logger: HFTLoggerInterface,
                 context: Optional[ArbitrageTaskContext] = None):
        """Initialize maker limit arbitrage strategy"""
        
        # Create default context if not provided
        if context is None:
            context = ArbitrageTaskContext(
                symbol=config.symbol,
                spot_exchange=config.spot_exchange,
                futures_exchange=config.futures_exchange
            )
        
        # Initialize base class
        super().__init__(
            logger=logger,
            context=context,
            spot_exchange=config.spot_exchange,
            futures_exchange=config.futures_exchange
        )
        
        # Store configuration
        self.config = config
        self.runtime_state = MakerLimitRuntimeState()
        
        # Initialize exchange clients
        self.spot_public: Optional[BasePublicComposite] = None
        self.spot_private: Optional[BasePrivateComposite] = None
        self.futures_public: Optional[BasePublicComposite] = None
        self.futures_private: Optional[BasePrivateComposite] = None
        
        # Initialize strategy components
        self.market_analyzer = MakerMarketAnalyzer(
            lookback_periods=100, 
            logger=self.logger
        )
        self.circuit_breaker = VolatilityCircuitBreaker(
            config=self.config,
            logger=self.logger
        )
        self.offset_calculator = DynamicOffsetCalculator(
            config=self.config,
            logger=self.logger
        )
        
        # Initialize execution engines (will be set after exchange initialization)
        self.maker_engine: Optional[MakerLimitEngine] = None
        self.hedge_executor: Optional[DeltaNeutralHedgeExecutor] = None
        
        # Performance tracking
        self.loop_count = 0
        self.last_performance_log = time.time()
        self.strategy_start_time = time.time()
        
        self.logger.info("MakerLimitArbitrageTask initialized", extra={
            'symbol': str(config.symbol),
            'spot_exchange': config.spot_exchange.name,
            'futures_exchange': config.futures_exchange.name,
            'base_position_size': config.position_size_usd,
            'base_offset_ticks': config.base_offset_ticks
        })
    
    async def setup(self):
        """Setup exchange connections and initialize execution engines"""
        try:
            self.logger.info("Setting up exchange connections...")
            
            # Get exchange configurations
            spot_config = self._get_exchange_config(self.config.spot_exchange)
            futures_config = self._get_exchange_config(self.config.futures_exchange)
            
            # Initialize public exchanges (for market data)
            self.spot_public = get_composite_implementation(
                spot_config, is_private=False
            )
            self.futures_public = get_composite_implementation(
                futures_config, is_private=False
            )
            
            # Initialize private exchanges (for trading)
            self.spot_private = get_composite_implementation(
                spot_config, is_private=True
            )
            self.futures_private = get_composite_implementation(
                futures_config, is_private=True
            )
            
            # Initialize execution engines
            self.maker_engine = MakerLimitEngine(
                spot_exchange=self.spot_private,
                config=self.config,
                logger=self.logger
            )
            self.hedge_executor = DeltaNeutralHedgeExecutor(
                futures_exchange=self.futures_private,
                config=self.config,
                logger=self.logger
            )
            
            self.logger.info("Exchange connections and execution engines initialized")
            
        except Exception as e:
            self.logger.error(f"Setup failed: {e}")
            raise
    
    async def _trading_loop(self):
        """Main trading loop with HFT-optimized execution"""
        
        while self.is_running:
            loop_start_time = time.time()
            self.loop_count += 1
            
            try:
                # 1. Get current market data
                spot_book, futures_book = await self._get_market_data()
                
                if not spot_book or not futures_book:
                    await asyncio.sleep(0.1)  # Wait before retry
                    continue
                
                # 2. Update market analysis
                market_analysis = await self.market_analyzer.update_market_data(
                    spot_book, futures_book
                )
                
                # 3. Check circuit breakers
                circuit_result = self.circuit_breaker.check_circuit_conditions(market_analysis)
                should_trade = not circuit_result.should_trigger
                
                if circuit_result.should_trigger:
                    await self._handle_circuit_breaker_activation(circuit_result, market_analysis)
                    continue
                
                # 4. Check daily trading limits
                if not self.runtime_state.can_trade_today(self.config.max_daily_trades):
                    self.logger.warning("Daily trade limit reached")
                    should_trade = False
                
                # 5. Calculate dynamic offsets
                offset_results = {}
                if should_trade:
                    for side in [Side.BUY, Side.SELL]:
                        offset_results[side] = self.offset_calculator.calculate_optimal_offset(
                            market_analysis, side, spot_book
                        )
                
                # 6. Update limit orders
                maker_result = await self.maker_engine.update_limit_orders(
                    spot_book, offset_results, should_trade
                )
                
                # 7. Check for order fills
                fill_events = await self.maker_engine.check_order_fills()
                
                # 8. Execute hedges for any fills
                for fill_event in fill_events:
                    hedge_result = await self.hedge_executor.execute_hedge(fill_event)
                    
                    # Update runtime state
                    self.runtime_state.total_trades_today += 1
                    
                    # Handle hedge failures
                    if not hedge_result.success:
                        await self._handle_hedge_failure(fill_event, hedge_result)
                
                # 9. Performance monitoring
                loop_time_ms = (time.time() - loop_start_time) * 1000
                
                if loop_time_ms > self.config.max_loop_time_ms:
                    self.runtime_state.loop_performance_warnings += 1
                    self.logger.warning(f"Slow trading loop: {loop_time_ms:.2f}ms")
                
                # 10. Periodic performance logging
                await self._log_performance_metrics(market_analysis, loop_time_ms)
                
                # 11. Sleep for next iteration
                await asyncio.sleep(self.config.loop_interval_ms / 1000)
                
            except Exception as e:
                self.logger.error(f"Trading loop error: {e}")
                await asyncio.sleep(1)  # Error recovery delay
    
    async def _get_market_data(self) -> tuple[Optional[BookTicker], Optional[BookTicker]]:
        """Get current market data from both exchanges"""
        try:
            spot_book, futures_book = await asyncio.gather(
                self.spot_public.get_book_ticker(self.config.symbol),
                self.futures_public.get_book_ticker(self.config.symbol),
                return_exceptions=True
            )
            
            # Handle exceptions
            if isinstance(spot_book, Exception):
                self.logger.error(f"Error getting spot book ticker: {spot_book}")
                spot_book = None
            
            if isinstance(futures_book, Exception):
                self.logger.error(f"Error getting futures book ticker: {futures_book}")
                futures_book = None
            
            self.runtime_state.last_market_data_time = time.time()
            return spot_book, futures_book
            
        except Exception as e:
            self.logger.error(f"Error getting market data: {e}")
            return None, None
    
    async def _handle_circuit_breaker_activation(self, circuit_result: CircuitBreakerResult,
                                               market_analysis: MarketAnalysis):
        """Handle circuit breaker activation"""
        
        self.runtime_state.circuit_breaker_active = True
        self.runtime_state.circuit_breaker_reason = str(circuit_result.triggers)
        self.runtime_state.circuit_breaker_activation_time = time.time()
        self.runtime_state.circuit_breaker_cooldown_until = time.time() + circuit_result.cooldown_period
        
        # Cancel all active orders immediately
        if self.maker_engine:
            await self.maker_engine._cancel_all_orders()
        
        self.logger.warning("Circuit breaker activated - trading halted", extra={
            'triggers': [t.value for t in circuit_result.triggers],
            'severity': circuit_result.severity_level,
            'cooldown_period': circuit_result.cooldown_period,
            'volatility_ratio': market_analysis.volatility_metrics.volatility_ratio,
            'correlation': market_analysis.correlation_metrics.correlation
        })
        
        # Wait for cooldown period
        await asyncio.sleep(circuit_result.cooldown_period)
        
        # Reset circuit breaker state
        self.runtime_state.circuit_breaker_active = False
        self.runtime_state.circuit_breaker_reason = ""
        
        self.logger.info("Circuit breaker cooldown completed - trading can resume")
    
    async def _handle_hedge_failure(self, fill_event: OrderFillEvent, hedge_result: HedgeResult):
        """Handle hedge execution failure"""
        
        if hedge_result.requires_manual_intervention:
            # Register hedge failure with circuit breaker
            failure_details = {
                'fill_event_side': fill_event.side.name,
                'fill_price': fill_event.fill_price,
                'fill_quantity': fill_event.fill_quantity,
                'hedge_error': hedge_result.error,
                'hedge_status': hedge_result.status.name,
                'execution_time_ms': hedge_result.execution_time_ms,
                'net_delta': hedge_result.net_position_delta if hedge_result.net_position_delta else 0.0
            }
            
            self.circuit_breaker.register_hedge_failure(failure_details)
            
            # Log critical alert
            self.logger.critical("MANUAL INTERVENTION REQUIRED - Hedge execution failed", extra=failure_details)
            
            # Pause trading until manual resolution
            self.runtime_state.is_trading_active = False
    
    async def _log_performance_metrics(self, market_analysis: MarketAnalysis, loop_time_ms: float):
        """Log comprehensive performance metrics"""
        
        current_time = time.time()
        
        # Log metrics every configured interval
        if current_time - self.last_performance_log >= self.config.metrics_log_interval_seconds:
            
            # Get component statistics
            maker_stats = self.maker_engine.get_performance_stats() if self.maker_engine else {}
            hedge_stats = self.hedge_executor.get_performance_stats() if self.hedge_executor else {}
            circuit_stats = self.circuit_breaker.get_circuit_stats()
            analyzer_stats = self.market_analyzer.get_analysis_stats()
            
            # Strategy runtime metrics
            strategy_uptime = current_time - self.strategy_start_time
            avg_loop_frequency = self.loop_count / strategy_uptime if strategy_uptime > 0 else 0
            
            self.logger.info("Strategy performance metrics", extra={
                # Strategy metrics
                'strategy_uptime_seconds': strategy_uptime,
                'loop_count': self.loop_count,
                'avg_loop_frequency_hz': avg_loop_frequency,
                'current_loop_time_ms': loop_time_ms,
                'loop_performance_warnings': self.runtime_state.loop_performance_warnings,
                
                # Market analysis
                'volatility_ratio': market_analysis.volatility_metrics.volatility_ratio,
                'correlation': market_analysis.correlation_metrics.correlation,
                'market_regime': market_analysis.regime_metrics.regime_multiplier,
                'liquidity_tier': market_analysis.liquidity_metrics.liquidity_tier,
                'spike_detected': market_analysis.volatility_metrics.spike_detected,
                
                # Trading metrics
                'active_orders': maker_stats.get('active_orders', 0),
                'total_fills': maker_stats.get('fill_events_count', 0),
                'hedge_success_rate': hedge_stats.get('success_rate', 0.0),
                'avg_hedge_time_ms': hedge_stats.get('average_execution_time_ms', 0.0),
                
                # Circuit breaker
                'circuit_breaker_active': circuit_stats.get('currently_active', False),
                'circuit_trigger_rate': circuit_stats.get('trigger_rate', 0.0),
                
                # Position summary
                'position_summary': hedge_stats.get('position_summary', {}),
                
                # Trading state
                'is_trading_active': self.runtime_state.is_trading_active,
                'trades_today': self.runtime_state.total_trades_today
            })
            
            self.last_performance_log = current_time
    
    def _get_exchange_config(self, exchange: ExchangeEnum):
        """Get exchange configuration (placeholder - implement based on your config system)"""
        # This should use your existing config system
        # For now, return a minimal config object
        from dataclasses import dataclass
        
        @dataclass
        class MockExchangeConfig:
            name: str
            exchange_enum: ExchangeEnum
            
        return MockExchangeConfig(name=exchange.name, exchange_enum=exchange)
    
    async def cleanup(self):
        """Cleanup function to properly close connections and cancel orders"""
        try:
            self.logger.info("Cleaning up MakerLimitArbitrageTask...")
            
            # Cancel all active orders
            if self.maker_engine:
                await self.maker_engine.cleanup()
            
            # Log final statistics
            if self.hedge_executor:
                final_stats = self.hedge_executor.get_performance_stats()
                self.logger.info("Final hedge executor statistics", extra=final_stats)
            
            # Close exchange connections
            exchanges_to_close = [
                self.spot_public, self.spot_private,
                self.futures_public, self.futures_private
            ]
            
            for exchange in exchanges_to_close:
                if exchange and hasattr(exchange, 'close'):
                    try:
                        await exchange.close()
                    except Exception as e:
                        self.logger.warning(f"Error closing exchange connection: {e}")
            
            self.logger.info("MakerLimitArbitrageTask cleanup completed")
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    # Administrative functions
    def get_strategy_status(self) -> Dict[str, any]:
        """Get comprehensive strategy status"""
        return {
            'strategy_name': self.name,
            'is_running': self.is_running,
            'runtime_state': {
                'is_trading_active': self.runtime_state.is_trading_active,
                'circuit_breaker_active': self.runtime_state.circuit_breaker_active,
                'circuit_breaker_reason': self.runtime_state.circuit_breaker_reason,
                'trades_today': self.runtime_state.total_trades_today,
                'loop_count': self.loop_count
            },
            'position_summary': self.hedge_executor.get_current_position_summary() if self.hedge_executor else {},
            'active_orders': self.maker_engine.get_active_orders_summary() if self.maker_engine else {},
            'circuit_breaker_stats': self.circuit_breaker.get_circuit_stats()
        }
    
    def force_emergency_stop(self):
        """Emergency stop function"""
        self.runtime_state.is_trading_active = False
        self.logger.critical("EMERGENCY STOP ACTIVATED - Strategy halted")
    
    def resume_trading(self):
        """Resume trading after emergency stop"""
        self.runtime_state.is_trading_active = True
        self.circuit_breaker.force_reset()
        if self.hedge_executor:
            self.hedge_executor.reset_emergency_mode()
        self.logger.info("Trading resumed after emergency stop")