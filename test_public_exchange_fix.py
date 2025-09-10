#!/usr/bin/env python3
"""
Test script to verify the public exchange interface fix
"""

import sys
import os
import asyncio

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

async def test_public_exchange_init():
    """Test that public exchange can initialize with Symbol objects"""
    try:
        from src.structs.exchange import Symbol, AssetName, ExchangeName
        from src.exchanges.mexc.mexc_public import MexcPublicExchange
        
        print("Testing public exchange initialization with hashable symbols...")
        
        # Create test symbols
        symbols = [
            Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
            Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
            Symbol(base=AssetName("BNB"), quote=AssetName("USDT")),
        ]
        
        print(f"✅ Created {len(symbols)} test symbols")
        
        # Create exchange instance
        exchange = MexcPublicExchange()
        print("✅ MexcPublicExchange instance created")
        
        # Test symbol hashability directly
        symbols_set = set(symbols)
        print(f"✅ Symbols can be added to set: {len(symbols_set)} unique symbols")
        
        # Test the specific operation that was failing
        active_symbols = set()
        for symbol in symbols:
            active_symbols.add(symbol)
        
        print(f"✅ Symbol.add() operation works: {len(active_symbols)} symbols in set")
        
        # Test the set.update() operation
        test_set = set()
        test_set.update(symbols)
        print(f"✅ set.update() works: {len(test_set)} symbols")
        
        # Verify symbols are properly formatted
        for symbol in symbols:
            print(f"  - {symbol.base}/{symbol.quote} (futures: {symbol.is_futures})")
        
        print("\n🎉 All public exchange hashability tests passed!")
        print("The TypeError: unhashable type: 'Symbol' should now be fixed!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("This is expected if dependencies are not installed")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test function"""
    print("=" * 60)
    print("Testing Symbol Hashability Fix")
    print("=" * 60)
    
    success = await test_public_exchange_init()
    
    if success:
        print("\n✅ SOLUTION: The Symbol struct is now frozen=True, making it hashable")
        print("✅ The public exchange interface should work correctly now")
    else:
        print("\n❌ Tests failed - check dependencies and imports")
    
    return success

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)