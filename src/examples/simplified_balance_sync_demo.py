#!/usr/bin/env python3
"""
Simplified Balance Sync Demo

Demonstrates the new simplified balance synchronization approach where
balance sync is configured directly on private composite exchanges using
the balance_sync_interval parameter.

Key Features:
- Direct integration with BasePrivateComposite
- Simple balance_sync_interval parameter configuration
- Automatic REST-based balance fetching
- on_balance_snapshot event publishing
- No complex TaskManager setup required

Usage:
    python examples/simplified_balance_sync_demo.py
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict

from infrastructure.logging import LoggerFactory
from config.config_manager import HftConfig
from exchanges.structs import ExchangeEnum
from exchanges.exchange_factory import get_composite_implementation
from infrastructure.networking.websocket.structs import PrivateWebsocketChannelType


class BalanceSnapshotListener:
    """Simple listener for balance snapshot events."""
    
    def __init__(self, logger):
        self.logger = logger
        self.snapshot_count = 0
        self.last_snapshot_time = None
    
    def on_balance_snapshot(self, data: Dict):
        """Handle balance snapshot events."""
        self.snapshot_count += 1
        self.last_snapshot_time = data.get('timestamp', datetime.now())
        
        exchange = data.get('exchange', 'Unknown')
        balance_count = data.get('balance_count', 0)
        
        self.logger.info(
            f"📊 Balance Snapshot #{self.snapshot_count} from {exchange}: "
            f"{balance_count} assets at {self.last_snapshot_time}"
        )
        
        # Log some balance details (first few assets)
        balances = data.get('balances', {})
        if balances:
            sample_assets = list(balances.keys())[:3]  # First 3 assets
            for asset in sample_assets:
                balance = balances[asset]
                self.logger.info(
                    f"  {asset}: Available={balance.available}, Locked={balance.locked}"
                )
            
            if len(balances) > 3:
                self.logger.info(f"  ... and {len(balances) - 3} more assets")


async def demo_simplified_balance_sync():
    """Demonstrate simplified balance sync with direct configuration."""
    
    print("🚀 Simplified Balance Sync Demo")
    print("=" * 50)
    
    # Initialize logger
    logger = LoggerFactory.create_logger("simplified_balance_sync_demo")
    
    # Initialize configuration
    config_manager = HftConfig()
    
    print("📡 Creating private exchange with balance sync enabled...")
    
    try:
        # Get exchange config
        exchange_config = config_manager.get_exchange_config('mexc_spot')
        
        # Create private composite exchange with balance sync interval
        private_exchange = get_composite_implementation(
            exchange_config, 
            is_private=True,
            balance_sync_interval=30.0  # Sync every 30 seconds
        )
        
        print("✅ Private exchange created with 30-second balance sync interval")
        
        # Create balance snapshot listener
        listener = BalanceSnapshotListener(logger)
        
        # Bind to balance snapshot events
        if hasattr(private_exchange, '_ws') and private_exchange._ws:
            # This would need to be implemented in the actual exchange
            # For demo, we'll simulate it differently
            print("📡 Balance snapshot listener would be bound here")
        
        # Start balance sync
        print("🔄 Starting balance sync...")
        sync_started = private_exchange.start_balance_sync()
        
        if sync_started:
            print("✅ Balance sync started successfully")
            print(f"   Sync enabled: {private_exchange.balance_sync_enabled}")
            
            # Run for a demonstration period
            print("⏳ Running balance sync demo for 2 minutes...")
            print("   (Press Ctrl+C to stop early)")
            
            try:
                # Simulate running for 2 minutes
                for i in range(4):  # 4 cycles of 30 seconds each
                    await asyncio.sleep(30)
                    print(f"🔄 Cycle {i+1}/4 completed")
                    
                    if not private_exchange.balance_sync_enabled:
                        print("❌ Balance sync stopped unexpectedly")
                        break
            
            except KeyboardInterrupt:
                print("\n⏹️  Demo stopped by user")
            
            # Stop balance sync
            print("🛑 Stopping balance sync...")
            private_exchange.stop_balance_sync()
            print("✅ Balance sync stopped")
            
        else:
            print("❌ Failed to start balance sync")
            print("   Possible reasons:")
            print("   - No balance_sync_interval configured")
            print("   - Already running")
            print("   - No credentials available")
        
        # Clean up
        await private_exchange.close()
        print("🧹 Exchange connection closed")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


async def demo_balance_sync_configuration():
    """Demonstrate different balance sync configuration options."""
    
    print("\n🚀 Balance Sync Configuration Demo")
    print("=" * 50)
    
    logger = LoggerFactory.create_logger("balance_sync_config_demo")
    config_manager = HftConfig()
    
    # Test different configuration scenarios
    scenarios = [
        {"interval": None, "description": "No balance sync (interval=None)"},
        {"interval": 0, "description": "Disabled balance sync (interval=0)"},
        {"interval": 60.0, "description": "1-minute balance sync"},
        {"interval": 300.0, "description": "5-minute balance sync"},
    ]
    
    for scenario in scenarios:
        print(f"\n📋 Testing: {scenario['description']}")
        
        try:
            exchange_config = config_manager.get_exchange_config('mexc_spot')
            
            # Create exchange with different configurations
            private_exchange = get_composite_implementation(
                exchange_config,
                is_private=True,
                balance_sync_interval=scenario['interval']
            )
            
            # Try to start balance sync
            sync_started = private_exchange.start_balance_sync()
            
            print(f"   Sync started: {sync_started}")
            print(f"   Sync enabled: {private_exchange.balance_sync_enabled}")
            
            if sync_started:
                # Stop immediately for demo
                private_exchange.stop_balance_sync()
                print("   Sync stopped for demo")
            
            await private_exchange.close()
            
        except Exception as e:
            print(f"   ❌ Error: {e}")


async def main():
    """Run all simplified balance sync demos."""
    
    print("🎯 CEX Arbitrage - Simplified Balance Sync Demo")
    print("=" * 60)
    print("This demo shows the simplified balance sync integration")
    print("directly in BasePrivateComposite exchanges.\n")
    
    # Check for credentials
    try:
        config_manager = HftConfig()
        mexc_config = config_manager.get_exchange_config('mexc_spot')
        has_mexc_creds = mexc_config and hasattr(mexc_config, 'credentials') and mexc_config.has_credentials()
        
        if not has_mexc_creds:
            print("⚠️  No MEXC API credentials found in config.")
            print("   Set MEXC_API_KEY and MEXC_SECRET_KEY environment variables")
            print("   to run the full balance sync demo with real exchanges.\n")
            
            # Run configuration demo only
            await demo_balance_sync_configuration()
        else:
            print("✅ MEXC credentials found. Running full demo...\n")
            
            # Run both demos
            await demo_simplified_balance_sync()
            await demo_balance_sync_configuration()
        
    except Exception as e:
        print(f"❌ Demo initialization failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Set up logging for demo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    asyncio.run(main())