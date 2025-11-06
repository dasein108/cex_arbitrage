"""
Trading Signals V2 - Visualization Module

Comprehensive visualization tools for analyzing cryptocurrency arbitrage trading performance,
including price charts, trade entry points, P&L tracking, and spread analysis.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from typing import List, Optional, Dict, Tuple
import seaborn as sns

from exchanges.structs.enums import ExchangeEnum
from trading.signals_v2.entities import ArbitrageTrade, PerformanceMetrics
from trading.data_sources.column_utils import get_column_key

# Set style for professional-looking charts
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")

class ArbitrageVisualization:
    """
    Comprehensive visualization suite for arbitrage trading analysis.
    
    This class provides multiple chart types for analyzing trading performance:
    - Price charts with bid/ask spreads for each exchange
    - Trade entry/exit markers with P&L information
    - Cumulative P&L tracking over time
    - Spread analysis between exchanges
    - Performance metrics dashboard
    """
    
    def __init__(self, figsize: Tuple[int, int] = (14, 10)):
        """
        Initialize the visualization module.
        
        Args:
            figsize: Figure size for the charts (width, height)
        """
        self.figsize = figsize
        self.exchanges = [ExchangeEnum.MEXC, ExchangeEnum.GATEIO]
        
        # Color scheme for exchanges
        self.exchange_colors = {
            ExchangeEnum.MEXC: {'bid': '#1f77b4', 'ask': '#aec7e8'},
            ExchangeEnum.GATEIO: {'bid': '#ff7f0e', 'ask': '#ffbb78'}
        }
        
        # Trade markers (without color to avoid conflicts)
        self.trade_markers = {
            'buy': {'marker': '^', 's': 100},
            'sell': {'marker': 'v', 's': 100}
        }

    def create_comprehensive_analysis(self, 
                                    df: pd.DataFrame, 
                                    trades: List[ArbitrageTrade],
                                    performance_metrics: PerformanceMetrics,
                                    symbol_name: str = "Trading Pair",
                                    save_path: Optional[str] = None) -> None:
        """
        Create comprehensive multi-subplot analysis of arbitrage trading performance.
        
        Args:
            df: DataFrame with historical price data including bid/ask for each exchange
            trades: List of arbitrage trades executed
            performance_metrics: Performance metrics from backtesting
            symbol_name: Name of the trading symbol for chart titles
            save_path: Optional path to save the chart image
        """
        
        # Create figure with subplots - main area + right sidebar
        fig = plt.figure(figsize=self.figsize)
        gs = fig.add_gridspec(3, 3, height_ratios=[2, 1, 1], width_ratios=[2, 2, 1], hspace=0.1, wspace=0.1)
        
        # Main price chart with trades (spans top two columns)
        ax_price = fig.add_subplot(gs[0, :2])
        self._plot_price_with_trades(ax_price, df, trades, symbol_name)
        
        # P&L tracking (bottom left)
        ax_pnl = fig.add_subplot(gs[1, :2])
        self._plot_cumulative_pnl(ax_pnl, trades)
        
        # Spread analysis (bottom center)
        ax_spread = fig.add_subplot(gs[2, :2])
        self._plot_spread_analysis(ax_spread, df, trades)
        
        # Performance metrics dashboard (right sidebar - spans all rows)
        ax_metrics = fig.add_subplot(gs[:, 2])
        self._plot_performance_dashboard(ax_metrics, performance_metrics)
        
        # Overall title
        fig.suptitle(f'{symbol_name} - Arbitrage Trading Analysis\n'
                    f'Total Trades: {len(trades)} | Total P&L: ${performance_metrics.total_pnl_usd:.2f} '
                    f'({performance_metrics.total_pnl_pct:.2f}%) | Win Rate: {performance_metrics.win_rate:.1f}%',
                    fontsize=16, fontweight='bold')

        fig.subplots_adjust(wspace=0.08)  # tighten horizontal spacing for this figure
        fig.tight_layout(pad=0.1, w_pad=0.4, h_pad=0.1)  # w_pad further reduces horizontal padding used by tight_layout

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"📊 Chart saved to: {save_path}")
        
        plt.show()

    def _plot_price_with_trades(self, ax: plt.Axes, df: pd.DataFrame, trades: List[ArbitrageTrade], symbol_name: str) -> None:
        """Plot price charts with bid/ask spreads and trade entry points."""
        
        # Plot bid/ask prices for each exchange
        for exchange in self.exchanges:
            bid_col = get_column_key(exchange, 'bid_price')
            ask_col = get_column_key(exchange, 'ask_price')
            
            if bid_col in df.columns and ask_col in df.columns:
                colors = self.exchange_colors[exchange]
                exchange_name = exchange.value.replace('_SPOT', '').title()
                
                # Plot bid and ask lines
                ax.plot(df.index, df[bid_col], color=colors['bid'], 
                       linewidth=1.5, label=f'{exchange_name} Bid', alpha=0.8)
                ax.plot(df.index, df[ask_col], color=colors['ask'], 
                       linewidth=1.5, label=f'{exchange_name} Ask', alpha=0.8)
                
                # Fill spread area
                ax.fill_between(df.index, df[bid_col], df[ask_col], 
                               alpha=0.2, color=colors['bid'])
        
        # Plot trade entry points
        buy_trades = []
        sell_trades = []
        
        for trade in trades:
            # Determine if this exchange was buy or sell side for this trade
            if trade.buy_exchange in [ExchangeEnum.MEXC, ExchangeEnum.GATEIO]:
                buy_trades.append((trade.timestamp, trade.buy_price, trade.buy_exchange, trade.pnl_usdt))
            if trade.sell_exchange in [ExchangeEnum.MEXC, ExchangeEnum.GATEIO]:
                sell_trades.append((trade.timestamp, trade.sell_price, trade.sell_exchange, trade.pnl_usdt))
        
        # Plot buy markers
        for timestamp, price, exchange, pnl in buy_trades:
            color = 'darkgreen' if pnl > 0 else 'darkred'
            ax.scatter(timestamp, price, **self.trade_markers['buy'], 
                      color=color, alpha=0.8, edgecolors='white', linewidth=1,
                      label='Buy Trade' if timestamp == buy_trades[0][0] else "")
        
        # Plot sell markers
        for timestamp, price, exchange, pnl in sell_trades:
            color = 'darkgreen' if pnl > 0 else 'darkred'
            ax.scatter(timestamp, price, **self.trade_markers['sell'], 
                      color=color, alpha=0.8, edgecolors='white', linewidth=1,
                      label='Sell Trade' if timestamp == sell_trades[0][0] else "")
        
        ax.set_title(f'{symbol_name} - Price Chart with Trade Entry Points', fontsize=14, fontweight='bold')
        ax.set_ylabel('Price (USDT)', fontsize=12)
        ax.legend(loc='upper left', fontsize=10)
        ax.grid(True, alpha=0.3)
        
        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

    def _plot_cumulative_pnl(self, ax: plt.Axes, trades: List[ArbitrageTrade]) -> None:
        """Plot cumulative P&L over time."""
        
        if not trades:
            ax.text(0.5, 0.5, 'No trades to display', ha='center', va='center', 
                   transform=ax.transAxes, fontsize=12)
            ax.set_title('Cumulative P&L', fontsize=12, fontweight='bold')
            return
        
        # Calculate cumulative P&L
        timestamps = [trade.timestamp for trade in trades]
        cumulative_pnl = np.cumsum([trade.pnl_usdt for trade in trades])
        
        # Plot cumulative P&L line
        colors = ['green' if pnl >= 0 else 'red' for pnl in cumulative_pnl]
        ax.plot(timestamps, cumulative_pnl, linewidth=2.5, color='blue', alpha=0.8)
        ax.fill_between(timestamps, 0, cumulative_pnl, alpha=0.3, color='blue')
        
        # Add individual trade markers
        for i, (timestamp, pnl) in enumerate(zip(timestamps, cumulative_pnl)):
            trade_pnl = trades[i].pnl_usdt
            color = 'green' if trade_pnl > 0 else 'red'
            ax.scatter(timestamp, pnl, color=color, s=50, alpha=0.8, edgecolors='white', linewidth=1)
        
        # Add zero line
        ax.axhline(y=0, color='black', linestyle='--', alpha=0.5, linewidth=1)
        
        ax.set_title('Cumulative P&L Over Time', fontsize=12, fontweight='bold')
        ax.set_ylabel('Cumulative P&L (USDT)', fontsize=11)
        ax.grid(True, alpha=0.3)
        
        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

    def _plot_spread_analysis(self, ax: plt.Axes, df: pd.DataFrame, trades: List[ArbitrageTrade]) -> None:
        """Plot spread analysis between exchanges."""
        
        mexc_bid_col = get_column_key(ExchangeEnum.MEXC, 'bid_price')
        mexc_ask_col = get_column_key(ExchangeEnum.MEXC, 'ask_price')
        gateio_bid_col = get_column_key(ExchangeEnum.GATEIO, 'bid_price')
        gateio_ask_col = get_column_key(ExchangeEnum.GATEIO, 'ask_price')
        
        # Check if required columns exist
        required_cols = [mexc_bid_col, mexc_ask_col, gateio_bid_col, gateio_ask_col]
        if not all(col in df.columns for col in required_cols):
            ax.text(0.5, 0.5, 'Insufficient data for spread analysis', ha='center', va='center', 
                   transform=ax.transAxes, fontsize=12)
            ax.set_title('Cross-Exchange Spread Analysis', fontsize=12, fontweight='bold')
            return
        
        # Calculate spreads
        mexc_to_gateio_spread = ((df[gateio_bid_col] - df[mexc_ask_col]) / df[mexc_ask_col] * 100)
        gateio_to_mexc_spread = ((df[mexc_bid_col] - df[gateio_ask_col]) / df[gateio_ask_col] * 100)
        
        # Plot spreads
        ax.plot(df.index, mexc_to_gateio_spread, linewidth=1.5, color='blue', 
               label='MEXC→Gate.io Spread', alpha=0.8)
        ax.plot(df.index, gateio_to_mexc_spread, linewidth=1.5, color='orange', 
               label='Gate.io→MEXC Spread', alpha=0.8)
        
        # Add zero line
        ax.axhline(y=0, color='black', linestyle='--', alpha=0.5, linewidth=1)
        
        # Add profitable threshold lines
        ax.axhline(y=0.3, color='green', linestyle=':', alpha=0.7, linewidth=1, label='Profit Threshold (0.3%)')
        ax.axhline(y=-0.3, color='green', linestyle=':', alpha=0.7, linewidth=1)
        
        # Mark trade execution points
        for trade in trades:
            # Determine spread direction and mark on chart
            timestamp = trade.timestamp
            if timestamp in df.index:
                mexc_spread = mexc_to_gateio_spread.loc[timestamp]
                gateio_spread = gateio_to_mexc_spread.loc[timestamp]
                
                if trade.buy_exchange == ExchangeEnum.MEXC:
                    ax.scatter(timestamp, gateio_spread, color='red', s=60, alpha=0.8, marker='o')
                elif trade.buy_exchange == ExchangeEnum.GATEIO:
                    ax.scatter(timestamp, mexc_spread, color='red', s=60, alpha=0.8, marker='o')
        
        ax.set_title('Cross-Exchange Spread Analysis', fontsize=12, fontweight='bold')
        ax.set_ylabel('Spread (%)', fontsize=11)
        ax.legend(loc='upper right', fontsize=9)
        ax.grid(True, alpha=0.3)
        
        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

    def _plot_performance_dashboard(self, ax: plt.Axes, metrics: PerformanceMetrics) -> None:
        """Create a performance metrics dashboard in the right sidebar."""
        
        # Turn off axis for text-based dashboard
        ax.axis('off')
        
        # Create metrics text with compact formatting for sidebar
        metrics_text = f"""Performance Metrics
────────────────────

💰 Financial:
  P&L: ${metrics.total_pnl_usd:.2f}
  P&L%: {metrics.total_pnl_pct:.2f}%
  Avg: ${metrics.avg_trade_pnl:.2f}
  Trades: {metrics.total_trades}

📊 Success:
  Win Rate: {metrics.win_rate:.1f}%
  Max DD: {metrics.max_drawdown:.2f}%
  Sharpe: {metrics.sharpe_ratio:.2f}

🔍 Analysis:
  Wins: {len([t for t in metrics.trades if t.pnl_usdt > 0])}
  Losses: {len([t for t in metrics.trades if t.pnl_usdt <= 0])}
  Best: ${max([t.pnl_usdt for t in metrics.trades]) if metrics.trades else 0:.2f}
  Worst: ${min([t.pnl_usdt for t in metrics.trades]) if metrics.trades else 0:.2f}

🎯 Strategy:
  Duration: {self._get_duration_text(metrics)}
  Freq: {self._get_trade_frequency(metrics)}
        """
        
        # Add colored background based on performance
        bg_color = 'lightgreen' if metrics.total_pnl_usd > 0 else 'lightcoral'
        ax.text(0.05, 0.98, metrics_text.strip(), transform=ax.transAxes, fontsize=9,
               verticalalignment='top', fontfamily='monospace',
               bbox=dict(boxstyle='round,pad=0.4', facecolor=bg_color, alpha=0.3))

    def _get_duration_text(self, metrics: PerformanceMetrics) -> str:
        """Get trading duration text."""
        if not metrics.trades:
            return "N/A"
        
        start_time = min(trade.timestamp for trade in metrics.trades)
        end_time = max(trade.timestamp for trade in metrics.trades)
        duration = end_time - start_time
        
        if duration.total_seconds() < 3600:
            return f"{duration.total_seconds()/60:.0f}m"
        else:
            return f"{duration.total_seconds()/3600:.1f}h"

    def _get_trade_frequency(self, metrics: PerformanceMetrics) -> str:
        """Get trade frequency text."""
        if len(metrics.trades) < 2:
            return "N/A"
        
        start_time = min(trade.timestamp for trade in metrics.trades)
        end_time = max(trade.timestamp for trade in metrics.trades)
        duration_hours = (end_time - start_time).total_seconds() / 3600
        
        if duration_hours > 0:
            freq = len(metrics.trades) / duration_hours
            return f"{freq:.1f}/h"
        return "N/A"

def visualize_arbitrage_results(df: pd.DataFrame, 
                              trades: List[ArbitrageTrade],
                              performance_metrics: PerformanceMetrics,
                              symbol_name: str = "Arbitrage Trading",
                              save_path: Optional[str] = None) -> None:
    """
    Main function to create comprehensive arbitrage trading visualization.
    
    This function should be called from signal_backtester.py to generate
    complete visual analysis of trading performance.
    
    Args:
        df: DataFrame with historical market data
        trades: List of executed arbitrage trades
        performance_metrics: Performance metrics from backtesting
        symbol_name: Name of trading symbol for chart titles
        save_path: Optional path to save the chart
    """
    
    # Create visualization instance
    viz = ArbitrageVisualization(figsize=(14, 10))
    
    # Generate comprehensive analysis
    viz.create_comprehensive_analysis(
        df=df,
        trades=trades,
        performance_metrics=performance_metrics,
        symbol_name=symbol_name,
        save_path=save_path
    )

def create_trade_summary_chart(trades: List[ArbitrageTrade], 
                             figsize: Tuple[int, int] = (12, 8)) -> None:
    """
    Create a focused chart showing trade summary statistics.
    
    Args:
        trades: List of arbitrage trades
        figsize: Figure size for the chart
    """
    
    if not trades:
        print("❌ No trades available for summary chart")
        return
    
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=figsize)
    
    # Trade P&L distribution
    trade_pnls = [trade.pnl_usdt for trade in trades]
    ax1.hist(trade_pnls, bins=min(10, len(trades)), alpha=0.7, color='blue', edgecolor='black')
    ax1.axvline(x=0, color='red', linestyle='--', alpha=0.7)
    ax1.set_title('Trade P&L Distribution', fontweight='bold')
    ax1.set_xlabel('P&L (USDT)')
    ax1.set_ylabel('Frequency')
    ax1.grid(True, alpha=0.3)
    
    # Trade timing
    timestamps = [trade.timestamp for trade in trades]
    hours = [ts.hour for ts in timestamps]
    ax2.hist(hours, bins=24, alpha=0.7, color='green', edgecolor='black')
    ax2.set_title('Trade Timing Distribution', fontweight='bold')
    ax2.set_xlabel('Hour of Day')
    ax2.set_ylabel('Number of Trades')
    ax2.grid(True, alpha=0.3)
    
    # Exchange usage
    buy_exchanges = [trade.buy_exchange.value.replace('_SPOT', '') for trade in trades]
    sell_exchanges = [trade.sell_exchange.value.replace('_SPOT', '') for trade in trades]
    
    exchange_counts = {}
    for ex in buy_exchanges + sell_exchanges:
        exchange_counts[ex] = exchange_counts.get(ex, 0) + 1
    
    ax3.bar(exchange_counts.keys(), exchange_counts.values(), alpha=0.7, color='orange')
    ax3.set_title('Exchange Usage', fontweight='bold')
    ax3.set_xlabel('Exchange')
    ax3.set_ylabel('Number of Operations')
    ax3.grid(True, alpha=0.3)
    
    # Cumulative P&L over time
    cumulative_pnl = np.cumsum(trade_pnls)
    ax4.plot(range(len(trades)), cumulative_pnl, linewidth=2, color='purple', marker='o')
    ax4.axhline(y=0, color='red', linestyle='--', alpha=0.7)
    ax4.set_title('Cumulative P&L by Trade', fontweight='bold')
    ax4.set_xlabel('Trade Number')
    ax4.set_ylabel('Cumulative P&L (USDT)')
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.show()