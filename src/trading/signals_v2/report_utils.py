"""
Performance Reporting Utilities

This module provides comprehensive reporting and analysis tools for cryptocurrency
arbitrage trading strategies, including trade tables and performance metrics visualization.
"""

from typing import List, Dict, Any, Optional
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

def generate_performance_summary(metrics: PerformanceMetrics) -> str:
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

def generate_generic_report(items: Dict[str, Any], title: Optional[str] = None,
                            offset: int = 0) -> str:
    """
    Generate a generic report from a dictionary of items.

    Args:
        items: Dictionary of items to report
        title: Title of the report
    Returns:
        Formatted report string
    """
    lines = []
    if title:
        lines.append(title)
        lines.append("=" * len(title))

    for key, value in items.items():
        if isinstance(value, Dict):
            lines.append(f"{' '*offset}{key}:")
            sub_offset = offset+2
            if any(isinstance(v, Dict) for v in value.values()):
                lines.append(generate_generic_report(value, offset=sub_offset))
            else:
                lines.append(f'{" "*sub_offset}' + f" | ".join([f'{k}: {v}' for k, v in value.items()]))
            continue

        if isinstance(value, float):
            value = f"{value:.2f}"

        lines.append(f"{" "*offset}{key:>10} {value}")

    return "\n".join(lines)