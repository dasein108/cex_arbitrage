#!/usr/bin/env python3
"""
Multi-Spot Futures Arbitrage Demo

Demonstrates the new multi-spot arbitrage functionality with:
- Multiple spot exchanges (MEXC + Binance) + single futures (Gate.io)
- Two operation modes: traditional vs spot switching
- Intelligent opportunity scanning and position migration
- Enhanced risk management with delta neutrality validation

Usage:
    python src/examples/demo/multi_spot_arbitrage_demo.py [--mode traditional|spot_switching] [--duration 60] [--symbol BTCUSDT]
"""

import asyncio
import argparse
import signal
import sys
from typing import Optional

from trading.tasks.multi_spot_futures_arbitrage_task import create_multi_spot_futures_arbitrage_task
from exchanges.structs import Symbol, AssetName, ExchangeEnum
from infrastructure.logging import get_logger


class MultiSpotArbitrageDemo:
    """Demo controller for multi-spot arbitrage strategy."""
    
    def __init__(self, 
                 symbol: Symbol,
                 operation_mode: str = 'spot_switching',
                 duration_seconds: int = 300):
        self.symbol = symbol
        self.operation_mode = operation_mode
        self.duration_seconds = duration_seconds
        self.task = None
        self.running = True
        
        # Setup logging
        self.logger = get_logger(f'multi_spot_demo.{symbol}')
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info(f"🛑 Received signal {signum}, initiating graceful shutdown...")
        self.running = False
    
    async def run_demo(self):
        """Run the multi-spot arbitrage demo."""
        try:
            self.logger.info("🚀 Starting Multi-Spot Futures Arbitrage Demo")
            self.logger.info(f"📊 Symbol: {self.symbol}")
            self.logger.info(f"🔄 Operation Mode: {self.operation_mode}")
            self.logger.info(f"⏱️  Duration: {self.duration_seconds} seconds")
            self.logger.info("="*80)
            
            # Create multi-spot arbitrage task
            self.task = await create_multi_spot_futures_arbitrage_task(
                symbol=self.symbol,
                spot_exchanges=[ExchangeEnum.MEXC, ExchangeEnum.GATEIO],  # Multiple spots
                futures_exchange=ExchangeEnum.GATEIO_FUTURES,              # Single futures hedge
                operation_mode=self.operation_mode,
                base_position_size_usdt=50.0,  # Smaller size for demo
                max_entry_cost_pct=0.3,        # More aggressive entry
                min_profit_pct=0.05,           # Lower profit target for demo
                max_hours=1.0,                 # Shorter timeout for demo
                min_switch_profit_pct=0.02,    # Lower switch threshold for demo
                logger=self.logger
            )
            
            self.logger.info("✅ Multi-spot arbitrage task created and started")
            
            if self.operation_mode == 'spot_switching':
                self.logger.info("🔄 Spot switching mode: Will migrate positions between MEXC and Binance")
                self.logger.info("   - Initial entry: Best price between MEXC/Binance vs Gate.io futures")
                self.logger.info("   - Dynamic switching: Move between MEXC/Binance for better opportunities")
                self.logger.info("   - Futures hedge: Maintained throughout on Gate.io futures")
            else:
                self.logger.info("📈 Traditional mode: Single entry/exit between best spot and futures")
            
            # Monitor task execution
            await self._monitor_task_execution()
            
        except Exception as e:
            self.logger.error(f"❌ Demo execution error: {e}")
            raise
        finally:
            await self._cleanup()
    
    async def _monitor_task_execution(self):
        """Monitor the task execution and log key events."""
        start_time = asyncio.get_event_loop().time()
        last_status_time = start_time
        
        while self.running and (asyncio.get_event_loop().time() - start_time) < self.duration_seconds:
            try:
                # Check if task is still running
                if self.task.is_done():
                    self.logger.info("🏁 Task completed")
                    break
                
                # Log status every 30 seconds
                current_time = asyncio.get_event_loop().time()
                if current_time - last_status_time >= 30:
                    await self._log_task_status()
                    last_status_time = current_time
                
                # Wait before next check
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"❌ Monitoring error: {e}")
                break
        
        if not self.task.is_done():
            self.logger.info("⏰ Demo duration completed, stopping task...")
    
    async def _log_task_status(self):
        """Log current task status and positions."""
        try:
            if not self.task or not self.task.context:
                return
            
            context = self.task.context
            state = context.status
            arbitrage_state = context.arbitrage_state
            
            self.logger.info(f"📊 Status: {state} | Arbitrage: {arbitrage_state}")
            
            # Log multi-spot positions if available
            if context.multi_spot_positions and context.multi_spot_positions.has_positions:
                active_spot = context.multi_spot_positions.active_spot_exchange
                spot_pos = context.multi_spot_positions.active_spot_position
                futures_pos = context.multi_spot_positions.futures_position
                delta = context.multi_spot_positions.delta
                
                self.logger.info(f"💼 Positions: Spot({active_spot})={spot_pos}, Futures={futures_pos}")
                self.logger.info(f"⚖️  Delta: {delta:.6f} (neutral: {abs(delta) < 0.001})")
                
                if context.total_volume_usdt > 0:
                    self.logger.info(f"📈 Total Volume: ${context.total_volume_usdt:.2f}")
            
            # Log current opportunity if analyzing
            if arbitrage_state == 'analyzing' and context.current_opportunity:
                opp = context.current_opportunity
                self.logger.info(f"🎯 Opportunity: {opp.direction} at {opp.spread_pct:.4f}% spread")
            
            # Log operation mode specific info
            if context.operation_mode == 'spot_switching':
                self.logger.info(f"🔄 Spot switching enabled: {context.spot_switch_enabled}")
                self.logger.info(f"📊 Switch threshold: {context.min_switch_profit_pct:.2f}%")
                
        except Exception as e:
            self.logger.error(f"❌ Status logging error: {e}")
    
    async def _cleanup(self):
        """Clean up resources and stop the task."""
        try:
            if self.task and not self.task.is_done():
                self.logger.info("🧹 Stopping multi-spot arbitrage task...")
                await self.task.stop()
                self.logger.info("✅ Task stopped successfully")
            
            self.logger.info("🏁 Multi-Spot Futures Arbitrage Demo completed")
            
        except Exception as e:
            self.logger.error(f"❌ Cleanup error: {e}")


async def main():
    """Main demo entry point."""
    parser = argparse.ArgumentParser(description='Multi-Spot Futures Arbitrage Demo')
    parser.add_argument('--mode', choices=['traditional', 'spot_switching'], 
                       default='spot_switching', help='Operation mode')
    parser.add_argument('--duration', type=int, default=300, 
                       help='Demo duration in seconds')
    parser.add_argument('--symbol', type=str, default='BTCUSDT', 
                       help='Trading symbol')
    
    args = parser.parse_args()
    
    # Parse symbol
    if 'USDT' in args.symbol:
        base = args.symbol.replace('USDT', '')
        quote = 'USDT'
    elif 'BTC' in args.symbol and args.symbol != 'BTC':
        base = args.symbol.replace('BTC', '')
        quote = 'BTC'
    else:
        base = args.symbol
        quote = 'USDT'
    
    symbol = Symbol(base=AssetName(base), quote=AssetName(quote))
    
    # Create and run demo
    demo = MultiSpotArbitrageDemo(
        symbol=symbol,
        operation_mode=args.mode,
        duration_seconds=args.duration
    )
    
    try:
        await demo.run_demo()
    except KeyboardInterrupt:
        print("\n🛑 Demo interrupted by user")
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())