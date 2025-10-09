-- Automated Data Retention Policy
-- Implements safe data retention for production CEX arbitrage system
-- Run this daily via cron job

-- Configuration
-- book_ticker_snapshots: Keep 24 hours (for real-time arbitrage)
-- funding_rate_snapshots: Keep 7 days (for trend analysis)
-- arbitrage_opportunities: Keep 30 days (for performance analysis)

BEGIN;

-- Log retention operation
INSERT INTO collector_status (component, status, details, timestamp)
VALUES ('retention_policy', 'running', 'Starting automated data retention', NOW());

-- Store counts before cleanup
CREATE TEMP TABLE retention_stats AS
SELECT 
    'book_ticker_snapshots' as table_name,
    COUNT(*) as records_before,
    pg_total_relation_size('book_ticker_snapshots') as size_before
FROM book_ticker_snapshots
UNION ALL
SELECT 
    'funding_rate_snapshots',
    COUNT(*),
    pg_total_relation_size('funding_rate_snapshots')
FROM funding_rate_snapshots
UNION ALL
SELECT 
    'arbitrage_opportunities',
    COUNT(*),
    pg_total_relation_size('arbitrage_opportunities')
FROM arbitrage_opportunities;

-- Retention: book_ticker_snapshots (24 hours)
DELETE FROM book_ticker_snapshots 
WHERE timestamp < NOW() - INTERVAL '24 hours';

-- Retention: funding_rate_snapshots (7 days)
DELETE FROM funding_rate_snapshots 
WHERE timestamp < NOW() - INTERVAL '7 days';

-- Retention: arbitrage_opportunities (30 days)
DELETE FROM arbitrage_opportunities 
WHERE created_at < NOW() - INTERVAL '30 days';

-- Store counts after cleanup
CREATE TEMP TABLE retention_results AS
SELECT 
    'book_ticker_snapshots' as table_name,
    COUNT(*) as records_after,
    pg_total_relation_size('book_ticker_snapshots') as size_after
FROM book_ticker_snapshots
UNION ALL
SELECT 
    'funding_rate_snapshots',
    COUNT(*),
    pg_total_relation_size('funding_rate_snapshots')
FROM funding_rate_snapshots
UNION ALL
SELECT 
    'arbitrage_opportunities',
    COUNT(*),
    pg_total_relation_size('arbitrage_opportunities')
FROM arbitrage_opportunities;

-- Generate retention report
SELECT 
    rs.table_name,
    rs.records_before,
    rr.records_after,
    rs.records_before - rr.records_after as records_deleted,
    pg_size_pretty(rs.size_before) as size_before,
    pg_size_pretty(rr.size_after) as size_after
FROM retention_stats rs
JOIN retention_results rr ON rs.table_name = rr.table_name;

-- Update table statistics
ANALYZE book_ticker_snapshots;
ANALYZE funding_rate_snapshots;
ANALYZE arbitrage_opportunities;

-- Log completion
INSERT INTO collector_status (component, status, details, timestamp)
VALUES ('retention_policy', 'completed', 
        'Automated retention completed successfully', NOW());

COMMIT;

-- Recommendation: Run VACUUM during low-usage periods
-- VACUUM book_ticker_snapshots;
-- VACUUM funding_rate_snapshots;
-- VACUUM arbitrage_opportunities;