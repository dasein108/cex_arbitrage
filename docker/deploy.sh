#!/bin/bash

# =============================================================================
# Simple CEX Arbitrage Server Deployment
# =============================================================================
# KISS principle: Simple script to sync code and deploy to 139.180.134.54

set -e
# Configuration
SERVER="31.192.233.13"
SSH_KEY="~/.ssh/deploy_ci_o"
REMOTE_PATH="/opt/arbitrage"
LOCAL_PATH="/Users/dasein/dev/cex_arbitrage"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
echo_success() { echo -e "${GREEN}✅ $1${NC}"; }
echo_error() { echo -e "${RED}❌ $1${NC}"; }

sync_code() {
    echo_info "Syncing code to server..."
    
    # Ensure we're using correct paths regardless of where script is run from
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
    EXCLUDE_FILE="$SCRIPT_DIR/.rsync-exclude"
    
    rsync -avz --progress \
        --exclude-from="$EXCLUDE_FILE" \
        -e "ssh -i $SSH_KEY" \
        -v \
        "$PROJECT_ROOT/" \
        "root@$SERVER:$REMOTE_PATH/"
        
    echo_success "Code synced"
    
    # Auto-restart services after sync unless explicitly disabled
    if [ "${SKIP_RESTART:-false}" != "true" ]; then
        echo_info "Auto-restarting services after code sync..."
        ssh -i "$SSH_KEY" "root@$SERVER" << 'EOF'
cd /opt/arbitrage/docker

# Verify Docker Compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "⚠️  Docker Compose not found - skipping restart"
    exit 0
fi

# Check if services are running before restarting
if docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml ps --services --filter "status=running" | grep -q "data_collector"; then
    echo "Restarting data collector with updated code..."
    docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml restart data_collector
    echo "✅ Data collector restarted"
else
    echo "ℹ️  Data collector not running - no restart needed"
fi
EOF
    fi
}

deploy_server() {
    echo_info "Deploying on server..."
    
    ssh -i "$SSH_KEY" "root@$SERVER" << 'EOF'
cd /opt/arbitrage/docker

# Install Docker if needed
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh
fi

# Install Docker Compose if needed
if ! command -v docker-compose &> /dev/null; then
    echo "Installing Docker Compose..."
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    
    # Also try to install via pip as fallback
    if command -v pip3 &> /dev/null; then
        pip3 install docker-compose
    fi
fi

# Setup swap for 4GB server optimization
if [ ! -f "/swapfile" ]; then
    echo "Setting up swap space for memory optimization..."
    ./setup-swap.sh
else
    echo "Swap already configured"
fi

# Verify Docker Compose is working
if ! docker-compose --version &> /dev/null; then
    echo "❌ Docker Compose installation failed"
    exit 1
fi

# Generate passwords if needed
if [ ! -f ".env.prod" ]; then
    ./generate-passwords.sh
    echo "⚠️  EDIT .env.prod WITH YOUR API CREDENTIALS!"
fi

# Create required data directories
echo "Creating data directories..."
sudo mkdir -p /opt/arbitrage/data/{postgres,pgadmin,grafana}
sudo mkdir -p /opt/arbitrage/backups
sudo mkdir -p /opt/arbitrage/logs

# Set proper ownership and permissions
sudo chown -R root:root /opt/arbitrage/data /opt/arbitrage/backups /opt/arbitrage/logs
sudo chmod 755 /opt/arbitrage/data /opt/arbitrage/backups /opt/arbitrage/logs
sudo chmod 700 /opt/arbitrage/data/postgres

# Deploy services with explicit env file
echo "Stopping existing services..."
docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml down --remove-orphans || true

echo "Pulling latest images and rebuilding custom images..."
docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml pull
docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml build --no-cache data_collector

echo "Starting database..."
docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d database

# Wait for DB and initialize
echo "Waiting for database to be ready..."
sleep 15

# Get database container name
DB_CONTAINER=$(docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml ps -q database)
if [ -z "$DB_CONTAINER" ]; then
    echo "❌ Database container not found"
    docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml ps
    exit 1
fi

# Wait for database to be ready
echo "Waiting for PostgreSQL to be ready..."
timeout 120 sh -c "until docker exec $DB_CONTAINER pg_isready -U arbitrage_user; do sleep 2; done"

# Initialize database schema
echo "Initializing database schema..."

# First, diagnose current constraint state
echo "Diagnosing database constraints..."
docker exec -i "$DB_CONTAINER" psql -U arbitrage_user -d arbitrage_data < diagnose-constraints.sql || true

# Fix constraints if needed
echo "Fixing constraints if needed..."
docker exec -i "$DB_CONTAINER" psql -U arbitrage_user -d arbitrage_data < fix-constraints.sql

# Apply the full schema (this will be idempotent due to IF NOT EXISTS clauses)
echo "Applying full schema..."
docker exec -i "$DB_CONTAINER" psql -U arbitrage_user -d arbitrage_data < init-db.sql

# Verify constraints are correct
echo "Verifying constraints..."
docker exec -i "$DB_CONTAINER" psql -U arbitrage_user -d arbitrage_data -c "
SELECT 
    tc.constraint_name,
    tc.constraint_type,
    STRING_AGG(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS columns
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
WHERE tc.table_name = 'book_ticker_snapshots'
AND tc.constraint_type = 'PRIMARY KEY'
GROUP BY tc.constraint_name, tc.constraint_type;
"

# Start all services
echo "Starting all services..."
docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d

echo "✅ Deployment complete!"
echo ""
echo "🎯 Production Services (Core Only):"
echo "   📊 Database: Internal (PostgreSQL + TimescaleDB)"
echo "   🔄 Data Collector: Running"
echo ""
echo "📊 Optional Monitoring (enable as needed):"
echo "   docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml --profile monitoring up -d grafana"
echo "   docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml --profile admin up -d pgadmin"
echo ""
echo "🏠 Local Monitoring Setup:"
echo "   Edit .env.local-monitoring with your DB password"
echo "   docker-compose --env-file .env.local-monitoring -f docker-compose.local-monitoring.yml up -d"
echo ""
echo "🔑 Passwords: Check .env.prod on server"
echo "💾 Memory: Optimized for 4GB server with 7-day retention"
EOF

    echo_success "Server deployed"
}

update_only() {
    echo_info "Updating code and configuration..."
    
    # Sync code with auto-restart (default behavior)
    sync_code
    
    # Additional restart logic for comprehensive update
    ssh -i "$SSH_KEY" "root@$SERVER" << 'EOF'
cd /opt/arbitrage/docker

# Verify Docker Compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose not found"
    exit 1
fi

echo "Performing comprehensive service restart for full configuration reload..."
# Full restart cycle for comprehensive update
docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml stop data_collector
docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d data_collector

echo "✅ Comprehensive update complete with full service restart"
EOF

    echo_success "Update complete - full configuration reloaded"
}

rebuild_image() {
    echo_info "Rebuilding Docker image..."
    sync_code
    
    ssh -i "$SSH_KEY" "root@$SERVER" << 'EOF'
cd /opt/arbitrage/docker

# Verify Docker Compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose not found"
    exit 1
fi

echo "Stopping data collector..."
docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml stop data_collector

echo "Rebuilding data collector image with latest dependencies..."
docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml build --no-cache data_collector

echo "Starting data collector with rebuilt image..."
docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d data_collector

echo "✅ Image rebuilt and collector restarted"
EOF

    echo_success "Docker image rebuilt successfully"
}

cleanup_production() {
    echo_info "Cleaning up production server obsolete files..."
    
    ssh -i "$SSH_KEY" "root@$SERVER" << 'EOF'
cd /opt/arbitrage

echo "Removing incorrectly placed files from src/..."
# Remove files that should be in root
if [ -f "src/PROJECT_GUIDES.md" ]; then
    echo "Removing src/PROJECT_GUIDES.md (should be in root)"
    rm -f src/PROJECT_GUIDES.md
fi

if [ -f "src/main.py" ]; then
    echo "Removing src/main.py (should be in root)"
    rm -f src/main.py
fi

echo "Removing obsolete directories from src/..."
# Remove directories that no longer exist in current codebase
for dir in cex core arbitrage interfaces data_collector structs tools; do
    if [ -d "src/$dir" ]; then
        echo "Removing obsolete directory: src/$dir"
        rm -rf "src/$dir"
    fi
done

# Remove obsolete files from root that shouldn't be there
echo "Removing obsolete files from root..."
for file in ARCHITECTURE_DIAGRAM.md COMPLETE_LOGGER_MIGRATION_PLAN.md \
           COMPONENT_INTERFACE_MAPPING.md EXCHANGE_INTEGRATION_GUIDE.md \
           IMPLEMENTATION_CHECKLIST.md LOGGER_INJECTION_IMPLEMENTATION.md \
           LOGGER_INJECTION_PLAN.md LOGGING_PLAN.md MICROSTRUCTURE_ARBITRAGE.md \
           STRATEGY_LOGGER_INJECTION_PLAN.md data_collector_plan.md \
           generic_rest_response.md test_logger_injection.py test_logging_system.py \
           db_analysis_20250923_092330.txt docker_analysis_20250923_092403.txt \
           docker-compose.optimized.yml docker-compose.yml \
           automated_maintenance.sh maintenance_config.conf monitor_config.conf \
           space_monitor.sh; do
    if [ -f "$file" ]; then
        echo "Removing obsolete file: $file"
        rm -f "$file"
    fi
done

# Remove obsolete directories from root
for dir in PRD archive emergency infra; do
    if [ -d "$dir" ]; then
        echo "Removing obsolete directory: $dir"
        rm -rf "$dir"
    fi
done

echo "✅ Production cleanup complete"
EOF

    echo_success "Production server cleaned up"
}

case "${1:-deploy}" in
    "deploy")
        sync_code
        deploy_server
        ;;
    "update")
        update_only
        ;;
    "rebuild")
        rebuild_image
        ;;
    "sync")
        sync_code
        ;;
    "sync-only")
        SKIP_RESTART=true sync_code
        ;;
    "cleanup")
        cleanup_production
        ;;
    "fix")
        echo_info "Running complete fix: cleanup + sync + update"
        cleanup_production
        sync_code
        update_only
        ;;
    *)
        echo "Usage: $0 {deploy|update|rebuild|sync|sync-only|cleanup|fix}"
        echo ""
        echo "Commands:"
        echo "  deploy    - Full deployment (sync + setup + deploy + rebuild)"
        echo "  update    - Update code/config and restart collector (no rebuild)"
        echo "  rebuild   - Rebuild Docker image with new dependencies"
        echo "  sync      - Sync code and auto-restart services (smart restart)"
        echo "  sync-only - Sync code without restarting services"
        echo "  cleanup   - Remove obsolete files from production server"
        echo "  fix       - Complete fix (cleanup + sync + update)"
        echo ""
        echo "Smart Sync Features:"
        echo "  • 'sync' automatically restarts services after code changes"
        echo "  • Only restarts running services (skips stopped services)"
        echo "  • Use 'sync-only' to disable auto-restart behavior"
        echo "  • Use SKIP_RESTART=true with any command to disable restarts"
        echo ""
        echo "Examples:"
        echo "  ./deploy.sh fix             # Fix current deployment issues"
        echo "  ./deploy.sh sync            # Quick code update with smart restart"
        echo "  ./deploy.sh sync-only       # Sync code without restart"
        echo "  ./deploy.sh update          # Update with full restart logic"
        echo "  ./deploy.sh rebuild         # Rebuild image after dependency changes"
        echo "  ./deploy.sh deploy          # Full deployment for new servers"
        echo "  SKIP_RESTART=true ./deploy.sh sync  # Sync without restart"
        exit 1
        ;;
esac