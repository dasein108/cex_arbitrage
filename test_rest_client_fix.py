#!/usr/bin/env python3
"""
Test script to verify the REST client fix for tcp_keepalive parameter
"""

import sys
import os
import asyncio

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

async def test_rest_client_creation():
    """Test that REST client can be created without tcp_keepalive error"""
    try:
        from src.common.rest import HighPerformanceRestClient, ConnectionConfig
        
        print("Testing REST client creation with new aiohttp version...")
        
        # Create connection config
        config = ConnectionConfig(
            connector_limit=50,
            connector_limit_per_host=20,
            total_timeout=10.0
        )
        print("✅ ConnectionConfig created successfully")
        
        # Create REST client
        client = HighPerformanceRestClient(
            base_url="https://api.mexc.com",
            connection_config=config
        )
        print("✅ HighPerformanceRestClient created successfully")
        
        # Test session creation (the part that was failing)
        async with client:
            print("✅ REST client session created successfully")
            print("✅ No tcp_keepalive error!")
            
            # Test that the client has the expected attributes
            assert client._connector is not None, "Connector should be created"
            assert client._session is not None, "Session should be created"
            
        print("\n🎉 All REST client tests passed!")
        print("The tcp_keepalive error has been fixed!")
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
    print("Testing REST Client tcp_keepalive Fix")
    print("=" * 60)
    
    success = await test_rest_client_creation()
    
    if success:
        print("\n✅ SOLUTION: Removed deprecated tcp_keepalive parameter from aiohttp.TCPConnector")
        print("✅ REST client should now work with aiohttp 3.12+ versions")
    else:
        print("\n❌ Tests failed - check dependencies and imports")
    
    return success

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)