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

# Deploy services
echo "Stopping existing services..."
docker-compose -f docker-compose.yml -f docker-compose.prod.yml down --remove-orphans || true

echo "Pulling latest images..."
docker-compose -f docker-compose.yml -f docker-compose.prod.yml pull

echo "Starting database..."
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d database

# Wait for DB and initialize
echo "Waiting for database to be ready..."
sleep 15

# Get database container name
DB_CONTAINER=$(docker-compose -f docker-compose.yml -f docker-compose.prod.yml ps -q database)
if [ -z "$DB_CONTAINER" ]; then
    echo "❌ Database container not found"
    exit 1
fi

# Wait for database to be ready
timeout 120 sh -c "until docker exec $DB_CONTAINER pg_isready -U arbitrage_user; do sleep 2; done"

# Initialize database schema
echo "Initializing database schema..."
docker exec -i "$DB_CONTAINER" psql -U arbitrage_user -d arbitrage_data < init-db.sql

# Start all services
echo "Starting all services..."
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

echo "✅ Deployment complete!"
echo "📊 Grafana: http://31.192.233.13:3000"
echo "🔧 PgAdmin: http://31.192.233.13:8080"
echo "🔑 Check passwords in .env.prod"
EOF

    echo_success "Server deployed"
}

update_only() {
    echo_info "Updating code only..."
    sync_code
    
    ssh -i "$SSH_KEY" "root@$SERVER" << 'EOF'
cd /opt/arbitrage/docker

# Verify Docker Compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose not found"
    exit 1
fi

echo "Updating data collector..."
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps data_collector
echo "✅ Collector updated"
EOF

    echo_success "Update complete"
}

case "${1:-deploy}" in
    "deploy")
        sync_code
        deploy_server
        ;;
    "update")
        update_only
        ;;
    "sync")
        sync_code
        ;;
    *)
        echo "Usage: $0 {deploy|update|sync}"
        echo ""
        echo "Commands:"
        echo "  deploy  - Full deployment (sync + setup + deploy)"
        echo "  update  - Update code and restart collector"
        echo "  sync    - Sync code only"
        exit 1
        ;;
esac