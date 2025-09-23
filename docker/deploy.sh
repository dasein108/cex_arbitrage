#!/bin/bash

# =============================================================================
# Simple CEX Arbitrage Server Deployment
# =============================================================================
# KISS principle: Simple script to sync code and deploy to 139.180.134.54

set -e

# Configuration
SERVER="31.192.233.13"
SSH_KEY="~/.ssh/deploy_ci"
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
    
    rsync -avz --progress \
        --exclude-from=.rsync-exclude \
        -e "ssh -i $SSH_KEY" \
        -v \
        "$LOCAL_PATH/" \
        "root@$SERVER:$REMOTE_PATH/"
        
    echo_success "Code synced"
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
    sync_code
    
    ssh -i "$SSH_KEY" "root@$SERVER" << 'EOF'
cd /opt/arbitrage/docker

# Verify Docker Compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose not found"
    exit 1
fi

echo "Restarting data collector with fresh configuration..."
# Use restart to ensure config volume is properly reloaded
docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml restart data_collector

echo "✅ Collector restarted with new configuration"
EOF

    echo_success "Update complete - configuration reloaded"
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
    *)
        echo "Usage: $0 {deploy|update|rebuild|sync}"
        echo ""
        echo "Commands:"
        echo "  deploy  - Full deployment (sync + setup + deploy + rebuild)"
        echo "  update  - Update code/config and restart collector (no rebuild)"
        echo "  rebuild - Rebuild Docker image with new dependencies"
        echo "  sync    - Sync code only (no restart)"
        echo ""
        echo "Examples:"
        echo "  ./deploy.sh update          # Quick update for code/config changes"
        echo "  ./deploy.sh rebuild         # Rebuild image after dependency changes"
        echo "  ./deploy.sh deploy          # Full deployment for new servers"
        exit 1
        ;;
esac