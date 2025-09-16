"""
MEXC Hybrid Architecture Demo

Demonstrates the new hybrid architecture implementation of MexcPublicExchange
where the base class handles common orderbook management, REST initialization,
reconnection handling, and update notifications.

Features showcased:
- Base class orderbook management
- REST API initialization sequence
- WebSocket streaming integration
- Update handler registration
- Statistics and monitoring
- Graceful shutdown handling

HFT Compliance:
- No caching of real-time data
- Event-driven architecture
- Sub-millisecond orderbook access
"""

import asyncio
import logging
import time
from typing import List

from core.config.structs import ExchangeConfig, ExchangeCredentials, NetworkConfig, WebSocketConfig
from cex.mexc.public_exchange import MexcPublicExchange
from structs.exchange import Symbol, AssetName, OrderBook
from core.cex.base.base_exchange import OrderbookUpdateType


class HybridArchitectureDemo:
    """Demo showcasing MEXC hybrid architecture implementation."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.exchange: MexcPublicExchange = None
        self.update_count = 0
        self.start_time = time.time()
        
    def create_exchange_config(self) -> ExchangeConfig:
        """Create exchange configuration for demo."""
        # Demo credentials (not real)
        credentials = ExchangeCredentials(
            api_key='demo_key_12345',
            secret_key='demo_secret_abcdef'
        )
        
        # HFT-optimized network settings
        network_config = NetworkConfig(
            request_timeout=5.0,
            connect_timeout=3.0,
            max_retries=3,
            retry_delay=0.5
        )
        
        # WebSocket configuration
        websocket_config = WebSocketConfig(
            url='wss://wbs.mexc.com/ws',
            connect_timeout=10.0,
            ping_interval=20.0,
            ping_timeout=10.0,
            close_timeout=10.0,
            max_reconnect_attempts=5,
            reconnect_delay=1.0,
            reconnect_backoff=2.0,
            max_reconnect_delay=30.0,
            max_message_size=1024 * 1024,  # 1MB
            max_queue_size=1000,
            heartbeat_interval=30.0,
            enable_compression=True,
            text_encoding='utf-8'
        )
        
        return ExchangeConfig(
            name='MEXC',
            credentials=credentials,
            base_url='https://api.mexc.com',
            websocket_url='wss://wbs.mexc.com/ws',
            network=network_config,
            websocket=websocket_config
        )
    
    async def orderbook_update_handler(
        self, 
        symbol: Symbol, 
        orderbook: OrderBook, 
        update_type: OrderbookUpdateType
    ) -> None:
        """Demo orderbook update handler for arbitrage layer integration."""
        self.update_count += 1
        
        if self.update_count % 100 == 0:
            elapsed = time.time() - self.start_time
            updates_per_sec = self.update_count / elapsed if elapsed > 0 else 0
            
            self.logger.info(
                f"📊 Received {self.update_count} updates "
                f"({updates_per_sec:.1f}/sec) - "
                f"Latest: {symbol} [{update_type.value}] "
                f"Bids: {len(orderbook.bids)}, Asks: {len(orderbook.asks)}"
            )
    
    async def demonstrate_hybrid_architecture(self):
        """Main demo showcasing hybrid architecture features."""
        self.logger.info("🚀 Starting MEXC Hybrid Architecture Demo")
        
        try:
            # 1. Create exchange with hybrid architecture
            config = self.create_exchange_config()
            self.exchange = MexcPublicExchange(config)
            
            self.logger.info("✅ Exchange created with hybrid architecture")
            self.logger.info(f"   - Exchange name: {self.exchange.exchange_name}")
            self.logger.info(f"   - Uses base class: {type(self.exchange).__bases__[0].__name__}")
            
            # 2. Register update handler (arbitrage layer integration)
            self.exchange.add_orderbook_update_handler(self.orderbook_update_handler)
            self.logger.info("✅ Orderbook update handler registered")
            
            # 3. Demo symbols for testing
            demo_symbols = [
                Symbol(base=AssetName('BTC'), quote=AssetName('USDT'), is_futures=False),
                Symbol(base=AssetName('ETH'), quote=AssetName('USDT'), is_futures=False)
            ]
            
            # 4. Initialize exchange (base class handles common sequence)
            self.logger.info("🔄 Initializing exchange with base class sequence...")
            await self.exchange.initialize(demo_symbols)
            
            self.logger.info("✅ Exchange initialized successfully")
            self.logger.info(f"   - Active symbols: {len(self.exchange.active_symbols)}")
            self.logger.info(f"   - Connection status: {self.exchange.is_connected}")
            
            # 5. Demonstrate base class statistics
            stats = self.exchange.get_orderbook_stats()
            self.logger.info("📈 Base class statistics:")
            for key, value in stats.items():
                self.logger.info(f"   - {key}: {value}")
            
            # 6. Demonstrate market data statistics
            market_stats = self.exchange.get_market_data_statistics()
            self.logger.info("📊 Market data statistics:")
            for key, value in market_stats.items():
                if isinstance(value, dict):
                    self.logger.info(f"   - {key}:")
                    for sub_key, sub_value in value.items():
                        self.logger.info(f"     - {sub_key}: {sub_value}")
                else:
                    self.logger.info(f"   - {key}: {value}")
            
            # 7. Demonstrate individual symbol orderbook access
            for symbol in demo_symbols:
                orderbook = self.exchange.get_symbol_orderbook(symbol)
                if orderbook:
                    self.logger.info(f"📖 {symbol}: {len(orderbook.bids)} bids, {len(orderbook.asks)} asks")
                else:
                    self.logger.info(f"📖 {symbol}: No orderbook data available")
            
            # 8. Run for demonstration period
            self.logger.info("⏰ Running demo for 10 seconds...")
            await asyncio.sleep(10)
            
            # 9. Demonstrate symbol management
            self.logger.info("🔧 Demonstrating symbol management...")
            new_symbol = Symbol(base=AssetName('BNB'), quote=AssetName('USDT'), is_futures=False)
            
            await self.exchange.add_symbol(new_symbol)
            self.logger.info(f"➕ Added symbol: {new_symbol}")
            self.logger.info(f"   - Active symbols: {len(self.exchange.active_symbols)}")
            
            await self.exchange.remove_symbol(new_symbol)
            self.logger.info(f"➖ Removed symbol: {new_symbol}")
            self.logger.info(f"   - Active symbols: {len(self.exchange.active_symbols)}")
            
        except Exception as e:
            self.logger.error(f"❌ Demo error: {e}", exc_info=True)
            
        finally:
            # 10. Demonstrate graceful shutdown (base class handles cleanup)
            if self.exchange:
                self.logger.info("🛑 Shutting down exchange...")
                await self.exchange.close()
                self.logger.info("✅ Exchange shutdown complete")
    
    async def demonstrate_reconnection_handling(self):
        """Demonstrate base class reconnection handling."""
        self.logger.info("🔄 Demonstrating reconnection handling...")
        
        # This would be triggered by connection loss in real usage
        # For demo purposes, we show the available methods
        self.logger.info("📋 Reconnection features available:")
        self.logger.info("   - Automatic reconnection with exponential backoff")
        self.logger.info("   - REST snapshot reload on reconnect")
        self.logger.info("   - Update notification for arbitrage layer")
        self.logger.info("   - Connection health monitoring")


async def main():
    """Run the hybrid architecture demo."""
    # Setup logging for demo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    demo = HybridArchitectureDemo()
    
    try:
        await demo.demonstrate_hybrid_architecture()
        await demo.demonstrate_reconnection_handling()
        
    except KeyboardInterrupt:
        logging.info("Demo interrupted by user")
    except Exception as e:
        logging.error(f"Demo failed: {e}", exc_info=True)
    
    logging.info("🏁 Hybrid Architecture Demo Complete")


if __name__ == "__main__":
    """
    Run the demo:
    
    PYTHONPATH=src python src/examples/mexc/hybrid_architecture_demo.py
    
    Note: This demo showcases the hybrid architecture patterns without 
    requiring actual MEXC API credentials or network connectivity.
    """
    asyncio.run(main())