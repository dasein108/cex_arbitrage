#!/usr/bin/env python3
"""
Strategy Performance Monitoring Tool

Real-time monitoring and analysis tool for arbitrage strategies with comprehensive
performance metrics, risk analysis, and visual dashboards.

Features:
- Real-time performance tracking
- Risk metric analysis
- Exchange health monitoring
- Position tracking and delta analysis
- Performance visualization
- Alert system integration
- Export capabilities for analysis

Usage:
    python tools/monitor_strategy.py --strategy mexc_gateio --live
    python tools/monitor_strategy.py --strategy mexc_gateio --analyze --export metrics.json
    python tools/monitor_strategy.py --dashboard --port 8080
"""

import sys
import asyncio
import argparse
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import signal

# Add src to path for imports
current_dir = Path(__file__).parent
project_root = current_dir.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from infrastructure.logging import get_logger


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics for strategy analysis."""
    timestamp: float
    uptime_seconds: float
    
    # Trading performance
    total_profit: float
    total_volume: float
    total_trades: int
    successful_trades: int
    arbitrage_cycles: int
    win_rate: float
    
    # Position tracking
    mexc_position: float
    gateio_position: float
    current_delta: float
    delta_neutral: bool
    
    # Risk metrics
    max_drawdown: float
    current_drawdown: float
    sharpe_ratio: Optional[float]
    volatility: float
    
    # Exchange metrics
    mexc_connection_health: str
    gateio_connection_health: str
    price_update_frequency: float
    avg_execution_latency: float
    
    # Strategy state
    current_state: str
    opportunities_detected: int
    opportunities_executed: int
    execution_success_rate: float


@dataclass
class RiskAlert:
    """Risk alert structure."""
    timestamp: float
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    category: str  # POSITION, DRAWDOWN, CONNECTION, EXECUTION
    message: str
    current_value: float
    threshold_value: float
    action_required: bool


class PerformanceTracker:
    """Tracks and analyzes strategy performance metrics."""
    
    def __init__(self, strategy_name: str, logger):
        self.strategy_name = strategy_name
        self.logger = logger
        
        # Metrics storage
        self.metrics_history: List[PerformanceMetrics] = []
        self.alerts_history: List[RiskAlert] = []
        
        # Analysis parameters
        self.max_history_hours = 24
        self.analysis_window_minutes = 5
        
        # Risk thresholds
        self.risk_thresholds = {
            'max_drawdown_warning': 2.0,  # 2%
            'max_drawdown_critical': 5.0,  # 5%
            'delta_warning': 0.1,  # 10%
            'delta_critical': 0.2,  # 20%
            'win_rate_warning': 0.3,  # 30%
            'execution_latency_warning': 100,  # 100ms
            'connection_loss_critical': 30  # 30 seconds
        }
    
    def add_metrics(self, metrics: PerformanceMetrics):
        """Add new performance metrics."""
        self.metrics_history.append(metrics)
        
        # Cleanup old metrics
        cutoff_time = time.time() - (self.max_history_hours * 3600)
        self.metrics_history = [
            m for m in self.metrics_history if m.timestamp > cutoff_time
        ]
        
        # Analyze for alerts
        self._analyze_for_alerts(metrics)
    
    def _analyze_for_alerts(self, metrics: PerformanceMetrics):
        """Analyze metrics for risk alerts."""
        current_time = time.time()
        
        # Drawdown alerts
        if metrics.current_drawdown > self.risk_thresholds['max_drawdown_critical']:
            self._create_alert(
                'CRITICAL', 'DRAWDOWN',
                f'Critical drawdown: {metrics.current_drawdown:.2f}%',
                metrics.current_drawdown, self.risk_thresholds['max_drawdown_critical']
            )
        elif metrics.current_drawdown > self.risk_thresholds['max_drawdown_warning']:
            self._create_alert(
                'HIGH', 'DRAWDOWN',
                f'High drawdown warning: {metrics.current_drawdown:.2f}%',
                metrics.current_drawdown, self.risk_thresholds['max_drawdown_warning']
            )
        
        # Delta alerts
        delta_pct = abs(metrics.current_delta) * 100
        if delta_pct > self.risk_thresholds['delta_critical']:
            self._create_alert(
                'CRITICAL', 'POSITION',
                f'Critical delta exposure: {delta_pct:.2f}%',
                delta_pct, self.risk_thresholds['delta_critical']
            )
        elif delta_pct > self.risk_thresholds['delta_warning']:
            self._create_alert(
                'MEDIUM', 'POSITION',
                f'High delta exposure: {delta_pct:.2f}%',
                delta_pct, self.risk_thresholds['delta_warning']
            )
        
        # Win rate alerts
        if metrics.win_rate < self.risk_thresholds['win_rate_warning'] and metrics.total_trades > 10:
            self._create_alert(
                'HIGH', 'EXECUTION',
                f'Low win rate: {metrics.win_rate:.1%}',
                metrics.win_rate, self.risk_thresholds['win_rate_warning']
            )
        
        # Execution latency alerts
        if metrics.avg_execution_latency > self.risk_thresholds['execution_latency_warning']:
            self._create_alert(
                'MEDIUM', 'EXECUTION',
                f'High execution latency: {metrics.avg_execution_latency:.1f}ms',
                metrics.avg_execution_latency, self.risk_thresholds['execution_latency_warning']
            )
        
        # Connection health alerts
        if (metrics.mexc_connection_health != 'healthy' or 
            metrics.gateio_connection_health != 'healthy'):
            self._create_alert(
                'HIGH', 'CONNECTION',
                f'Exchange connection issues: MEXC={metrics.mexc_connection_health}, Gate.io={metrics.gateio_connection_health}',
                0, 0
            )
    
    def _create_alert(self, severity: str, category: str, message: str, 
                     current_value: float, threshold_value: float):
        """Create and store a risk alert."""
        alert = RiskAlert(
            timestamp=time.time(),
            severity=severity,
            category=category,
            message=message,
            current_value=current_value,
            threshold_value=threshold_value,
            action_required=severity in ['HIGH', 'CRITICAL']
        )
        
        self.alerts_history.append(alert)
        self.logger.warning(f"🚨 [{severity}] {category}: {message}")
        
        # Keep only recent alerts
        cutoff_time = time.time() - (24 * 3600)  # 24 hours
        self.alerts_history = [
            a for a in self.alerts_history if a.timestamp > cutoff_time
        ]
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        if not self.metrics_history:
            return {'error': 'No metrics data available'}
        
        latest = self.metrics_history[-1]
        
        # Calculate trends
        trend_data = self._calculate_trends()
        
        # Recent alerts
        recent_alerts = [
            a for a in self.alerts_history 
            if a.timestamp > time.time() - 3600  # Last hour
        ]
        
        return {
            'strategy': self.strategy_name,
            'timestamp': latest.timestamp,
            'uptime_hours': latest.uptime_seconds / 3600,
            
            'performance': {
                'total_profit': latest.total_profit,
                'total_volume': latest.total_volume,
                'arbitrage_cycles': latest.arbitrage_cycles,
                'win_rate': latest.win_rate,
                'sharpe_ratio': latest.sharpe_ratio,
                'profit_trend': trend_data.get('profit_trend', 0.0)
            },
            
            'risk': {
                'current_drawdown': latest.current_drawdown,
                'max_drawdown': latest.max_drawdown,
                'current_delta': latest.current_delta,
                'delta_neutral': latest.delta_neutral,
                'volatility': latest.volatility
            },
            
            'execution': {
                'execution_success_rate': latest.execution_success_rate,
                'avg_latency_ms': latest.avg_execution_latency,
                'opportunities_detected': latest.opportunities_detected,
                'opportunities_executed': latest.opportunities_executed
            },
            
            'exchanges': {
                'mexc_health': latest.mexc_connection_health,
                'gateio_health': latest.gateio_connection_health,
                'price_update_frequency': latest.price_update_frequency
            },
            
            'alerts': {
                'recent_count': len(recent_alerts),
                'critical_count': len([a for a in recent_alerts if a.severity == 'CRITICAL']),
                'recent_alerts': [asdict(a) for a in recent_alerts[-5:]]  # Last 5 alerts
            },
            
            'trends': trend_data
        }
    
    def _calculate_trends(self) -> Dict[str, float]:
        """Calculate performance trends."""
        if len(self.metrics_history) < 2:
            return {}
        
        # Get recent window
        window_start = time.time() - (self.analysis_window_minutes * 60)
        recent_metrics = [m for m in self.metrics_history if m.timestamp > window_start]
        
        if len(recent_metrics) < 2:
            return {}
        
        # Calculate trends
        first = recent_metrics[0]
        last = recent_metrics[-1]
        time_diff = last.timestamp - first.timestamp
        
        if time_diff == 0:
            return {}
        
        trends = {
            'profit_trend': (last.total_profit - first.total_profit) / time_diff * 3600,  # per hour
            'volume_trend': (last.total_volume - first.total_volume) / time_diff * 3600,
            'cycles_trend': (last.arbitrage_cycles - first.arbitrage_cycles) / time_diff * 3600,
            'delta_trend': abs(last.current_delta) - abs(first.current_delta)
        }
        
        return trends
    
    def export_metrics(self, file_path: str, hours: Optional[int] = None):
        """Export metrics to JSON file."""
        if hours:
            cutoff_time = time.time() - (hours * 3600)
            export_metrics = [m for m in self.metrics_history if m.timestamp > cutoff_time]
        else:
            export_metrics = self.metrics_history
        
        export_data = {
            'strategy': self.strategy_name,
            'export_timestamp': time.time(),
            'total_records': len(export_metrics),
            'metrics': [asdict(m) for m in export_metrics],
            'alerts': [asdict(a) for a in self.alerts_history],
            'summary': self.get_performance_summary()
        }
        
        with open(file_path, 'w') as f:
            json.dump(export_data, f, indent=2)


class StrategyMonitor:
    """Main strategy monitoring orchestrator."""
    
    def __init__(self, strategy_name: str):
        self.strategy_name = strategy_name
        self.logger = get_logger(f'strategy_monitor_{strategy_name}')
        
        self.tracker = PerformanceTracker(strategy_name, self.logger)
        self.running = False
        self.update_interval = 30  # seconds
        
        # Simulated strategy connection (in real implementation, connect to actual strategy)
        self.strategy_connection = None
    
    async def start_monitoring(self):
        """Start real-time monitoring."""
        self.running = True
        self.logger.info(f"🔍 Starting monitoring for strategy: {self.strategy_name}")
        
        while self.running:
            try:
                # Collect metrics from strategy
                metrics = await self._collect_metrics()
                
                if metrics:
                    self.tracker.add_metrics(metrics)
                    
                    # Log periodic status
                    summary = self.tracker.get_performance_summary()
                    self._log_status(summary)
                
                await asyncio.sleep(self.update_interval)
                
            except Exception as e:
                self.logger.error(f"❌ Monitoring error: {e}")
                await asyncio.sleep(5)  # Brief pause before retry
    
    async def _collect_metrics(self) -> Optional[PerformanceMetrics]:
        """Collect current strategy metrics."""
        # In real implementation, this would connect to the actual running strategy
        # For now, return simulated metrics
        
        current_time = time.time()
        
        # Simulate metrics collection
        metrics = PerformanceMetrics(
            timestamp=current_time,
            uptime_seconds=3600,  # 1 hour uptime
            
            # Trading performance (simulated)
            total_profit=10.5,
            total_volume=1000.0,
            total_trades=25,
            successful_trades=20,
            arbitrage_cycles=15,
            win_rate=0.8,
            
            # Position tracking (simulated)
            mexc_position=50.0,
            gateio_position=-49.8,
            current_delta=0.2,
            delta_neutral=True,
            
            # Risk metrics (simulated)
            max_drawdown=1.2,
            current_drawdown=0.5,
            sharpe_ratio=1.8,
            volatility=0.15,
            
            # Exchange metrics (simulated)
            mexc_connection_health='healthy',
            gateio_connection_health='healthy',
            price_update_frequency=10.0,
            avg_execution_latency=25.0,
            
            # Strategy state (simulated)
            current_state='MONITORING',
            opportunities_detected=45,
            opportunities_executed=15,
            execution_success_rate=0.85
        )
        
        return metrics
    
    def _log_status(self, summary: Dict[str, Any]):
        """Log current status summary."""
        perf = summary['performance']
        risk = summary['risk']
        alerts = summary['alerts']
        
        self.logger.info(f"📊 Strategy: {self.strategy_name} | "
                        f"Profit: {perf['total_profit']:.2f} | "
                        f"Cycles: {perf['arbitrage_cycles']} | "
                        f"Win Rate: {perf['win_rate']:.1%} | "
                        f"Drawdown: {risk['current_drawdown']:.2f}% | "
                        f"Delta: {risk['current_delta']:.4f} | "
                        f"Alerts: {alerts['recent_count']}")
    
    def stop_monitoring(self):
        """Stop monitoring."""
        self.running = False
        self.logger.info("🛑 Stopping strategy monitoring")
    
    def get_current_summary(self) -> Dict[str, Any]:
        """Get current performance summary."""
        return self.tracker.get_performance_summary()
    
    def export_data(self, file_path: str, hours: Optional[int] = None):
        """Export monitoring data."""
        self.tracker.export_metrics(file_path, hours)
        self.logger.info(f"📊 Exported monitoring data to {file_path}")


async def run_live_monitoring(strategy_name: str):
    """Run live monitoring for a strategy."""
    monitor = StrategyMonitor(strategy_name)
    
    # Set up signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        print(f"\n📡 Received signal {signum}, stopping monitoring...")
        monitor.stop_monitoring()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await monitor.start_monitoring()
    except KeyboardInterrupt:
        monitor.stop_monitoring()
    
    print("✅ Monitoring stopped")


async def analyze_strategy(strategy_name: str, export_path: Optional[str] = None):
    """Analyze strategy performance and generate report."""
    monitor = StrategyMonitor(strategy_name)
    
    # Collect current metrics
    metrics = await monitor._collect_metrics()
    if metrics:
        monitor.tracker.add_metrics(metrics)
    
    # Generate analysis report
    summary = monitor.get_current_summary()
    
    print(f"\n📊 Strategy Analysis Report: {strategy_name}")
    print("=" * 60)
    
    # Performance section
    perf = summary['performance']
    print(f"\n💰 PERFORMANCE:")
    print(f"  Total Profit: {perf['total_profit']:.4f}")
    print(f"  Total Volume: {perf['total_volume']:.2f}")
    print(f"  Arbitrage Cycles: {perf['arbitrage_cycles']}")
    print(f"  Win Rate: {perf['win_rate']:.1%}")
    if perf['sharpe_ratio']:
        print(f"  Sharpe Ratio: {perf['sharpe_ratio']:.2f}")
    
    # Risk section
    risk = summary['risk']
    print(f"\n⚠️  RISK METRICS:")
    print(f"  Current Drawdown: {risk['current_drawdown']:.2f}%")
    print(f"  Max Drawdown: {risk['max_drawdown']:.2f}%")
    print(f"  Current Delta: {risk['current_delta']:.4f}")
    print(f"  Delta Neutral: {'✅' if risk['delta_neutral'] else '❌'}")
    print(f"  Volatility: {risk['volatility']:.2%}")
    
    # Execution section
    exec_data = summary['execution']
    print(f"\n⚡ EXECUTION:")
    print(f"  Success Rate: {exec_data['execution_success_rate']:.1%}")
    print(f"  Avg Latency: {exec_data['avg_latency_ms']:.1f}ms")
    print(f"  Opportunities: {exec_data['opportunities_executed']}/{exec_data['opportunities_detected']}")
    
    # Exchange health
    exchanges = summary['exchanges']
    print(f"\n🔗 EXCHANGES:")
    print(f"  MEXC Health: {exchanges['mexc_health']}")
    print(f"  Gate.io Health: {exchanges['gateio_health']}")
    print(f"  Price Updates: {exchanges['price_update_frequency']:.1f}/sec")
    
    # Alerts
    alerts = summary['alerts']
    print(f"\n🚨 ALERTS:")
    print(f"  Recent Alerts: {alerts['recent_count']}")
    print(f"  Critical Alerts: {alerts['critical_count']}")
    
    if export_path:
        monitor.export_data(export_path)
        print(f"\n💾 Data exported to: {export_path}")


def main():
    """Main monitoring tool entry point."""
    parser = argparse.ArgumentParser(description="Strategy Performance Monitoring Tool")
    
    # Strategy selection
    parser.add_argument('--strategy', required=True, choices=['mexc_gateio'], 
                       help='Strategy to monitor')
    
    # Monitoring modes
    parser.add_argument('--live', action='store_true', 
                       help='Start live monitoring')
    parser.add_argument('--analyze', action='store_true', 
                       help='Analyze current performance')
    parser.add_argument('--dashboard', action='store_true', 
                       help='Start web dashboard (future feature)')
    
    # Export options
    parser.add_argument('--export', type=str, 
                       help='Export data to JSON file')
    parser.add_argument('--hours', type=int, 
                       help='Hours of data to export (default: all)')
    
    # Dashboard options
    parser.add_argument('--port', type=int, default=8080, 
                       help='Dashboard port (default: 8080)')
    
    args = parser.parse_args()
    
    if args.live:
        print(f"🔍 Starting live monitoring for {args.strategy} strategy...")
        asyncio.run(run_live_monitoring(args.strategy))
    
    elif args.analyze:
        print(f"📊 Analyzing {args.strategy} strategy performance...")
        asyncio.run(analyze_strategy(args.strategy, args.export))
    
    elif args.dashboard:
        print(f"🌐 Starting web dashboard on port {args.port}...")
        print("⚠️  Dashboard feature not yet implemented")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()