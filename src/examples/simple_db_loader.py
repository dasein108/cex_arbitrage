#!/usr/bin/env python3
"""
Simple Database Loader for Backtest
Uses direct asyncpg connection without complex dependencies.
"""

import asyncio
import asyncpg
import pandas as pd
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple


async def load_book_ticker_data(
    symbol_base: str,
    symbol_quote: str, 
    start_time: datetime,
    end_time: datetime,
    exchange: str = None
) -> pd.DataFrame:
    """Load book ticker data from database directly"""
    
    # Database connection
    db_host = os.getenv('POSTGRES_HOST', 'localhost')
    db_port = int(os.getenv('POSTGRES_PORT', '5432'))
    db_user = os.getenv('POSTGRES_USER', 'arbitrage_user')
    db_password = os.getenv('POSTGRES_PASSWORD', 'dev_password_2024')
    db_name = os.getenv('POSTGRES_DB', 'arbitrage_data')
    
    conn = await asyncpg.connect(
        host=db_host, port=db_port, user=db_user,
        password=db_password, database=db_name
    )
    
    try:
        # Build query
        where_clause = """
        WHERE symbol_base = $1 AND symbol_quote = $2 
        AND timestamp BETWEEN $3 AND $4
        """
        params = [symbol_base, symbol_quote, start_time, end_time]
        
        if exchange:
            where_clause += " AND exchange = $5"
            params.append(exchange)
        
        query = f"""
        SELECT timestamp, exchange, symbol_base, symbol_quote,
               bid_price, bid_qty, ask_price, ask_qty
        FROM book_ticker_snapshots
        {where_clause}
        ORDER BY timestamp
        """
        
        rows = await conn.fetch(query, *params)
        
        # Convert to DataFrame
        df = pd.DataFrame([dict(row) for row in rows])
        
        if not df.empty:
            # Convert decimal to float
            numeric_cols = ['bid_price', 'bid_qty', 'ask_price', 'ask_qty']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = df[col].astype(float)
        
        return df
        
    finally:
        await conn.close()


async def get_cached_book_ticker_data(
    exchange: str,
    symbol_base: str,
    symbol_quote: str,
    start_time: datetime,
    end_time: datetime
) -> pd.DataFrame:
    """
    Compatibility function matching the original interface.
    Loads data from database and returns in expected format.
    """
    
    df = await load_book_ticker_data(
        symbol_base=symbol_base,
        symbol_quote=symbol_quote,
        start_time=start_time,
        end_time=end_time,
        exchange=exchange
    )
    
    if df.empty:
        return pd.DataFrame()
    
    # Rename columns to match expected format
    df = df.rename(columns={
        'bid_price': 'bid_price',
        'ask_price': 'ask_price',
        'bid_qty': 'bid_qty', 
        'ask_qty': 'ask_qty'
    })
    
    return df


if __name__ == "__main__":
    # Test the loader
    async def test():
        from datetime import datetime, timedelta, timezone
        
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=3)
        
        print(f'Testing period: {start_time} to {end_time}')
        
        df = await get_cached_book_ticker_data(
            exchange='MEXC',
            symbol_base='F',
            symbol_quote='USDT',
            start_time=start_time,
            end_time=end_time
        )
        
        print(f'MEXC data: {len(df)} rows')
        if not df.empty:
            print(f'Time range: {df["timestamp"].min()} to {df["timestamp"].max()}')
    
    asyncio.run(test())