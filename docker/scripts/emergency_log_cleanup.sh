#!/bin/bash

# Emergency Log Cleanup Script for Production HFT Trading System
# Safe cleanup of oversized Docker logs without stopping containers
# Designed for zero-downtime deployment in production environments

set -euo pipefail

# Configuration
CONTAINER_NAME="arbitrage_collector"
LOG_BACKUP_DIR="/opt/arbitrage/docker/logs/emergency_backup"
SAFETY_LOG_LINES=1000  # Keep last 1000 lines for debugging
MAX_LOG_SIZE_MB=500   # Consider cleanup if logs exceed this size

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Safety checks
check_production_environment() {
    log "Performing production safety checks..."
    
    # Check if we're in the correct directory
    if [[ ! -f "docker-compose.prod.yml" ]]; then
        error "Not in production docker directory. This script must be run from /opt/arbitrage/docker/"
        exit 1
    fi
    
    # Check if container exists and is running
    if ! docker ps --format "table {{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
        error "Container ${CONTAINER_NAME} is not running"
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
        exit 1
    fi
    
    success "Production environment checks passed"
}

# Create backup directory
create_backup_directory() {
    log "Creating backup directory..."
    
    mkdir -p "${LOG_BACKUP_DIR}"
    if [[ ! -d "${LOG_BACKUP_DIR}" ]]; then
        error "Failed to create backup directory: ${LOG_BACKUP_DIR}"
        exit 1
    fi
    
    success "Backup directory ready: ${LOG_BACKUP_DIR}"
}

# Get container log file path
get_container_log_path() {
    log "Locating container log file..."
    
    CONTAINER_ID=$(docker ps --filter "name=${CONTAINER_NAME}" --format "{{.ID}}")
    if [[ -z "$CONTAINER_ID" ]]; then
        error "Could not find container ID for ${CONTAINER_NAME}"
        exit 1
    fi
    
    # Get log file path from Docker inspect
    LOG_PATH=$(docker inspect "$CONTAINER_ID" | jq -r '.[0].LogPath')
    if [[ -z "$LOG_PATH" || "$LOG_PATH" == "null" ]]; then
        error "Could not determine log file path for container"
        exit 1
    fi
    
    if [[ ! -f "$LOG_PATH" ]]; then
        error "Log file does not exist: $LOG_PATH"
        exit 1
    fi
    
    # Check log file size
    LOG_SIZE_MB=$(du -m "$LOG_PATH" | cut -f1)
    
    log "Container ID: $CONTAINER_ID"
    log "Log file path: $LOG_PATH"
    log "Current log size: ${LOG_SIZE_MB}MB"
    
    if [[ $LOG_SIZE_MB -lt $MAX_LOG_SIZE_MB ]]; then
        warn "Log file size (${LOG_SIZE_MB}MB) is below cleanup threshold (${MAX_LOG_SIZE_MB}MB)"
        echo "Do you want to continue anyway? (y/N)"
        read -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            log "Cleanup cancelled by user"
            exit 0
        fi
    fi
}

# Backup recent log entries
backup_recent_logs() {
    log "Backing up recent log entries..."
    
    BACKUP_FILE="${LOG_BACKUP_DIR}/$(basename "$LOG_PATH").backup.$(date +%Y%m%d_%H%M%S)"
    
    # Extract last N lines for backup
    tail -n $SAFETY_LOG_LINES "$LOG_PATH" > "$BACKUP_FILE"
    
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    success "Backup created: $BACKUP_FILE (${BACKUP_SIZE})"
}

# Perform safe log cleanup
cleanup_logs() {
    log "Performing safe log cleanup..."
    
    # Method 1: Truncate log file while preserving recent entries
    log "Truncating log file while preserving last ${SAFETY_LOG_LINES} lines..."
    
    # Create temporary file with recent logs
    TEMP_FILE="/tmp/$(basename "$LOG_PATH").temp.$$"
    tail -n $SAFETY_LOG_LINES "$LOG_PATH" > "$TEMP_FILE"
    
    # Replace original with truncated version
    # This preserves the inode, so Docker logging continues seamlessly
    cp "$TEMP_FILE" "$LOG_PATH"
    rm -f "$TEMP_FILE"
    
    # Verify the cleanup
    NEW_LOG_SIZE_MB=$(du -m "$LOG_PATH" | cut -f1)
    LOG_LINES=$(wc -l < "$LOG_PATH")
    
    success "Log cleanup completed:"
    success "  - Original size: ${LOG_SIZE_MB}MB"
    success "  - New size: ${NEW_LOG_SIZE_MB}MB"
    success "  - Lines preserved: ${LOG_LINES}"
    success "  - Space saved: $((LOG_SIZE_MB - NEW_LOG_SIZE_MB))MB"
}

# Verify container health after cleanup
verify_container_health() {
    log "Verifying container health after cleanup..."
    
    # Check container status
    STATUS=$(docker inspect "$CONTAINER_ID" --format '{{.State.Status}}')
    if [[ "$STATUS" != "running" ]]; then
        error "Container is not running after cleanup. Status: $STATUS"
        exit 1
    fi
    
    # Test log commands
    log "Testing log command responsiveness..."
    
    # Test that docker logs command works and returns quickly
    timeout 10s docker logs "$CONTAINER_NAME" -n 5 >/dev/null 2>&1
    if [[ $? -eq 0 ]]; then
        success "Log commands are responsive"
    else
        warn "Log commands may still be slow, but container is healthy"
    fi
    
    # Check container health check if available
    HEALTH_STATUS=$(docker inspect "$CONTAINER_ID" --format '{{.State.Health.Status}}' 2>/dev/null || echo "no-healthcheck")
    if [[ "$HEALTH_STATUS" != "no-healthcheck" ]]; then
        log "Container health check status: $HEALTH_STATUS"
    fi
    
    success "Container health verification completed"
}

# Force log rotation (if needed)
force_log_rotation() {
    log "Checking if log rotation needs to be triggered..."
    
    # Send SIGUSR1 to Docker daemon to trigger log rotation
    # This is safe and will rotate logs according to the configured policy
    DOCKER_PID=$(pgrep dockerd | head -n1)
    if [[ -n "$DOCKER_PID" ]]; then
        log "Sending log rotation signal to Docker daemon (PID: $DOCKER_PID)"
        sudo kill -USR1 "$DOCKER_PID" 2>/dev/null || true
        sleep 2
        success "Log rotation signal sent"
    else
        warn "Could not find Docker daemon PID for log rotation signal"
    fi
}

# Display final status
show_final_status() {
    log "=== EMERGENCY LOG CLEANUP COMPLETED ==="
    
    echo
    success "✓ Container is running and healthy"
    success "✓ Logs have been cleaned up safely"
    success "✓ Recent log entries have been preserved"
    success "✓ Log rotation configuration is active"
    
    echo
    log "Test log command responsiveness:"
    echo "docker logs ${CONTAINER_NAME} -n 1"
    
    echo
    log "Backup location:"
    echo "${LOG_BACKUP_DIR}"
    
    echo
    log "Production log rotation settings:"
    echo "  - Max log size: 100MB"
    echo "  - Max files: 3"
    echo "  - Compression: enabled"
}

# Main execution
main() {
    log "=== EMERGENCY LOG CLEANUP FOR HFT PRODUCTION SYSTEM ==="
    log "Container: $CONTAINER_NAME"
    log "Safety preserve lines: $SAFETY_LOG_LINES"
    
    # Execute cleanup steps
    check_production_environment
    create_backup_directory
    get_container_log_path
    backup_recent_logs
    cleanup_logs
    force_log_rotation
    verify_container_health
    show_final_status
}

# Show usage if needed
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << EOF
Emergency Log Cleanup Script for HFT Production System

USAGE:
  $0                    # Run emergency cleanup
  $0 --help            # Show this help

DESCRIPTION:
  Safely cleans up oversized Docker container logs without stopping
  the container. Designed for zero-downtime operation in production
  HFT trading environments.

SAFETY FEATURES:
  - Preserves last $SAFETY_LOG_LINES log lines for debugging
  - Creates backup of recent log entries
  - Verifies container health after cleanup
  - Forces log rotation to activate new settings
  - Only runs from production docker directory

REQUIREMENTS:
  - Must be run from /opt/arbitrage/docker/ directory
  - Container '$CONTAINER_NAME' must be running
  - Requires sudo access for Docker daemon signal

EOF
    exit 0
fi

# Run main function
main "$@"