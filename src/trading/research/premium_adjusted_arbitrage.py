"""
Premium-Adjusted Delta-Neutral Arbitrage

Key insight: Market has a persistent premium/basis.
Only trade when spread deviates significantly from the average premium.
"""

import datetime
from typing import Optional, List, Dict
from dataclasses import dataclass
import numpy as np

from exchanges.structs import Symbol, AssetName
from trading.research.trading_utlis import load_market_data
import pandas as pd

pd.set_option('display.precision', 10)
pd.set_option('display.float_format', None)


@dataclass
class Position:
    position_id: int
    entry_time: pd.Timestamp
    entry_spot_ask: float
    entry_fut_bid: float
    entry_spread_pct: float
    expected_exit_spread: float  # Based on mean premium
    max_pnl_seen: float = -float('inf')


def calculate_market_premium(df: pd.DataFrame, lookback: int = 500) -> Dict:
    """
    Calculate the persistent market premium/basis.
    
    Returns statistics about the spread behavior.
    """
    # Entry spread (what we pay to enter)
    df['entry_spread'] = df['spot_ask_price'] - df['fut_bid_price']
    df['entry_spread_pct'] = (df['entry_spread'] / df['spot_ask_price']) * 100
    
    # Exit spread (what we pay to exit)
    df['exit_spread'] = df['fut_ask_price'] - df['spot_bid_price']
    df['exit_spread_pct'] = (df['exit_spread'] / df['fut_ask_price']) * 100
    
    # Rolling statistics
    df['entry_spread_mean'] = df['entry_spread_pct'].rolling(lookback, min_periods=50).mean()
    df['entry_spread_std'] = df['entry_spread_pct'].rolling(lookback, min_periods=50).std()
    df['exit_spread_mean'] = df['exit_spread_pct'].rolling(lookback, min_periods=50).mean()
    df['exit_spread_std'] = df['exit_spread_pct'].rolling(lookback, min_periods=50).std()
    
    # Deviation from mean (z-score)
    df['entry_zscore'] = ((df['entry_spread_pct'] - df['entry_spread_mean']) / 
                          (df['entry_spread_std'] + 1e-10))
    
    return {
        'mean_entry_spread': df['entry_spread_pct'].mean(),
        'mean_exit_spread': df['exit_spread_pct'].mean(),
        'entry_std': df['entry_spread_pct'].std(),
        'exit_std': df['exit_spread_pct'].std(),
        'avg_premium': (df['entry_spread_pct'].mean() + df['exit_spread_pct'].mean()) / 2
    }


def premium_adjusted_backtest(
    df: pd.DataFrame,
    total_capital: float = 10000.0,
    max_positions: int = 3,
    entry_zscore_threshold: float = -2.0,  # Enter when spread is 2 std below mean
    min_expected_profit: float = 0.15,     # Need 0.15% expected profit after costs
    min_profit_pct: float = 0.1,
    max_loss_pct: float = -0.3,
    max_hours: float = 6,
    spot_fee: float = 0.0005,
    fut_fee: float = 0.0005,
    lookback: int = 500
) -> List[Dict]:
    """
    Trade only when spread deviates significantly from the market premium.
    
    Logic:
    1. Calculate rolling average premium
    2. Enter when entry spread is much lower than normal (z-score < -2)
    3. Expected exit spread = mean exit spread
    4. Only enter if expected profit > threshold
    """
    
    # Calculate premium statistics
    stats = calculate_market_premium(df, lookback)
    
    print(f"\n📊 MARKET PREMIUM ANALYSIS:")
    print(f"{'Mean entry spread:':<30} {stats['mean_entry_spread']:.4f}%")
    print(f"{'Mean exit spread:':<30} {stats['mean_exit_spread']:.4f}%")
    print(f"{'Average premium:':<30} {stats['avg_premium']:.4f}%")
    print(f"{'Entry std dev:':<30} {stats['entry_std']:.4f}%")
    print(f"{'Exit std dev:':<30} {stats['exit_std']:.4f}%")
    
    # Expected round-trip cost
    expected_cost = stats['mean_entry_spread'] + stats['mean_exit_spread']
    fees = (spot_fee + fut_fee) * 2 * 100  # 0.20%
    total_expected_cost = expected_cost + fees
    
    print(f"\n💰 EXPECTED COSTS:")
    print(f"{'Entry spread (avg):':<30} {stats['mean_entry_spread']:.4f}%")
    print(f"{'Exit spread (avg):':<30} {stats['mean_exit_spread']:.4f}%")
    print(f"{'Fees (round-trip):':<30} {fees:.4f}%")
    print(f"{'Total expected cost:':<30} {total_expected_cost:.4f}%")
    print(f"{'Min profit needed:':<30} {min_expected_profit:.4f}%")
    
    positions: List[Position] = []
    completed_trades = []
    next_id = 1
    
    trades_considered = 0
    trades_rejected_zscore = 0
    trades_rejected_expected_profit = 0
    
    for idx in range(lookback, len(df)):
        row = df.iloc[idx]
        
        # CHECK EXITS
        positions_to_close = []
        
        for pos in positions:
            # Calculate current P&L
            entry_spot_cost = pos.entry_spot_ask * (1 + spot_fee)
            entry_fut_receive = pos.entry_fut_bid * (1 - fut_fee)
            
            exit_spot_receive = row['spot_bid_price'] * (1 - spot_fee)
            exit_fut_cost = row['fut_ask_price'] * (1 + fut_fee)
            
            entry_net = entry_fut_receive - entry_spot_cost
            exit_net = exit_spot_receive - exit_fut_cost
            total_pnl = entry_net + exit_net
            
            pnl_pct = (total_pnl / entry_spot_cost) * 100
            
            if pnl_pct > pos.max_pnl_seen:
                pos.max_pnl_seen = pnl_pct
            
            hours_held = (row.name - pos.entry_time).total_seconds() / 3600
            
            # EXIT CONDITIONS
            exit_now = False
            exit_reason = ''
            
            if pnl_pct >= min_profit_pct:
                exit_now = True
                exit_reason = 'profit_target'
            elif pnl_pct <= max_loss_pct:
                exit_now = True
                exit_reason = 'stop_loss'
            elif hours_held >= max_hours:
                exit_now = True
                exit_reason = 'timeout'
            
            if exit_now:
                current_exit_spread_pct = row['exit_spread_pct']
                
                completed_trades.append({
                    'position_id': pos.position_id,
                    'entry_time': pos.entry_time,
                    'exit_time': row.name,
                    'hours': hours_held,
                    'entry_spread_pct': pos.entry_spread_pct,
                    'exit_spread_pct': current_exit_spread_pct,
                    'expected_exit_spread': pos.expected_exit_spread,
                    'exit_surprise': current_exit_spread_pct - pos.expected_exit_spread,
                    'pnl_pct': pnl_pct,
                    'max_pnl_seen': pos.max_pnl_seen,
                    'exit_reason': exit_reason
                })
                
                positions_to_close.append(pos)
        
        for pos in positions_to_close:
            positions.remove(pos)
        
        # CHECK ENTRY
        if len(positions) < max_positions:
            trades_considered += 1
            
            entry_spread_pct = row['entry_spread_pct']
            entry_zscore = row['entry_zscore']
            entry_mean = row['entry_spread_mean']
            exit_mean = row['exit_spread_mean']
            
            # Skip if not enough data
            if pd.isna(entry_zscore) or pd.isna(exit_mean):
                continue
            
            # FILTER 1: Entry spread must be significantly below average (z-score < -2)
            if entry_zscore >= entry_zscore_threshold:
                trades_rejected_zscore += 1
                continue
            
            # FILTER 2: Calculate expected profit
            # Entry advantage = how much better than average
            entry_advantage = entry_mean - entry_spread_pct
            
            # Expected exit cost = average exit spread
            expected_exit_spread = exit_mean
            
            # Expected gross profit = entry advantage - exit cost
            expected_gross_profit = entry_advantage - expected_exit_spread
            
            # Expected net profit = gross profit - fees
            expected_net_profit = expected_gross_profit - fees
            
            if expected_net_profit < min_expected_profit:
                trades_rejected_expected_profit += 1
                continue
            
            # ENTER POSITION
            pos = Position(
                position_id=next_id,
                entry_time=row.name,
                entry_spot_ask=row['spot_ask_price'],
                entry_fut_bid=row['fut_bid_price'],
                entry_spread_pct=entry_spread_pct,
                expected_exit_spread=expected_exit_spread
            )
            positions.append(pos)
            next_id += 1
            
            print(f"✅ Position #{pos.position_id} at {row.name}")
            print(f"   Entry spread: {entry_spread_pct:.4f}% (z={entry_zscore:.2f})")
            print(f"   Entry advantage: {entry_advantage:.4f}%")
            print(f"   Expected exit: {expected_exit_spread:.4f}%")
            print(f"   Expected profit: {expected_net_profit:.4f}%")
            print(f"   Positions: {len(positions)}\n")
    
    print(f"\n📈 ENTRY FILTERING:")
    print(f"{'Opportunities considered:':<30} {trades_considered}")
    print(f"{'Rejected (z-score):':<30} {trades_rejected_zscore}")
    print(f"{'Rejected (expected profit):':<30} {trades_rejected_expected_profit}")
    print(f"{'Positions entered:':<30} {len(completed_trades)}")
    
    return completed_trades


def print_results(trades: List[Dict]):
    if not trades:
        print("\n❌ NO TRADES - Entry criteria too strict")
        print("\nTry:")
        print("  1. Lower entry_zscore_threshold (e.g., -1.5 instead of -2.0)")
        print("  2. Lower min_expected_profit (e.g., 0.10% instead of 0.15%)")
        return
    
    df = pd.DataFrame(trades)
    
    print(f"\n{'='*100}")
    print(f"RESULTS")
    print(f"{'='*100}")
    
    winning = df[df['pnl_pct'] > 0]
    
    print(f"\n📊 PERFORMANCE:")
    print(f"{'Total trades:':<30} {len(df)}")
    print(f"{'Win rate:':<30} {len(winning)/len(df)*100:.1f}%")
    print(f"{'Average P&L:':<30} {df['pnl_pct'].mean():.4f}%")
    print(f"{'Total P&L:':<30} {df['pnl_pct'].sum():.4f}%")
    print(f"{'Best:':<30} {df['pnl_pct'].max():.4f}%")
    print(f"{'Worst:':<30} {df['pnl_pct'].min():.4f}%")
    
    print(f"\n📈 SPREAD ANALYSIS:")
    print(f"{'Avg entry spread:':<30} {df['entry_spread_pct'].mean():.4f}%")
    print(f"{'Avg exit spread:':<30} {df['exit_spread_pct'].mean():.4f}%")
    print(f"{'Avg expected exit:':<30} {df['expected_exit_spread'].mean():.4f}%")
    print(f"{'Avg exit surprise:':<30} {df['exit_surprise'].mean():.4f}%")
    
    print(f"\n🎯 EXIT REASONS:")
    for reason in df['exit_reason'].unique():
        subset = df[df['exit_reason'] == reason]
        print(f"  {reason:<20} {len(subset)} trades (avg: {subset['pnl_pct'].mean():.4f}%)")


async def main():
    symbol = Symbol(base=AssetName("F"), quote=AssetName("USDT"))
    date_to = datetime.datetime.utcnow()
    date_from = date_to - datetime.timedelta(hours=8)
    
    print(f"{'='*80}")
    print(f"PREMIUM-ADJUSTED DELTA-NEUTRAL ARBITRAGE")
    print(f"{'='*80}")
    
    df = await load_market_data(symbol, date_from, date_to)
    print(f"✅ Loaded {len(df)} data points")
    
    trades = premium_adjusted_backtest(
        df,
        total_capital=10000.0,
        max_positions=3,
        entry_zscore_threshold=-2.0,  # Very selective
        min_expected_profit=0.15,     # Need 0.15% expected profit
        min_profit_pct=0.1,
        max_loss_pct=-0.3,
        spot_fee=0.0005,
        fut_fee=0.0005
    )
    
    print_results(trades)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
