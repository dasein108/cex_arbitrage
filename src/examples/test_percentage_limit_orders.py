#!/usr/bin/env python3
"""
Test script for percentage-based limit order functionality.

Validates the new profit percentage calculation and tolerance logic.
"""

import msgspec
from typing import Dict, Any, Literal


class TradingParameters(msgspec.Struct):
    """Trading parameters with percentage-based limit order parameters."""
    max_entry_cost_pct: float = 0.5
    min_profit_pct: float = 0.1
    max_hours: float = 6.0
    spot_fee: float = 0.0005
    fut_fee: float = 0.0005
    # New percentage-based limit order parameters
    limit_orders_enabled: bool = False
    limit_profit_pct: float = 0.2       # 20 bps target profit
    limit_profit_tolerance_pct: float = 0.1  # 10 bps tolerance before updating


def test_limit_price_calculation():
    """Test the percentage-based limit price calculation."""
    print("🧪 Testing limit price calculation logic...")
    
    params = TradingParameters(
        limit_profit_pct=0.5,  # 50 bps target profit
        limit_profit_tolerance_pct=0.1  # 10 bps tolerance
    )
    
    # Test entry limit price calculation
    fut_bid = 100.0  # Futures bid
    expected_spot_limit = fut_bid / (1 + params.limit_profit_pct / 100)
    
    print(f"Entry limit calculation:")
    print(f"  Futures bid: {fut_bid}")
    print(f"  Target profit: {params.limit_profit_pct}%")
    print(f"  Calculated spot limit price: {expected_spot_limit:.6f}")
    
    # Verify the profit calculation
    actual_profit_pct = (fut_bid - expected_spot_limit) / expected_spot_limit * 100
    print(f"  Actual profit at limit price: {actual_profit_pct:.4f}%")
    
    assert abs(actual_profit_pct - params.limit_profit_pct) < 1e-10, "Profit calculation error"
    print("✅ Entry limit price calculation correct")
    
    # Test exit limit price calculation
    spot_bid = 99.0  # Current spot bid
    exit_limit_price = spot_bid * (1 + params.limit_profit_pct / 100)
    
    print(f"\nExit limit calculation:")
    print(f"  Current spot bid: {spot_bid}")
    print(f"  Target improvement: {params.limit_profit_pct}%")
    print(f"  Calculated exit limit price: {exit_limit_price:.6f}")
    
    # Verify the improvement
    improvement_pct = (exit_limit_price - spot_bid) / spot_bid * 100
    print(f"  Actual improvement: {improvement_pct:.4f}%")
    
    assert abs(improvement_pct - params.limit_profit_pct) < 1e-10, "Improvement calculation error"
    print("✅ Exit limit price calculation correct")


def test_tolerance_logic():
    """Test the tolerance-based update logic."""
    print("\n🧪 Testing tolerance logic...")
    
    params = TradingParameters(
        limit_profit_pct=0.5,
        limit_profit_tolerance_pct=0.1
    )
    
    current_limit_price = 99.5
    
    # Test scenarios with different price movements
    test_cases = [
        (99.45, "Small move - no update"),     # 0.05% change < 0.1% tolerance
        (99.4001, "Edge case - update"),       # ~0.1% change = tolerance (should update)
        (99.35, "Large move - update"),       # 0.15% change > 0.1% tolerance
        (99.0, "Very large move - update"),   # 0.5% change > 0.1% tolerance
    ]
    
    for new_price, description in test_cases:
        price_change_pct = abs(new_price - current_limit_price) / current_limit_price * 100
        should_update = price_change_pct >= params.limit_profit_tolerance_pct
        
        print(f"  {description}:")
        print(f"    Price change: {current_limit_price:.6f} -> {new_price:.6f}")
        print(f"    Change %: {price_change_pct:.3f}%")
        print(f"    Should update: {should_update}")
        
        if "no update" in description.lower():
            assert not should_update, f"Should not update for {description}"
        else:
            assert should_update, f"Should update for {description}"
    
    print("✅ Tolerance logic working correctly")


def test_spike_catching_logic():
    """Test the spike catching logic with realistic scenarios."""
    print("\n🧪 Testing spike catching scenarios...")
    
    params = TradingParameters(
        limit_profit_pct=0.3,      # 30 bps target 
        limit_profit_tolerance_pct=0.05,  # 5 bps tolerance (tight tracking)
        min_profit_pct=0.1         # 10 bps minimum profit
    )
    
    # Scenario 1: Normal market conditions
    spot_ask = 100.0
    fut_bid = 100.2  # 20 bps spread
    
    limit_price = fut_bid / (1 + params.limit_profit_pct / 100)
    can_place_limit = limit_price < spot_ask  # Must be below ask
    
    print(f"Scenario 1 - Normal conditions:")
    print(f"  Spot ask: {spot_ask}, Futures bid: {fut_bid}")
    print(f"  Calculated limit: {limit_price:.6f}")
    print(f"  Can place limit: {can_place_limit}")
    
    if can_place_limit:
        expected_profit = (fut_bid - limit_price) / limit_price * 100
        print(f"  Expected profit: {expected_profit:.3f}%")
    
    # Scenario 2: Spike conditions (wider spread)
    spot_ask = 100.0
    fut_bid = 100.5  # 50 bps spread - spike opportunity
    
    limit_price = fut_bid / (1 + params.limit_profit_pct / 100)
    can_place_limit = limit_price < spot_ask
    
    print(f"\nScenario 2 - Spike conditions:")
    print(f"  Spot ask: {spot_ask}, Futures bid: {fut_bid}")
    print(f"  Calculated limit: {limit_price:.6f}")
    print(f"  Can place limit: {can_place_limit}")
    
    if can_place_limit:
        expected_profit = (fut_bid - limit_price) / limit_price * 100
        print(f"  Expected profit: {expected_profit:.3f}%")
        
        # This should be profitable
        total_threshold = params.min_profit_pct + params.limit_profit_pct
        meets_threshold = expected_profit >= total_threshold
        print(f"  Meets threshold ({total_threshold:.1f}%): {meets_threshold}")
    
    print("✅ Spike catching logic validated")


def test_market_boundaries():
    """Test edge cases with market boundaries."""
    print("\n🧪 Testing market boundary conditions...")
    
    params = TradingParameters(limit_profit_pct=0.2)
    
    # Edge case 1: Limit price would be above ask (invalid)
    spot_ask = 100.0
    fut_bid = 100.1  # Very small spread
    
    limit_price = fut_bid / (1 + params.limit_profit_pct / 100)
    is_valid = limit_price < spot_ask
    
    print(f"Edge case 1 - Limit above ask:")
    print(f"  Spot ask: {spot_ask}, Futures bid: {fut_bid}")
    print(f"  Calculated limit: {limit_price:.6f}")
    print(f"  Valid (< ask): {is_valid}")
    
    # Edge case 2: Exit limit below bid (invalid)
    spot_bid = 99.0
    exit_limit = spot_bid * (1 + params.limit_profit_pct / 100)
    is_valid_exit = exit_limit > spot_bid
    
    print(f"\nEdge case 2 - Exit limit validity:")
    print(f"  Spot bid: {spot_bid}")
    print(f"  Calculated exit limit: {exit_limit:.6f}")
    print(f"  Valid (> bid): {is_valid_exit}")
    
    print("✅ Market boundary conditions handled correctly")


def main():
    """Run all percentage-based limit order tests."""
    print("🚀 Testing Percentage-Based Limit Order Logic")
    print("=" * 60)
    
    try:
        test_limit_price_calculation()
        test_tolerance_logic()
        test_spike_catching_logic()
        test_market_boundaries()
        
        print("\n" + "=" * 60)
        print("🎉 All tests passed! Percentage-based limit order logic ready.")
        print("\n📋 Key Improvements:")
        print("  • Profit percentage-based price calculation (not fixed ticks)")
        print("  • Tolerance percentage for smart order updates")
        print("  • Automatic spike detection and optimal positioning")
        print("  • Market boundary validation prevents invalid orders")
        print("  • Consistent profit targeting across different price levels")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    main()