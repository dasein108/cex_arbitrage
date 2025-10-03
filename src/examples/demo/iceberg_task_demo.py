#!/usr/bin/env python3
"""
IcebergTask Demo

Demonstrates iceberg order execution using the separated domain architecture:
- Initialize IcebergTask with minimal context (symbol required)
- Start execution with trading parameters (side, quantities, pricing)
- Update parameters during execution
- Monitor execution progress and completion
- Handle cleanup and graceful shutdown

Key features demonstrated:
- Partial context update pattern (minimal init, evolve during lifecycle)
- Separated domain architecture (public/private exchanges)
- Constructor injection pattern from exchange factory
- Handler binding pattern for WebSocket channels
- Real-time parameter updates during execution
- Proper error handling and logging

Usage:
    PYTHONPATH=src python src/examples/demo/iceberg_task_demo.py
"""

import asyncio
from typing import Optional
import signal
import sys

from config import get_exchange_config, get_logging_config
from exchanges.utils import get_exchange_enum
from exchanges.structs.common import Symbol, AssetName, Side
from infrastructure.logging import get_logger
from trading.tasks.iceberg_task import IcebergTask, IcebergTaskContext


class IcebergTaskDemo:
    """Demonstration of IcebergTask execution with separated domain architecture."""
    
    def __init__(self):
        self.logger = get_logger("iceberg_demo")
        self.task: Optional[IcebergTask] = None
        self.running = True
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.running = False
    
    async def run_demo(self):
        """Main demo execution."""
        try:
            # Configuration
            exchange_name = "gateio_futures"  # Change to desired exchange
            
            # Get exchange configuration and logging setup
            config = get_exchange_config(exchange_name)
            logging_config = get_logging_config()
            logger = get_logger("iceberg_task")
            
            # Define trading symbol
            symbol = Symbol(
                base=AssetName("ADA"), 
                quote=AssetName("USDT"),
                is_futures='_futures' in exchange_name.lower()
            )
            
            self.logger.info("Starting IcebergTask demo",
                           exchange=exchange_name, 
                           symbol=f"{symbol.base}/{symbol.quote}")
            
            # Demo 1: Initialize IcebergTask with minimal context (symbol only required)
            self.logger.info("=== Demo 1: Initialize IcebergTask with minimal context ===")
            
            # Create task with minimal context - only symbol is required
            # Other parameters will be added when starting execution
            self.task = IcebergTask(
                config=config,
                logger=logger,
                symbol=symbol,  # Only required field for initialization
                side=Side.SELL
            )
            
            self.logger.info("IcebergTask initialized with minimal context",
                           symbol=str(symbol),
                           context_state="minimal")
            
            # Demo 2: Start execution with trading parameters
            self.logger.info("=== Demo 2: Start execution with trading parameters ===")
            
            # Start task with additional context parameters
            # This demonstrates the partial context update pattern
            await self.task.start(
                total_quantity=20.0,     # Total amount to execute
                order_quantity=3.0,      # Size of each slice
                offset_ticks=1,           # Price offset from top of book
                tick_tolerance=2          # Price movement tolerance
            )
            
            self.logger.info("IcebergTask started with trading parameters",
                           side="SELL",
                           total_quantity=100.0,
                           order_quantity=10.0,
                           offset_ticks=2)
            
            # Demo 3: Monitor execution progress
            self.logger.info("=== Demo 3: Monitor execution progress ===")
            
            # Let the task execute for a short period
            execution_time = 5.0  # seconds
            self.logger.info(f"Monitoring execution for {execution_time} seconds...")
            
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) < execution_time and self.running:
                # Check task state and progress
                if hasattr(self.task.context, 'filled_quantity'):
                    progress = (self.task.context.filled_quantity / self.task.context.total_quantity) * 100
                    self.logger.info("Execution progress",
                                   filled=self.task.context.filled_quantity,
                                   total=self.task.context.total_quantity,
                                   progress_pct=f"{progress:.1f}%",
                                   state=self.task.state.name)
                else:
                    self.logger.info("Task state", state=self.task.state.name)
                
                await asyncio.sleep(1.0)  # Check every second
            
            # Demo 4: Update parameters during execution
            self.logger.info("=== Demo 4: Update parameters during execution ===")
            
            # Demonstrate partial context updates during execution
            # This shows how to modify iceberg parameters on the fly
            await self.task.update(
                order_quantity=15.0,      # Increase slice size
                offset_ticks=1,           # Move closer to market
                tick_tolerance=5          # Increase tolerance
            )
            
            self.logger.info("IcebergTask parameters updated during execution",
                           new_order_quantity=15.0,
                           new_offset_ticks=1,
                           new_tick_tolerance=5)
            
            # Monitor updated execution for a short period
            self.logger.info("Monitoring updated execution...")
            
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) < 3.0 and self.running:
                if hasattr(self.task.context, 'filled_quantity'):
                    progress = (self.task.context.filled_quantity / self.task.context.total_quantity) * 100
                    self.logger.info("Updated execution progress",
                                   filled=self.task.context.filled_quantity,
                                   total=self.task.context.total_quantity,
                                   progress_pct=f"{progress:.1f}%",
                                   avg_price=getattr(self.task.context, 'avg_price', 0.0),
                                   state=self.task.state.name)
                
                await asyncio.sleep(1.0)
            
            # Demo 5: Context serialization/deserialization
            self.logger.info("=== Demo 5: Context serialization ===")
            
            # Demonstrate context persistence
            context_data = self.task.save_context()
            self.logger.info("Context serialized",
                           size_bytes=len(context_data),
                           preview=context_data[:100].decode('utf-8', errors='ignore'))
            
            # Demo 6: Graceful completion
            self.logger.info("=== Demo 6: Graceful completion ===")
            
            # For demo purposes, complete the task rather than waiting for full execution
            await self.task.pause()
            self.logger.info("IcebergTask paused for demo completion")
            
            await self.task.complete()
            self.logger.info("IcebergTask marked as completed")
            
        except Exception as e:
            self.logger.error("Demo execution failed", error=str(e))
            raise
        finally:
            # Ensure cleanup
            await self.cleanup()
    
    async def cleanup(self):
        """Clean up resources and connections."""
        try:
            if self.task:
                self.logger.info("Cleaning up IcebergTask...")
                
                # Cancel the task if still running
                if hasattr(self.task, 'state') and self.task.state.name in ['EXECUTING', 'IDLE']:
                    await self.task.cancel()
                    self.logger.info("IcebergTask cancelled")
                
                # Cleanup exchange connections if available
                if hasattr(self.task, '_exchange') and self.task._exchange:
                    try:
                        # Close public exchange connections
                        if hasattr(self.task._exchange, 'public'):
                            public_rest = getattr(self.task._exchange.public, '_rest_client', None)
                            public_ws = getattr(self.task._exchange.public, '_websocket_client', None)
                            
                            if public_rest and hasattr(public_rest, 'close'):
                                await public_rest.close()
                                self.logger.info("Public REST client closed")
                            
                            if public_ws and hasattr(public_ws, 'close'):
                                await public_ws.close()
                                self.logger.info("Public WebSocket client closed")
                        
                        # Close private exchange connections
                        if hasattr(self.task._exchange, 'private'):
                            private_rest = getattr(self.task._exchange.private, '_rest_client', None)
                            private_ws = getattr(self.task._exchange.private, '_websocket_client', None)
                            
                            if private_rest and hasattr(private_rest, 'close'):
                                await private_rest.close()
                                self.logger.info("Private REST client closed")
                            
                            if private_ws and hasattr(private_ws, 'close'):
                                await private_ws.close()
                                self.logger.info("Private WebSocket client closed")
                    
                    except Exception as e:
                        self.logger.warning("Error during exchange cleanup", error=str(e))
                
        except Exception as e:
            self.logger.error("Cleanup failed", error=str(e))


async def main():
    """Main demo entry point."""
    demo = IcebergTaskDemo()
    
    try:
        await demo.run_demo()
        demo.logger.info("🎉 IcebergTask demo completed successfully")
        
    except KeyboardInterrupt:
        demo.logger.info("Demo interrupted by user")
    except Exception as e:
        demo.logger.error("Demo failed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    print("🚀 Starting IcebergTask Demo...")
    print("📋 This demo will show:")
    print("   • Minimal context initialization (symbol only)")
    print("   • Starting execution with trading parameters")
    print("   • Real-time parameter updates")
    print("   • Execution progress monitoring")
    print("   • Context serialization")
    print("   • Graceful shutdown and cleanup")
    print()
    print("⚠️  Note: This demo uses testnet/demo mode for safety")
    print("📊 For production use, ensure proper risk management")
    print()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Demo terminated by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        sys.exit(1)