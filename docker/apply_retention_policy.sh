#!/bin/bash
# =============================================================================
# Apply 3-day retention policy to production database
# =============================================================================

set -e

echo "🔧 Applying 3-day retention policy to production database..."
echo "=================================================="

# SSH connection details
SSH_KEY="~/.ssh/deploy_ci"
SSH_HOST="root@31.192.233.13"

# Create the SQL script for immediate application
cat > /tmp/retention_update.sql << 'EOF'
-- =============================================================================
-- IMMEDIATE RETENTION POLICY UPDATE - 3 DAYS
-- =============================================================================

\echo 'Starting retention policy update...'

-- Remove existing retention policies
SELECT remove_retention_policy('book_ticker_snapshots', if_exists => TRUE);
SELECT remove_retention_policy('orderbook_depth', if_exists => TRUE);
SELECT remove_retention_policy('trade_snapshots', if_exists => TRUE);
SELECT remove_retention_policy('funding_rate_snapshots', if_exists => TRUE);
SELECT remove_retention_policy('order_flow_metrics', if_exists => TRUE);
SELECT remove_retention_policy('arbitrage_opportunities', if_exists => TRUE);
SELECT remove_retention_policy('collector_status', if_exists => TRUE);

-- Add new retention policies with reduced periods
SELECT add_retention_policy('book_ticker_snapshots', INTERVAL '3 days', if_not_exists => TRUE);
SELECT add_retention_policy('orderbook_depth', INTERVAL '3 days', if_not_exists => TRUE);
SELECT add_retention_policy('trade_snapshots', INTERVAL '3 days', if_not_exists => TRUE);
SELECT add_retention_policy('funding_rate_snapshots', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('order_flow_metrics', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('arbitrage_opportunities', INTERVAL '14 days', if_not_exists => TRUE);
SELECT add_retention_policy('collector_status', INTERVAL '7 days', if_not_exists => TRUE);

\echo 'Retention policies updated successfully!'

-- Show current policies
\echo 'Current retention policies:'
SELECT 
    hypertable_name,
    config->>'drop_after' as retention_period
FROM timescaledb_information.jobs
WHERE job_type = 'drop_chunks'
ORDER BY hypertable_name;

-- Drop old chunks immediately to free space
\echo 'Dropping old chunks (this may take a while)...'

-- Get space usage before cleanup
SELECT 
    'Before cleanup:' as status,
    pg_size_pretty(pg_database_size('arbitrage_data')) as database_size;

-- Drop old chunks for each table
SELECT drop_chunks('book_ticker_snapshots', older_than => INTERVAL '3 days');
SELECT drop_chunks('orderbook_depth', older_than => INTERVAL '3 days');
SELECT drop_chunks('trade_snapshots', older_than => INTERVAL '3 days');
SELECT drop_chunks('funding_rate_snapshots', older_than => INTERVAL '7 days');
SELECT drop_chunks('order_flow_metrics', older_than => INTERVAL '7 days');
SELECT drop_chunks('arbitrage_opportunities', older_than => INTERVAL '14 days');
SELECT drop_chunks('collector_status', older_than => INTERVAL '7 days');

-- Vacuum to reclaim space
\echo 'Running VACUUM to reclaim space...'
VACUUM ANALYZE;

-- Get space usage after cleanup
SELECT 
    'After cleanup:' as status,
    pg_size_pretty(pg_database_size('arbitrage_data')) as database_size;

-- Show chunk statistics
\echo 'Chunk statistics after cleanup:'
SELECT 
    hypertable_name,
    COUNT(*) as chunk_count,
    pg_size_pretty(SUM(total_bytes)) as total_size
FROM timescaledb_information.chunks
GROUP BY hypertable_name
ORDER BY SUM(total_bytes) DESC;

\echo 'Retention policy update and cleanup completed!'
EOF

echo "📋 SQL script created at /tmp/retention_update.sql"

# Copy the script to the server
echo "📤 Copying script to server..."
scp -i $SSH_KEY /tmp/retention_update.sql $SSH_HOST:/tmp/retention_update.sql

# Execute the script on the server
echo "🚀 Executing retention policy update on production database..."
ssh -i $SSH_KEY $SSH_HOST << 'REMOTE_COMMANDS'
    # Run the SQL script
    docker exec -i arbitrage_db psql -U arbitrage_user -d arbitrage_data < /tmp/retention_update.sql
    
    # Check disk usage after cleanup
    echo ""
    echo "📊 Disk usage after retention policy update:"
    df -h /opt/arbitrage
    
    # Clean up temp file
    rm /tmp/retention_update.sql
    
    echo ""
    echo "✅ Retention policy successfully applied!"
REMOTE_COMMANDS

# Clean up local temp file
rm /tmp/retention_update.sql

echo ""
echo "🎉 Retention policy update completed successfully!"
echo ""
echo "📋 Summary:"
echo "  - Main data tables: 3 days retention"
echo "  - Funding rates: 7 days retention"
echo "  - Analytics data: 7-14 days retention"
echo ""
echo "💡 Next steps:"
echo "  1. Monitor disk usage over next 24 hours"
echo "  2. Verify data collection continues normally"
echo "  3. Update docker/init-db.sql for future deployments"