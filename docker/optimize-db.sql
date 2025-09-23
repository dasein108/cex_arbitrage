-- =============================================================================
-- Database Optimization Script for 4GB Server
-- =============================================================================
-- Optimizations for the CEX arbitrage database to reduce disk usage
-- and improve performance on resource-constrained servers

-- 1. Enable compression on TimescaleDB hypertables (significant space savings)
SELECT compress_chunk(chunk) FROM timescaledb_information.chunks
WHERE hypertable_name = 'book_ticker_snapshots' AND NOT is_compressed;

SELECT compress_chunk(chunk) FROM timescaledb_information.chunks  
WHERE hypertable_name = 'orderbook_depth' AND NOT is_compressed;

SELECT compress_chunk(chunk) FROM timescaledb_information.chunks
WHERE hypertable_name = 'trades' AND NOT is_compressed;

-- 2. Set up automatic compression policies (compress data older than 1 hour)
SELECT add_compression_policy('book_ticker_snapshots', INTERVAL '1 hour', if_not_exists => true);
SELECT add_compression_policy('orderbook_depth', INTERVAL '1 hour', if_not_exists => true);
SELECT add_compression_policy('trades', INTERVAL '1 hour', if_not_exists => true);

-- 3. Optimize chunk intervals for smaller server (reduce overhead)
SELECT set_chunk_time_interval('book_ticker_snapshots', INTERVAL '15 minutes');
SELECT set_chunk_time_interval('orderbook_depth', INTERVAL '15 minutes');
SELECT set_chunk_time_interval('trades', INTERVAL '15 minutes');

-- 4. Reduce data retention for space savings (3 days instead of 7)
SELECT remove_retention_policy('book_ticker_snapshots', if_exists => true);
SELECT remove_retention_policy('orderbook_depth', if_exists => true);
SELECT remove_retention_policy('trades', if_exists => true);

SELECT add_retention_policy('book_ticker_snapshots', INTERVAL '3 days');
SELECT add_retention_policy('orderbook_depth', INTERVAL '3 days');
SELECT add_retention_policy('trades', INTERVAL '3 days');

-- 5. Optimize numeric precision (reduce storage requirements)
-- These changes would require table recreation, so commented out for safety
-- ALTER TABLE book_ticker_snapshots 
--   ALTER COLUMN bid_price TYPE NUMERIC(16,6),
--   ALTER COLUMN ask_price TYPE NUMERIC(16,6),
--   ALTER COLUMN bid_qty TYPE NUMERIC(16,4),
--   ALTER COLUMN ask_qty TYPE NUMERIC(16,4);

-- 6. Clean up old data immediately
DELETE FROM book_ticker_snapshots WHERE timestamp < NOW() - INTERVAL '3 days';
DELETE FROM orderbook_depth WHERE timestamp < NOW() - INTERVAL '3 days';
DELETE FROM trades WHERE timestamp < NOW() - INTERVAL '3 days';

-- 7. Vacuum and analyze for immediate space reclaim
VACUUM FULL book_ticker_snapshots;
VACUUM FULL orderbook_depth;
VACUUM FULL trades;
ANALYZE;

-- 8. Show compression and space savings
SELECT 
    hypertable_name,
    pg_size_pretty(before_compression_total_bytes) as before_compression,
    pg_size_pretty(after_compression_total_bytes) as after_compression,
    ROUND(100 - (after_compression_total_bytes::float / before_compression_total_bytes::float * 100), 2) as compression_ratio
FROM timescaledb_information.hypertable_compression_stats
WHERE before_compression_total_bytes > 0;