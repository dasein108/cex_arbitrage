"""
Statistical Adaptive Threshold Optimizer for Spot-Futures Arbitrage
Implements dynamic spread thresholds based on rolling statistical analysis
"""

import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Tuple, Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

from db.database_manager import initialize_database_manager, close_database_manager
from exchanges.structs import Symbol, AssetName, ExchangeEnum
from trading.analysis.data_loader import get_cached_book_ticker_data


@dataclass
class TradingSignal:
    timestamp: pd.Timestamp
    action: str  # 'enter' or 'exit'
    spot_price: float
    futures_price: float
    spread_pct: float
    threshold: float
    z_score: float


@dataclass
class BacktestResult:
    total_trades: int
    winning_trades: int
    total_pnl: float
    total_pnl_pct: float
    sharpe_ratio: float
    max_drawdown: float
    avg_trade_duration: float
    fee_paid: float
    win_rate: float
    profit_factor: float
    avg_spread_capture: float


class StatisticalSpreadOptimizer:
    """
    Implements adaptive threshold optimization using rolling statistics.
    Dynamically adjusts entry/exit thresholds based on spread distribution.
    """
    
    def __init__(self, 
                 fast_window: int = 4,  # hours
                 slow_window: int = 24,  # hours
                 entry_z_score: float = -1.5,
                 exit_z_score: float = 1.5,
                 min_spread_threshold: float = -2.0,  # minimum entry spread %
                 max_spread_threshold: float = 3.0):  # maximum exit spread %
        
        self.fast_window_hours = fast_window
        self.slow_window_hours = slow_window
        self.entry_z_score = entry_z_score
        self.exit_z_score = exit_z_score
        self.min_spread_threshold = min_spread_threshold
        self.max_spread_threshold = max_spread_threshold
        
        # Fee structure
        self.fees = {
            "spot_maker": 0.0000,  # MEXC spot maker (0%)
            "spot_taker": 0.0005,  # MEXC spot taker (0.05%)
            "futures_maker": 0.0002,  # Gate.io futures maker (0.02%)
            "futures_taker": 0.0005,  # Gate.io futures taker (0.05%)
        }
        
    def calculate_rolling_statistics(self, spreads: pd.Series, window: str) -> pd.DataFrame:
        """Calculate rolling mean and standard deviation for spreads"""
        stats = pd.DataFrame(index=spreads.index)
        stats['mean'] = spreads.rolling(window, min_periods=1).mean()
        stats['std'] = spreads.rolling(window, min_periods=1).std()
        stats['z_score'] = (spreads - stats['mean']) / stats['std'].replace(0, 1)
        
        # Calculate percentile ranks for regime detection
        stats['percentile'] = spreads.rolling(window, min_periods=1).apply(
            lambda x: (x.iloc[-1] > x).mean() * 100 if len(x) > 1 else 50
        )
        
        return stats
    
    def generate_adaptive_thresholds(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate dynamic entry/exit thresholds based on rolling statistics"""
        
        # Calculate spreads
        df['spot_fut_spread'] = ((df['spot_bid_price'] - df['fut_ask_price']) / df['spot_bid_price']) * 100
        df['fut_spot_spread'] = ((df['fut_bid_price'] - df['spot_ask_price']) / df['fut_bid_price']) * 100
        
        # Calculate rolling statistics for both windows
        fast_stats = self.calculate_rolling_statistics(
            df['spot_fut_spread'], 
            f'{self.fast_window_hours}h'
        )
        slow_stats = self.calculate_rolling_statistics(
            df['spot_fut_spread'], 
            f'{self.slow_window_hours}h'
        )
        
        # Blend fast and slow statistics (weighted average)
        alpha = 0.7  # Weight for fast window
        df['spread_mean'] = alpha * fast_stats['mean'] + (1 - alpha) * slow_stats['mean']
        df['spread_std'] = alpha * fast_stats['std'] + (1 - alpha) * slow_stats['std']
        df['spread_z_score'] = (df['spot_fut_spread'] - df['spread_mean']) / df['spread_std'].replace(0, 1)
        
        # Calculate adaptive thresholds
        df['entry_threshold'] = df['spread_mean'] + self.entry_z_score * df['spread_std']
        df['exit_threshold'] = df['spread_mean'] + self.exit_z_score * df['spread_std']
        
        # Apply min/max constraints
        df['entry_threshold'] = df['entry_threshold'].clip(lower=self.min_spread_threshold)
        df['exit_threshold'] = df['exit_threshold'].clip(upper=self.max_spread_threshold)
        
        # Add regime detection
        df['volatility_regime'] = pd.cut(
            df['spread_std'],
            bins=[0, df['spread_std'].quantile(0.33), df['spread_std'].quantile(0.67), float('inf')],
            labels=['low', 'medium', 'high']
        )
        
        # Add momentum indicator
        df['spread_momentum'] = df['spot_fut_spread'].diff(12)  # 12 period momentum
        
        return df
    
    def generate_trading_signals(self, df: pd.DataFrame) -> List[TradingSignal]:
        """Generate entry and exit signals based on adaptive thresholds"""
        signals = []
        position_open = False
        entry_signal = None
        
        for idx, row in df.iterrows():
            if pd.isna(row['spread_z_score']):
                continue
                
            # Entry signal: spot_fut_spread < entry_threshold (spot cheap vs futures)
            if not position_open and row['spot_fut_spread'] < row['entry_threshold']:
                entry_signal = TradingSignal(
                    timestamp=idx,
                    action='enter',
                    spot_price=row['spot_ask_price'],  # Buy spot at ask
                    futures_price=row['fut_bid_price'],  # Sell futures at bid
                    spread_pct=row['spot_fut_spread'],
                    threshold=row['entry_threshold'],
                    z_score=row['spread_z_score']
                )
                signals.append(entry_signal)
                position_open = True
            
            # Exit signal: fut_spot_spread > exit_threshold (futures cheap vs spot)
            elif position_open and row['fut_spot_spread'] > row['exit_threshold']:
                signals.append(TradingSignal(
                    timestamp=idx,
                    action='exit',
                    spot_price=row['spot_bid_price'],  # Sell spot at bid
                    futures_price=row['fut_ask_price'],  # Buy futures at ask
                    spread_pct=row['fut_spot_spread'],
                    threshold=row['exit_threshold'],
                    z_score=row['spread_z_score']
                ))
                position_open = False
                entry_signal = None
        
        return signals
    
    def backtest_strategy(self, df: pd.DataFrame, signals: List[TradingSignal], 
                         initial_capital: float = 10000) -> BacktestResult:
        """Run backtest with detailed performance metrics"""
        
        trades = []
        capital = initial_capital
        peak_capital = capital
        max_drawdown = 0
        
        # Pair entry and exit signals
        i = 0
        while i < len(signals) - 1:
            if signals[i].action == 'enter' and signals[i + 1].action == 'exit':
                entry = signals[i]
                exit_signal = signals[i + 1]
                
                # Calculate trade PnL
                # Entry: Buy spot, sell futures
                position_size = capital * 0.95  # Use 95% of capital per trade
                
                # Entry fees
                spot_buy_fee = position_size * self.fees['spot_taker']
                futures_sell_fee = position_size * self.fees['futures_taker']
                entry_cost = spot_buy_fee + futures_sell_fee
                
                # Exit fees
                spot_sell_fee = position_size * self.fees['spot_taker']
                futures_buy_fee = position_size * self.fees['futures_taker']
                exit_cost = spot_sell_fee + futures_buy_fee
                
                # Price changes
                spot_pnl = (exit_signal.spot_price - entry.spot_price) / entry.spot_price
                futures_pnl = (entry.futures_price - exit_signal.futures_price) / entry.futures_price
                
                # Total PnL
                gross_pnl = position_size * (spot_pnl + futures_pnl)
                net_pnl = gross_pnl - entry_cost - exit_cost
                
                # Update capital
                capital += net_pnl
                
                # Track drawdown
                peak_capital = max(peak_capital, capital)
                drawdown = (peak_capital - capital) / peak_capital
                max_drawdown = max(max_drawdown, drawdown)
                
                # Record trade
                trades.append({
                    'entry_time': entry.timestamp,
                    'exit_time': exit_signal.timestamp,
                    'duration_hours': (exit_signal.timestamp - entry.timestamp).total_seconds() / 3600,
                    'entry_spread': entry.spread_pct,
                    'exit_spread': exit_signal.spread_pct,
                    'spread_capture': exit_signal.spread_pct - entry.spread_pct,
                    'gross_pnl': gross_pnl,
                    'fees': entry_cost + exit_cost,
                    'net_pnl': net_pnl,
                    'net_pnl_pct': net_pnl / position_size * 100
                })
                
                i += 2
            else:
                i += 1
        
        # Calculate metrics
        if not trades:
            return BacktestResult(
                total_trades=0, winning_trades=0, total_pnl=0, total_pnl_pct=0,
                sharpe_ratio=0, max_drawdown=0, avg_trade_duration=0,
                fee_paid=0, win_rate=0, profit_factor=0, avg_spread_capture=0
            )
        
        trades_df = pd.DataFrame(trades)
        winning_trades = len(trades_df[trades_df['net_pnl'] > 0])
        losing_trades = len(trades_df[trades_df['net_pnl'] <= 0])
        
        # Calculate Sharpe ratio (assuming daily returns)
        if len(trades_df) > 1:
            returns = trades_df.set_index('entry_time')['net_pnl_pct']
            daily_returns = returns.resample('D').sum().fillna(0)
            sharpe_ratio = np.sqrt(365) * daily_returns.mean() / (daily_returns.std() + 1e-8)
        else:
            sharpe_ratio = 0
        
        # Calculate profit factor
        gross_profit = trades_df[trades_df['net_pnl'] > 0]['net_pnl'].sum()
        gross_loss = abs(trades_df[trades_df['net_pnl'] <= 0]['net_pnl'].sum())
        profit_factor = gross_profit / (gross_loss + 1e-8)
        
        return BacktestResult(
            total_trades=len(trades),
            winning_trades=winning_trades,
            total_pnl=capital - initial_capital,
            total_pnl_pct=(capital - initial_capital) / initial_capital * 100,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown * 100,
            avg_trade_duration=trades_df['duration_hours'].mean(),
            fee_paid=trades_df['fees'].sum(),
            win_rate=winning_trades / len(trades) * 100 if trades else 0,
            profit_factor=profit_factor,
            avg_spread_capture=trades_df['spread_capture'].mean()
        )
    
    def optimize_parameters(self, df: pd.DataFrame, 
                           z_score_range: Tuple[float, float] = (-3.0, -0.5),
                           step: float = 0.25) -> Dict:
        """Optimize entry/exit z-scores using grid search"""
        
        best_result = None
        best_params = {}
        results = []
        
        # Grid search over z-score parameters
        for entry_z in np.arange(z_score_range[0], z_score_range[1], step):
            for exit_z in np.arange(0.5, 3.0, step):
                # Update parameters
                self.entry_z_score = entry_z
                self.exit_z_score = exit_z
                
                # Generate thresholds and signals
                df_with_thresholds = self.generate_adaptive_thresholds(df.copy())
                signals = self.generate_trading_signals(df_with_thresholds)
                
                # Run backtest
                result = self.backtest_strategy(df_with_thresholds, signals)
                
                # Track results
                results.append({
                    'entry_z': entry_z,
                    'exit_z': exit_z,
                    'sharpe': result.sharpe_ratio,
                    'total_pnl_pct': result.total_pnl_pct,
                    'trades': result.total_trades,
                    'win_rate': result.win_rate,
                    'max_dd': result.max_drawdown
                })
                
                # Update best (optimize for Sharpe ratio)
                if best_result is None or result.sharpe_ratio > best_result.sharpe_ratio:
                    best_result = result
                    best_params = {'entry_z': entry_z, 'exit_z': exit_z}
        
        return {
            'best_params': best_params,
            'best_result': best_result,
            'all_results': pd.DataFrame(results)
        }


async def main():
    """Main execution function with example usage"""
    
    print("=" * 80)
    print("STATISTICAL ADAPTIVE THRESHOLD OPTIMIZER")
    print("=" * 80)
    
    # Load market data
    await initialize_database_manager()
    
    try:
        # Configuration
        end_date = datetime(2025, 10, 11, 16, 15, 0, tzinfo=timezone.utc)
        start_date = end_date - timedelta(days=7)  # Use 7 days for optimization
        symbol = Symbol(base=AssetName("LUNC"), quote=AssetName("USDT"))
        
        print(f"\n📊 Loading data for {symbol.base}/{symbol.quote}")
        print(f"📅 Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        
        # Load spot data (MEXC)
        spot_df = await get_cached_book_ticker_data(
            exchange=ExchangeEnum.MEXC.value,
            symbol_base=symbol.base,
            symbol_quote=symbol.quote,
            start_time=start_date,
            end_time=end_date
        )
        
        # Load futures data (Gate.io)
        futures_df = await get_cached_book_ticker_data(
            exchange=ExchangeEnum.GATEIO_FUTURES.value,
            symbol_base=symbol.base,
            symbol_quote=symbol.quote,
            start_time=start_date,
            end_time=end_date
        )
        
        if spot_df.empty or futures_df.empty:
            print("❌ Insufficient data available")
            return
        
        # Prepare data
        def prepare_data(spot_df, futures_df):
            # Add prefixes
            spot_df = spot_df[['bid_price', 'bid_qty', 'ask_price', 'ask_qty']].copy()
            futures_df = futures_df[['bid_price', 'bid_qty', 'ask_price', 'ask_qty']].copy()
            
            spot_df.columns = [f'spot_{col}' for col in spot_df.columns]
            futures_df.columns = [f'fut_{col}' for col in futures_df.columns]
            
            # Round to 1 second and merge
            spot_df.index = spot_df.index.round('1s')
            futures_df.index = futures_df.index.round('1s')
            
            merged = spot_df.merge(futures_df, left_index=True, right_index=True, how='inner')
            return merged.dropna()
        
        df = prepare_data(spot_df, futures_df)
        print(f"✅ Loaded {len(df)} synchronized data points")
        
        # Initialize optimizer with default parameters
        optimizer = StatisticalSpreadOptimizer(
            fast_window=4,   # 4 hour fast window
            slow_window=24,  # 24 hour slow window
            entry_z_score=-1.5,
            exit_z_score=1.5
        )
        
        # Generate adaptive thresholds
        print("\n🔄 Generating adaptive thresholds...")
        df_with_thresholds = optimizer.generate_adaptive_thresholds(df.copy())
        
        # Display threshold statistics
        print("\n📈 Threshold Statistics:")
        print(f"  Entry threshold range: {df_with_thresholds['entry_threshold'].min():.2f}% to {df_with_thresholds['entry_threshold'].max():.2f}%")
        print(f"  Exit threshold range: {df_with_thresholds['exit_threshold'].min():.2f}% to {df_with_thresholds['exit_threshold'].max():.2f}%")
        print(f"  Spread volatility (std): {df_with_thresholds['spread_std'].mean():.2f}%")
        
        # Generate trading signals
        signals = optimizer.generate_trading_signals(df_with_thresholds)
        print(f"\n📊 Generated {len(signals)} trading signals")
        
        # Run backtest
        result = optimizer.backtest_strategy(df_with_thresholds, signals)
        
        print("\n📊 BACKTEST RESULTS (Default Parameters)")
        print("-" * 40)
        print(f"Total trades:        {result.total_trades}")
        print(f"Winning trades:      {result.winning_trades}")
        print(f"Win rate:            {result.win_rate:.1f}%")
        print(f"Total PnL:           ${result.total_pnl:.2f}")
        print(f"Total PnL %:         {result.total_pnl_pct:.2f}%")
        print(f"Sharpe ratio:        {result.sharpe_ratio:.2f}")
        print(f"Max drawdown:        {result.max_drawdown:.1f}%")
        print(f"Avg trade duration:  {result.avg_trade_duration:.1f} hours")
        print(f"Total fees paid:     ${result.fee_paid:.2f}")
        print(f"Profit factor:       {result.profit_factor:.2f}")
        print(f"Avg spread capture:  {result.avg_spread_capture:.2f}%")
        
        # Optimize parameters
        print("\n🔧 Optimizing parameters (this may take a minute)...")
        optimization_result = optimizer.optimize_parameters(df)
        
        print("\n✨ OPTIMIZED PARAMETERS")
        print("-" * 40)
        print(f"Best entry z-score:  {optimization_result['best_params']['entry_z']:.2f}")
        print(f"Best exit z-score:   {optimization_result['best_params']['exit_z']:.2f}")
        
        best = optimization_result['best_result']
        print("\n📊 OPTIMIZED BACKTEST RESULTS")
        print("-" * 40)
        print(f"Total trades:        {best.total_trades}")
        print(f"Win rate:            {best.win_rate:.1f}%")
        print(f"Total PnL %:         {best.total_pnl_pct:.2f}%")
        print(f"Sharpe ratio:        {best.sharpe_ratio:.2f}")
        print(f"Max drawdown:        {best.max_drawdown:.1f}%")
        print(f"Profit factor:       {best.profit_factor:.2f}")
        
        # Show top 5 parameter combinations
        all_results = optimization_result['all_results']
        top_5 = all_results.nlargest(5, 'sharpe')
        
        print("\n🏆 TOP 5 PARAMETER COMBINATIONS (by Sharpe)")
        print("-" * 60)
        print(top_5[['entry_z', 'exit_z', 'sharpe', 'total_pnl_pct', 'trades', 'win_rate']].to_string(index=False))
        
        # Analyze regime performance
        print("\n📊 REGIME ANALYSIS")
        print("-" * 40)
        regime_counts = df_with_thresholds['volatility_regime'].value_counts()
        for regime, count in regime_counts.items():
            pct = count / len(df_with_thresholds) * 100
            print(f"{regime} volatility: {pct:.1f}% of time")
        
    finally:
        await close_database_manager()
        print("\n✅ Analysis complete")


if __name__ == "__main__":
    asyncio.run(main())