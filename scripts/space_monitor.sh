#!/bin/bash
# =============================================================================
# Space Monitoring and Alerting Script for CEX Arbitrage System
# =============================================================================
# This script provides real-time monitoring and alerting for disk space,
# database size, and Docker storage consumption

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"
METRICS_DIR="${PROJECT_ROOT}/metrics"
CONFIG_FILE="${SCRIPT_DIR}/monitor_config.conf"

# Default configuration
DISK_WARNING_THRESHOLD=80
DISK_CRITICAL_THRESHOLD=90
DB_WARNING_THRESHOLD_GB=6
DB_CRITICAL_THRESHOLD_GB=8
DOCKER_WARNING_THRESHOLD_GB=8
DOCKER_CRITICAL_THRESHOLD_GB=12

# Monitoring intervals (seconds)
MONITOR_INTERVAL=300  # 5 minutes
ALERT_COOLDOWN=1800   # 30 minutes between identical alerts

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
mkdir -p "$LOG_DIR" "$METRICS_DIR"

# Load configuration if exists
if [[ -f "$CONFIG_FILE" ]]; then
    source "$CONFIG_FILE"
fi

# Logging functions
log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" >> "${LOG_DIR}/space_monitor.log"
    if [[ "$level" == "ERROR" ]] || [[ "$level" == "WARN" ]]; then
        echo -e "${RED}[$timestamp] [$level] $message${NC}" >&2
    else
        echo "[$timestamp] [$level] $message"
    fi
}

log_info() { log "INFO" "$@"; }
log_warn() { log "WARN" "$@"; }
log_error() { log "ERROR" "$@"; }
log_success() { log "SUCCESS" "$@"; }

# Metrics storage functions
save_metric() {
    local metric_name="$1"
    local value="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local metrics_file="${METRICS_DIR}/${metric_name}_$(date +%Y%m%d).csv"
    
    # Create CSV header if file doesn't exist
    if [[ ! -f "$metrics_file" ]]; then
        echo "timestamp,value" > "$metrics_file"
    fi
    
    echo "$timestamp,$value" >> "$metrics_file"
}

get_latest_metric() {
    local metric_name="$1"
    local metrics_file="${METRICS_DIR}/${metric_name}_$(date +%Y%m%d).csv"
    
    if [[ -f "$metrics_file" ]]; then
        tail -n 1 "$metrics_file" | cut -d',' -f2
    else
        echo "0"
    fi
}

# System metrics collection functions
get_disk_usage() {
    df / | awk 'NR==2 {print $5}' | sed 's/%//'
}

get_disk_available_gb() {
    df / | awk 'NR==2 {print $4}' | awk '{print int($1/1024/1024)}'
}

get_database_size_gb() {
    if command -v psql &> /dev/null; then
        if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c '\q' 2>/dev/null; then
            PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "
                SELECT ROUND(pg_database_size('$DB_NAME') / 1024.0 / 1024.0 / 1024.0, 2);
            " 2>/dev/null | xargs || echo "0"
        else
            echo "0"
        fi
    else
        echo "0"
    fi
}

get_docker_size_gb() {
    if command -v docker &> /dev/null && docker system df &> /dev/null 2>&1; then
        # Extract total Docker space usage
        docker system df --format "table {{.Type}}\t{{.Size}}" | grep -E "(Images|Containers|Local Volumes|Build Cache)" | \
        awk '{
            if ($2 ~ /GB/) gsub(/GB/, "", $2); else if ($2 ~ /MB/) {gsub(/MB/, "", $2); $2 = $2/1024} else if ($2 ~ /KB/) {gsub(/KB/, "", $2); $2 = $2/1024/1024} else if ($2 ~ /B/) {gsub(/B/, "", $2); $2 = $2/1024/1024/1024}
            sum += $2
        } END {printf "%.2f", sum}' || echo "0"
    else
        echo "0"
    fi
}

get_database_table_sizes() {
    if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c '\q' 2>/dev/null; then
        PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "
            SELECT 
                tablename,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
                pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
            FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
        " 2>/dev/null || echo "No data available"
    else
        echo "Database not accessible"
    fi
}

# Alert management functions
should_send_alert() {
    local alert_type="$1"
    local last_alert_file="${METRICS_DIR}/last_alert_${alert_type}"
    local current_time=$(date +%s)
    
    if [[ -f "$last_alert_file" ]]; then
        local last_alert_time=$(cat "$last_alert_file")
        local time_diff=$((current_time - last_alert_time))
        
        if [[ $time_diff -lt $ALERT_COOLDOWN ]]; then
            return 1  # Don't send alert (too soon)
        fi
    fi
    
    echo "$current_time" > "$last_alert_file"
    return 0  # Send alert
}

send_alert() {
    local level="$1"
    local title="$2"
    local message="$3"
    local alert_type="$4"
    
    if ! should_send_alert "$alert_type"; then
        log_info "Skipping alert (cooldown): $title"
        return 0
    fi
    
    log_warn "ALERT [$level]: $title - $message"
    
    # Save alert to file
    local alert_file="${METRICS_DIR}/alerts_$(date +%Y%m%d).log"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$level] $title: $message" >> "$alert_file"
    
    # Send email alert if configured
    if [[ -n "${ALERT_EMAIL:-}" ]] && command -v mail &> /dev/null; then
        echo "$message" | mail -s "CEX Arbitrage Alert: $title" "$ALERT_EMAIL" 2>/dev/null || true
    fi
    
    # Send Slack alert if configured
    if [[ -n "${SLACK_WEBHOOK:-}" ]] && command -v curl &> /dev/null; then
        local slack_payload="{\"text\":\"🚨 *$title*\n$message\"}"
        curl -s -X POST -H 'Content-type: application/json' \
            --data "$slack_payload" "$SLACK_WEBHOOK" >/dev/null 2>&1 || true
    fi
    
    # Send Telegram alert if configured
    if [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] && [[ -n "${TELEGRAM_CHAT_ID:-}" ]] && command -v curl &> /dev/null; then
        local telegram_message="🚨 *$title*%0A$message"
        curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
            -d "chat_id=$TELEGRAM_CHAT_ID&text=$telegram_message&parse_mode=Markdown" >/dev/null 2>&1 || true
    fi
    
    # Trigger automated maintenance if critical
    if [[ "$level" == "CRITICAL" ]] && [[ -f "$SCRIPT_DIR/automated_maintenance.sh" ]]; then
        log_info "Triggering automated maintenance due to critical alert"
        "$SCRIPT_DIR/automated_maintenance.sh" check >> "${LOG_DIR}/auto_maintenance.log" 2>&1 &
    fi
}

# Monitoring functions
monitor_disk_space() {
    local disk_usage=$(get_disk_usage)
    local disk_available=$(get_disk_available_gb)
    
    save_metric "disk_usage_percent" "$disk_usage"
    save_metric "disk_available_gb" "$disk_available"
    
    if [[ $disk_usage -ge $DISK_CRITICAL_THRESHOLD ]]; then
        send_alert "CRITICAL" "Disk Space Critical" \
            "Disk usage: ${disk_usage}% (≥${DISK_CRITICAL_THRESHOLD}%), Available: ${disk_available}GB" \
            "disk_critical"
    elif [[ $disk_usage -ge $DISK_WARNING_THRESHOLD ]]; then
        send_alert "WARNING" "Disk Space Warning" \
            "Disk usage: ${disk_usage}% (≥${DISK_WARNING_THRESHOLD}%), Available: ${disk_available}GB" \
            "disk_warning"
    fi
    
    return $disk_usage
}

monitor_database_size() {
    local db_size=$(get_database_size_gb)
    
    save_metric "database_size_gb" "$db_size"
    
    if [[ "$(echo "$db_size >= $DB_CRITICAL_THRESHOLD_GB" | bc -l)" == "1" ]]; then
        send_alert "CRITICAL" "Database Size Critical" \
            "Database size: ${db_size}GB (≥${DB_CRITICAL_THRESHOLD_GB}GB)" \
            "db_critical"
    elif [[ "$(echo "$db_size >= $DB_WARNING_THRESHOLD_GB" | bc -l)" == "1" ]]; then
        send_alert "WARNING" "Database Size Warning" \
            "Database size: ${db_size}GB (≥${DB_WARNING_THRESHOLD_GB}GB)" \
            "db_warning"
    fi
    
    echo "$db_size"
}

monitor_docker_size() {
    local docker_size=$(get_docker_size_gb)
    
    save_metric "docker_size_gb" "$docker_size"
    
    if [[ "$(echo "$docker_size >= $DOCKER_CRITICAL_THRESHOLD_GB" | bc -l)" == "1" ]]; then
        send_alert "CRITICAL" "Docker Size Critical" \
            "Docker usage: ${docker_size}GB (≥${DOCKER_CRITICAL_THRESHOLD_GB}GB)" \
            "docker_critical"
    elif [[ "$(echo "$docker_size >= $DOCKER_WARNING_THRESHOLD_GB" | bc -l)" == "1" ]]; then
        send_alert "WARNING" "Docker Size Warning" \
            "Docker usage: ${docker_size}GB (≥${DOCKER_WARNING_THRESHOLD_GB}GB)" \
            "docker_warning"
    fi
    
    echo "$docker_size"
}

# Health check function
health_check() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local status_file="${METRICS_DIR}/health_status.json"
    
    # Collect all metrics
    local disk_usage=$(monitor_disk_space)
    local db_size=$(monitor_database_size)
    local docker_size=$(monitor_docker_size)
    local disk_available=$(get_disk_available_gb)
    
    # Check database connectivity
    local db_status="down"
    if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c '\q' 2>/dev/null; then
        db_status="up"
    fi
    
    # Check Docker status
    local docker_status="down"
    if docker system df &> /dev/null; then
        docker_status="up"
    fi
    
    # Determine overall health
    local overall_status="healthy"
    if [[ $disk_usage -ge $DISK_CRITICAL_THRESHOLD ]] || \
       [[ "$(echo "$db_size >= $DB_CRITICAL_THRESHOLD_GB" | bc -l)" == "1" ]] || \
       [[ "$db_status" == "down" ]]; then
        overall_status="critical"
    elif [[ $disk_usage -ge $DISK_WARNING_THRESHOLD ]] || \
         [[ "$(echo "$db_size >= $DB_WARNING_THRESHOLD_GB" | bc -l)" == "1" ]] || \
         [[ "$(echo "$docker_size >= $DOCKER_WARNING_THRESHOLD_GB" | bc -l)" == "1" ]]; then
        overall_status="warning"
    fi
    
    # Create health status JSON
    cat > "$status_file" <<EOF
{
    "timestamp": "$timestamp",
    "overall_status": "$overall_status",
    "disk": {
        "usage_percent": $disk_usage,
        "available_gb": $disk_available,
        "warning_threshold": $DISK_WARNING_THRESHOLD,
        "critical_threshold": $DISK_CRITICAL_THRESHOLD
    },
    "database": {
        "size_gb": $db_size,
        "status": "$db_status",
        "warning_threshold": $DB_WARNING_THRESHOLD_GB,
        "critical_threshold": $DB_CRITICAL_THRESHOLD_GB
    },
    "docker": {
        "size_gb": $docker_size,
        "status": "$docker_status",
        "warning_threshold": $DOCKER_WARNING_THRESHOLD_GB,
        "critical_threshold": $DOCKER_CRITICAL_THRESHOLD_GB
    }
}
EOF
    
    log_info "Health check completed - Status: $overall_status, Disk: ${disk_usage}%, DB: ${db_size}GB, Docker: ${docker_size}GB"
    
    return 0
}

# Continuous monitoring function
continuous_monitor() {
    log_info "Starting continuous monitoring (interval: ${MONITOR_INTERVAL}s)"
    
    while true; do
        health_check
        sleep "$MONITOR_INTERVAL"
    done
}

# Generate monitoring report
generate_report() {
    local report_file="${METRICS_DIR}/space_report_$(date +%Y%m%d_%H%M%S).txt"
    
    cat > "$report_file" <<EOF
=============================================================================
CEX ARBITRAGE SPACE MONITORING REPORT
Generated: $(date '+%Y-%m-%d %H:%M:%S')
=============================================================================

CURRENT STATUS:
$(cat "${METRICS_DIR}/health_status.json" 2>/dev/null || echo "No health data available")

DISK USAGE TREND (Last 24 hours):
$(if [[ -f "${METRICS_DIR}/disk_usage_percent_$(date +%Y%m%d).csv" ]]; then
    tail -n 288 "${METRICS_DIR}/disk_usage_percent_$(date +%Y%m%d).csv" | \
    awk -F',' 'NR>1 {sum+=$2; count++; if(min=="" || $2<min) min=$2; if(max=="" || $2>max) max=$2} END {printf "Average: %.1f%%, Min: %s%%, Max: %s%%\n", sum/count, min, max}'
else
    echo "No data available"
fi)

DATABASE SIZE TREND (Last 24 hours):
$(if [[ -f "${METRICS_DIR}/database_size_gb_$(date +%Y%m%d).csv" ]]; then
    tail -n 288 "${METRICS_DIR}/database_size_gb_$(date +%Y%m%d).csv" | \
    awk -F',' 'NR>1 {sum+=$2; count++; if(min=="" || $2<min) min=$2; if(max=="" || $2>max) max=$2} END {printf "Average: %.2fGB, Min: %.2fGB, Max: %.2fGB\n", sum/count, min, max}'
else
    echo "No data available"
fi)

DOCKER SIZE TREND (Last 24 hours):
$(if [[ -f "${METRICS_DIR}/docker_size_gb_$(date +%Y%m%d).csv" ]]; then
    tail -n 288 "${METRICS_DIR}/docker_size_gb_$(date +%Y%m%d).csv" | \
    awk -F',' 'NR>1 {sum+=$2; count++; if(min=="" || $2<min) min=$2; if(max=="" || $2>max) max=$2} END {printf "Average: %.2fGB, Min: %.2fGB, Max: %.2fGB\n", sum/count, min, max}'
else
    echo "No data available"
fi)

DATABASE TABLE SIZES:
$(get_database_table_sizes)

RECENT ALERTS (Last 24 hours):
$(find "${METRICS_DIR}" -name "alerts_*.log" -mtime -1 -exec cat {} \; 2>/dev/null | tail -20 || echo "No recent alerts")

RECOMMENDATIONS:
$(
if [[ $(get_disk_usage) -gt 85 ]]; then
    echo "- Disk usage high: Consider running cleanup maintenance"
fi
if [[ "$(echo "$(get_database_size_gb) > 6" | bc -l)" == "1" ]]; then
    echo "- Database size large: Review retention policies"
fi
if [[ "$(echo "$(get_docker_size_gb) > 8" | bc -l)" == "1" ]]; then
    echo "- Docker size large: Run Docker cleanup"
fi
echo "- Monitor trends and adjust thresholds as needed"
)

=============================================================================
EOF
    
    echo "$report_file"
}

# Cleanup old metrics and logs
cleanup_old_data() {
    local retention_days="${1:-7}"
    
    log_info "Cleaning up data older than $retention_days days"
    
    # Clean old metric files
    find "$METRICS_DIR" -name "*.csv" -mtime +$retention_days -delete 2>/dev/null || true
    find "$METRICS_DIR" -name "alerts_*.log" -mtime +$retention_days -delete 2>/dev/null || true
    
    # Clean old log files
    find "$LOG_DIR" -name "space_monitor.log.*" -mtime +$retention_days -delete 2>/dev/null || true
    
    log_info "Cleanup completed"
}

# Dashboard function (simple text-based)
show_dashboard() {
    clear
    echo -e "${CYAN}=== CEX ARBITRAGE SPACE MONITORING DASHBOARD ===${NC}"
    echo -e "${CYAN}Last Updated: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo ""
    
    # Current metrics
    local disk_usage=$(get_disk_usage)
    local db_size=$(get_database_size_gb)
    local docker_size=$(get_docker_size_gb)
    local disk_available=$(get_disk_available_gb)
    
    # Disk usage
    echo -e "${BLUE}DISK USAGE:${NC}"
    printf "  Usage: %d%% " "$disk_usage"
    if [[ $disk_usage -ge $DISK_CRITICAL_THRESHOLD ]]; then
        echo -e "${RED}[CRITICAL]${NC}"
    elif [[ $disk_usage -ge $DISK_WARNING_THRESHOLD ]]; then
        echo -e "${YELLOW}[WARNING]${NC}"
    else
        echo -e "${GREEN}[OK]${NC}"
    fi
    echo "  Available: ${disk_available}GB"
    echo ""
    
    # Database size
    echo -e "${BLUE}DATABASE:${NC}"
    printf "  Size: %.2fGB " "$db_size"
    if [[ "$(echo "$db_size >= $DB_CRITICAL_THRESHOLD_GB" | bc -l)" == "1" ]]; then
        echo -e "${RED}[CRITICAL]${NC}"
    elif [[ "$(echo "$db_size >= $DB_WARNING_THRESHOLD_GB" | bc -l)" == "1" ]]; then
        echo -e "${YELLOW}[WARNING]${NC}"
    else
        echo -e "${GREEN}[OK]${NC}"
    fi
    echo ""
    
    # Docker size
    echo -e "${BLUE}DOCKER:${NC}"
    printf "  Size: %.2fGB " "$docker_size"
    if [[ "$(echo "$docker_size >= $DOCKER_CRITICAL_THRESHOLD_GB" | bc -l)" == "1" ]]; then
        echo -e "${RED}[CRITICAL]${NC}"
    elif [[ "$(echo "$docker_size >= $DOCKER_WARNING_THRESHOLD_GB" | bc -l)" == "1" ]]; then
        echo -e "${YELLOW}[WARNING]${NC}"
    else
        echo -e "${GREEN}[OK]${NC}"
    fi
    echo ""
    
    # Recent alerts
    echo -e "${BLUE}RECENT ALERTS:${NC}"
    if [[ -f "${METRICS_DIR}/alerts_$(date +%Y%m%d).log" ]]; then
        tail -5 "${METRICS_DIR}/alerts_$(date +%Y%m%d).log" 2>/dev/null || echo "  No alerts today"
    else
        echo "  No alerts today"
    fi
    echo ""
    
    echo -e "${CYAN}Press Ctrl+C to exit dashboard${NC}"
}

# Live dashboard
live_dashboard() {
    while true; do
        show_dashboard
        sleep 10
    done
}

# Main function
main() {
    local action="${1:-help}"
    
    case "$action" in
        "check")
            health_check
            ;;
        "monitor")
            continuous_monitor
            ;;
        "dashboard")
            live_dashboard
            ;;
        "report")
            report_file=$(generate_report)
            echo "Report generated: $report_file"
            cat "$report_file"
            ;;
        "status")
            show_dashboard
            ;;
        "cleanup")
            cleanup_old_data "${2:-7}"
            ;;
        "alert-test")
            send_alert "WARNING" "Test Alert" "This is a test alert from the monitoring system" "test"
            ;;
        *)
            echo "Usage: $0 {check|monitor|dashboard|report|status|cleanup [days]|alert-test}"
            echo ""
            echo "Commands:"
            echo "  check      - Run single health check"
            echo "  monitor    - Start continuous monitoring"
            echo "  dashboard  - Show live dashboard"
            echo "  report     - Generate detailed report"
            echo "  status     - Show current status (one-time)"
            echo "  cleanup    - Clean old metrics and logs"
            echo "  alert-test - Send test alert"
            exit 1
            ;;
    esac
}

# Execute main function
main "$@"