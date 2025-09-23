#!/bin/bash

# =============================================================================
# Server Disk Space Cleanup Script
# =============================================================================
# Clean up Docker images, build cache, and other space-consuming files

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
echo_success() { echo -e "${GREEN}✅ $1${NC}"; }
echo_error() { echo -e "${RED}❌ $1${NC}"; }
echo_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }

show_disk_usage() {
    echo_info "Current disk usage:"
    df -h / | tail -n 1
    echo ""
}

cleanup_docker() {
    echo_info "Cleaning up Docker..."
    
    # Show current Docker usage
    echo "Current Docker space usage:"
    docker system df
    echo ""
    
    # Remove unused containers
    echo_info "Removing stopped containers..."
    docker container prune -f
    
    # Remove unused images (keep current ones)
    echo_info "Removing unused images..."
    docker image prune -f
    
    # Remove dangling images
    echo_info "Removing dangling images..."
    docker images -f "dangling=true" -q | xargs -r docker rmi -f
    
    # Clean build cache (this can free significant space)
    echo_info "Cleaning build cache..."
    docker builder prune -f
    
    # Remove unused networks
    echo_info "Removing unused networks..."
    docker network prune -f
    
    # Remove unused volumes (be careful with data)
    echo_info "Checking for unused volumes..."
    docker volume ls -qf dangling=true | while read volume; do
        echo_warning "Found dangling volume: $volume"
        echo "Use 'docker volume rm $volume' to remove if safe"
    done
    
    echo_success "Docker cleanup completed"
    echo "New Docker space usage:"
    docker system df
    echo ""
}

cleanup_old_projects() {
    echo_info "Checking old projects in /root..."
    
    cd /root
    
    # List directories with sizes
    du -h --max-depth=1 . | sort -hr
    echo ""
    
    echo_warning "Large directories found in /root:"
    echo "- freqtrade (434M) - Trading bot"
    echo "- vector_bt_bot (128M) - Vector bot"
    echo "- mexc_bot (29M) - MEXC bot"
    echo ""
    echo "Consider removing unused projects manually:"
    echo "rm -rf /root/freqtrade      # If no longer needed"
    echo "rm -rf /root/vector_bt_bot  # If no longer needed"
    echo "rm -rf /root/mexc_bot       # If no longer needed"
}

cleanup_logs() {
    echo_info "Cleaning up log files..."
    
    # Clean journal logs older than 7 days
    journalctl --vacuum-time=7d
    
    # Clean old log files
    find /var/log -name "*.log.1" -delete 2>/dev/null || true
    find /var/log -name "*.log.*.gz" -delete 2>/dev/null || true
    
    echo_success "Log cleanup completed"
}

cleanup_apt_cache() {
    echo_info "Cleaning APT cache..."
    
    apt-get clean
    apt-get autoclean
    apt-get autoremove -y
    
    echo_success "APT cache cleaned"
}

aggressive_cleanup() {
    echo_warning "AGGRESSIVE CLEANUP - This will remove old Docker images"
    echo "This might break things if containers depend on them!"
    read -p "Are you sure? (y/N) " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo_info "Performing aggressive Docker cleanup..."
        
        # Stop all containers except database
        echo "Stopping non-essential containers..."
        docker ps --format "table {{.Names}}" | grep -v arbitrage_db | grep -v NAMES | xargs -r docker stop
        
        # Remove all stopped containers
        docker container prune -f
        
        # Remove all unused images
        docker image prune -a -f
        
        # Clean everything
        docker system prune -a -f
        
        echo_success "Aggressive cleanup completed"
    else
        echo "Aggressive cleanup cancelled"
    fi
}

analyze_database() {
    echo_info "Analyzing database space usage..."
    
    # Check PostgreSQL data directory size
    echo "PostgreSQL data directory size:"
    docker exec arbitrage_db du -h /var/lib/postgresql/data | tail -1
    
    # Check individual table sizes
    echo ""
    echo "Database table sizes:"
    docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "
    SELECT 
        schemaname,
        tablename,
        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
        pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) as table_size,
        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) as index_size
    FROM pg_tables 
    WHERE schemaname = 'public'
    ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
    "
    
    echo ""
    echo "TimescaleDB chunks and compression status:"
    docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "
    SELECT 
        hypertable_name,
        pg_size_pretty(hypertable_size(hypertable_name)) as size,
        compression_enabled,
        (SELECT count(*) FROM timescaledb_information.chunks WHERE hypertable_name = ht.hypertable_name) as chunk_count
    FROM timescaledb_information.hypertables ht;
    "
    
    echo ""
    echo "Recent data volume (last 24 hours):"
    docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "
    SELECT 
        exchange,
        symbol_base,
        symbol_quote,
        COUNT(*) as records,
        MIN(timestamp) as first_record,
        MAX(timestamp) as last_record
    FROM book_ticker_snapshots 
    WHERE timestamp > NOW() - INTERVAL '24 hours'
    GROUP BY exchange, symbol_base, symbol_quote
    ORDER BY records DESC
    LIMIT 10;
    "
}

deep_analysis() {
    echo_info "Performing deep system analysis..."
    
    echo "=== DISK USAGE BY MAJOR CATEGORIES ==="
    echo "Docker: $(du -sh /var/lib/docker 2>/dev/null | cut -f1)"
    echo "System: $(du -sh /usr 2>/dev/null | cut -f1)"
    echo "Projects: $(du -sh /root 2>/dev/null | cut -f1)"
    echo "Logs: $(du -sh /var/log 2>/dev/null | cut -f1)"
    echo "Cache: $(du -sh /var/cache 2>/dev/null | cut -f1)"
    echo ""
    
    echo "=== TOP 20 LARGEST DIRECTORIES ==="
    find / -type d -exec du -sh {} + 2>/dev/null | sort -hr | head -20
    echo ""
    
    echo "=== LARGEST FILES (>50MB) ==="
    find / -type f -size +50M -exec ls -lh {} + 2>/dev/null | sort -k5 -hr | head -10
    echo ""
    
    analyze_database
}

case "${1:-help}" in
    "docker")
        show_disk_usage
        cleanup_docker
        show_disk_usage
        ;;
    "logs")
        show_disk_usage
        cleanup_logs
        show_disk_usage
        ;;
    "apt")
        show_disk_usage
        cleanup_apt_cache
        show_disk_usage
        ;;
    "projects")
        cleanup_old_projects
        ;;
    "database")
        analyze_database
        ;;
    "analyze")
        deep_analysis
        ;;
    "all")
        show_disk_usage
        cleanup_docker
        cleanup_logs
        cleanup_apt_cache
        cleanup_old_projects
        show_disk_usage
        ;;
    "aggressive")
        show_disk_usage
        aggressive_cleanup
        show_disk_usage
        ;;
    "status")
        show_disk_usage
        echo_info "Docker space usage:"
        docker system df
        echo ""
        echo_info "Largest directories:"
        du -h --max-depth=1 / 2>/dev/null | sort -hr | head -10
        ;;
    "help"|*)
        echo "Server Disk Space Cleanup Script"
        echo ""
        echo "Usage: $0 {command}"
        echo ""
        echo "Commands:"
        echo "  docker      - Clean Docker images, containers, cache"
        echo "  logs        - Clean log files and journal"
        echo "  apt         - Clean APT cache and packages"
        echo "  projects    - Show old projects for manual removal"
        echo "  database    - Analyze database space usage"
        echo "  analyze     - Deep system analysis"
        echo "  all         - Run all safe cleanup operations"
        echo "  aggressive  - Aggressive Docker cleanup (DANGEROUS)"
        echo "  status      - Show current disk usage"
        echo "  help        - Show this help message"
        echo ""
        echo "Recommended usage:"
        echo "  ./cleanup-server.sh docker    # Clean Docker (safest)"
        echo "  ./cleanup-server.sh analyze   # Deep analysis"
        echo "  ./cleanup-server.sh database  # Check DB usage"
        echo "  ./cleanup-server.sh all       # Full safe cleanup"
        ;;
esac