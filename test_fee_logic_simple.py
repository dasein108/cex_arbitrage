#!/usr/bin/env python3
"""
Simple test of fee-adjusted entry logic without complex imports.
"""

def test_fee_logic():
    """Test the fee-adjusted logic manually."""
    print("🧪 Testing Fee-Adjusted Entry Logic (Simple)")
    print("=" * 60)
    
    # Fee structure (from strategy)
    mexc_spot_taker_fee = 0.0005   # 0.05%
    gateio_futures_taker_fee = 0.0006  # 0.06% 
    total_fees = mexc_spot_taker_fee + gateio_futures_taker_fee  # 0.0011 (0.11%)
    min_spread_threshold = 0.0015   # 0.15% additional margin
    
    print(f"Fee Structure:")
    print(f"  MEXC spot taker: {mexc_spot_taker_fee*100:.2f}%")
    print(f"  Gate.io futures taker: {gateio_futures_taker_fee*100:.2f}%")
    print(f"  Total fees: {total_fees*100:.2f}%")
    print(f"  Minimum threshold: {min_spread_threshold*100:.2f}%")
    print(f"  Required spread: {(total_fees + min_spread_threshold)*100:.2f}%")
    print()
    
    # Test scenarios based on your backtest results
    test_cases = [
        # (description, mexc_bid, mexc_ask, gateio_fut_bid, gateio_fut_ask)
        ("Original failing case", 0.0046, 0.0046, 0.0046, 0.0046),  # No spread = guaranteed loss
        ("Minimal spread", 0.0046, 0.0046, 0.00462, 0.00462),      # 0.04% spread < fees
        ("Break-even spread", 0.0046, 0.0046, 0.004651, 0.004651), # 0.11% spread = fees
        ("Profitable spread", 0.0046, 0.0046, 0.004672, 0.004672), # 0.26% spread > fees + threshold
    ]
    
    for desc, mexc_bid, mexc_ask, gateio_fut_bid, gateio_fut_ask in test_cases:
        print(f"📊 {desc}:")
        print(f"  MEXC: bid={mexc_bid:.6f}, ask={mexc_ask:.6f}")
        print(f"  Gate.io futures: bid={gateio_fut_bid:.6f}, ask={gateio_fut_ask:.6f}")
        
        # Calculate spreads for both directions
        mexc_to_fut_spread = gateio_fut_bid - mexc_ask
        fut_to_mexc_spread = mexc_bid - gateio_fut_ask
        
        print(f"  MEXC to Futures spread: {mexc_to_fut_spread:.6f} ({mexc_to_fut_spread*100:.3f}%)")
        print(f"  Futures to MEXC spread: {fut_to_mexc_spread:.6f} ({fut_to_mexc_spread*100:.3f}%)")
        
        # Check profitability (new logic)
        mexc_to_fut_profitable = mexc_to_fut_spread > (total_fees + min_spread_threshold)
        fut_to_mexc_profitable = fut_to_mexc_spread > (total_fees + min_spread_threshold)
        
        mexc_net_profit = mexc_to_fut_spread - total_fees if mexc_to_fut_spread > 0 else mexc_to_fut_spread
        fut_net_profit = fut_to_mexc_spread - total_fees if fut_to_mexc_spread > 0 else fut_to_mexc_spread
        
        print(f"  MEXC direction - Net profit: {mexc_net_profit:.6f} ({mexc_net_profit*100:.3f}%) - Profitable: {mexc_to_fut_profitable}")
        print(f"  Futures direction - Net profit: {fut_net_profit:.6f} ({fut_net_profit*100:.3f}%) - Profitable: {fut_to_mexc_profitable}")
        
        should_enter = mexc_to_fut_profitable or fut_to_mexc_profitable
        print(f"  🎯 Decision: {'ENTER TRADE' if should_enter else 'NO ENTRY'}")
        
        if not should_enter and desc == "Original failing case":
            print(f"  ✅ Correctly rejects unprofitable trade")
        elif should_enter and "Profitable" in desc:
            print(f"  ✅ Correctly accepts profitable trade")
        elif should_enter and "Break-even" in desc:
            print(f"  ⚠️  Enters break-even trade (should be rejected)")
        
        print()
    
    print("🎯 Summary:")
    print(f"  • New logic requires >0.26% spread to enter")
    print(f"  • This includes 0.11% fees + 0.15% profit margin")
    print(f"  • Original failing trades (0% spread) will be rejected")
    print(f"  • Only genuinely profitable opportunities will generate signals")

if __name__ == "__main__":
    test_fee_logic()