"""
Multi-Position Delta-Neutral Arbitrage Strategy
Supports parallel positions with smart entry/exit timing

FIXED: Proper handling of warmup period and NaN values
"""

import datetime
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
import numpy as np

from exchanges.structs import Symbol, AssetName
from trading.research.trading_utlis import load_market_data
import pandas as pd

pd.set_option('display.precision', 10)
pd.set_option('display.float_format', None)


@dataclass
class Position:
    """Single arbitrage position"""
    position_id: int
    entry_time: pd.Timestamp
    entry_spot_ask: float
    entry_fut_bid: float
    entry_spread_pct: float
    entry_spread_zscore: float
    max_pnl_seen: float = -float('inf')
    capital_allocated: float = 0.0


class PositionManager:
    """Manages multiple parallel positions with intelligent sizing"""
    
    def __init__(self, total_capital: float, max_positions: int = 5,
                 capital_per_position: float = 0.2):
        self.total_capital = total_capital
        self.max_positions = max_positions
        self.capital_per_position = capital_per_position
        self.positions: List[Position] = []
        self.next_position_id = 1
        
    def available_capital(self) -> float:
        allocated = sum(p.capital_allocated for p in self.positions)
        return self.total_capital - allocated
    
    def can_open_position(self, required_capital: float) -> bool:
        if len(self.positions) >= self.max_positions:
            return False
        if self.available_capital() < required_capital:
            return False
        return True
    
    def open_position(self, entry_time: pd.Timestamp, entry_spot_ask: float,
                     entry_fut_bid: float, entry_spread_pct: float,
                     entry_spread_zscore: float) -> Optional[Position]:
        required_capital = self.total_capital * self.capital_per_position
        
        if not self.can_open_position(required_capital):
            return None
        
        position = Position(
            position_id=self.next_position_id,
            entry_time=entry_time,
            entry_spot_ask=entry_spot_ask,
            entry_fut_bid=entry_fut_bid,
            entry_spread_pct=entry_spread_pct,
            entry_spread_zscore=entry_spread_zscore,
            capital_allocated=required_capital
        )
        
        self.positions.append(position)
        self.next_position_id += 1
        return position
    
    def close_position(self, position: Position):
        self.positions.remove(position)
    
    def get_position_count(self) -> int:
        return len(self.positions)


class SmartEntryExit:
    """Intelligent entry/exit timing based on spread statistics"""
    
    def __init__(self, lookback_period: int = 500, min_warmup: int = 100):
        self.lookback_period = lookback_period
        self.min_warmup = min_warmup  # Minimum data points before trading
    
    def calculate_spread_stats(self, df: pd.DataFrame, 
                               current_idx: int) -> Optional[Dict[str, float]]:
        """Calculate spread statistics from historical data"""
        
        # Need minimum warmup period
        if current_idx < self.min_warmup:
            return None
        
        start_idx = max(0, current_idx - self.lookback_period)
        historical_spreads = df['entry_cost_pct'].iloc[start_idx:current_idx]
        
        # Filter out NaN values
        historical_spreads = historical_spreads.dropna()
        
        if len(historical_spreads) < 50:
            return None
        
        current_spread = df['entry_cost_pct'].iloc[current_idx]
        
        # Check for NaN in current spread
        if pd.isna(current_spread):
            return None
        
        mean = historical_spreads.mean()
        std = historical_spreads.std()
        
        # Check for invalid std
        if pd.isna(std) or std < 1e-10:
            return None
        
        zscore = (current_spread - mean) / std
        percentile = (historical_spreads < current_spread).mean() * 100
        volatility = std
        
        return {
            'mean': mean,
            'std': std,
            'zscore': zscore,
            'percentile': percentile,
            'volatility': volatility,
            'current': current_spread
        }
    
    def should_enter(self, df: pd.DataFrame, current_idx: int,
                    min_zscore: float = -1.0,
                    max_entry_cost: float = 0.5) -> Tuple[bool, Optional[Dict]]:
        """
        Determine if we should enter a position.
        Returns (should_enter, stats_dict)
        """
        stats = self.calculate_spread_stats(df, current_idx)
        
        # No stats = not enough data yet
        if stats is None:
            return False, None
        
        current_spread = stats['current']
        zscore = stats['zscore']
        percentile = stats['percentile']
        
        # Check for NaN in calculated values
        if pd.isna(zscore) or pd.isna(percentile):
            return False, stats
        
        # Criteria 1: Absolute threshold
        if current_spread >= max_entry_cost:
            return False, stats
        
        # Criteria 2: Z-score (spread is significantly cheap)
        if zscore >= min_zscore:
            return False, stats
        
        # Criteria 3: Percentile (in bottom 30%)
        if percentile >= 30:
            return False, stats
        
        return True, stats
    
    def should_exit(self, position: Position, current_row: pd.Series,
                   spot_fee: float, fut_fee: float,
                   min_profit_pct: float = 0.1,
                   trailing_stop_pct: float = 0.05,
                   profit_acceleration: bool = True) -> Tuple[bool, str, float]:
        """
        Determine if we should exit a position.
        Returns (should_exit, reason, current_pnl_pct)
        """
        
        # Calculate current P&L
        entry_spot_cost = position.entry_spot_ask * (1 + spot_fee)
        entry_fut_receive = position.entry_fut_bid * (1 - fut_fee)
        exit_spot_receive = current_row['spot_bid_price'] * (1 - spot_fee)
        exit_fut_cost = current_row['fut_ask_price'] * (1 + fut_fee)
        
        spot_pnl = exit_spot_receive - entry_spot_cost
        fut_pnl = entry_fut_receive - exit_fut_cost
        total_pnl = spot_pnl + fut_pnl
        
        capital = entry_spot_cost
        net_pnl_pct = (total_pnl / capital) * 100
        
        # Update max P&L seen
        if net_pnl_pct > position.max_pnl_seen:
            position.max_pnl_seen = net_pnl_pct
        
        # Calculate holding time
        hours_held = (current_row.name - position.entry_time).total_seconds() / 3600
        
        # DYNAMIC PROFIT TARGET based on holding time
        if profit_acceleration and hours_held > 1.0:
            time_factor = min(hours_held / 6.0, 1.0)
            adjusted_profit_target = min_profit_pct * (1 - 0.5 * time_factor)
        else:
            adjusted_profit_target = min_profit_pct
        
        # EXIT LOGIC
        
        # 1. Profit target (dynamic)
        if net_pnl_pct >= adjusted_profit_target:
            return True, 'profit_target', net_pnl_pct
        
        # 2. Trailing stop (lock in profits)
        if position.max_pnl_seen >= min_profit_pct:
            pullback = position.max_pnl_seen - net_pnl_pct
            if pullback >= trailing_stop_pct:
                return True, 'trailing_stop', net_pnl_pct
        
        # 3. Timeout with minimum acceptable profit
        if hours_held >= 6.0 and net_pnl_pct >= -0.05:
            return True, 'timeout', net_pnl_pct
        
        # 4. Emergency exit (spread went very wrong)
        if net_pnl_pct < -0.5:
            return True, 'emergency_exit', net_pnl_pct
        
        return False, '', net_pnl_pct


def multi_position_backtest(
    df: pd.DataFrame,
    total_capital: float = 10000.0,
    max_positions: int = 5,
    capital_per_position: float = 0.2,
    entry_zscore_threshold: float = -1.0,
    max_entry_cost: float = 0.5,
    min_profit_pct: float = 0.1,
    trailing_stop_pct: float = 0.05,
    spot_fee: float = 0.0005,
    fut_fee: float = 0.0005,
    min_warmup: int = 100
) -> List[Dict]:
    """
    Multi-position backtest with intelligent entry/exit.
    
    Args:
        min_warmup: Minimum data points before starting to trade (default 100)
    """
    
    # Calculate entry cost for the entire dataframe
    df['entry_cost_pct'] = ((df['spot_ask_price'] - df['fut_bid_price']) / 
                             df['spot_ask_price']) * 100
    
    manager = PositionManager(total_capital, max_positions, capital_per_position)
    entry_exit = SmartEntryExit(lookback_period=500, min_warmup=min_warmup)
    
    completed_trades = []
    
    print(f"⏳ Warming up (need {min_warmup} data points before trading)...")
    
    # Iterate through data
    for idx in range(len(df)):
        row = df.iloc[idx]
        
        # CHECK EXITS for all open positions
        positions_to_close = []
        
        for position in manager.positions:
            should_exit, exit_reason, current_pnl = entry_exit.should_exit(
                position, row, spot_fee, fut_fee,
                min_profit_pct, trailing_stop_pct
            )
            
            if should_exit:
                # Calculate final execution prices
                entry_spot_cost = position.entry_spot_ask * (1 + spot_fee)
                entry_fut_receive = position.entry_fut_bid * (1 - fut_fee)
                exit_spot_receive = row['spot_bid_price'] * (1 - spot_fee)
                exit_fut_cost = row['fut_ask_price'] * (1 + fut_fee)
                
                spot_pnl = exit_spot_receive - entry_spot_cost
                fut_pnl = entry_fut_receive - exit_fut_cost
                total_pnl = spot_pnl + fut_pnl
                net_pnl_pct = current_pnl
                
                hours_held = (row.name - position.entry_time).total_seconds() / 3600
                
                exit_cost_pct = ((row['fut_ask_price'] - row['spot_bid_price']) / 
                                row['fut_ask_price']) * 100
                spread_improvement = position.entry_spread_pct - exit_cost_pct
                
                completed_trades.append({
                    'position_id': position.position_id,
                    'entry_time': position.entry_time,
                    'exit_time': row.name,
                    'hours': hours_held,
                    'entry_spot_ask': position.entry_spot_ask,
                    'entry_fut_bid': position.entry_fut_bid,
                    'exit_spot_bid': row['spot_bid_price'],
                    'exit_fut_ask': row['fut_ask_price'],
                    'spot_pnl_pts': spot_pnl,
                    'fut_pnl_pts': fut_pnl,
                    'total_pnl_pts': total_pnl,
                    'net_pnl_pct': net_pnl_pct,
                    'entry_spread_pct': position.entry_spread_pct,
                    'entry_spread_zscore': position.entry_spread_zscore,
                    'exit_spread_pct': exit_cost_pct,
                    'spread_improvement': spread_improvement,
                    'max_pnl_seen': position.max_pnl_seen,
                    'capital_allocated': position.capital_allocated,
                    'exit_reason': exit_reason
                })
                
                positions_to_close.append(position)
        
        # Close positions
        for position in positions_to_close:
            manager.close_position(position)
        
        # CHECK ENTRY for new positions
        should_enter, stats = entry_exit.should_enter(
            df, idx, entry_zscore_threshold, max_entry_cost
        )
        
        if idx == min_warmup:
            print(f"✅ Warmup complete! Starting to look for trades at index {idx}")
        
        if should_enter and stats:
            position = manager.open_position(
                entry_time=row.name,
                entry_spot_ask=row['spot_ask_price'],
                entry_fut_bid=row['fut_bid_price'],
                entry_spread_pct=stats['current'],
                entry_spread_zscore=stats['zscore']
            )
            
            if position:
                print(f"✅ Opened position #{position.position_id} at {row.name} | "
                      f"Spread: {stats['current']:.4f}% (z={stats['zscore']:.2f}) | "
                      f"Open positions: {manager.get_position_count()}")
    
    return completed_trades


def print_multi_position_summary(trades: List[Dict]):
    """Print comprehensive summary of multi-position backtest"""
    if not trades:
        print("\n❌ No trades executed")
        print("\nPossible reasons:")
        print("  1. Entry criteria too strict (try entry_zscore_threshold=-0.5)")
        print("  2. Not enough data points (need 100+ for warmup)")
        print("  3. Spreads never favorable enough")
        return
    
    df = pd.DataFrame(trades)
    
    print(f"\n{'='*180}")
    print(f"MULTI-POSITION BACKTEST SUMMARY")
    print(f"{'='*180}")
    
    winning = df[df['net_pnl_pct'] > 0]
    losing = df[df['net_pnl_pct'] <= 0]
    
    print(f"\n📊 OVERALL PERFORMANCE:")
    print(f"{'Total trades:':<30} {len(df)}")
    print(f"{'Winning trades:':<30} {len(winning)} ({len(winning)/len(df)*100:.1f}%)")
    print(f"{'Losing trades:':<30} {len(losing)} ({len(losing)/len(df)*100:.1f}%)")
    print(f"{'Average P&L:':<30} {df['net_pnl_pct'].mean():.4f}%")
    print(f"{'Total P&L:':<30} {df['net_pnl_pct'].sum():.4f}%")
    print(f"{'Best trade:':<30} {df['net_pnl_pct'].max():.4f}%")
    print(f"{'Worst trade:':<30} {df['net_pnl_pct'].min():.4f}%")
    print(f"{'Avg duration:':<30} {df['hours'].mean():.2f} hours")
    
    print(f"\n📈 ENTRY QUALITY:")
    print(f"{'Avg entry spread:':<30} {df['entry_spread_pct'].mean():.4f}%")
    print(f"{'Avg entry z-score:':<30} {df['entry_spread_zscore'].mean():.2f}")
    print(f"{'Avg spread improvement:':<30} {df['spread_improvement'].mean():.4f}%")
    
    print(f"\n🎯 EXIT REASONS:")
    for reason, count in df['exit_reason'].value_counts().items():
        subset = df[df['exit_reason'] == reason]
        print(f"  {reason:<20} {count:>3} trades  "
              f"(avg P&L: {subset['net_pnl_pct'].mean():>7.4f}%, "
              f"win rate: {(subset['net_pnl_pct'] > 0).mean()*100:.1f}%)")
    
    print(f"\n📋 SAMPLE TRADES (first 5 and last 5):")
    print(f"{'-'*180}")
    print(f"{'ID':<4} {'Entry':<20} {'Exit':<20} "
          f"{'Entry Spread':<13} {'Z-Score':<9} "
          f"{'Exit Spread':<13} {'Improvement':<13} "
          f"{'P&L %':<10} {'Hrs':<6} {'Reason':<15}")
    print(f"{'-'*180}")
    
    sample = pd.concat([df.head(5), df.tail(5)]) if len(df) > 10 else df
    
    for _, t in sample.iterrows():
        marker = '✅' if t['net_pnl_pct'] > 0 else '❌'
        print(f"{t['position_id']:<4} {str(t['entry_time']):<20} {str(t['exit_time']):<20} "
              f"{t['entry_spread_pct']:>12.4f}% {t['entry_spread_zscore']:>8.2f} "
              f"{t['exit_spread_pct']:>12.4f}% {t['spread_improvement']:>12.4f}% "
              f"{marker} {t['net_pnl_pct']:<8.4f} {t['hours']:<6.2f} {t['exit_reason']:<15}")
    
    print(f"{'='*180}\n")


async def main():
    symbol = Symbol(base=AssetName("HIFI"), quote=AssetName("USDT"))
    date_to = datetime.datetime.utcnow()
    date_from = date_to - datetime.timedelta(hours=8)
    
    print(f"{'='*80}")
    print(f"MULTI-POSITION DELTA-NEUTRAL ARBITRAGE (FIXED)")
    print(f"{'='*80}")
    print(f"Symbol: {symbol.base}/{symbol.quote}")
    print(f"Period: {date_from} to {date_to}")
    print(f"{'='*80}\n")
    
    print("📥 Loading market data...")
    df = await load_market_data(symbol, date_from, date_to)
    print(f"✅ Loaded {len(df)} data points\n")
    
    print("🚀 Running multi-position backtest...")
    print(f"   Max positions: 5")
    print(f"   Capital per position: 20% ($2000)")
    print(f"   Entry z-score threshold: -1.0 (1 std below mean)")
    print(f"   Min profit target: 0.1%")
    print(f"   Warmup period: 100 data points\n")
    
    trades = multi_position_backtest(
        df,
        total_capital=10000.0,
        max_positions=5,
        capital_per_position=0.2,
        entry_zscore_threshold=-1.0,  # Try -0.5 if no trades
        max_entry_cost=0.5,
        min_profit_pct=0.1,
        trailing_stop_pct=0.05,
        spot_fee=0.0005,
        fut_fee=0.0005,
        min_warmup=100
    )
    
    print_multi_position_summary(trades)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
