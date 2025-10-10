#!/usr/bin/env python3
"""
Direct data analysis to understand why backtester finds no opportunities
while SQL query shows profitable spreads.
"""

import asyncio
import sys
sys.path.append('src')

from datetime import datetime, timedelta
import pandas as pd
import numpy as np

async def analyze_data_directly():
    """Direct database analysis to understand the data availability issue."""
    
    # Initialize database connection
    from src.db.database_manager import initialize_database_manager, get_database_manager
    await initialize_database_manager()
    db = get_database_manager()
    
    print("=== DIRECT DATA ANALYSIS ===")
    print()
    
    # Check what exchanges and symbols we have
    exchanges_query = """
    SELECT e.enum_value, e.exchange_name, COUNT(s.id) as symbol_count
    FROM exchanges e
    LEFT JOIN symbols s ON e.id = s.exchange_id
    GROUP BY e.enum_value, e.exchange_name
    ORDER BY symbol_count DESC
    """
    
    async with db._pool.acquire() as conn:
        exchanges = await conn.fetch(exchanges_query)
        print("📊 Available Exchanges:")
        for exchange in exchanges:
            print(f"  {exchange['enum_value']:15} - {exchange['symbol_count']:3} symbols")
    
    print()
    
    # Check recent data availability
    recent_data_query = """
    SELECT 
        e.enum_value as exchange,
        s.symbol_base,
        s.symbol_quote,
        COUNT(*) as record_count,
        MIN(bts.timestamp) as earliest,
        MAX(bts.timestamp) as latest
    FROM book_ticker_snapshots bts
    JOIN symbols s ON bts.symbol_id = s.id  
    JOIN exchanges e ON s.exchange_id = e.id
    WHERE bts.timestamp > NOW() - INTERVAL '6 hours'
    GROUP BY e.enum_value, s.symbol_base, s.symbol_quote
    ORDER BY record_count DESC
    LIMIT 20
    """
    
    async with db._pool.acquire() as conn:
        recent_data = await conn.fetch(recent_data_query)
        print("📈 Recent Data (Last 6 hours):")
        for row in recent_data:
            print(f"  {row['exchange']:15} {row['symbol_base']:8}/{row['symbol_quote']:5} - {row['record_count']:6} records - {row['latest']}")
    
    print()
    
    # Focus on LUNC/USDT if available
    lunc_data_query = """
    SELECT 
        e.enum_value as exchange,
        COUNT(*) as record_count,
        MIN(bts.timestamp) as earliest,
        MAX(bts.timestamp) as latest,
        AVG(bts.bid_price) as avg_bid,
        AVG(bts.ask_price) as avg_ask
    FROM book_ticker_snapshots bts
    JOIN symbols s ON bts.symbol_id = s.id  
    JOIN exchanges e ON s.exchange_id = e.id
    WHERE s.symbol_base = 'LUNC' 
      AND s.symbol_quote = 'USDT'
      AND bts.timestamp > NOW() - INTERVAL '6 hours'
    GROUP BY e.enum_value
    ORDER BY record_count DESC
    """
    
    async with db._pool.acquire() as conn:
        lunc_data = await conn.fetch(lunc_data_query)
        if lunc_data:
            print("🎯 LUNC/USDT Data:")
            for row in lunc_data:
                print(f"  {row['exchange']:15} - {row['record_count']:4} records - Avg bid: {row['avg_bid']:.6f}, ask: {row['avg_ask']:.6f}")
                print(f"                    - Range: {row['earliest']} to {row['latest']}")
        else:
            print("❌ No LUNC/USDT data found in last 6 hours")
    
    print()
    
    # If we have LUNC data, try the SQL arbitrage query
    if lunc_data and len(lunc_data) >= 2:
        print("🔍 Testing SQL Arbitrage Query (Last 1 hour):")
        arbitrage_query = """
        WITH exchange_prices AS (
            SELECT
                DATE_TRUNC('second', bts.timestamp) as time_bucket,
                e.enum_value as exchange,
                AVG(bts.bid_price) as bid_price,
                AVG(bts.ask_price) as ask_price
            FROM book_ticker_snapshots bts
            JOIN symbols s ON bts.symbol_id = s.id
            JOIN exchanges e ON s.exchange_id = e.id
            WHERE
                bts.timestamp > NOW() - INTERVAL '1 hour'
                AND s.symbol_base = 'LUNC'
                AND s.symbol_quote = 'USDT'
                AND bts.bid_price > 0 
                AND bts.ask_price > 0
            GROUP BY DATE_TRUNC('second', bts.timestamp), e.enum_value
        )
        SELECT
            e1.time_bucket,
            e1.exchange as sell_exchange,
            e2.exchange as buy_exchange,
            e1.bid_price as sell_price,
            e2.ask_price as buy_price,
            ((e1.bid_price - e2.ask_price) / e2.ask_price * 100) as spread_pct
        FROM exchange_prices e1
        JOIN exchange_prices e2 
            ON e1.time_bucket = e2.time_bucket
            AND e1.exchange != e2.exchange
        WHERE ((e1.bid_price - e2.ask_price) / e2.ask_price * 100) > 0.05  -- > 0.05%
        ORDER BY e1.time_bucket DESC, spread_pct DESC
        LIMIT 10
        """
        
        async with db._pool.acquire() as conn:
            arbitrage_ops = await conn.fetch(arbitrage_query)
            if arbitrage_ops:
                print(f"✅ Found {len(arbitrage_ops)} profitable arbitrage opportunities!")
                for op in arbitrage_ops:
                    print(f"  {op['time_bucket']} - Sell {op['sell_exchange']} @ {op['sell_price']:.6f}, Buy {op['buy_exchange']} @ {op['buy_price']:.6f} = {op['spread_pct']:.3f}%")
            else:
                print("❌ No profitable arbitrage opportunities found")
    
    # Check if the issue is symbol resolution
    print()
    print("🔧 Symbol Resolution Test:")
    
    symbol_resolution_query = """
    SELECT s.id, s.symbol_base, s.symbol_quote, s.exchange_symbol, e.enum_value
    FROM symbols s
    JOIN exchanges e ON s.exchange_id = e.id
    WHERE s.symbol_base = 'LUNC' AND s.symbol_quote = 'USDT'
    ORDER BY e.enum_value
    """
    
    async with db._pool.acquire() as conn:
        symbols = await conn.fetch(symbol_resolution_query)
        if symbols:
            print("📋 Symbol mappings for LUNC/USDT:")
            for symbol in symbols:
                print(f"  ID {symbol['id']:2} - {symbol['enum_value']:15} - {symbol['symbol_base']}/{symbol['symbol_quote']} ({symbol['exchange_symbol']})")
        else:
            print("❌ No symbol mappings found for LUNC/USDT")

if __name__ == "__main__":
    asyncio.run(analyze_data_directly())