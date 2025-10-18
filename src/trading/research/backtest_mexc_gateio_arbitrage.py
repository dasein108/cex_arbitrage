"""
Cross-Exchange Arbitrage Backtest: MEXC Spot to GATEIO Futures

Strategy Overview:
1. Buy spot on MEXC when ask price is favorable
2. Simultaneously hedge with short futures position on GATEIO_FUTURES  
3. (Manual transfer of asset from MEXC to GATEIO_SPOT - not automated)
4. Sell spot on GATEIO_SPOT and close futures position on GATEIO_FUTURES
5. Profit from permanent price discrepancy where MEXC ask < GATEIO bid

This backtest accounts for:
- MEXC spot fees (maker/taker)
- GATEIO futures fees (maker/taker) 
- Funding rate costs during holding period
- Slippage estimates
- Realistic hedging ratios and position management
"""

import datetime
from typing import Optional, List, Dict
from dataclasses import dataclass, field
import pandas as pd
import numpy as np

from exchanges.structs import Symbol, AssetName
from trading.research.trading_utlis import load_market_data

# Set pandas display options for better precision
pd.set_option('display.precision', 10)
pd.set_option('display.float_format', None)

# Exchange fee schedules (as of October 2025)
MEXC_SPOT_FEES = {
    'maker': 0.0000,  # 0% maker fee for spot
    'taker': 0.0005   # 0.05% taker fee for spot
}

GATEIO_FUTURES_FEES = {
    'maker': 0.0002,  # 0.02% maker fee for futures
    'taker': 0.0005   # 0.05% taker fee for futures
}

GATEIO_SPOT_FEES = {
    'maker': 0.001,  # 0.02% maker fee for futures
    'taker': 0.001   # 0.05% taker fee for futures
}

# Funding rate assumptions (8-hour funding periods)
FUNDING_RATE_8H = 0.0001  # 0.01% per 8-hour period (conservative estimate)
FUNDING_PERIODS_PER_DAY = 3  # 8-hour periods


@dataclass
class CrossExchangePosition:
    """Track cross-exchange arbitrage position with hedging"""
    entry_time: pd.Timestamp
    
    # Entry prices and quantities
    mexc_spot_ask: float  # Price we pay to buy spot on MEXC
    mexc_spot_quantity: float  # Quantity bought on MEXC spot
    
    gateio_futures_bid: float  # Price we receive for short futures on GATEIO
    gateio_futures_quantity: float  # Quantity shorted on GATEIO futures (hedge ratio)
    
    # Calculated metrics
    entry_spread_bps: float = 0.0  # Entry spread in basis points
    hedge_ratio: float = 1.0  # Hedge ratio (typically 1.0 for delta neutral)
    
    # Cost tracking
    mexc_spot_fee_paid: float = 0.0
    gateio_futures_fee_paid: float = 0.0
    total_entry_cost: float = 0.0


@dataclass
class TradeResult:
    """Complete trade result with all costs and P&L breakdown"""
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    duration_hours: float
    
    # Entry details
    mexc_spot_entry_price: float
    mexc_spot_quantity: float
    gateio_futures_entry_price: float
    gateio_futures_quantity: float
    
    # Exit details  
    mexc_spot_exit_price: float  # Price received when selling on MEXC (if no transfer)
    gateio_spot_exit_price: float  # Price received when selling on GATEIO spot
    gateio_futures_exit_price: float  # Price paid to close futures position
    
    # Fee breakdown
    mexc_spot_entry_fee: float
    mexc_spot_exit_fee: float
    gateio_futures_entry_fee: float
    gateio_futures_exit_fee: float
    funding_rate_cost: float
    
    # P&L breakdown
    spot_pnl_mexc: float  # P&L from MEXC spot leg
    spot_pnl_gateio: float  # P&L from GATEIO spot leg (after transfer)
    futures_pnl: float  # P&L from GATEIO futures hedge
    total_fees: float
    net_pnl: float
    net_pnl_pct: float
    
    # Trade metadata
    entry_spread_bps: float
    exit_spread_bps: float
    exit_reason: str


def calculate_funding_cost(quantity: float, hours_held: float, funding_rate_8h: float = FUNDING_RATE_8H) -> float:
    """
    Calculate funding rate cost for holding futures position.
    
    Args:
        quantity: Futures position size
        hours_held: Hours position was held
        funding_rate_8h: 8-hour funding rate (default 0.01%)
    
    Returns:
        Total funding cost (positive = cost, negative = rebate)
    """
    funding_periods = hours_held / 8.0  # Number of 8-hour periods
    return quantity * funding_rate_8h * funding_periods


def calculate_slippage_cost(price: float, quantity: float, slippage_bps: float = 1.0) -> float:
    """
    Calculate estimated slippage cost.
    
    Args:
        price: Execution price
        quantity: Trade quantity  
        slippage_bps: Slippage in basis points (default 1 bps)
    
    Returns:
        Slippage cost in quote currency
    """
    return price * quantity * (slippage_bps / 10000.0)


def mexc_gateio_arbitrage_backtest(
    df: pd.DataFrame,
    min_entry_spread_bps: float = 50.0,  # Minimum spread to enter (5 bps)
    max_exit_spread_bps: float = 10.0,   # Maximum spread to exit (1 bps)
    max_holding_hours: float = 24.0,     # Maximum holding period
    position_size_usd: float = 1000.0,   # Position size in USD
    hedge_ratio: float = 1.0,            # Hedge ratio (1.0 = fully hedged)
    use_transfer_strategy: bool = True,   # True = transfer to GATEIO, False = close on MEXC
    slippage_bps: float = 1.0            # Slippage assumption in basis points
) -> List[TradeResult]:
    """
    Backtest cross-exchange arbitrage strategy.
    
    Strategy:
    1. Entry: Buy MEXC spot + Short GATEIO futures when spread > min_entry_spread_bps
    2. Exit: Close positions when spread < max_exit_spread_bps OR timeout
    3. Transfer: Optionally model asset transfer from MEXC to GATEIO
    
    Args:
        df: Market data with spot_ask_price, spot_bid_price, fut_ask_price, fut_bid_price
        min_entry_spread_bps: Minimum spread to enter position (basis points)
        max_exit_spread_bps: Maximum spread to maintain position (basis points) 
        max_holding_hours: Maximum hours to hold position
        position_size_usd: Position size in USD
        hedge_ratio: Hedge ratio for futures position
        use_transfer_strategy: Whether to model transfer to GATEIO spot
        slippage_bps: Slippage assumption
    
    Returns:
        List of TradeResult objects
    """
    trades = []
    position: Optional[CrossExchangePosition] = None
    
    for idx, row in df.iterrows():
        
        # =================================================================
        # ENTRY LOGIC: Look for favorable spread opportunities
        # =================================================================
        if position is None:
            # Calculate spread: MEXC ask vs GATEIO futures bid
            mexc_ask = row['spot_ask_price']
            gateio_fut_bid = row['fut_bid_price'] 
            
            # Spread in basis points (positive = opportunity)
            spread_bps = ((gateio_fut_bid - mexc_ask) / mexc_ask) * 10000
            
            # Enter if spread is favorable
            if spread_bps >= min_entry_spread_bps:
                # Calculate position sizes
                spot_quantity = position_size_usd / mexc_ask
                futures_quantity = spot_quantity * hedge_ratio
                
                # Calculate entry fees
                mexc_fee = mexc_ask * spot_quantity * MEXC_SPOT_FEES['taker']
                gateio_fee = gateio_fut_bid * futures_quantity * GATEIO_FUTURES_FEES['taker']
                
                position = CrossExchangePosition(
                    entry_time=idx,
                    mexc_spot_ask=mexc_ask,
                    mexc_spot_quantity=spot_quantity,
                    gateio_futures_bid=gateio_fut_bid,
                    gateio_futures_quantity=futures_quantity,
                    entry_spread_bps=spread_bps,
                    hedge_ratio=hedge_ratio,
                    mexc_spot_fee_paid=mexc_fee,
                    gateio_futures_fee_paid=gateio_fee,
                    total_entry_cost=mexc_fee + gateio_fee
                )
        
        # =================================================================
        # EXIT LOGIC: Close positions when conditions are met
        # =================================================================
        else:
            hours_held = (idx - position.entry_time).total_seconds() / 3600
            
            # Calculate current spread for exit decision
            mexc_bid = row['spot_bid_price'] 
            gateio_fut_ask = row['fut_ask_price']
            exit_spread_bps = ((mexc_bid - gateio_fut_ask) / gateio_fut_ask) * 10000
            
            # Exit conditions
            exit_now = False
            exit_reason = None
            
            # 1. Spread converged (profitable exit)
            if exit_spread_bps <= max_exit_spread_bps:
                exit_now = True
                exit_reason = 'spread_converged'
            
            # 2. Timeout (risk management)
            elif hours_held >= max_holding_hours:
                exit_now = True
                exit_reason = 'timeout'
            
            if exit_now:
                # =============================================================
                # EXECUTE EXIT AND CALCULATE P&L
                # =============================================================
                
                # Exit prices
                if use_transfer_strategy:
                    # Strategy: Transfer to GATEIO and sell there
                    gateio_spot_exit = row['spot_bid_price'] * 0.9995  # Assume GATEIO trades slightly lower
                    mexc_spot_exit = 0.0  # No sale on MEXC (transferred out)
                else:
                    # Strategy: Sell back on MEXC  
                    mexc_spot_exit = mexc_bid
                    gateio_spot_exit = 0.0  # No sale on GATEIO
                
                gateio_futures_exit = gateio_fut_ask
                
                # Calculate fees for exit
                if use_transfer_strategy:
                    mexc_exit_fee = 0.0  # No trading fee (just transfer fee, not modeled here)
                    gateio_spot_exit_fee = gateio_spot_exit * position.mexc_spot_quantity * MEXC_SPOT_FEES['taker']  # Use MEXC fee structure as proxy
                else:
                    mexc_exit_fee = mexc_spot_exit * position.mexc_spot_quantity * MEXC_SPOT_FEES['taker']
                    gateio_spot_exit_fee = 0.0
                
                gateio_futures_exit_fee = gateio_futures_exit * position.gateio_futures_quantity * GATEIO_FUTURES_FEES['taker']
                
                # Calculate funding cost (cost for short futures position)
                funding_cost = calculate_funding_cost(
                    position.gateio_futures_quantity, 
                    hours_held, 
                    FUNDING_RATE_8H
                )
                
                # Calculate slippage costs
                slippage_cost = (
                    calculate_slippage_cost(position.mexc_spot_ask, position.mexc_spot_quantity, slippage_bps) +
                    calculate_slippage_cost(gateio_futures_exit, position.gateio_futures_quantity, slippage_bps)
                )
                
                # P&L calculations
                # MEXC spot P&L (if selling on MEXC)
                if not use_transfer_strategy:
                    spot_pnl_mexc = (mexc_spot_exit - position.mexc_spot_ask) * position.mexc_spot_quantity - mexc_exit_fee
                else:
                    spot_pnl_mexc = -position.mexc_spot_ask * position.mexc_spot_quantity  # Cost of acquisition
                
                # GATEIO spot P&L (if transferring and selling on GATEIO)
                if use_transfer_strategy:
                    spot_pnl_gateio = gateio_spot_exit * position.mexc_spot_quantity - gateio_spot_exit_fee
                else:
                    spot_pnl_gateio = 0.0
                
                # GATEIO futures P&L (short position)
                futures_pnl = (position.gateio_futures_bid - gateio_futures_exit) * position.gateio_futures_quantity - gateio_futures_exit_fee
                
                # Total costs and P&L
                total_fees = (position.mexc_spot_fee_paid + position.gateio_futures_fee_paid + 
                             mexc_exit_fee + gateio_spot_exit_fee + gateio_futures_exit_fee + 
                             funding_cost + slippage_cost)
                
                net_pnl = spot_pnl_mexc + spot_pnl_gateio + futures_pnl - total_fees
                net_pnl_pct = (net_pnl / position_size_usd) * 100
                
                # Create trade result
                trade = TradeResult(
                    entry_time=position.entry_time,
                    exit_time=idx,
                    duration_hours=hours_held,
                    mexc_spot_entry_price=position.mexc_spot_ask,
                    mexc_spot_quantity=position.mexc_spot_quantity,
                    gateio_futures_entry_price=position.gateio_futures_bid,
                    gateio_futures_quantity=position.gateio_futures_quantity,
                    mexc_spot_exit_price=mexc_spot_exit,
                    gateio_spot_exit_price=gateio_spot_exit,
                    gateio_futures_exit_price=gateio_futures_exit,
                    mexc_spot_entry_fee=position.mexc_spot_fee_paid,
                    mexc_spot_exit_fee=mexc_exit_fee,
                    gateio_futures_entry_fee=position.gateio_futures_fee_paid,
                    gateio_futures_exit_fee=gateio_futures_exit_fee,
                    funding_rate_cost=funding_cost,
                    spot_pnl_mexc=spot_pnl_mexc,
                    spot_pnl_gateio=spot_pnl_gateio,
                    futures_pnl=futures_pnl,
                    total_fees=total_fees,
                    net_pnl=net_pnl,
                    net_pnl_pct=net_pnl_pct,
                    entry_spread_bps=position.entry_spread_bps,
                    exit_spread_bps=exit_spread_bps,
                    exit_reason=exit_reason
                )
                
                trades.append(trade)
                position = None
    
    return trades


def print_detailed_trade_analysis(trades: List[TradeResult], position_size_usd: float):
    """Print comprehensive trade analysis with cost breakdown."""
    if not trades:
        print("\n❌ No trades executed")
        return
    
    # Convert to DataFrame for analysis
    trade_data = []
    for trade in trades:
        trade_data.append({
            'entry_time': trade.entry_time,
            'exit_time': trade.exit_time,
            'duration_hours': trade.duration_hours,
            'net_pnl': trade.net_pnl,
            'net_pnl_pct': trade.net_pnl_pct,
            'total_fees': trade.total_fees,
            'funding_cost': trade.funding_rate_cost,
            'spot_pnl_mexc': trade.spot_pnl_mexc,
            'spot_pnl_gateio': trade.spot_pnl_gateio,
            'futures_pnl': trade.futures_pnl,
            'entry_spread_bps': trade.entry_spread_bps,
            'exit_spread_bps': trade.exit_spread_bps,
            'exit_reason': trade.exit_reason
        })
    
    df = pd.DataFrame(trade_data)
    
    print(f"\n{'=' * 120}")
    print(f"CROSS-EXCHANGE ARBITRAGE BACKTEST RESULTS")
    print(f"{'=' * 120}")
    print(f"Position Size: ${position_size_usd:,.2f} USD per trade")
    print(f"Total Trades: {len(trades)}")
    
    # Performance metrics
    winning_trades = df[df['net_pnl'] > 0]
    losing_trades = df[df['net_pnl'] <= 0]
    
    print(f"\n📊 PERFORMANCE SUMMARY:")
    print(f"{'Win Rate:':<25} {len(winning_trades)}/{len(df)} ({len(winning_trades)/len(df)*100:.1f}%)")
    print(f"{'Total P&L:':<25} ${df['net_pnl'].sum():.2f}")
    print(f"{'Average P&L:':<25} ${df['net_pnl'].mean():.2f} ({df['net_pnl_pct'].mean():.4f}%)")
    print(f"{'Best Trade:':<25} ${df['net_pnl'].max():.2f} ({df['net_pnl_pct'].max():.4f}%)")
    print(f"{'Worst Trade:':<25} ${df['net_pnl'].min():.2f} ({df['net_pnl_pct'].min():.4f}%)")
    print(f"{'Average Duration:':<25} {df['duration_hours'].mean():.2f} hours")
    print(f"{'Sharpe Ratio:':<25} {df['net_pnl_pct'].mean() / df['net_pnl_pct'].std():.2f}")
    
    # Cost breakdown
    print(f"\n💰 COST BREAKDOWN (Average per Trade):")
    print(f"{'Total Fees:':<25} ${df['total_fees'].mean():.4f} ({df['total_fees'].mean()/position_size_usd*100:.4f}%)")
    print(f"{'Funding Costs:':<25} ${df['funding_cost'].mean():.4f}")
    print(f"{'Fees as % of P&L:':<25} {(df['total_fees'].sum() / abs(df['net_pnl'].sum()) * 100):.2f}%")
    
    # P&L source analysis
    print(f"\n📈 P&L SOURCE ANALYSIS:")
    print(f"{'MEXC Spot P&L:':<25} ${df['spot_pnl_mexc'].sum():.2f}")
    print(f"{'GATEIO Spot P&L:':<25} ${df['spot_pnl_gateio'].sum():.2f}")
    print(f"{'GATEIO Futures P&L:':<25} ${df['futures_pnl'].sum():.2f}")
    print(f"{'Total Before Fees:':<25} ${(df['spot_pnl_mexc'] + df['spot_pnl_gateio'] + df['futures_pnl']).sum():.2f}")
    
    # Exit reason analysis
    print(f"\n🚪 EXIT REASON BREAKDOWN:")
    for reason, group in df.groupby('exit_reason'):
        avg_pnl = group['net_pnl_pct'].mean()
        win_rate = (group['net_pnl'] > 0).mean() * 100
        print(f"  {reason:<20} {len(group):>3} trades (avg: {avg_pnl:>7.4f}%, win: {win_rate:>5.1f}%)")
    
    # Spread analysis
    print(f"\n📏 SPREAD ANALYSIS:")
    print(f"{'Entry Spread (avg):':<25} {df['entry_spread_bps'].mean():.2f} bps")
    print(f"{'Exit Spread (avg):':<25} {df['exit_spread_bps'].mean():.2f} bps")
    print(f"{'Spread Capture:':<25} {(df['entry_spread_bps'] - df['exit_spread_bps']).mean():.2f} bps")
    
    # Detailed trade table
    print(f"\n{'=' * 120}")
    print(f"DETAILED TRADE LOG:")
    print(f"{'=' * 120}")
    print(f"{'#':<3} {'Entry Time':<20} {'Exit':<20} {'Dur(h)':<7} {'Entry':<8} {'Exit':<8} "
          f"{'P&L $':<10} {'P&L %':<8} {'Fees $':<8} {'Reason':<15}")
    print(f"{'-' * 120}")
    
    for i, trade in enumerate(trades, 1):
        status = '✅' if trade.net_pnl > 0 else '❌'
        print(f"{i:<3} {str(trade.entry_time):<20} {str(trade.exit_time):<20} "
              f"{trade.duration_hours:<7.2f} {trade.entry_spread_bps:<8.1f} {trade.exit_spread_bps:<8.1f} "
              f"{status} {trade.net_pnl:<8.2f} {trade.net_pnl_pct:<8.4f} {trade.total_fees:<8.4f} {trade.exit_reason:<15}")
    
    print(f"{'=' * 120}\n")


def analyze_market_data(df: pd.DataFrame):
    """Analyze market data to understand spread behavior."""
    print(f"📊 MARKET DATA ANALYSIS:")
    print(f"{'Data Points:':<25} {len(df)}")
    
    # Calculate spreads
    df['mexc_gateio_spread_bps'] = ((df['fut_bid_price'] - df['spot_ask_price']) / df['spot_ask_price']) * 10000
    df['reverse_spread_bps'] = ((df['spot_bid_price'] - df['fut_ask_price']) / df['fut_ask_price']) * 10000
    
    print(f"{'MEXC→GATEIO Spread:':<25} min={df['mexc_gateio_spread_bps'].min():.2f} bps, "
          f"max={df['mexc_gateio_spread_bps'].max():.2f} bps, "
          f"mean={df['mexc_gateio_spread_bps'].mean():.2f} bps")
    print(f"{'Reverse Spread:':<25} min={df['reverse_spread_bps'].min():.2f} bps, "
          f"max={df['reverse_spread_bps'].max():.2f} bps, "
          f"mean={df['reverse_spread_bps'].mean():.2f} bps")
    
    # Opportunity analysis
    favorable_mexc_gateio = (df['mexc_gateio_spread_bps'] > 15).sum()
    favorable_reverse = (df['reverse_spread_bps'] > 15).sum()
    
    print(f"{'Favorable MEXC→GATEIO:':<25} {favorable_mexc_gateio} times ({favorable_mexc_gateio/len(df)*100:.2f}%)")
    print(f"{'Favorable Reverse:':<25} {favorable_reverse} times ({favorable_reverse/len(df)*100:.2f}%)")
    
    # Price correlation analysis
    mexc_spot_mean = df['spot_ask_price'].mean()
    gateio_fut_mean = df['fut_bid_price'].mean()
    price_ratio = gateio_fut_mean / mexc_spot_mean
    
    print(f"{'MEXC Spot Mean:':<25} ${mexc_spot_mean:.6f}")
    print(f"{'GATEIO Futures Mean:':<25} ${gateio_fut_mean:.6f}")
    print(f"{'Price Ratio (G/M):':<25} {price_ratio:.6f}")
    print(f"{'Price Diff:':<25} {(price_ratio - 1) * 100:.4f}%")
    
    return df


async def main():
    """Main backtest execution."""
    symbol = Symbol(base=AssetName("F"), quote=AssetName("USDT"))
    
    # Use recent data period with known data availability
    date_to = datetime.datetime(2025, 10, 12, 9, 45, 0, tzinfo=datetime.timezone.utc)
    date_from = date_to - datetime.timedelta(hours=8)
    
    print(f"{'=' * 80}")
    print(f"CROSS-EXCHANGE ARBITRAGE BACKTEST")
    print(f"MEXC Spot → GATEIO Futures Arbitrage Strategy")
    print(f"{'=' * 80}")
    print(f"Symbol: {symbol.base}/{symbol.quote}")
    print(f"Period: {date_from} to {date_to}")
    print(f"Strategy: Buy MEXC Spot + Short GATEIO Futures")
    print(f"{'=' * 80}\n")
    
    # Load market data
    print("📥 Loading market data...")
    df = await load_market_data(symbol, date_from, date_to)
    print(f"✅ Loaded {len(df)} data points\n")
    
    # Analyze market data first
    df = analyze_market_data(df)
    print()
    
    # Run backtest with different parameter sets
    test_scenarios = [
        {
            'name': 'Conservative Strategy',
            'min_entry_spread_bps': 30.0,
            'max_exit_spread_bps': 5.0,
            'max_holding_hours': 12.0,
            'position_size_usd': 1000.0,
            'use_transfer_strategy': True
        },
        {
            'name': 'Aggressive Strategy', 
            'min_entry_spread_bps': 15.0,
            'max_exit_spread_bps': 2.0,
            'max_holding_hours': 24.0,
            'position_size_usd': 1000.0,
            'use_transfer_strategy': True
        },
        {
            'name': 'No Transfer Strategy',
            'min_entry_spread_bps': 25.0,
            'max_exit_spread_bps': 5.0,
            'max_holding_hours': 16.0,
            'position_size_usd': 1000.0,
            'use_transfer_strategy': False
        }
    ]
    
    for scenario in test_scenarios:
        print(f"\n🚀 Running {scenario['name']}...")
        print(f"   Entry Threshold: {scenario['min_entry_spread_bps']:.1f} bps")
        print(f"   Exit Threshold: {scenario['max_exit_spread_bps']:.1f} bps")
        print(f"   Max Holding: {scenario['max_holding_hours']:.1f} hours")
        print(f"   Transfer Strategy: {scenario['use_transfer_strategy']}")
        
        trades = mexc_gateio_arbitrage_backtest(
            df,
            min_entry_spread_bps=scenario['min_entry_spread_bps'],
            max_exit_spread_bps=scenario['max_exit_spread_bps'],
            max_holding_hours=scenario['max_holding_hours'],
            position_size_usd=scenario['position_size_usd'],
            use_transfer_strategy=scenario['use_transfer_strategy']
        )
        
        print(f"\n📊 {scenario['name']} Results:")
        print_detailed_trade_analysis(trades, scenario['position_size_usd'])


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())