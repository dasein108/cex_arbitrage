"""
FIXED Delta-Neutral Arbitrage Strategy

Key fixes:
1. Only enter when entry spread is NEGATIVE (we get paid to enter)
2. Proper P&L calculation accounting for all costs
3. Realistic exit conditions
"""

import datetime
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass

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
    entry_spread: float  # Absolute spread in price
    max_pnl_seen: float = -float('inf')


def simple_delta_neutral_backtest(
    df: pd.DataFrame,
    total_capital: float = 10000.0,
    max_positions: int = 5,
    max_entry_spread: float = 0.0,  # Only enter when spread <= 0 (negative = we get paid)
    min_profit_pct: float = 0.1,
    max_loss_pct: float = -0.3,  # Stop loss at -0.3%
    max_hours: float = 6,
    spot_fee: float = 0.0005,
    fut_fee: float = 0.0005
) -> List[Dict]:
    """
    Simple backtest that only enters on PROFITABLE spreads.
    
    Entry: Only when fut_bid > spot_ask (we get paid to enter!)
    Exit: When profitable or stop loss
    """
    
    positions: List[Position] = []
    completed_trades = []
    next_id = 1
    capital_per_position = total_capital / max_positions
    
    # Calculate spreads
    df['entry_spread'] = df['spot_ask_price'] - df['fut_bid_price']
    df['entry_spread_pct'] = (df['entry_spread'] / df['spot_ask_price']) * 100
    
    print(f"\n📊 SPREAD ANALYSIS:")
    print(f"{'Entry spread range:':<30} {df['entry_spread_pct'].min():.4f}% to {df['entry_spread_pct'].max():.4f}%")
    print(f"{'Entry spread mean:':<30} {df['entry_spread_pct'].mean():.4f}%")
    print(f"{'Negative spreads (profitable):':<30} {(df['entry_spread_pct'] < 0).sum()} / {len(df)} ({(df['entry_spread_pct'] < 0).mean()*100:.1f}%)")
    
    if (df['entry_spread_pct'] < 0).sum() == 0:
        print("\n⚠️  WARNING: NO NEGATIVE SPREADS FOUND!")
        print("   This strategy CANNOT be profitable with this data.")
        print("   All entries will cost money.")
        return []
    
    for idx, row in df.iterrows():
        # CHECK EXITS
        positions_to_close = []
        
        for pos in positions:
            # Calculate current P&L
            entry_spot_cost = pos.entry_spot_ask * (1 + spot_fee)
            entry_fut_receive = pos.entry_fut_bid * (1 - fut_fee)
            
            exit_spot_receive = row['spot_bid_price'] * (1 - spot_fee)
            exit_fut_cost = row['fut_ask_price'] * (1 + fut_fee)
            
            # P&L = what we receive minus what we pay
            entry_net = entry_fut_receive - entry_spot_cost  # Negative if we paid
            exit_net = exit_spot_receive - exit_fut_cost     # Positive if we profit
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
                exit_spread_pct = ((row['fut_ask_price'] - row['spot_bid_price']) / 
                                  row['fut_ask_price']) * 100
                
                completed_trades.append({
                    'position_id': pos.position_id,
                    'entry_time': pos.entry_time,
                    'exit_time': row.name,
                    'hours': hours_held,
                    'entry_spread_pct': pos.entry_spread / pos.entry_spot_ask * 100,
                    'exit_spread_pct': exit_spread_pct,
                    'entry_net': entry_net,
                    'exit_net': exit_net,
                    'total_pnl': total_pnl,
                    'pnl_pct': pnl_pct,
                    'max_pnl_seen': pos.max_pnl_seen,
                    'exit_reason': exit_reason
                })
                
                positions_to_close.append(pos)
        
        for pos in positions_to_close:
            positions.remove(pos)
        
        # CHECK ENTRY
        if len(positions) < max_positions:
            entry_spread_pct = row['entry_spread_pct']
            
            # CRITICAL: Only enter when spread is NEGATIVE or very close to zero
            if entry_spread_pct <= max_entry_spread:
                pos = Position(
                    position_id=next_id,
                    entry_time=row.name,
                    entry_spot_ask=row['spot_ask_price'],
                    entry_fut_bid=row['fut_bid_price'],
                    entry_spread=row['entry_spread']
                )
                positions.append(pos)
                next_id += 1
                
                print(f"✅ Position #{pos.position_id} at {row.name} | "
                      f"Spread: {entry_spread_pct:.4f}% | "
                      f"Positions: {len(positions)}")
    
    return completed_trades


def print_results(trades: List[Dict]):
    if not trades:
        print("\n❌ NO TRADES - Strategy cannot be profitable with this data")
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
    
    print(f"\n📈 EXIT REASONS:")
    for reason in df['exit_reason'].unique():
        subset = df[df['exit_reason'] == reason]
        print(f"  {reason:<20} {len(subset)} trades (avg: {subset['pnl_pct'].mean():.4f}%)")


async def main():
    symbol = Symbol(base=AssetName("HIFI"), quote=AssetName("USDT"))
    date_to = datetime.datetime.utcnow()
    date_from = date_to - datetime.timedelta(hours=8)
    
    print(f"{'='*80}")
    print(f"FIXED DELTA-NEUTRAL ARBITRAGE")
    print(f"{'='*80}")
    
    df = await load_market_data(symbol, date_from, date_to)
    print(f"✅ Loaded {len(df)} data points")
    
    trades = simple_delta_neutral_backtest(
        df,
        total_capital=10000.0,
        max_positions=5,
        max_entry_spread=0.0,  # Only negative spreads
        min_profit_pct=0.1,
        max_loss_pct=-0.3,
        spot_fee=0.0005,
        fut_fee=0.0005
    )
    
    print_results(trades)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
