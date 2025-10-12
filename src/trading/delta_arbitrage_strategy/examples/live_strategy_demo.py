"""
Live Delta Arbitrage Strategy Demo

This example demonstrates the complete integrated system:
1. Parameter optimization engine
2. Simplified live trading strategy  
3. Dynamic parameter updates
4. Real-time strategy execution simulation

This is a complete PoC showing how all components work together.
"""

import asyncio
import sys
import os
import signal
from typing import Optional

from exchanges.structs import Symbol, AssetName
from ..optimization import DeltaArbitrageOptimizer, OptimizationConfig
from ..strategy.strategy_config import DeltaArbitrageConfig, create_default_config
from ..strategy.delta_arbitrage_strategy import SimpleDeltaArbitrageStrategy
from ..integration.optimizer_bridge import OptimizerBridge
from ..integration.parameter_scheduler import ParameterScheduler


class LiveStrategyDemo:
    """
    Complete demo of the delta arbitrage system.
    
    This class orchestrates all components to demonstrate:
    - Strategy initialization with optimization
    - Live trading simulation with mock data
    - Dynamic parameter updates every N minutes
    - Performance monitoring and reporting
    - Graceful shutdown handling
    """
    
    def __init__(self, symbol: Symbol):
        """Initialize the complete demo system."""
        self.symbol = symbol
        
        # Core components
        self.optimizer: Optional[DeltaArbitrageOptimizer] = None
        self.strategy: Optional[SimpleDeltaArbitrageStrategy] = None
        self.optimizer_bridge: Optional[OptimizerBridge] = None
        self.parameter_scheduler: Optional[ParameterScheduler] = None
        
        # Demo control
        self._demo_running = False
        self._demo_task: Optional[asyncio.Task] = None
        
        print(f"🚀 LiveStrategyDemo initialized for {symbol}")
    
    async def setup_system(self) -> None:
        """Setup all system components."""
        try:
            print("🔧 Setting up integrated delta arbitrage system...")
            
            # 1. Create optimization configuration
            opt_config = OptimizationConfig(
                target_hit_rate=0.7,
                min_trades_per_day=5,
                entry_percentile_range=(75, 85),
                exit_percentile_range=(25, 35),
                optimization_timeout_seconds=30.0
            )
            
            # 2. Initialize optimizer
            self.optimizer = DeltaArbitrageOptimizer(opt_config)
            print("✅ Optimizer initialized")
            
            # 3. Create strategy configuration
            strategy_config = create_default_config(self.symbol)
            strategy_config.parameter_update_interval_minutes = 2  # Fast updates for demo
            
            # 4. Initialize strategy
            self.strategy = SimpleDeltaArbitrageStrategy(strategy_config, self.optimizer)
            print("✅ Strategy initialized")
            
            # 5. Create optimizer bridge
            self.optimizer_bridge = OptimizerBridge(
                self.optimizer, 
                strategy_reference=self.strategy
            )
            print("✅ Optimizer bridge initialized")
            
            # 6. Create parameter scheduler with callback
            async def parameter_update_callback(optimization_result):
                """Callback to update strategy when parameters change."""
                if self.strategy:
                    self.strategy.context.update_parameters(optimization_result)
                    print(f"📈 Strategy parameters updated via scheduler")
            
            self.parameter_scheduler = ParameterScheduler(
                self.optimizer_bridge,
                update_callback=parameter_update_callback
            )
            print("✅ Parameter scheduler initialized")
            
            print("🎉 System setup completed successfully!")
            
        except Exception as e:
            print(f"❌ System setup failed: {e}")
            raise
    
    async def start_demo(self, duration_minutes: int = 10) -> None:
        """
        Start the complete demo.
        
        Args:
            duration_minutes: How long to run the demo
        """
        try:
            print(f"\n{'='*80}")
            print(f"🚀 STARTING LIVE DELTA ARBITRAGE DEMO")
            print(f"{'='*80}")
            print(f"Duration: {duration_minutes} minutes")
            print(f"Symbol: {self.symbol}")
            print(f"{'='*80}\n")
            
            self._demo_running = True
            
            # 1. Start strategy
            await self.strategy.start()
            
            # 2. Start parameter scheduler
            await self.parameter_scheduler.start_scheduled_updates(
                interval_minutes=2,  # Update every 2 minutes for demo
                lookback_hours=6,    # Use 6 hours of data
                min_data_points=50   # Lower threshold for demo
            )
            
            # 3. Start market data simulation and strategy execution
            self._demo_task = asyncio.create_task(
                self._run_demo_loop(duration_minutes)
            )
            
            # 4. Wait for demo completion or interruption
            await self._demo_task
            
        except asyncio.CancelledError:
            print("\n🛑 Demo interrupted by user")
        except Exception as e:
            print(f"\n❌ Demo error: {e}")
        finally:
            await self._cleanup_demo()
    
    async def stop_demo(self) -> None:
        """Stop the demo gracefully."""
        print("\n🛑 Stopping demo...")
        self._demo_running = False
        
        if self._demo_task and not self._demo_task.done():
            self._demo_task.cancel()
            try:
                await self._demo_task
            except asyncio.CancelledError:
                pass
    
    async def _run_demo_loop(self, duration_minutes: int) -> None:
        """Main demo execution loop."""
        import time
        
        demo_start = time.time()
        demo_end = demo_start + (duration_minutes * 60)
        
        # Status reporting intervals
        last_status_report = 0
        status_interval = 30  # Report every 30 seconds
        
        print("🎮 Starting demo execution loop...")
        
        # Start market simulation in parallel
        simulation_task = asyncio.create_task(
            self.strategy.simulate_market_data_feed(duration_minutes + 1)
        )
        
        try:
            while self._demo_running and time.time() < demo_end:
                current_time = time.time()
                
                # Run strategy cycle
                await self.strategy.run_strategy_cycle()
                
                # Periodic status reports
                if current_time - last_status_report >= status_interval:
                    await self._print_status_report()
                    last_status_report = current_time
                
                # Short sleep to prevent busy waiting
                await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"❌ Demo loop error: {e}")
        finally:
            # Stop market simulation
            if not simulation_task.done():
                simulation_task.cancel()
                try:
                    await simulation_task
                except asyncio.CancelledError:
                    pass
    
    async def _print_status_report(self) -> None:
        """Print comprehensive status report."""
        print(f"\n{'='*60}")
        print(f"📊 DEMO STATUS REPORT")
        print(f"{'='*60}")
        
        # Strategy status
        if self.strategy:
            summary = self.strategy.context.get_strategy_summary()
            print(f"STRATEGY STATUS:")
            print(f"• Active: {summary['is_active']}")
            print(f"• Total trades: {summary['performance']['total_trades']}")
            print(f"• Win rate: {summary['performance']['win_rate']:.1%}")
            print(f"• Net P&L: {summary['performance']['net_pnl']:.6f}")
            print(f"• Current parameters: Entry={summary['parameters']['entry_threshold_pct']:.4f}%, Exit={summary['parameters']['exit_threshold_pct']:.4f}%")
            
            if summary['positions']['spot_position'] != 0 or summary['positions']['futures_position'] != 0:
                print(f"• POSITION OPEN: Spot={summary['positions']['spot_position']:.2f}, Futures={summary['positions']['futures_position']:.2f}")
                print(f"• Delta: {summary['positions']['current_delta']:.2f}")
                print(f"• Hold time: {summary['positions']['position_hold_time_minutes']:.1f} minutes")
        
        # Scheduler status
        if self.parameter_scheduler:
            scheduler_status = self.parameter_scheduler.get_update_status()
            print(f"\nSCHEDULER STATUS:")
            print(f"• Status: {scheduler_status['scheduler_status']}")
            print(f"• Total updates: {scheduler_status['statistics']['total_updates']}")
            print(f"• Success rate: {scheduler_status['statistics']['success_rate']:.1%}")
            print(f"• Next update in: {scheduler_status['timing']['time_until_next_update_seconds']:.0f}s")
        
        # Health check
        await self._print_health_check()
        
        print(f"{'='*60}\n")
    
    async def _print_health_check(self) -> None:
        """Print system health status."""
        print(f"\nHEALTH CHECK:")
        
        # Strategy health
        if self.strategy and self.strategy.context.emergency_stop_triggered:
            print(f"• ❌ EMERGENCY STOP ACTIVE")
        else:
            print(f"• ✅ Strategy operational")
        
        # Scheduler health
        if self.parameter_scheduler:
            health = self.parameter_scheduler.get_health_status()
            if health['is_healthy']:
                print(f"• ✅ Scheduler healthy")
            else:
                print(f"• ⚠️ Scheduler issues: {', '.join(health['health_issues'])}")
        
        # Optimizer health
        if self.optimizer_bridge:
            bridge_health = self.optimizer_bridge.get_health_status()
            if bridge_health['is_healthy']:
                print(f"• ✅ Optimizer healthy")
            else:
                print(f"• ⚠️ Optimizer issues: {', '.join(bridge_health['health_issues'])}")
    
    async def _cleanup_demo(self) -> None:
        """Clean up all demo components."""
        print("\n🧹 Cleaning up demo components...")
        
        try:
            # Stop scheduler
            if self.parameter_scheduler:
                await self.parameter_scheduler.stop_scheduled_updates()
            
            # Stop strategy
            if self.strategy:
                await self.strategy.stop()
            
            print("✅ Demo cleanup completed")
            
        except Exception as e:
            print(f"❌ Cleanup error: {e}")
    
    async def print_final_summary(self) -> None:
        """Print comprehensive final summary."""
        print(f"\n{'='*80}")
        print(f"📊 FINAL DEMO SUMMARY")
        print(f"{'='*80}")
        
        if self.strategy:
            # Strategy summary
            summary = self.strategy.context.get_strategy_summary()
            
            print(f"TRADING PERFORMANCE:")
            print(f"• Symbol: {summary['symbol']}")
            print(f"• Total trades: {summary['performance']['total_trades']}")
            print(f"• Winning trades: {summary['performance']['winning_trades']}")
            print(f"• Win rate: {summary['performance']['win_rate']:.1%}")
            print(f"• Total P&L: {summary['performance']['total_pnl']:.6f}")
            print(f"• Total fees: {summary['performance']['total_fees']:.6f}")
            print(f"• Net P&L: {summary['performance']['net_pnl']:.6f}")
            
            if summary['performance']['total_trades'] > 0:
                print(f"• Average P&L per trade: {summary['performance']['average_pnl']:.6f}")
                print(f"• Max drawdown: {summary['performance']['max_drawdown']:.6f}")
        
        if self.parameter_scheduler:
            # Optimization summary
            scheduler_status = self.parameter_scheduler.get_update_status()
            
            print(f"\nOPTIMIZATION PERFORMANCE:")
            print(f"• Total parameter updates: {scheduler_status['statistics']['total_updates']}")
            print(f"• Successful updates: {scheduler_status['statistics']['successful_updates']}")
            print(f"• Update success rate: {scheduler_status['statistics']['success_rate']:.1%}")
            
            if self.optimizer_bridge:
                bridge_status = self.optimizer_bridge.get_optimization_status()
                print(f"• Average optimization time: {bridge_status['avg_optimization_time_seconds']:.3f}s")
        
        # Final parameter values
        if self.strategy and self.strategy.context.last_optimization_result:
            result = self.strategy.context.last_optimization_result
            print(f"\nFINAL PARAMETERS:")
            print(f"• Entry threshold: {result.entry_threshold_pct:.4f}%")
            print(f"• Exit threshold: {result.exit_threshold_pct:.4f}%")
            print(f"• Confidence score: {result.confidence_score:.3f}")
            print(f"• Mean reversion speed: {result.mean_reversion_speed:.4f}")
        
        print(f"{'='*80}")
        print(f"✅ Demo completed successfully!")
        print(f"{'='*80}\n")


async def main():
    """Main demo function."""
    # Setup signal handling for graceful shutdown
    demo = None
    
    def signal_handler(signum, frame):
        print(f"\n🛑 Received signal {signum}")
        if demo:
            asyncio.create_task(demo.stop_demo())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Configuration
        symbol = Symbol(base=AssetName("NEIROETH"), quote=AssetName("USDT"))
        demo_duration = 5  # 5 minutes for demo
        
        print(f"🚀 LIVE DELTA ARBITRAGE STRATEGY DEMO")
        print(f"Symbol: {symbol}")
        print(f"Duration: {demo_duration} minutes")
        print(f"{'='*80}")
        
        # Create and setup demo
        demo = LiveStrategyDemo(symbol)
        await demo.setup_system()
        
        # Run demo
        await demo.start_demo(demo_duration)
        
        # Print final results
        await demo.print_final_summary()
        
    except KeyboardInterrupt:
        print("\n🛑 Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if demo:
            await demo._cleanup_demo()


if __name__ == "__main__":
    print("🎮 Starting Live Delta Arbitrage Strategy Demo...")
    print("Press Ctrl+C to stop the demo at any time")
    print("="*80)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Demo terminated by user")
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
    
    print("\n🎉 Thank you for trying the Delta Arbitrage Strategy Demo!")