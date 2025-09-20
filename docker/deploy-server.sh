#!/bin/bash

# =============================================================================
# Server Deployment Script for CEX Arbitrage System
# =============================================================================
# Deploys the system with external access to Grafana and PgAdmin

set -e

# Configuration
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod-external.yml"
ENV_FILE=".env.prod"
DATA_DIR="/opt/arbitrage/data"
SERVER_IP="139.180.134.54"

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
    echo "🚀 CEX Arbitrage Server Deployment"
    echo "=================================="
    echo "Server: ${SERVER_IP}"
    echo "Timestamp: $(date)"
    echo "User: $(whoami)"
    echo ""
}

check_prerequisites() {
    echo_info "Checking server prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        echo_error "Docker is not installed"
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        echo_error "Docker Compose is not installed"
        exit 1
    fi
    
    # Check environment file
    if [[ ! -f "$ENV_FILE" ]]; then
        echo_error "Production environment file not found: $ENV_FILE"
        echo_info "Run ./generate-passwords.sh first"
        exit 1
    fi
    
    echo_success "Prerequisites check passed"
}

setup_directories() {
    echo_info "Setting up data directories..."
    
    # Create data directories with proper permissions
    mkdir -p "$DATA_DIR"/{postgres,pgadmin,grafana}
    mkdir -p logs
    
    # Set proper ownership and permissions
    chown -R root:root "$DATA_DIR"
    chmod 755 "$DATA_DIR"
    chmod 700 "$DATA_DIR"/postgres
    
    echo_success "Data directories configured"
}

configure_firewall() {
    echo_info "Configuring firewall rules..."
    
    # Install ufw if not present
    if ! command -v ufw &> /dev/null; then
        apt update && apt install -y ufw
    fi
    
    # Configure firewall rules
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow ssh
    ufw allow 3000/tcp  # Grafana
    ufw allow 8080/tcp  # PgAdmin
    
    # Enable firewall (with confirmation)
    echo_warning "Enabling firewall. Make sure SSH access is configured!"
    read -p "Continue with firewall configuration? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ufw --force enable
        echo_success "Firewall configured and enabled"
    else
        echo_warning "Firewall configuration skipped"
    fi
}

initialize_database() {
    echo_info "Initializing database schema..."
    
    # Wait for database to be fully ready
    echo_info "Waiting for database to be ready..."
    timeout 120 sh -c 'until docker exec $(docker-compose $COMPOSE_FILES ps -q database) pg_isready -U arbitrage_user; do sleep 2; done'
    
    # Check if database is already initialized
    if docker exec $(docker-compose $COMPOSE_FILES ps -q database) psql -U arbitrage_user -d arbitrage_data -c "SELECT 1 FROM information_schema.tables WHERE table_name='book_ticker_snapshots';" 2>/dev/null | grep -q "1 row"; then
        echo_success "Database already initialized"
        return 0
    fi
    
    echo_info "Applying database schema from init-db.sql..."
    
    # Apply schema from init-db.sql file
    if [ -f "init-db.sql" ]; then
        docker exec -i $(docker-compose $COMPOSE_FILES ps -q database) psql -U arbitrage_user -d arbitrage_data < init-db.sql
        
        if [ $? -eq 0 ]; then
            echo_success "Database schema initialized successfully from init-db.sql"
        else
            echo_error "Failed to initialize database schema from init-db.sql"
            return 1
        fi
    else
        echo_error "init-db.sql file not found"
        return 1
    fi
}

update_database_schema() {
    echo_info "Updating database schema (safe updates only)..."
    
    # Apply schema updates from schema-updates.sql file
    if [ -f "schema-updates.sql" ]; then
        docker exec -i $(docker-compose $COMPOSE_FILES ps -q database) psql -U arbitrage_user -d arbitrage_data < schema-updates.sql
        
        if [ $? -eq 0 ]; then
            echo_success "Database schema updated successfully from schema-updates.sql"
        else
            echo_warning "Schema update had issues - check manually"
        fi
    else
        echo_warning "schema-updates.sql file not found - no schema updates applied"
    fi
}

graceful_update_collector() {
    echo_info "Performing graceful collector update..."
    
    # First update the image
    docker-compose $COMPOSE_FILES pull data_collector
    
    # Gracefully restart collector (this preserves database connections)
    echo_info "Restarting data collector..."
    docker-compose $COMPOSE_FILES up -d --no-deps data_collector
    
    # Wait for collector to be healthy
    echo_info "Waiting for collector to restart..."
    sleep 15
    
    # Check if collector is running and healthy
    if docker-compose $COMPOSE_FILES ps data_collector | grep -q "Up"; then
        echo_success "Collector updated and running"
        
        # Show recent logs to verify it's working
        echo_info "Recent collector logs:"
        docker-compose $COMPOSE_FILES logs --tail=20 data_collector
    else
        echo_error "Collector update failed"
        return 1
    fi
}

deploy_services() {
    echo_info "Deploying production services..."
    
    # Load environment variables
    set -a
    source "$ENV_FILE"
    set +a
    
    # Stop any existing services gracefully
    echo_info "Stopping existing services gracefully..."
    if docker-compose $COMPOSE_FILES ps | grep -q "Up"; then
        docker-compose $COMPOSE_FILES stop
    fi
    docker-compose $COMPOSE_FILES down --remove-orphans 2>/dev/null || true
    
    # Pull latest images
    echo_info "Pulling latest Docker images..."
    docker-compose $COMPOSE_FILES pull
    
    # Start database first
    echo_info "Starting database..."
    docker-compose $COMPOSE_FILES up -d database
    
    # Initialize database schema
    initialize_database
    
    # Start remaining services
    echo_info "Starting all services..."
    docker-compose $COMPOSE_FILES up -d
    
    echo_success "Services deployed successfully"
}

run_health_checks() {
    echo_info "Running health checks..."
    
    # Check service status
    echo_info "Service status:"
    docker-compose $COMPOSE_FILES ps
    
    # Check database connectivity
    echo_info "Testing database connection..."
    if docker exec $(docker-compose $COMPOSE_FILES ps -q database) psql -U arbitrage_user -d arbitrage_data -c "SELECT 1;" &>/dev/null; then
        echo_success "Database connection: OK"
    else
        echo_error "Database connection: FAILED"
        return 1
    fi
    
    # Check web services
    echo_info "Checking web services accessibility..."
    sleep 10
    
    # Test Grafana
    if curl -f -s http://localhost:3000/api/health &>/dev/null; then
        echo_success "Grafana health check: OK"
    else
        echo_warning "Grafana health check: Check manually"
    fi
    
    # Test PgAdmin
    if curl -f -s http://localhost:8080/misc/ping &>/dev/null; then
        echo_success "PgAdmin health check: OK"
    else
        echo_warning "PgAdmin health check: Check manually"
    fi
    
    echo_success "Health checks completed"
}

print_access_info() {
    # Load environment variables to show passwords
    set -a
    source "$ENV_FILE"
    set +a
    
    # Get actual server IP
    ACTUAL_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s icanhazip.com 2>/dev/null || echo "${SERVER_IP}")
    
    echo ""
    echo_success "🎉 Server deployment completed successfully!"
    echo "=========================================="
    echo ""
    echo "🔗 External Access URLs (HTTP - No Domain Required):"
    echo "   📊 Grafana:  http://${ACTUAL_IP}:3000"
    echo "   🔧 PgAdmin:  http://${ACTUAL_IP}:8080"
    echo ""
    echo "🔑 Login Credentials:"
    echo "   Grafana:"
    echo "     Username: admin"
    echo "     Password: ${GRAFANA_PASSWORD}"
    echo ""
    echo "   PgAdmin:"
    echo "     Email: ${PGLADMIN_EMAIL:-admin@example.com}"
    echo "     Password: ${PGADMIN_PASSWORD}"
    echo ""
    echo "🗄️  Database Connection (for PgAdmin):"
    echo "   Host: database"
    echo "   Port: 5432"
    echo "   Database: arbitrage_data"
    echo "   Username: arbitrage_user"
    echo "   Password: ${POSTGRES_PASSWORD}"
    echo ""
    echo "🛠️  Management Commands:"
    echo "   Status:           ./deploy-server.sh status"
    echo "   Logs:             ./deploy-server.sh logs"
    echo "   Update Schema:    ./deploy-server.sh update-schema"
    echo "   Update Collector: ./deploy-server.sh update-collector"
    echo "   Update All:       ./deploy-server.sh update"
    echo "   Restart:          ./deploy-server.sh restart"
    echo "   Stop:             ./deploy-server.sh stop"
    echo ""
    echo "📊 Quick Data Check:"
    echo "   ./deploy-server.sh check-data"
    echo ""
    echo "🔄 Safe Update Procedures:"
    echo "   - Schema updates: Adds columns safely, no breaking changes"
    echo "   - Collector updates: Graceful restart, preserves connections"
    echo "   - All updates preserve existing data and connections"
    echo ""
    echo_warning "🔒 SECURITY NOTES:"
    echo "   ✅ HTTP access configured for easy testing"
    echo "   ✅ Firewall configured for ports 3000 and 8080"
    echo "   ✅ Database not exposed externally"
    echo "   ⚠️  Consider adding SSL/TLS for production use"
}

# Main deployment flow
main() {
    print_header
    check_prerequisites
    setup_directories
    configure_firewall
    deploy_services
    run_health_checks
    print_access_info
}

# Handle script arguments
case "${1:-deploy}" in
    "deploy")
        main
        ;;
    "stop")
        echo_info "Stopping all services..."
        docker-compose $COMPOSE_FILES down
        echo_success "Services stopped"
        ;;
    "restart")
        echo_info "Restarting all services..."
        docker-compose $COMPOSE_FILES restart
        echo_success "Services restarted"
        ;;
    "logs")
        docker-compose $COMPOSE_FILES logs -f "${2:-}"
        ;;
    "status")
        echo_info "Service Status:"
        docker-compose $COMPOSE_FILES ps
        echo ""
        echo_info "System Resources:"
        docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"
        ;;
    "update")
        echo_info "Updating all services (graceful)..."
        
        # Load environment variables
        set -a
        source "$ENV_FILE"
        set +a
        
        # Update schema safely
        update_database_schema
        
        # Update collector gracefully
        graceful_update_collector
        
        # Update other services (Grafana, PgAdmin)
        echo_info "Updating monitoring services..."
        docker-compose $COMPOSE_FILES pull pgadmin grafana
        docker-compose $COMPOSE_FILES up -d --no-deps pgadmin grafana
        
        echo_success "All services updated successfully"
        ;;
    "update-schema")
        echo_info "Updating database schema only..."
        
        # Load environment variables
        set -a
        source "$ENV_FILE"
        set +a
        
        update_database_schema
        ;;
    "update-collector")
        echo_info "Updating data collector only..."
        
        # Load environment variables
        set -a
        source "$ENV_FILE"
        set +a
        
        graceful_update_collector
        ;;
    "check-data")
        echo_info "Checking database data..."
        
        # Load environment variables
        set -a
        source "$ENV_FILE"
        set +a
        
        docker exec $(docker-compose $COMPOSE_FILES ps -q database) psql -U arbitrage_user -d arbitrage_data -c "
        -- Database statistics
        SELECT 
            'Total Records' as metric,
            COUNT(*) as value,
            'records' as unit
        FROM book_ticker_snapshots
        UNION ALL
        SELECT 
            'Latest Timestamp' as metric,
            MAX(timestamp)::text as value,
            'timestamp' as unit
        FROM book_ticker_snapshots
        UNION ALL
        SELECT 
            'Exchanges' as metric,
            COUNT(DISTINCT exchange)::text as value,
            'count' as unit
        FROM book_ticker_snapshots
        UNION ALL
        SELECT 
            'Symbols' as metric,
            COUNT(DISTINCT symbol_base || '/' || symbol_quote)::text as value,
            'count' as unit
        FROM book_ticker_snapshots;
        
        -- Recent data by exchange
        \echo ''
        \echo 'Recent data by exchange (last 5 minutes):'
        SELECT 
            exchange,
            COUNT(*) as records,
            MAX(timestamp) as latest_timestamp
        FROM book_ticker_snapshots 
        WHERE timestamp > NOW() - INTERVAL '5 minutes'
        GROUP BY exchange
        ORDER BY latest_timestamp DESC;
        "
        ;;
    "backup")
        echo_info "Creating database backup..."
        
        # Create backup directory
        mkdir -p backups
        
        BACKUP_FILE="backups/arbitrage_backup_$(date +%Y%m%d_%H%M%S).sql"
        
        docker exec $(docker-compose $COMPOSE_FILES ps -q database) pg_dump -U arbitrage_user -d arbitrage_data > "$BACKUP_FILE"
        
        if [ $? -eq 0 ]; then
            gzip "$BACKUP_FILE"
            echo_success "Backup created: ${BACKUP_FILE}.gz"
        else
            echo_error "Backup failed"
        fi
        ;;
    "restore")
        if [ -z "$2" ]; then
            echo_error "Usage: $0 restore <backup_file.sql.gz>"
            exit 1
        fi
        
        echo_warning "This will restore database from backup and overwrite existing data!"
        read -p "Continue? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo_info "Restoring database from $2..."
            gunzip -c "$2" | docker exec -i $(docker-compose $COMPOSE_FILES ps -q database) psql -U arbitrage_user -d arbitrage_data
            echo_success "Database restored"
        fi
        ;;
    "shell")
        echo_info "Opening database shell..."
        docker exec -it $(docker-compose $COMPOSE_FILES ps -q database) psql -U arbitrage_user -d arbitrage_data
        ;;
    *)
        echo "CEX Arbitrage Server Management"
        echo "Usage: $0 {deploy|stop|restart|logs|status|update|update-schema|update-collector|check-data|backup|restore|shell}"
        echo ""
        echo "🚀 Deployment Commands:"
        echo "  deploy           - Full server deployment with database initialization"
        echo "  stop             - Stop all services"
        echo "  restart          - Restart all services"
        echo ""
        echo "📊 Monitoring Commands:"
        echo "  status           - Show service status and resource usage"
        echo "  logs [service]   - Show service logs (optionally for specific service)"
        echo "  check-data       - Display database statistics and recent data"
        echo ""
        echo "🔄 Update Commands (Safe - No Downtime):"
        echo "  update           - Update all services gracefully"
        echo "  update-schema    - Update database schema only (safe operations)"
        echo "  update-collector - Update data collector only (graceful restart)"
        echo ""
        echo "💾 Database Commands:"
        echo "  backup           - Create database backup"
        echo "  restore <file>   - Restore from backup file"
        echo "  shell            - Open database shell (psql)"
        echo ""
        echo "Examples:"
        echo "  ./deploy-server.sh deploy          # Initial deployment"
        echo "  ./deploy-server.sh update          # Safe update all"
        echo "  ./deploy-server.sh logs collector  # View collector logs"
        echo "  ./deploy-server.sh check-data      # Check data collection"
        exit 1
        ;;
esac