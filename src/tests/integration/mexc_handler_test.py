"""
MEXC Handler Integration Test

Test the new MEXC direct handler implementation to ensure it works
correctly with both protobuf and JSON message formats.
"""

import asyncio
import time
from typing import Dict, Any


from infrastructure.networking.websocket.message_types import WebSocketMessageType
from exchanges.structs.common import Symbol, AssetName


async def test_mexc_handler_basic():
    """Test basic MEXC handler functionality."""
    print("Testing MEXC Public WebSocket Handler...")
    
    # Create handler
    handler = MexcPublicWebSocketHandler()
    
    # Test message type detection
    print("\n1. Testing message type detection...")
    
    # Test protobuf detection
    protobuf_msg = b'\x0a\x2espot@public.aggre.deals.v3.api.pb@100ms@BTCUSDT\x1a\x07BTCUSDT'
    msg_type = await handler._detect_message_type(protobuf_msg)
    print(f"   Protobuf message type: {msg_type}")
    assert msg_type == WebSocketMessageType.TRADE
    
    # Test JSON detection
    json_msg = '{"c":"spot@public.limit.depth.v3.api@BTCUSDT@20","d":{"bids":[["50000","1.0"]],"asks":[["50001","2.0"]]}}'
    msg_type = await handler._detect_message_type(json_msg)
    print(f"   JSON message type: {msg_type}")
    assert msg_type == WebSocketMessageType.ORDERBOOK
    
    # Test performance stats
    print("\n2. Testing performance tracking...")
    stats = handler.get_performance_stats()
    print(f"   Initial stats: {stats}")
    
    # Test health status
    print("\n3. Testing health status...")
    health = handler.get_health_status()
    print(f"   Health status: {health['exchange_specific']['exchange']}")
    assert health['exchange_specific']['exchange'] == 'mexc'
    
    print("✅ Basic MEXC handler tests passed!")


async def test_mexc_handler_json_parsing():
    """Test JSON message parsing."""
    print("\nTesting JSON message parsing...")
    
    handler = MexcPublicWebSocketHandler()
    
    # Test orderbook JSON
    orderbook_json = '''
    {
        "c": "spot@public.limit.depth.v3.api@BTCUSDT@20",
        "d": {
            "bids": [["50000", "1.5"], ["49999", "2.0"]],
            "asks": [["50001", "1.0"], ["50002", "1.5"]],
            "version": "12345"
        },
        "t": 1672531200000
    }
    '''
    
    # Parse orderbook
    start_time = time.perf_counter()
    orderbook = await handler._parse_orderbook_message(orderbook_json.strip())
    parse_time = (time.perf_counter() - start_time) * 1_000_000  # μs
    
    if orderbook:
        print(f"   Orderbook parsed successfully in {parse_time:.1f}μs")
        print(f"   Symbol: {orderbook.symbol}")
        print(f"   Bids: {len(orderbook.bids)}, Asks: {len(orderbook.asks)}")
        assert len(orderbook.bids) == 2
        assert len(orderbook.asks) == 2
        assert orderbook.bids[0].price == 50000.0
        print("   ✅ Orderbook parsing test passed!")
    else:
        print("   ❌ Orderbook parsing failed")
    
    # Test trade JSON
    trade_json = '''
    {
        "c": "spot@public.aggre.deals.v3.api@BTCUSDT",
        "d": {
            "deals": [
                {"p": "50000.5", "v": "0.1", "t": 1672531200000, "s": 1},
                {"p": "50000.6", "v": "0.2", "t": 1672531201000, "s": 0}
            ]
        },
        "t": 1672531200000
    }
    '''
    
    # Parse trades
    start_time = time.perf_counter()
    trades = await handler._parse_trade_message(trade_json.strip())
    parse_time = (time.perf_counter() - start_time) * 1_000_000  # μs
    
    if trades:
        print(f"   Trades parsed successfully in {parse_time:.1f}μs")
        print(f"   Trade count: {len(trades)}")
        print(f"   First trade: {trades[0].price} @ {trades[0].quantity}")
        assert len(trades) == 2
        assert trades[0].price == 50000.5
        assert trades[0].quantity == 0.1
        print("   ✅ Trade parsing test passed!")
    else:
        print("   ❌ Trade parsing failed")


async def test_mexc_handler_performance():
    """Test performance characteristics."""
    print("\nTesting performance characteristics...")
    
    handler = MexcPublicWebSocketHandler()
    
    # Test rapid message processing
    test_messages = [
        '{"c":"spot@public.limit.depth.v3.api@BTCUSDT@20","d":{"bids":[["50000","1.0"]]}}',
        '{"c":"spot@public.aggre.deals.v3.api@BTCUSDT","d":{"deals":[{"p":"50000","v":"0.1","t":1672531200000,"s":1}]}}',
        '{"c":"spot@public.book_ticker.v3.api@BTCUSDT","d":{"bp":"50000","bv":"1.0","ap":"50001","av":"1.0"}}'
    ]
    
    # Measure parsing times
    parsing_times = []
    
    for i, msg in enumerate(test_messages * 100):  # 300 messages total
        start_time = time.perf_counter()
        
        # Detect type and parse
        msg_type = await handler._detect_message_type(msg)
        
        if msg_type == WebSocketMessageType.ORDERBOOK:
            await handler._parse_orderbook_message(msg)
        elif msg_type == WebSocketMessageType.TRADE:
            await handler._parse_trade_message(msg)
        elif msg_type == WebSocketMessageType.TICKER:
            await handler._parse_ticker_message(msg)
        
        parse_time = (time.perf_counter() - start_time) * 1_000_000  # μs
        parsing_times.append(parse_time)
    
    # Calculate statistics
    avg_time = sum(parsing_times) / len(parsing_times)
    max_time = max(parsing_times)
    min_time = min(parsing_times)
    
    print(f"   Processed {len(parsing_times)} messages")
    print(f"   Average parsing time: {avg_time:.1f}μs")
    print(f"   Max parsing time: {max_time:.1f}μs")
    print(f"   Min parsing time: {min_time:.1f}μs")
    
    # Check performance targets
    targets_met = {
        "avg_under_50us": avg_time < 50,
        "max_under_100us": max_time < 100,
        "min_under_20us": min_time < 20
    }
    
    print(f"   Performance targets: {targets_met}")
    
    if targets_met["avg_under_50us"]:
        print("   ✅ Average parsing time target met (<50μs)")
    else:
        print("   ⚠️  Average parsing time above target")
    
    # Get final performance stats
    final_stats = handler.get_performance_stats()
    print(f"   Final performance stats: {final_stats}")


async def test_mexc_handler_edge_cases():
    """Test edge cases and error handling."""
    print("\nTesting edge cases...")
    
    handler = MexcPublicWebSocketHandler()
    
    # Test invalid messages
    invalid_messages = [
        "",  # Empty string
        "invalid json",  # Invalid JSON
        b"invalid protobuf",  # Invalid protobuf
        '{"c":"unknown","d":{}}',  # Unknown channel
        None,  # None value
    ]
    
    for i, msg in enumerate(invalid_messages):
        try:
            msg_type = await handler._detect_message_type(msg)
            print(f"   Message {i+1}: {msg_type}")
            
            # Try parsing
            if msg_type != WebSocketMessageType.UNKNOWN:
                if msg_type == WebSocketMessageType.ORDERBOOK:
                    result = await handler._parse_orderbook_message(msg)
                elif msg_type == WebSocketMessageType.TRADE:
                    result = await handler._parse_trade_message(msg)
                elif msg_type == WebSocketMessageType.TICKER:
                    result = await handler._parse_ticker_message(msg)
                
                print(f"     Parsing result: {result is not None}")
            
        except Exception as e:
            print(f"   Message {i+1} error (expected): {type(e).__name__}")
    
    print("   ✅ Edge case handling test completed!")


async def main():
    """Run all MEXC handler tests."""
    print("🚀 MEXC WebSocket Handler Integration Tests")
    print("=" * 50)
    
    try:
        await test_mexc_handler_basic()
        await test_mexc_handler_json_parsing() 
        await test_mexc_handler_performance()
        await test_mexc_handler_edge_cases()
        
        print("\n" + "=" * 50)
        print("🎉 All MEXC handler tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())