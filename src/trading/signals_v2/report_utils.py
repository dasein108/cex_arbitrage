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

    return "\n".join(lines)