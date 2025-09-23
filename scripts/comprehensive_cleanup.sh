#!/bin/bash
# =============================================================================
# Comprehensive Cleanup and Reset Procedures for CEX Arbitrage System
# =============================================================================
# This script provides step-by-step cleanup procedures for various scenarios
# including emergency cleanup, system reset, and database migration

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"
BACKUP_DIR="${PROJECT_ROOT}/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/cleanup_${TIMESTAMP}.log"

# Database settings
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-arbitrage_data}"
DB_USER="${DB_USER:-arbitrage_user}"
DB_PASSWORD="${DB_PASSWORD:-}"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Create directories
mkdir -p "$LOG_DIR" "$BACKUP_DIR"

# Logging functions
log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

log_info() { log "INFO" "${BLUE}$*${NC}"; }
log_warn() { log "WARN" "${YELLOW}$*${NC}"; }
log_error() { log "ERROR" "${RED}$*${NC}"; }
log_success() { log "SUCCESS" "${GREEN}$*${NC}"; }
log_header() { 
    echo -e "\n${CYAN}============================================================${NC}"
    echo -e "${CYAN}$*${NC}"
    echo -e "${CYAN}============================================================${NC}"
    log "HEADER" "$*"
}

# Function to check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if Docker is available
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        return 1
    fi
    
    # Check if PostgreSQL client is available
    if ! command -v psql &> /dev/null; then
        log_error "PostgreSQL client (psql) is not installed"
        return 1
    fi
    
    # Check if bc is available for calculations
    if ! command -v bc &> /dev/null; then
        log_error "bc calculator is not installed"
        return 1
    fi
    
    log_success "Prerequisites check passed"
}

# Function to check current system status
check_system_status() {
    log_header "SYSTEM STATUS CHECK"
    
    # Disk usage
    local disk_usage=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
    log_info "Current disk usage: ${disk_usage}%"
    
    # Database status
    if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c '\q' 2>/dev/null; then
        local db_size=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "
            SELECT ROUND(pg_database_size('$DB_NAME') / 1024.0 / 1024.0 / 1024.0, 2);
        " 2>/dev/null | xargs || echo "0")
        log_info "Database accessible, size: ${db_size}GB"
    else
        log_warn "Database not accessible"
    fi
    
    # Docker status
    if docker system df &> /dev/null; then
        log_info "Docker system usage:"
        docker system df | tee -a "$LOG_FILE"
    else
        log_warn "Docker not accessible"
    fi
    
    # Available space
    local available_gb=$(df / | awk 'NR==2 {print $4}' | awk '{print int($1/1024/1024)}')
    log_info "Available disk space: ${available_gb}GB"
    
    if [[ "$disk_usage" -gt 95 ]]; then
        log_error "CRITICAL: Disk usage above 95%!"
        return 1
    elif [[ "$disk_usage" -gt 90 ]]; then
        log_warn "WARNING: Disk usage above 90%"
    fi
    
    return 0
}

# Function to create backup of essential data
create_backup() {
    local backup_type="${1:-minimal}"  # minimal, essential, full
    
    log_header "CREATING BACKUP - TYPE: $backup_type"
    
    local backup_file="${BACKUP_DIR}/backup_${backup_type}_${TIMESTAMP}.sql"
    
    case "$backup_type" in
        "minimal")
            log_info "Creating minimal backup (last 6 hours of data)"
            PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" \
                --table=book_ticker_snapshots \
                --where="timestamp > NOW() - INTERVAL '6 hours'" \
                --no-owner --no-privileges > "$backup_file" 2>>"$LOG_FILE"
            ;;
        "essential")
            log_info "Creating essential backup (last 24 hours + config)"
            PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" \
                --exclude-table=orderbook_depth \
                --exclude-table=trades \
                --where="timestamp > NOW() - INTERVAL '24 hours'" \
                --no-owner --no-privileges > "$backup_file" 2>>"$LOG_FILE"
            ;;
        "full")
            log_info "Creating full database backup"
            PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" \
                --no-owner --no-privileges > "$backup_file" 2>>"$LOG_FILE"
            ;;
    esac
    
    if [[ -f "$backup_file" ]] && [[ -s "$backup_file" ]]; then
        local backup_size=$(du -sh "$backup_file" | cut -f1)
        log_success "Backup created: $backup_file (${backup_size})"
        
        # Compress backup to save space
        gzip "$backup_file"
        log_success "Backup compressed: ${backup_file}.gz"
        
        echo "$backup_file.gz"
        return 0
    else
        log_error "Backup creation failed"
        return 1
    fi
}

# Function for emergency database cleanup
emergency_database_cleanup() {
    log_header "EMERGENCY DATABASE CLEANUP"
    
    log_warn "This will aggressively remove data to free space!"
    
    # Create minimal backup first
    if ! create_backup "minimal"; then
        log_error "Backup failed, aborting emergency cleanup"
        return 1
    fi
    
    # Set ultra-aggressive retention
    log_info "Setting emergency retention policies..."
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" <<EOF 2>>"$LOG_FILE"
-- Remove existing retention policies
SELECT remove_retention_policy('book_ticker_snapshots', true);
SELECT remove_retention_policy('orderbook_depth', true);
SELECT remove_retention_policy('trades', true);
SELECT remove_retention_policy('arbitrage_opportunities', true);
SELECT remove_retention_policy('order_flow_metrics', true);

-- Set emergency retention (6 hours for critical data)
SELECT add_retention_policy('book_ticker_snapshots', INTERVAL '6 hours');
SELECT add_retention_policy('orderbook_depth', INTERVAL '2 hours');
SELECT add_retention_policy('trades', INTERVAL '2 hours');
SELECT add_retention_policy('arbitrage_opportunities', INTERVAL '12 hours');
SELECT add_retention_policy('order_flow_metrics', INTERVAL '1 hour');

-- Force immediate execution of retention policies
SELECT run_job(job_id) FROM timescaledb_information.jobs WHERE proc_name = 'policy_retention';
EOF
    
    # Drop non-essential tables
    log_info "Dropping non-essential tables..."
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" <<EOF 2>>"$LOG_FILE"
-- Drop continuous aggregates (can be recreated)
DROP MATERIALIZED VIEW IF EXISTS book_ticker_1min CASCADE;

-- Drop analytics tables (non-critical for trading)
DROP TABLE IF EXISTS collector_status CASCADE;

-- Truncate old arbitrage opportunities
DELETE FROM arbitrage_opportunities WHERE detected_at < NOW() - INTERVAL '6 hours';
EOF
    
    # Aggressive vacuum
    log_info "Running aggressive vacuum..."
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" <<EOF 2>>"$LOG_FILE"
VACUUM FULL ANALYZE;
REINDEX DATABASE arbitrage_data;
EOF
    
    log_success "Emergency database cleanup completed"
}

# Function for complete Docker cleanup
complete_docker_cleanup() {
    log_header "COMPLETE DOCKER CLEANUP"
    
    log_warn "This will remove ALL Docker data except running containers!"
    
    if ! command -v docker &> /dev/null; then
        log_warn "Docker not available, skipping Docker cleanup"
        return 0
    fi
    
    # Stop all containers except database
    log_info "Stopping non-essential containers..."
    docker ps --format "{{.Names}}" | grep -v "arbitrage_db" | while read -r container; do
        if [[ -n "$container" ]]; then
            log_info "Stopping container: $container"
            docker stop "$container" >> "$LOG_FILE" 2>&1 || log_warn "Failed to stop $container"
        fi
    done
    
    # Remove all stopped containers
    log_info "Removing stopped containers..."
    docker container prune -f >> "$LOG_FILE" 2>&1 || log_warn "Container prune failed"
    
    # Remove all unused images
    log_info "Removing unused images..."
    docker image prune -a -f >> "$LOG_FILE" 2>&1 || log_warn "Image prune failed"
    
    # Remove all unused volumes (except named volumes for database)
    log_info "Removing unused volumes..."
    docker volume prune -f >> "$LOG_FILE" 2>&1 || log_warn "Volume prune failed"
    
    # Remove all unused networks
    log_info "Removing unused networks..."
    docker network prune -f >> "$LOG_FILE" 2>&1 || log_warn "Network prune failed"
    
    # Clean build cache
    log_info "Cleaning build cache..."
    if docker buildx version &> /dev/null; then
        docker buildx prune -a -f >> "$LOG_FILE" 2>&1 || log_warn "Build cache prune failed"
    fi
    
    # System prune (final cleanup)
    log_info "Final system cleanup..."
    docker system prune -a -f >> "$LOG_FILE" 2>&1 || log_warn "System prune failed"
    
    log_success "Docker cleanup completed"
}

# Function for nuclear option - complete system reset
nuclear_reset() {
    log_header "NUCLEAR RESET - COMPLETE SYSTEM CLEANUP"
    
    log_error "WARNING: This will destroy ALL data except backups!"
    log_error "This action is IRREVERSIBLE!"
    
    read -p "Type 'NUCLEAR' to confirm complete system reset: " confirmation
    if [[ "$confirmation" != "NUCLEAR" ]]; then
        log_info "Reset cancelled by user"
        return 1
    fi
    
    # Create essential backup
    log_info "Creating essential backup before reset..."
    local backup_file
    if backup_file=$(create_backup "essential"); then
        log_success "Backup created: $backup_file"
    else
        log_error "Backup failed. Aborting nuclear reset."
        return 1
    fi
    
    # Stop all containers
    log_info "Stopping all containers..."
    docker stop $(docker ps -q) 2>/dev/null || true
    
    # Remove all containers
    log_info "Removing all containers..."
    docker rm $(docker ps -aq) 2>/dev/null || true
    
    # Remove all images
    log_info "Removing all images..."
    docker rmi $(docker images -q) -f 2>/dev/null || true
    
    # Remove all volumes
    log_info "Removing all volumes..."
    docker volume rm $(docker volume ls -q) 2>/dev/null || true
    
    # System prune
    log_info "Docker system prune..."
    docker system prune -a -f --volumes 2>/dev/null || true
    
    # Clean overlay2 storage (if running as root)
    if [[ "$EUID" -eq 0 ]]; then
        local docker_root=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo "/var/lib/docker")
        if [[ -d "$docker_root/overlay2" ]]; then
            log_info "Cleaning overlay2 storage..."
            rm -rf "$docker_root/overlay2"/* 2>/dev/null || true
        fi
    fi
    
    # Recreate database with optimized schema
    log_info "Recreating database with optimized schema..."
    cd "$PROJECT_ROOT"
    docker-compose up -d database
    
    # Wait for database to be ready
    log_info "Waiting for database to be ready..."
    sleep 30
    
    # Apply optimized schema
    if [[ -f "$SCRIPT_DIR/optimized_schema.sql" ]]; then
        log_info "Applying optimized schema..."
        PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
            -f "$SCRIPT_DIR/optimized_schema.sql" >> "$LOG_FILE" 2>&1
    fi
    
    log_success "Nuclear reset completed. System rebuilt with optimized configuration."
}

# Function to restore from backup
restore_from_backup() {
    local backup_file="$1"
    
    log_header "RESTORING FROM BACKUP: $backup_file"
    
    if [[ ! -f "$backup_file" ]]; then
        log_error "Backup file not found: $backup_file"
        return 1
    fi
    
    # Extract if compressed
    local restore_file="$backup_file"
    if [[ "$backup_file" == *.gz ]]; then
        restore_file="${backup_file%.gz}"
        gunzip -c "$backup_file" > "$restore_file"
    fi
    
    # Restore database
    log_info "Restoring database from backup..."
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        < "$restore_file" >> "$LOG_FILE" 2>&1
    
    if [[ "$?" -eq 0 ]]; then
        log_success "Database restored successfully"
        
        # Clean up temporary file
        if [[ "$backup_file" == *.gz ]] && [[ -f "$restore_file" ]]; then
            rm "$restore_file"
        fi
        
        return 0
    else
        log_error "Database restore failed"
        return 1
    fi
}

# Function to optimize existing database
optimize_existing_database() {
    log_header "OPTIMIZING EXISTING DATABASE"
    
    # Create backup first
    local backup_file
    if backup_file=$(create_backup "essential"); then
        log_success "Backup created: $backup_file"
    else
        log_error "Backup failed. Aborting optimization."
        return 1
    fi
    
    # Apply optimizations
    log_info "Applying database optimizations..."
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" <<EOF 2>>"$LOG_FILE"
-- Enable compression on existing hypertables
ALTER TABLE book_ticker_snapshots SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'exchange, symbol_base, symbol_quote',
    timescaledb.compress_orderby = 'timestamp'
);

-- Add compression policy
SELECT add_compression_policy('book_ticker_snapshots', INTERVAL '2 hours', if_not_exists => true);

-- Update retention policies to be more aggressive
SELECT remove_retention_policy('book_ticker_snapshots', true);
SELECT add_retention_policy('book_ticker_snapshots', INTERVAL '24 hours');

SELECT remove_retention_policy('orderbook_depth', true);
SELECT add_retention_policy('orderbook_depth', INTERVAL '12 hours');

SELECT remove_retention_policy('trades', true);
SELECT add_retention_policy('trades', INTERVAL '12 hours');

-- Force compression of old chunks
SELECT compress_chunk(chunk_name)
FROM timescaledb_information.chunks
WHERE NOT is_compressed
AND range_end < NOW() - INTERVAL '2 hours';

-- Vacuum and analyze
VACUUM ANALYZE;
EOF
    
    log_success "Database optimization completed"
}

# Main menu function
show_menu() {
    echo -e "\n${CYAN}=== CEX ARBITRAGE CLEANUP & RESET MENU ===${NC}"
    echo "1. System Status Check"
    echo "2. Create Backup (Essential Data)"
    echo "3. Emergency Database Cleanup"
    echo "4. Complete Docker Cleanup"
    echo "5. Optimize Existing Database"
    echo "6. Nuclear Reset (DANGEROUS)"
    echo "7. Restore from Backup"
    echo "8. Automated Maintenance Check"
    echo "9. Exit"
    echo -e "${YELLOW}Choose an option (1-9):${NC}"
}

# Interactive mode
interactive_mode() {
    log_header "INTERACTIVE CLEANUP MODE"
    
    while true; do
        show_menu
        read -p "> " choice
        
        case $choice in
            1)
                check_system_status
                ;;
            2)
                create_backup "essential"
                ;;
            3)
                echo -e "${YELLOW}WARNING: This will aggressively remove data!${NC}"
                read -p "Continue? (y/N): " confirm
                if [[ "$confirm" =~ ^[Yy]$ ]]; then
                    emergency_database_cleanup
                fi
                ;;
            4)
                echo -e "${YELLOW}WARNING: This will remove all Docker data except running containers!${NC}"
                read -p "Continue? (y/N): " confirm
                if [[ "$confirm" =~ ^[Yy]$ ]]; then
                    complete_docker_cleanup
                fi
                ;;
            5)
                optimize_existing_database
                ;;
            6)
                nuclear_reset
                ;;
            7)
                echo "Available backups:"
                ls -la "$BACKUP_DIR"/*.sql.gz 2>/dev/null || echo "No backups found"
                read -p "Enter backup file path: " backup_path
                if [[ -f "$backup_path" ]]; then
                    restore_from_backup "$backup_path"
                else
                    log_error "Backup file not found"
                fi
                ;;
            8)
                if [[ -f "$SCRIPT_DIR/automated_maintenance.sh" ]]; then
                    "$SCRIPT_DIR/automated_maintenance.sh" check
                else
                    log_error "Automated maintenance script not found"
                fi
                ;;
            9)
                log_info "Exiting cleanup menu"
                break
                ;;
            *)
                echo -e "${RED}Invalid option. Please choose 1-9.${NC}"
                ;;
        esac
        
        echo -e "\n${BLUE}Press Enter to continue...${NC}"
        read
    done
}

# Main execution
main() {
    local action="${1:-interactive}"
    
    log_header "CEX ARBITRAGE COMPREHENSIVE CLEANUP"
    
    # Check prerequisites
    if ! check_prerequisites; then
        exit 1
    fi
    
    # Execute based on action
    case "$action" in
        "status")
            check_system_status
            ;;
        "backup")
            create_backup "${2:-essential}"
            ;;
        "emergency")
            emergency_database_cleanup
            ;;
        "docker")
            complete_docker_cleanup
            ;;
        "optimize")
            optimize_existing_database
            ;;
        "nuclear")
            nuclear_reset
            ;;
        "restore")
            if [[ -n "${2:-}" ]]; then
                restore_from_backup "$2"
            else
                log_error "Backup file path required for restore"
                exit 1
            fi
            ;;
        "interactive"|*)
            interactive_mode
            ;;
    esac
    
    log_success "Cleanup script completed. Log file: $LOG_FILE"
}

# Execute main function
main "$@"