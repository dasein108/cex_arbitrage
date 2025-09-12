#!/usr/bin/env python3
"""
Minimal test for MEXC exchange architectural fixes.
Tests the composition pattern and HFT policy compliance.
"""
import asyncio
import logging
from exchanges.mexc.mexc_exchange import MexcExchange
from exchanges.interface.structs import Symbol, AssetName

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_architecture_compliance():
    """Test the refactored MEXC exchange architecture."""
    
    logger.info("=== Testing MEXC Exchange Architecture Compliance ===")
    
    # Test instantiation with composition pattern
    exchange = MexcExchange()
    
    # Verify interface compliance
    logger.info(f"Exchange name: {exchange.exchange}")
    logger.info(f"Has private: {exchange.has_private}")
    
    # Test properties required by BaseExchangeInterface
    active_symbols = exchange.active_symbols
    logger.info(f"Active symbols: {len(active_symbols)}")
    
    balances = exchange.balances
    logger.info(f"Balances (HFT compliant - no caching): {len(balances)}")
    
    open_orders = exchange.open_orders  # Required property
    logger.info(f"Open orders: {len(open_orders)}")
    
    orderbook = exchange.orderbook
    logger.info(f"Current orderbook bids: {len(orderbook.bids)}, asks: {len(orderbook.asks)}")
    
    # Test performance metrics (should exclude caching metrics)
    metrics = exchange.get_performance_metrics()
    logger.info(f"Performance metrics: {metrics}")
    
    # Verify no HFT policy violations in metrics
    hft_violations = [key for key in metrics.keys() if 'cache' in key.lower()]
    if hft_violations:
        logger.error(f"HFT Policy Violation: Found caching metrics: {hft_violations}")
        return False
    else:
        logger.info("✅ HFT Policy Compliance: No caching metrics found")
    
    logger.info("✅ All architecture compliance tests passed")
    return True

async def main():
    """Main test function."""
    try:
        success = await test_architecture_compliance()
        if success:
            logger.info("🎉 MEXC Exchange architecture successfully refactored!")
        else:
            logger.error("❌ Architecture tests failed")
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())