"""
Test Telegram alerts for arbitrage opportunities.

Creates a mock arbitrage opportunity and processes it through the OpportunityProcessor
to verify that Telegram alerts are sent correctly.
"""

import asyncio
import logging
from infrastructure.data_structures.common import Symbol, AssetName, ExchangeName
from trading.arbitrage import ArbitrageOpportunity, OpportunityType
from trading.arbitrage import OpportunityProcessor
from trading.arbitrage import ArbitrageConfig, EngineStatistics, RiskLimits

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_mock_opportunity() -> ArbitrageOpportunity:
    """Create a mock arbitrage opportunity for testing."""
    symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
    
    return ArbitrageOpportunity(
        opportunity_id="test_opportunity_001",
        opportunity_type=OpportunityType.SPOT_SPOT,
        symbol=symbol,
        buy_exchange=ExchangeName("MEXC"),
        sell_exchange=ExchangeName("GATEIO"),
        buy_price=50000.50,
        sell_price=50125.75,
        max_quantity=0.5,
        profit_per_unit=125.25,
        total_profit_estimate=62.625,
        profit_margin_bps=250,  # 2.5% profit margin
        price_impact_estimate=0.001,
        execution_time_window_ms=30000,
        required_balance_buy=25000.25,
        required_balance_sell=0.5,
        timestamp_detected=1632150000000,
        market_depth_validated=True,
        balance_validated=True,
        risk_approved=True
    )


def create_mock_config() -> ArbitrageConfig:
    """Create mock configuration for testing."""
    risk_limits = RiskLimits(
        max_position_size_usd=10000.0,
        max_total_exposure_usd=50000.0,
        max_exchange_exposure_usd=25000.0,
        max_symbol_exposure_usd=15000.0,
        max_daily_loss_usd=5000.0,
        max_single_loss_usd=1000.0,
        min_profit_margin_bps=50,
        stop_loss_threshold_bps=200,
        max_execution_time_ms=60000,
        max_slippage_bps=25,
        max_partial_fill_ratio=0.2,
        max_concurrent_operations=5,
        max_price_deviation_bps=100,
        min_market_depth_usd=25000.0,
        max_spread_bps=500,
        volatility_circuit_breaker_bps=1000,
        max_recovery_attempts=3,
        recovery_timeout_seconds=300,
        emergency_close_threshold_bps=500
    )
    
    return ArbitrageConfig(
        engine_name="test_engine",
        enabled_opportunity_types=[OpportunityType.SPOT_SPOT],
        enabled_exchanges=[ExchangeName("MEXC"), ExchangeName("GATEIO")],
        target_execution_time_ms=30,
        opportunity_scan_interval_ms=100,
        position_monitor_interval_ms=1000,
        balance_refresh_interval_ms=5000,
        market_data_staleness_ms=100,
        risk_limits=risk_limits,
        enable_risk_checks=True,
        enable_circuit_breakers=True,
        enable_websocket_feeds=True,
        websocket_fallback_to_rest=True,
        enable_dry_run=True,
        enable_detailed_logging=True,
        enable_performance_metrics=True,
        enable_recovery_mode=True
    )


async def test_telegram_alerts():
    """Test Telegram alerts for arbitrage opportunities."""
    logger.info("🚀 Testing Telegram alerts for arbitrage opportunities")
    
    # Create mock configuration and statistics
    config = create_mock_config()
    statistics = EngineStatistics()
    
    # Initialize opportunity processor
    processor = OpportunityProcessor(config, statistics)
    
    # Create mock opportunity
    opportunity = create_mock_opportunity()
    
    logger.info("📡 Processing mock opportunity (should trigger Telegram alert)...")
    
    # Process the opportunity (this should trigger Telegram alert)
    await processor.handle_opportunity_detected(opportunity)
    
    # Wait a moment for async Telegram request
    await asyncio.sleep(2)
    
    logger.info("✅ Test completed - check Telegram channel for alerts")
    logger.info(f"Statistics: {processor.statistics.opportunities_detected} opportunities detected")


if __name__ == "__main__":
    asyncio.run(test_telegram_alerts())