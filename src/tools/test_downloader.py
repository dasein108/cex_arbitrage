#!/usr/bin/env python3
"""
Quick test script for CandlesDownloader

Simple test to verify the downloader works correctly with both cex.
Downloads a small amount of recent data for validation.
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path so we can import from cex
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from candles_downloader import CandlesDownloader


async def test_mexc_download():
    """Test MEXC download functionality"""
    print("🧪 Testing MEXC download...")
    
    downloader = CandlesDownloader(output_dir="./test_data")
    
    try:
        csv_path = await downloader.download_candles(
            exchange='mexc',
            symbol='BTC_USDT',
            timeframe='1h',
            days=1,  # Small test - just 1 day
            filename='test_mexc_btc_1h.csv'
        )
        
        # Verify file exists and has content
        file_path = Path(csv_path)
        if file_path.exists():
            file_size = file_path.stat().st_size
            print(f"✅ MEXC test passed: {csv_path} ({file_size} bytes)")
            
            # Show first few lines
            with open(csv_path, 'r') as f:
                lines = f.readlines()[:3]  # Header + 2 data lines
                print("   Sample data:")
                for line in lines:
                    print(f"   {line.strip()}")
            
            return True
        else:
            print("❌ MEXC test failed: File not created")
            return False
            
    except Exception as e:
        print(f"❌ MEXC test failed: {e}")
        return False


async def test_gateio_download():
    """Test Gate.io download functionality"""
    print("\n🧪 Testing Gate.io download...")
    
    downloader = CandlesDownloader(output_dir="./test_data")
    
    try:
        csv_path = await downloader.download_candles(
            exchange='gateio',
            symbol='BTC_USDT',
            timeframe='1h',
            days=1,  # Small test - just 1 day
            filename='test_gateio_btc_1h.csv'
        )
        
        # Verify file exists and has content
        file_path = Path(csv_path)
        if file_path.exists():
            file_size = file_path.stat().st_size
            print(f"✅ Gate.io test passed: {csv_path} ({file_size} bytes)")
            
            # Show first few lines
            with open(csv_path, 'r') as f:
                lines = f.readlines()[:3]  # Header + 2 data lines
                print("   Sample data:")
                for line in lines:
                    print(f"   {line.strip()}")
            
            return True
        else:
            print("❌ Gate.io test failed: File not created")
            return False
            
    except Exception as e:
        print(f"❌ Gate.io test failed: {e}")
        return False


def test_info_methods():
    """Test information methods"""
    print("\n🧪 Testing info methods...")
    
    downloader = CandlesDownloader()
    
    exchanges = downloader.list_available_exchanges()
    timeframes = downloader.list_available_timeframes()
    
    print(f"✅ Available cex: {exchanges}")
    print(f"✅ Available timeframes: {timeframes}")
    
    return len(exchanges) > 0 and len(timeframes) > 0


async def run_tests():
    """Run all tests"""
    print("🚀 Running CandlesDownloader Tests")
    print("=" * 50)
    
    # Create test data directory
    Path("./test_data").mkdir(exist_ok=True)
    
    results = []
    
    # Test info methods (no API calls)
    results.append(test_info_methods())
    
    # Test actual downloads (requires API access)
    try:
        results.append(await test_mexc_download())
        results.append(await test_gateio_download())
    except Exception as e:
        print(f"⚠️  API tests failed: {e}")
        print("   This might be due to network issues or API limitations")
        results.extend([False, False])
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print(f"\n📊 Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed!")
        return True
    else:
        print("💥 Some tests failed!")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)