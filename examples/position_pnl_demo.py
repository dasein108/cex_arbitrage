#!/usr/bin/env python3
"""
Demo script showing how to use Position with PNL tracking integrated with exchange fees.

This example demonstrates:
1. Setting up position with exchange fee rates
2. Building a position in accumulate mode  
3. Switching to release mode and tracking PNL with fees
4. Both full and partial position closes
"""

from exchanges.structs.common import Side
from trading.strategies.implementations.base_strategy.unified_position import Position


def demo_position_pnl():
    """Demonstrate PNL tracking with fees."""
    print("=== Position PNL Demo ===\n")
    
    # Create position 
    position = Position()
    fee_rate = 0.001  # 0.1% taker fee (would come from exchange.fees[symbol].taker_fee)
    
    print(f"Initial position: {position}")
    print(f"Fee rate: {fee_rate * 100:.3f}%\n")
    
    # 1. Accumulate position (mode = 'accumulate' by default)
    print("1. Building position in accumulate mode...")
    change1 = position.update(Side.BUY, 100.0, 50.0)
    print(f"   Buy 100 @ $50.00: {change1}")
    
    change2 = position.update(Side.BUY, 50.0, 52.0)
    print(f"   Buy 50 @ $52.00: {change2}")
    print(f"   Current position: {position}")
    print(f"   Weighted avg price: ${position.price:.2f}\n")
    
    # 2. Switch to release mode for PNL tracking
    print("2. Switching to release mode for PNL tracking...")
    position.mode = 'release'
    
    # 3. Partial close with profit
    print("3. Partial close with profit...")
    change3 = position.update(Side.SELL, 80.0, 55.0, fee_rate)
    print(f"   Sell 80 @ $55.00: {change3}")
    
    if change3.has_pnl:
        print(f"   PNL Details:")
        print(f"   - Entry: ${change3.entry_price:.2f} | Exit: ${change3.exit_price:.2f} | Qty: {change3.close_quantity}")
        print(f"   - Raw PNL: ${change3.pnl_usdt:.2f} ({change3.pnl_pct:.2f}%)")
        print(f"   - Entry Fee: ${change3.entry_fee_usdt:.2f} | Exit Fee: ${change3.exit_fee_usdt:.2f}")
        print(f"   - Net PNL: ${change3.pnl_usdt_net:.2f} ({change3.pnl_pct_net:.2f}%)")
    
    print(f"   Remaining position: {position}\n")
    
    # 4. Complete close with loss
    print("4. Complete close at lower price...")
    change4 = position.update(Side.SELL, 70.0, 49.0, fee_rate)
    print(f"   Sell remaining 70 @ $49.00: {change4}")
    
    if change4.has_pnl:
        print(f"   PNL Details:")
        print(f"   - Entry: ${change4.entry_price:.2f} | Exit: ${change4.exit_price:.2f} | Qty: {change4.close_quantity}")
        print(f"   - Raw PNL: ${change4.pnl_usdt:.2f} ({change4.pnl_pct:.2f}%)")
        print(f"   - Entry Fee: ${change4.entry_fee_usdt:.2f} | Exit Fee: ${change4.exit_fee_usdt:.2f}")
        print(f"   - Net PNL: ${change4.pnl_usdt_net:.2f} ({change4.pnl_pct_net:.2f}%)")
    
    print(f"   Final position: {position}")
    print(f"   Last change: {change4.get_pnl_summary()}")
    
    # 5. Show cumulative PNL summary
    print("\\n5. Cumulative PNL Summary...")
    print(f"   {position.get_cumulative_pnl_summary()}")
    print(f"   Max position achieved: {position.max_position_qty}")
    print(f"   Position closed: {position.position_closed_percent:.1f}%")


def demo_hedge_mode():
    """Demonstrate hedge mode PNL tracking."""
    print("\n=== Hedge Mode Demo ===\n")
    
    position = Position()
    position.mode = 'hedge'
    fee_rate = 0.0015  # 0.15% fee
    
    print("1. Open hedge position...")
    change1 = position.update(Side.BUY, 200.0, 45.0)
    print(f"   Buy 200 @ $45.00: {change1}")
    
    print("2. Hedge with opposite position...")
    change2 = position.update(Side.SELL, 100.0, 47.0, fee_rate)
    print(f"   Sell 100 @ $47.00: {change2}")
    
    if change2.has_pnl:
        print(f"   Hedge PNL: ${change2.pnl_usdt_net:.2f} ({change2.pnl_pct_net:.2f}%)")
    
    print(f"   Remaining position: {position}")


def demo_integration_pattern():
    """Show how to integrate with CompositePrivateSpotExchange."""
    print("\n=== Integration Pattern ===\n")
    
    # This is how you would integrate with actual exchange:
    print("""
    # In your trading strategy:
    
    # 1. Get fee rate from exchange
    exchange = get_composite_implementation(mexc_config, is_private=True)
    symbol = Symbol(base=AssetName('BTC'), quote=AssetName('USDT'))
    fee_rate = exchange.fees[symbol].taker_fee
    
    # 2. Set up position
    position = Position()
    position.mode = 'release'  # Enable PNL tracking
    
    # 3. Update position on order fills with fee
    order = await exchange.place_order(symbol, Side.BUY, 100.0, 50000.0)
    change = position.update_position_with_order(order, fee_rate)
    
    # 4. Check for PNL on closes
    if change.has_pnl:
        print(f"Trade PNL: {change.pnl_usdt_net:.2f} USDT")
        # Log to database, send alerts, etc.
    """)


if __name__ == "__main__":
    demo_position_pnl()
    demo_hedge_mode()
    demo_integration_pattern()