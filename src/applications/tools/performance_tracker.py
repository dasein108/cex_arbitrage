"""
Performance Tracker for NEIROETH Arbitrage

Comprehensive performance monitoring and analysis for arbitrage operations.
Tracks execution metrics, success rates, risk-adjusted returns, and provides
detailed analytics for strategy optimization.

Features:
- Real-time execution tracking
- Success rate monitoring
- Risk metrics calculation (Sharpe ratio, maximum drawdown)
- Trade lifecycle analysis
- Performance benchmarking
- Alert generation for performance degradation
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set
from statistics import mean, stdev
from collections import defaultdict, deque
from dataclasses import dataclass, field
import logging

import msgspec
import numpy as np

try:
    from .pnl_calculator import ArbitragePnL, TradeExecution
except ImportError:
    from pnl_calculator import ArbitragePnL, TradeExecution

logger = logging.getLogger(__name__)


class ExecutionMetrics(msgspec.Struct):
    """
    Execution timing and quality metrics.
    """
    trade_id: str
    execution_start: datetime
    execution_end: datetime
    execution_duration_ms: float
    
    # Execution quality
    planned_price: float
    executed_price: float
    price_slippage_pct: float
    execution_success: bool
    
    # Market conditions during execution
    market_volatility: Optional[float] = None
    spread_at_execution: Optional[float] = None
    liquidity_score: Optional[float] = None


class PerformancePeriod(msgspec.Struct):
    """
    Performance analysis for a specific time period.
    """
    period_start: datetime
    period_end: datetime
    period_type: str  # 'daily', 'weekly', 'monthly'
    
    # Trade statistics
    total_trades: int
    successful_trades: int
    failed_trades: int
    success_rate_pct: float
    
    # P&L metrics
    total_pnl: float
    average_pnl_per_trade: float
    best_trade_pnl: float
    worst_trade_pnl: float
    win_rate_pct: float  # Percentage of profitable trades
    
    # Risk metrics
    total_risk_exposure: float
    max_drawdown: float
    max_drawdown_pct: float
    
    # Execution metrics
    average_execution_time_ms: float
    execution_success_rate_pct: float
    average_slippage_pct: float
    
    # Efficiency metrics
    capital_utilization_pct: float
    return_on_capital_pct: float
    trades_per_hour: float
    
    # Optional risk metrics (moved to end)
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None


class PerformanceAlert(msgspec.Struct):
    """
    Performance alert for monitoring systems.
    """
    alert_id: str
    timestamp: datetime
    severity: str  # 'info', 'warning', 'critical'
    category: str  # 'execution', 'pnl', 'risk', 'system'
    
    message: str
    current_value: float
    threshold_value: float
    metric_name: str
    
    # Context for investigation
    related_trades: List[str] = field(default_factory=list)
    suggested_actions: List[str] = field(default_factory=list)


class PerformanceTracker:
    """
    Comprehensive performance tracking and analysis system.
    
    Monitors all aspects of arbitrage strategy performance including
    execution quality, profitability, risk metrics, and operational efficiency.
    """
    
    # Performance thresholds for alerting
    ALERT_THRESHOLDS = {
        'min_success_rate': 95.0,      # 95% minimum success rate
        'max_execution_time_ms': 100.0, # 100ms maximum execution time
        'max_slippage_pct': 0.1,       # 0.1% maximum slippage
        'min_sharpe_ratio': 2.0,       # 2.0 minimum Sharpe ratio
        'max_drawdown_pct': 5.0,       # 5% maximum drawdown
    }
    
    # Rolling window sizes for metrics
    EXECUTION_WINDOW = 1000  # Last 1000 executions
    PNL_WINDOW = 500        # Last 500 trades for P&L analysis
    RISK_WINDOW = 200       # Last 200 trades for risk metrics
    
    def __init__(self):
        self.logger = logger.getChild("PerformanceTracker")
        
        # Trade and execution tracking
        self._executions: Dict[str, ExecutionMetrics] = {}
        self._trades: Dict[str, ArbitragePnL] = {}
        self._trade_sequence: List[str] = []  # Ordered list of trade IDs
        
        # Rolling windows for real-time metrics
        self._execution_times = deque(maxlen=self.EXECUTION_WINDOW)
        self._slippages = deque(maxlen=self.EXECUTION_WINDOW)
        self._pnl_values = deque(maxlen=self.PNL_WINDOW)
        self._success_flags = deque(maxlen=self.EXECUTION_WINDOW)
        
        # Cumulative tracking
        self._cumulative_pnl = 0.0
        self._peak_pnl = 0.0
        self._max_drawdown = 0.0
        
        # Alert tracking
        self._alerts: List[PerformanceAlert] = []
        self._alert_history: Dict[str, datetime] = {}  # Last alert time by metric
        
        # Performance cache
        self._cached_daily_performance: Optional[PerformancePeriod] = None
        self._cache_timestamp: Optional[datetime] = None
    
    def record_execution(self, execution: ExecutionMetrics):
        """
        Record execution metrics for performance analysis.
        
        Args:
            execution: ExecutionMetrics object with timing and quality data
        """
        self._executions[execution.trade_id] = execution
        
        # Update rolling windows
        self._execution_times.append(execution.execution_duration_ms)
        self._slippages.append(abs(execution.price_slippage_pct))
        self._success_flags.append(execution.execution_success)
        
        # Check for execution alerts
        self._check_execution_alerts(execution)
        
        self.logger.debug(f"Recorded execution {execution.trade_id}: "
                         f"{execution.execution_duration_ms:.1f}ms, "
                         f"slippage={execution.price_slippage_pct:.3f}%")
    
    def record_trade_pnl(self, pnl: ArbitragePnL):
        """
        Record trade P&L for performance analysis.
        
        Args:
            pnl: ArbitragePnL object with complete trade results
        """
        trade_id = pnl.opportunity_id
        self._trades[trade_id] = pnl
        self._trade_sequence.append(trade_id)
        
        # Update rolling windows
        self._pnl_values.append(pnl.net_profit)
        
        # Update cumulative tracking
        self._cumulative_pnl += pnl.net_profit
        if self._cumulative_pnl > self._peak_pnl:
            self._peak_pnl = self._cumulative_pnl
        
        # Calculate current drawdown
        current_drawdown = self._peak_pnl - self._cumulative_pnl
        if current_drawdown > self._max_drawdown:
            self._max_drawdown = current_drawdown
        
        # Check for P&L alerts
        self._check_pnl_alerts(pnl)
        
        self.logger.debug(f"Recorded trade P&L {trade_id}: ${pnl.net_profit:.4f}, "
                         f"cumulative=${self._cumulative_pnl:.4f}")
    
    def get_current_performance(self) -> Dict[str, float]:
        """
        Get current real-time performance metrics.
        
        Returns:
            Dictionary with key performance indicators
        """
        metrics = {}
        
        # Execution metrics
        if self._execution_times:
            metrics['avg_execution_time_ms'] = mean(self._execution_times)
            metrics['p95_execution_time_ms'] = np.percentile(list(self._execution_times), 95)
        
        if self._slippages:
            metrics['avg_slippage_pct'] = mean(self._slippages)
            metrics['max_slippage_pct'] = max(self._slippages)
        
        if self._success_flags:
            metrics['execution_success_rate_pct'] = (sum(self._success_flags) / len(self._success_flags)) * 100
        
        # P&L metrics
        if self._pnl_values:
            metrics['avg_trade_pnl'] = mean(self._pnl_values)
            metrics['win_rate_pct'] = (len([p for p in self._pnl_values if p > 0]) / len(self._pnl_values)) * 100
            
            if len(self._pnl_values) > 1:
                pnl_std = stdev(self._pnl_values)
                if pnl_std > 0:
                    metrics['sharpe_ratio'] = mean(self._pnl_values) / pnl_std
        
        # Cumulative metrics
        metrics['cumulative_pnl'] = self._cumulative_pnl
        metrics['max_drawdown'] = self._max_drawdown
        metrics['max_drawdown_pct'] = (self._max_drawdown / self._peak_pnl) * 100 if self._peak_pnl > 0 else 0
        
        # Trade volume
        metrics['total_trades'] = len(self._trades)
        metrics['total_executions'] = len(self._executions)
        
        return metrics
    
    def get_period_performance(
        self, 
        period_type: str = 'daily',
        periods_back: int = 1
    ) -> Optional[PerformancePeriod]:
        """
        Get performance analysis for a specific period.
        
        Args:
            period_type: 'daily', 'weekly', or 'monthly'
            periods_back: Number of periods back from current (1 = current period)
            
        Returns:
            PerformancePeriod with comprehensive analysis
        """
        # Calculate period boundaries
        now = datetime.utcnow()
        if period_type == 'daily':
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=periods_back-1)
            period_end = period_start + timedelta(days=1)
        elif period_type == 'weekly':
            days_since_monday = now.weekday()
            week_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
            period_start = week_start - timedelta(weeks=periods_back-1)
            period_end = period_start + timedelta(weeks=1)
        elif period_type == 'monthly':
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # Calculate start of target month
            target_month = month_start
            for _ in range(periods_back - 1):
                if target_month.month == 1:
                    target_month = target_month.replace(year=target_month.year - 1, month=12)
                else:
                    target_month = target_month.replace(month=target_month.month - 1)
            period_start = target_month
            
            # Calculate end of period
            if target_month.month == 12:
                period_end = target_month.replace(year=target_month.year + 1, month=1)
            else:
                period_end = target_month.replace(month=target_month.month + 1)
        else:
            self.logger.error(f"Unknown period type: {period_type}")
            return None
        
        # Filter trades and executions for the period
        period_trades = []
        period_executions = []
        
        for trade_id, trade in self._trades.items():
            if period_start <= trade.calculation_time < period_end:
                period_trades.append(trade)
                
        for exec_id, execution in self._executions.items():
            if period_start <= execution.execution_start < period_end:
                period_executions.append(execution)
        
        if not period_trades and not period_executions:
            self.logger.warning(f"No data found for {period_type} period {periods_back} periods back")
            return None
        
        # Calculate period metrics
        return self._calculate_period_metrics(
            period_start, period_end, period_type, period_trades, period_executions
        )
    
    def get_risk_metrics(self) -> Dict[str, float]:
        """
        Calculate comprehensive risk metrics.
        
        Returns:
            Dictionary with risk analysis
        """
        if not self._pnl_values or len(self._pnl_values) < 10:
            return {'insufficient_data': True}
        
        pnl_array = np.array(list(self._pnl_values))
        
        # Basic risk metrics
        volatility = float(np.std(pnl_array))
        downside_deviation = float(np.std(pnl_array[pnl_array < 0])) if len(pnl_array[pnl_array < 0]) > 0 else 0
        
        # Value at Risk (95% confidence)
        var_95 = float(np.percentile(pnl_array, 5))
        
        # Maximum consecutive losses
        max_consecutive_losses = self._calculate_max_consecutive_losses()
        
        # Risk ratios
        avg_return = float(np.mean(pnl_array))
        sharpe_ratio = avg_return / volatility if volatility > 0 else 0
        sortino_ratio = avg_return / downside_deviation if downside_deviation > 0 else 0
        
        # Drawdown analysis
        drawdown_pct = (self._max_drawdown / self._peak_pnl) * 100 if self._peak_pnl > 0 else 0
        
        return {
            'volatility': volatility,
            'value_at_risk_95': var_95,
            'max_consecutive_losses': max_consecutive_losses,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'max_drawdown_pct': drawdown_pct,
            'downside_deviation': downside_deviation,
            'total_trades_analyzed': len(pnl_array)
        }
    
    def get_active_alerts(self) -> List[PerformanceAlert]:
        """
        Get current active performance alerts.
        
        Returns:
            List of active alerts requiring attention
        """
        # Remove old alerts (older than 1 hour)
        cutoff_time = datetime.utcnow() - timedelta(hours=1)
        self._alerts = [alert for alert in self._alerts if alert.timestamp >= cutoff_time]
        
        return self._alerts.copy()
    
    def generate_performance_report(self) -> Dict[str, any]:
        """
        Generate comprehensive performance report.
        
        Returns:
            Complete performance analysis dictionary
        """
        report = {
            'report_timestamp': datetime.utcnow(),
            'current_metrics': self.get_current_performance(),
            'risk_analysis': self.get_risk_metrics(),
            'active_alerts': len(self.get_active_alerts()),
        }
        
        # Add period analysis
        for period in ['daily', 'weekly', 'monthly']:
            period_perf = self.get_period_performance(period)
            if period_perf:
                report[f'{period}_performance'] = period_perf
        
        # Add trend analysis
        report['trend_analysis'] = self._analyze_performance_trends()
        
        return report
    
    def _check_execution_alerts(self, execution: ExecutionMetrics):
        """Check execution metrics against thresholds and generate alerts."""
        alerts = []
        
        # Execution time alert
        if execution.execution_duration_ms > self.ALERT_THRESHOLDS['max_execution_time_ms']:
            alerts.append(self._create_alert(
                'warning', 'execution', 'execution_time_exceeded',
                f"Execution time {execution.execution_duration_ms:.1f}ms exceeds threshold",
                execution.execution_duration_ms,
                self.ALERT_THRESHOLDS['max_execution_time_ms'],
                [execution.trade_id]
            ))
        
        # Slippage alert
        if abs(execution.price_slippage_pct) > self.ALERT_THRESHOLDS['max_slippage_pct']:
            alerts.append(self._create_alert(
                'warning', 'execution', 'slippage_exceeded',
                f"Price slippage {execution.price_slippage_pct:.3f}% exceeds threshold",
                abs(execution.price_slippage_pct),
                self.ALERT_THRESHOLDS['max_slippage_pct'],
                [execution.trade_id]
            ))
        
        # Execution failure alert
        if not execution.execution_success:
            alerts.append(self._create_alert(
                'critical', 'execution', 'execution_failed',
                f"Trade execution failed for {execution.trade_id}",
                0.0, 1.0, [execution.trade_id]
            ))
        
        self._alerts.extend(alerts)
    
    def _check_pnl_alerts(self, pnl: ArbitragePnL):
        """Check P&L metrics against thresholds and generate alerts."""
        alerts = []
        
        # Large loss alert
        if pnl.net_profit < -100:  # Loss > $100
            alerts.append(self._create_alert(
                'warning', 'pnl', 'large_loss',
                f"Large loss of ${abs(pnl.net_profit):.2f} in trade {pnl.opportunity_id}",
                pnl.net_profit, -100, [pnl.opportunity_id]
            ))
        
        # High risk exposure alert
        if pnl.execution_risk_score > 0.8:
            alerts.append(self._create_alert(
                'warning', 'risk', 'high_risk_execution',
                f"High risk execution (score: {pnl.execution_risk_score:.2f})",
                pnl.execution_risk_score, 0.8, [pnl.opportunity_id]
            ))
        
        self._alerts.extend(alerts)
    
    def _create_alert(
        self, 
        severity: str, 
        category: str, 
        metric_name: str,
        message: str, 
        current_value: float, 
        threshold_value: float,
        related_trades: List[str]
    ) -> PerformanceAlert:
        """Create a performance alert."""
        alert_id = f"{category}_{metric_name}_{datetime.utcnow().isoformat()}"
        
        return PerformanceAlert(
            alert_id=alert_id,
            timestamp=datetime.utcnow(),
            severity=severity,
            category=category,
            message=message,
            current_value=current_value,
            threshold_value=threshold_value,
            metric_name=metric_name,
            related_trades=related_trades,
            suggested_actions=self._get_suggested_actions(category, metric_name)
        )
    
    def _get_suggested_actions(self, category: str, metric_name: str) -> List[str]:
        """Get suggested actions for alert resolution."""
        actions = {
            'execution_time_exceeded': [
                "Check network connectivity",
                "Review exchange API response times",
                "Consider reducing trade size",
                "Check system resource utilization"
            ],
            'slippage_exceeded': [
                "Reduce trade size",
                "Check market volatility",
                "Review order book depth",
                "Consider using limit orders"
            ],
            'execution_failed': [
                "Check exchange connectivity",
                "Verify account balances",
                "Review order parameters",
                "Check for exchange maintenance"
            ],
            'large_loss': [
                "Review market conditions",
                "Check spread calculations",
                "Verify execution timing",
                "Consider position sizing adjustments"
            ]
        }
        
        return actions.get(metric_name, ["Review system logs", "Contact support if issue persists"])
    
    def _calculate_period_metrics(
        self,
        period_start: datetime,
        period_end: datetime,
        period_type: str,
        trades: List[ArbitragePnL],
        executions: List[ExecutionMetrics]
    ) -> PerformancePeriod:
        """Calculate comprehensive metrics for a period."""
        # Trade statistics
        total_trades = len(trades)
        successful_trades = len([t for t in trades if t.net_profit > 0])
        failed_trades = total_trades - successful_trades
        success_rate = (successful_trades / total_trades) * 100 if total_trades > 0 else 0
        
        # P&L metrics
        total_pnl = sum(t.net_profit for t in trades)
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
        best_trade = max((t.net_profit for t in trades), default=0)
        worst_trade = min((t.net_profit for t in trades), default=0)
        win_rate = (len([t for t in trades if t.net_profit > 0]) / total_trades) * 100 if total_trades > 0 else 0
        
        # Execution metrics
        execution_times = [e.execution_duration_ms for e in executions]
        avg_exec_time = mean(execution_times) if execution_times else 0
        exec_success_rate = (len([e for e in executions if e.execution_success]) / len(executions)) * 100 if executions else 0
        slippages = [abs(e.price_slippage_pct) for e in executions]
        avg_slippage = mean(slippages) if slippages else 0
        
        # Risk metrics
        total_risk = sum(t.max_drawdown_risk for t in trades)
        capital_required = sum(t.capital_required for t in trades)
        
        # Calculate Sharpe ratio for period
        if trades and len(trades) > 1:
            pnl_values = [t.net_profit for t in trades]
            pnl_std = stdev(pnl_values)
            sharpe = avg_pnl / pnl_std if pnl_std > 0 else None
        else:
            sharpe = None
        
        # Calculate period-specific metrics
        period_hours = (period_end - period_start).total_seconds() / 3600
        trades_per_hour = total_trades / period_hours if period_hours > 0 else 0
        
        return PerformancePeriod(
            period_start=period_start,
            period_end=period_end,
            period_type=period_type,
            total_trades=total_trades,
            successful_trades=successful_trades,
            failed_trades=failed_trades,
            success_rate_pct=success_rate,
            total_pnl=total_pnl,
            average_pnl_per_trade=avg_pnl,
            best_trade_pnl=best_trade,
            worst_trade_pnl=worst_trade,
            win_rate_pct=win_rate,
            total_risk_exposure=total_risk,
            max_drawdown=self._max_drawdown,
            max_drawdown_pct=(self._max_drawdown / self._peak_pnl) * 100 if self._peak_pnl > 0 else 0,
            sharpe_ratio=sharpe,
            average_execution_time_ms=avg_exec_time,
            execution_success_rate_pct=exec_success_rate,
            average_slippage_pct=avg_slippage,
            capital_utilization_pct=0.0,  # Would need portfolio size to calculate
            return_on_capital_pct=(total_pnl / capital_required) * 100 if capital_required > 0 else 0,
            trades_per_hour=trades_per_hour
        )
    
    def _calculate_max_consecutive_losses(self) -> int:
        """Calculate maximum consecutive losing trades."""
        if not self._pnl_values:
            return 0
            
        max_consecutive = 0
        current_consecutive = 0
        
        for pnl in self._pnl_values:
            if pnl < 0:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
                
        return max_consecutive
    
    def _analyze_performance_trends(self) -> Dict[str, str]:
        """Analyze performance trends over recent periods."""
        trends = {}
        
        # Analyze P&L trend
        if len(self._pnl_values) >= 20:
            recent_pnl = list(self._pnl_values)[-20:]
            early_avg = mean(recent_pnl[:10])
            late_avg = mean(recent_pnl[10:])
            
            if late_avg > early_avg * 1.1:
                trends['pnl_trend'] = 'improving'
            elif late_avg < early_avg * 0.9:
                trends['pnl_trend'] = 'deteriorating'
            else:
                trends['pnl_trend'] = 'stable'
        
        # Analyze execution time trend
        if len(self._execution_times) >= 50:
            recent_times = list(self._execution_times)[-50:]
            early_avg = mean(recent_times[:25])
            late_avg = mean(recent_times[25:])
            
            if late_avg > early_avg * 1.2:
                trends['execution_trend'] = 'slowing'
            elif late_avg < early_avg * 0.8:
                trends['execution_trend'] = 'improving'
            else:
                trends['execution_trend'] = 'stable'
        
        return trends