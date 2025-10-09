#!/bin/bash

# =============================================================================
# Database Space Monitoring and Automated Cleanup Script
# =============================================================================
# Monitors database space usage and performs automated cleanup when needed
# Run via cron: */30 * * * * /opt/arbitrage/docker/database_monitoring.sh

set -e

# Configuration
ALERT_THRESHOLD=90  # Alert when disk usage exceeds 90%
CLEANUP_THRESHOLD=95  # Start aggressive cleanup at 95%
LOG_FILE="/var/log/database_monitoring.log"
DB_CONTAINER="arbitrage_db"
DATA_COLLECTOR_CONTAINER="arbitrage_collector"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_message() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

get_disk_usage() {
    df / | tail -1 | awk '{print $5}' | sed 's/%//'
}

get_db_size() {
    docker exec "$DB_CONTAINER" psql -U arbitrage_user -d arbitrage_data -t -c \
        "SELECT pg_size_pretty(pg_database_size('arbitrage_data'));" 2>/dev/null | xargs || echo "Unknown"
}

get_table_stats() {
    docker exec "$DB_CONTAINER" psql -U arbitrage_user -d arbitrage_data -t -c \
        "SELECT COUNT(*) FROM book_ticker_snapshots;" 2>/dev/null | xargs || echo "0"
}

stop_data_collection() {
    log_message "${YELLOW}Stopping data collection to prevent further growth${NC}"
    docker stop "$DATA_COLLECTOR_CONTAINER" 2>/dev/null || true
}

start_data_collection() {
    log_message "${GREEN}Restarting data collection${NC}"
    cd /opt/arbitrage/docker
    docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d data_collector
}

emergency_cleanup() {
    log_message "${RED}EMERGENCY: Running aggressive cleanup (6-hour retention)${NC}"
    
    # Stop data collection immediately
    stop_data_collection
    
    # Emergency cleanup - keep only 6 hours
    docker exec "$DB_CONTAINER" psql -U arbitrage_user -d arbitrage_data -c \
        "DELETE FROM book_ticker_snapshots WHERE timestamp < NOW() - INTERVAL '6 hours';" || true
    
    docker exec "$DB_CONTAINER" psql -U arbitrage_user -d arbitrage_data -c \
        "DELETE FROM funding_rate_snapshots WHERE timestamp < NOW() - INTERVAL '12 hours';" || true
        
    log_message "${GREEN}Emergency cleanup completed${NC}"
}

regular_cleanup() {
    log_message "${BLUE}Running regular cleanup (24-hour retention)${NC}"
    
    # Regular cleanup - keep 24 hours
    docker exec "$DB_CONTAINER" psql -U arbitrage_user -d arbitrage_data -c \
        "DELETE FROM book_ticker_snapshots WHERE timestamp < NOW() - INTERVAL '24 hours';" || true
    
    docker exec "$DB_CONTAINER" psql -U arbitrage_user -d arbitrage_data -c \
        "DELETE FROM funding_rate_snapshots WHERE timestamp < NOW() - INTERVAL '7 days';" || true
        
    log_message "${GREEN}Regular cleanup completed${NC}"
}

# Main monitoring logic
main() {
    DISK_USAGE=$(get_disk_usage)
    DB_SIZE=$(get_db_size)
    RECORD_COUNT=$(get_table_stats)
    
    log_message "${BLUE}Monitoring: Disk ${DISK_USAGE}%, DB ${DB_SIZE}, Records ${RECORD_COUNT}${NC}"
    
    if [ "$DISK_USAGE" -ge "$CLEANUP_THRESHOLD" ]; then
        log_message "${RED}CRITICAL: Disk usage ${DISK_USAGE}% >= ${CLEANUP_THRESHOLD}%${NC}"
        emergency_cleanup
        
        # Wait and check if we need to restart collection
        sleep 10
        NEW_USAGE=$(get_disk_usage)
        if [ "$NEW_USAGE" -lt "$ALERT_THRESHOLD" ]; then
            start_data_collection
        fi
        
    elif [ "$DISK_USAGE" -ge "$ALERT_THRESHOLD" ]; then
        log_message "${YELLOW}WARNING: Disk usage ${DISK_USAGE}% >= ${ALERT_THRESHOLD}%${NC}"
        regular_cleanup
        
    else
        log_message "${GREEN}OK: Disk usage ${DISK_USAGE}% < ${ALERT_THRESHOLD}%${NC}"
        
        # Ensure data collection is running if space is good
        if ! docker ps | grep -q "$DATA_COLLECTOR_CONTAINER"; then
            start_data_collection
        fi
    fi
}

# Run monitoring
main "$@"