"""Example usage of arbitrage signal generation."""

import asyncio
import numpy as np
from trading.analysis.arbitrage_signals import (
    calculate_arb_signals,
    calculate_arb_signals_simple
)
from trading.analysis.structs import Signal


def simulate_spread_data(size: int = 1000) -> tuple:
    """Simulate historical spread data for testing."""
    # Simulate MEXC vs Gate.io futures spread (typically negative when arb opportunity)
    mexc_vs_gateio_futures = np.random.normal(-0.002, 0.001, size)  # Mean -0.2%, std 0.1%
    
    # Simulate Gate.io spot vs futures spread (typically small, positive when futures > spot)
    gateio_spot_vs_futures = np.random.normal(0.001, 0.0005, size)  # Mean 0.1%, std 0.05%
    
    return mexc_vs_gateio_futures.tolist(), gateio_spot_vs_futures.tolist()


async def main():
    print("=== Arbitrage Signal Generation Example ===\n")
    
    # Generate simulated historical data
    mexc_vs_gateio_history, gateio_spot_futures_history = simulate_spread_data(1000)
    
    # Test different current spread scenarios
    scenarios = [
        # Scenario 1: Strong ENTER signal (very negative MEXC vs Gate.io spread)
        {
            "name": "Strong Entry Opportunity",
            "mexc_vs_gateio_current": -0.005,  # -0.5% (very negative)
            "gateio_spot_futures_current": 0.0008  # 0.08% (normal)
        },
        # Scenario 2: Strong EXIT signal (high Gate.io spot vs futures spread)
        {
            "name": "Exit Signal",
            "mexc_vs_gateio_current": -0.0015,  # -0.15% (normal)
            "gateio_spot_futures_current": 0.003  # 0.3% (high)
        },
        # Scenario 3: HOLD (normal spreads)
        {
            "name": "Normal Market - Hold",
            "mexc_vs_gateio_current": -0.002,  # -0.2% (normal)
            "gateio_spot_futures_current": 0.001  # 0.1% (normal)
        }
    ]
    
    for scenario in scenarios:
        print(f"\n📊 {scenario['name']}")
        print("-" * 50)
        
        # Calculate signals with full statistics
        result = calculate_arb_signals(
            mexc_vs_gateio_history,
            gateio_spot_futures_history,
            scenario["mexc_vs_gateio_current"],
            scenario["gateio_spot_futures_current"]
        )
        
        print(f"Current Spreads:")
        print(f"  MEXC vs Gate.io Futures: {scenario['mexc_vs_gateio_current']:.4f} ({scenario['mexc_vs_gateio_current']*100:.2f}%)")
        print(f"  Gate.io Spot vs Futures: {scenario['gateio_spot_futures_current']:.4f} ({scenario['gateio_spot_futures_current']*100:.2f}%)")
        
        print(f"\nThresholds:")
        print(f"  MEXC/Gate.io 25th percentile MIN: {result.mexc_vs_gateio_futures.min_25pct:.4f} ({result.mexc_vs_gateio_futures.min_25pct*100:.2f}%)")
        print(f"  Gate.io S/F 25th percentile MAX: {result.gateio_spot_vs_futures.max_25pct:.4f} ({result.gateio_spot_vs_futures.max_25pct*100:.2f}%)")
        
        print(f"\n🎯 SIGNAL: {result.signal.value}")
        print(f"📝 Reason: {result.reason}")
        
        # Also test simple version
        signal, thresholds = calculate_arb_signals_simple(
            mexc_vs_gateio_history,
            gateio_spot_futures_history,
            scenario["mexc_vs_gateio_current"],
            scenario["gateio_spot_futures_current"]
        )
        
        if signal == Signal.ENTER:
            print("\n✅ ACTION: Enter arbitrage position (Buy MEXC spot, Sell Gate.io futures)")
        elif signal == Signal.EXIT:
            print("\n🔴 ACTION: Exit arbitrage position (Sell MEXC spot, Buy Gate.io futures)")
        else:
            print("\n⏸️  ACTION: Hold position, no action needed")
    
    print("\n" + "="*60)
    print("Signal Logic Summary:")
    print("  ENTER: When MEXC vs Gate.io futures < 25th percentile of historical minimums")
    print("  EXIT:  When Gate.io spot vs futures > 25th percentile of historical maximums")
    print("  HOLD:  Otherwise")


if __name__ == "__main__":
    asyncio.run(main())