#!/usr/bin/env python3
"""
Check Database Data Availability

Simple script to check what book ticker data is available for backtesting.
"""

import asyncio
import asyncpg
import os
from datetime import datetime, timedelta, timezone


async def check_database_data():
    """Check what data is available in the database"""
    
    print("🔍 Checking Database Data Availability")
    print("=" * 50)
    
    # Database connection
    db_host = os.getenv('POSTGRES_HOST', 'localhost')
    db_port = int(os.getenv('POSTGRES_PORT', '5432'))
    db_user = os.getenv('POSTGRES_USER', 'arbitrage_user')
    db_password = os.getenv('POSTGRES_PASSWORD', 'dev_password_2024')
    db_name = os.getenv('POSTGRES_DB', 'arbitrage_data')
    
    if not db_password or db_password == 'dev_password_2024':
        print("⚠️  Using default password. Set POSTGRES_PASSWORD environment variable.")
    
    try:
        conn = await asyncpg.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database=db_name
        )
        
        print(f"✅ Connected to database: {db_host}:{db_port}/{db_name}")
        
        # Check what symbols are available
        symbols_query = """
        SELECT DISTINCT 
            exchange,
            symbol_base,
            symbol_quote,
            COUNT(*) as snapshot_count,
            MIN(timestamp) as earliest,
            MAX(timestamp) as latest
        FROM book_ticker_snapshots
        WHERE symbol_base IN ('F', 'BTC', 'ETH', 'NEIROETH')
        AND symbol_quote = 'USDT'
        GROUP BY exchange, symbol_base, symbol_quote
        ORDER BY exchange, symbol_base
        """
        
        rows = await conn.fetch(symbols_query)
        
        if not rows:
            print("❌ No book ticker data found")
            return
        
        print(f"\n📊 Available Data Summary:")
        print(f"{'Exchange':<15} {'Symbol':<10} {'Count':<10} {'Latest':<20}")
        print("-" * 65)
        
        symbol_data = {}
        for row in rows:
            exchange = row['exchange']
            symbol = f"{row['symbol_base']}/{row['symbol_quote']}"
            count = row['snapshot_count']
            latest = row['latest']
            
            print(f"{exchange:<15} {symbol:<10} {count:<10} {latest}")
            
            # Track symbols that have data on all 3 exchanges
            if symbol not in symbol_data:
                symbol_data[symbol] = set()
            symbol_data[symbol].add(exchange)
        
        # Find symbols available on all required exchanges
        required_exchanges = {'MEXC', 'GATEIO', 'GATEIO_FUTURES'}
        complete_symbols = [symbol for symbol, exchanges in symbol_data.items() 
                          if required_exchanges.issubset(exchanges)]
        
        print(f"\n✅ Symbols with complete data (all 3 exchanges):")
        for symbol in complete_symbols:
            print(f"  📈 {symbol}")
        
        if not complete_symbols:
            print("❌ No symbols found with data on all 3 exchanges")
            print("Required exchanges: MEXC, GATEIO, GATEIO_FUTURES")
            return
        
        # Check data for last 24 hours for F/USDT
        print(f"\n🔍 Detailed check for F/USDT (last 24 hours):")
        
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=24)
        
        detailed_query = """
        SELECT 
            exchange,
            COUNT(*) as count_24h,
            MIN(timestamp) as earliest_24h,
            MAX(timestamp) as latest_24h,
            AVG(bid_price) as avg_bid,
            AVG(ask_price) as avg_ask
        FROM book_ticker_snapshots
        WHERE symbol_base = 'F'
        AND symbol_quote = 'USDT'
        AND timestamp >= $1
        GROUP BY exchange
        ORDER BY exchange
        """
        
        detail_rows = await conn.fetch(detailed_query, start_time)
        
        for row in detail_rows:
            exchange = row['exchange']
            count = row['count_24h']
            avg_bid = float(row['avg_bid'])
            avg_ask = float(row['avg_ask'])
            spread_bps = ((avg_ask - avg_bid) / avg_bid) * 10000
            
            print(f"  {exchange:<15}: {count:>6} snapshots, avg_spread={spread_bps:.1f} bps")
        
        # Calculate potential spreads
        if len(detail_rows) >= 3:
            print(f"\n💡 Ready for backtesting with F/USDT!")
            print(f"Run: python src/examples/standalone_db_backtest.py")
        else:
            print(f"\n⚠️  Insufficient data for F/USDT backtesting")
            
        await conn.close()
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("\n💡 Setup instructions:")
        print("1. Ensure PostgreSQL is running")
        print("2. Set environment variables:")
        print("   export POSTGRES_HOST=localhost")
        print("   export POSTGRES_PASSWORD=your_password")


if __name__ == "__main__":
    asyncio.run(check_database_data())