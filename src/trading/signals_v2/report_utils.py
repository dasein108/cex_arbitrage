"""
Performance Reporting Utilities

This module provides comprehensive reporting and analysis tools for cryptocurrency
arbitrage trading strategies, including trade tables and performance metrics visualization.
"""

from typing import List
from datetime import datetime
from .entities import ArbitrageTrade, PerformanceMetrics

def arbitrage_trade_to_table(trades: List[ArbitrageTrade], include_header: bool = True) -> str:
    """
    Convert ArbitrageTrade instances to a formatted table string.

    Args:
        trades: List of ArbitrageTrade instances
        include_header: Whether to include the header row (default: True for first/single item)

    Returns:
        Formatted table string
    """
    if not trades:
        return ""

    lines = []

    # Header
    if include_header:
        header = (
            f"{'Timestamp':<20} | {'Buy Exchange':<12} | {'Sell Exchange':<12} | "
            f"{'Buy Price':>12} | {'Sell Price':>12} | {'Qty':>10} | "
            f"{'PnL %':>8} | {'PnL USDT':>10}"
        )
        separator = "-" * len(header)
        lines.extend([header, separator])

    # Data rows
    for trade in trades:
        timestamp_str = trade.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        row = (
            f"{timestamp_str:<20} | {trade.buy_exchange.value:<12} | {trade.sell_exchange.value:<12} | "
            f"{trade.buy_price:>12.4f} | {trade.sell_price:>12.4f} | {trade.qty:>10.4f} | "
            f"{trade.pnl_pct:>7.2f}% | {trade.pnl_usdt:>10.4f}"
        )
        lines.append(row)

    return "\n".join(lines)


def performance_metrics_table(metrics_list: List[PerformanceMetrics], include_header = False) -> str:
    """
    Convert PerformanceMetrics instances to a formatted table with each metrics object as a row.

    Args:
        metrics_list: List of PerformanceMetrics instances
        include_header: Whether to include the header row (default: True for first/single item)

    Returns:
        Formatted table string with header and one row per metrics instance
    """
    if not metrics_list:
        return "No metrics to display"

    lines = []

    if include_header:
        # Header
        header = (
            f"{'Trades':>7} | {'Total PnL ($)':>14} | {'Total PnL (%)':>13} | "
            f"{'Win Rate':>9} | {'Avg Trade':>11} | {'Max DD':>8} | {'Sharpe':>7}"
        )
        separator = "=" * len(header)
        lines.extend([header, separator])

    # Each metrics object as a row
    for metrics in metrics_list:
        row = (
            f"{metrics.total_trades:>7} | {metrics.total_pnl_usd:>14,.2f} | "
            f"{metrics.total_pnl_pct:>12.2f}% | {metrics.win_rate:>8.2f}% | "
            f"{metrics.avg_trade_pnl:>11,.2f} | {metrics.max_drawdown:>7.2f}% | "
            f"{metrics.sharpe_ratio:>7.2f}"
        )
        lines.append(row)

    return "\n".join(lines)


def validate_performance_metrics(metrics: PerformanceMetrics) -> List[str]:
    """
    Validate performance metrics for realistic arbitrage trading results.
    
    This function checks for unrealistic performance characteristics that may
    indicate bugs in strategy implementation or overly optimistic assumptions.
    
    Args:
        metrics: Performance metrics to validate
        
    Returns:
        List of warning messages for unrealistic metrics
    """
    warnings = []
    
    # Check for unrealistic win rate
    if metrics.win_rate > 90:
        warnings.append(f"⚠️  Win rate {metrics.win_rate:.1f}% is unrealistically high for arbitrage (expected: 65-85%)")
    
    # Check for unrealistic average trade P&L
    if metrics.avg_trade_pnl > 5.0:  # $5 per trade is very high for arbitrage
        warnings.append(f"⚠️  Average trade P&L ${metrics.avg_trade_pnl:.2f} is very high (expected: $0.10-$2.00)")
    
    # Check for zero max drawdown
    if metrics.max_drawdown == 0 and metrics.total_trades > 5:
        warnings.append("⚠️  Zero max drawdown is unrealistic for multi-trade strategies")
    
    # Check for unrealistic Sharpe ratio
    if metrics.sharpe_ratio > 3.0:
        warnings.append(f"⚠️  Sharpe ratio {metrics.sharpe_ratio:.2f} is unusually high (expected: 0.5-2.0)")
    
    # Check individual trade P&L percentages
    if metrics.trades:
        high_pnl_trades = [t for t in metrics.trades if t.pnl_pct > 2.0]  # >2% per trade
        if len(high_pnl_trades) > len(metrics.trades) * 0.1:  # >10% of trades
            warnings.append(f"⚠️  {len(high_pnl_trades)} trades show >2% P&L (may indicate cost modeling issues)")
    
    return warnings


def generate_performance_summary(metrics: PerformanceMetrics, include_warnings: bool = True) -> str:
    """
    Generate comprehensive performance summary with validation warnings.
    
    Args:
        metrics: Performance metrics to summarize
        include_warnings: Whether to include validation warnings
        
    Returns:
        Formatted performance summary string
    """
    lines = []
    
    # Main performance table
    lines.append("PERFORMANCE SUMMARY")
    lines.append("=" * 50)
    lines.append(performance_metrics_table([metrics], include_header=True))
    
    if include_warnings:
        warnings = validate_performance_metrics(metrics)
        if warnings:
            lines.append("")
            lines.append("VALIDATION WARNINGS")
            lines.append("=" * 50)
            for warning in warnings:
                lines.append(warning)
        else:
            lines.append("")
            lines.append("✅ All metrics appear realistic for arbitrage trading")
    
    # Trade statistics
    if metrics.trades:
        lines.append("")
        lines.append("TRADE STATISTICS")
        lines.append("=" * 50)
        
        profitable_trades = [t for t in metrics.trades if t.pnl_usdt > 0]
        losing_trades = [t for t in metrics.trades if t.pnl_usdt < 0]
        
        lines.append(f"Profitable trades: {len(profitable_trades)} ({len(profitable_trades)/len(metrics.trades)*100:.1f}%)")
        lines.append(f"Losing trades: {len(losing_trades)} ({len(losing_trades)/len(metrics.trades)*100:.1f}%)")
        
        if profitable_trades:
            avg_win = sum(t.pnl_usdt for t in profitable_trades) / len(profitable_trades)
            lines.append(f"Average winning trade: ${avg_win:.2f}")
            
        if losing_trades:
            avg_loss = sum(t.pnl_usdt for t in losing_trades) / len(losing_trades)
            lines.append(f"Average losing trade: ${avg_loss:.2f}")
    
    return "\n".join(lines)