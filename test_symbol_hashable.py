#!/usr/bin/env python3
"""
Test script to verify Symbol struct is hashable
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_symbol_hashable():
    """Test that Symbol struct is hashable and can be used in sets"""
    try:
        from src.structs.exchange import Symbol, AssetName
        
        print("Testing Symbol hashability...")
        
        # Create test symbols
        btc_usdt = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        eth_usdt = Symbol(base=AssetName("ETH"), quote=AssetName("USDT"))
        btc_usdt_duplicate = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        
        print("✅ Symbol objects created successfully")
        
        # Test hashability by using in set
        symbols_set = {btc_usdt, eth_usdt, btc_usdt_duplicate}
        
        print(f"✅ Symbol is hashable! Set contains {len(symbols_set)} unique symbols")
        print(f"Symbols in set: {[f'{s.base}/{s.quote}' for s in symbols_set]}")
        
        # Test that duplicate is recognized
        assert len(symbols_set) == 2, "Duplicate symbols should be deduplicated in set"
        print("✅ Duplicate symbol correctly deduplicated")
        
        # Test dictionary usage
        symbol_dict = {}
        symbol_dict[btc_usdt] = "BTC orderbook"
        symbol_dict[eth_usdt] = "ETH orderbook"
        
        print(f"✅ Symbol can be used as dictionary key! Dict has {len(symbol_dict)} entries")
        
        # Test equality
        assert btc_usdt == btc_usdt_duplicate, "Equal symbols should be equal"
        print("✅ Symbol equality works correctly")
        
        # Test hash consistency
        assert hash(btc_usdt) == hash(btc_usdt_duplicate), "Equal symbols should have same hash"
        print("✅ Symbol hash consistency verified")
        
        print("\n🎉 All Symbol hashability tests passed!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("This is expected if msgspec is not installed")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_symbol_hashable()
    sys.exit(0 if success else 1)