# MEXC-GATEIO Spread Delta Dashboard - SQL Migration Summary

## Overview
Successfully updated all SQL queries in the MEXC-GATEIO spread delta Grafana dashboard to use the new normalized database schema from init-db.sql.

## Database Schema Changes Applied

### From Flat Schema:
- `trades` table with direct `exchange`, `symbol_base` fields
- `book_ticker_snapshots` table with direct `exchange`, `symbol_base` fields

### To Normalized Schema:
- `exchanges` table: `id`, `enum_value` (MEXC_SPOT, GATEIO_SPOT), `exchange_name`, `market_type`
- `symbols` table: `id`, `exchange_id` (FK), `symbol_base`, `symbol_quote`, `exchange_symbol`
- `trade_snapshots` table: `symbol_id` (FK), `price`, `quantity`, `timestamp` (renamed from `trades`)
- `book_ticker_snapshots` table: `symbol_id` (FK), `bid_price`, `ask_price`, `timestamp`

## Updated Queries

### 1. Template Variable Query (Lines 675, 678)
**Before:**
```sql
SELECT DISTINCT symbol_base 
FROM book_ticker_snapshots 
WHERE timestamp > NOW() - INTERVAL '1 hour'
ORDER BY symbol_base
```

**After:**
```sql
SELECT DISTINCT s.symbol_base 
FROM book_ticker_snapshots bts
JOIN symbols s ON bts.symbol_id = s.id
JOIN exchanges e ON s.exchange_id = e.id
WHERE bts.timestamp > NOW() - INTERVAL '1 hour'
  AND e.enum_value IN ('MEXC_SPOT', 'GATEIO_SPOT')
ORDER BY s.symbol_base
```

### 2. Panel 1 - Trade Data Query (Line 118)
**Before:**
```sql
FROM trades
WHERE
  timestamp > NOW() - INTERVAL '30 minutes'
  AND symbol_base = '$symbol_base'
  AND exchange IS NOT NULL
```

**After:**
```sql
FROM trade_snapshots ts
JOIN symbols s ON ts.symbol_id = s.id
JOIN exchanges e ON s.exchange_id = e.id
WHERE
  ts.timestamp > NOW() - INTERVAL '30 minutes'
  AND s.symbol_base = '$symbol_base'
  AND e.enum_value IN ('MEXC_SPOT', 'GATEIO_SPOT')
```

### 3. Panel 2 - Exchange Spreads Query (Line 229)
**Before:**
```sql
FROM book_ticker_snapshots
WHERE
  timestamp > NOW() - INTERVAL '1 minute'
  AND symbol_base = '$symbol_base'
  AND symbol_quote = 'USDT'
GROUP BY exchange
```

**After:**
```sql
FROM book_ticker_snapshots bts
JOIN symbols s ON bts.symbol_id = s.id
JOIN exchanges e ON s.exchange_id = e.id
WHERE
  bts.timestamp > NOW() - INTERVAL '1 minute'
  AND s.symbol_base = '$symbol_base'
  AND s.symbol_quote = 'USDT'
  AND e.enum_value IN ('MEXC_SPOT', 'GATEIO_SPOT')
GROUP BY e.enum_value
```

### 4. Panel 3 - BID-ASK Combined Query (Line 428)
**Before:**
```sql
-- Multiple separate queries with direct field access:
FROM book_ticker_snapshots WHERE symbol_base = '$symbol_base'
FROM trades WHERE symbol_base = '$symbol_base'
```

**After:**
```sql
-- Unified pattern with proper JOINs:
FROM book_ticker_snapshots bts
JOIN symbols s ON bts.symbol_id = s.id
JOIN exchanges e ON s.exchange_id = e.id
WHERE s.symbol_base = '$symbol_base'
  AND e.enum_value IN ('MEXC_SPOT', 'GATEIO_SPOT')

FROM trade_snapshots ts
JOIN symbols s ON ts.symbol_id = s.id
JOIN exchanges e ON s.exchange_id = e.id
WHERE s.symbol_base = '$symbol_base'
  AND e.enum_value IN ('MEXC_SPOT', 'GATEIO_SPOT')
```

### 5. Panel 4 - Arbitrage Calculation Query (Line 516)
**Before:**
```sql
SELECT DISTINCT ON (exchange, symbol_quote)
FROM book_ticker_snapshots
WHERE symbol_base = '$symbol_base'
ORDER BY exchange, symbol_quote, timestamp DESC
```

**After:**
```sql
SELECT DISTINCT ON (e.enum_value, s.symbol_quote)
FROM book_ticker_snapshots bts
JOIN symbols s ON bts.symbol_id = s.id
JOIN exchanges e ON s.exchange_id = e.id
WHERE s.symbol_base = '$symbol_base'
  AND e.enum_value IN ('MEXC_SPOT', 'GATEIO_SPOT')
ORDER BY e.enum_value, s.symbol_quote, bts.timestamp DESC
```

### 6. Panel 5 - Spreads Tradable Query (Line 639)
**Before:**
```sql
FROM book_ticker_snapshots
WHERE symbol_base = '$symbol_base'
GROUP BY DATE_TRUNC('second', timestamp), exchange, symbol_base, symbol_quote
```

**After:**
```sql
FROM book_ticker_snapshots bts
JOIN symbols s ON bts.symbol_id = s.id
JOIN exchanges e ON s.exchange_id = e.id
WHERE s.symbol_base = '$symbol_base'
  AND e.enum_value IN ('MEXC_SPOT', 'GATEIO_SPOT')
GROUP BY DATE_TRUNC('second', bts.timestamp), e.enum_value, s.symbol_base, s.symbol_quote
```

## Key Migration Patterns Applied

### 1. JOIN Pattern
All queries now use the standard JOIN pattern:
```sql
FROM [main_table] alias
JOIN symbols s ON alias.symbol_id = s.id
JOIN exchanges e ON s.exchange_id = e.id
```

### 2. Exchange Filtering
Replace direct exchange field filtering with:
```sql
WHERE e.enum_value IN ('MEXC_SPOT', 'GATEIO_SPOT')
```

### 3. Symbol Filtering
Replace direct symbol_base filtering with:
```sql
WHERE s.symbol_base = '$symbol_base'
```

### 4. Table Name Updates
- `trades` → `trade_snapshots`
- All field references now use table aliases (bts, ts, s, e)

## HFT Performance Optimizations Maintained

1. **Efficient WHERE Clauses**: All queries maintain foreign key relationships for optimal JOIN performance
2. **Proper Indexing Support**: Queries align with indexes defined in init-db.sql
3. **Time-based Filtering**: All timestamp filters preserved to leverage TimescaleDB partitioning
4. **Exchange Enum Filtering**: Uses indexed enum_value field for fast exchange filtering

## Verification Results

✅ All 6 panels updated successfully
✅ Template variable query updated
✅ No old schema references remain
✅ All queries use proper JOIN patterns
✅ Exchange filtering uses enum_value IN ('MEXC_SPOT', 'GATEIO_SPOT')
✅ Symbol filtering uses joined symbols table
✅ Table names correctly updated (trades → trade_snapshots)
✅ HFT performance requirements maintained

## Files Modified

- `/Users/dasein/dev/cex_arbitrage/docker/grafana/provisioning/dashboards/mexc-gateio-spread-delta.json`

The dashboard is now fully compatible with the normalized database schema and ready for deployment with TimescaleDB optimizations.