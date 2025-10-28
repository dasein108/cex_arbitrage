#!/usr/bin/env python3
"""
Test script for ArbitrageAnalyzer

Quick validation and demonstration of the arbitrage analysis tool.
Tests with 1 day of F_USDT data and provides sample output.
"""

import asyncio
import sys
import os

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from trading.research.cross_arbitrage.arbitrage_analyzer import ArbitrageAnalyzer


async def test_single_symbol():
    """Test analyzer with a single symbol."""
    print("🧪 Testing ArbitrageAnalyzer with F_USDT (1 day)")
    print("="*50)
    
    analyzer = ArbitrageAnalyzer()
    
    try:
        # Run analysis
        df, results = await analyzer.run_analysis("F_USDT", days=1)
        
        # Display formatted report
        print(analyzer.format_report(results))
        
        # Show sample data
        print("\n📋 SAMPLE DATA (last 5 periods):")
        cols = ['timestamp', 'mexc_vs_gateio_futures_arb', 'gateio_spot_vs_futures_arb', 
               'total_arbitrage_sum_fees', 'is_profitable']
        print(df[cols].tail().to_string(index=False))
        
        # Show profitable periods summary
        profitable_count = results['profitable_streaks']['total_profitable_periods']
        total_periods = results['total_periods']
        print(f"\n✅ Test completed: {profitable_count}/{total_periods} profitable periods")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_multiple_symbols():
    """Test analyzer with multiple symbols (if available)."""
    print("\n🧪 Testing multiple symbols (quick validation)")
    print("="*50)
    
    analyzer = ArbitrageAnalyzer()
    test_symbols = ["F_USDT", "LUNC_USDT", "BTC_USDT"]
    
    for symbol in test_symbols:
        try:
            print(f"\n📊 Quick test: {symbol}")
            df, results = await analyzer.run_analysis(symbol, days=1)
            
            print(f"  ✅ {symbol}: {results['profitability_pct']:.1f}% profitable periods")
            print(f"      Best profit: {results['max_profit']:.3f}%")
            print(f"      Entry threshold (10th %ile): {results['entry_thresholds']['10th_percentile']:.3f}%")
            
        except Exception as e:
            print(f"  ❌ {symbol}: Failed - {e}")


async def validate_calculations():
    """Validate arbitrage calculations with sample data."""
    print("\n🔍 Validating calculations")
    print("="*30)
    
    analyzer = ArbitrageAnalyzer()
    
    try:
        df, _ = await analyzer.run_analysis("F_USDT", days=1)
        
        # Check first few rows for calculation logic
        sample = df.head(3)
        
        print("Sample calculation validation:")
        for i, row in sample.iterrows():
            mexc_ask = row['mexc_spot_ask_price']
            gateio_futures_bid = row['gateio_futures_bid_price']
            
            # Manual calculation
            manual_arb = (gateio_futures_bid - mexc_ask) / gateio_futures_bid * 100
            calculated_arb = row['mexc_vs_gateio_futures_arb']
            
            print(f"  Period {i+1}:")
            print(f"    MEXC ask: {mexc_ask:.4f} | Gate.io futures bid: {gateio_futures_bid:.4f}")
            print(f"    Manual: {manual_arb:.3f}% | Calculated: {calculated_arb:.3f}% ✅")
            
            if abs(manual_arb - calculated_arb) > 0.001:
                print(f"    ❌ CALCULATION MISMATCH!")
                return False
        
        print("\n✅ All calculations validated successfully")
        return True
        
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("🚀 ARBITRAGE ANALYZER TEST SUITE")
    print("="*60)
    
    # Test 1: Single symbol analysis
    test1_passed = await test_single_symbol()
    
    # Test 2: Multiple symbols (optional)
    await test_multiple_symbols()
    
    # Test 3: Calculation validation
    test3_passed = await validate_calculations()
    
    # Summary
    print("\n" + "="*60)
    print("📊 TEST SUMMARY:")
    print(f"  Single symbol test: {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"  Calculation validation: {'✅ PASSED' if test3_passed else '❌ FAILED'}")
    
    if test1_passed and test3_passed:
        print("\n🎉 ALL TESTS PASSED - ArbitrageAnalyzer is ready to use!")
        print("\n🔗 Usage examples:")
        print("  analyzer = ArbitrageAnalyzer()")
        print("  df, results = await analyzer.run_analysis('BTC_USDT', days=7)")
        print("  print(analyzer.format_report(results))")
    else:
        print("\n⚠️  Some tests failed - check errors above")


if __name__ == "__main__":
    asyncio.run(main())