#!/bin/bash
# =============================================================================
# Daily Cleanup Script for CEX Arbitrage Database
# =============================================================================
# This script runs daily to maintain 3-day data retention and prevent disk overflow

set -e

LOG_FILE="/var/log/database_cleanup.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$DATE] Starting daily database cleanup..." | tee -a $LOG_FILE

# Function to log with timestamp
log() {
    echo "[$DATE] $1" | tee -a $LOG_FILE
}

# Check disk usage
DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
log "Current disk usage: ${DISK_USAGE}%"

if [ $DISK_USAGE -gt 90 ]; then
    log "⚠️  WARNING: Disk usage above 90% - running aggressive cleanup"
    RETENTION_HOURS=12
elif [ $DISK_USAGE -gt 80 ]; then
    log "📊 Disk usage above 80% - running standard cleanup"
    RETENTION_HOURS=24
else
    log "✅ Disk usage normal - running maintenance cleanup"
    RETENTION_HOURS=72  # 3 days
fi

# Database cleanup
log "🗑️  Cleaning data older than ${RETENTION_HOURS} hours..."

docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data << EOF 2>&1 | tee -a $LOG_FILE
-- Show data before cleanup
SELECT 
    'Before cleanup:' as status,
    COUNT(*) as records,
    pg_size_pretty(pg_total_relation_size('book_ticker_snapshots')) as table_size
FROM book_ticker_snapshots;

-- Delete old data
DELETE FROM book_ticker_snapshots 
WHERE timestamp < NOW() - INTERVAL '${RETENTION_HOURS} hours';

DELETE FROM trade_snapshots 
WHERE timestamp < NOW() - INTERVAL '${RETENTION_HOURS} hours';

DELETE FROM funding_rate_snapshots 
WHERE timestamp < NOW() - INTERVAL '7 days';  -- Keep funding rates longer

DELETE FROM order_flow_metrics 
WHERE timestamp < NOW() - INTERVAL '7 days';

DELETE FROM arbitrage_opportunities 
WHERE detected_at < NOW() - INTERVAL '14 days';

DELETE FROM collector_status 
WHERE timestamp < NOW() - INTERVAL '7 days';

-- Show data after cleanup
SELECT 
    'After cleanup:' as status,
    COUNT(*) as records,
    pg_size_pretty(pg_total_relation_size('book_ticker_snapshots')) as table_size
FROM book_ticker_snapshots;

-- Run maintenance
VACUUM ANALYZE book_ticker_snapshots;
VACUUM ANALYZE trade_snapshots;

-- Final database size
SELECT 
    'Final database size:' as metric,
    pg_size_pretty(pg_database_size('arbitrage_data')) as size;
EOF

# Check final disk usage
FINAL_DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
log "Final disk usage: ${FINAL_DISK_USAGE}%"

# Docker cleanup if still high usage
if [ $FINAL_DISK_USAGE -gt 85 ]; then
    log "🧹 Running Docker system cleanup..."
    docker system prune -f --volumes 2>&1 | tee -a $LOG_FILE
fi

log "✅ Daily cleanup completed successfully"

# Alert if usage is still critical
if [ $FINAL_DISK_USAGE -gt 95 ]; then
    log "🚨 CRITICAL: Disk usage still above 95% after cleanup!"
    # Optional: Send alert or stop data collection
fi

echo "[$DATE] Cleanup completed. Log: $LOG_FILE"