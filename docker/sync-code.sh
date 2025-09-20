#!/bin/bash

# =============================================================================
# Code Sync Script for CEX Arbitrage Development
# =============================================================================
# This script syncs code from your development machine to the production server
# Use this for rapid development cycles without committing to git

set -e

# Configuration
REMOTE_HOST="${REMOTE_HOST:-root@139.180.134.54}"
REMOTE_KEY="${REMOTE_KEY:-~/.ssh/id_rsa_old}"
REMOTE_PATH="${REMOTE_PATH:-/opt/arbitrage/}"
LOCAL_SOURCE="${LOCAL_SOURCE:-/Users/dasein/dev/cex_arbitrage/}"

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
    echo "🔄 CEX Arbitrage Code Sync"
    echo "========================="
    echo "From: $LOCAL_SOURCE"
    echo "To:   $REMOTE_HOST:$REMOTE_PATH"
    echo "Time: $(date)"
    echo ""
}

check_prerequisites() {
    echo_info "Checking prerequisites..."
    
    # Check if source directory exists
    if [ ! -d "$LOCAL_SOURCE" ]; then
        echo_error "Source directory not found: $LOCAL_SOURCE"
        exit 1
    fi
    
    # Check if SSH key exists
    if [ ! -f "$REMOTE_KEY" ]; then
        echo_error "SSH key not found: $REMOTE_KEY"
        exit 1
    fi
    
    # Check if rsync is available
    if ! command -v rsync &> /dev/null; then
        echo_error "rsync is not installed"
        exit 1
    fi
    
    # Test SSH connection
    echo_info "Testing SSH connection..."
    if ssh -i "$REMOTE_KEY" -o ConnectTimeout=10 -o BatchMode=yes "$REMOTE_HOST" exit 2>/dev/null; then
        echo_success "SSH connection successful"
    else
        echo_error "SSH connection failed"
        exit 1
    fi
    
    echo_success "Prerequisites check passed"
}

sync_code() {
    echo_info "Syncing source code..."
    
    # Create exclusion file path
    EXCLUDE_FILE="$LOCAL_SOURCE/docker/.rsync-exclude"
    
    # Build rsync command
    RSYNC_CMD="rsync -avz --progress --delete"
    
    # Add exclusion file if it exists
    if [ -f "$EXCLUDE_FILE" ]; then
        RSYNC_CMD="$RSYNC_CMD --exclude-from=$EXCLUDE_FILE"
        echo_info "Using exclusion patterns from: $EXCLUDE_FILE"
    else
        # Default exclusions if no file
        RSYNC_CMD="$RSYNC_CMD --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='.venv' --exclude='docker/data' --exclude='docker/.env.prod'"
        echo_warning "No exclusion file found, using default exclusions"
    fi
    
    # Add SSH options
    RSYNC_CMD="$RSYNC_CMD -e 'ssh -i $REMOTE_KEY'"
    
    echo_info "Executing: $RSYNC_CMD"
    echo_info "Source: $LOCAL_SOURCE"
    echo_info "Destination: $REMOTE_HOST:$REMOTE_PATH"
    echo ""
    
    # Perform the sync
    eval "$RSYNC_CMD '$LOCAL_SOURCE' '$REMOTE_HOST:$REMOTE_PATH'"
    
    if [ $? -eq 0 ]; then
        echo_success "Code sync completed successfully"
    else
        echo_error "Code sync failed"
        return 1
    fi
}

update_collector() {
    echo_info "Updating data collector on remote server..."
    
    # Execute remote update command
    ssh -i "$REMOTE_KEY" "$REMOTE_HOST" << 'EOF'
cd /opt/arbitrage/docker
echo "🔄 Updating collector with new code..."
./deploy-server.sh update-collector
EOF
    
    if [ $? -eq 0 ]; then
        echo_success "Remote collector updated successfully"
    else
        echo_warning "Remote collector update may have issues - check manually"
    fi
}

show_remote_status() {
    echo_info "Checking remote system status..."
    
    ssh -i "$REMOTE_KEY" "$REMOTE_HOST" << 'EOF'
cd /opt/arbitrage/docker
echo "📊 Remote System Status:"
./deploy-server.sh status
echo ""
echo "📈 Recent Data Check:"
./deploy-server.sh check-data
EOF
}

print_sync_summary() {
    echo ""
    echo_success "🎉 Code sync completed!"
    echo "======================"
    echo ""
    echo "✅ Actions performed:"
    echo "   - Source code synced to production server"
    echo "   - Data collector updated with new code"
    echo "   - System status verified"
    echo ""
    echo "🔗 Access your system:"
    echo "   📊 Grafana:  http://139.180.134.54:3000"
    echo "   🔧 PgAdmin:  http://139.180.134.54:8080"
    echo ""
    echo "🛠️  Remote management:"
    echo "   SSH:      ssh -i $REMOTE_KEY $REMOTE_HOST"
    echo "   Logs:     ssh -i $REMOTE_KEY $REMOTE_HOST 'cd /opt/arbitrage/docker && ./deploy-server.sh logs'"
    echo "   Status:   ssh -i $REMOTE_KEY $REMOTE_HOST 'cd /opt/arbitrage/docker && ./deploy-server.sh status'"
    echo ""
    echo_info "Development workflow ready! Make changes locally and run ./sync-code.sh to update server."
}

# Main sync flow
main() {
    print_header
    check_prerequisites
    sync_code
    update_collector
    show_remote_status
    print_sync_summary
}

# Handle script arguments
case "${1:-sync}" in
    "sync")
        main
        ;;
    "dry-run")
        echo_info "Performing dry run (no actual sync)..."
        print_header
        check_prerequisites
        
        # Dry run rsync
        EXCLUDE_FILE="$LOCAL_SOURCE/docker/.rsync-exclude"
        RSYNC_CMD="rsync -avz --dry-run --delete"
        
        if [ -f "$EXCLUDE_FILE" ]; then
            RSYNC_CMD="$RSYNC_CMD --exclude-from=$EXCLUDE_FILE"
        else
            RSYNC_CMD="$RSYNC_CMD --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='.venv'"
        fi
        
        RSYNC_CMD="$RSYNC_CMD -e 'ssh -i $REMOTE_KEY'"
        
        echo_info "Files that would be synced:"
        eval "$RSYNC_CMD '$LOCAL_SOURCE' '$REMOTE_HOST:$REMOTE_PATH'"
        ;;
    "quick")
        echo_info "Quick sync (code only, no collector update)..."
        print_header
        check_prerequisites
        sync_code
        echo_success "Quick sync completed"
        ;;
    "status")
        echo_info "Checking remote status only..."
        check_prerequisites
        show_remote_status
        ;;
    *)
        echo "CEX Arbitrage Code Sync Tool"
        echo "Usage: $0 {sync|dry-run|quick|status}"
        echo ""
        echo "Commands:"
        echo "  sync     - Full sync with collector update (default)"
        echo "  dry-run  - Show what would be synced without doing it"
        echo "  quick    - Sync code only, no collector restart"
        echo "  status   - Check remote system status"
        echo ""
        echo "Environment variables:"
        echo "  REMOTE_HOST=$REMOTE_HOST"
        echo "  REMOTE_KEY=$REMOTE_KEY"
        echo "  REMOTE_PATH=$REMOTE_PATH"
        echo "  LOCAL_SOURCE=$LOCAL_SOURCE"
        echo ""
        echo "Examples:"
        echo "  ./sync-code.sh                    # Full sync"
        echo "  ./sync-code.sh dry-run            # Preview changes"
        echo "  ./sync-code.sh quick              # Fast sync"
        echo "  REMOTE_HOST=user@server ./sync-code.sh  # Custom host"
        exit 1
        ;;
esac