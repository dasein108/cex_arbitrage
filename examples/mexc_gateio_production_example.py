#!/usr/bin/env python3
"""
MEXC-Gate.io Arbitrage Strategy Production Example

This example demonstrates a production-ready setup with comprehensive
monitoring, risk management, and error handling.

Features demonstrated:
- Production configuration loading
- Advanced monitoring and alerting
- Risk management controls
- Performance tracking
- Graceful shutdown procedures

Usage:
    python examples/mexc_gateio_production_example.py --config config/mexc_gateio_production.json
    python examples/mexc_gateio_production_example.py --symbol BTC/USDT --position-size 100.0
"""

import sys
import asyncio
import argparse
import json
import signal
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, Optional

# Add src to path for imports
current_dir = Path(__file__).parent
project_root = current_dir.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from exchanges.structs import Symbol
from exchanges.structs.types import AssetName
from infrastructure.logging import get_logger
from applications.hedged_arbitrage.strategy.mexc_gateio_futures_strategy import (
    create_mexc_gateio_strategy
)


@dataclass
class ProductionConfig:
    """Production configuration structure."""
    # Strategy parameters
    symbol: str
    base_position_size: float
    entry_threshold_bps: int
    exit_threshold_bps: int
    futures_leverage: float
    
    # Risk management
    max_drawdown_pct: float
    delta_tolerance: float
    position_timeout_minutes: int
    emergency_exit_threshold_pct: float
    
    # Monitoring
    monitoring_interval: int
    enable_alerts: bool
    log_level: str


class ProductionMonitor:
    """Production-grade monitoring system."""
    
    def __init__(self, strategy, config: ProductionConfig, logger):
        self.strategy = strategy
        self.config = config
        self.logger = logger
        
        # Monitoring state
        self.start_time = time.time()
        self.last_health_check = 0.0
        self.performance_history = []
        self.alert_count = 0
        
        # Risk tracking
        self.max_drawdown_seen = 0.0
        self.consecutive_errors = 0
    
    async def monitor_loop(self):
        """Production monitoring loop."""
        self.logger.info("🔍 Starting production monitoring")
        
        while True:
            try:
                current_time = time.time()
                
                # Comprehensive health check
                await self._comprehensive_health_check()
                
                # Risk assessment
                await self._risk_assessment()
                
                # Performance tracking
                await self._performance_tracking()
                
                # Status reporting
                if current_time - self.last_health_check >= self.config.monitoring_interval:
                    await self._status_report()
                    self.last_health_check = current_time
                
                # Reset error counter on successful cycle
                self.consecutive_errors = 0
                
                await asyncio.sleep(5)  # 5-second monitoring cycle
                
            except Exception as e:
                self.consecutive_errors += 1
                self.logger.error(f"❌ Monitoring error #{self.consecutive_errors}: {e}")
                
                if self.consecutive_errors >= 3:
                    await self._trigger_emergency_shutdown("Too many monitoring errors")
                    break
                
                await asyncio.sleep(1)  # Brief pause before retry
    
    async def _comprehensive_health_check(self):
        """Comprehensive health assessment."""
        try:
            # Exchange health
            if hasattr(self.strategy, 'exchange_manager'):
                health = await self.strategy.exchange_manager.health_check()
                
                if health['overall_status'] != 'healthy':
                    self.alert_count += 1
                    self.logger.warning(f"🔗 Exchange health degraded: {health}")
            
            # Strategy state health
            if hasattr(self.strategy.context, 'state'):
                state_name = self.strategy.context.state.name
                if state_name in ['ERROR_RECOVERY', 'IDLE']:
                    self.logger.warning(f"⚠️ Strategy in concerning state: {state_name}")
            
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
    
    async def _risk_assessment(self):
        """Continuous risk assessment."""
        try:
            summary = self.strategy.get_strategy_summary()
            
            # Drawdown monitoring
            current_profit = summary['performance']['total_profit']
            if current_profit < 0:
                drawdown_pct = abs(current_profit) / self.config.base_position_size * 100
                self.max_drawdown_seen = max(self.max_drawdown_seen, drawdown_pct)
                
                if drawdown_pct > self.config.emergency_exit_threshold_pct:
                    await self._trigger_emergency_shutdown(f"Drawdown {drawdown_pct:.2f}% exceeds limit")
                elif drawdown_pct > self.config.max_drawdown_pct:
                    self.logger.warning(f"⚠️ High drawdown: {drawdown_pct:.2f}%")
            
            # Delta exposure monitoring
            current_delta = abs(summary['positions']['current_delta'])
            if current_delta > self.config.delta_tolerance * 2:
                self.logger.warning(f"⚠️ High delta exposure: {current_delta:.4f}")
            
            # Position timeout monitoring
            # (Implementation would depend on position timestamp tracking)
            
        except Exception as e:
            self.logger.error(f"Risk assessment failed: {e}")
    
    async def _performance_tracking(self):
        """Track and analyze performance metrics."""
        try:
            current_time = time.time()
            summary = self.strategy.get_strategy_summary()
            
            # Create performance snapshot
            snapshot = {
                'timestamp': current_time,
                'uptime_hours': (current_time - self.start_time) / 3600,
                'total_profit': summary['performance']['total_profit'],
                'total_volume': summary['performance']['total_volume'],
                'arbitrage_cycles': summary['performance']['arbitrage_cycles'],
                'current_delta': summary['positions']['current_delta'],
                'max_drawdown': self.max_drawdown_seen
            }
            
            self.performance_history.append(snapshot)
            
            # Keep only last 24 hours
            cutoff_time = current_time - (24 * 3600)
            self.performance_history = [
                p for p in self.performance_history if p['timestamp'] > cutoff_time
            ]
            
        except Exception as e:
            self.logger.error(f"Performance tracking failed: {e}")
    
    async def _status_report(self):
        """Detailed status reporting."""
        try:
            summary = self.strategy.get_strategy_summary()
            uptime_hours = (time.time() - self.start_time) / 3600
            
            self.logger.info(f"📊 PRODUCTION STATUS REPORT")
            self.logger.info(f"  • Uptime: {uptime_hours:.2f} hours")
            self.logger.info(f"  • Total Profit: {summary['performance']['total_profit']:.4f}")
            self.logger.info(f"  • Arbitrage Cycles: {summary['performance']['arbitrage_cycles']}")
            self.logger.info(f"  • Total Volume: {summary['performance']['total_volume']:.2f}")
            self.logger.info(f"  • Current Delta: {summary['positions']['current_delta']:.4f}")
            self.logger.info(f"  • Max Drawdown: {self.max_drawdown_seen:.2f}%")
            self.logger.info(f"  • Alert Count: {self.alert_count}")
            
            # Exchange status
            if hasattr(self.strategy, 'exchange_manager'):
                health = await self.strategy.exchange_manager.health_check()
                self.logger.info(f"  • Exchange Health: {health['connected_exchanges']}/{health['total_exchanges']} connected")
            
        except Exception as e:
            self.logger.error(f"Status report failed: {e}")
    
    async def _trigger_emergency_shutdown(self, reason: str):
        """Trigger emergency shutdown procedure."""
        self.logger.error(f"🚨 EMERGENCY SHUTDOWN: {reason}")
        
        try:
            # Attempt graceful strategy cleanup
            await self.strategy.cleanup()
            self.logger.info("✅ Emergency cleanup completed")
        except Exception as e:
            self.logger.error(f"❌ Emergency cleanup failed: {e}")


async def production_example(config: ProductionConfig):
    """Production strategy execution example."""
    
    logger = get_logger('mexc_gateio_production')
    
    print("🏭 MEXC-Gate.io Arbitrage Strategy - Production Mode")
    print("=" * 60)
    
    # Parse symbol
    base, quote = config.symbol.split('/')
    symbol = Symbol(base=AssetName(base), quote=AssetName(quote))
    
    print(f"📊 Production Configuration:")
    print(f"  • Symbol: {symbol.base}/{symbol.quote}")
    print(f"  • Position Size: {config.base_position_size}")
    print(f"  • Entry Threshold: {config.entry_threshold_bps} bps")
    print(f"  • Exit Threshold: {config.exit_threshold_bps} bps")
    print(f"  • Max Drawdown: {config.max_drawdown_pct}%")
    print(f"  • Emergency Exit: {config.emergency_exit_threshold_pct}%")
    print(f"  • Monitoring Interval: {config.monitoring_interval}s")
    print()
    
    # Setup shutdown handling
    shutdown_event = asyncio.Event()
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating production shutdown...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        print("🚀 Initializing production strategy...")
        
        # Create strategy
        strategy = await create_mexc_gateio_strategy(
            symbol=symbol,
            base_position_size_usdt=config.base_position_size,
            entry_threshold_bps=config.entry_threshold_bps,
            exit_threshold_bps=config.exit_threshold_bps,
            futures_leverage=config.futures_leverage
        )
        
        print("✅ Strategy initialized successfully!")
        
        # Initialize production monitoring
        monitor = ProductionMonitor(strategy, config, logger)
        
        print("📡 Starting production monitoring...")
        print("🔍 Press Ctrl+C for graceful shutdown")
        print("=" * 60)
        
        # Start monitoring task
        monitor_task = asyncio.create_task(monitor.monitor_loop())
        shutdown_task = asyncio.create_task(shutdown_event.wait())
        
        # Wait for shutdown or monitor exit
        done, pending = await asyncio.wait(
            [monitor_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel remaining tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        print("\n" + "=" * 60)
        print("📊 Final Production Summary:")
        
        final_summary = strategy.get_strategy_summary()
        runtime_hours = (time.time() - monitor.start_time) / 3600
        
        print(f"  • Runtime: {runtime_hours:.2f} hours")
        print(f"  • Total Profit: {final_summary['performance']['total_profit']:.4f}")
        print(f"  • Total Volume: {final_summary['performance']['total_volume']:.2f}")
        print(f"  • Arbitrage Cycles: {final_summary['performance']['arbitrage_cycles']}")
        print(f"  • Max Drawdown: {monitor.max_drawdown_seen:.2f}%")
        print(f"  • Alert Count: {monitor.alert_count}")
        
        print("\n🔄 Performing graceful shutdown...")
        await strategy.cleanup()
        print("✅ Production shutdown completed successfully!")
        
    except Exception as e:
        print(f"❌ Production error: {e}")
        import traceback
        traceback.print_exc()


def load_config(config_path: str) -> ProductionConfig:
    """Load production configuration from JSON file."""
    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
        
        strategy_config = data['strategy_config']
        risk_config = data['risk_management']
        deployment_config = data['deployment_settings']
        
        return ProductionConfig(
            symbol=strategy_config['symbol'],
            base_position_size=strategy_config['base_position_size'],
            entry_threshold_bps=strategy_config['entry_threshold_bps'],
            exit_threshold_bps=strategy_config['exit_threshold_bps'],
            futures_leverage=strategy_config['futures_leverage'],
            
            max_drawdown_pct=risk_config['max_drawdown_pct'],
            delta_tolerance=risk_config['delta_tolerance'],
            position_timeout_minutes=risk_config['position_timeout_minutes'],
            emergency_exit_threshold_pct=risk_config['emergency_exit_threshold_pct'],
            
            monitoring_interval=deployment_config['monitoring_interval'],
            enable_alerts=deployment_config['enable_alerts'],
            log_level=deployment_config['log_level']
        )
        
    except Exception as e:
        raise ValueError(f"Failed to load config from {config_path}: {e}")


def main():
    """Main production example entry point."""
    parser = argparse.ArgumentParser(description="MEXC-Gate.io Production Example")
    
    # Configuration options
    parser.add_argument('--config', type=str, help='Configuration file path')
    parser.add_argument('--symbol', type=str, default='BTC/USDT', help='Trading symbol')
    parser.add_argument('--position-size', type=float, default=100.0, help='Base position size')
    parser.add_argument('--entry-threshold', type=int, default=10, help='Entry threshold (bps)')
    parser.add_argument('--exit-threshold', type=int, default=3, help='Exit threshold (bps)')
    
    args = parser.parse_args()
    
    # Load configuration
    if args.config:
        config = load_config(args.config)
        print(f"✅ Loaded configuration from {args.config}")
    else:
        # Create default production config
        config = ProductionConfig(
            symbol=args.symbol,
            base_position_size=args.position_size,
            entry_threshold_bps=args.entry_threshold,
            exit_threshold_bps=args.exit_threshold,
            futures_leverage=1.0,
            max_drawdown_pct=2.0,
            delta_tolerance=0.05,
            position_timeout_minutes=5,
            emergency_exit_threshold_pct=5.0,
            monitoring_interval=30,
            enable_alerts=True,
            log_level="INFO"
        )
        print("✅ Using default production configuration")
    
    # Run production example
    print("🏭 Starting production example...")
    asyncio.run(production_example(config))


if __name__ == "__main__":
    main()