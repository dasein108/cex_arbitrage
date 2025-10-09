-- Emergency Database Cleanup Script
-- Safe data retention for CEX arbitrage system
-- Keeps only last 12 hours of data to free up space immediately

-- Step 1: Check current data status
\echo 'Current database status:'
SELECT 
    pg_size_pretty(pg_database_size('arbitrage_data')) as db_size,
    pg_size_pretty(pg_total_relation_size('book_ticker_snapshots')) as book_ticker_size;

SELECT COUNT(*) as total_records, 
       MIN(timestamp) as oldest, 
       MAX(timestamp) as newest 
FROM book_ticker_snapshots;

-- Step 2: Delete data older than 12 hours (aggressive cleanup)
\echo 'Deleting data older than 12 hours...'
DELETE FROM book_ticker_snapshots 
WHERE timestamp < NOW() - INTERVAL '12 hours';

-- Step 3: Check results
\echo 'After cleanup:'
SELECT COUNT(*) as remaining_records, 
       MIN(timestamp) as oldest, 
       MAX(timestamp) as newest 
FROM book_ticker_snapshots;

-- Step 4: Clean up other tables if they exist
DELETE FROM funding_rate_snapshots 
WHERE timestamp < NOW() - INTERVAL '24 hours';

DELETE FROM arbitrage_opportunities 
WHERE created_at < NOW() - INTERVAL '24 hours';

-- Step 5: Update table statistics
ANALYZE book_ticker_snapshots;
ANALYZE funding_rate_snapshots;
ANALYZE arbitrage_opportunities;

\echo 'Emergency cleanup completed.'
\echo 'Next step: Run VACUUM during low-usage periods to reclaim disk space.'