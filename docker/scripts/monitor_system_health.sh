#!/bin/bash

# Production System Health Monitoring Script
# Continuous monitoring for HFT trading system health and log performance
# Designed for production arbitrage system monitoring

set -euo pipefail

# Configuration
CONTAINER_NAME="arbitrage_collector"
CHECK_INTERVAL=60  # seconds
LOG_PERFORMANCE_THRESHOLD_MS=1000  # 1 second
LOG_SIZE_WARNING_MB=80  # Warn at 80MB (rotation at 100MB)
MONITORING_DURATION=3600  # 1 hour default

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
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

info() {
    echo -e "${CYAN}[INFO]${NC} $1"
}

# Check container health
check_container_health() {
    local container_status="unknown"
    local health_status="unknown"
    local uptime="unknown"
    
    # Get container info
    if docker ps --format "table {{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
        container_status=$(docker inspect "$CONTAINER_NAME" --format '{{.State.Status}}')
        health_status=$(docker inspect "$CONTAINER_NAME" --format '{{.State.Health.Status}}' 2>/dev/null || echo "no-healthcheck")
        uptime=$(docker inspect "$CONTAINER_NAME" --format '{{.State.StartedAt}}')
        
        if [[ "$container_status" == "running" ]]; then
            echo -e "${GREEN}●${NC} Container: running"
        else
            echo -e "${RED}●${NC} Container: $container_status"
            return 1
        fi
        
        if [[ "$health_status" == "healthy" ]]; then
            echo -e "${GREEN}●${NC} Health: healthy"
        elif [[ "$health_status" == "no-healthcheck" ]]; then
            echo -e "${CYAN}●${NC} Health: no healthcheck configured"
        else
            echo -e "${YELLOW}●${NC} Health: $health_status"
        fi
    else
        echo -e "${RED}●${NC} Container: not running"
        return 1
    fi
    
    return 0
}

# Test log performance
test_log_performance() {
    local start_time=$(date +%s%N)
    
    if timeout 10s docker logs "$CONTAINER_NAME" -n 1 >/dev/null 2>&1; then
        local end_time=$(date +%s%N)
        local response_time=$(( (end_time - start_time) / 1000000 ))  # Convert to milliseconds
        
        if [[ $response_time -lt $LOG_PERFORMANCE_THRESHOLD_MS ]]; then
            echo -e "${GREEN}●${NC} Log performance: ${response_time}ms"
        else
            echo -e "${YELLOW}●${NC} Log performance: ${response_time}ms (slow)"
            warn "Log response time exceeds threshold (${LOG_PERFORMANCE_THRESHOLD_MS}ms)"
        fi
        
        return 0
    else
        echo -e "${RED}●${NC} Log performance: TIMEOUT/FAIL"
        return 1
    fi
}

# Check log file size
check_log_file_size() {
    local container_id=$(docker ps --filter "name=${CONTAINER_NAME}" --format "{{.ID}}")
    local log_path=$(docker inspect "$container_id" | jq -r '.[0].LogPath' 2>/dev/null)
    
    if [[ -f "$log_path" ]]; then
        local log_size_bytes=$(stat -c%s "$log_path")
        local log_size_mb=$((log_size_bytes / 1024 / 1024))
        local log_lines=$(wc -l < "$log_path")
        
        if [[ $log_size_mb -lt $LOG_SIZE_WARNING_MB ]]; then
            echo -e "${GREEN}●${NC} Log size: ${log_size_mb}MB (${log_lines} lines)"
        else
            echo -e "${YELLOW}●${NC} Log size: ${log_size_mb}MB (${log_lines} lines) - approaching rotation"
            
            if [[ $log_size_mb -ge 95 ]]; then
                warn "Log file approaching 100MB rotation limit"
            fi
        fi
    else
        echo -e "${RED}●${NC} Log file: not found"
        return 1
    fi
    
    return 0
}

# Check log rotation configuration
check_log_rotation_config() {
    local container_id=$(docker ps --filter "name=${CONTAINER_NAME}" --format "{{.ID}}")
    local log_driver=$(docker inspect "$container_id" --format '{{.HostConfig.LogConfig.Type}}')
    local log_config=$(docker inspect "$container_id" --format '{{json .HostConfig.LogConfig.Config}}')
    
    if [[ "$log_driver" == "json-file" ]] && echo "$log_config" | grep -q "max-size"; then
        local max_size=$(echo "$log_config" | jq -r '.["max-size"]' 2>/dev/null || echo "unknown")
        local max_file=$(echo "$log_config" | jq -r '.["max-file"]' 2>/dev/null || echo "unknown")
        echo -e "${GREEN}●${NC} Log rotation: active (${max_size}, ${max_file} files)"
    else
        echo -e "${RED}●${NC} Log rotation: not configured properly"
        return 1
    fi
    
    return 0
}

# Check application activity
check_application_activity() {
    # Look for recent application activity
    if docker logs "$CONTAINER_NAME" --since 5m 2>/dev/null | grep -i "collected\|inserted\|processing\|snapshot" >/dev/null 2>&1; then
        echo -e "${GREEN}●${NC} Data collection: active"
    else
        echo -e "${YELLOW}●${NC} Data collection: no recent activity (5min)"
        
        # Check for errors in recent logs
        if docker logs "$CONTAINER_NAME" --since 5m 2>/dev/null | grep -i "error\|exception\|traceback" >/dev/null 2>&1; then
            echo -e "${RED}●${NC} Recent errors: detected"
            return 1
        fi
    fi
    
    return 0
}

# Check system resources
check_system_resources() {
    # Get container resource usage
    local resource_info=$(docker stats "$CONTAINER_NAME" --no-stream --format "table {{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null)
    
    if [[ -n "$resource_info" ]]; then
        local cpu_mem=$(echo "$resource_info" | tail -n1)
        echo -e "${CYAN}●${NC} Resources: $cpu_mem"
    else
        echo -e "${YELLOW}●${NC} Resources: unable to retrieve"
    fi
}

# Single health check iteration
perform_health_check() {
    local timestamp=$(date +'%Y-%m-%d %H:%M:%S')
    local overall_status="OK"
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Health Check: $timestamp"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Perform all checks
    check_container_health || overall_status="WARNING"
    test_log_performance || overall_status="CRITICAL"
    check_log_file_size || overall_status="WARNING"
    check_log_rotation_config || overall_status="WARNING"
    check_application_activity || overall_status="WARNING"
    check_system_resources
    
    # Overall status
    echo
    case "$overall_status" in
        "OK")
            echo -e "${GREEN}Overall Status: $overall_status ✓${NC}"
            ;;
        "WARNING")
            echo -e "${YELLOW}Overall Status: $overall_status ⚠${NC}"
            ;;
        "CRITICAL")
            echo -e "${RED}Overall Status: $overall_status ✗${NC}"
            ;;
    esac
    
    echo
    return 0
}

# Continuous monitoring mode
continuous_monitoring() {
    local duration=${1:-$MONITORING_DURATION}
    local start_time=$(date +%s)
    local end_time=$((start_time + duration))
    local check_count=0
    
    log "Starting continuous monitoring for ${duration} seconds ($(($duration / 60)) minutes)"
    log "Check interval: ${CHECK_INTERVAL} seconds"
    log "Press Ctrl+C to stop monitoring"
    
    echo
    
    while [[ $(date +%s) -lt $end_time ]]; do
        check_count=$((check_count + 1))
        
        perform_health_check
        
        # Calculate time remaining
        local current_time=$(date +%s)
        local remaining=$((end_time - current_time))
        
        if [[ $remaining -gt 0 ]]; then
            echo "Next check in ${CHECK_INTERVAL}s (${remaining}s remaining, check #$check_count)"
            sleep $CHECK_INTERVAL
        else
            break
        fi
    done
    
    echo
    success "Monitoring completed after $check_count checks"
}

# Show usage
show_usage() {
    cat << EOF
Production System Health Monitoring Script

USAGE:
  $0                           # Single health check
  $0 --continuous             # Continuous monitoring (1 hour)
  $0 --continuous --duration 1800  # Continuous monitoring (30 minutes)
  $0 --help                   # Show this help

DESCRIPTION:
  Monitors the health of the HFT trading system with focus on
  log performance, container health, and data collection activity.

MONITORING CHECKS:
  - Container status and health
  - Log command performance (<${LOG_PERFORMANCE_THRESHOLD_MS}ms requirement)
  - Log file size (warning at ${LOG_SIZE_WARNING_MB}MB)
  - Log rotation configuration
  - Data collection activity
  - System resource usage

CONTINUOUS MODE:
  - Default duration: $((MONITORING_DURATION / 60)) minutes
  - Check interval: ${CHECK_INTERVAL} seconds
  - Press Ctrl+C to stop early

EOF
}

# Main execution
main() {
    local mode="single"
    local duration=$MONITORING_DURATION
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --continuous)
                mode="continuous"
                shift
                ;;
            --duration)
                duration="$2"
                shift 2
                ;;
            --help|-h)
                show_usage
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    # Execute based on mode
    case "$mode" in
        "single")
            log "Performing single health check for container: $CONTAINER_NAME"
            echo
            perform_health_check
            ;;
        "continuous")
            continuous_monitoring "$duration"
            ;;
    esac
}

# Set up signal handling for graceful shutdown
trap 'echo; log "Monitoring interrupted by user"; exit 0' INT

# Run main function
main "$@"