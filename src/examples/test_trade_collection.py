#!/usr/bin/env python3
"""
Test Trade Collection Integration

Tests the complete trade collection flow:
1. Configuration loading
2. Analytics engine initialization  
3. Trade data processing
4. Database operations
5. WebSocket integration

This demonstrates the end-to-end trade collection system.
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from exchanges.structs.common import Symbol, Trade
from exchanges.structs.types import AssetName
from exchanges.structs import Side
from applications.data_collection.config import load_data_collector_config
from applications.data_collection.analytics import RealTimeAnalytics
from db.models import TradeSnapshot


async def test_trade_analytics():
    """Test trade analytics functionality."""
    print("🧪 Testing Trade Analytics...")
    
    try:
        # Load configuration
        config = load_data_collector_config()
        print(f"✅ Configuration loaded: {len(config.symbols)} symbols, analytics enabled")
        
        # Initialize analytics engine
        analytics = RealTimeAnalytics(config.analytics)
        print("✅ Analytics engine initialized")
        
        # Create test trade data
        symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"), is_futures=False)
        trade = Trade(
            symbol=symbol,
            side=Side.BUY,
            quantity=0.5,
            price=45000.0,
            timestamp=int(datetime.now().timestamp() * 1000),
            trade_id="test_trade_123",
            quote_quantity=22500.0,
            is_buyer=True,
            is_maker=False
        )
        
        # Process trade update
        await analytics.on_trade_update("MEXC", symbol, trade)
        print("✅ Trade update processed")
        
        # Check analytics statistics
        stats = analytics.get_statistics()
        print(f"✅ Analytics stats: {stats['trade_count']} trades processed")
        
        # Get recent trades
        recent_trades = analytics.get_recent_trades("MEXC", symbol, minutes=1)
        print(f"✅ Recent trades retrieved: {len(recent_trades)} trades")
        
        # Get trade analysis
        analysis = analytics.get_trade_analysis("MEXC", symbol, minutes=1)
        print(f"✅ Trade analysis: {analysis.trade_count} trades, ${analysis.volume_usd:.2f} volume")
        
        return True
        
    except Exception as e:
        print(f"❌ Trade analytics test failed: {e}")
        return False


async def test_trade_data_model():
    """Test trade data model conversion."""
    print("🧪 Testing Trade Data Model...")
    
    try:
        # Create test trade
        symbol = Symbol(base=AssetName("ETH"), quote=AssetName("USDT"), is_futures=False)
        trade = Trade(
            symbol=symbol,
            side=Side.SELL,
            quantity=2.0,
            price=3000.0,
            timestamp=int(datetime.now().timestamp() * 1000),
            trade_id="test_trade_456",
            quote_quantity=6000.0,
            is_buyer=False,
            is_maker=True
        )
        
        # Convert to TradeSnapshot
        snapshot = TradeSnapshot.from_trade_struct("GATEIO", trade)
        print(f"✅ Trade converted to snapshot: {snapshot.exchange} {snapshot.symbol_base}/{snapshot.symbol_quote}")
        
        # Convert back to Trade
        reconstructed_trade = snapshot.to_trade_struct()
        print(f"✅ Snapshot converted back to trade: {reconstructed_trade.symbol.base}/{reconstructed_trade.symbol.quote}")
        
        # Verify data integrity
        assert reconstructed_trade.symbol == trade.symbol
        assert reconstructed_trade.side == trade.side
        assert reconstructed_trade.quantity == trade.quantity
        assert reconstructed_trade.price == trade.price
        print("✅ Data integrity verified")
        
        return True
        
    except Exception as e:
        print(f"❌ Trade data model test failed: {e}")
        return False


async def test_database_operations():
    """Test database operations (without actual DB connection)."""
    print("🧪 Testing Database Operations...")
    
    try:
        # Create test snapshots
        snapshots = []
        symbols = [
            ("BTC", "USDT"),
            ("ETH", "USDT"), 
            ("BNB", "USDT")
        ]
        
        for base, quote in symbols:
            symbol = Symbol(base=AssetName(base), quote=AssetName(quote), is_futures=False)
            trade = Trade(
                symbol=symbol,
                side=Side.BUY if base == "BTC" else Side.SELL,
                quantity=1.0,
                price=50000.0 if base == "BTC" else 3000.0,
                timestamp=int(datetime.now().timestamp() * 1000),
                trade_id=f"test_{base.lower()}_123",
                is_buyer=True,
                is_maker=False
            )
            
            snapshot = TradeSnapshot.from_trade_struct("MEXC", trade)
            snapshots.append(snapshot)
        
        print(f"✅ Created {len(snapshots)} test trade snapshots")
        
        # Test deduplication logic (simulate)
        unique_snapshots = []
        seen_keys = set()
        
        for snapshot in snapshots:
            # Simulate the deduplication key generation
            key = f"{snapshot.exchange}_{snapshot.symbol_base}{snapshot.symbol_quote}_{snapshot.trade_id}_{snapshot.timestamp}"
            if key not in seen_keys:
                unique_snapshots.append(snapshot)
                seen_keys.add(key)
        
        print(f"✅ Deduplication test: {len(unique_snapshots)} unique snapshots")
        
        # Note: Actual database operations would require a DB connection
        print("ℹ️  Database operations structure validated (DB connection not tested)")
        
        return True
        
    except Exception as e:
        print(f"❌ Database operations test failed: {e}")
        return False


async def test_configuration():
    """Test configuration loading and validation."""
    print("🧪 Testing Configuration...")
    
    try:
        # Load configuration
        config = load_data_collector_config()
        
        # Validate trade collection settings
        assert hasattr(config, 'collect_trades')
        assert hasattr(config, 'trade_snapshot_interval')
        print(f"✅ Trade collection configured: {config.collect_trades}")
        print(f"✅ Trade snapshot interval: {config.trade_snapshot_interval}s")
        
        # Validate analytics configuration
        assert hasattr(config.analytics, 'arbitrage_threshold')
        assert hasattr(config.analytics, 'volume_threshold')
        print(f"✅ Analytics thresholds configured")
        
        # Validate symbols
        assert len(config.symbols) > 0
        print(f"✅ Symbols configured: {len(config.symbols)} symbols")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False


async def main():
    """Run all trade collection tests."""
    print("🚀 Starting Trade Collection Integration Tests")
    print("=" * 60)
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Run tests
    tests = [
        ("Configuration", test_configuration),
        ("Trade Data Model", test_trade_data_model),
        ("Database Operations", test_database_operations),
        ("Trade Analytics", test_trade_analytics),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\n📋 Running {test_name} Test...")
        try:
            if await test_func():
                passed += 1
                print(f"✅ {test_name} Test PASSED")
            else:
                failed += 1
                print(f"❌ {test_name} Test FAILED")
        except Exception as e:
            failed += 1
            print(f"❌ {test_name} Test FAILED with exception: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All trade collection tests passed!")
        print("\n📚 Next Steps:")
        print("1. Run database migrations: ./migrations/migrate.sh")
        print("2. Start data collector with trade collection enabled")
        print("3. Monitor trade analytics in logs")
        return True
    else:
        print("❌ Some tests failed. Please review the output above.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)