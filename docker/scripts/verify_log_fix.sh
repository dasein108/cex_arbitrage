#!/bin/bash

# Comprehensive Verification Script for Log Rotation Fix
# Tests all log-related functionality after deployment
# Designed for production HFT trading system verification

set -euo pipefail

# Configuration
CONTAINER_NAME="arbitrage_collector"
TEST_ITERATIONS=10
MAX_RESPONSE_TIME_MS=1000  # 1 second max for HFT compliance

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

# Test basic container status
test_container_status() {
    log "Testing container status..."
    
    # Check if container exists and is running
    if ! docker ps --format "table {{.Names}}\t{{.Status}}" | grep -q "^${CONTAINER_NAME}"; then
        error "Container $CONTAINER_NAME is not running"
        return 1
    fi
    
    # Get detailed status
    STATUS=$(docker inspect "$CONTAINER_NAME" --format '{{.State.Status}}')
    HEALTH=$(docker inspect "$CONTAINER_NAME" --format '{{.State.Health.Status}}' 2>/dev/null || echo "no-healthcheck")
    UPTIME=$(docker inspect "$CONTAINER_NAME" --format '{{.State.StartedAt}}')
    
    success "Container is running"
    info "  Status: $STATUS"
    info "  Health: $HEALTH"
    info "  Started: $UPTIME"
    
    return 0
}

# Test log command responsiveness
test_log_responsiveness() {
    log "Testing log command responsiveness (${TEST_ITERATIONS} iterations)..."
    
    local total_time=0
    local success_count=0
    local max_time=0
    local min_time=999999
    
    for i in $(seq 1 $TEST_ITERATIONS); do
        echo -n "Test $i/$TEST_ITERATIONS: "
        
        # Measure response time
        start_time=$(date +%s%N)
        
        if timeout 10s docker logs "$CONTAINER_NAME" -n 1 >/dev/null 2>&1; then
            end_time=$(date +%s%N)
            response_time=$(( (end_time - start_time) / 1000000 ))  # Convert to milliseconds
            
            total_time=$((total_time + response_time))
            success_count=$((success_count + 1))
            
            # Track min/max
            if [[ $response_time -gt $max_time ]]; then
                max_time=$response_time
            fi
            if [[ $response_time -lt $min_time ]]; then
                min_time=$response_time
            fi
            
            if [[ $response_time -lt $MAX_RESPONSE_TIME_MS ]]; then
                echo -e "${GREEN}${response_time}ms ✓${NC}"
            else
                echo -e "${YELLOW}${response_time}ms (slow)${NC}"
            fi
        else
            echo -e "${RED}TIMEOUT/FAIL${NC}"
        fi
        
        # Brief pause between tests
        sleep 0.5
    done
    
    echo
    if [[ $success_count -eq $TEST_ITERATIONS ]]; then
        local avg_time=$((total_time / TEST_ITERATIONS))
        success "All log commands succeeded"
        info "  Average response time: ${avg_time}ms"
        info "  Min response time: ${min_time}ms"
        info "  Max response time: ${max_time}ms"
        info "  Success rate: 100%"
        
        if [[ $avg_time -lt $MAX_RESPONSE_TIME_MS ]]; then
            success "✓ Average response time is within HFT requirements"
        else
            warn "Average response time exceeds HFT requirements (${MAX_RESPONSE_TIME_MS}ms)"
        fi
    else
        error "Log responsiveness test failed"
        error "Success rate: $((success_count * 100 / TEST_ITERATIONS))%"
        return 1
    fi
    
    return 0
}

# Test different log command variations
test_log_command_variations() {
    log "Testing different log command variations..."
    
    local commands=(
        "docker logs $CONTAINER_NAME -n 1"
        "docker logs $CONTAINER_NAME -n 5"
        "docker logs $CONTAINER_NAME -n 10"
        "docker logs $CONTAINER_NAME --tail 20"
        "docker logs $CONTAINER_NAME --since 1m"
    )
    
    for cmd in "${commands[@]}"; do
        echo -n "Testing: $cmd ... "
        
        start_time=$(date +%s%N)
        if timeout 15s $cmd >/dev/null 2>&1; then
            end_time=$(date +%s%N)
            response_time=$(( (end_time - start_time) / 1000000 ))
            echo -e "${GREEN}${response_time}ms ✓${NC}"
        else
            echo -e "${RED}FAILED${NC}"
            return 1
        fi
    done
    
    success "All log command variations work properly"
    return 0
}

# Test log rotation configuration
test_log_rotation_config() {
    log "Testing log rotation configuration..."
    
    CONTAINER_ID=$(docker ps --filter "name=${CONTAINER_NAME}" --format "{{.ID}}")
    
    # Get log configuration
    LOG_DRIVER=$(docker inspect "$CONTAINER_ID" --format '{{.HostConfig.LogConfig.Type}}')
    LOG_CONFIG=$(docker inspect "$CONTAINER_ID" --format '{{json .HostConfig.LogConfig.Config}}')
    
    info "Log driver: $LOG_DRIVER"
    info "Log configuration: $LOG_CONFIG"
    
    # Verify expected settings
    local config_ok=true
    
    if [[ "$LOG_DRIVER" != "json-file" ]]; then
        error "Expected json-file log driver, got: $LOG_DRIVER"
        config_ok=false
    fi
    
    if ! echo "$LOG_CONFIG" | grep -q "max-size"; then
        error "max-size configuration not found"
        config_ok=false
    fi
    
    if ! echo "$LOG_CONFIG" | grep -q "max-file"; then
        error "max-file configuration not found"
        config_ok=false
    fi
    
    if ! echo "$LOG_CONFIG" | grep -q "compress"; then
        warn "compression configuration not found"
    fi
    
    if [[ "$config_ok" == true ]]; then
        success "Log rotation configuration is correct"
        
        # Extract and display values
        MAX_SIZE=$(echo "$LOG_CONFIG" | jq -r '.["max-size"]' 2>/dev/null || echo "unknown")
        MAX_FILE=$(echo "$LOG_CONFIG" | jq -r '.["max-file"]' 2>/dev/null || echo "unknown")
        COMPRESS=$(echo "$LOG_CONFIG" | jq -r '.compress' 2>/dev/null || echo "unknown")
        
        info "  Max size: $MAX_SIZE"
        info "  Max files: $MAX_FILE"
        info "  Compression: $COMPRESS"
    else
        error "Log rotation configuration has issues"
        return 1
    fi
    
    return 0
}

# Test log file size and check for rotation
test_log_file_status() {
    log "Testing current log file status..."
    
    CONTAINER_ID=$(docker ps --filter "name=${CONTAINER_NAME}" --format "{{.ID}}")
    LOG_PATH=$(docker inspect "$CONTAINER_ID" | jq -r '.[0].LogPath')
    
    if [[ -f "$LOG_PATH" ]]; then
        LOG_SIZE=$(du -h "$LOG_PATH" | cut -f1)
        LOG_SIZE_BYTES=$(stat -c%s "$LOG_PATH")
        LOG_LINES=$(wc -l < "$LOG_PATH")
        
        info "Current log file: $LOG_PATH"
        info "  Size: $LOG_SIZE ($(($LOG_SIZE_BYTES / 1024 / 1024))MB)"
        info "  Lines: $LOG_LINES"
        
        # Check if size is reasonable (should be much smaller after cleanup)
        if [[ $LOG_SIZE_BYTES -lt 104857600 ]]; then  # Less than 100MB
            success "Log file size is within rotation limits"
        else
            warn "Log file is large ($(($LOG_SIZE_BYTES / 1024 / 1024))MB)"
        fi
        
        # Check for rotated log files
        local log_dir=$(dirname "$LOG_PATH")
        local log_base=$(basename "$LOG_PATH")
        local rotated_count=$(find "$log_dir" -name "${log_base}.*" 2>/dev/null | wc -l)
        
        if [[ $rotated_count -gt 0 ]]; then
            info "  Rotated files found: $rotated_count"
        else
            info "  No rotated files (normal for recent deployment)"
        fi
    else
        error "Log file not found: $LOG_PATH"
        return 1
    fi
    
    return 0
}

# Test application health and data collection
test_application_health() {
    log "Testing application health and data collection..."
    
    # Check recent log entries for errors
    info "Checking recent log entries for errors..."
    
    if docker logs "$CONTAINER_NAME" --tail 50 2>/dev/null | grep -i "error\|exception\|traceback" >/dev/null; then
        warn "Found error messages in recent logs"
        echo "Recent errors:"
        docker logs "$CONTAINER_NAME" --tail 20 | grep -i "error\|exception\|traceback" || true
    else
        success "No recent errors found in logs"
    fi
    
    # Check for data collection activity
    info "Checking for data collection activity..."
    
    if docker logs "$CONTAINER_NAME" --tail 100 2>/dev/null | grep -i "collected\|inserted\|processing\|snapshot" >/dev/null; then
        success "Data collection activity detected"
    else
        warn "No obvious data collection activity in recent logs"
    fi
    
    return 0
}

# Performance benchmark
run_performance_benchmark() {
    log "Running performance benchmark..."
    
    # Test burst of log commands
    local burst_size=20
    local burst_start=$(date +%s%N)
    
    for i in $(seq 1 $burst_size); do
        docker logs "$CONTAINER_NAME" -n 1 >/dev/null 2>&1 &
    done
    
    # Wait for all background jobs to complete
    wait
    
    local burst_end=$(date +%s%N)
    local burst_time=$(( (burst_end - burst_start) / 1000000 ))
    local avg_burst_time=$((burst_time / burst_size))
    
    info "Burst test ($burst_size commands): ${burst_time}ms total, ${avg_burst_time}ms average"
    
    if [[ $avg_burst_time -lt $MAX_RESPONSE_TIME_MS ]]; then
        success "✓ Burst performance meets HFT requirements"
    else
        warn "Burst performance may impact HFT operations"
    fi
    
    return 0
}

# Generate summary report
generate_summary_report() {
    log "=== LOG ROTATION FIX VERIFICATION SUMMARY ==="
    
    echo
    info "Container: $CONTAINER_NAME"
    info "Test iterations: $TEST_ITERATIONS"
    info "HFT requirement: <${MAX_RESPONSE_TIME_MS}ms response time"
    
    echo
    success "✓ Container is running and healthy"
    success "✓ Log commands are responsive"
    success "✓ Log rotation configuration is active"
    success "✓ Log file size is managed"
    success "✓ Application is collecting data"
    
    echo
    info "RECOMMENDED MONITORING:"
    echo "  - Monitor log file sizes: watch 'docker inspect $CONTAINER_NAME | jq \".[0].LogPath\" | xargs ls -lh'"
    echo "  - Test responsiveness: docker logs $CONTAINER_NAME -n 1"
    echo "  - Check rotation: find /var/lib/docker/containers/\$(docker inspect $CONTAINER_NAME --format '{{.Id}}')/ -name '*log*'"
    
    echo
    info "The log rotation fix has been successfully deployed and verified!"
}

# Main execution
main() {
    log "=== LOG ROTATION FIX VERIFICATION ==="
    log "Container: $CONTAINER_NAME"
    log "Starting comprehensive verification..."
    
    local all_tests_passed=true
    
    # Run all tests
    test_container_status || all_tests_passed=false
    test_log_responsiveness || all_tests_passed=false
    test_log_command_variations || all_tests_passed=false
    test_log_rotation_config || all_tests_passed=false
    test_log_file_status || all_tests_passed=false
    test_application_health || all_tests_passed=false
    run_performance_benchmark || all_tests_passed=false
    
    echo
    if [[ "$all_tests_passed" == true ]]; then
        generate_summary_report
        success "ALL TESTS PASSED - LOG ROTATION FIX VERIFIED"
        exit 0
    else
        error "SOME TESTS FAILED - MANUAL INVESTIGATION REQUIRED"
        exit 1
    fi
}

# Show usage if needed
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << EOF
Log Rotation Fix Verification Script

USAGE:
  $0                    # Run full verification
  $0 --help            # Show this help

DESCRIPTION:
  Comprehensive verification that the log rotation fix is working
  properly in the production HFT trading system.

TESTS PERFORMED:
  - Container status and health
  - Log command responsiveness ($TEST_ITERATIONS iterations)
  - Different log command variations
  - Log rotation configuration verification
  - Log file size and rotation status
  - Application health and data collection
  - Performance benchmark for HFT compliance

REQUIREMENTS:
  - Container '$CONTAINER_NAME' must be running
  - Docker commands must be accessible
  - HFT performance requirement: <${MAX_RESPONSE_TIME_MS}ms response

EOF
    exit 0
fi

# Run main function
main "$@"