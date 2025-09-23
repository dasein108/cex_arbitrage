#!/bin/bash

# =============================================================================
# Docker Image Rebuild Script
# =============================================================================
# Manual commands to rebuild Docker images when needed

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

# Change to docker directory
cd "$(dirname "$0")"

case "${1:-help}" in
    "local")
        echo_info "Rebuilding data_collector image locally..."
        docker-compose -f docker-compose.yml build --no-cache data_collector
        echo_success "Local image rebuilt"
        ;;
    "server")
        echo_info "Rebuilding data_collector image on server..."
        docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml build --no-cache data_collector
        echo_success "Server image rebuilt"
        ;;
    "restart-local")
        echo_info "Rebuilding and restarting locally..."
        docker-compose down data_collector
        docker-compose build --no-cache data_collector  
        docker-compose up -d data_collector
        echo_success "Local container rebuilt and restarted"
        ;;
    "restart-server")
        echo_info "Rebuilding and restarting on server..."
        docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml down data_collector
        docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml build --no-cache data_collector
        docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d data_collector
        echo_success "Server container rebuilt and restarted"
        ;;
    "clean")
        echo_warning "Cleaning up Docker images and containers..."
        
        # Stop containers
        docker-compose down || true
        
        # Remove old images
        echo_info "Removing old arbitrage images..."
        docker images | grep arbitrage | awk '{print $3}' | xargs -r docker rmi -f || true
        
        # Clean up dangling images
        echo_info "Cleaning up dangling images..."
        docker image prune -f
        
        # Clean up build cache
        echo_info "Cleaning up build cache..."
        docker builder prune -f
        
        echo_success "Docker cleanup complete"
        ;;
    "logs")
        echo_info "Showing data_collector logs..."
        docker-compose logs -f data_collector
        ;;
    "status")
        echo_info "Docker container status:"
        docker-compose ps
        echo ""
        echo_info "Data collector logs (last 20 lines):"
        docker-compose logs --tail=20 data_collector
        ;;
    "help"|*)
        echo "Docker Image Rebuild Script"
        echo ""
        echo "Usage: $0 {command}"
        echo ""
        echo "Commands:"
        echo "  local           - Rebuild data_collector image locally"
        echo "  server          - Rebuild data_collector image on server"
        echo "  restart-local   - Rebuild and restart container locally"
        echo "  restart-server  - Rebuild and restart container on server"
        echo "  clean           - Clean up old images and build cache"
        echo "  logs            - Show data_collector logs"
        echo "  status          - Show container status and recent logs"
        echo "  help            - Show this help message"
        echo ""
        echo "Examples:"
        echo "  # Quick rebuild after code changes"
        echo "  ./rebuild.sh restart-server"
        echo ""
        echo "  # Clean rebuild after dependency changes"
        echo "  ./rebuild.sh clean"
        echo "  ./rebuild.sh restart-server"
        echo ""
        echo "  # Debug deployment issues"
        echo "  ./rebuild.sh status"
        echo "  ./rebuild.sh logs"
        ;;
esac