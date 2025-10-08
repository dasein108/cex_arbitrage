#!/usr/bin/env python3
"""
Enhanced 3-Exchange Delta Neutral Task with State Machine Integration

Integrates the sophisticated state machine for 3-exchange delta neutral arbitrage
with the existing TaskManager infrastructure. This provides a production-ready
implementation that combines:

1. State machine coordination for complex multi-exchange logic
2. TaskManager integration for persistence and monitoring
3. Real-time analytics and performance tracking
4. HFT-optimized execution with sub-50ms cycles

The task coordinates between:
- Gate.io spot (for delta neutral hedging)
- Gate.io futures (for delta neutral hedging) 
- MEXC spot (for arbitrage opportunities)

Usage:
    PYTHONPATH=src python hedged_arbitrage/strategy/enhanced_delta_neutral_task.py
"""

import sys
from pathlib import Path

# Add src to path for imports when running from anywhere
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import asyncio
from typing import Optional, Dict, Any
import signal
import os
from datetime import datetime, timedelta
from decimal import Decimal

# Configure immediate logging for dev environment
os.environ['ENVIRONMENT'] = 'dev'

# Ensure src is in path
sys.path.insert(0, str(project_root / "src"))

try:
    from exchanges.structs.common import Symbol
    from exchanges.structs.types import AssetName
    from common.logger_factory import LoggerFactory
    from tasks.base_task import BaseTask
    from tasks.task_manager import TaskManager
    from common.enums import ExchangeEnum
except ImportError as e:
    print(f"⚠️  Import warning: {e}")
    print("Running in standalone mode without TaskManager integration")
    
    # Fallback imports for testing
    from exchanges.structs.common import Symbol
    from exchanges.structs.types import AssetName
    
    # Create minimal logger
    import logging
    class LoggerFactory:
        @staticmethod
        def get_logger(name):
            return logging.getLogger(name)
    
    # Mock BaseTask for testing
    class BaseTask:
        def __init__(self, context=None):
            self.context = context or {}
            self.task_id = f"task_{id(self)}"
        
        async def update_context(self, key, value):
            self.context[key] = value
    
    # Mock TaskManager
    class TaskManager:
        async def add_task(self, task): pass
        async def start(self): pass
        async def stop(self): pass

# Import our state machine
try:
    from .state_machine import (
        DeltaNeutralArbitrageStateMachine,
        StrategyConfiguration,
        StrategyState
    )
except ImportError:
    from state_machine import (
        DeltaNeutralArbitrageStateMachine,
        StrategyConfiguration,
        StrategyState
    )

logger = LoggerFactory.get_logger('enhanced_delta_neutral_task')


class EnhancedDeltaNeutralTask(BaseTask):
    """
    Enhanced Delta Neutral Task with 3-Exchange State Machine Integration.
    
    Combines the sophisticated state machine logic with TaskManager infrastructure
    for production-ready delta neutral arbitrage across Gate.io and MEXC.
    """
    
    def __init__(self, 
                 symbol: Symbol,
                 base_position_size: float = 100.0,
                 arbitrage_entry_threshold: float = 0.1,
                 arbitrage_exit_threshold: float = 0.01):
        """
        Initialize enhanced delta neutral task.
        
        Args:
            symbol: Trading symbol (e.g., NEIROETH/USDT)
            base_position_size: Base position size for delta neutral trades
            arbitrage_entry_threshold: Entry threshold percentage for arbitrage
            arbitrage_exit_threshold: Exit threshold percentage for arbitrage
        """
        # Create task context for TaskManager
        context = {
            'symbol': f"{symbol.base}/{symbol.quote}",
            'strategy_type': 'enhanced_delta_neutral_3exchange',
            'base_position_size': base_position_size,
            'exchanges': ['GATEIO_SPOT', 'GATEIO_FUTURES', 'MEXC_SPOT'],
            'entry_threshold_pct': arbitrage_entry_threshold,
            'exit_threshold_pct': arbitrage_exit_threshold
        }
        
        super().__init__(context=context)
        
        self.symbol = symbol
        self.base_position_size = base_position_size
        
        # Create strategy configuration
        self.strategy_config = StrategyConfiguration(
            symbol=symbol,
            base_position_size=Decimal(str(base_position_size)),
            arbitrage_entry_threshold_pct=Decimal(str(arbitrage_entry_threshold)),
            arbitrage_exit_threshold_pct=Decimal(str(arbitrage_exit_threshold)),
            exchanges={
                'GATEIO_SPOT': 'GATEIO_SPOT',
                'GATEIO_FUTURES': 'GATEIO_FUTURES', 
                'MEXC_SPOT': 'MEXC_SPOT'
            }
        )
        
        # Initialize state machine
        self.state_machine = DeltaNeutralArbitrageStateMachine(self.strategy_config)
        
        # Task state tracking
        self.is_running = False
        self.execution_start_time: Optional[datetime] = None
        self.last_status_update = datetime.utcnow()
        
        logger.info(f"✅ Enhanced delta neutral task initialized for {symbol.base}/{symbol.quote}")
    
    async def execute(self) -> bool:
        """
        Execute the enhanced delta neutral strategy.
        
        Returns:
            bool: True if execution completed successfully
        """
        try:
            logger.info(f"🚀 Starting enhanced delta neutral execution for {self.symbol.base}/{self.symbol.quote}")
            self.execution_start_time = datetime.utcnow()
            self.is_running = True
            
            # Update task status
            await self.update_context('status', 'running')
            await self.update_context('start_time', self.execution_start_time.isoformat())
            
            # Start the state machine
            state_machine_task = asyncio.create_task(self.state_machine.start())
            
            # Monitor execution with periodic status updates
            monitor_task = asyncio.create_task(self._monitor_execution())
            
            # Wait for either completion or termination
            done, pending = await asyncio.wait(
                [state_machine_task, monitor_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # Check if state machine completed successfully
            if state_machine_task in done:
                if not state_machine_task.exception():
                    logger.info("✅ State machine completed successfully")
                    await self.update_context('status', 'completed')
                    return True
                else:
                    logger.error(f"❌ State machine failed: {state_machine_task.exception()}")
                    await self.update_context('status', 'failed')
                    await self.update_context('error', str(state_machine_task.exception()))
                    return False
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Enhanced delta neutral execution failed: {e}")
            await self.update_context('status', 'failed')
            await self.update_context('error', str(e))
            return False
        finally:
            self.is_running = False
            execution_duration = datetime.utcnow() - (self.execution_start_time or datetime.utcnow())
            await self.update_context('execution_duration_seconds', execution_duration.total_seconds())
            logger.info(f"📊 Enhanced delta neutral execution completed in {execution_duration}")
    
    async def _monitor_execution(self) -> None:
        """Monitor strategy execution and update task context."""
        while self.is_running:
            try:
                # Get current strategy status
                status = self.state_machine.get_current_status()
                
                # Update task context with current metrics
                await self.update_context('current_state', status['state'])
                await self.update_context('total_trades', status['total_trades'])
                await self.update_context('total_pnl', status['total_pnl'])
                await self.update_context('delta_neutral', status['delta_neutral'])
                await self.update_context('positions_count', status['positions_count'])
                await self.update_context('arbitrage_active', status['arbitrage_active'])
                
                # Log periodic status updates
                now = datetime.utcnow()
                if (now - self.last_status_update).total_seconds() >= 30:  # Every 30 seconds
                    logger.info(
                        f"📊 Strategy Status - State: {status['state']} | "
                        f"Trades: {status['total_trades']} | "
                        f"P&L: ${status['total_pnl']:.4f} | "
                        f"Delta Neutral: {status['delta_neutral']}"
                    )
                    self.last_status_update = now
                
                await asyncio.sleep(1)  # Update every second
                
            except Exception as e:
                logger.warning(f"⚠️  Monitor update failed: {e}")
                await asyncio.sleep(5)  # Longer sleep on error
    
    async def stop(self) -> None:
        """Stop the enhanced delta neutral task."""
        logger.info("🛑 Stopping enhanced delta neutral task")
        self.is_running = False
        
        # Stop the state machine
        await self.state_machine.stop()
        
        # Update task status
        await self.update_context('status', 'stopped')
        await self.update_context('stop_time', datetime.utcnow().isoformat())
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        status = self.state_machine.get_current_status()
        context = self.context or {}
        
        execution_duration = None
        if self.execution_start_time:
            execution_duration = (datetime.utcnow() - self.execution_start_time).total_seconds()
        
        return {
            'task_info': {
                'symbol': f"{self.symbol.base}/{self.symbol.quote}",
                'strategy_type': 'enhanced_delta_neutral_3exchange',
                'base_position_size': self.base_position_size,
                'execution_duration_seconds': execution_duration
            },
            'strategy_performance': status,
            'task_context': context,
            'configuration': {
                'entry_threshold_pct': float(self.strategy_config.arbitrage_entry_threshold_pct),
                'exit_threshold_pct': float(self.strategy_config.arbitrage_exit_threshold_pct),
                'max_position_multiplier': float(self.strategy_config.max_position_multiplier),
                'exchanges': list(self.strategy_config.exchanges.keys())
            }
        }


async def create_and_run_enhanced_task(
    symbol: Symbol,
    duration_minutes: int = 5,
    base_position_size: float = 100.0,
    entry_threshold: float = 0.1,
    exit_threshold: float = 0.01
) -> EnhancedDeltaNeutralTask:
    """
    Create and run enhanced delta neutral task with TaskManager integration.
    
    Args:
        symbol: Trading symbol
        duration_minutes: How long to run the strategy
        base_position_size: Base position size
        entry_threshold: Entry threshold percentage
        exit_threshold: Exit threshold percentage
        
    Returns:
        EnhancedDeltaNeutralTask: The completed task instance
    """
    logger.info(f"🚀 Creating enhanced delta neutral task for {symbol.base}/{symbol.quote}")
    
    # Create the enhanced task
    task = EnhancedDeltaNeutralTask(
        symbol=symbol,
        base_position_size=base_position_size,
        arbitrage_entry_threshold=entry_threshold,
        arbitrage_exit_threshold=exit_threshold
    )
    
    # Initialize TaskManager
    task_manager = TaskManager()
    
    try:
        # Add task to TaskManager
        await task_manager.add_task(task)
        logger.info(f"✅ Task added to TaskManager with ID: {task.task_id}")
        
        # Start TaskManager
        manager_task = asyncio.create_task(task_manager.start())
        
        # Let it run for specified duration
        logger.info(f"⏰ Running strategy for {duration_minutes} minutes...")
        await asyncio.sleep(duration_minutes * 60)
        
        # Stop the task
        await task.stop()
        
        # Stop TaskManager
        await task_manager.stop()
        await manager_task
        
        # Get final performance summary
        performance = task.get_performance_summary()
        logger.info("📊 Final Performance Summary:")
        logger.info(f"   Strategy Type: {performance['task_info']['strategy_type']}")
        logger.info(f"   Symbol: {performance['task_info']['symbol']}")
        logger.info(f"   Duration: {performance['task_info']['execution_duration_seconds']:.1f}s")
        logger.info(f"   Total Trades: {performance['strategy_performance']['total_trades']}")
        logger.info(f"   Total P&L: ${performance['strategy_performance']['total_pnl']:.4f}")
        logger.info(f"   Final State: {performance['strategy_performance']['state']}")
        
        return task
        
    except Exception as e:
        logger.error(f"❌ Enhanced task execution failed: {e}")
        await task_manager.stop()
        raise


async def run_neiroeth_demo():
    """Run NEIROETH demo with the enhanced 3-exchange delta neutral strategy."""
    print("🚀 Enhanced 3-Exchange Delta Neutral Strategy Demo")
    print("=" * 70)
    print("Strategy: Gate.io Spot + Gate.io Futures (Delta Neutral) + MEXC Spot (Arbitrage)")
    print()
    
    # Create NEIROETH symbol
    symbol = Symbol(base=AssetName("NEIROETH"), quote=AssetName("USDT"))
    
    print(f"📊 Symbol: {symbol.base}/{symbol.quote}")
    print(f"💰 Base Position Size: 50.0")
    print(f"📈 Entry Threshold: 0.1%")
    print(f"📉 Exit Threshold: 0.01%")
    print(f"⏰ Demo Duration: 2 minutes")
    print()
    
    try:
        # Run the enhanced task
        task = await create_and_run_enhanced_task(
            symbol=symbol,
            duration_minutes=2,  # Short demo
            base_position_size=50.0,
            entry_threshold=0.1,
            exit_threshold=0.01
        )
        
        print("\n✅ Enhanced delta neutral strategy demo completed successfully!")
        
        # Display final summary
        performance = task.get_performance_summary()
        print("\n📈 Key Results:")
        print(f"   • Total Execution Time: {performance['task_info']['execution_duration_seconds']:.1f}s")
        print(f"   • Trades Executed: {performance['strategy_performance']['total_trades']}")
        print(f"   • Net P&L: ${performance['strategy_performance']['total_pnl']:.4f}")
        print(f"   • Delta Neutral Status: {performance['strategy_performance']['delta_neutral']}")
        print(f"   • Final State: {performance['strategy_performance']['state']}")
        
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Main execution with graceful shutdown handling."""
    # Set up signal handling for graceful shutdown
    shutdown_event = asyncio.Event()
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Run the demo
        demo_task = asyncio.create_task(run_neiroeth_demo())
        shutdown_task = asyncio.create_task(shutdown_event.wait())
        
        # Wait for either completion or shutdown signal
        done, pending = await asyncio.wait(
            [demo_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel remaining tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        if shutdown_task in done:
            logger.info("🛑 Shutdown signal received, demo terminated")
        
    except Exception as e:
        logger.error(f"❌ Main execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())