-- Comprehensive PostgreSQL Space Analysis
-- Deep analysis of space consumption for HFT arbitrage database

\echo '🔍 COMPREHENSIVE DATABASE SPACE ANALYSIS'
\echo '========================================'

-- Overall database statistics
\echo '1. DATABASE OVERVIEW'
\echo '==================='
SELECT 
    current_database() as database_name,
    pg_size_pretty(pg_database_size(current_database())) as total_size,
    (SELECT COUNT(*) FROM timescaledb_information.hypertables) as hypertables_count,
    (SELECT COUNT(*) FROM timescaledb_information.chunks) as total_chunks
;

-- Table-by-table space analysis
\echo ''
\echo '2. TABLE SPACE BREAKDOWN'
\echo '======================='
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) as table_size,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) as index_size,
    pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
FROM pg_tables 
WHERE schemaname NOT IN ('information_schema', 'pg_catalog', 'timescaledb_information', 'timescaledb_catalog')
ORDER BY size_bytes DESC;

-- Row count analysis
\echo ''
\echo '3. ROW COUNT ANALYSIS'
\echo '===================='
\echo 'Checking row counts for all main tables...'

DO $$
DECLARE
    table_name TEXT;
    row_count BIGINT;
    table_size TEXT;
BEGIN
    FOR table_name IN 
        SELECT tablename FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename IN ('book_ticker_snapshots', 'trades', 'orderbook_depth', 'arbitrage_opportunities', 'order_flow_metrics')
    LOOP
        EXECUTE format('SELECT COUNT(*) FROM %I', table_name) INTO row_count;
        EXECUTE format('SELECT pg_size_pretty(pg_total_relation_size(%L))', table_name) INTO table_size;
        RAISE NOTICE 'Table: % | Rows: % | Size: %', table_name, row_count, table_size;
    END LOOP;
END $$;

-- Chunk analysis for hypertables
\echo ''
\echo '4. TIMESCALEDB CHUNK ANALYSIS'
\echo '============================='
SELECT 
    hypertable_name,
    COUNT(*) as chunk_count,
    pg_size_pretty(SUM(total_bytes)) as total_size,
    pg_size_pretty(AVG(total_bytes)) as avg_chunk_size,
    MIN(range_start) as oldest_data,
    MAX(range_end) as newest_data,
    MAX(range_end) - MIN(range_start) as data_span
FROM timescaledb_information.chunks
GROUP BY hypertable_name
ORDER BY SUM(total_bytes) DESC;

-- Largest chunks
\echo ''
\echo '5. LARGEST CHUNKS'
\echo '================='
SELECT 
    hypertable_name,
    chunk_name,
    pg_size_pretty(total_bytes) as size,
    range_start,
    range_end,
    range_end - range_start as chunk_span
FROM timescaledb_information.chunks
ORDER BY total_bytes DESC
LIMIT 20;

-- Index space analysis
\echo ''
\echo '6. INDEX SPACE ANALYSIS'
\echo '======================'
SELECT 
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size,
    pg_relation_size(indexrelid) as size_bytes
FROM pg_stat_user_indexes 
JOIN pg_class ON pg_class.oid = indexrelid
ORDER BY size_bytes DESC
LIMIT 20;

-- Data freshness analysis
\echo ''
\echo '7. DATA FRESHNESS ANALYSIS'
\echo '=========================='
\echo 'Analyzing data age and distribution...'

-- Book ticker snapshots freshness
SELECT 
    'book_ticker_snapshots' as table_name,
    COUNT(*) as total_rows,
    MIN(timestamp) as oldest_data,
    MAX(timestamp) as newest_data,
    COUNT(*) FILTER (WHERE timestamp > NOW() - INTERVAL '1 hour') as last_1h,
    COUNT(*) FILTER (WHERE timestamp > NOW() - INTERVAL '6 hours') as last_6h,
    COUNT(*) FILTER (WHERE timestamp > NOW() - INTERVAL '24 hours') as last_24h,
    COUNT(*) FILTER (WHERE timestamp > NOW() - INTERVAL '3 days') as last_3d,
    COUNT(*) FILTER (WHERE timestamp <= NOW() - INTERVAL '3 days') as older_than_3d
FROM book_ticker_snapshots
WHERE EXISTS (SELECT 1 FROM book_ticker_snapshots LIMIT 1);

-- Trades freshness
SELECT 
    'trades' as table_name,
    COUNT(*) as total_rows,
    MIN(timestamp) as oldest_data,
    MAX(timestamp) as newest_data,
    COUNT(*) FILTER (WHERE timestamp > NOW() - INTERVAL '1 hour') as last_1h,
    COUNT(*) FILTER (WHERE timestamp > NOW() - INTERVAL '6 hours') as last_6h,
    COUNT(*) FILTER (WHERE timestamp > NOW() - INTERVAL '24 hours') as last_24h,
    COUNT(*) FILTER (WHERE timestamp > NOW() - INTERVAL '3 days') as last_3d,
    COUNT(*) FILTER (WHERE timestamp <= NOW() - INTERVAL '3 days') as older_than_3d
FROM trades
WHERE EXISTS (SELECT 1 FROM trades LIMIT 1);

-- Retention policy analysis
\echo ''
\echo '8. RETENTION POLICY STATUS'
\echo '========================='
SELECT 
    hypertable_name,
    job_id,
    config,
    schedule_interval,
    last_run_started_at,
    next_start,
    job_status
FROM timescaledb_information.jobs 
WHERE proc_name = 'policy_retention'
ORDER BY hypertable_name;

-- Compression analysis
\echo ''
\echo '9. COMPRESSION ANALYSIS'
\echo '======================'
SELECT 
    hypertable_name,
    COUNT(*) as total_chunks,
    COUNT(*) FILTER (WHERE is_compressed = true) as compressed_chunks,
    ROUND((COUNT(*) FILTER (WHERE is_compressed = true)::numeric / COUNT(*)) * 100, 2) as compression_ratio_pct,
    pg_size_pretty(SUM(total_bytes) FILTER (WHERE is_compressed = false)) as uncompressed_size,
    pg_size_pretty(SUM(compressed_total_size) FILTER (WHERE is_compressed = true)) as compressed_size
FROM timescaledb_information.chunks
GROUP BY hypertable_name
ORDER BY COUNT(*) DESC;

-- Continuous aggregates analysis
\echo ''
\echo '10. CONTINUOUS AGGREGATES ANALYSIS'
\echo '=================================='
SELECT 
    view_name,
    view_owner,
    pg_size_pretty(pg_total_relation_size(view_name)) as view_size,
    refresh_lag,
    compression_enabled
FROM timescaledb_information.continuous_aggregates;

-- Exchange and symbol distribution
\echo ''
\echo '11. DATA DISTRIBUTION ANALYSIS'
\echo '============================='
\echo 'Exchange distribution in book_ticker_snapshots:'
SELECT 
    exchange,
    COUNT(*) as row_count,
    MIN(timestamp) as oldest,
    MAX(timestamp) as newest,
    COUNT(DISTINCT symbol_base||symbol_quote) as unique_symbols
FROM book_ticker_snapshots
GROUP BY exchange
ORDER BY row_count DESC;

\echo ''
\echo 'Symbol distribution (top 20):'
SELECT 
    symbol_base||'/'||symbol_quote as symbol,
    COUNT(*) as row_count,
    COUNT(DISTINCT exchange) as exchanges,
    pg_size_pretty(COUNT(*) * 200) as estimated_size -- rough estimate
FROM book_ticker_snapshots
GROUP BY symbol_base, symbol_quote
ORDER BY row_count DESC
LIMIT 20;

-- WAL and temp file analysis
\echo ''
\echo '12. WAL AND TEMP FILE ANALYSIS'
\echo '=============================='
\echo 'Note: WAL analysis requires filesystem access'

-- Database bloat estimation
\echo ''
\echo '13. DATABASE BLOAT ESTIMATION'
\echo '============================'
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size,
    CASE 
        WHEN pg_stat_get_live_tuples(c.oid) > 0 THEN
            ROUND((pg_stat_get_dead_tuples(c.oid)::numeric / pg_stat_get_live_tuples(c.oid)) * 100, 2)
        ELSE 0
    END as bloat_ratio_pct,
    pg_stat_get_dead_tuples(c.oid) as dead_tuples,
    pg_stat_get_live_tuples(c.oid) as live_tuples
FROM pg_tables t
JOIN pg_class c ON c.relname = t.tablename
WHERE t.schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Space recommendations
\echo ''
\echo '14. SPACE OPTIMIZATION RECOMMENDATIONS'
\echo '====================================='
\echo 'Based on the analysis above:'

DO $$
DECLARE
    total_db_size_bytes BIGINT;
    book_ticker_size_bytes BIGINT;
    trades_size_bytes BIGINT;
    old_data_est BIGINT;
BEGIN
    SELECT pg_database_size(current_database()) INTO total_db_size_bytes;
    
    SELECT pg_total_relation_size('book_ticker_snapshots') INTO book_ticker_size_bytes;
    SELECT pg_total_relation_size('trades') INTO trades_size_bytes;
    
    RAISE NOTICE 'CURRENT SITUATION:';
    RAISE NOTICE '- Total database size: %', pg_size_pretty(total_db_size_bytes);
    RAISE NOTICE '- Book ticker snapshots: %', pg_size_pretty(book_ticker_size_bytes);
    RAISE NOTICE '- Trades table: %', pg_size_pretty(trades_size_bytes);
    
    RAISE NOTICE '';
    RAISE NOTICE 'IMMEDIATE ACTIONS RECOMMENDED:';
    
    IF total_db_size_bytes > 8 * 1024 * 1024 * 1024 THEN -- 8GB
        RAISE NOTICE '🚨 CRITICAL: Database exceeds 8GB - immediate cleanup required';
        RAISE NOTICE '  1. Drop data older than 24 hours';
        RAISE NOTICE '  2. Enable aggressive compression';
        RAISE NOTICE '  3. Reduce chunk intervals to 15 minutes';
    ELSIF total_db_size_bytes > 5 * 1024 * 1024 * 1024 THEN -- 5GB
        RAISE NOTICE '⚠️  WARNING: Database approaching limits';
        RAISE NOTICE '  1. Set 3-day retention policy';
        RAISE NOTICE '  2. Enable compression for data > 2 hours old';
        RAISE NOTICE '  3. Remove unnecessary indexes';
    ELSE
        RAISE NOTICE '✅ Database size within acceptable limits';
    END IF;
    
    -- Calculate potential space savings
    SELECT COUNT(*) * 200 INTO old_data_est -- rough estimate
    FROM book_ticker_snapshots 
    WHERE timestamp < NOW() - INTERVAL '24 hours';
    
    IF old_data_est > 0 THEN
        RAISE NOTICE '';
        RAISE NOTICE 'POTENTIAL SPACE SAVINGS:';
        RAISE NOTICE '- Remove data >24h old: ~%', pg_size_pretty(old_data_est);
        RAISE NOTICE '- Enable compression: ~70%% of remaining data';
        RAISE NOTICE '- Optimize schema: ~25%% reduction';
    END IF;
END $$;

\echo ''
\echo '🏁 ANALYSIS COMPLETE'
\echo 'Next steps: Review recommendations and execute appropriate cleanup procedures'