#!/usr/bin/env python3
"""
Example usage of CandlesDownloader class

Demonstrates various ways to use the candles downloader both 
programmatically and with different configuration options.
"""

import asyncio
from datetime import datetime, timedelta
from candles_downloader import CandlesDownloader


async def example_single_download():
    """Example: Single exchange download with automatic date range"""
    print("=== Single Download Example ===")
    
    downloader = CandlesDownloader(output_dir="./data")
    
    # Download last 7 days of BTC/USDT 1h candles from MEXC
    csv_path = await downloader.download_candles(
        exchange='mexc',
        symbol='BTC_USDT',
        timeframe='1h',
        days=7
    )
    
    print(f"Downloaded to: {csv_path}")


async def example_date_range_download():
    """Example: Download with specific date range"""
    print("\n=== Date Range Download Example ===")
    
    downloader = CandlesDownloader(output_dir="./data")
    
    # Download specific date range
    start_date = datetime(2024, 8, 1)
    end_date = datetime(2024, 8, 31)
    
    csv_path = await downloader.download_candles(
        exchange='gateio',
        symbol='ETH_USDT', 
        timeframe='1d',
        start_date=start_date,
        end_date=end_date
    )
    
    print(f"Downloaded to: {csv_path}")


async def example_multiple_downloads():
    """Example: Download from multiple cex concurrently"""
    print("\n=== Multiple Downloads Example ===")
    
    downloader = CandlesDownloader(output_dir="./data")
    
    # Configuration for multiple downloads
    download_configs = [
        {
            'exchange': 'mexc',
            'symbol': 'BTC_USDT',
            'timeframe': '1h',
            'days': 3
        },
        {
            'exchange': 'gateio', 
            'symbol': 'BTC_USDT',
            'timeframe': '1h',
            'days': 3
        },
        {
            'exchange': 'mexc',
            'symbol': 'ETH_USDT',
            'timeframe': '4h',
            'days': 7
        }
    ]
    
    # Download all configurations concurrently
    csv_paths = await downloader.download_multiple(download_configs)
    
    print(f"Downloaded {len(csv_paths)} files:")
    for path in csv_paths:
        print(f"  - {path}")


async def example_custom_filename():
    """Example: Download with custom filename"""
    print("\n=== Custom Filename Example ===")
    
    downloader = CandlesDownloader(output_dir="./data")
    
    csv_path = await downloader.download_candles(
        exchange='mexc',
        symbol='BNB_USDT',
        timeframe='5m',
        days=1,
        filename='custom_bnb_data.csv'
    )
    
    print(f"Downloaded to: {csv_path}")


def example_info_methods():
    """Example: Get information about supported cex and timeframes"""
    print("\n=== Available Options ===")
    
    downloader = CandlesDownloader()
    
    print("Supported cex:")
    for exchange in downloader.list_available_exchanges():
        print(f"  - {exchange}")
    
    print("\nSupported timeframes:")
    for timeframe in downloader.list_available_timeframes():
        print(f"  - {timeframe}")


async def main():
    """Run all examples"""
    print("🚀 CandlesDownloader Examples")
    print("=" * 50)
    
    # Show available options
    example_info_methods()
    
    try:
        # Run download examples (comment out if you don't want actual downloads)
        await example_single_download()
        await example_date_range_download()
        await example_multiple_downloads() 
        await example_custom_filename()
        
        print("\n✅ All examples completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Example failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())