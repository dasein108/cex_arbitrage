import datetime
from typing import Optional
from dataclasses import dataclass, field

from exchanges.structs import Symbol, AssetName
from trading.research.trading_utlis import load_market_data
import pandas as pd

pd.set_option('display.precision', 10)
pd.set_option('display.float_format', None)


@dataclass
class Position:
    """Track open arbitrage position"""
    entry_time: pd.Timestamp
    entry_spot_ask: float
    entry_fut_bid: float
    entry_spread_pct: float = 0.0


def add_execution_calculations(df: pd.DataFrame,
                               spot_fee: float = 0.0005,
                               fut_fee: float = 0.0005) -> pd.DataFrame:
    """Calculate execution prices including fees"""
    df = df.copy()

    # Entry cost (what we pay to enter position)
    df['entry_cost_pct'] = ((df['spot_ask_price'] - df['fut_bid_price']) /
                            df['spot_ask_price']) * 100

    # Exit cost (what we pay to exit position)
    df['exit_cost_pct'] = ((df['fut_ask_price'] - df['spot_bid_price']) /
                           df['fut_ask_price']) * 100

    return df


def delta_neutral_backtest(
        df: pd.DataFrame,
        max_entry_cost_pct: float = 0.5,  # Only enter if cost < 0.5%
        min_profit_pct: float = 0.1,  # Exit when profit > 0.1%
        max_hours: float = 6,  # Timeout
        spot_fee: float = 0.0005,
        fut_fee: float = 0.0005
) -> list:
    """
    Delta-neutral backtest without stop-loss.

    Exit when:
    1. Profitable (spread converged)
    2. Timeout (spread not moving)

    NO STOP-LOSS because:
    - Delta-neutral = hedged against price moves
    - Losses only from spread widening
    - Stop-loss doesn't help with spread risk
    """
    trades = []
    position: Optional[Position] = None

    for idx, row in df.iterrows():

        # ==========================================
        # ENTRY: When spread is favorable
        # ==========================================
        if position is None:
            entry_cost_pct = ((row['spot_ask_price'] - row['fut_bid_price']) /
                              row['spot_ask_price']) * 100

            if entry_cost_pct < max_entry_cost_pct:
                position = Position(
                    entry_time=idx,
                    entry_spot_ask=row['spot_ask_price'],
                    entry_fut_bid=row['fut_bid_price'],
                    entry_spread_pct=entry_cost_pct
                )

        # ==========================================
        # EXIT: When profitable or timeout
        # ==========================================
        else:
            # Calculate actual P&L with fees
            entry_spot_cost = position.entry_spot_ask * (1 + spot_fee)
            entry_fut_receive = position.entry_fut_bid * (1 - fut_fee)
            exit_spot_receive = row['spot_bid_price'] * (1 - spot_fee)
            exit_fut_cost = row['fut_ask_price'] * (1 + fut_fee)

            # P&L in absolute points
            spot_pnl_pts = exit_spot_receive - entry_spot_cost
            fut_pnl_pts = entry_fut_receive - exit_fut_cost
            total_pnl_pts = spot_pnl_pts + fut_pnl_pts

            # P&L in percentage
            capital = entry_spot_cost
            net_pnl_pct = (total_pnl_pts / capital) * 100

            hours_held = (idx - position.entry_time).total_seconds() / 3600

            # Calculate current spreads
            exit_cost_pct = ((row['fut_ask_price'] - row['spot_bid_price']) /
                             row['fut_ask_price']) * 100
            spread_improvement = position.entry_spread_pct - exit_cost_pct

            # EXIT LOGIC
            exit_now = False
            exit_reason = None

            # 1. PROFIT TARGET: Exit when profitable
            if net_pnl_pct >= min_profit_pct:
                exit_now = True
                exit_reason = 'profit_target'

            # 2. TIMEOUT: Spread not converging
            elif hours_held >= max_hours:
                exit_now = True
                exit_reason = 'timeout'

            if exit_now:
                trades.append({
                    'entry_time': position.entry_time,
                    'exit_time': idx,
                    'hours': hours_held,
                    'entry_spot_ask': position.entry_spot_ask,
                    'entry_fut_bid': position.entry_fut_bid,
                    'exit_spot_bid': row['spot_bid_price'],
                    'exit_fut_ask': row['fut_ask_price'],
                    'spot_pnl_pts': spot_pnl_pts,
                    'fut_pnl_pts': fut_pnl_pts,
                    'total_pnl_pts': total_pnl_pts,
                    'net_pnl_pct': net_pnl_pct,
                    'entry_spread_pct': position.entry_spread_pct,
                    'exit_spread_pct': exit_cost_pct,
                    'spread_improvement': spread_improvement,
                    'exit_reason': exit_reason
                })

                position = None

    return trades


def print_trade_summary(trades: list):
    """Print trade analysis"""
    if not trades:
        print("\n❌ No trades executed")
        return

    df = pd.DataFrame(trades)

    print(f"\n{'=' * 160}")
    print(f"TRADE SUMMARY - {len(trades)} trades")
    print(f"{'=' * 160}")

    winning = df[df['net_pnl_pct'] > 0]
    losing = df[df['net_pnl_pct'] <= 0]

    print(f"\n📊 PERFORMANCE:")
    print(f"{'Win rate:':<25} {len(winning)}/{len(df)} ({len(winning) / len(df) * 100:.1f}%)")
    print(f"{'Average P&L:':<25} {df['net_pnl_pct'].mean():.4f}%")
    print(f"{'Total P&L:':<25} {df['net_pnl_pct'].sum():.4f}%")
    print(f"{'Best trade:':<25} {df['net_pnl_pct'].max():.4f}%")
    print(f"{'Worst trade:':<25} {df['net_pnl_pct'].min():.4f}%")
    print(f"{'Avg duration:':<25} {df['hours'].mean():.2f} hours")
    print(f"{'Avg spread improvement:':<25} {df['spread_improvement'].mean():.4f}%")

    print(f"\n📈 EXIT REASONS:")
    for reason, count in df['exit_reason'].value_counts().items():
        subset = df[df['exit_reason'] == reason]
        print(f"  {reason:<20} {count:>3} trades  "
              f"(avg P&L: {subset['net_pnl_pct'].mean():>7.4f}%, "
              f"win rate: {(subset['net_pnl_pct'] > 0).mean() * 100:.1f}%)")

    print(f"\n{'=' * 160}")
    print(f"DETAILED TRADES:")
    print(f"{'=' * 160}")
    print(f"{'#':<4} {'Entry':<20} {'Exit':<20} "
          f"{'Spot ↔ Fut Entry':<28} {'Spot ↔ Fut Exit':<28} "
          f"{'Spread':<18} {'P&L %':<10} {'Hrs':<6} {'Exit':<15}")
    print(f"{'-' * 160}")

    for i, t in enumerate(trades, 1):
        marker = '✅' if t['net_pnl_pct'] > 0 else '❌'
        print(f"{i:<4} {str(t['entry_time']):<20} {str(t['exit_time']):<20} "
              f"{t['entry_spot_ask']:.10f} ↔ {t['entry_fut_bid']:.10f} "
              f"{t['exit_spot_bid']:.10f} ↔ {t['exit_fut_ask']:.10f} "
              f"{t['entry_spread_pct']:>6.4f} → {t['exit_spread_pct']:>6.4f} "
              f"{marker} {t['net_pnl_pct']:<8.4f} {t['hours']:<6.2f} {t['exit_reason']:<15}")

    print(f"{'=' * 160}\n")


async def main():
    symbol = Symbol(base=AssetName("HIFI"), quote=AssetName("USDT"))
    date_to = datetime.datetime.utcnow()
    # date_to = datetime.datetime.fromisoformat("2025-10-12 06:17").replace(tzinfo=datetime.timezone.utc)  # For consistent testing

    date_from = date_to - datetime.timedelta(hours=8)

    print(f"{'=' * 80}")
    print(f"DELTA-NEUTRAL ARBITRAGE BACKTEST (No Stop-Loss)")
    print(f"{'=' * 80}")
    print(f"Symbol: {symbol.base}/{symbol.quote}")
    print(f"Period: {date_from} to {date_to}")
    print(f"{'=' * 80}\n")

    print("📥 Loading market data...")
    df = await load_market_data(symbol, date_from, date_to)
    df = add_execution_calculations(df)
    print(f"✅ Loaded {len(df)} data points\n")

    print("📊 SPREAD STATISTICS:")
    print(f"Entry cost: min={df['entry_cost_pct'].min():.4f}% "
          f"max={df['entry_cost_pct'].max():.4f}% "
          f"mean={df['entry_cost_pct'].mean():.4f}%")
    print(f"Exit cost:  min={df['exit_cost_pct'].min():.4f}% "
          f"max={df['exit_cost_pct'].max():.4f}% "
          f"mean={df['exit_cost_pct'].mean():.4f}%\n")

    print("🚀 Running backtest...\n")

    trades = delta_neutral_backtest(
        df,
        max_entry_cost_pct=0.5,  # Enter when cost < 0.5%
        min_profit_pct=0.1,  # Exit when profit > 0.1%
        max_hours=6,  # Timeout
        spot_fee=0.0005,
        fut_fee=0.0005
    )

    print_trade_summary(trades)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())