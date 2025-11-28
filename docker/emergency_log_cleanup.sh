#!/bin/bash

# Emergency Log Cleanup Script for CEX Arbitrage Production Data Collector
# This script safely cleans up large Docker container log files without stopping healthy containers
# 
# Usage: ./emergency_log_cleanup.sh [container_name_or_id]
# Example: ./emergency_log_cleanup.sh arbitrage_collector
# Example: ./emergency_log_cleanup.sh eea40728d716

set -euo pipefail

CONTAINER_ID_OR_NAME="${1:-arbitrage_collector}"
BACKUP_DIR="/tmp/docker_log_backups"
MAX_LOG_SIZE_MB=1024  # Alert if log file is larger than 1GB

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# Check if running as root (required for Docker log file access)
check_permissions() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root to access Docker log files"
        echo "Please run: sudo $0 $*"
        exit 1
    fi
}

# Verify container exists and is running
verify_container() {
    local container="$1"
    
    if ! docker inspect "$container" >/dev/null 2>&1; then
        error "Container '$container' not found"
        echo "Available containers:"
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Size}}"
        exit 1
    fi
    
    local status=$(docker inspect --format='{{.State.Status}}' "$container")
    if [[ "$status" != "running" ]]; then
        error "Container '$container' is not running (status: $status)"
        exit 1
    fi
    
    log "Container '$container' verified as running"
}

# Get container log file path
get_log_file_path() {
    local container="$1"
    local container_id
    local log_path
    
    # Get full container ID
    container_id=$(docker inspect --format='{{.Id}}' "$container")
    
    # Get log file path
    log_path="/var/lib/docker/containers/${container_id}/${container_id}-json.log"
    
    if [[ ! -f "$log_path" ]]; then
        error "Log file not found at: $log_path"
        exit 1
    fi
    
    echo "$log_path"
}

# Check log file size and warn if too large
check_log_size() {
    local log_path="$1"
    local size_mb
    
    if [[ ! -f "$log_path" ]]; then
        error "Log file does not exist: $log_path"
        return 1
    fi
    
    # Get file size in MB
    size_mb=$(du -m "$log_path" | cut -f1)
    
    log "Current log file size: ${size_mb}MB"
    
    if [[ $size_mb -gt $MAX_LOG_SIZE_MB ]]; then
        warn "Log file is large (${size_mb}MB > ${MAX_LOG_SIZE_MB}MB) - cleanup recommended"
        return 1
    fi
    
    return 0
}

# Create backup of current log (last 1000 lines for emergency reference)
backup_log_tail() {
    local log_path="$1"
    local container="$2"
    local backup_file
    
    mkdir -p "$BACKUP_DIR"
    backup_file="${BACKUP_DIR}/$(basename "$container")_$(date +%Y%m%d_%H%M%S)_tail.log"
    
    log "Creating backup of last 1000 log entries to: $backup_file"
    tail -n 1000 "$log_path" > "$backup_file"
    
    log "Backup created successfully"
}

# Safely truncate log file (preserves file handle)
truncate_log_file() {
    local log_path="$1"
    local original_size
    local new_size
    
    original_size=$(du -h "$log_path" | cut -f1)
    
    log "Original log file size: $original_size"
    log "Truncating log file: $log_path"
    
    # Use truncate to safely empty the file while preserving the file handle
    # This is safer than rm + touch as it doesn't break Docker's file handle
    truncate -s 0 "$log_path"
    
    new_size=$(du -h "$log_path" | cut -f1)
    log "New log file size: $new_size"
    
    # Verify truncation worked
    if [[ $(stat -c%s "$log_path") -eq 0 ]]; then
        log "Log file successfully truncated"
    else
        error "Log file truncation failed"
        return 1
    fi
}

# Test Docker logs command after cleanup
test_docker_logs() {
    local container="$1"
    
    log "Testing 'docker logs' command after cleanup..."
    
    # Test basic logs command
    if timeout 10 docker logs "$container" --tail 5 >/dev/null 2>&1; then
        log "✅ 'docker logs $container --tail 5' works correctly"
    else
        warn "❌ 'docker logs $container --tail 5' failed or timed out"
    fi
    
    # Test the problematic command that was hanging
    if timeout 10 docker logs "$container" -n 1 >/dev/null 2>&1; then
        log "✅ 'docker logs $container -n 1' works correctly"
    else
        warn "❌ 'docker logs $container -n 1' still failing or timing out"
    fi
}

# Show summary and recommendations
show_summary() {
    local container="$1"
    local log_path="$2"
    
    echo
    log "=== CLEANUP SUMMARY ==="
    log "Container: $container"
    log "Log file: $log_path"
    log "Current size: $(du -h "$log_path" | cut -f1)"
    log "Backup location: $BACKUP_DIR"
    
    echo
    log "=== RECOMMENDATIONS ==="
    log "1. Deploy log rotation configuration to prevent future issues:"
    log "   docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d"
    echo
    log "2. Monitor log rotation effectiveness:"
    log "   watch 'docker logs $container --tail 10'"
    echo
    log "3. Set up regular monitoring:"
    log "   ./log_rotation_monitor.sh $container"
}

# Main execution
main() {
    local container="$1"
    local log_path
    
    log "Starting emergency log cleanup for container: $container"
    
    # Verification steps
    check_permissions
    verify_container "$container"
    
    # Get log file path
    log_path=$(get_log_file_path "$container")
    log "Log file path: $log_path"
    
    # Check if cleanup is needed
    if check_log_size "$log_path"; then
        log "Log file size is acceptable - no cleanup needed"
        test_docker_logs "$container"
        exit 0
    fi
    
    # Perform cleanup
    warn "Proceeding with log cleanup..."
    
    # Create backup before cleanup
    backup_log_tail "$log_path" "$container"
    
    # Safely truncate log file
    truncate_log_file "$log_path"
    
    # Test Docker logs functionality
    test_docker_logs "$container"
    
    # Show summary
    show_summary "$container" "$log_path"
    
    log "Emergency log cleanup completed successfully!"
}

# Help function
show_help() {
    echo "Emergency Log Cleanup Script for Docker Containers"
    echo
    echo "Usage: $0 [container_name_or_id]"
    echo
    echo "Examples:"
    echo "  $0 arbitrage_collector"
    echo "  $0 eea40728d716"
    echo
    echo "This script:"
    echo "  - Verifies container is running"
    echo "  - Backs up last 1000 log entries"
    echo "  - Safely truncates large log files"
    echo "  - Tests Docker logs functionality"
    echo "  - Provides deployment recommendations"
    echo
    echo "Note: Must be run as root to access Docker log files"
}

# Handle command line arguments
if [[ $# -eq 0 ]] || [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    show_help
    exit 0
fi

# Execute main function
main "$@"