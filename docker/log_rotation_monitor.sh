#!/bin/bash

# Log Rotation Monitoring Script for CEX Arbitrage Production
# This script monitors log rotation effectiveness and provides health status
# 
# Usage: ./log_rotation_monitor.sh [container_name] [monitoring_duration]
# Example: ./log_rotation_monitor.sh arbitrage_collector 300
# Example: ./log_rotation_monitor.sh arbitrage_collector (runs indefinitely)

set -euo pipefail

CONTAINER_NAME="${1:-arbitrage_collector}"
MONITORING_DURATION="${2:-0}"  # 0 means run indefinitely
CHECK_INTERVAL=60              # Check every minute
ALERT_THRESHOLD_MB=150         # Alert if log file exceeds this size

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Check if container exists and is running
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
}

# Get log configuration from container
get_log_config() {
    local container="$1"
    local config
    
    if command -v jq >/dev/null 2>&1; then
        config=$(docker inspect "$container" | jq -r '.[0].HostConfig.LogConfig' 2>/dev/null || echo "{}")
        
        local driver=$(echo "$config" | jq -r '.Type // "unknown"')
        local max_size=$(echo "$config" | jq -r '.Config."max-size" // "not set"')
        local max_files=$(echo "$config" | jq -r '.Config."max-file" // "not set"')
        local compress=$(echo "$config" | jq -r '.Config.compress // "not set"')
        
        echo "Driver: $driver | Max Size: $max_size | Max Files: $max_files | Compress: $compress"
    else
        echo "jq not available - cannot parse log configuration"
    fi
}

# Get current log file path and size
get_log_info() {
    local container="$1"
    local container_id
    local log_path
    local size_bytes
    local size_mb
    
    container_id=$(docker inspect --format='{{.Id}}' "$container")
    log_path="/var/lib/docker/containers/${container_id}/${container_id}-json.log"
    
    if [[ -f "$log_path" ]]; then
        size_bytes=$(stat -c%s "$log_path" 2>/dev/null || echo "0")
        size_mb=$((size_bytes / 1024 / 1024))
        echo "$log_path|$size_mb"
    else
        echo "not_found|0"
    fi
}

# Check for rotated log files
check_rotated_logs() {
    local container="$1"
    local container_id
    local log_dir
    local rotated_count
    
    container_id=$(docker inspect --format='{{.Id}}' "$container")
    log_dir="/var/lib/docker/containers/${container_id}"
    
    if [[ -d "$log_dir" ]]; then
        # Count compressed log files (rotated logs)
        rotated_count=$(ls -1 "${log_dir}"/*.gz 2>/dev/null | wc -l || echo "0")
        echo "$rotated_count"
    else
        echo "0"
    fi
}

# Test Docker logs commands
test_logs_commands() {
    local container="$1"
    local test_results=""
    
    # Test the problematic command that was hanging
    if timeout 5 docker logs "$container" -n 1 >/dev/null 2>&1; then
        test_results+="✅"
    else
        test_results+="❌"
    fi
    
    # Test tail command
    if timeout 5 docker logs "$container" --tail 5 >/dev/null 2>&1; then
        test_results+="✅"
    else
        test_results+="❌"
    fi
    
    # Test follow command (quick test)
    if timeout 2 docker logs "$container" -f >/dev/null 2>&1; then
        test_results+="✅"
    else
        test_results+="❌"
    fi
    
    echo "$test_results"
}

# Generate status report
generate_status_report() {
    local container="$1"
    local log_info
    local log_path
    local current_size_mb
    local rotated_count
    local log_config
    local test_results
    
    # Gather information
    log_info=$(get_log_info "$container")
    log_path=$(echo "$log_info" | cut -d'|' -f1)
    current_size_mb=$(echo "$log_info" | cut -d'|' -f2)
    rotated_count=$(check_rotated_logs "$container")
    log_config=$(get_log_config "$container")
    test_results=$(test_logs_commands "$container")
    
    # Determine health status
    local health_status="HEALTHY"
    local health_color="$GREEN"
    
    if [[ "$current_size_mb" -gt "$ALERT_THRESHOLD_MB" ]]; then
        health_status="WARNING"
        health_color="$YELLOW"
    fi
    
    if [[ "$test_results" == *"❌"* ]]; then
        health_status="ERROR"
        health_color="$RED"
    fi
    
    # Display status
    echo
    echo -e "${health_color}=== LOG ROTATION STATUS: $health_status ===${NC}"
    echo "Container: $container"
    echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
    echo
    echo "Log Configuration:"
    echo "  $log_config"
    echo
    echo "Current Log Status:"
    echo "  File: $log_path"
    echo "  Size: ${current_size_mb}MB"
    echo "  Rotated files: $rotated_count"
    echo
    echo "Command Tests:"
    echo "  docker logs -n 1: $(echo "$test_results" | cut -c1)"
    echo "  docker logs --tail 5: $(echo "$test_results" | cut -c2)"
    echo "  docker logs -f: $(echo "$test_results" | cut -c3)"
    echo
    
    # Alerts and recommendations
    if [[ "$current_size_mb" -gt "$ALERT_THRESHOLD_MB" ]]; then
        warn "Log file size (${current_size_mb}MB) exceeds threshold (${ALERT_THRESHOLD_MB}MB)"
        echo "  Recommendation: Check if log rotation is working properly"
    fi
    
    if [[ "$rotated_count" -gt 0 ]]; then
        info "Log rotation is active - found $rotated_count rotated files"
    else
        if [[ "$current_size_mb" -gt 50 ]]; then
            warn "No rotated files found but log is getting large"
            echo "  Recommendation: Verify log rotation configuration"
        fi
    fi
    
    if [[ "$test_results" == *"❌"* ]]; then
        error "Some Docker logs commands are failing"
        echo "  Recommendation: Check container health and log file integrity"
    fi
    
    echo "----------------------------------------"
}

# Continuous monitoring mode
continuous_monitoring() {
    local container="$1"
    local duration="$2"
    local elapsed=0
    local iteration=1
    
    log "Starting continuous monitoring for container: $container"
    if [[ "$duration" -gt 0 ]]; then
        log "Monitoring duration: ${duration} seconds"
    else
        log "Monitoring duration: indefinite (press Ctrl+C to stop)"
    fi
    
    log "Check interval: ${CHECK_INTERVAL} seconds"
    log "Alert threshold: ${ALERT_THRESHOLD_MB}MB"
    echo
    
    while true; do
        echo "=== MONITORING ITERATION $iteration ==="
        generate_status_report "$container"
        
        elapsed=$((elapsed + CHECK_INTERVAL))
        iteration=$((iteration + 1))
        
        # Check if we should stop
        if [[ "$duration" -gt 0 ]] && [[ "$elapsed" -ge "$duration" ]]; then
            log "Monitoring duration reached. Stopping."
            break
        fi
        
        sleep "$CHECK_INTERVAL"
    done
}

# Single check mode
single_check() {
    local container="$1"
    
    log "Performing single log rotation health check for: $container"
    generate_status_report "$container"
}

# Show summary statistics
show_summary_stats() {
    local container="$1"
    
    echo
    log "=== SUMMARY STATISTICS ==="
    
    # Container uptime
    local uptime
    uptime=$(docker inspect --format='{{.State.StartedAt}}' "$container" 2>/dev/null | xargs -I {} date -d {} +%s 2>/dev/null || echo "")
    if [[ -n "$uptime" ]]; then
        local current_time=$(date +%s)
        local uptime_seconds=$((current_time - uptime))
        local uptime_hours=$((uptime_seconds / 3600))
        local uptime_days=$((uptime_hours / 24))
        
        echo "Container uptime: ${uptime_days} days, $((uptime_hours % 24)) hours"
    fi
    
    # Log directory info
    local container_id
    container_id=$(docker inspect --format='{{.Id}}' "$container" 2>/dev/null || echo "")
    if [[ -n "$container_id" ]]; then
        local log_dir="/var/lib/docker/containers/${container_id}"
        if [[ -d "$log_dir" ]]; then
            local total_log_size
            total_log_size=$(du -sh "$log_dir" 2>/dev/null | cut -f1 || echo "unknown")
            echo "Total log directory size: $total_log_size"
            
            local log_files_count
            log_files_count=$(ls -1 "$log_dir"/*.log* 2>/dev/null | wc -l || echo "0")
            echo "Total log files: $log_files_count"
        fi
    fi
    
    echo
    info "To fix log rotation issues, run: ./deploy_log_rotation_fix.sh"
    info "To clean up large logs, run: sudo ./emergency_log_cleanup.sh $container"
}

# Main execution
main() {
    local container="$1"
    local duration="$2"
    
    # Verify container
    verify_container "$container"
    
    if [[ "$duration" -eq 0 ]]; then
        # Continuous monitoring
        continuous_monitoring "$container" "$duration"
    else
        # Single check with optional monitoring
        single_check "$container"
        
        if [[ "$duration" -gt "$CHECK_INTERVAL" ]]; then
            echo
            read -p "Start continuous monitoring for ${duration} seconds? [y/N]: " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                continuous_monitoring "$container" "$duration"
            fi
        fi
    fi
    
    show_summary_stats "$container"
}

# Help function
show_help() {
    echo "Log Rotation Monitoring Script"
    echo
    echo "Usage: $0 [container_name] [monitoring_duration]"
    echo
    echo "Arguments:"
    echo "  container_name       Container to monitor (default: arbitrage_collector)"
    echo "  monitoring_duration  Seconds to monitor (default: single check, 0 = indefinite)"
    echo
    echo "Examples:"
    echo "  $0                                    # Single check of arbitrage_collector"
    echo "  $0 arbitrage_collector                # Single check"
    echo "  $0 arbitrage_collector 300            # Monitor for 5 minutes"
    echo "  $0 arbitrage_collector 0              # Monitor indefinitely"
    echo
    echo "Features:"
    echo "  - Monitor current log file size"
    echo "  - Check for rotated/compressed logs"
    echo "  - Test Docker logs commands"
    echo "  - Provide health status and alerts"
    echo "  - Continuous monitoring with intervals"
    echo
    echo "Thresholds:"
    echo "  - Alert if log file exceeds ${ALERT_THRESHOLD_MB}MB"
    echo "  - Check interval: ${CHECK_INTERVAL} seconds"
}

# Handle command line arguments
if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
    show_help
    exit 0
fi

# Set up signal handling for graceful shutdown
trap 'echo; log "Monitoring stopped by user"; exit 0' INT TERM

# Execute main function
main "$CONTAINER_NAME" "$MONITORING_DURATION"