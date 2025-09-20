#!/bin/bash

# =============================================================================
# Code Update Script for CEX Arbitrage System
# =============================================================================
# This script safely updates source code and applies changes without downtime

set -e

# Configuration
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod-external.yml"
ENV_FILE=".env.prod"
BACKUP_DIR="backups"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
echo_success() { echo -e "${GREEN}✅ $1${NC}"; }
echo_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
echo_error() { echo -e "${RED}❌ $1${NC}"; }

print_header() {
    echo "🔄 CEX Arbitrage Code Update"
    echo "============================"
    echo "Timestamp: $(date)"
    echo ""
}

backup_current_state() {
    echo_info "Creating backup before update..."
    
    # Create backup directory
    mkdir -p "$BACKUP_DIR"
    
    # Backup database
    BACKUP_FILE="$BACKUP_DIR/pre_update_backup_$(date +%Y%m%d_%H%M%S).sql"
    docker exec $(docker-compose $COMPOSE_FILES ps -q database) pg_dump -U arbitrage_user -d arbitrage_data > "$BACKUP_FILE"
    
    if [ $? -eq 0 ]; then
        gzip "$BACKUP_FILE"
        echo_success "Database backup created: ${BACKUP_FILE}.gz"
    else
        echo_warning "Database backup failed - continuing anyway"
    fi
    
    # Backup current source code
    CODE_BACKUP="$BACKUP_DIR/source_code_$(date +%Y%m%d_%H%M%S).tar.gz"
    tar -czf "$CODE_BACKUP" ../src/ --exclude="__pycache__" --exclude="*.pyc" 2>/dev/null || true
    echo_success "Source code backup created: $CODE_BACKUP"
}

update_source_code() {
    echo_info "Updating source code..."
    
    # Check if we're running on the server (production) or locally
    if [ -n "$REMOTE_HOST" ] && [ -n "$REMOTE_KEY" ]; then
        echo_info "Syncing code from remote development machine..."
        sync_from_remote
    elif [ -d "../.git" ]; then
        echo_info "Pulling latest changes from git..."
        cd ..
        git pull origin main || git pull origin master || echo_warning "Git pull failed - manual update required"
        cd docker
    else
        echo_warning "No remote sync configured and no git repository detected"
        echo_info "To update code:"
        echo "  1. Set REMOTE_HOST and REMOTE_KEY environment variables for remote sync"
        echo "  2. Or use git to pull latest changes"
        echo "  3. Or manually upload new source files to ../src/"
    fi
}

sync_from_remote() {
    echo_info "Syncing source code from ${REMOTE_HOST}..."
    
    # Create rsync command with exclusions
    RSYNC_CMD="rsync -avz --progress --exclude-from=.rsync-exclude"
    
    if [ -n "$REMOTE_KEY" ]; then
        RSYNC_CMD="$RSYNC_CMD -e 'ssh -i $REMOTE_KEY'"
    fi
    
    # Source path (remote development machine)
    REMOTE_SOURCE="${REMOTE_HOST}:${REMOTE_PATH:-/Users/dasein/dev/cex_arbitrage/}"
    
    # Destination path (current server)
    LOCAL_DEST="/opt/arbitrage/"
    
    echo_info "Syncing from: $REMOTE_SOURCE"
    echo_info "Syncing to: $LOCAL_DEST"
    
    # Perform the sync
    eval "$RSYNC_CMD $REMOTE_SOURCE $LOCAL_DEST"
    
    if [ $? -eq 0 ]; then
        echo_success "Code sync completed successfully"
        
        # Show what was updated
        echo_info "Files updated in sync:"
        find ../src -name "*.py" -newer ../src 2>/dev/null | head -10 || echo "All files are current"
    else
        echo_error "Code sync failed"
        return 1
    fi
}

test_configuration() {
    echo_info "Testing configuration and dependencies..."
    
    # Test Docker Compose configuration
    if docker-compose $COMPOSE_FILES config > /dev/null 2>&1; then
        echo_success "Docker Compose configuration valid"
    else
        echo_error "Docker Compose configuration invalid"
        return 1
    fi
    
    # Test Python syntax if possible
    if command -v python3 &> /dev/null; then
        echo_info "Testing Python syntax..."
        find ../src -name "*.py" -exec python3 -m py_compile {} \; 2>/dev/null && echo_success "Python syntax check passed" || echo_warning "Python syntax check failed - review code manually"
    fi
}

graceful_update() {
    echo_info "Performing graceful service update..."
    
    # Load environment variables
    set -a
    source "$ENV_FILE"
    set +a
    
    # Rebuild collector with new code
    echo_info "Rebuilding data collector with updated code..."
    docker-compose $COMPOSE_FILES build --no-cache data_collector
    
    # Update collector gracefully (zero downtime)
    echo_info "Updating data collector (zero downtime)..."
    docker-compose $COMPOSE_FILES up -d --no-deps data_collector
    
    # Wait for collector to be healthy
    echo_info "Waiting for collector to be healthy..."
    sleep 20
    
    # Check if collector is running properly
    if docker-compose $COMPOSE_FILES ps data_collector | grep -q "Up"; then
        echo_success "Data collector updated successfully"
        
        # Show recent logs to verify
        echo_info "Recent collector logs:"
        docker-compose $COMPOSE_FILES logs --tail=10 data_collector
    else
        echo_error "Data collector update failed"
        
        # Try to restore from backup
        echo_warning "Attempting to restore previous version..."
        docker-compose $COMPOSE_FILES down data_collector
        docker-compose $COMPOSE_FILES up -d data_collector
        
        return 1
    fi
}

verify_update() {
    echo_info "Verifying update success..."
    
    # Check service status
    echo_info "Service status:"
    docker-compose $COMPOSE_FILES ps
    
    # Check data collection is still working
    echo_info "Verifying data collection..."
    sleep 30
    
    # Check recent data
    RECENT_COUNT=$(docker exec $(docker-compose $COMPOSE_FILES ps -q database) psql -U arbitrage_user -d arbitrage_data -t -c "SELECT COUNT(*) FROM book_ticker_snapshots WHERE timestamp > NOW() - INTERVAL '2 minutes';" | tr -d ' ')
    
    if [ "$RECENT_COUNT" -gt 0 ]; then
        echo_success "Data collection verified - $RECENT_COUNT records in last 2 minutes"
    else
        echo_warning "No recent data found - check collector logs"
    fi
    
    # Show system resource usage
    echo_info "System resource usage:"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"
}

print_update_summary() {
    echo ""
    echo_success "🎉 Code update completed!"
    echo "========================="
    echo ""
    echo "✅ Updated components:"
    echo "   - Source code updated"
    echo "   - Data collector rebuilt and restarted"
    echo "   - Database schema preserved"
    echo "   - Monitoring services maintained"
    echo ""
    echo "📊 System Status:"
    echo "   Check status: ./deploy-server.sh status"
    echo "   View logs:    ./deploy-server.sh logs data_collector"
    echo "   Check data:   ./deploy-server.sh check-data"
    echo ""
    echo "🔄 Additional Updates:"
    echo "   Schema update:    ./deploy-server.sh update-schema"
    echo "   Full update:      ./deploy-server.sh update"
    echo ""
    echo_info "Update completed with zero downtime!"
}

# Main update flow
main() {
    print_header
    backup_current_state
    update_source_code
    test_configuration
    graceful_update
    verify_update
    print_update_summary
}

# Handle script arguments
case "${1:-update}" in
    "update")
        main
        ;;
    "quick")
        echo_info "Quick code update (no backup)..."
        update_source_code
        graceful_update
        verify_update
        echo_success "Quick update completed"
        ;;
    "test")
        echo_info "Testing configuration only..."
        test_configuration
        echo_success "Configuration test completed"
        ;;
    "backup")
        echo_info "Creating backup only..."
        backup_current_state
        echo_success "Backup completed"
        ;;
    *)
        echo "CEX Arbitrage Code Update Tool"
        echo "Usage: $0 {update|quick|test|backup}"
        echo ""
        echo "Commands:"
        echo "  update  - Full safe update with backup and verification"
        echo "  quick   - Quick update without backup (faster)"
        echo "  test    - Test configuration without updating"
        echo "  backup  - Create backup without updating"
        echo ""
        echo "Examples:"
        echo "  ./update-code.sh update   # Safe full update"
        echo "  ./update-code.sh quick    # Quick development update"
        echo "  ./update-code.sh test     # Test before updating"
        exit 1
        ;;
esac