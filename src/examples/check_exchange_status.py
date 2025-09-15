#!/usr/bin/env python3
"""
Test Exchange Status Implementation

This script tests the newly implemented status property for MEXC and Gate.io exchanges.
It demonstrates how the status changes during initialization and connection lifecycle.
"""

import asyncio
import logging

from exchanges.mexc.mexc_exchange import MexcExchange
from exchanges.gateio.gateio_exchange import GateioExchange
from structs.exchange import Symbol, AssetName, ExchangeStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def check_exchange_status(exchange_name: str = "mexc"):
    """
    Test the status property implementation for an exchange.
    
    Args:
        exchange_name: "mexc" or "gateio" to test specific exchange
    """
    logger.info(f"🚀 Testing {exchange_name.upper()} Exchange Status Implementation")
    logger.info("=" * 60)
    
    # Create exchange instance (public only, no credentials needed)
    if exchange_name.lower() == "mexc":
        exchange = MexcExchange()
        test_symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"), is_futures=False)
    else:
        exchange = GateioExchange()
        test_symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"), is_futures=False)
    
    try:
        # Test 1: Status before initialization
        logger.info("📊 Test 1: Status before initialization")
        status = exchange.status
        logger.info(f"   Status: {status.name} (Expected: INACTIVE)")
        assert status == ExchangeStatus.INACTIVE, f"Expected INACTIVE, got {status.name}"
        logger.info("   ✅ Test 1 passed!")
        
        logger.info("-" * 60)
        
        # Test 2: Status during initialization
        logger.info("📊 Test 2: Status during initialization")
        logger.info("   Initializing exchange with BTC/USDT...")
        
        # Start initialization task
        init_task = asyncio.create_task(exchange.initialize([test_symbol]))
        
        # Check status while initializing (give it a moment to start)
        await asyncio.sleep(0.5)
        status = exchange.status
        logger.info(f"   Status during init: {status.name} (Expected: CONNECTING or ACTIVE)")
        
        # Wait for initialization to complete
        await init_task
        logger.info("   ✅ Initialization complete")
        
        logger.info("-" * 60)
        
        # Test 3: Status after successful initialization
        logger.info("📊 Test 3: Status after successful initialization")
        await asyncio.sleep(2)  # Give connections time to stabilize
        status = exchange.status
        logger.info(f"   Status: {status.name} (Expected: ACTIVE)")
        
        if status == ExchangeStatus.ACTIVE:
            logger.info("   ✅ Test 3 passed - Exchange is fully operational!")
        elif status == ExchangeStatus.CONNECTING:
            logger.info("   ⚠️  Exchange still connecting - WebSocket may be establishing connection")
        else:
            logger.info(f"   ❌ Unexpected status: {status.name}")
        
        # Show connection details
        logger.info("-" * 60)
        logger.info("📊 Connection Details:")
        
        # Check WebSocket state
        if exchange._ws_public and exchange._ws_public.ws_client:
            ws_state = exchange._ws_public.ws_client.state
            logger.info(f"   WebSocket State: {ws_state.name if hasattr(ws_state, 'name') else ws_state}")
        else:
            logger.info("   WebSocket State: Not initialized")
        
        # Check REST client state
        logger.info(f"   REST Clients Healthy: {exchange._is_rest_healthy()}")
        logger.info(f"   Public API: {'✅ Ready' if exchange._public_api else '❌ Not initialized'}")
        logger.info(f"   Private API: {'✅ Ready' if exchange._private_api else '❌ Not initialized'}")
        
        # Test 4: Monitor status changes over time
        logger.info("-" * 60)
        logger.info("📊 Test 4: Monitoring status for 5 seconds...")
        
        for i in range(5):
            await asyncio.sleep(1)
            status = exchange.status
            logger.info(f"   Second {i+1}: Status = {status.name}")
        
        logger.info("   ✅ Status monitoring complete")
        
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up
        logger.info("-" * 60)
        logger.info("🧹 Cleaning up...")
        if exchange:
            await exchange.close()
        logger.info("✅ Test complete!")


async def test_both_exchanges():
    """Test status implementation for both MEXC and Gate.io exchanges."""
    logger.info("🎯 Testing Exchange Status Implementation for Both Exchanges")
    logger.info("=" * 60)
    
    # Test MEXC
    await check_exchange_status("mexc")
    
    logger.info("\n" + "=" * 60 + "\n")
    
    # Test Gate.io
    await check_exchange_status("gateio")


async def main():
    """Main test function."""
    # You can test individual exchanges or both
    # await test_exchange_status("mexc")
    # await test_exchange_status("gateio")
    await test_both_exchanges()


if __name__ == "__main__":
    asyncio.run(main())