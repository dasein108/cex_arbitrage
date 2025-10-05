# =============================================================================
# CEX Arbitrage - Deployment Makefile
# =============================================================================
# Simple commands for local monitoring, deployment, and maintenance

.PHONY: help local-monitoring dev deploy update rebuild sync status clean logs

# Default target
help:
	@echo "CEX Arbitrage Deployment Commands"
	@echo "================================="
	@echo ""
	@echo "🏠 Local Development & Monitoring:"
	@echo "  make local-monitoring    Start local monitoring (Grafana + PgAdmin → remote DB)"
	@echo "  make dev                 Start full development environment"
	@echo "  make stop-local          Stop local services"
	@echo ""
	@echo "🚀 Production Deployment:"
	@echo "  make deploy              Full production deployment"
	@echo "  make update              Quick update (config/code changes)"
	@echo "  make rebuild             Rebuild Docker images"
	@echo "  make sync                Sync code only (no restart)"
	@echo ""
	@echo "🔧 Container Management:"
	@echo "  make rebuild-local       Rebuild and restart locally"
	@echo "  make rebuild-server      Rebuild and restart on server"
	@echo "  make logs                Show data collector logs"
	@echo "  make status              Show container status"
	@echo ""
	@echo "🧹 Maintenance:"
	@echo "  make clean               Clean Docker resources"
	@echo "  make clean-server        Clean server resources"
	@echo "  make analyze-db          Analyze database usage"
	@echo ""
	@echo "📊 Monitoring Access:"
	@echo "  Local Grafana:  http://localhost:3000 (admin/local_grafana_2024)"
	@echo "  Local PgAdmin:  http://localhost:8080 (admin@localhost.com/local_pgadmin_2024)"
	@echo "  Remote DB:      31.192.233.13:5432"

# =============================================================================
# Local Development & Monitoring
# =============================================================================

local-monitoring:
	@echo "🏠 Starting local monitoring stack..."
	@echo "   → Grafana: http://localhost:3000"
	@echo "   → PgAdmin: http://localhost:8080"
	@echo "   → Connects to remote DB: 31.192.233.13:5432"
	docker-compose -f docker-compose.local-monitoring.yml up -d
	@echo "✅ Local monitoring started"
	@echo ""
	@echo "📊 Access URLs:"
	@echo "   Grafana:  http://localhost:3000 (admin/local_grafana_2024)"
	@echo "   PgAdmin:  http://localhost:8080 (admin@localhost.com/local_pgadmin_2024)"

dev:
	@echo "⚡ Starting full development environment..."
	./start-dev.sh

stop-local:
	@echo "🛑 Stopping local services..."
	docker-compose -f docker-compose.local-monitoring.yml down || true
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml down || true
	docker stop arbitrage_grafana arbitrage_pgadmin 2>/dev/null || true
	docker rm arbitrage_grafana arbitrage_pgadmin 2>/dev/null || true
	@echo "✅ Local services stopped"

# =============================================================================
# Production Deployment
# =============================================================================

deploy:
	@echo "🚀 Starting full production deployment..."
	./deploy.sh deploy

update:
	@echo "⚡ Quick update (config/code changes)..."
	./deploy.sh update

rebuild:
	@echo "🔄 Rebuilding Docker images..."
	./deploy.sh rebuild

sync:
	@echo "📦 Syncing code only..."
	./deploy.sh sync

# =============================================================================
# Container Management
# =============================================================================

rebuild-local:
	@echo "🔄 Rebuilding and restarting locally..."
	./rebuild.sh restart-local

rebuild-server:
	@echo "🔄 Rebuilding and restarting on server..."
	./rebuild.sh restart-server

logs:
	@echo "📋 Showing data collector logs..."
	./rebuild.sh logs

status:
	@echo "📊 Container status and health..."
	./rebuild.sh status

# =============================================================================
# Maintenance & Cleanup
# =============================================================================

clean:
	@echo "🧹 Cleaning local Docker resources..."
	./rebuild.sh clean

clean-server:
	@echo "🧹 Cleaning server resources..."
	./cleanup-server.sh all

clean-docker-server:
	@echo "🧹 Cleaning Docker on server..."
	./cleanup-server.sh docker

analyze-db:
	@echo "📊 Analyzing database space usage..."
	./cleanup-server.sh database

analyze-server:
	@echo "🔍 Deep server analysis..."
	./cleanup-server.sh analyze

# =============================================================================
# Development Helpers
# =============================================================================

config-check:
	@echo "🔍 Validating Docker Compose configurations..."
	@echo "Checking base configuration..."
	docker-compose -f docker-compose.yml config --quiet && echo "✅ Base config valid"
	@echo "Checking development configuration..."
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml config --quiet && echo "✅ Dev config valid"
	@echo "Checking production configuration..."
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet && echo "✅ Prod config valid"
	@echo "Checking local monitoring configuration..."
	docker-compose -f docker-compose.local-monitoring.yml config --quiet && echo "✅ Local monitoring config valid"

ps:
	@echo "📊 Docker container status..."
	docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" --filter "name=arbitrage" || true
	@echo ""
	docker-compose -f docker-compose.local-monitoring.yml ps || true

# =============================================================================
# Quick Access Commands
# =============================================================================

grafana:
	@echo "🌐 Opening Grafana in browser..."
	@echo "URL: http://localhost:3000"
	@echo "Login: admin / local_grafana_2024"
	open http://localhost:3000 2>/dev/null || xdg-open http://localhost:3000 2>/dev/null || echo "Open http://localhost:3000 manually"

pgadmin:
	@echo "🌐 Opening PgAdmin in browser..."
	@echo "URL: http://localhost:8080"
	@echo "Login: admin@localhost.com / local_pgadmin_2024"
	open http://localhost:8080 2>/dev/null || xdg-open http://localhost:8080 2>/dev/null || echo "Open http://localhost:8080 manually"

# =============================================================================
# Production Monitoring Commands
# =============================================================================

prod-monitoring:
	@echo "📊 Starting production monitoring services on server..."
	ssh -i ~/.ssh/deploy_ci root@31.192.233.13 'cd /opt/arbitrage/docker && docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml --profile monitoring up -d grafana'
	@echo "✅ Production Grafana started"

prod-admin:
	@echo "🔧 Starting production admin services on server..."
	ssh -i ~/.ssh/deploy_ci root@31.192.233.13 'cd /opt/arbitrage/docker && docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml --profile admin up -d pgadmin'
	@echo "✅ Production PgAdmin started"

prod-status:
	@echo "📊 Production server status..."
	ssh -i ~/.ssh/deploy_ci root@31.192.233.13 'cd /opt/arbitrage/docker && docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml ps'

prod-logs:
	@echo "📋 Production data collector logs..."
	ssh -i ~/.ssh/deploy_ci root@31.192.233.13 'cd /opt/arbitrage/docker && docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml logs --tail=50 data_collector'

# =============================================================================
# Environment Setup
# =============================================================================

setup-env:
	@echo "🔧 Setting up environment files..."
	@if [ ! -f ".env.local" ]; then \
		echo "Creating .env.local..."; \
		echo "GRAFANA_PASSWORD=local_grafana_2024" > .env.local; \
		echo "PGADMIN_EMAIL=admin@localhost.com" >> .env.local; \
		echo "PGADMIN_PASSWORD=local_pgadmin_2024" >> .env.local; \
		echo "DB_PASSWORD=your_remote_db_password_here" >> .env.local; \
		echo "✅ Created .env.local"; \
		echo "⚠️  Edit .env.local with your remote database password"; \
	else \
		echo "✅ .env.local already exists"; \
	fi

# =============================================================================
# Troubleshooting
# =============================================================================

debug:
	@echo "🔍 Debug information..."
	@echo ""
	@echo "=== Docker Status ==="
	docker --version || echo "❌ Docker not installed"
	docker-compose --version || echo "❌ Docker Compose not installed"
	@echo ""
	@echo "=== Running Containers ==="
	docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
	@echo ""
	@echo "=== Network Status ==="
	docker network ls | grep arbitrage || echo "No arbitrage networks found"
	@echo ""
	@echo "=== Volume Status ==="
	docker volume ls | grep -E "(grafana|pgadmin|postgres)" || echo "No data volumes found"

reset:
	@echo "⚠️  DANGER: This will reset all local containers and data"
	@echo "Are you sure? Press Ctrl+C to cancel, Enter to continue..."
	@read dummy
	@echo "🗑️  Stopping and removing all arbitrage containers..."
	docker-compose -f docker-compose.local-monitoring.yml down -v || true
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml down -v || true
	docker stop arbitrage_grafana arbitrage_pgadmin 2>/dev/null || true
	docker rm arbitrage_grafana arbitrage_pgadmin 2>/dev/null || true
	@echo "🧹 Cleaning up volumes..."
	docker volume prune -f
	@echo "✅ Reset complete - all local data removed"

# =============================================================================
# Documentation
# =============================================================================

docs:
	@echo "📚 Opening deployment documentation..."
	@if [ -f "DEPLOYMENT_GUIDE.md" ]; then \
		echo "=== DEPLOYMENT_GUIDE.md ==="; \
		head -20 DEPLOYMENT_GUIDE.md; \
		echo "..."; \
		echo "📖 Full documentation: docker/DEPLOYMENT_GUIDE.md"; \
	else \
		echo "❌ DEPLOYMENT_GUIDE.md not found"; \
	fi