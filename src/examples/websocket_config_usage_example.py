#!/usr/bin/env python3
"""
WebSocket Configuration Usage Example

Demonstrates how exchange implementations should use WebSocket configuration
from ExchangeConfig instead of hard-coded values.

Usage:
    PYTHONPATH=src python src/examples/websocket_config_usage_example.py
"""

import asyncio
from core.config.config_manager import get_exchange_config_struct
from core.config.structs import ExchangeConfig, WebSocketConfig


class ExampleWebSocketClient:
    """
    Example WebSocket client showing proper configuration usage.
    
    This demonstrates the pattern that should be used in actual exchange
    implementations instead of hard-coding WebSocket settings.
    """
    
    def __init__(self, websocket_config: WebSocketConfig, websocket_url: str):
        """
        Initialize WebSocket client with configuration from ExchangeConfig.
        
        Args:
            websocket_config: WebSocket configuration from ExchangeConfig
            websocket_url: WebSocket URL from ExchangeConfig
        """
        self.config = websocket_config
        self.url = websocket_url
        self.connected = False
        
    async def connect(self) -> bool:
        """
        Connect to WebSocket using configuration settings.
        
        Returns:
            True if connection successful
        """
        print(f"🔗 Connecting to WebSocket: {self.url}")
        print(f"   Timeout: {self.config.connect_timeout}s")
        print(f"   Heartbeat: {self.config.heartbeat_interval}s")
        print(f"   Max Reconnects: {self.config.max_reconnect_attempts}")
        print(f"   Reconnect Delay: {self.config.reconnect_delay}s")
        
        # Simulate connection using config timeout
        try:
            await asyncio.sleep(0.1)  # Simulate connection time
            self.connected = True
            print(f"✅ WebSocket connected successfully")
            return True
            
        except Exception as e:
            print(f"❌ WebSocket connection failed: {e}")
            return False
    
    async def start_heartbeat(self):
        """Start heartbeat using configured interval."""
        while self.connected:
            print(f"💓 Sending heartbeat (interval: {self.config.heartbeat_interval}s)")
            await asyncio.sleep(self.config.heartbeat_interval)
    
    async def disconnect(self):
        """Disconnect WebSocket."""
        self.connected = False
        print(f"🔌 WebSocket disconnected")


class ExampleExchangeImplementation:
    """
    Example showing how an exchange implementation should use ExchangeConfig.
    
    This pattern should be followed by actual exchange implementations like
    MexcPublicExchange, GateioPublicExchange, etc.
    """
    
    def __init__(self, exchange_config: ExchangeConfig):
        """
        Initialize exchange with complete configuration.
        
        Args:
            exchange_config: Complete exchange configuration including WebSocket settings
        """
        self.config = exchange_config
        self.websocket_client = None
        
    async def initialize_websocket(self) -> bool:
        """
        Initialize WebSocket client using ExchangeConfig.websocket settings.
        
        This demonstrates the CORRECT way to use WebSocket configuration
        instead of hard-coding values.
        """
        if not self.config.websocket:
            print(f"⚠️  No WebSocket configuration for {self.config.name}")
            return False
        
        print(f"🚀 Initializing WebSocket for {self.config.name.upper()}")
        
        # Create WebSocket client with config settings
        self.websocket_client = ExampleWebSocketClient(
            websocket_config=self.config.websocket,
            websocket_url=self.config.websocket_url
        )
        
        # Connect using configured settings
        return await self.websocket_client.connect()
    
    async def start_real_time_data(self):
        """Start real-time data collection."""
        if not self.websocket_client or not self.websocket_client.connected:
            print(f"❌ WebSocket not connected for {self.config.name}")
            return
        
        print(f"📊 Starting real-time data collection for {self.config.name}")
        # Start heartbeat task
        asyncio.create_task(self.websocket_client.start_heartbeat())
    
    async def cleanup(self):
        """Clean up resources."""
        if self.websocket_client:
            await self.websocket_client.disconnect()


async def demo_websocket_config_usage():
    """Demonstrate proper WebSocket configuration usage."""
    print("🌟 WebSocket Configuration Usage Demo")
    print("=====================================")
    
    # Load exchange configurations from YAML
    try:
        mexc_config = get_exchange_config_struct('mexc')
        gateio_config = get_exchange_config_struct('gateio')
        
        print(f"\n📋 Loaded Exchange Configurations:")
        print(f"   MEXC WebSocket URL: {mexc_config.websocket_url}")
        print(f"   Gate.io WebSocket URL: {gateio_config.websocket_url}")
        
        if mexc_config.websocket:
            print(f"   MEXC WebSocket Config: {mexc_config.websocket.connect_timeout}s timeout")
        if gateio_config.websocket:
            print(f"   Gate.io WebSocket Config: {gateio_config.websocket.connect_timeout}s timeout")
        
        # Create example exchange implementations
        mexc_exchange = ExampleExchangeImplementation(mexc_config)
        gateio_exchange = ExampleExchangeImplementation(gateio_config)
        
        # Initialize WebSocket connections
        print(f"\n🔧 Initializing WebSocket Connections:")
        
        mexc_success = await mexc_exchange.initialize_websocket()
        gateio_success = await gateio_exchange.initialize_websocket()
        
        if mexc_success:
            await mexc_exchange.start_real_time_data()
        
        if gateio_success:
            await gateio_exchange.start_real_time_data()
        
        # Simulate running for a short time
        print(f"\n⏱️  Running for 3 seconds to demonstrate heartbeat...")
        await asyncio.sleep(3)
        
        # Clean up
        print(f"\n🧹 Cleaning up...")
        await mexc_exchange.cleanup()
        await gateio_exchange.cleanup()
        
        print(f"\n✨ Demo completed successfully!")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


async def demo_old_vs_new_pattern():
    """Show the difference between old and new configuration patterns."""
    print(f"\n🔄 Old vs New Configuration Patterns")
    print("=====================================")
    
    print(f"\n❌ OLD PATTERN (Hard-coded - DON'T DO THIS):")
    print(f"   ws_config = WebSocketConfig(")
    print(f"       url='wss://api.example.com/ws',")
    print(f"       ping_interval=30,  # Hard-coded!")
    print(f"       ping_timeout=10,   # Hard-coded!")
    print(f"       close_timeout=10   # Hard-coded!")
    print(f"   )")
    
    print(f"\n✅ NEW PATTERN (Config-driven - CORRECT):")
    print(f"   exchange_config = get_exchange_config_struct('mexc')")
    print(f"   websocket_client = WebSocketClient(")
    print(f"       websocket_config=exchange_config.websocket,  # From config!")
    print(f"       websocket_url=exchange_config.websocket_url  # From config!")
    print(f"   )")
    
    print(f"\n🎯 Benefits of New Pattern:")
    print(f"   ✅ Centralized configuration in YAML")
    print(f"   ✅ Exchange-specific tuning possible")
    print(f"   ✅ No scattered hard-coded values")
    print(f"   ✅ Easy to modify without code changes")
    print(f"   ✅ Consistent with REST configuration pattern")


async def main():
    """Main demo orchestrator."""
    await demo_websocket_config_usage()
    await demo_old_vs_new_pattern()


if __name__ == "__main__":
    asyncio.run(main())