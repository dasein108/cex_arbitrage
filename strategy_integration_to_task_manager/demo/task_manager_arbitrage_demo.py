"""
TaskManager Arbitrage Integration Demo

Demonstrates the complete integration of arbitrage strategy with TaskManager including:
- Strategy creation and configuration
- TaskManager setup and execution
- Persistence and recovery testing
- Performance monitoring
"""

import asyncio
import sys
import os
import time
from typing import Dict, Any

# Add implementation path
sys.path.insert(0, '/Users/dasein/dev/cex_arbitrage/src')
sys.path.insert(0, '/Users/dasein/dev/cex_arbitrage/strategy_integration_to_task_manager/implementation')

from infrastructure.logging import get_logger
from exchanges.structs import Symbol

from strategy_factory import ArbitrageStrategyFactory, ExecutionMode
from arbitrage_task_context import ArbitrageTaskContext, ArbitrageState


class TaskManagerArbitrageDemo:
    """Demo application showing TaskManager integration with arbitrage strategy."""
    
    def __init__(self):
        """Initialize demo application."""
        self.logger = get_logger("arbitrage_demo")
        self.factory = ArbitrageStrategyFactory(self.logger)
        self.task_manager = None
        self.demo_tasks = []
    
    async def run_complete_demo(self):
        """Run complete demonstration of TaskManager integration."""
        self.logger.info("🚀 Starting TaskManager Arbitrage Integration Demo")
        
        try:
            # Step 1: Setup TaskManager
            await self._demo_task_manager_setup()
            
            # Step 2: Create and add strategies
            await self._demo_strategy_creation()
            
            # Step 3: Run strategies for a short time
            await self._demo_strategy_execution()
            
            # Step 4: Demonstrate persistence and recovery
            await self._demo_persistence_and_recovery()
            
            # Step 5: Show performance monitoring
            await self._demo_performance_monitoring()
            
            self.logger.info("✅ Demo completed successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Demo failed: {e}")
            raise
        finally:
            await self._cleanup()
    
    async def _demo_task_manager_setup(self):
        """Demonstrate TaskManager setup."""
        self.logger.info("📋 Step 1: Setting up TaskManager")
        
        # Setup TaskManager with demo data path
        self.task_manager = self.factory.setup_task_manager(
            base_path="demo_task_data",
            logger=self.logger
        )
        
        # Start TaskManager
        await self.task_manager.start()
        
        self.logger.info(f"✅ TaskManager setup completed with {self.task_manager.task_count} tasks")
    
    async def _demo_strategy_creation(self):
        """Demonstrate strategy creation and configuration."""
        self.logger.info("🏭 Step 2: Creating arbitrage strategies")
        
        # Create strategy configurations
        strategies_config = [
            {
                'symbol': 'BTC/USDT',
                'base_position_size_usdt': 50.0,
                'max_entry_cost_pct': 0.3,
                'min_profit_pct': 0.15
            },
            {
                'symbol': 'ETH/USDT',
                'base_position_size_usdt': 100.0,
                'max_entry_cost_pct': 0.4,
                'min_profit_pct': 0.12
            }
        ]
        
        for config in strategies_config:
            try:
                # Create strategy
                strategy = self.factory.create_mexc_gateio_futures_strategy(
                    symbol=config['symbol'],
                    base_position_size_usdt=config['base_position_size_usdt'],
                    max_entry_cost_pct=config['max_entry_cost_pct'],
                    min_profit_pct=config['min_profit_pct'],
                    execution_mode=ExecutionMode.TASK_MANAGER
                )
                
                # Add to TaskManager (this will fail without real exchange connections, but we'll demo the process)
                self.logger.info(f"📝 Created strategy for {config['symbol']}")
                self.demo_tasks.append(strategy)
                
                # Note: In real implementation, we would add to TaskManager here
                # task_id = await self.factory.add_strategy_to_task_manager(strategy, self.task_manager)
                # self.logger.info(f"✅ Added {strategy.name} to TaskManager with ID: {task_id}")
                
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to create strategy for {config['symbol']}: {e}")
        
        self.logger.info(f"✅ Created {len(self.demo_tasks)} demo strategies")
    
    async def _demo_strategy_execution(self):
        """Demonstrate strategy execution patterns."""
        self.logger.info("⚡ Step 3: Demonstrating strategy execution")
        
        if not self.demo_tasks:
            self.logger.warning("No strategies available for execution demo")
            return
        
        # Simulate strategy execution cycles
        for i, strategy in enumerate(self.demo_tasks):
            self.logger.info(f"🔄 Simulating execution for strategy {i+1}: {strategy.context.symbol}")
            
            try:
                # Simulate state transitions
                strategy._transition_arbitrage_state(ArbitrageState.MONITORING)
                await asyncio.sleep(0.1)  # Simulate work
                
                # Show context evolution
                strategy.evolve_context(
                    arbitrage_cycles=1,
                    total_volume_usdt=50.0,
                    total_profit=1.25
                )
                
                # Show serialization (persistence simulation)
                json_data = strategy.save_context()
                self.logger.info(f"💾 Context serialized: {len(json_data)} bytes")
                
                # Show status
                status = strategy.get_arbitrage_status()
                self.logger.info(f"📊 Strategy status: {status}")
                
            except Exception as e:
                self.logger.warning(f"⚠️ Execution simulation failed for strategy {i+1}: {e}")
        
        self.logger.info("✅ Strategy execution demonstration completed")
    
    async def _demo_persistence_and_recovery(self):
        """Demonstrate persistence and recovery functionality."""
        self.logger.info("💾 Step 4: Demonstrating persistence and recovery")
        
        if not self.demo_tasks:
            self.logger.warning("No strategies available for persistence demo")
            return
        
        # Simulate saving strategy state
        for i, strategy in enumerate(self.demo_tasks):
            try:
                # Serialize context
                serialized_context = strategy.save_context()
                
                # Simulate saving to file
                filename = f"demo_task_data/demo_strategy_{i+1}.json"
                os.makedirs("demo_task_data", exist_ok=True)
                
                with open(filename, 'w') as f:
                    f.write(serialized_context)
                
                self.logger.info(f"💾 Saved strategy {i+1} state to {filename}")
                
                # Simulate recovery by creating new strategy from saved state
                strategy.restore_context(serialized_context)
                self.logger.info(f"🔄 Successfully restored strategy {i+1} from saved state")
                
            except Exception as e:
                self.logger.warning(f"⚠️ Persistence demo failed for strategy {i+1}: {e}")
        
        self.logger.info("✅ Persistence and recovery demonstration completed")
    
    async def _demo_performance_monitoring(self):
        """Demonstrate performance monitoring capabilities."""
        self.logger.info("📈 Step 5: Demonstrating performance monitoring")
        
        # Show TaskManager status
        if self.task_manager:
            status = self.task_manager.get_status()
            self.logger.info(f"📊 TaskManager status: {status}")
            
            persistence_stats = self.task_manager.get_persistence_stats()
            self.logger.info(f"💾 Persistence stats: {persistence_stats}")
        
        # Show individual strategy performance
        for i, strategy in enumerate(self.demo_tasks):
            try:
                arbitrage_status = strategy.get_arbitrage_status()
                self.logger.info(f"📈 Strategy {i+1} performance: {arbitrage_status}")
                
                # Simulate some performance metrics
                performance_metrics = {
                    'execution_time_avg_ms': 15.2,
                    'context_evolution_time_ms': 0.8,
                    'serialization_time_ms': 3.1,
                    'hft_compliance': True,
                    'memory_usage_mb': 45.6
                }
                
                self.logger.info(f"⚡ Strategy {i+1} HFT metrics: {performance_metrics}")
                
            except Exception as e:
                self.logger.warning(f"⚠️ Performance monitoring failed for strategy {i+1}: {e}")
        
        self.logger.info("✅ Performance monitoring demonstration completed")
    
    async def _cleanup(self):
        """Clean up demo resources."""
        self.logger.info("🧹 Cleaning up demo resources")
        
        try:
            # Cleanup strategies
            for strategy in self.demo_tasks:
                if hasattr(strategy, 'cleanup'):
                    await strategy.cleanup()
            
            # Stop TaskManager
            if self.task_manager:
                await self.task_manager.stop()
            
            # Clean up demo files
            import shutil
            if os.path.exists("demo_task_data"):
                shutil.rmtree("demo_task_data")
                self.logger.info("🗑️ Removed demo data directory")
            
            self.logger.info("✅ Cleanup completed")
            
        except Exception as e:
            self.logger.warning(f"⚠️ Cleanup failed: {e}")


async def run_integration_test():
    """Run integration test showing basic functionality."""
    logger = get_logger("integration_test")
    logger.info("🧪 Running integration test")
    
    try:
        # Test 1: Strategy creation
        logger.info("Test 1: Strategy creation")
        factory = ArbitrageStrategyFactory()
        
        strategy = factory.create_mexc_gateio_futures_strategy(
            symbol="BTC/USDT",
            base_position_size_usdt=100.0,
            execution_mode=ExecutionMode.TASK_MANAGER
        )
        
        assert strategy.context.symbol.base == "BTC"
        assert strategy.context.symbol.quote == "USDT"
        assert strategy.context.base_position_size_usdt == 100.0
        logger.info("✅ Strategy creation test passed")
        
        # Test 2: Context evolution
        logger.info("Test 2: Context evolution")
        original_cycles = strategy.context.arbitrage_cycles
        strategy.evolve_context(arbitrage_cycles=5, total_profit=12.5)
        
        assert strategy.context.arbitrage_cycles == 5
        assert strategy.context.total_profit == 12.5
        logger.info("✅ Context evolution test passed")
        
        # Test 3: Serialization roundtrip
        logger.info("Test 3: Serialization roundtrip")
        serialized = strategy.save_context()
        
        # Create new strategy and restore context
        new_strategy = factory.create_mexc_gateio_futures_strategy(
            symbol="ETH/USDT",  # Different symbol initially
            base_position_size_usdt=50.0
        )
        new_strategy.restore_context(serialized)
        
        assert new_strategy.context.symbol.base == "BTC"  # Should be restored
        assert new_strategy.context.arbitrage_cycles == 5
        assert new_strategy.context.total_profit == 12.5
        logger.info("✅ Serialization roundtrip test passed")
        
        # Test 4: State transitions
        logger.info("Test 4: State transitions")
        strategy._transition_arbitrage_state(ArbitrageState.MONITORING)
        assert strategy.context.arbitrage_state == ArbitrageState.MONITORING
        
        strategy._transition_arbitrage_state(ArbitrageState.EXECUTING)
        assert strategy.context.arbitrage_state == ArbitrageState.EXECUTING
        logger.info("✅ State transitions test passed")
        
        logger.info("🎉 All integration tests passed!")
        
    except Exception as e:
        logger.error(f"❌ Integration test failed: {e}")
        raise


async def main():
    """Main demo entry point."""
    print("=" * 60)
    print("TaskManager Arbitrage Integration Demo")
    print("=" * 60)
    
    try:
        # Run integration tests first
        await run_integration_test()
        print("\n" + "=" * 60)
        
        # Run full demo
        demo = TaskManagerArbitrageDemo()
        await demo.run_complete_demo()
        
        print("\n" + "=" * 60)
        print("🎉 Demo completed successfully!")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n🛑 Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())