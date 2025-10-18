"""
Backtesting framework for portfolio rebalancing strategy.
"""

import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import numpy as np

from exchanges.structs import Symbol, Kline
from exchanges.structs.enums import KlineInterval
from exchanges.structs.types import AssetName
from exchanges.integrations.mexc.rest.mexc_rest_spot_public import MexcPublicSpotRestInterface
from config.config_manager import HftConfig

from .config import RebalanceConfig
from .portfolio_tracker import PortfolioTracker
from .rebalancer import ThresholdCascadeRebalancer
from .trend_filtered_rebalancer import TrendFilteredRebalancer


@dataclass
class BacktestResults:
    """Results from backtesting simulation."""
    
    # Performance metrics
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    
    # Trading statistics
    total_trades: int
    total_rebalances: int
    total_fees: float
    avg_rebalance_size: float
    
    # Portfolio metrics
    final_value: float
    initial_value: float
    best_performer: Tuple[str, float]
    worst_performer: Tuple[str, float]
    
    # Time metrics
    start_date: datetime
    end_date: datetime
    days_tested: int
    
    # Trend filtering metrics (optional)
    trend_filter_stats: Optional[Dict] = None
    strategy_type: str = "Standard"
    
    def summary(self) -> str:
        """Generate summary report."""
        base_report = f"""
=== Backtest Results Summary ({self.strategy_type}) ===
Period: {self.start_date.date()} to {self.end_date.date()} ({self.days_tested} days)

Performance Metrics:
  Total Return: {self.total_return:.2%}
  Annualized Return: {self.annualized_return:.2%}
  Sharpe Ratio: {self.sharpe_ratio:.2f}
  Max Drawdown: {self.max_drawdown:.2%}
  Win Rate: {self.win_rate:.2%}

Trading Statistics:
  Total Trades: {self.total_trades}
  Total Rebalances: {self.total_rebalances}
  Total Fees Paid: ${self.total_fees:.2f}
  Avg Rebalance Size: ${self.avg_rebalance_size:.2f}

Portfolio Results:
  Initial Value: ${self.initial_value:,.2f}
  Final Value: ${self.final_value:,.2f}
  Best Performer: {self.best_performer[0]} ({self.best_performer[1]:.2%})
  Worst Performer: {self.worst_performer[0]} ({self.worst_performer[1]:.2%})
"""
        
        # Add trend filtering statistics if available
        if self.trend_filter_stats:
            stats = self.trend_filter_stats
            trend_report = f"""
Trend Filtering Statistics:
  Total Rebalance Checks: {stats.get('total_checks', 0)}
  Trend Filtered (Blocked): {stats.get('trend_filtered', 0)}
  Mean Reversion Allowed: {stats.get('mean_reversion_allowed', 0)}
  Filter Rate: {stats.get('filter_rate', 0):.1%}
  Mean Reversion Rate: {stats.get('mean_reversion_rate', 0):.1%}
"""
            base_report += trend_report
        
        return base_report


class BacktestEngine:
    """
    Backtesting engine for portfolio rebalancing strategy using MEXC historical data.
    """
    
    def __init__(self, assets: List[str], initial_capital: float, 
                 config: Optional[RebalanceConfig] = None, use_trend_filter: bool = False):
        """
        Initialize backtest engine.
        
        Args:
            assets: List of asset symbols to trade
            initial_capital: Starting capital in USDT
            config: Rebalancing configuration (uses defaults if None)
            use_trend_filter: Whether to use trend-filtered rebalancer
        """
        self.assets = assets
        self.initial_capital = initial_capital
        self.config = config or RebalanceConfig()
        self.use_trend_filter = use_trend_filter
        
        # Initialize HFT config manager and MEXC client
        self.hft_config = HftConfig()
        self.mexc_config = self.hft_config.get_exchange_config('mexc_spot')
        self.rest_client = MexcPublicSpotRestInterface(self.mexc_config)
        
        # Will be initialized per backtest run
        self.tracker: Optional[PortfolioTracker] = None
        self.rebalancer: Optional[ThresholdCascadeRebalancer] = None
        self.price_data: Dict[str, List[Kline]] = {}
        
    async def fetch_historical_data(self, start_date: datetime, 
                                   end_date: datetime, interval: KlineInterval = KlineInterval.HOUR_1):
        """
        Fetch historical kline data from MEXC.
        
        Args:
            start_date: Start date for data
            end_date: End date for data
            interval: Kline interval (default 1 hour)
        """
        print(f"Fetching historical data from {start_date} to {end_date}...")
        
        for asset in self.assets:
            symbol = Symbol(base=AssetName(asset), quote=AssetName('USDT'))
            
            try:
                # Use get_klines_batch for efficient fetching
                klines = await self.rest_client.get_klines_batch(
                    symbol=symbol,
                    timeframe=interval,
                    date_from=start_date,
                    date_to=end_date
                )
                
                self.price_data[asset] = klines
                print(f"  {asset}: Fetched {len(klines)} candles")
                
            except Exception as e:
                print(f"  {asset}: Failed to fetch data - {e}")
                self.price_data[asset] = []
            
            # Small delay to respect rate limits
            await asyncio.sleep(0.5)
    
    def align_price_data(self) -> List[datetime]:
        """
        Align price data across all assets and return common timestamps.
        
        Returns:
            List of timestamps where all assets have data
        """
        if not self.price_data:
            return []
        
        # Get all unique timestamps
        all_timestamps = set()
        for klines in self.price_data.values():
            for kline in klines:
                all_timestamps.add(datetime.fromtimestamp(kline.open_time / 1000))
        
        # Sort timestamps
        sorted_timestamps = sorted(all_timestamps)
        
        # Filter to only timestamps where all assets have data
        common_timestamps = []
        for timestamp in sorted_timestamps:
            ts_ms = int(timestamp.timestamp() * 1000)
            has_all_data = True
            
            for asset, klines in self.price_data.items():
                # Check if this timestamp exists for this asset
                if not any(k.open_time == ts_ms for k in klines):
                    has_all_data = False
                    break
            
            if has_all_data:
                common_timestamps.append(timestamp)
        
        return common_timestamps
    
    def get_prices_at_timestamp(self, timestamp: datetime) -> Dict[str, float]:
        """
        Get prices for all assets at a specific timestamp.
        
        Args:
            timestamp: Target timestamp
            
        Returns:
            Dictionary of asset prices
        """
        prices = {}
        ts_ms = int(timestamp.timestamp() * 1000)
        
        for asset, klines in self.price_data.items():
            for kline in klines:
                if kline.open_time == ts_ms:
                    # Use close price of the candle
                    prices[asset] = kline.close_price
                    break
        
        return prices
    
    async def run_backtest(self, start_date: datetime, 
                          end_date: datetime) -> BacktestResults:
        """
        Run backtest simulation.
        
        Args:
            start_date: Backtest start date
            end_date: Backtest end date
            
        Returns:
            Backtest results
        """
        # Fetch historical data
        await self.fetch_historical_data(start_date, end_date)
        
        # Align timestamps
        timestamps = self.align_price_data()
        
        if not timestamps:
            raise ValueError("No common timestamps found for all assets")
        
        print(f"\nRunning backtest with {len(timestamps)} time points...")
        
        # Initialize portfolio tracker and rebalancer
        self.tracker = PortfolioTracker(self.assets, self.initial_capital, self.config)
        
        if self.use_trend_filter:
            self.rebalancer = TrendFilteredRebalancer(self.assets, self.config, self.tracker)
            print("Using Trend-Filtered Rebalancer")
        else:
            self.rebalancer = ThresholdCascadeRebalancer(self.assets, self.config, self.tracker)
            print("Using Standard Threshold Rebalancer")
        
        # Get initial prices and initialize portfolio
        initial_prices = self.get_prices_at_timestamp(timestamps[0])
        self.tracker.initialize_equal_weights(initial_prices, timestamps[0])
        
        # Track performance
        rebalance_count = 0
        winning_rebalances = 0
        
        # Run simulation
        for i, timestamp in enumerate(timestamps):
            # Get current prices
            prices = self.get_prices_at_timestamp(timestamp)
            
            # Update portfolio state
            state = self.tracker.update_prices(prices, timestamp)
            
            # Check and execute rebalancing
            event = self.rebalancer.execute_rebalance(state, prices)
            
            if event:
                rebalance_count += 1
                
                # Check if rebalance was profitable
                if event.portfolio_after and event.portfolio_after.total_value > event.portfolio_before.total_value:
                    winning_rebalances += 1
                
                # Print rebalance info
                if i % 100 == 0:  # Print every 100th rebalance
                    print(f"  [{timestamp.strftime('%Y-%m-%d')}] Rebalanced {event.trigger_asset} "
                          f"(deviation: {event.trigger_deviation:.1%})")
        
        # Calculate final metrics
        metrics = self.tracker.get_portfolio_metrics()
        rebalance_stats = self.rebalancer.get_statistics()
        
        # Calculate asset performance
        final_state = self.tracker.portfolio_history[-1]
        asset_returns = {}
        
        for asset in self.assets:
            initial_price = self.get_prices_at_timestamp(timestamps[0])[asset]
            final_price = self.get_prices_at_timestamp(timestamps[-1])[asset]
            asset_returns[asset] = (final_price - initial_price) / initial_price
        
        best_performer = max(asset_returns.items(), key=lambda x: x[1])
        worst_performer = min(asset_returns.items(), key=lambda x: x[1])
        
        # Calculate annualized return
        days = (timestamps[-1] - timestamps[0]).days
        years = days / 365.25
        annualized_return = (1 + metrics['total_return']) ** (1/years) - 1 if years > 0 else 0
        
        # Get trend filtering stats if using trend filter
        trend_stats = None
        strategy_type = "Standard"
        
        if self.use_trend_filter and hasattr(self.rebalancer, 'get_trend_statistics'):
            trend_stats = self.rebalancer.get_trend_statistics()
            strategy_type = "Trend-Filtered"
        
        return BacktestResults(
            total_return=metrics['total_return'],
            annualized_return=annualized_return,
            sharpe_ratio=metrics['sharpe_ratio'],
            max_drawdown=metrics['max_drawdown'],
            win_rate=winning_rebalances / rebalance_count if rebalance_count > 0 else 0,
            total_trades=rebalance_stats['total_actions'],
            total_rebalances=rebalance_count,
            total_fees=rebalance_stats['total_fees'],
            avg_rebalance_size=rebalance_stats['total_volume'] / rebalance_count if rebalance_count > 0 else 0,
            final_value=metrics['current_value'],
            initial_value=self.initial_capital,
            best_performer=best_performer,
            worst_performer=worst_performer,
            start_date=timestamps[0],
            end_date=timestamps[-1],
            days_tested=days,
            trend_filter_stats=trend_stats,
            strategy_type=strategy_type
        )
    
    def plot_results(self) -> None:
        """
        Plot backtest results (requires matplotlib).
        """
        try:
            import matplotlib.pyplot as plt
            
            if not self.tracker or not self.tracker.portfolio_history:
                print("No data to plot")
                return
            
            # Extract data
            timestamps = [state.timestamp for state in self.tracker.portfolio_history]
            values = [state.total_value for state in self.tracker.portfolio_history]
            
            # Create figure
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
            
            # Plot portfolio value
            ax1.plot(timestamps, values, label='Portfolio Value')
            ax1.axhline(y=self.initial_capital, color='r', linestyle='--', label='Initial Capital')
            ax1.set_ylabel('Portfolio Value (USDT)')
            ax1.set_title('Portfolio Performance')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # Plot asset weights
            for asset in self.assets:
                weights = []
                for state in self.tracker.portfolio_history:
                    if asset in state.assets:
                        weights.append(state.assets[asset].weight)
                    else:
                        weights.append(0)
                ax2.plot(timestamps, weights, label=asset)
            
            ax2.axhline(y=1/len(self.assets), color='r', linestyle='--', label='Target Weight')
            ax2.set_xlabel('Date')
            ax2.set_ylabel('Portfolio Weight')
            ax2.set_title('Asset Weights Over Time')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            
            plt.tight_layout()
            plt.show()
            
        except ImportError:
            print("Matplotlib not installed. Cannot plot results.")