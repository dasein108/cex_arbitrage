#!/bin/bash
# Arbitrage Data Collector - Server Deployment Script
# 
# This script sets up and runs the data collection system on a server
# Usage: ./deploy.sh [start|stop|restart|status|logs|update]

set -euo pipefail

# Configuration
PROJECT_NAME="arbitrage-collector"
DOCKER_COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env"
LOG_FILE="deployment.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] ✓${NC} $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] ⚠${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ✗${NC} $1" | tee -a "$LOG_FILE"
}

# Check if Docker and Docker Compose are installed
check_dependencies() {
    log "Checking dependencies..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    log_success "Dependencies check passed"
}

# Setup environment file
setup_environment() {
    log "Setting up environment configuration..."
    
    if [ ! -f "$ENV_FILE" ]; then
        log "Creating environment file from template..."
        cat > "$ENV_FILE" << EOF
# Database Configuration
DB_PASSWORD=arbitrage_secure_password_$(date +%s)

# PgAdmin Configuration (optional)
PGADMIN_PASSWORD=admin_password_$(date +%s)

# Grafana Configuration (optional)
GRAFANA_PASSWORD=grafana_password_$(date +%s)

# Exchange API Credentials (for private data collection)
# Leave empty for public data only
MEXC_API_KEY=
MEXC_SECRET_KEY=
GATEIO_API_KEY=
GATEIO_SECRET_KEY=

# Application Settings
LOG_LEVEL=INFO
ENVIRONMENT=production
EOF
        log_success "Environment file created: $ENV_FILE"
        log_warning "Please edit $ENV_FILE to configure your settings"
    else
        log_success "Environment file already exists"
    fi
}

# Create required directories
setup_directories() {
    log "Creating required directories..."
    
    mkdir -p logs
    mkdir -p grafana/provisioning/datasources
    mkdir -p grafana/provisioning/dashboards
    
    # Create Grafana datasource configuration
    cat > grafana/provisioning/datasources/postgres.yml << EOF
apiVersion: 1

datasources:
  - name: PostgreSQL
    type: postgres
    url: database:5432
    database: arbitrage_data
    user: readonly_user
    secureJsonData:
      password: readonly_password_2024
    jsonData:
      sslmode: disable
      maxOpenConns: 0
      maxIdleConns: 2
      connMaxLifetime: 14400
EOF
    
    log_success "Directories and configuration created"
}

# Start the services
start_services() {
    local mode=${1:-production}
    
    if [ "$mode" = "dev" ] || [ "$mode" = "development" ]; then
        log "Starting arbitrage data collector in DEVELOPMENT mode..."
        log_warning "Source code is mounted - changes will apply immediately"
        
        # Use both compose files for development
        docker-compose -f "$DOCKER_COMPOSE_FILE" -f docker-compose.dev.yml up -d
    else
        log "Starting arbitrage data collector in PRODUCTION mode..."
        
        # Start core services (database + collector)
        docker-compose -f "$DOCKER_COMPOSE_FILE" up -d database data_collector
    fi
    
    log "Waiting for database to be ready..."
    sleep 10
    
    # Check if services are running
    if docker-compose -f "$DOCKER_COMPOSE_FILE" ps | grep -q "Up"; then
        log_success "Services started successfully"
        
        # Show status
        show_status
        
        log "🚀 Data collection is now running!"
        log "📊 Database: localhost:5432 (user: arbitrage_user)"
        log "📝 Logs: docker-compose -f $DOCKER_COMPOSE_FILE logs -f data_collector"
        
        # Optional services prompt
        echo
        read -p "Do you want to start PgAdmin for database management? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker-compose -f "$DOCKER_COMPOSE_FILE" --profile admin up -d pgadmin
            log_success "PgAdmin started at http://localhost:8080"
            log "Login: admin@arbitrage.local / Password: check $ENV_FILE"
        fi
        
        echo
        read -p "Do you want to start Grafana for monitoring? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker-compose -f "$DOCKER_COMPOSE_FILE" --profile monitoring up -d grafana
            log_success "Grafana started at http://localhost:3000"
            log "Login: admin / Password: check $ENV_FILE"
        fi
        
    else
        log_error "Failed to start services"
        docker-compose -f "$DOCKER_COMPOSE_FILE" logs
        exit 1
    fi
}

# Stop the services
stop_services() {
    log "Stopping arbitrage data collector services..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" down
    log_success "Services stopped"
}

# Restart the services
restart_services() {
    log "Restarting arbitrage data collector services..."
    stop_services
    start_services
}

# Show status
show_status() {
    log "Service Status:"
    docker-compose -f "$DOCKER_COMPOSE_FILE" ps
    
    echo
    log "Container Health:"
    docker-compose -f "$DOCKER_COMPOSE_FILE" ps --format "table {{.Name}}\t{{.State}}\t{{.Status}}"
    
    # Show recent logs from data collector
    echo
    log "Recent data collector logs (last 10 lines):"
    docker-compose -f "$DOCKER_COMPOSE_FILE" logs --tail=10 data_collector 2>/dev/null || log_warning "Data collector not running"
}

# Show logs
show_logs() {
    local service=${2:-data_collector}
    log "Showing logs for $service (Press Ctrl+C to exit)..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" logs -f "$service"
}

# Update services
update_services() {
    log "Updating arbitrage data collector..."
    
    # Pull latest images
    docker-compose -f "$DOCKER_COMPOSE_FILE" pull
    
    # Rebuild local images
    docker-compose -f "$DOCKER_COMPOSE_FILE" build --no-cache
    
    # Restart services
    restart_services
    
    log_success "Update completed"
}

# Backup database
backup_database() {
    log "Creating database backup..."
    
    local backup_file="backup_$(date +%Y%m%d_%H%M%S).sql"
    
    docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T database pg_dump -U arbitrage_user arbitrage_data > "$backup_file"
    
    log_success "Database backup created: $backup_file"
}

# Clean up old data
cleanup_old_data() {
    log "Cleaning up old data..."
    
    # This would typically run database cleanup commands
    # For now, just log the action
    log_warning "Database cleanup should be implemented based on your retention policies"
    log "Consider running VACUUM and ANALYZE on your PostgreSQL database"
}

# Health check
health_check() {
    log "Performing health check..."
    
    # Check if containers are running
    if docker-compose -f "$DOCKER_COMPOSE_FILE" ps | grep -q "Up"; then
        log_success "Containers are running"
    else
        log_error "Some containers are not running"
        return 1
    fi
    
    # Check database connectivity
    if docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T database pg_isready -U arbitrage_user > /dev/null 2>&1; then
        log_success "Database is accessible"
    else
        log_error "Database is not accessible"
        return 1
    fi
    
    # Check data collector health
    if docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T data_collector python -c "import sys; sys.exit(0)" > /dev/null 2>&1; then
        log_success "Data collector is responsive"
    else
        log_error "Data collector is not responsive"
        return 1
    fi
    
    log_success "Health check passed"
}

# Main function
main() {
    local action=${1:-start}
    local mode=${2:-production}
    
    echo "🔄 Arbitrage Data Collector - Deployment Manager"
    echo "================================================"
    
    case "$action" in
        "start")
            check_dependencies
            setup_environment
            setup_directories
            start_services "$mode"
            ;;
        "dev")
            check_dependencies
            setup_environment
            setup_directories
            start_services "development"
            ;;
        "stop")
            stop_services
            ;;
        "restart")
            restart_services
            ;;
        "status")
            show_status
            ;;
        "logs")
            show_logs "$@"
            ;;
        "update")
            update_services
            ;;
        "backup")
            backup_database
            ;;
        "cleanup")
            cleanup_old_data
            ;;
        "health")
            health_check
            ;;
        "install")
            log "Installing Docker and Docker Compose..."
            # This would include installation scripts for different OS
            log_warning "Please install Docker manually for your operating system"
            ;;
        *)
            echo "Usage: $0 {start|dev|stop|restart|status|logs|update|backup|cleanup|health|install} [mode]"
            echo
            echo "Commands:"
            echo "  start [mode] - Start in production mode (or specify 'dev')"
            echo "  dev          - Start in development mode with hot-reload"
            echo "  stop         - Stop all services"
            echo "  restart      - Restart all services"
            echo "  status       - Show service status"
            echo "  logs         - Show service logs (default: data_collector)"
            echo "  update       - Update services to latest version"
            echo "  backup       - Create database backup"
            echo "  cleanup      - Clean up old data"
            echo "  health       - Perform health check"
            echo "  install      - Install Docker dependencies"
            echo
            echo "Examples:"
            echo "  $0 start          # Production mode"
            echo "  $0 start dev      # Development mode with mounted source"
            echo "  $0 dev            # Shortcut for development mode"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"