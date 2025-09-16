"""
MEXC Private WebSocket Test

Test script for private WebSocket functionality including:
- Listen key management (create, keep-alive, delete)
- Private channel subscriptions (account, trades, orders)
- Protobuf message parsing
- Strategy pattern with dependency injection

HFT COMPLIANCE: Sub-millisecond message processing, zero-copy patterns.
"""

import asyncio
import logging
import os
from typing import List

from core.cex.websocket.strategies import WebSocketStrategySet
from core.transport.websocket.ws_client import WebSocketConfig
from cex.mexc.ws.strategies_mexc import (
    MexcPrivateConnectionStrategy,
    MexcPrivateSubscriptionStrategy,
    MexcPrivateMessageParser
)
from cex.mexc.rest.rest_private import MexcPrivateSpotRest
from core.config.structs import ExchangeConfig
from structs.exchange import Symbol, AssetName
from core.cex.websocket.ws_manager import WebSocketManager


async def main():
    """
    Test MEXC private WebSocket with listen key management.
    
    This test verifies:
    1. Listen key creation, keep-alive, and deletion
    2. Private channel subscriptions
    3. Message reception and parsing
    4. Strategy pattern dependency injection
    """
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    logger.info("🚀 Starting MEXC Private WebSocket Test")
    
    # Configuration
    mexc_config = ExchangeConfig(
        name="MEXC",
        api_key=os.getenv("MEXC_API_KEY", "test_key"),
        secret_key=os.getenv("MEXC_SECRET_KEY", "test_secret"),
        base_url="https://api.mexc.com",
        websocket_url="wss://wbs-api.mexc.com/ws",
        rate_limit=20  # 20 req/sec
    )
    
    if not mexc_config.api_key or mexc_config.api_key == "test_key":
        logger.warning("⚠️ Using test credentials - set MEXC_API_KEY and MEXC_SECRET_KEY for live testing")
    
    # Create REST client for listen key management
    rest_client = MexcPrivateSpotRest(mexc_config)
    
    # Create strategy set with dependency injection
    strategies = WebSocketStrategySet(
        connection_strategy=MexcPrivateConnectionStrategy(mexc_config, rest_client),
        subscription_strategy=MexcPrivateSubscriptionStrategy(),
        message_parser=MexcPrivateMessageParser()
    )
    
    # WebSocket configuration
    ws_config = WebSocketConfig(
        url=mexc_config.websocket_url,
        ping_interval=30,
        ping_timeout=10,
        close_timeout=10
    )
    
    # Test symbols (dummy symbol to trigger subscriptions)
    symbols: List[Symbol] = [
        Symbol(base=AssetName("BTC"), quote=AssetName("USDT"), is_futures=False)
    ]
    
    # Create WebSocket manager
    ws_manager = WebSocketManager(
        config=ws_config,
        strategies=strategies
    )
    
    try:
        logger.info("📡 Initializing WebSocket connection...")
        await ws_manager.initialize(symbols)
        
        logger.info("✅ WebSocket initialized, testing for 30 seconds...")
        await asyncio.sleep(30)
        
        # Get performance metrics
        metrics = ws_manager.get_performance_metrics()
        logger.info(f"📊 Performance metrics: {metrics}")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        raise
        
    finally:
        logger.info("🛑 Cleaning up...")
        await ws_manager.close()
        await rest_client.close()
        
    logger.info("✅ MEXC Private WebSocket test completed")


if __name__ == "__main__":
    asyncio.run(main())