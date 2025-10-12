"""
REVERSE Delta-Neutral Arbitrage: Short Spot, Long Futures

When spot is consistently more expensive than futures,
flip the strategy:
- Entry: SHORT spot (sell), LONG futures (buy)
- Exit: Buy back spot, Sell futures
"""

import datetime
from typing import List, Dict
from dataclasses import dataclass

from exchanges.structs import Symbol, AssetName
from trading.research.trading_utlis import load_market_data
import pandas as pd

pd.set_option('display.precision', 10)


@dataclass
class Position:
    position_id: int
    entry_time: pd.Timestamp
    entry_spot_bid: float  # We SELL spot at bid
    entry_fut_ask: float   # We BUY futures at ask
    entry_spread_pct: float
    max_pnl_seen: float = -float('inf')


def reverse_arbitrage_backtest(
    df: pd.DataFrame,
    total_capital: float = 10000.0,
    max_positions: int = 3,
    max_entry_spread: float = 0.5,  # Enter when spread < 0.5%
    min_profit_pct: float = 0.1,
    max_loss_pct: float = -0.3,
    max_hours: float = 6,
    spot_fee: float = 0.0005,
    fut_fee: float = 0.0005
) -> List[Dict]:
    """
    REVERSE strategy: Short spot, Long futures
    
    Entry: Sell spot at bid, Buy futures at ask
    Exit: Buy spot at ask, Sell futures at bid
    
    Profit when: Spread narrows (spot becomes less expensive)
    """
    
    # Calculate spreads for REVERSE strategy
    # Entry spread: Cost to enter (sell spot, buy futures)
    df['entry_spread'] = df['fut_ask_price'] - df['spot_bid_price']
    df['entry_spread_pct'] = (df['entry_spread'] / df['fut_ask_price']) * 100
    
    print(f"\n📊 REVERSE STRATEGY SPREAD ANALYSIS:")
    print(f"{'Entry spread range:':<30} {df['entry_spread_pct'].min():.4f}% to {df['entry_spread_pct'].max():.4f}%")
    print(f"{'Entry spread mean:':<30} {df['entry_spread_pct'].mean():.4f}%")
    print(f"{'Entry spread median:':<30} {df['entry_spread_pct'].median():.4f}%")
    
    positions: List[Position] = []
    completed_trades = []
    next_id = 1
    
    for idx, row in df.iterrows():
        # CHECK EXITS
        positions_to_close = []
        
        for pos in positions:
            # REVERSE P&L calculation
            # Entry: Sold spot at bid, Bought futures at ask (both with fees)
            entry_spot_receive = pos.entry_spot_bid * (1 - spot_fee)  # We receive from selling spot
            entry_fut_cost = pos.entry_fut_ask * (1 + fut_fee)         # We pay for buying futures
            
            # Exit: Buy spot at ask, Sell futures at bid (both with fees)
            exit_spot_cost = row['spot_ask_price'] * (1 + spot_fee)   # We pay to buy back spot
            exit_fut_receive = row['fut_bid_price'] * (1 - fut_fee)   # We receive from selling futures
            
            # Net P&L
            entry_net = entry_spot_receive - entry_fut_cost  # What we netted at entry
            exit_net = exit_fut_receive - exit_spot_cost     # What we net at exit
            total_pnl = entry_net + exit_net
            
            pnl_pct = (total_pnl / entry_fut_cost) * 100  # Relative to capital deployed
            
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
                exit_spread_pct = ((row['spot_ask_price'] - row['fut_bid_price']) / 
                                  row['spot_ask_price']) * 100
                
                completed_trades.append({
                    'position_id': pos.position_id,
                    'entry_time': pos.entry_time,
                    'exit_time': row.name,
                    'hours': hours_held,
                    'entry_spread_pct': pos.entry_spread_pct,
                    'exit_spread_pct': exit_spread_pct,
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
            
            # Enter when spread is LOW (cheap to enter)
            if entry_spread_pct <= max_entry_spread:
                pos = Position(
                    position_id=next_id,
                    entry_time=row.name,
                    entry_spot_bid=row['spot_bid_price'],
                    entry_fut_ask=row['fut_ask_price'],
                    entry_spread_pct=entry_spread_pct
                )
                positions.append(pos)
                next_id += 1
                
                if next_id <= 10 or next_id % 50 == 0:
                    print(f"✅ Position #{pos.position_id} at {row.name} | "
                          f"Spread: {entry_spread_pct:.4f}% | "
                          f"Positions: {len(positions)}")
    
    return completed_trades


def print_results(trades: List[Dict]):
    if not trades:
        print("\n❌ NO TRADES")
        return
    
    df = pd.DataFrame(trades)
    
    print(f"\n{'='*100}")
    print(f"REVERSE STRATEGY RESULTS")
    print(f"{'='*100}")
    
    winning = df[df['pnl_pct'] > 0]
    
    print(f"\n📊 PERFORMANCE:")
    print(f"{'Total trades:':<30} {len(df)}")
    print(f"{'Win rate:':<30} {len(winning)/len(df)*100:.1f}%")
    print(f"{'Average P&L:':<30} {df['pnl_pct'].mean():.4f}%")
    print(f"{'Total P&L:':<30} {df['pnl_pct'].sum():.4f}%")
    print(f"{'Best:':<30} {df['pnl_pct'].max():.4f}%")
    print(f"{'Worst:':<30} {df['pnl_pct'].min():.4f}%")
    
    print(f"\n🎯 EXIT REASONS:")
    for reason in df['exit_reason'].unique():
        subset = df[df['exit_reason'] == reason]
        print(f"  {reason:<20} {len(subset)} trades (avg: {subset['pnl_pct'].mean():.4f}%)")


async def main():
    symbol = Symbol(base=AssetName("F"), quote=AssetName("USDT"))
    date_to = datetime.datetime.utcnow()
    date_from = date_to - datetime.timedelta(hours=8)
    
    print(f"{'='*80}")
    print(f"REVERSE ARBITRAGE: SHORT SPOT, LONG FUTURES")
    print(f"{'='*80}")
    
    df = await load_market_data(symbol, date_from, date_to)
    print(f"✅ Loaded {len(df)} data points")
    
    trades = reverse_arbitrage_backtest(
        df,
        total_capital=10000.0,
        max_positions=3,
        max_entry_spread=0.5,
        min_profit_pct=0.1,
        max_loss_pct=-0.3,
        spot_fee=0.0005,
        fut_fee=0.0005
    )
    
    print_results(trades)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
