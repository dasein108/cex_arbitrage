#!/bin/bash

# PostgreSQL Connection Monitoring Script for HFT Trading System
# Monitors connection usage and provides alerts for connection limits

set -euo pipefail

# Configuration
DB_CONTAINER="arbitrage_db"
DB_USER="arbitrage_user"
DB_NAME="arbitrage_data"
ALERT_THRESHOLD=85  # Alert when connections exceed 85% of max

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to check if container is running
check_container() {
    if ! docker ps --filter "name=${DB_CONTAINER}" --format "{{.Names}}" | grep -q "${DB_CONTAINER}"; then
        echo -e "${RED}ERROR: PostgreSQL container '${DB_CONTAINER}' is not running${NC}"
        exit 1
    fi
}

# Function to get connection statistics
get_connection_stats() {
    docker exec ${DB_CONTAINER} psql -U ${DB_USER} -d ${DB_NAME} -t -c "
        SELECT 
            COUNT(*) as current_connections,
            (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') as max_connections,
            ROUND((COUNT(*)::numeric / (SELECT setting::int FROM pg_settings WHERE name = 'max_connections')) * 100, 2) as usage_percentage
        FROM pg_stat_activity;
    " | tr -d ' '
}

# Function to get detailed connection breakdown
get_connection_breakdown() {
    docker exec ${DB_CONTAINER} psql -U ${DB_USER} -d ${DB_NAME} -c "
        SELECT 
            state,
            COUNT(*) as count,
            ROUND((COUNT(*)::numeric / (SELECT COUNT(*) FROM pg_stat_activity)) * 100, 2) as percentage
        FROM pg_stat_activity 
        WHERE state IS NOT NULL
        GROUP BY state
        ORDER BY count DESC;
    "
}

# Function to get long-running connections
get_long_running() {
    docker exec ${DB_CONTAINER} psql -U ${DB_USER} -d ${DB_NAME} -c "
        SELECT 
            pid,
            usename,
            application_name,
            client_addr,
            state,
            EXTRACT(EPOCH FROM (now() - state_change))/60 as minutes_in_state,
            EXTRACT(EPOCH FROM (now() - backend_start))/60 as connection_age_minutes
        FROM pg_stat_activity 
        WHERE state IS NOT NULL
        AND EXTRACT(EPOCH FROM (now() - backend_start)) > 300  -- More than 5 minutes
        ORDER BY backend_start;
    "
}

# Function to display real-time monitoring
monitor_connections() {
    echo -e "${BLUE}=== PostgreSQL Connection Monitor ===${NC}"
    echo -e "${BLUE}Container: ${DB_CONTAINER}${NC}"
    echo -e "${BLUE}Database: ${DB_NAME}${NC}"
    echo -e "${BLUE}Alert Threshold: ${ALERT_THRESHOLD}%${NC}"
    echo ""
    
    while true; do
        clear
        echo -e "${BLUE}=== PostgreSQL Connection Monitor - $(date) ===${NC}"
        echo ""
        
        # Get current stats
        stats=$(get_connection_stats)
        current=$(echo "$stats" | cut -d'|' -f1)
        max_conn=$(echo "$stats" | cut -d'|' -f2)
        usage=$(echo "$stats" | cut -d'|' -f3)
        
        # Determine color based on usage
        if (( $(echo "$usage > $ALERT_THRESHOLD" | bc -l) )); then
            color=$RED
            status="ALERT"
        elif (( $(echo "$usage > 70" | bc -l) )); then
            color=$YELLOW
            status="WARNING"
        else
            color=$GREEN
            status="OK"
        fi
        
        echo -e "${color}Status: $status${NC}"
        echo -e "Current Connections: ${color}$current${NC}/$max_conn (${color}$usage%${NC})"
        echo ""
        
        echo -e "${BLUE}Connection Breakdown:${NC}"
        get_connection_breakdown
        echo ""
        
        echo -e "${BLUE}Long-running Connections (>5 min):${NC}"
        long_running_count=$(docker exec ${DB_CONTAINER} psql -U ${DB_USER} -d ${DB_NAME} -t -c "
            SELECT COUNT(*) FROM pg_stat_activity 
            WHERE state IS NOT NULL
            AND EXTRACT(EPOCH FROM (now() - backend_start)) > 300;
        " | tr -d ' ')
        
        if [ "$long_running_count" -gt 0 ]; then
            get_long_running
        else
            echo "No long-running connections"
        fi
        
        echo ""
        echo -e "${BLUE}Press Ctrl+C to stop monitoring${NC}"
        echo "Next update in 5 seconds..."
        
        sleep 5
    done
}

# Function to show current snapshot
show_snapshot() {
    echo -e "${BLUE}=== Connection Status Snapshot - $(date) ===${NC}"
    echo ""
    
    # Get current stats
    stats=$(get_connection_stats)
    current=$(echo "$stats" | cut -d'|' -f1)
    max_conn=$(echo "$stats" | cut -d'|' -f2)
    usage=$(echo "$stats" | cut -d'|' -f3)
    
    # Determine color based on usage
    if (( $(echo "$usage > $ALERT_THRESHOLD" | bc -l) )); then
        color=$RED
        status="ALERT"
    elif (( $(echo "$usage > 70" | bc -l) )); then
        color=$YELLOW
        status="WARNING"
    else
        color=$GREEN
        status="OK"
    fi
    
    echo -e "${color}Status: $status${NC}"
    echo -e "Current Connections: ${color}$current${NC}/$max_conn (${color}$usage%${NC})"
    echo ""
    
    echo -e "${BLUE}Connection Breakdown:${NC}"
    get_connection_breakdown
    echo ""
    
    # Show application-specific connections
    echo -e "${BLUE}Connections by Application:${NC}"
    docker exec ${DB_CONTAINER} psql -U ${DB_USER} -d ${DB_NAME} -c "
        SELECT 
            COALESCE(application_name, 'Unknown') as application,
            COUNT(*) as connections,
            ROUND((COUNT(*)::numeric / (SELECT COUNT(*) FROM pg_stat_activity)) * 100, 2) as percentage
        FROM pg_stat_activity 
        GROUP BY application_name
        ORDER BY connections DESC;
    "
}

# Main script logic
case "${1:-snapshot}" in
    "monitor")
        check_container
        monitor_connections
        ;;
    "snapshot")
        check_container
        show_snapshot
        ;;
    "breakdown")
        check_container
        echo -e "${BLUE}=== Detailed Connection Breakdown ===${NC}"
        get_connection_breakdown
        ;;
    "long-running")
        check_container
        echo -e "${BLUE}=== Long-running Connections ===${NC}"
        get_long_running
        ;;
    "help")
        echo "PostgreSQL Connection Monitoring Script"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  snapshot      Show current connection status (default)"
        echo "  monitor       Real-time connection monitoring"
        echo "  breakdown     Show connection state breakdown"
        echo "  long-running  Show connections older than 5 minutes"
        echo "  help          Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0                # Show current snapshot"
        echo "  $0 monitor       # Start real-time monitoring"
        echo "  $0 breakdown     # Show connection states"
        echo "  $0 long-running  # Show old connections"
        ;;
    *)
        echo -e "${RED}Error: Unknown command '$1'${NC}"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac