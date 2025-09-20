#!/bin/bash

# =============================================================================
# Production Deployment Script for CEX Arbitrage System
# =============================================================================
# This script deploys the arbitrage system to production with security best practices

set -e

# Configuration
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml"
ENV_FILE=".env.prod"
BACKUP_DIR="/opt/arbitrage/backups"
DATA_DIR="/opt/arbitrage/data"

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
    echo "🚀 CEX Arbitrage Production Deployment"
    echo "======================================="
    echo "Timestamp: $(date)"
    echo "User: $(whoami)"
    echo "Host: $(hostname)"
    echo ""
}

check_prerequisites() {
    echo_info "Checking prerequisites..."
    
    # Check if running as root or with sudo
    if [[ $EUID -eq 0 ]]; then
        echo_warning "Running as root. Consider using a dedicated user."
    fi
    
    # Check Docker and Docker Compose
    if ! command -v docker &> /dev/null; then
        echo_error "Docker is not installed"
        exit 1
    fi
    
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
    
    # Check SSL certificates
    if [[ ! -f "nginx/ssl/fullchain.pem" ]] || [[ ! -f "nginx/ssl/privkey.pem" ]]; then
        echo_warning "SSL certificates not found in nginx/ssl/"
        echo_info "Place your SSL certificates before proceeding"
        read -p "Continue without SSL? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    echo_success "Prerequisites check passed"
}

setup_directories() {
    echo_info "Setting up production directories..."
    
    # Create data directories
    sudo mkdir -p "$DATA_DIR"/{postgres,pgadmin,grafana}
    sudo mkdir -p "$BACKUP_DIR"
    sudo mkdir -p logs
    
    # Set proper permissions
    sudo chown -R $USER:$USER "$DATA_DIR" "$BACKUP_DIR" logs
    sudo chmod 755 "$DATA_DIR" "$BACKUP_DIR"
    sudo chmod 700 "$DATA_DIR"/postgres
    
    echo_success "Directories created and configured"
}

deploy_services() {
    echo_info "Deploying production services..."
    
    # Load environment variables
    set -a
    source "$ENV_FILE"
    set +a
    
    # Stop any existing services
    echo_info "Stopping existing services..."
    docker-compose $COMPOSE_FILES down --remove-orphans 2>/dev/null || true
    
    # Pull latest images
    echo_info "Pulling latest Docker images..."
    docker-compose $COMPOSE_FILES pull
    
    # Deploy core services (database + data collector)
    echo_info "Starting core services..."
    COMPOSE_PROFILES=production docker-compose $COMPOSE_FILES up -d database data_collector
    
    # Wait for database to be ready
    echo_info "Waiting for database to be ready..."
    timeout 120 sh -c 'until docker exec arbitrage_db pg_isready -U arbitrage_user; do sleep 2; done'
    
    # Deploy management services (optional)
    read -p "Deploy management services (PgAdmin, Grafana, Nginx)? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo_info "Starting management services..."
        COMPOSE_PROFILES=production,admin,monitoring,management docker-compose $COMPOSE_FILES up -d
    fi
    
    echo_success "Services deployed successfully"
}

run_health_checks() {
    echo_info "Running health checks..."
    
    # Check service status
    echo_info "Service status:"
    docker-compose $COMPOSE_FILES ps
    
    # Check database connectivity
    echo_info "Testing database connection..."
    if docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "SELECT 1;" &>/dev/null; then
        echo_success "Database connection: OK"
    else
        echo_error "Database connection: FAILED"
        return 1
    fi
    
    # Check data collection
    echo_info "Checking data collector..."
    sleep 10
    if docker logs arbitrage_collector --tail 5 | grep -q "WebSocket.*connected\|Starting data collector"; then
        echo_success "Data collector: OK"
    else
        echo_warning "Data collector: Check logs for issues"
    fi
    
    echo_success "Health checks completed"
}

setup_monitoring() {
    echo_info "Setting up monitoring and alerting..."
    
    # Create backup script
    cat > backup-database.sh << 'EOF'
#!/bin/bash
# Automated database backup script

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="/opt/arbitrage/backups/arbitrage_backup_${DATE}.sql"

echo "Starting database backup: $DATE"
docker exec arbitrage_db pg_dump -U arbitrage_user -d arbitrage_data > "$BACKUP_FILE"

if [[ $? -eq 0 ]]; then
    echo "Backup completed: $BACKUP_FILE"
    gzip "$BACKUP_FILE"
    
    # Keep only last 7 days of backups
    find /opt/arbitrage/backups -name "arbitrage_backup_*.sql.gz" -mtime +7 -delete
else
    echo "Backup failed!"
    exit 1
fi
EOF
    
    chmod +x backup-database.sh
    
    # Setup cron job for backups (if not exists)
    if ! crontab -l 2>/dev/null | grep -q "backup-database.sh"; then
        echo_info "Setting up daily database backups..."
        (crontab -l 2>/dev/null; echo "0 2 * * * $(pwd)/backup-database.sh") | crontab -
        echo_success "Daily backup cron job created"
    fi
    
    echo_success "Monitoring setup completed"
}

print_deployment_info() {
    echo ""
    echo_success "🎉 Production deployment completed successfully!"
    echo "=============================================="
    echo ""
    echo "🔗 Service Access:"
    if docker ps --format "table {{.Names}}" | grep -q "arbitrage_nginx"; then
        echo "   📊 Grafana:  https://your-domain.com/grafana/"
        echo "   🔧 PgAdmin:  https://your-domain.com/pgadmin/"
        echo "   🔒 Auth:     admin / [nginx password from generation]"
    else
        echo "   📊 Grafana:  http://localhost:3000 (if exposed)"
        echo "   🔧 PgAdmin:  http://localhost:8080 (if exposed)"
    fi
    
    echo ""
    echo "📁 Important Files:"
    echo "   🔑 Passwords:    $ENV_FILE"
    echo "   📋 Logs:        logs/"
    echo "   💾 Backups:     $BACKUP_DIR"
    echo "   📊 Data:        $DATA_DIR"
    
    echo ""
    echo "🛠️  Management Commands:"
    echo "   Status:      docker-compose $COMPOSE_FILES ps"
    echo "   Logs:        docker-compose $COMPOSE_FILES logs -f"
    echo "   Stop:        docker-compose $COMPOSE_FILES down"
    echo "   Backup:      ./backup-database.sh"
    
    echo ""
    echo_warning "🔒 SECURITY REMINDERS:"
    echo "   - Keep $ENV_FILE secure and never commit it"
    echo "   - Monitor logs regularly for security events"
    echo "   - Update Docker images periodically"
    echo "   - Review firewall rules for exposed ports"
}

# Main deployment flow
main() {
    print_header
    check_prerequisites
    setup_directories
    deploy_services
    run_health_checks
    setup_monitoring
    print_deployment_info
}

# Handle script arguments
case "${1:-deploy}" in
    "deploy")
        main
        ;;
    "stop")
        echo_info "Stopping production services..."
        docker-compose $COMPOSE_FILES down
        echo_success "Services stopped"
        ;;
    "restart")
        echo_info "Restarting production services..."
        docker-compose $COMPOSE_FILES restart
        echo_success "Services restarted"
        ;;
    "logs")
        docker-compose $COMPOSE_FILES logs -f "${2:-}"
        ;;
    "status")
        docker-compose $COMPOSE_FILES ps
        ;;
    "backup")
        ./backup-database.sh
        ;;
    *)
        echo "Usage: $0 {deploy|stop|restart|logs|status|backup}"
        echo ""
        echo "Commands:"
        echo "  deploy   - Full production deployment"
        echo "  stop     - Stop all services"
        echo "  restart  - Restart all services"
        echo "  logs     - Show service logs"
        echo "  status   - Show service status"
        echo "  backup   - Run database backup"
        exit 1
        ;;
esac