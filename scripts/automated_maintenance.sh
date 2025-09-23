#!/bin/bash
# =============================================================================
# Automated Maintenance Script for CEX Arbitrage Database
# =============================================================================
# This script provides automated maintenance for PostgreSQL and Docker
# to prevent space consumption issues from recurring

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/../logs"
LOG_FILE="${LOG_DIR}/maintenance_$(date +%Y%m%d_%H%M%S).log"
CONFIG_FILE="${SCRIPT_DIR}/maintenance_config.conf"

# Database connection settings (can be overridden in config file)
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-arbitrage_data}"
DB_USER="${DB_USER:-arbitrage_user}"
DB_PASSWORD="${DB_PASSWORD:-}"

# Maintenance thresholds
DISK_USAGE_THRESHOLD=${DISK_USAGE_THRESHOLD:-85}  # Trigger cleanup at 85% disk usage
DB_SIZE_THRESHOLD_GB=${DB_SIZE_THRESHOLD_GB:-8}   # Trigger cleanup at 8GB database size
DOCKER_SIZE_THRESHOLD_GB=${DOCKER_SIZE_THRESHOLD_GB:-10} # Trigger Docker cleanup at 10GB

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Logging function
log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

log_info() { log "INFO" "$@"; }
log_warn() { log "WARN" "$@"; }
log_error() { log "ERROR" "$@"; }
log_success() { log "SUCCESS" "$@"; }

# Load configuration if exists
if [[ -f "$CONFIG_FILE" ]]; then
    source "$CONFIG_FILE"
    log_info "Loaded configuration from $CONFIG_FILE"
fi

# Function to check if PostgreSQL is accessible
check_postgres() {
    if command -v psql &> /dev/null; then
        if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c '\q' 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

# Function to execute SQL with error handling
execute_sql() {
    local sql="$1"
    local description="$2"
    
    log_info "Executing: $description"
    if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "$sql" >> "$LOG_FILE" 2>&1; then
        log_success "$description completed"
        return 0
    else
        log_error "$description failed"
        return 1
    fi
}

# Function to get current disk usage percentage
get_disk_usage() {
    df / | awk 'NR==2 {print $5}' | sed 's/%//'
}

# Function to get database size in GB
get_db_size_gb() {
    if check_postgres; then
        PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "
            SELECT ROUND(pg_database_size('$DB_NAME') / 1024.0 / 1024.0 / 1024.0, 2);
        " 2>/dev/null | xargs || echo "0"
    else
        echo "0"
    fi
}

# Function to get Docker system size in GB
get_docker_size_gb() {
    if command -v docker &> /dev/null && docker system df &> /dev/null; then
        docker system df --format "{{.Size}}" | grep -o '[0-9.]*GB' | sed 's/GB//' | awk '{sum += $1} END {print sum}' || echo "0"
    else
        echo "0"
    fi
}

# =============================================================================
# DATABASE MAINTENANCE FUNCTIONS
# =============================================================================

# Function to run database vacuum and analyze
vacuum_database() {
    log_info "Starting database vacuum and analyze"
    
    local tables=("book_ticker_snapshots" "orderbook_depth" "trades" "arbitrage_opportunities" "order_flow_metrics")
    
    for table in "${tables[@]}"; do
        # Check if table exists
        local table_exists=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_name = '$table' AND table_schema = 'public';
        " 2>/dev/null | xargs || echo "0")
        
        if [[ "$table_exists" -gt 0 ]]; then
            execute_sql "VACUUM ANALYZE $table;" "Vacuum and analyze $table"
        else
            log_warn "Table $table does not exist, skipping"
        fi
    done
}

# Function to compress old chunks (TimescaleDB)
compress_old_chunks() {
    log_info "Starting chunk compression"
    
    execute_sql "
        SELECT compress_chunk(chunk_name)
        FROM timescaledb_information.chunks
        WHERE NOT is_compressed
        AND range_end < NOW() - INTERVAL '2 hours';
    " "Compress old chunks"
}

# Function to manually trigger retention policies
trigger_retention() {
    log_info "Triggering retention policies"
    
    execute_sql "
        SELECT job_id, hypertable_name, config, next_start
        FROM timescaledb_information.jobs 
        WHERE proc_name = 'policy_retention';
    " "Check retention policies"
    
    # Force run retention jobs
    execute_sql "
        SELECT run_job(job_id)
        FROM timescaledb_information.jobs 
        WHERE proc_name = 'policy_retention';
    " "Force run retention policies"
}

# Function to clean up temporary and dead tuples
cleanup_dead_tuples() {
    log_info "Cleaning up dead tuples"
    
    execute_sql "
        SELECT schemaname, tablename, n_dead_tup, n_live_tup,
               ROUND(100.0 * n_dead_tup / GREATEST(n_live_tup + n_dead_tup, 1), 2) as dead_pct
        FROM pg_stat_user_tables 
        WHERE n_dead_tup > 1000
        ORDER BY n_dead_tup DESC;
    " "Analyze dead tuple statistics"
    
    # Run VACUUM on tables with high dead tuple percentage
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "
        SELECT 'VACUUM ' || schemaname || '.' || tablename || ';'
        FROM pg_stat_user_tables 
        WHERE n_dead_tup > 1000 
        AND ROUND(100.0 * n_dead_tup / GREATEST(n_live_tup + n_dead_tup, 1), 2) > 20;
    " 2>/dev/null | while read -r vacuum_cmd; do
        if [[ -n "$vacuum_cmd" ]]; then
            execute_sql "$vacuum_cmd" "Vacuum table with high dead tuple ratio"
        fi
    done
}

# Function for emergency database cleanup
emergency_db_cleanup() {
    log_warn "Performing emergency database cleanup"
    
    # Set very aggressive retention (12 hours for emergency)
    execute_sql "
        SELECT remove_retention_policy('book_ticker_snapshots', true);
        SELECT add_retention_policy('book_ticker_snapshots', INTERVAL '12 hours');
    " "Set emergency 12-hour retention for book_ticker_snapshots"
    
    execute_sql "
        SELECT remove_retention_policy('orderbook_depth', true);
        SELECT add_retention_policy('orderbook_depth', INTERVAL '6 hours');
    " "Set emergency 6-hour retention for orderbook_depth"
    
    execute_sql "
        SELECT remove_retention_policy('trades', true);
        SELECT add_retention_policy('trades', INTERVAL '6 hours');
    " "Set emergency 6-hour retention for trades"
    
    # Force immediate retention cleanup
    trigger_retention
    
    # Aggressive vacuum
    execute_sql "VACUUM FULL;" "Emergency full vacuum"
}

# =============================================================================
# DOCKER MAINTENANCE FUNCTIONS
# =============================================================================

# Function to clean Docker system
docker_cleanup() {
    log_info "Starting Docker cleanup"
    
    if ! command -v docker &> /dev/null; then
        log_warn "Docker not found, skipping Docker cleanup"
        return 0
    fi
    
    # Remove dangling images
    log_info "Removing dangling Docker images"
    docker image prune -f >> "$LOG_FILE" 2>&1 || log_warn "Failed to prune dangling images"
    
    # Remove unused volumes
    log_info "Removing unused Docker volumes"
    docker volume prune -f >> "$LOG_FILE" 2>&1 || log_warn "Failed to prune unused volumes"
    
    # Remove unused networks
    log_info "Removing unused Docker networks"
    docker network prune -f >> "$LOG_FILE" 2>&1 || log_warn "Failed to prune unused networks"
    
    # Remove stopped containers older than 24 hours
    log_info "Removing old stopped containers"
    docker container prune -f --filter "until=24h" >> "$LOG_FILE" 2>&1 || log_warn "Failed to prune old containers"
    
    # Clean build cache
    if docker buildx version &> /dev/null; then
        log_info "Cleaning Docker build cache"
        docker buildx prune -f >> "$LOG_FILE" 2>&1 || log_warn "Failed to clean build cache"
    fi
}

# Function for aggressive Docker cleanup
emergency_docker_cleanup() {
    log_warn "Performing emergency Docker cleanup"
    
    if ! command -v docker &> /dev/null; then
        log_warn "Docker not found, skipping emergency Docker cleanup"
        return 0
    fi
    
    # Stop all non-essential containers (keep database running)
    log_info "Stopping non-essential containers"
    docker ps --format "{{.Names}}" | grep -v "arbitrage_db" | while read -r container; do
        if [[ -n "$container" ]]; then
            log_info "Stopping container: $container"
            docker stop "$container" >> "$LOG_FILE" 2>&1 || log_warn "Failed to stop $container"
        fi
    done
    
    # Aggressive system cleanup (removes everything except running containers)
    log_info "Performing aggressive Docker system cleanup"
    docker system prune -a -f >> "$LOG_FILE" 2>&1 || log_warn "Failed to perform aggressive Docker cleanup"
    
    # Clean overlay2 storage (requires root access)
    if [[ "$EUID" -eq 0 ]]; then
        log_info "Cleaning Docker overlay2 storage"
        docker_root=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo "/var/lib/docker")
        if [[ -d "$docker_root/overlay2" ]]; then
            find "$docker_root/overlay2" -name "diff" -type d -empty -delete 2>/dev/null || log_warn "Failed to clean empty overlay2 directories"
        fi
    else
        log_warn "Not running as root, skipping overlay2 cleanup"
    fi
}

# =============================================================================
# MONITORING AND ALERTING FUNCTIONS
# =============================================================================

# Function to check system health and trigger appropriate actions
check_and_maintain() {
    log_info "=== Starting automated maintenance check ==="
    log_info "Maintenance thresholds - Disk: ${DISK_USAGE_THRESHOLD}%, DB: ${DB_SIZE_THRESHOLD_GB}GB, Docker: ${DOCKER_SIZE_THRESHOLD_GB}GB"
    
    # Get current system status
    local disk_usage=$(get_disk_usage)
    local db_size=$(get_db_size_gb)
    local docker_size=$(get_docker_size_gb)
    
    log_info "Current status - Disk usage: ${disk_usage}%, DB size: ${db_size}GB, Docker size: ${docker_size}GB"
    
    # Determine maintenance level needed
    local emergency_mode=false
    local maintenance_needed=false
    
    # Check for emergency conditions (disk > 95% or DB > 12GB)
    if [[ "$disk_usage" -gt 95 ]] || [[ "$(echo "$db_size > 12" | bc -l)" == "1" ]]; then
        emergency_mode=true
        log_error "EMERGENCY: Critical disk usage detected!"
    # Check for regular maintenance conditions
    elif [[ "$disk_usage" -gt "$DISK_USAGE_THRESHOLD" ]] || 
         [[ "$(echo "$db_size > $DB_SIZE_THRESHOLD_GB" | bc -l)" == "1" ]] || 
         [[ "$(echo "$docker_size > $DOCKER_SIZE_THRESHOLD_GB" | bc -l)" == "1" ]]; then
        maintenance_needed=true
        log_warn "Maintenance thresholds exceeded, starting cleanup"
    fi
    
    # Execute appropriate maintenance level
    if [[ "$emergency_mode" == true ]]; then
        log_error "=== EMERGENCY MAINTENANCE MODE ==="
        
        # Emergency database cleanup
        if check_postgres; then
            emergency_db_cleanup
        else
            log_error "Cannot connect to database for emergency cleanup!"
        fi
        
        # Emergency Docker cleanup
        emergency_docker_cleanup
        
    elif [[ "$maintenance_needed" == true ]]; then
        log_info "=== REGULAR MAINTENANCE MODE ==="
        
        # Regular database maintenance
        if check_postgres; then
            compress_old_chunks
            trigger_retention
            vacuum_database
            cleanup_dead_tuples
        else
            log_warn "Cannot connect to database, skipping database maintenance"
        fi
        
        # Regular Docker cleanup
        docker_cleanup
        
    else
        log_info "=== MONITORING MODE ==="
        log_success "System within normal parameters, no maintenance needed"
        return 0
    fi
    
    # Check results after maintenance
    local new_disk_usage=$(get_disk_usage)
    local new_db_size=$(get_db_size_gb)
    local new_docker_size=$(get_docker_size_gb)
    
    log_info "Post-maintenance status - Disk usage: ${new_disk_usage}%, DB size: ${new_db_size}GB, Docker size: ${new_docker_size}GB"
    
    # Calculate improvements
    local disk_improvement=$((disk_usage - new_disk_usage))
    local db_improvement=$(echo "$db_size - $new_db_size" | bc -l)
    local docker_improvement=$(echo "$docker_size - $new_docker_size" | bc -l)
    
    log_success "Maintenance complete - Freed ${disk_improvement}% disk, ${db_improvement}GB database, ${docker_improvement}GB Docker"
    
    # Check if emergency intervention is still needed
    if [[ "$new_disk_usage" -gt 95 ]]; then
        log_error "CRITICAL: Disk usage still above 95% after maintenance. Manual intervention required!"
        return 1
    fi
    
    return 0
}

# =============================================================================
# CRON JOB INSTALLATION
# =============================================================================

install_cron_job() {
    local cron_schedule="${1:-*/15 * * * *}"  # Default: every 15 minutes
    
    log_info "Installing maintenance cron job with schedule: $cron_schedule"
    
    # Create cron job entry
    local cron_job="$cron_schedule $SCRIPT_DIR/automated_maintenance.sh check >> $LOG_DIR/cron_maintenance.log 2>&1"
    
    # Add to crontab (avoid duplicates)
    (crontab -l 2>/dev/null | grep -v "automated_maintenance.sh"; echo "$cron_job") | crontab -
    
    log_success "Cron job installed. Use 'crontab -l' to verify."
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

main() {
    local action="${1:-check}"
    
    case "$action" in
        "check")
            check_and_maintain
            ;;
        "emergency")
            log_warn "Manual emergency maintenance triggered"
            emergency_db_cleanup
            emergency_docker_cleanup
            ;;
        "vacuum")
            if check_postgres; then
                vacuum_database
            else
                log_error "Cannot connect to database"
                exit 1
            fi
            ;;
        "docker")
            docker_cleanup
            ;;
        "install-cron")
            install_cron_job "$2"
            ;;
        "status")
            log_info "System Status Check"
            log_info "Disk usage: $(get_disk_usage)%"
            log_info "Database size: $(get_db_size_gb)GB"
            log_info "Docker size: $(get_docker_size_gb)GB"
            ;;
        *)
            echo "Usage: $0 {check|emergency|vacuum|docker|install-cron [schedule]|status}"
            echo ""
            echo "Commands:"
            echo "  check         - Check thresholds and perform maintenance if needed"
            echo "  emergency     - Force emergency cleanup (aggressive)"
            echo "  vacuum        - Run database vacuum and analyze only"
            echo "  docker        - Run Docker cleanup only"
            echo "  install-cron  - Install cron job (optionally specify schedule)"
            echo "  status        - Show current system status"
            echo ""
            echo "Examples:"
            echo "  $0 check                    # Regular maintenance check"
            echo "  $0 emergency                # Emergency cleanup"
            echo "  $0 install-cron '0 */6 * * *'  # Install cron job (every 6 hours)"
            exit 1
            ;;
    esac
}

# Execute main function with all arguments
main "$@"