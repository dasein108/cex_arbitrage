"""
Result formatters for optimal threshold demo display.
"""

from typing import Any, Dict, Optional


class ThresholdFormatter:
    """Formats threshold results for display."""
    
    @staticmethod
    def format_thresholds(result: Any) -> str:
        """Format optimal thresholds section."""
        return f"""
🎯 OPTIMAL THRESHOLDS:
  FTS Entry (Futures-to-Spot): {result.optimal_fts_entry:.3f}%
    → Enter when futures discount >= {result.optimal_fts_entry:.3f}%
    → Action: BUY futures, SELL spot

  STF Entry (Spot-to-Futures): {result.optimal_stf_entry:.3f}%
    → Enter when spot discount >= {result.optimal_stf_entry:.3f}%
    → Action: BUY spot, SELL futures

  FTS Exit: {result.optimal_fts_exit:.3f}%
    → Close position when spread < {result.optimal_fts_exit:.3f}%

  STF Exit: {result.optimal_stf_exit:.3f}%
    → Close position when spread <= {result.optimal_stf_exit:.3f}%"""


class PerformanceFormatter:
    """Formats performance metrics for display."""
    
    @staticmethod
    def format_performance(result: Any) -> str:
        """Format expected performance section."""
        return f"""
📈 EXPECTED PERFORMANCE:
  Expected Profit: ${result.expected_profit:.2f}
  Total Trades: {result.trade_count}
    - FTS Trades: {result.fts_trades}
    - STF Trades: {result.stf_trades}
  Win Rate: {result.win_rate:.1f}%
  Profit Factor: {result.profit_factor:.2f}
  Sharpe Ratio: {result.sharpe_ratio:.2f}

⏱️ OPERATIONAL METRICS:
  Avg Holding Time: {result.avg_holding_time_hours:.2f} hours
  Max Drawdown: {result.max_drawdown:.2%}
  Total Fees Paid: ${result.total_fees_paid:.2f}"""


class StatisticsFormatter:
    """Formats market statistics for display."""
    
    @staticmethod
    def format_market_statistics(result: Any, spot_exchange: str, futures_exchange: str) -> str:
        """Format market statistics section."""
        if not (hasattr(result, 'market_statistics') and result.market_statistics):
            return "\n📊 MARKET STATISTICS:\n    ❌ Market statistics not available"
        
        stats = result.market_statistics
        output = ["\n📊 MARKET STATISTICS:"]
        
        # Spot exchange statistics
        if 'spot_exchange' in stats:
            output.append(StatisticsFormatter._format_exchange_stats(
                stats['spot_exchange'], spot_exchange, "📈"))
        
        # Futures exchange statistics  
        if 'futures_exchange' in stats:
            output.append(StatisticsFormatter._format_exchange_stats(
                stats['futures_exchange'], futures_exchange, "📉"))
        
        # Cross-exchange analysis
        if 'aligned_data' in stats:
            output.append(StatisticsFormatter._format_aligned_data(stats['aligned_data']))
        
        return "\n".join(output)
    
    @staticmethod
    def _format_exchange_stats(exchange_stats: Dict[str, Any], exchange_name: str, icon: str) -> str:
        """Format individual exchange statistics."""
        lines = [f"\n  {icon} {exchange_name} Statistics:"]
        
        if 'bid_price' in exchange_stats:
            bid = exchange_stats['bid_price']
            lines.append(f"    Bid prices: mean=${bid['mean']:.6f}, median=${bid['median']:.6f}")
        
        if 'ask_price' in exchange_stats:
            ask = exchange_stats['ask_price'] 
            lines.append(f"    Ask prices: mean=${ask['mean']:.6f}, median=${ask['median']:.6f}")
        
        if 'mid_price' in exchange_stats:
            mid = exchange_stats['mid_price']
            lines.append(f"    Mid prices: mean=${mid['mean']:.6f}, std=${mid['std']:.6f}")
        
        if 'bid_ask_spread' in exchange_stats:
            spread = exchange_stats['bid_ask_spread']
            lines.append(f"    Bid-ask spread: mean={spread['mean_percentage']:.3f}%, max={spread['max_percentage']:.3f}%")
        
        return "\n".join(lines)
    
    @staticmethod
    def _format_aligned_data(aligned_stats: Dict[str, Any]) -> str:
        """Format cross-exchange aligned data analysis."""
        lines = ["\n  🔀 Cross-Exchange Analysis:"]
        
        if 'price_correlation' in aligned_stats:
            corr = aligned_stats['price_correlation']['spot_futures_correlation']
            lines.append(f"    Price correlation: {corr:.3f}")
        
        if 'spot_to_futures_spread' in aligned_stats:
            stf = aligned_stats['spot_to_futures_spread']
            lines.append(f"    STF spread: mean={stf['mean']:.3f}%, positive={stf['positive_percentage']:.1f}%")
        
        if 'futures_to_spot_spread' in aligned_stats:
            fts = aligned_stats['futures_to_spot_spread']
            lines.append(f"    FTS spread: mean={fts['mean']:.3f}%, negative={fts['negative_percentage']:.1f}%")
        
        if 'data_quality' in aligned_stats:
            quality = aligned_stats['data_quality']
            lines.extend([
                "\n  ✅ Data Quality:",
                f"    Aligned data points: {quality['total_aligned_points']}",
                f"    Time range: {quality['timestamp_range_hours']:.1f} hours", 
                f"    Avg time gap: {quality['avg_time_gap_seconds']:.1f} seconds"
            ])
        
        return "\n".join(lines)


class RecommendationFormatter:
    """Formats implementation recommendations."""
    
    @staticmethod
    def format_recommendations(result: Any) -> str:
        """Format implementation recommendations section."""
        if result.trade_count == 0:
            return RecommendationFormatter._format_no_trades_recommendations()
        
        avg_profit_per_trade = result.expected_profit / result.trade_count
        output = [
            "=" * 70,
            "IMPLEMENTATION RECOMMENDATIONS",
            "=" * 70,
            f"\n✅ Strategy appears profitable with ${avg_profit_per_trade:.2f} per trade",
            "\n📋 To use these thresholds in production:"
        ]
        
        # Configuration code block
        config_block = f"""
# Add to your BacktestConfig or strategy configuration:
config = BacktestConfig(
    futures_to_spot_entry_threshold_pct={result.optimal_fts_entry:.3f},
    spot_to_futures_entry_threshold_pct={result.optimal_stf_entry:.3f},
    futures_to_spot_exit_threshold_pct={result.optimal_fts_exit:.3f},
    spot_to_futures_exit_threshold_pct={result.optimal_stf_exit:.3f}
)"""
        output.append(config_block)
        
        # Warnings
        warnings = RecommendationFormatter._generate_warnings(result)
        if warnings:
            output.extend(warnings)
        
        return "\n".join(output)
    
    @staticmethod
    def _format_no_trades_recommendations() -> str:
        """Format recommendations when no profitable trades found."""
        return f"""
{"=" * 70}
IMPLEMENTATION RECOMMENDATIONS
{"=" * 70}

❌ No profitable trades found with tested thresholds
   Consider:
   - Using longer historical data period
   - Adjusting fee structure
   - Testing different symbols
   - Checking data quality"""
    
    @staticmethod
    def _generate_warnings(result: Any) -> list:
        """Generate performance warnings."""
        warnings = []
        
        if result.sharpe_ratio < 1.0:
            warnings.append("⚠️  Low Sharpe ratio - consider tighter risk management")
        
        if result.win_rate < 50:
            warnings.append("⚠️  Win rate below 50% - ensure profit factor compensates")
        
        if result.max_drawdown > 0.05:
            warnings.append("⚠️  High drawdown - consider reducing position sizes")
        
        return warnings