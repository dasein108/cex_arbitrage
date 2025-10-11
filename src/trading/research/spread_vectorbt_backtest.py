"""
Vectorbt-based Backtesting Framework for Spot-Futures Arbitrage
High-performance vectorized backtesting using vectorbt.pro
"""

import asyncio
import numpy as np
import pandas as pd
import vectorbt as vbt
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Tuple, Dict, Optional
import warnings
warnings.filterwarnings('ignore')

from db.database_manager import initialize_database_manager, close_database_manager
from exchanges.structs import Symbol, AssetName, ExchangeEnum
from trading.analysis.data_loader import get_cached_book_ticker_data


@dataclass
class ArbitrageConfig:
    """
    BUSINESS LOGIC: Configuration parameters for spot-futures arbitrage strategy
    
    This dataclass encapsulates all strategy parameters for systematic testing:
    
    Signal Thresholds:
    - entry_threshold: Spread level to enter position (negative = spot cheaper)
    - exit_threshold: Spread level to exit position (positive = futures cheaper)
    
    Risk Management:
    - position_size: Capital allocation per trade (0.95 = 95% of available capital)
    - initial_capital: Starting portfolio value for backtesting
    
    Trading Costs (realistic exchange fees):
    - spot_maker_fee: MEXC spot maker fee (0% - zero fee advantage)
    - spot_taker_fee: MEXC spot taker fee (0.05% - market orders)
    - futures_maker_fee: Gate.io futures maker fee (0.02% - limit orders)
    - futures_taker_fee: Gate.io futures taker fee (0.05% - market orders)
    
    Execution Assumptions:
    - slippage: Market impact cost (0.01% - conservative estimate)
    """
    entry_threshold: float = -0.5  # Entry when spot_fut_spread < this (spot cheap)
    exit_threshold: float = 0.5    # Exit when fut_spot_spread > this (futures cheap)
    position_size: float = 0.95    # Use 95% of capital per trade
    spot_maker_fee: float = 0.0000  # MEXC spot maker (0% advantage)
    spot_taker_fee: float = 0.0005  # MEXC spot taker (0.05%)
    futures_maker_fee: float = 0.0002  # Gate.io futures maker (0.02%)
    futures_taker_fee: float = 0.0005  # Gate.io futures taker (0.05%)
    slippage: float = 0.0001       # 0.01% market impact
    initial_capital: float = 10000.0  # Starting capital for backtesting


class SpreadArbitrageBacktest:
    """
    BUSINESS LOGIC: Professional arbitrage backtesting engine using vectorbt
    
    This class implements a complete spot-futures arbitrage strategy with:
    
    Core Strategy:
    - Delta-neutral positions (long spot + short futures)
    - Profit from spread convergence/divergence
    - Market-neutral exposure (hedged against directional moves)
    
    Key Features:
    - High-performance vectorbt integration for fast backtesting
    - Realistic trading costs (fees + slippage) modeling
    - Systematic parameter optimization (grid search)
    - Comprehensive performance analytics and visualization
    
    Trading Mechanics:
    1. Entry: Buy spot asset + Sell futures contract (delta-neutral)
    2. Monitor: Track spread evolution and exit conditions
    3. Exit: Sell spot asset + Buy futures contract (close position)
    4. Profit: Net return from spread movements minus trading costs
    
    Risk Management:
    - Position sizing controls (max capital per trade)
    - No overlapping positions (one trade at a time)
    - Slippage and fee modeling for realistic P&L
    - Drawdown tracking and risk metrics
    """
    
    def __init__(self, config: ArbitrageConfig = None):
        self.config = config or ArbitrageConfig()
        self.spot_data = None
        self.futures_data = None
        self.merged_data = None
        
    def prepare_data(self, spot_df: pd.DataFrame, futures_df: pd.DataFrame) -> pd.DataFrame:
        """
        BUSINESS LOGIC: Prepare synchronized market data for arbitrage analysis
        
        This function transforms raw exchange data into arbitrage-ready format:
        1. Aligns spot and futures timestamps for synchronized analysis
        2. Calculates entry/exit spreads for arbitrage opportunities
        3. Adds technical indicators for market regime detection
        
        Key Arbitrage Metrics:
        - Entry spread: (spot_bid - futures_ask) / spot_bid * 100
          → Measures profitability of buying spot, selling futures
        - Exit spread: (futures_bid - spot_ask) / futures_bid * 100
          → Measures profitability of selling spot, buying futures
        
        Returns: Synchronized DataFrame ready for signal generation
        """
        
        # Ensure we have the required columns
        required_cols = ['bid_price', 'bid_qty', 'ask_price', 'ask_qty']
        
        # Select and rename columns
        spot_df = spot_df[required_cols].copy()
        futures_df = futures_df[required_cols].copy()
        
        # Add prefixes
        spot_df.columns = [f'spot_{col}' for col in spot_df.columns]
        futures_df.columns = [f'fut_{col}' for col in futures_df.columns]
        
        # Align timestamps (round to 1 second)
        spot_df.index = spot_df.index.round('1s')
        futures_df.index = futures_df.index.round('1s')
        
        # Merge on timestamp
        merged = spot_df.merge(
            futures_df,
            left_index=True,
            right_index=True,
            how='inner'
        )
        
        # Calculate spreads
        # Entry spread: spot cheap relative to futures
        merged['entry_spread'] = ((merged['spot_bid_price'] - merged['fut_ask_price']) / 
                                  merged['spot_bid_price']) * 100
        
        # Exit spread: futures cheap relative to spot  
        merged['exit_spread'] = ((merged['fut_bid_price'] - merged['spot_ask_price']) / 
                                 merged['fut_bid_price']) * 100
        
        # Add mid prices for analysis
        merged['spot_mid'] = (merged['spot_bid_price'] + merged['spot_ask_price']) / 2
        merged['fut_mid'] = (merged['fut_bid_price'] + merged['fut_ask_price']) / 2
        
        # Calculate spread volatility (rolling)
        merged['spread_volatility'] = merged['entry_spread'].rolling(window=100, min_periods=10).std()
        
        return merged.dropna()
    
    def generate_signals_vectorized(self, data: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """
        BUSINESS LOGIC: Generate arbitrage trading signals with position management
        
        This function implements the core arbitrage strategy logic:
        1. Entry Signal: When entry_spread < threshold (spot is cheap relative to futures)
           → Execute: Buy spot + Sell futures
        2. Exit Signal: When exit_spread > threshold (futures is cheap relative to spot)
           → Execute: Sell spot + Buy futures
        
        Position Management Rules:
        - Only one position open at any time (no overlapping trades)
        - Must exit current position before entering new one
        - Prevents over-leveraging and simplifies risk management
        
        Strategy Logic:
        - Profit from spread mean reversion between spot and futures
        - Entry when spread widens beyond threshold (opportunity)
        - Exit when spread reverses beyond threshold (take profit)
        
        Returns: (entry_signals, exit_signals) as boolean Series
        """
        
        # Entry signals: when entry_spread < threshold (spot is cheap)
        potential_entries = data['entry_spread'] < self.config.entry_threshold
        
        # Exit signals: when exit_spread > threshold (futures is cheap)
        potential_exits = data['exit_spread'] > self.config.exit_threshold
        
        # Use manual signal generation to ensure no overlapping positions
        entries = pd.Series(False, index=data.index)
        exits = pd.Series(False, index=data.index)
        
        in_position = False
        
        for i, (idx, row) in enumerate(data.iterrows()):
            if not in_position and potential_entries.iloc[i]:
                # Enter position
                entries.iloc[i] = True
                in_position = True
            elif in_position and potential_exits.iloc[i]:
                # Exit position
                exits.iloc[i] = True
                in_position = False
        
        return entries, exits
    
    def calculate_trade_returns(self, data: pd.DataFrame, entries: pd.Series, 
                               exits: pd.Series) -> pd.DataFrame:
        """
        BUSINESS LOGIC: Calculate delta-neutral arbitrage trade returns
        
        This function implements the core P&L calculation for spot-futures arbitrage:
        1. Entry: Buy spot asset + Sell futures (delta-neutral position)
        2. Exit: Sell spot asset + Buy futures (close delta-neutral position)
        3. Profit from spread convergence/divergence between spot and futures
        
        Key Trading Mechanics:
        - Entry prices include slippage (realistic execution costs)
        - Fees applied on both entry and exit (round-trip costs)
        - Returns calculated for both legs (spot + futures)
        - Net return = gross return - total fees
        
        Returns: DataFrame with trade-by-trade performance metrics
        """
        
        # Get entry and exit timestamps where signals are True
        entry_points = entries[entries].index
        exit_points = exits[exits].index
        
        # Ensure we have matching entry/exit pairs for complete trades
        num_trades = min(len(entry_points), len(exit_points))
        entry_points = entry_points[:num_trades]
        exit_points = exit_points[:num_trades]
        
        trades = []
        
        for entry_time, exit_time in zip(entry_points, exit_points):
            # Get row indices for exact timestamp matching
            try:
                # Find the exact row for entry and exit times
                entry_row = data.loc[entry_time]
                exit_row = data.loc[exit_time]
                
                # Handle case where loc returns Series (multiple matches) vs scalar
                if isinstance(entry_row, pd.Series) and len(entry_row.shape) == 1:
                    # Single row - extract values directly
                    spot_ask_entry = entry_row['spot_ask_price']
                    fut_bid_entry = entry_row['fut_bid_price']
                    entry_spread_val = entry_row['entry_spread']
                else:
                    # Multiple rows - take the first one
                    spot_ask_entry = entry_row['spot_ask_price'].iloc[0]
                    fut_bid_entry = entry_row['fut_bid_price'].iloc[0]
                    entry_spread_val = entry_row['entry_spread'].iloc[0]
                
                if isinstance(exit_row, pd.Series) and len(exit_row.shape) == 1:
                    # Single row - extract values directly
                    spot_bid_exit = exit_row['spot_bid_price']
                    fut_ask_exit = exit_row['fut_ask_price']
                    exit_spread_val = exit_row['exit_spread']
                else:
                    # Multiple rows - take the first one
                    spot_bid_exit = exit_row['spot_bid_price'].iloc[0]
                    fut_ask_exit = exit_row['fut_ask_price'].iloc[0]
                    exit_spread_val = exit_row['exit_spread'].iloc[0]
                
            except (KeyError, IndexError) as e:
                print(f"Warning: Could not find data for entry {entry_time} or exit {exit_time}, skipping trade")
                continue
            
            # ENTRY EXECUTION PRICES (with realistic slippage)
            # Buy spot: pay ask price + slippage (market impact)
            spot_entry_price = float(spot_ask_entry) * (1 + self.config.slippage)
            # Sell futures: receive bid price - slippage (market impact)
            fut_entry_price = float(fut_bid_entry) * (1 - self.config.slippage)
            
            # EXIT EXECUTION PRICES (with realistic slippage)
            # Sell spot: receive bid price - slippage (market impact)
            spot_exit_price = float(spot_bid_exit) * (1 - self.config.slippage)
            # Buy futures: pay ask price + slippage (market impact)
            fut_exit_price = float(fut_ask_exit) * (1 + self.config.slippage)
            
            # CALCULATE P&L FOR EACH LEG
            # Spot leg return: bought low, sold high (long position)
            spot_return = (spot_exit_price - spot_entry_price) / spot_entry_price
            # Futures leg return: sold high, bought low (short position)
            fut_return = (fut_entry_price - fut_exit_price) / fut_entry_price
            
            # TOTAL TRADING COSTS
            # Round-trip fees: entry (spot taker + futures taker) + exit (spot taker + futures taker)
            total_fees = (self.config.spot_taker_fee + self.config.futures_taker_fee) * 2
            
            # NET RETURN CALCULATION
            # Gross return: combined P&L from both legs (delta-neutral strategy)
            gross_return = spot_return + fut_return
            # Net return: gross return minus all trading costs
            net_return = gross_return - total_fees
            
            # Extract scalar spread values for trade record
            entry_spread = float(entry_spread_val)
            exit_spread = float(exit_spread_val)
            
            # Store trade record with all scalar values
            trades.append({
                'entry_time': entry_time,
                'exit_time': exit_time,
                'duration': (exit_time - entry_time).total_seconds() / 3600,
                'entry_spread': entry_spread,
                'exit_spread': exit_spread,
                'spot_return': spot_return * 100,      # Convert to percentage
                'fut_return': fut_return * 100,        # Convert to percentage
                'gross_return': gross_return * 100,    # Convert to percentage
                'fees_pct': total_fees * 100,          # Convert to percentage
                'net_return': net_return * 100         # Convert to percentage
            })
        
        return pd.DataFrame(trades)
    
    def run_vectorbt_backtest(self, data: pd.DataFrame, entries: pd.Series, 
                             exits: pd.Series) -> Dict:
        """
        BUSINESS LOGIC: Execute comprehensive portfolio backtest using vectorbt
        
        This function runs the complete arbitrage strategy simulation:
        1. Portfolio Simulation: Uses vectorbt's high-performance engine
        2. Performance Metrics: Calculates risk-adjusted returns (Sharpe, Sortino)
        3. Trade Analysis: Detailed P&L breakdown for each trade
        4. Risk Metrics: Drawdown analysis and volatility measures
        
        Vectorbt Integration:
        - Uses spot mid-price as reference for portfolio tracking
        - Applies realistic fees and slippage to all trades
        - Calculates standard portfolio metrics (returns, drawdown, etc.)
        
        Custom Arbitrage Metrics:
        - Win rate: Percentage of profitable trades
        - Profit factor: Gross profit / Gross loss ratio
        - Average trade duration: Holding period analysis
        - Fee impact: Total trading costs as % of gross profit
        
        Returns: Dictionary with portfolio object, trades DataFrame, and metrics
        """
        
        # Create price series for vectorbt
        # We use spot mid price as reference (could also use a synthetic price)
        price = data['spot_mid'].copy()
        
        # Calculate position sizes
        size = pd.Series(self.config.position_size, index=data.index)
        
        # Run portfolio simulation
        portfolio = vbt.Portfolio.from_signals(
            price,
            entries=entries,
            exits=exits,
            size=size,
            size_type='percent',
            fees=self.config.spot_taker_fee + self.config.futures_taker_fee,
            slippage=self.config.slippage,
            init_cash=self.config.initial_capital,
            freq='1s'
        )
        
        # Calculate detailed metrics
        stats = portfolio.stats()
        returns = portfolio.returns()
        
        # Custom metrics
        trades_df = self.calculate_trade_returns(data, entries, exits)
        
        if len(trades_df) > 0:
            winning_mask = trades_df['net_return'] > 0
            losing_mask = trades_df['net_return'] <= 0
            
            winning_trades = winning_mask.sum()
            losing_trades = losing_mask.sum()
            win_rate = winning_trades / len(trades_df) * 100
            
            avg_win = trades_df.loc[winning_mask, 'net_return'].mean() if winning_trades > 0 else 0
            avg_loss = trades_df.loc[losing_mask, 'net_return'].mean() if losing_trades > 0 else 0
            
            gross_profit = trades_df.loc[winning_mask, 'net_return'].sum() if winning_trades > 0 else 0
            gross_loss = abs(trades_df.loc[losing_mask, 'net_return'].sum()) if losing_trades > 0 else 0
            
            profit_factor = gross_profit / (gross_loss + 1e-10)
        else:
            win_rate = avg_win = avg_loss = profit_factor = 0
        
        return {
            'portfolio': portfolio,
            'trades': trades_df,
            'metrics': {
                'total_return': stats['Total Return [%]'],
                'sharpe_ratio': stats['Sharpe Ratio'],
                'sortino_ratio': stats['Sortino Ratio'],
                'max_drawdown': stats['Max Drawdown [%]'],
                'total_trades': len(trades_df),
                'win_rate': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'profit_factor': profit_factor,
                'avg_duration_hours': trades_df['duration'].mean() if len(trades_df) > 0 else 0,
                'total_fees_paid': trades_df['fees_pct'].sum() if len(trades_df) > 0 else 0
            },
            'returns': returns
        }
    
    def optimize_thresholds(self, data: pd.DataFrame, 
                           entry_range: Tuple[float, float] = (-2.0, 0.0),
                           exit_range: Tuple[float, float] = (0.0, 2.0),
                           step: float = 0.1) -> Dict:
        """
        BUSINESS LOGIC: Systematic threshold optimization for maximum profitability
        
        This function implements grid search optimization for arbitrage parameters:
        1. Parameter Grid: Tests all combinations of entry/exit thresholds
        2. Objective Function: Maximizes Sharpe ratio (risk-adjusted returns)
        3. Performance Tracking: Records all metrics for each parameter set
        4. Robustness Testing: Ensures strategy works across parameter ranges
        
        Optimization Strategy:
        - Entry thresholds: Negative values (spot cheaper than futures)
        - Exit thresholds: Positive values (futures cheaper than spot)
        - Step size: Balance between thoroughness and computation time
        
        Key Trade-offs:
        - Tighter thresholds: More trades, lower per-trade profit
        - Wider thresholds: Fewer trades, higher per-trade profit
        - Optimal point: Best risk-adjusted returns (Sharpe ratio)
        
        Returns: Dictionary with best parameters, results DataFrame, and heatmap
        """
        
        # Create parameter grid
        entry_thresholds = np.arange(entry_range[0], entry_range[1] + step, step)
        exit_thresholds = np.arange(exit_range[0], exit_range[1] + step, step)
        
        best_sharpe = -np.inf
        best_params = {}
        results = []
        
        print(f"Testing {len(entry_thresholds) * len(exit_thresholds)} parameter combinations...")
        
        for entry_thresh in entry_thresholds:
            for exit_thresh in exit_thresholds:
                # Update config
                self.config.entry_threshold = entry_thresh
                self.config.exit_threshold = exit_thresh
                
                # Generate signals
                entries, exits = self.generate_signals_vectorized(data)
                
                # Skip if no trades
                if not entries.any() or not exits.any():
                    continue
                
                # Run backtest
                try:
                    result = self.run_vectorbt_backtest(data, entries, exits)
                    
                    metrics = result['metrics']
                    sharpe = metrics['sharpe_ratio']
                    
                    results.append({
                        'entry_threshold': entry_thresh,
                        'exit_threshold': exit_thresh,
                        'sharpe_ratio': sharpe,
                        'total_return': metrics['total_return'],
                        'max_drawdown': metrics['max_drawdown'],
                        'total_trades': metrics['total_trades'],
                        'win_rate': metrics['win_rate'],
                        'profit_factor': metrics['profit_factor']
                    })
                    
                    # Update best
                    if sharpe > best_sharpe:
                        best_sharpe = sharpe
                        best_params = {
                            'entry_threshold': entry_thresh,
                            'exit_threshold': exit_thresh
                        }
                        
                except Exception as e:
                    continue
        
        results_df = pd.DataFrame(results)
        
        return {
            'best_params': best_params,
            'best_sharpe': best_sharpe,
            'all_results': results_df,
            'parameter_heatmap': results_df.pivot(
                index='entry_threshold',
                columns='exit_threshold',
                values='sharpe_ratio'
            )
        }
    
    def create_advanced_analysis(self, result: Dict, data: pd.DataFrame):
        """
        BUSINESS LOGIC: Generate comprehensive arbitrage strategy analysis dashboard
        
        This function creates a multi-panel visualization for strategy evaluation:
        1. Performance Charts: Cumulative returns, drawdown, portfolio value
        2. Strategy Analysis: Spread evolution, signal timing, trade distribution
        3. Risk Assessment: Return distribution, trade duration patterns
        4. Trade Quality: Individual trade performance over time
        
        Dashboard Panels:
        - Cumulative Returns: Overall strategy performance
        - Spread Evolution: Market dynamics and signal generation
        - Drawdown: Risk assessment and recovery periods
        - Trade Distribution: Profit/loss pattern analysis
        - Portfolio Value: Capital growth trajectory
        - Trade Timing: Performance consistency over time
        - Return Distribution: Risk/reward profile
        - Duration Analysis: Holding period optimization
        
        Returns: Matplotlib figure ready for saving/display
        """
        
        portfolio = result['portfolio']
        trades = result['trades']
        
        import matplotlib.pyplot as plt
        
        # Create matplotlib subplots instead of vectorbt
        fig, axes = plt.subplots(4, 2, figsize=(15, 12))
        fig.suptitle('Vectorbt Arbitrage Analysis', fontsize=16)
        
        # 1. Cumulative returns
        cumulative_returns = portfolio.cumulative_returns()
        axes[0, 0].plot(cumulative_returns.index, cumulative_returns.values)
        axes[0, 0].set_title('Cumulative Returns')
        axes[0, 0].grid(True, alpha=0.3)
        
        # 2. Spread evolution
        axes[0, 1].plot(data.index, data['entry_spread'], label='Entry Spread', alpha=0.7)
        axes[0, 1].plot(data.index, data['exit_spread'], label='Exit Spread', alpha=0.7)
        axes[0, 1].set_title('Spread Evolution')
        axes[0, 1].legend()
        axes[0, 1].grid(True, alpha=0.3)
        
        # 3. Drawdown
        drawdown = portfolio.drawdown()
        axes[1, 0].fill_between(drawdown.index, 0, drawdown.values, alpha=0.7, color='red')
        axes[1, 0].set_title('Drawdown')
        axes[1, 0].grid(True, alpha=0.3)
        
        # 4. Trade distribution
        if len(trades) > 0:
            axes[1, 1].hist(trades['net_return'], bins=20, alpha=0.7)
            axes[1, 1].set_title('Trade Returns Distribution')
            axes[1, 1].set_xlabel('Return %')
            axes[1, 1].grid(True, alpha=0.3)
        else:
            axes[1, 1].text(0.5, 0.5, 'No trades executed', ha='center', va='center', transform=axes[1, 1].transAxes)
            axes[1, 1].set_title('Trade Returns Distribution')
        
        # 5. Portfolio value
        portfolio_value = portfolio.value()
        axes[2, 0].plot(portfolio_value.index, portfolio_value.values)
        axes[2, 0].set_title('Portfolio Value')
        axes[2, 0].grid(True, alpha=0.3)
        
        # 6. Trade returns over time
        if len(trades) > 0:
            axes[2, 1].scatter(trades['entry_time'], trades['net_return'], alpha=0.7)
            axes[2, 1].set_title('Trade Returns Over Time')
            axes[2, 1].set_ylabel('Return %')
            axes[2, 1].grid(True, alpha=0.3)
        else:
            axes[2, 1].text(0.5, 0.5, 'No trades executed', ha='center', va='center', transform=axes[2, 1].transAxes)
            axes[2, 1].set_title('Trade Returns Over Time')
        
        # 7. Returns distribution
        returns = portfolio.returns()
        axes[3, 0].hist(returns.dropna(), bins=30, alpha=0.7)
        axes[3, 0].set_title('Portfolio Returns Distribution')
        axes[3, 0].set_xlabel('Return')
        axes[3, 0].grid(True, alpha=0.3)
        
        # 8. Trade duration distribution
        if len(trades) > 0:
            axes[3, 1].hist(trades['duration'], bins=15, alpha=0.7)
            axes[3, 1].set_title('Trade Duration Distribution')
            axes[3, 1].set_xlabel('Duration (hours)')
            axes[3, 1].grid(True, alpha=0.3)
        else:
            axes[3, 1].text(0.5, 0.5, 'No trades executed', ha='center', va='center', transform=axes[3, 1].transAxes)
            axes[3, 1].set_title('Trade Duration Distribution')
        
        plt.tight_layout()
        return fig


async def main():
    """
    BUSINESS LOGIC: Complete arbitrage strategy backtesting workflow
    
    This function executes the full arbitrage strategy development pipeline:
    
    1. Data Preparation:
       - Load synchronized spot and futures market data
       - Apply artificial spreads for demo (simulates real exchange differences)
       - Prepare arbitrage-ready dataset with spread calculations
    
    2. Strategy Testing:
       - Run initial backtest with default parameters
       - Analyze trade-by-trade performance
       - Display key performance metrics (Sharpe, drawdown, win rate)
    
    3. Parameter Optimization:
       - Grid search across entry/exit threshold combinations
       - Optimize for maximum Sharpe ratio (risk-adjusted returns)
       - Identify best parameter set from systematic testing
    
    4. Final Validation:
       - Run optimized strategy on same dataset
       - Compare default vs optimized performance
       - Generate comprehensive analysis dashboard
    
    5. Results Export:
       - Save portfolio statistics (CSV)
       - Save individual trade details (CSV)
       - Save analysis dashboard (PNG)
    
    Key Outputs:
    - Console: Real-time progress and performance metrics
    - Files: vectorbt_portfolio_stats.csv, vectorbt_trades.csv, vectorbt_arbitrage_analysis.png
    
    This provides a complete arbitrage strategy development and validation framework.
    """
    
    print("=" * 80)
    print("VECTORBT ARBITRAGE BACKTESTING FRAMEWORK")
    print("=" * 80)
    
    await initialize_database_manager()
    
    try:
        # Configuration
        end_date = datetime(2025, 10, 11, 9, 00, 0, tzinfo=timezone.utc)
        start_date = end_date - timedelta(days=1)
        symbol = Symbol(base=AssetName("LUNC"), quote=AssetName("USDT"))
        
        print(f"\n📊 Loading data for {symbol.base}/{symbol.quote}")
        print(f"📅 Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        
        # Load data (using same approach as spread_research.py)
        print("🏦 Simulating arbitrage with MEXC data at different price levels")
        
        spot_df = await get_cached_book_ticker_data(
            exchange=ExchangeEnum.MEXC.value,
            symbol_base=symbol.base,
            symbol_quote=symbol.quote,
            start_time=start_date,
            end_time=end_date
        )
        
        futures_df = await get_cached_book_ticker_data(
            exchange=ExchangeEnum.GATEIO_FUTURES.value,  # Using same data source
            symbol_base=symbol.base,
            symbol_quote=symbol.quote,
            start_time=start_date,
            end_time=end_date
        )
        
        # Add artificial spread to simulate different exchanges (for demo)
        spot_df = spot_df.copy()
        futures_df = futures_df.copy()
        
        spot_df['bid_price'] = spot_df['bid_price'] * 1.0002  # Slightly higher spot prices
        spot_df['ask_price'] = spot_df['ask_price'] * 1.0002
        futures_df['bid_price'] = futures_df['bid_price'] * 0.9998  # Slightly lower futures prices
        futures_df['ask_price'] = futures_df['ask_price'] * 0.9998
        
        if spot_df.empty or futures_df.empty:
            print("❌ Insufficient data available")
            return
        
        # Initialize backtester
        config = ArbitrageConfig(
            entry_threshold=-0.5,  # Entry when spread < -0.5%
            exit_threshold=0.5,    # Exit when spread > 0.5%
            position_size=0.95,
            initial_capital=10000
        )
        
        backtester = SpreadArbitrageBacktest(config)
        
        # Prepare data
        print("\n🔄 Preparing data...")
        data = backtester.prepare_data(spot_df, futures_df)
        print(f"✅ Prepared {len(data)} synchronized data points")
        
        # Generate signals
        print("\n📈 Generating trading signals...")
        entries, exits = backtester.generate_signals_vectorized(data)
        print(f"  Entry signals: {entries.sum()}")
        print(f"  Exit signals: {exits.sum()}")
        
        # Run backtest
        print("\n🚀 Running vectorbt backtest...")
        result = backtester.run_vectorbt_backtest(data, entries, exits)
        
        # Display results
        print("\n" + "=" * 60)
        print("BACKTEST RESULTS")
        print("=" * 60)
        
        metrics = result['metrics']
        for key, value in metrics.items():
            if isinstance(value, float):
                print(f"{key:.<30} {value:>10.2f}")
            else:
                print(f"{key:.<30} {value:>10}")
        
        # Display top trades
        trades = result['trades']
        if len(trades) > 0:
            print("\n📊 TOP 5 BEST TRADES")
            print("-" * 60)
            top_trades = trades.nlargest(5, 'net_return')[
                ['entry_time', 'exit_time', 'duration', 'net_return']
            ]
            print(top_trades.to_string())
            
            print("\n📉 TOP 5 WORST TRADES")
            print("-" * 60)
            worst_trades = trades.nsmallest(5, 'net_return')[
                ['entry_time', 'exit_time', 'duration', 'net_return']
            ]
            print(worst_trades.to_string())
        
        # Optimize parameters
        print("\n🔧 Optimizing thresholds (this may take a few minutes)...")
        optimization = backtester.optimize_thresholds(
            data,
            entry_range=(-2.0, 0.0),
            exit_range=(0.0, 2.0),
            step=0.25
        )
        
        print("\n✨ OPTIMIZATION RESULTS")
        print("-" * 60)
        print(f"Best parameters: {optimization['best_params']}")
        print(f"Best Sharpe ratio: {optimization['best_sharpe']:.2f}")
        
        # Show top parameter combinations
        top_5 = optimization['all_results'].nlargest(5, 'sharpe_ratio')
        print("\n🏆 TOP 5 PARAMETER COMBINATIONS")
        print("-" * 80)
        print(top_5[['entry_threshold', 'exit_threshold', 'sharpe_ratio', 
                    'total_return', 'total_trades', 'win_rate']].to_string(index=False))
        
        # Run backtest with optimal parameters
        print("\n🎯 Running backtest with optimal parameters...")
        backtester.config.entry_threshold = optimization['best_params']['entry_threshold']
        backtester.config.exit_threshold = optimization['best_params']['exit_threshold']
        
        opt_entries, opt_exits = backtester.generate_signals_vectorized(data)
        opt_result = backtester.run_vectorbt_backtest(data, opt_entries, opt_exits)
        
        print("\n📊 OPTIMIZED BACKTEST RESULTS")
        print("-" * 60)
        opt_metrics = opt_result['metrics']
        for key, value in opt_metrics.items():
            if isinstance(value, float):
                print(f"{key:.<30} {value:>10.2f}")
            else:
                print(f"{key:.<30} {value:>10}")
        
        # Create and save visualization
        print("\n📈 Creating advanced analysis charts...")
        fig = backtester.create_advanced_analysis(opt_result, data)
        fig.savefig('vectorbt_arbitrage_analysis.png', dpi=300, bbox_inches='tight')
        print("✅ Analysis saved to: vectorbt_arbitrage_analysis.png")
        
        # Save portfolio stats
        portfolio = opt_result['portfolio']
        stats_df = pd.DataFrame([portfolio.stats()])
        stats_df.to_csv('vectorbt_portfolio_stats.csv', index=False)
        print("✅ Portfolio stats saved to: vectorbt_portfolio_stats.csv")
        
        # Save trades for further analysis
        if len(opt_result['trades']) > 0:
            opt_result['trades'].to_csv('vectorbt_trades.csv', index=False)
            print("✅ Trade details saved to: vectorbt_trades.csv")
        
    finally:
        await close_database_manager()
        print("\n✅ Backtesting complete!")


if __name__ == "__main__":
    asyncio.run(main())