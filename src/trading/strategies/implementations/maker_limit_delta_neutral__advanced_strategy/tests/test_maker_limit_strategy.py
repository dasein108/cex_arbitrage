"""
Comprehensive Testing Framework for Maker Limit Strategy

Test suite covering all components of the maker limit order strategy including
market analysis, circuit breakers, offset calculation, order management,
hedge execution, and integration testing.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from dataclasses import dataclass
from typing import Dict, List, Optional

# Strategy components to test
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.config.maker_limit_config import MakerLimitConfig, MakerLimitRuntimeState
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.analysis.maker_market_analyzer import (
    MakerMarketAnalyzer, MarketAnalysis, VolatilityMetrics, 
    CorrelationMetrics, RegimeMetrics, LiquidityMetrics
)
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.analysis.volatility_circuit_breaker import (
    VolatilityCircuitBreaker, CircuitBreakerResult, CircuitBreakerTrigger
)
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.analysis.dynamic_offset_calculator import DynamicOffsetCalculator, OffsetResult
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.execution.maker_limit_engine import (
    MakerLimitEngine, OrderFillEvent, OrderUpdateAction
)
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.execution.delta_neutral_hedge_executor import (
    DeltaNeutralHedgeExecutor, HedgeResult, HedgeExecutionStatus
)
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.analytics.maker_performance_monitor import MakerPerformanceMonitor, TradeRecord

# Exchange structures for testing
from exchanges.structs import Symbol, Side, ExchangeEnum, BookTicker, Order, OrderStatus


@dataclass
class MockExchangeConfig:
    """Mock exchange configuration for testing"""
    name: str
    exchange_enum: ExchangeEnum


def create_test_symbol() -> Symbol:
    """Create test symbol for testing"""
    return Symbol(base="BTC", quote="USDT", is_futures=False)


def create_test_config() -> MakerLimitConfig:
    """Create test configuration with conservative settings"""
    return MakerLimitConfig(
        symbol=create_test_symbol(),
        spot_exchange=ExchangeEnum.MEXC,
        futures_exchange=ExchangeEnum.GATEIO_FUTURES,
        base_offset_ticks=2,
        max_offset_ticks=10,
        position_size_usd=50.0,  # Small size for testing
        max_volatility_threshold=0.10,
        min_correlation=0.8,
        loop_interval_ms=100,
        hedge_execution_timeout_ms=50  # Fast timeout for testing
    )


def create_test_book_ticker(bid_price: float = 100.0, ask_price: float = 100.1,
                          bid_qty: float = 1000.0, ask_qty: float = 1000.0) -> BookTicker:
    """Create test book ticker"""
    return BookTicker(
        symbol=str(create_test_symbol()),
        bid_price=bid_price,
        ask_price=ask_price,
        bid_qty=bid_qty,
        ask_qty=ask_qty
    )


def create_test_market_analysis(volatility_ratio: float = 1.1,
                              correlation: float = 0.85,
                              is_mean_reverting: bool = True,
                              spike_detected: bool = False) -> MarketAnalysis:
    """Create test market analysis"""
    return MarketAnalysis(
        timestamp=time.time(),
        spot_price=100.0,
        futures_price=100.05,
        volatility_metrics=VolatilityMetrics(
            volatility_ratio=volatility_ratio,
            spot_volatility=0.02,
            futures_volatility=0.018,
            spike_detected=spike_detected,
            spike_intensity=1.0 if spike_detected else 0.5,
            intraday_volatility_ratio=1.05
        ),
        correlation_metrics=CorrelationMetrics(
            correlation=correlation,
            basis_volatility=0.01,
            basis_mean=0.05,
            basis_volatility_pct=0.0001,
            hedge_effectiveness=correlation > 0.7
        ),
        regime_metrics=RegimeMetrics(
            rsi=50.0,
            trend_strength=0.01,
            sma_slope=0.001,
            bb_position=0.5,
            bb_width=0.05,
            is_trending=False,
            is_mean_reverting=is_mean_reverting,
            is_high_volatility=False,
            regime_multiplier=0.7 if is_mean_reverting else 1.0
        ),
        liquidity_metrics=LiquidityMetrics(
            spot_volume_ma=1000.0,
            futures_volume_ma=1200.0,
            volume_ratio=0.83,
            hourly_futures_volume=72000.0,
            liquidity_tier='LOW',
            volume_deviation=0.1
        )
    )


def create_test_order(side: Side, price: float, quantity: float,
                     status: OrderStatus = OrderStatus.FILLED) -> Order:
    """Create test order"""
    return Order(
        order_id=f"test_order_{int(time.time())}",
        symbol=str(create_test_symbol()),
        side=side,
        order_type="LIMIT",
        quantity=quantity,
        price=price,
        status=status,
        filled_quantity=quantity if status == OrderStatus.FILLED else 0.0,
        average_price=price if status == OrderStatus.FILLED else None
    )


def create_test_fill_event(side: Side, price: float, quantity: float) -> OrderFillEvent:
    """Create test order fill event"""
    order = create_test_order(side, price, quantity)
    return OrderFillEvent(
        side=side,
        order=order,
        fill_price=price,
        fill_quantity=quantity,
        timestamp=time.time()
    )


class TestMakerLimitConfig:
    """Test maker limit configuration"""
    
    def test_config_validation(self):
        """Test configuration parameter validation"""
        config = create_test_config()
        
        # Test valid configuration
        assert config.base_offset_ticks >= 1
        assert config.max_offset_ticks >= config.base_offset_ticks
        assert config.position_size_usd > 0
        assert 0 < config.min_correlation <= 1
        
    def test_invalid_config_raises_error(self):
        """Test that invalid configurations raise errors"""
        with pytest.raises(ValueError):
            MakerLimitConfig(
                symbol=create_test_symbol(),
                spot_exchange=ExchangeEnum.MEXC,
                futures_exchange=ExchangeEnum.GATEIO_FUTURES,
                base_offset_ticks=0  # Invalid: must be >= 1
            )
        
        with pytest.raises(ValueError):
            MakerLimitConfig(
                symbol=create_test_symbol(),
                spot_exchange=ExchangeEnum.MEXC,
                futures_exchange=ExchangeEnum.GATEIO_FUTURES,
                min_correlation=1.5  # Invalid: must be <= 1
            )
    
    def test_liquidity_multiplier(self):
        """Test liquidity tier multiplier calculation"""
        config = create_test_config()
        
        assert config.get_liquidity_multiplier('ULTRA_LOW') == 1.5
        assert config.get_liquidity_multiplier('LOW') == 1.3
        assert config.get_liquidity_multiplier('MEDIUM') == 1.0
        assert config.get_liquidity_multiplier('HIGH') == 0.8
        assert config.get_liquidity_multiplier('UNKNOWN') == 1.0  # Default
    
    def test_delta_tolerance_check(self):
        """Test delta neutrality tolerance checking"""
        config = create_test_config()
        
        position_size = 100.0
        
        # Within tolerance
        assert config.is_within_delta_tolerance(0.5, position_size) == True
        
        # Outside tolerance
        assert config.is_within_delta_tolerance(2.0, position_size) == False
        
        # Zero position size
        assert config.is_within_delta_tolerance(1.0, 0.0) == True


class TestMakerMarketAnalyzer:
    """Test market analysis framework"""
    
    @pytest.mark.asyncio
    async def test_market_analysis_basic(self):
        """Test basic market analysis functionality"""
        analyzer = MakerMarketAnalyzer(lookback_periods=50)
        
        spot_book = create_test_book_ticker(100.0, 100.1)
        futures_book = create_test_book_ticker(100.05, 100.15)
        
        # First update (insufficient data)
        analysis = await analyzer.update_market_data(spot_book, futures_book)
        
        assert analysis.spot_price == 100.05  # Mid price
        assert analysis.futures_price == 100.10  # Mid price
        
        # Volatility metrics should have defaults for insufficient data
        assert analysis.volatility_metrics.volatility_ratio >= 0
    
    @pytest.mark.asyncio
    async def test_volatility_calculation(self):
        """Test volatility metrics calculation"""
        analyzer = MakerMarketAnalyzer(lookback_periods=50)
        
        # Add enough data points for volatility calculation
        for i in range(25):
            price_variation = 100 + (i * 0.1)  # Small price movements
            spot_book = create_test_book_ticker(price_variation, price_variation + 0.1)
            futures_book = create_test_book_ticker(price_variation + 0.05, price_variation + 0.15)
            
            analysis = await analyzer.update_market_data(spot_book, futures_book)
        
        # Should have calculated meaningful volatility metrics
        assert analysis.volatility_metrics.volatility_ratio > 0
        assert analysis.volatility_metrics.spot_volatility >= 0
        assert analysis.volatility_metrics.futures_volatility >= 0
    
    @pytest.mark.asyncio
    async def test_correlation_calculation(self):
        """Test correlation metrics calculation"""
        analyzer = MakerMarketAnalyzer(lookback_periods=30)
        
        # Add correlated price data
        for i in range(25):
            base_price = 100 + (i * 0.1)
            spot_book = create_test_book_ticker(base_price, base_price + 0.1)
            futures_book = create_test_book_ticker(base_price + 0.02, base_price + 0.12)  # Highly correlated
            
            analysis = await analyzer.update_market_data(spot_book, futures_book)
        
        # Should detect high correlation
        assert analysis.correlation_metrics.correlation > 0.8
        assert analysis.correlation_metrics.hedge_effectiveness == True
    
    @pytest.mark.asyncio
    async def test_regime_detection(self):
        """Test market regime detection"""
        analyzer = MakerMarketAnalyzer(lookback_periods=60)
        
        # Create trending market data
        for i in range(55):
            price = 100 + (i * 0.5)  # Strong upward trend
            spot_book = create_test_book_ticker(price, price + 0.1)
            futures_book = create_test_book_ticker(price + 0.05, price + 0.15)
            
            analysis = await analyzer.update_market_data(spot_book, futures_book)
        
        # Should detect trending market
        assert analysis.regime_metrics.trend_strength > 0.01
        # Note: Trending detection depends on exact implementation


class TestVolatilityCircuitBreaker:
    """Test circuit breaker system"""
    
    def test_circuit_breaker_initialization(self):
        """Test circuit breaker initialization"""
        config = create_test_config()
        circuit_breaker = VolatilityCircuitBreaker(config)
        
        assert circuit_breaker.breaker_active == False
        assert len(circuit_breaker.active_triggers) == 0
        assert circuit_breaker.check_count == 0
    
    def test_volatility_spike_trigger(self):
        """Test volatility spike circuit breaker"""
        config = create_test_config()
        circuit_breaker = VolatilityCircuitBreaker(config)
        
        # Create high volatility analysis
        high_vol_analysis = create_test_market_analysis(
            volatility_ratio=0.25,  # Above 20% threshold
            correlation=0.85
        )
        
        result = circuit_breaker.check_circuit_conditions(high_vol_analysis)
        
        assert result.should_trigger == True
        assert CircuitBreakerTrigger.VOLATILITY_SPIKE in result.triggers
        assert result.severity_level in ["HIGH", "CRITICAL"]
    
    def test_correlation_breakdown_trigger(self):
        """Test correlation breakdown circuit breaker"""
        config = create_test_config()
        circuit_breaker = VolatilityCircuitBreaker(config)
        
        # Create low correlation analysis
        low_corr_analysis = create_test_market_analysis(
            volatility_ratio=1.0,
            correlation=0.5  # Below 60% threshold
        )
        
        result = circuit_breaker.check_circuit_conditions(low_corr_analysis)
        
        assert result.should_trigger == True
        assert CircuitBreakerTrigger.CORRELATION_BREAKDOWN in result.triggers
    
    def test_emergency_spike_trigger(self):
        """Test emergency spike detection"""
        config = create_test_config()
        circuit_breaker = VolatilityCircuitBreaker(config)
        
        # Create spike analysis
        spike_analysis = create_test_market_analysis(
            volatility_ratio=1.0,
            correlation=0.85,
            spike_detected=True
        )
        # Manually set high spike intensity
        spike_analysis.volatility_metrics.spike_intensity = 3.5  # >3.0 threshold
        
        result = circuit_breaker.check_circuit_conditions(spike_analysis)
        
        assert result.should_trigger == True
        assert CircuitBreakerTrigger.EMERGENCY_SPIKE in result.triggers
        assert result.requires_immediate_stop() == True
    
    def test_circuit_breaker_cooldown(self):
        """Test circuit breaker cooldown mechanism"""
        config = create_test_config()
        circuit_breaker = VolatilityCircuitBreaker(config)
        
        # Trigger circuit breaker
        high_vol_analysis = create_test_market_analysis(volatility_ratio=0.25)
        result1 = circuit_breaker.check_circuit_conditions(high_vol_analysis)
        assert result1.should_trigger == True
        
        # Immediate re-check should still be in cooldown
        normal_analysis = create_test_market_analysis(volatility_ratio=1.0)
        result2 = circuit_breaker.check_circuit_conditions(normal_analysis)
        assert result2.should_trigger == True  # Still in cooldown
        assert result2.recommended_action == "WAIT_COOLDOWN"


class TestDynamicOffsetCalculator:
    """Test dynamic offset calculation"""
    
    def test_offset_calculation_basic(self):
        """Test basic offset calculation"""
        config = create_test_config()
        calculator = DynamicOffsetCalculator(config)
        
        market_analysis = create_test_market_analysis()
        book = create_test_book_ticker()
        
        # Test buy side offset
        buy_offset = calculator.calculate_optimal_offset(
            market_analysis, Side.BUY, book
        )
        
        assert buy_offset.offset_ticks >= 1
        assert buy_offset.offset_ticks <= config.max_offset_ticks
        assert buy_offset.target_price < book.bid_price  # Buy below current bid
        assert buy_offset.safety_score >= 0
        assert buy_offset.safety_score <= 1
    
    def test_offset_volatility_adjustment(self):
        """Test offset adjustment for high volatility"""
        config = create_test_config()
        calculator = DynamicOffsetCalculator(config)
        book = create_test_book_ticker()
        
        # Normal volatility
        normal_analysis = create_test_market_analysis(volatility_ratio=1.0)
        normal_offset = calculator.calculate_optimal_offset(
            normal_analysis, Side.BUY, book
        )
        
        # High volatility
        high_vol_analysis = create_test_market_analysis(volatility_ratio=2.0)
        high_vol_offset = calculator.calculate_optimal_offset(
            high_vol_analysis, Side.BUY, book
        )
        
        # High volatility should result in larger offset
        assert high_vol_offset.offset_ticks >= normal_offset.offset_ticks
        assert high_vol_offset.multipliers['volatility'] > 1.0
    
    def test_offset_regime_adjustment(self):
        """Test offset adjustment for market regime"""
        config = create_test_config()
        calculator = DynamicOffsetCalculator(config)
        book = create_test_book_ticker()
        
        # Mean-reverting market
        mean_rev_analysis = create_test_market_analysis(is_mean_reverting=True)
        mean_rev_offset = calculator.calculate_optimal_offset(
            mean_rev_analysis, Side.BUY, book
        )
        
        # Should have regime multiplier applied
        assert 'regime' in mean_rev_offset.multipliers
        assert mean_rev_offset.multipliers['regime'] <= 1.0  # More aggressive in mean-reverting
    
    def test_offset_bounds_enforcement(self):
        """Test that offset stays within configured bounds"""
        config = create_test_config()
        calculator = DynamicOffsetCalculator(config)
        book = create_test_book_ticker()
        
        # Extreme conditions that might cause large offsets
        extreme_analysis = create_test_market_analysis(
            volatility_ratio=5.0,  # Extreme volatility
            correlation=0.3,       # Poor correlation
            spike_detected=True    # Emergency conditions
        )
        
        offset = calculator.calculate_optimal_offset(
            extreme_analysis, Side.BUY, book
        )
        
        # Should still respect bounds
        assert offset.offset_ticks >= 1
        assert offset.offset_ticks <= config.max_offset_ticks
    
    def test_offset_side_logic(self):
        """Test offset calculation for both buy and sell sides"""
        config = create_test_config()
        calculator = DynamicOffsetCalculator(config)
        book = create_test_book_ticker(100.0, 100.1)
        analysis = create_test_market_analysis()
        
        buy_offset = calculator.calculate_optimal_offset(analysis, Side.BUY, book)
        sell_offset = calculator.calculate_optimal_offset(analysis, Side.SELL, book)
        
        # Buy should be below bid, sell should be above ask
        assert buy_offset.target_price < book.bid_price
        assert sell_offset.target_price > book.ask_price
        
        # Both should have same tick count (symmetric strategy)
        assert buy_offset.offset_ticks == sell_offset.offset_ticks


class TestMakerLimitEngine:
    """Test market making engine"""
    
    @pytest.fixture
    def mock_spot_exchange(self):
        """Create mock spot exchange for testing"""
        exchange = AsyncMock()
        
        # Mock order placement
        async def mock_place_order(*args, **kwargs):
            return create_test_order(Side.BUY, 100.0, 1.0)
        
        exchange.place_order = mock_place_order
        
        # Mock order status
        async def mock_get_order_status(order_id):
            return create_test_order(Side.BUY, 100.0, 1.0)
        
        exchange.get_order_status = mock_get_order_status
        
        # Mock order cancellation
        async def mock_cancel_order(order_id):
            return True
        
        exchange.cancel_order = mock_cancel_order
        
        return exchange
    
    @pytest.mark.asyncio
    async def test_order_placement(self, mock_spot_exchange):
        """Test basic order placement"""
        config = create_test_config()
        engine = MakerLimitEngine(mock_spot_exchange, config, Mock())
        
        book = create_test_book_ticker()
        offset_results = {
            Side.BUY: OffsetResult(
                offset_ticks=2,
                offset_price=0.02,
                target_price=99.98,
                safety_score=0.8,
                multipliers={'test': 1.0},
                tick_size=0.01,
                base_price=book.bid_price,
                market_conditions="TEST"
            )
        }
        
        result = await engine.update_limit_orders(book, offset_results, should_trade=True)
        
        assert result.action == "ORDERS_UPDATED"
        assert Side.BUY.name in result.side_results
        assert result.side_results[Side.BUY.name].action == OrderUpdateAction.ORDER_PLACED
    
    @pytest.mark.asyncio
    async def test_order_cancellation_when_halted(self, mock_spot_exchange):
        """Test order cancellation when trading is halted"""
        config = create_test_config()
        engine = MakerLimitEngine(mock_spot_exchange, config, Mock())
        
        book = create_test_book_ticker()
        offset_results = {}
        
        result = await engine.update_limit_orders(book, offset_results, should_trade=False)
        
        assert result.action == "ORDERS_CANCELLED"
    
    @pytest.mark.asyncio
    async def test_fill_detection(self, mock_spot_exchange):
        """Test order fill detection"""
        config = create_test_config()
        engine = MakerLimitEngine(mock_spot_exchange, config, Mock())
        
        # Add a mock active order
        test_order = create_test_order(Side.BUY, 100.0, 1.0)
        engine.active_orders[Side.BUY] = test_order
        
        # Mock filled order status
        async def mock_filled_status(order_id):
            filled_order = create_test_order(Side.BUY, 100.0, 1.0, OrderStatus.FILLED)
            filled_order.average_price = 100.0
            filled_order.filled_quantity = 1.0
            return filled_order
        
        mock_spot_exchange.get_order_status = mock_filled_status
        
        fill_events = await engine.check_order_fills()
        
        assert len(fill_events) == 1
        assert fill_events[0].side == Side.BUY
        assert fill_events[0].fill_price == 100.0
        assert fill_events[0].fill_quantity == 1.0


class TestDeltaNeutralHedgeExecutor:
    """Test hedge execution system"""
    
    @pytest.fixture
    def mock_futures_exchange(self):
        """Create mock futures exchange for testing"""
        exchange = AsyncMock()
        
        # Mock successful hedge order
        async def mock_place_order(*args, **kwargs):
            return create_test_order(Side.SELL, 100.05, 1.0)
        
        exchange.place_order = mock_place_order
        
        # Mock filled hedge status
        async def mock_get_order_status(order_id):
            filled_order = create_test_order(Side.SELL, 100.05, 1.0, OrderStatus.FILLED)
            filled_order.average_price = 100.05
            filled_order.filled_quantity = 1.0
            return filled_order
        
        exchange.get_order_status = mock_get_order_status
        
        return exchange
    
    @pytest.mark.asyncio
    async def test_successful_hedge_execution(self, mock_futures_exchange):
        """Test successful hedge execution"""
        config = create_test_config()
        executor = DeltaNeutralHedgeExecutor(mock_futures_exchange, config, Mock())
        
        fill_event = create_test_fill_event(Side.BUY, 100.0, 1.0)
        
        hedge_result = await executor.execute_hedge(fill_event)
        
        assert hedge_result.success == True
        assert hedge_result.status == HedgeExecutionStatus.SUCCESS
        assert hedge_result.hedge_quantity == 1.0
        assert hedge_result.execution_time_ms > 0
        assert hedge_result.execution_time_ms < 1000  # Should be fast
    
    @pytest.mark.asyncio
    async def test_hedge_position_tracking(self, mock_futures_exchange):
        """Test position tracking during hedge execution"""
        config = create_test_config()
        executor = DeltaNeutralHedgeExecutor(mock_futures_exchange, config, Mock())
        
        # Initial position should be zero
        assert executor.net_spot_position == 0.0
        assert executor.net_futures_position == 0.0
        
        # Execute hedge for buy fill
        buy_fill = create_test_fill_event(Side.BUY, 100.0, 1.0)
        hedge_result = await executor.execute_hedge(buy_fill)
        
        # Should have long spot, short futures (delta neutral)
        assert executor.net_spot_position == 1.0
        assert executor.net_futures_position == -1.0
        assert executor._calculate_net_delta() == 0.0  # Delta neutral
    
    @pytest.mark.asyncio
    async def test_hedge_timeout_handling(self, mock_futures_exchange):
        """Test hedge execution timeout handling"""
        config = create_test_config()
        config.hedge_execution_timeout_ms = 10  # Very short timeout
        executor = DeltaNeutralHedgeExecutor(mock_futures_exchange, config, Mock())
        
        # Mock slow order status response
        async def slow_status_check(order_id):
            await asyncio.sleep(0.1)  # Longer than timeout
            return create_test_order(Side.SELL, 100.05, 1.0)
        
        mock_futures_exchange.get_order_status = slow_status_check
        
        fill_event = create_test_fill_event(Side.BUY, 100.0, 1.0)
        hedge_result = await executor.execute_hedge(fill_event)
        
        assert hedge_result.success == False
        assert hedge_result.status == HedgeExecutionStatus.TIMEOUT
        assert hedge_result.requires_manual_intervention == True


class TestIntegration:
    """Integration tests for the complete strategy"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_trade_execution(self):
        """Test complete trade execution flow"""
        config = create_test_config()
        
        # Create mock exchanges
        mock_spot = AsyncMock()
        mock_futures = AsyncMock()
        
        # Mock successful order placement and execution
        async def mock_spot_order(*args, **kwargs):
            return create_test_order(Side.BUY, 99.98, 0.5)
        
        async def mock_futures_order(*args, **kwargs):
            return create_test_order(Side.SELL, 100.05, 0.5)
        
        mock_spot.place_order = mock_spot_order
        mock_futures.place_order = mock_futures_order
        
        # Mock filled order status
        async def mock_filled_status(order_id):
            return create_test_order(Side.BUY, 99.98, 0.5, OrderStatus.FILLED)
        
        mock_spot.get_order_status = mock_filled_status
        mock_futures.get_order_status = mock_filled_status
        
        # Initialize components
        analyzer = MakerMarketAnalyzer(lookback_periods=30)
        circuit_breaker = VolatilityCircuitBreaker(config)
        offset_calculator = DynamicOffsetCalculator(config)
        maker_engine = MakerLimitEngine(mock_spot, config, Mock())
        hedge_executor = DeltaNeutralHedgeExecutor(mock_futures, config, Mock())
        
        # Simulate market data
        spot_book = create_test_book_ticker(100.0, 100.1)
        futures_book = create_test_book_ticker(100.05, 100.15)
        
        # 1. Market analysis
        market_analysis = await analyzer.update_market_data(spot_book, futures_book)
        
        # 2. Circuit breaker check
        circuit_result = circuit_breaker.check_circuit_conditions(market_analysis)
        assert circuit_result.should_trigger == False  # Should allow trading
        
        # 3. Offset calculation
        buy_offset = offset_calculator.calculate_optimal_offset(
            market_analysis, Side.BUY, spot_book
        )
        assert buy_offset.offset_ticks >= 1
        
        # 4. Order placement
        offset_results = {Side.BUY: buy_offset}
        maker_result = await maker_engine.update_limit_orders(
            spot_book, offset_results, should_trade=True
        )
        assert maker_result.action == "ORDERS_UPDATED"
        
        # 5. Simulate fill and hedge
        fill_event = create_test_fill_event(Side.BUY, 99.98, 0.5)
        hedge_result = await hedge_executor.execute_hedge(fill_event)
        
        assert hedge_result.success == True
        assert hedge_result.execution_time_ms < config.hedge_execution_timeout_ms
        
        # 6. Verify delta neutrality
        net_delta = hedge_executor._calculate_net_delta()
        assert abs(net_delta) < 0.01  # Should be approximately delta neutral
    
    def test_performance_monitoring_integration(self):
        """Test performance monitoring integration"""
        config = create_test_config()
        monitor = MakerPerformanceMonitor(config)
        
        # Test initial state
        assert monitor.metrics.total_trades == 0
        assert monitor.metrics.net_pnl == 0.0
        
        # Create test trade record
        trade_record = TradeRecord(
            timestamp=time.time(),
            spot_side="BUY",
            spot_price=100.0,
            spot_quantity=1.0,
            spot_order_id="test_001",
            hedge_success=True,
            hedge_price=100.05,
            hedge_quantity=1.0,
            hedge_execution_time_ms=25.0,
            hedge_slippage_bps=5.0,
            estimated_pnl=0.05,
            fees_paid=0.02,
            net_pnl=0.03
        )
        
        # Add trade to history
        monitor.trade_history.append(trade_record)
        
        # Test metrics calculation
        report = monitor.get_comprehensive_report()
        
        assert 'metrics' in report
        assert 'recent_performance' in report
        assert 'alerts' in report
        assert 'market_conditions' in report


if __name__ == "__main__":
    # Run basic smoke tests
    pytest.main([__file__, "-v", "--tb=short"])