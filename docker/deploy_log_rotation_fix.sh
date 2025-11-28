#!/bin/bash

# Production Log Rotation Fix Deployment Script
# This script deploys log rotation configuration and cleans up existing large log files
# 
# Usage: ./deploy_log_rotation_fix.sh
# 
# What this script does:
# 1. Backs up current configurations
# 2. Deploys new log rotation configuration  
# 3. Cleans up existing large log files
# 4. Verifies the fix is working
# 5. Monitors log rotation effectiveness

set -euo pipefail

# Configuration
COMPOSE_PROJECT="cex_arbitrage"
CONTAINER_NAME="arbitrage_collector"
BACKUP_DIR="/tmp/cex_arbitrage_deploy_backup"
LOG_FILE="/tmp/deploy_log_rotation_$(date +%Y%m%d_%H%M%S).log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE" >&2
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check if Docker is running
    if ! docker info >/dev/null 2>&1; then
        error "Docker is not running or not accessible"
        exit 1
    fi
    
    # Check if docker-compose is available
    if ! command -v docker-compose >/dev/null 2>&1; then
        error "docker-compose not found"
        exit 1
    fi
    
    # Check if we have the required compose files
    if [[ ! -f "docker-compose.yml" ]] || [[ ! -f "docker-compose.prod.yml" ]]; then
        error "Required docker-compose files not found"
        echo "Please run this script from the docker/ directory"
        exit 1
    fi
    
    # Check if emergency cleanup script exists
    if [[ ! -f "emergency_log_cleanup.sh" ]]; then
        error "emergency_log_cleanup.sh not found"
        exit 1
    fi
    
    log "✅ Prerequisites check passed"
}

# Backup current configuration
backup_configuration() {
    log "Backing up current configuration..."
    
    mkdir -p "$BACKUP_DIR"
    
    # Backup docker-compose files
    cp docker-compose.yml "$BACKUP_DIR/"
    cp docker-compose.prod.yml "$BACKUP_DIR/"
    
    # Backup current container state
    if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
        docker inspect "$CONTAINER_NAME" > "$BACKUP_DIR/container_inspect.json"
    fi
    
    log "Configuration backed up to: $BACKUP_DIR"
}

# Deploy log rotation configuration
deploy_log_rotation() {
    log "Deploying log rotation configuration..."
    
    # Check current container status
    if docker ps --format "{{.Names}}" | grep -q "$CONTAINER_NAME"; then
        log "Container $CONTAINER_NAME is currently running"
        
        # Apply new configuration (Docker Compose will recreate with new logging config)
        log "Applying new docker-compose configuration..."
        docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate data_collector
        
        # Wait for container to be healthy
        log "Waiting for container to become healthy..."
        local timeout=60
        local count=0
        
        while [[ $count -lt $timeout ]]; do
            if docker ps --filter "name=$CONTAINER_NAME" --filter "health=healthy" --format "{{.Names}}" | grep -q "$CONTAINER_NAME"; then
                log "✅ Container is healthy"
                break
            fi
            
            if [[ $count -eq 0 ]]; then
                info "Waiting for container health check..."
            fi
            
            sleep 5
            ((count+=5))
        done
        
        if [[ $count -ge $timeout ]]; then
            warn "Container health check timeout - continuing anyway"
        fi
        
    else
        warn "Container $CONTAINER_NAME is not running - starting with new configuration"
        docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d data_collector
    fi
    
    log "✅ Log rotation configuration deployed"
}

# Clean up existing large log files
cleanup_large_logs() {
    log "Cleaning up existing large log files..."
    
    # Check if we need to run as root
    if [[ $EUID -ne 0 ]]; then
        warn "Need root privileges for log file cleanup"
        log "Running emergency cleanup with sudo..."
        sudo ./emergency_log_cleanup.sh "$CONTAINER_NAME"
    else
        ./emergency_log_cleanup.sh "$CONTAINER_NAME"
    fi
    
    log "✅ Log cleanup completed"
}

# Verify the fix is working
verify_fix() {
    log "Verifying log rotation fix..."
    
    # Test Docker logs commands
    info "Testing 'docker logs' commands..."
    
    # Test the previously problematic command
    if timeout 10 docker logs "$CONTAINER_NAME" -n 1 >/dev/null 2>&1; then
        log "✅ 'docker logs $CONTAINER_NAME -n 1' works correctly"
    else
        error "❌ 'docker logs $CONTAINER_NAME -n 1' still failing"
        return 1
    fi
    
    # Test tail command
    if timeout 10 docker logs "$CONTAINER_NAME" --tail 5 >/dev/null 2>&1; then
        log "✅ 'docker logs $CONTAINER_NAME --tail 5' works correctly"
    else
        error "❌ 'docker logs $CONTAINER_NAME --tail 5' failing"
        return 1
    fi
    
    # Check log rotation configuration
    local log_config
    log_config=$(docker inspect "$CONTAINER_NAME" | jq -r '.[0].HostConfig.LogConfig.Config."max-size"' 2>/dev/null || echo "null")
    
    if [[ "$log_config" == "100m" ]]; then
        log "✅ Log rotation configuration verified (max-size: $log_config)"
    else
        warn "Log rotation configuration not found or incorrect (max-size: $log_config)"
        warn "You may need to recreate the container"
    fi
    
    log "✅ Verification completed"
}

# Show current log file status
show_log_status() {
    log "Current log file status..."
    
    if command -v jq >/dev/null 2>&1; then
        local container_id log_path
        container_id=$(docker inspect --format='{{.Id}}' "$CONTAINER_NAME" 2>/dev/null || echo "")
        
        if [[ -n "$container_id" ]]; then
            log_path="/var/lib/docker/containers/${container_id}/${container_id}-json.log"
            
            if [[ -f "$log_path" ]]; then
                local size
                size=$(du -h "$log_path" | cut -f1)
                log "Current log file size: $size"
                log "Log file path: $log_path"
            fi
        fi
    fi
    
    # Show recent logs to verify container is working
    info "Recent container logs:"
    docker logs "$CONTAINER_NAME" --tail 10 2>/dev/null || true
}

# Monitoring recommendations
show_monitoring_recommendations() {
    echo
    log "=== POST-DEPLOYMENT MONITORING ==="
    
    echo
    info "1. Monitor log file size growth:"
    echo "   watch 'docker inspect $CONTAINER_NAME | jq -r \".[0].LogPath\" | xargs du -h'"
    
    echo
    info "2. Test log commands periodically:"
    echo "   docker logs $CONTAINER_NAME -n 1"
    echo "   docker logs $CONTAINER_NAME --tail 10"
    
    echo
    info "3. Monitor log rotation effectiveness:"
    echo "   ./log_rotation_monitor.sh $CONTAINER_NAME"
    
    echo
    info "4. Check for rotated log files:"
    echo "   sudo ls -la /var/lib/docker/containers/\$(docker inspect --format='{{.Id}}' $CONTAINER_NAME)/*.gz"
    
    echo
    log "=== CONFIGURATION SUMMARY ==="
    info "- Log rotation: Enabled"
    info "- Max file size: 100MB"
    info "- Max files kept: 3"
    info "- Compression: Enabled"
    info "- Log driver: json-file"
    
    echo
    log "Deployment completed successfully! 🎉"
    log "Full deployment log saved to: $LOG_FILE"
}

# Rollback function
rollback() {
    error "Deployment failed - initiating rollback..."
    
    if [[ -d "$BACKUP_DIR" ]]; then
        log "Restoring configuration from backup..."
        cp "$BACKUP_DIR/docker-compose.yml" .
        cp "$BACKUP_DIR/docker-compose.prod.yml" .
        
        docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d data_collector
        log "Rollback completed"
    else
        error "Backup directory not found - manual rollback required"
    fi
}

# Main execution
main() {
    log "Starting log rotation fix deployment..."
    log "Deployment log: $LOG_FILE"
    
    # Set up error handling
    trap rollback ERR
    
    # Execute deployment steps
    check_prerequisites
    backup_configuration
    deploy_log_rotation
    
    # Wait a moment for the new container to start logging
    sleep 10
    
    cleanup_large_logs
    verify_fix
    show_log_status
    show_monitoring_recommendations
    
    # Clear the error trap on successful completion
    trap - ERR
}

# Help function
show_help() {
    echo "Production Log Rotation Fix Deployment Script"
    echo
    echo "This script automatically:"
    echo "  1. Backs up current configurations"
    echo "  2. Deploys new log rotation settings"
    echo "  3. Cleans up existing large log files"
    echo "  4. Verifies the fix is working"
    echo "  5. Provides monitoring recommendations"
    echo
    echo "Usage: $0"
    echo
    echo "Prerequisites:"
    echo "  - Run from the docker/ directory"
    echo "  - Docker and docker-compose installed"
    echo "  - Have sudo access for log file cleanup"
    echo
    echo "The script creates:"
    echo "  - Configuration backup in $BACKUP_DIR"
    echo "  - Deployment log at /tmp/deploy_log_rotation_*.log"
    echo
    echo "Options:"
    echo "  -h, --help    Show this help"
}

# Handle command line arguments
if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
    show_help
    exit 0
fi

# Execute main function
main "$@"