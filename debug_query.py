#!/usr/bin/env python3
"""Debug the SQL query construction."""

# Simulate the query building logic
exchange = "GATEIO_FUTURES"
symbol_base = "NEIROETH"
symbol_quote = "USDT"
limit = 10

where_conditions = []
params = []
param_counter = 1

if exchange:
    where_conditions.append(f"bts.exchange = ${param_counter}")
    params.append(exchange.upper())
    param_counter += 1

if symbol_base:
    where_conditions.append(f"bts.symbol_base = ${param_counter}")
    params.append(symbol_base.upper())
    param_counter += 1

if symbol_quote:
    where_conditions.append(f"bts.symbol_quote = ${param_counter}")
    params.append(symbol_quote.upper())
    param_counter += 1

params.append(limit)

where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

query = f"""
    SELECT 
        bts.timestamp,
        bts.exchange,
        bts.symbol_base,
        bts.symbol_quote,
        bts.bid_price::float as bid_price,
        bts.bid_qty::float as bid_qty,
        bts.ask_price::float as ask_price,
        bts.ask_qty::float as ask_qty,
        ((bts.bid_price + bts.ask_price) / 2.0)::float as mid_price,
        (((bts.ask_price - bts.bid_price) / ((bts.bid_price + bts.ask_price) / 2.0)) * 10000.0)::float as spread_bps
    FROM book_ticker_snapshots bts
    {where_clause}
    ORDER BY bts.timestamp DESC
    LIMIT ${param_counter}
"""

print("Generated query:")
print(query)
print(f"\nParameters: {params}")