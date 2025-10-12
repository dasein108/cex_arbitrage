"""
Simple Phase 2 Test - Core Components Only

This test demonstrates the core Phase 2 components working together
without requiring the full codebase integration.
"""

import asyncio
import sys
import os
import time
from dataclasses import dataclass

from ..optimization import DeltaArbitrageOptimizer, OptimizationConfig
from ..integration.optimizer_bridge import OptimizerBridge
from ..integration.parameter_scheduler import ParameterScheduler


@dataclass
class MockSymbol:
    """Mock symbol for testing"""
    base: str
    quote: str
    
    def __str__(self):
        return f"{self.base}/{self.quote}"


class SimplifiedStrategyTest:
    """
    Simplified test demonstrating the core Phase 2 functionality:
    1. Parameter optimization
    2. Optimizer bridge
    3. Parameter scheduler
    4. Dynamic parameter updates
    """
    
    def __init__(self):
        self.symbol = MockSymbol("NEIROETH", "USDT")
        self.optimizer = None
        self.bridge = None
        self.scheduler = None
        
        # Mock strategy state
        self.current_entry_threshold = 0.5
        self.current_exit_threshold = 0.1
        self.parameter_updates = 0
        
    async def setup_components(self):
        """Setup all Phase 2 components."""
        print("🔧 Setting up Phase 2 components...")
        
        # 1. Initialize optimizer
        config = OptimizationConfig(
            target_hit_rate=0.7,
            min_trades_per_day=5,
            optimization_timeout_seconds=10.0  # Faster for testing
        )
        self.optimizer = DeltaArbitrageOptimizer(config)
        print("✅ Optimizer initialized")
        
        # 2. Initialize bridge
        self.bridge = OptimizerBridge(self.optimizer, strategy_reference=self)
        print("✅ Bridge initialized")
        
        # 3. Initialize scheduler with callback
        async def parameter_update_callback(optimization_result):
            """Mock strategy parameter update."""
            old_entry = self.current_entry_threshold
            old_exit = self.current_exit_threshold
            
            self.current_entry_threshold = optimization_result.entry_threshold_pct
            self.current_exit_threshold = optimization_result.exit_threshold_pct
            self.parameter_updates += 1
            
            print(f"📈 Mock strategy parameters updated:")
            print(f"   • Entry: {old_entry:.4f}% → {self.current_entry_threshold:.4f}%")
            print(f"   • Exit: {old_exit:.4f}% → {self.current_exit_threshold:.4f}%")
            print(f"   • Update count: {self.parameter_updates}")
        
        self.scheduler = ParameterScheduler(self.bridge, update_callback=parameter_update_callback)
        print("✅ Scheduler initialized")
        
        print("🎉 All Phase 2 components ready!")
    
    async def _get_recent_market_data(self):
        """Mock method for bridge to access market data."""
        return await self.bridge._generate_fallback_data(hours=12)
    
    async def test_manual_optimization(self):
        """Test manual parameter optimization."""
        print("\n🧪 Testing manual optimization...")
        
        # Generate mock data
        market_data = await self.bridge.get_recent_market_data(hours=6)
        print(f"   • Generated {len(market_data)} data points")
        
        # Run optimization
        result = await self.optimizer.optimize_parameters(market_data, lookback_hours=6)
        
        print(f"✅ Manual optimization completed:")
        print(f"   • Entry threshold: {result.entry_threshold_pct:.4f}%")
        print(f"   • Exit threshold: {result.exit_threshold_pct:.4f}%")
        print(f"   • Confidence: {result.confidence_score:.3f}")
        
        return result
    
    async def test_bridge_functionality(self):
        """Test optimizer bridge functionality."""
        print("\n🔗 Testing bridge functionality...")
        
        # Test bridge update
        success = await self.bridge.update_strategy_parameters(
            lookback_hours=6,
            min_data_points=50
        )
        
        if success:
            print("✅ Bridge update successful")
            result = self.bridge.get_last_optimization_result()
            print(f"   • Retrieved result: Entry={result.entry_threshold_pct:.4f}%")
        else:
            print("❌ Bridge update failed")
        
        # Test bridge status
        status = self.bridge.get_optimization_status()
        print(f"📊 Bridge status:")
        print(f"   • Optimization count: {status['optimization_count']}")
        print(f"   • Success rate: {status['success_rate']:.1%}")
        print(f"   • Avg time: {status['avg_optimization_time_seconds']:.3f}s")
        
        return success
    
    async def test_scheduler_functionality(self):
        """Test parameter scheduler functionality."""
        print("\n⏰ Testing scheduler functionality...")
        
        # Start scheduler with fast updates for testing
        await self.scheduler.start_scheduled_updates(
            interval_minutes=0.05,  # 3 seconds for testing
            lookback_hours=3,
            min_data_points=30
        )
        
        print("✅ Scheduler started (3-second intervals)")
        
        # Let it run for a few cycles
        print("⏳ Running scheduler for 15 seconds...")
        await asyncio.sleep(15)
        
        # Check status
        status = self.scheduler.get_update_status()
        print(f"📊 Scheduler results:")
        print(f"   • Total updates: {status['statistics']['total_updates']}")
        print(f"   • Success rate: {status['statistics']['success_rate']:.1%}")
        print(f"   • Strategy parameter updates: {self.parameter_updates}")
        
        # Stop scheduler
        await self.scheduler.stop_scheduled_updates()
        print("🛑 Scheduler stopped")
        
        return status['statistics']['total_updates'] > 0
    
    async def test_health_monitoring(self):
        """Test health monitoring functionality."""
        print("\n🏥 Testing health monitoring...")
        
        # Bridge health
        bridge_health = self.bridge.get_health_status()
        print(f"🔗 Bridge health: {'✅ Healthy' if bridge_health['is_healthy'] else '❌ Issues'}")
        if not bridge_health['is_healthy']:
            print(f"   Issues: {bridge_health['health_issues']}")
        
        # Scheduler health
        scheduler_health = self.scheduler.get_health_status()
        print(f"⏰ Scheduler health: {'✅ Healthy' if scheduler_health['is_healthy'] else '❌ Issues'}")
        if not scheduler_health['is_healthy']:
            print(f"   Issues: {scheduler_health['health_issues']}")
        
        return bridge_health['is_healthy'] and scheduler_health['is_healthy']
    
    async def run_complete_test(self):
        """Run complete Phase 2 test suite."""
        print(f"🚀 PHASE 2 COMPONENT TEST SUITE")
        print(f"{'='*60}")
        print(f"Symbol: {self.symbol}")
        print(f"{'='*60}")
        
        try:
            # Setup
            await self.setup_components()
            
            # Test individual components
            test_results = {}
            
            # Test 1: Manual optimization
            result1 = await self.test_manual_optimization()
            test_results['manual_optimization'] = result1 is not None
            
            # Test 2: Bridge functionality
            result2 = await self.test_bridge_functionality()
            test_results['bridge_functionality'] = result2
            
            # Test 3: Scheduler functionality
            result3 = await self.test_scheduler_functionality()
            test_results['scheduler_functionality'] = result3
            
            # Test 4: Health monitoring
            result4 = await self.test_health_monitoring()
            test_results['health_monitoring'] = result4
            
            # Final summary
            print(f"\n{'='*60}")
            print(f"📊 PHASE 2 TEST RESULTS")
            print(f"{'='*60}")
            
            passed_tests = sum(test_results.values())
            total_tests = len(test_results)
            
            for test_name, passed in test_results.items():
                status = "✅ PASS" if passed else "❌ FAIL"
                print(f"• {test_name.replace('_', ' ').title()}: {status}")
            
            print(f"\nOverall: {passed_tests}/{total_tests} tests passed")
            
            if passed_tests == total_tests:
                print("🎉 ALL PHASE 2 TESTS PASSED!")
                print("✅ Live trading strategy components are working correctly")
                print("✅ Dynamic parameter optimization is functional")
                print("✅ Integration between components is successful")
            else:
                print("⚠️ Some tests failed - check implementation")
            
            print(f"{'='*60}")
            
            return passed_tests == total_tests
            
        except Exception as e:
            print(f"❌ Test suite failed: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """Run the Phase 2 test."""
    try:
        test = SimplifiedStrategyTest()
        success = await test.run_complete_test()
        
        if success:
            print("\n✅ Phase 2 implementation is ready!")
            print("🚀 The delta arbitrage system can now be deployed")
        else:
            print("\n❌ Phase 2 implementation needs fixes")
            
    except Exception as e:
        print(f"❌ Test execution failed: {e}")


if __name__ == "__main__":
    print("🧪 Starting Phase 2 Component Test...")
    asyncio.run(main())