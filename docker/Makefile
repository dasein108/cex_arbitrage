# =============================================================================
# CEX Arbitrage Infrastructure - Comprehensive Deployment & Management
# =============================================================================
# High-frequency trading arbitrage system deployment and monitoring tools
# Supports local development, production deployment, and automated maintenance

.PHONY: help setup-env clean install deploy monitor maintain debug
.DEFAULT_GOAL := help

# =============================================================================
# Configuration
# =============================================================================

# Server Configuration
SERVER := 31.192.233.13
SSH_KEY := ~/.ssh/deploy_ci
REMOTE_PATH := /opt/arbitrage
LOCAL_PATH := $(shell pwd)/..

# Docker Configuration
COMPOSE_LOCAL := docker-compose.yml -f docker-compose.dev.yml
COMPOSE_PROD := docker-compose.yml -f docker-compose.prod.yml
COMPOSE_MONITOR := docker-compose.local-monitoring.yml

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
BLUE := \033[0;34m
YELLOW := \033[1;33m
PURPLE := \033[0;35m
CYAN := \033[0;36m
NC := \033[0m

# =============================================================================
# Help & Documentation
# =============================================================================

help: ## Show comprehensive help for all available commands
	@echo ""
	@echo "$(CYAN)╔════════════════════════════════════════════════════════════╗$(NC)"
	@echo "$(CYAN)║          CEX Arbitrage Infrastructure Management           ║$(NC)"
	@echo "$(CYAN)║         High-Frequency Trading Deployment Tools           ║$(NC)"
	@echo "$(CYAN)╚════════════════════════════════════════════════════════════╝$(NC)"
	@echo ""
	@echo "$(BLUE)🚀 Quick Start:$(NC)"
	@echo "  $(YELLOW)make setup-env$(NC)        Setup environment files"
	@echo "  $(YELLOW)make dev$(NC)              Start local development environment"
	@echo "  $(YELLOW)make deploy$(NC)           Deploy to production server"
	@echo "  $(YELLOW)make monitor$(NC)          Start local monitoring stack"
	@echo ""
	@echo "$(BLUE)📦 Environment Management:$(NC)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / && /Environment/ {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(BLUE)🏗️  Development & Testing:$(NC)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / && /Development/ {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(BLUE)🚀 Production Deployment:$(NC)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / && /Production/ {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(BLUE)📊 Monitoring & Observability:$(NC)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / && /Monitoring/ {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(BLUE)🔧 Maintenance & Operations:$(NC)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / && /Maintenance/ {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(BLUE)🐛 Debugging & Troubleshooting:$(NC)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / && /Debug/ {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(GREEN)📊 Access URLs:$(NC)"
	@echo "  Local Grafana:   http://localhost:3000 (admin/local_grafana_2024)"
	@echo "  Local PgAdmin:   http://localhost:8080 (admin@localhost.com/local_pgadmin_2024)"
	@echo "  Production DB:   $(SERVER):5432"
	@echo ""
	@echo "$(PURPLE)📚 Documentation:$(NC)"
	@echo "  make docs                Show detailed documentation"
	@echo "  make debug               Show system diagnostic information"
	@echo "  make status              Show current system status"
	@echo ""

# =============================================================================
# Environment Setup & Configuration
# =============================================================================

setup-env: ## Environment: Setup all environment files and configurations
	@echo "$(BLUE)🔧 Setting up environment configuration...$(NC)"
	@if [ ! -f ".env.local" ]; then \
		echo "Creating .env.local for local development..."; \
		echo "GRAFANA_PASSWORD=local_grafana_2024" > .env.local; \
		echo "PGADMIN_EMAIL=admin@localhost.com" >> .env.local; \
		echo "PGADMIN_PASSWORD=local_pgadmin_2024" >> .env.local; \
		echo "DB_PASSWORD=dev_password_2024" >> .env.local; \
		echo "$(GREEN)✅ Created .env.local$(NC)"; \
	else \
		echo "$(YELLOW)⚠️  .env.local already exists$(NC)"; \
	fi
	@if [ ! -f ".env.prod" ]; then \
		echo "Creating .env.prod template..."; \
		echo "# Production Environment Configuration" > .env.prod; \
		echo "GRAFANA_PASSWORD=CHANGE_IN_PRODUCTION" >> .env.prod; \
		echo "PGADMIN_EMAIL=admin@$(SERVER)" >> .env.prod; \
		echo "PGADMIN_PASSWORD=CHANGE_IN_PRODUCTION" >> .env.prod; \
		echo "DB_PASSWORD=CHANGE_IN_PRODUCTION" >> .env.prod; \
		echo "SLACK_WEBHOOK_URL=https://hooks.slack.com/your/webhook/url" >> .env.prod; \
		echo "$(GREEN)✅ Created .env.prod template$(NC)"; \
		echo "$(YELLOW)⚠️  Edit .env.prod with production credentials$(NC)"; \
	else \
		echo "$(YELLOW)⚠️  .env.prod already exists$(NC)"; \
	fi
	@if [ ! -f ".rsync-exclude" ]; then \
		echo "Creating .rsync-exclude..."; \
		echo ".git/" > .rsync-exclude; \
		echo ".env.*" >> .rsync-exclude; \
		echo "logs/" >> .rsync-exclude; \
		echo "*.log" >> .rsync-exclude; \
		echo "__pycache__/" >> .rsync-exclude; \
		echo "*.pyc" >> .rsync-exclude; \
		echo ".DS_Store" >> .rsync-exclude; \
		echo "node_modules/" >> .rsync-exclude; \
		echo "$(GREEN)✅ Created .rsync-exclude$(NC)"; \
	fi
	@echo "$(GREEN)🎉 Environment setup complete!$(NC)"

validate-config: ## Environment: Validate all Docker Compose configurations
	@echo "$(BLUE)🔍 Validating Docker Compose configurations...$(NC)"
	@echo "Checking base configuration..."
	@docker-compose -f docker-compose.yml config --quiet && echo "$(GREEN)✅ Base config valid$(NC)" || echo "$(RED)❌ Base config invalid$(NC)"
	@echo "Checking development configuration..."
	@docker-compose -f $(COMPOSE_LOCAL) config --quiet && echo "$(GREEN)✅ Dev config valid$(NC)" || echo "$(RED)❌ Dev config invalid$(NC)"
	@echo "Checking production configuration..."
	@docker-compose -f $(COMPOSE_PROD) config --quiet && echo "$(GREEN)✅ Prod config valid$(NC)" || echo "$(RED)❌ Prod config invalid$(NC)"
	@echo "Checking local monitoring configuration..."
	@docker-compose -f $(COMPOSE_MONITOR) config --quiet && echo "$(GREEN)✅ Local monitoring config valid$(NC)" || echo "$(RED)❌ Local monitoring config invalid$(NC)"

install: setup-env validate-config ## Environment: Complete installation and setup
	@echo "$(BLUE)📦 Running complete installation...$(NC)"
	@echo "$(GREEN)✅ Installation complete - ready for development or deployment$(NC)"

# =============================================================================
# Development Environment
# =============================================================================

dev: ## Development: Start complete local development environment
	@echo "$(BLUE)🚀 Starting CEX Arbitrage Development Environment$(NC)"
	@echo "$(BLUE)===================================================$(NC)"
	
	@echo "$(BLUE)📋 Stopping existing containers...$(NC)"
	@docker-compose -f $(COMPOSE_LOCAL) down 2>/dev/null || true
	@docker stop arbitrage_grafana arbitrage_pgadmin 2>/dev/null || true
	@docker rm arbitrage_grafana arbitrage_pgadmin 2>/dev/null || true
	
	@echo "$(BLUE)🗄️  Starting core services (database + data collector)...$(NC)"
	@docker-compose -f $(COMPOSE_LOCAL) up -d database data_collector
	
	@echo "$(BLUE)⏳ Waiting for database to be healthy...$(NC)"
	@until docker exec arbitrage_db pg_isready -U arbitrage_user -d arbitrage_data > /dev/null 2>&1; do \
		echo "   Database not ready yet..."; \
		sleep 2; \
	done
	@echo "$(GREEN)✅ Database is ready!$(NC)"
	
	@echo "$(BLUE)📊 Starting monitoring services...$(NC)"
	@docker run -d \
		--name arbitrage_pgadmin \
		--network docker_arbitrage_network \
		-p 8080:80 \
		-e PGADMIN_DEFAULT_EMAIL=admin@example.com \
		-e PGADMIN_DEFAULT_PASSWORD=dev_admin \
		-e PGADMIN_CONFIG_SERVER_MODE=False \
		-v pgadmin_data:/var/lib/pgadmin \
		dpage/pgadmin4:latest > /dev/null
	
	@docker run -d \
		--name arbitrage_grafana \
		--network docker_arbitrage_network \
		-p 3000:3000 \
		-e GF_SECURITY_ADMIN_PASSWORD=dev_grafana \
		-e GF_AUTH_ANONYMOUS_ENABLED=true \
		-e GF_AUTH_ANONYMOUS_ORG_ROLE=Admin \
		-v grafana_data:/var/lib/grafana \
		-v $(shell pwd)/grafana/provisioning:/etc/grafana/provisioning:ro \
		grafana/grafana:latest > /dev/null
	
	@echo "$(BLUE)⏳ Waiting for services to start...$(NC)"
	@sleep 10
	
	@echo ""
	@echo "$(GREEN)🎉 Development environment is ready!$(NC)"
	@echo "$(GREEN)=====================================$(NC)"
	@echo "$(YELLOW)📊 Grafana:  http://localhost:3000 (admin/dev_grafana)$(NC)"
	@echo "$(YELLOW)🔧 PgAdmin:  http://localhost:8080 (admin@example.com/dev_admin)$(NC)"
	@echo "$(YELLOW)🗄️  Database: localhost:5432 (arbitrage_user/dev_password_2024)$(NC)"
	@echo ""
	@echo "$(BLUE)📈 Import the dashboard: $(shell pwd)/grafana/dashboard-import.json$(NC)"

dev-rebuild: ## Development: Rebuild and restart development environment
	@echo "$(BLUE)🔄 Rebuilding development environment...$(NC)"
	@docker-compose -f $(COMPOSE_LOCAL) down
	@docker-compose -f $(COMPOSE_LOCAL) build --no-cache data_collector
	@docker-compose -f $(COMPOSE_LOCAL) up -d
	@echo "$(GREEN)✅ Development environment rebuilt$(NC)"

stop-dev: ## Development: Stop all local development services
	@echo "$(BLUE)🛑 Stopping development services...$(NC)"
	@docker-compose -f $(COMPOSE_LOCAL) down || true
	@docker stop arbitrage_grafana arbitrage_pgadmin 2>/dev/null || true
	@docker rm arbitrage_grafana arbitrage_pgadmin 2>/dev/null || true
	@echo "$(GREEN)✅ Development services stopped$(NC)"

# =============================================================================
# Production Deployment
# =============================================================================

deploy: ## Production: Full production deployment to server
	@echo "$(BLUE)🚀 Starting full production deployment...$(NC)"
	@$(MAKE) --no-print-directory sync-code
	@$(MAKE) --no-print-directory deploy-server
	@echo "$(GREEN)✅ Production deployment complete$(NC)"

deploy-quick: ## Production: Quick deployment (code + restart)
	@echo "$(BLUE)⚡ Quick deployment (config/code changes)...$(NC)"
	@$(MAKE) --no-print-directory sync-code
	@ssh -i $(SSH_KEY) root@$(SERVER) 'cd $(REMOTE_PATH)/docker && docker-compose --env-file .env.prod -f $(COMPOSE_PROD) restart data_collector'
	@echo "$(GREEN)✅ Quick deployment complete$(NC)"

sync-code: ## Production: Sync code to production server
	@echo "$(BLUE)📦 Syncing code to server...$(NC)"
	@if [ ! -f ".rsync-exclude" ]; then $(MAKE) --no-print-directory setup-env; fi
	@rsync -avz --progress \
		--exclude-from=".rsync-exclude" \
		-e "ssh -i $(SSH_KEY)" \
		$(LOCAL_PATH)/ \
		root@$(SERVER):$(REMOTE_PATH)/
	@echo "$(GREEN)✅ Code synced to server$(NC)"

deploy-server: ## Production: Deploy services on server
	@echo "$(BLUE)🚀 Deploying services on server...$(NC)"
	@ssh -i $(SSH_KEY) root@$(SERVER) 'cd /opt/arbitrage/docker && \
		if ! command -v docker >/dev/null 2>&1; then \
			echo "Installing Docker..." && \
			curl -fsSL https://get.docker.com | sh && \
			systemctl enable docker && \
			systemctl start docker; \
		fi && \
		if [ ! -f ".env.prod" ]; then \
			echo "Creating production environment template..." && \
			echo "DB_PASSWORD=production_password_$$(date +%s)" > .env.prod && \
			echo "GRAFANA_PASSWORD=production_grafana_$$(date +%s)" >> .env.prod && \
			echo "PGADMIN_PASSWORD=production_pgadmin_$$(date +%s)" >> .env.prod && \
			echo "⚠️  Update .env.prod with secure passwords!"; \
		fi && \
		echo "Starting production services..." && \
		docker-compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d database data_collector && \
		echo "✅ Production deployment complete"'
	@echo "$(GREEN)✅ Server deployment complete$(NC)"

# =============================================================================
# Monitoring & Observability
# =============================================================================

monitor: ## Monitoring: Start local monitoring stack connecting to remote DB
	@echo "$(BLUE)🏠 Starting local monitoring stack...$(NC)"
	@echo "$(BLUE)   → Grafana: http://localhost:3000$(NC)"
	@echo "$(BLUE)   → PgAdmin: http://localhost:8080$(NC)"
	@echo "$(BLUE)   → Connects to remote DB: $(SERVER):5432$(NC)"
	@docker-compose -f $(COMPOSE_MONITOR) up -d
	@echo "$(GREEN)✅ Local monitoring started$(NC)"
	@echo ""
	@echo "$(YELLOW)📊 Access URLs:$(NC)"
	@echo "   Grafana:  http://localhost:3000 (admin/local_grafana_2024)"
	@echo "   PgAdmin:  http://localhost:8080 (admin@localhost.com/local_pgadmin_2024)"

stop-monitor: ## Monitoring: Stop local monitoring services
	@echo "$(BLUE)🛑 Stopping local monitoring services...$(NC)"
	@docker-compose -f $(COMPOSE_MONITOR) down
	@echo "$(GREEN)✅ Monitoring services stopped$(NC)"

prod-monitoring: ## Monitoring: Start production monitoring services on server
	@echo "$(BLUE)📊 Starting production monitoring services on server...$(NC)"
	@ssh -i $(SSH_KEY) root@$(SERVER) 'cd $(REMOTE_PATH)/docker && docker-compose --env-file .env.prod -f $(COMPOSE_PROD) --profile monitoring up -d grafana'
	@echo "$(GREEN)✅ Production Grafana started$(NC)"

prod-admin: ## Monitoring: Start production admin services on server
	@echo "$(BLUE)🔧 Starting production admin services on server...$(NC)"
	@ssh -i $(SSH_KEY) root@$(SERVER) 'cd $(REMOTE_PATH)/docker && docker-compose --env-file .env.prod -f $(COMPOSE_PROD) --profile admin up -d pgadmin'
	@echo "$(GREEN)✅ Production PgAdmin started$(NC)"

# =============================================================================
# Maintenance & Operations
# =============================================================================

maintain-server: ## Maintenance: Run comprehensive server maintenance
	@echo "$(BLUE)🔧 Running comprehensive server maintenance...$(NC)"
	@ssh -i $(SSH_KEY) root@$(SERVER) 'echo "Running disk space cleanup..." && \
		/opt/arbitrage/devops_refactoring/scripts/02_emergency_cleanup.sh && \
		echo "Running database optimization..." && \
		/opt/arbitrage/devops_refactoring/scripts/03_database_optimization.sh --dry-run && \
		echo "Running enhanced monitoring check..." && \
		/opt/arbitrage/enhanced_monitoring.sh && \
		echo "Docker system cleanup..." && \
		docker system prune -f && \
		echo "✅ Server maintenance complete"'
	@echo "$(GREEN)✅ Server maintenance complete$(NC)"

clean: ## Maintenance: Clean local Docker resources
	@echo "$(BLUE)🧹 Cleaning local Docker resources...$(NC)"
	@docker-compose -f $(COMPOSE_LOCAL) down -v 2>/dev/null || true
	@docker-compose -f $(COMPOSE_MONITOR) down -v 2>/dev/null || true
	@docker system prune -f
	@docker volume prune -f
	@echo "$(GREEN)✅ Local cleanup complete$(NC)"

clean-server: ## Maintenance: Clean production server resources
	@echo "$(BLUE)🧹 Cleaning server Docker resources...$(NC)"
	@ssh -i $(SSH_KEY) root@$(SERVER) 'cd $(REMOTE_PATH)/docker && docker system prune -f && docker volume prune -f'
	@echo "$(GREEN)✅ Server cleanup complete$(NC)"

backup-db: ## Maintenance: Create database backup
	@echo "$(BLUE)💾 Creating database backup...$(NC)"
	@ssh -i $(SSH_KEY) root@$(SERVER) 'docker exec arbitrage_db pg_dump -U arbitrage_user arbitrage_data | gzip > $(REMOTE_PATH)/backups/db_backup_$(shell date +%Y%m%d_%H%M%S).sql.gz'
	@echo "$(GREEN)✅ Database backup created$(NC)"

# =============================================================================
# Status & Information
# =============================================================================

status: ## Debug: Show current system status
	@echo "$(BLUE)📊 CEX Arbitrage System Status$(NC)"
	@echo "$(BLUE)==============================$(NC)"
	@echo ""
	@echo "$(YELLOW)Local Containers:$(NC)"
	@docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" --filter "name=arbitrage" 2>/dev/null || echo "No local containers running"
	@echo ""
	@echo "$(YELLOW)Production Server Status:$(NC)"
	@ssh -i $(SSH_KEY) root@$(SERVER) 'cd $(REMOTE_PATH)/docker && docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"' 2>/dev/null || echo "Cannot connect to production server"
	@echo ""
	@echo "$(YELLOW)Production Server Disk Usage:$(NC)"
	@ssh -i $(SSH_KEY) root@$(SERVER) 'df -h /' | tail -n 1 2>/dev/null || echo "Cannot check server disk usage"

logs: ## Debug: Show data collector logs
	@echo "$(BLUE)📋 Data Collector Logs (Local):$(NC)"
	@docker-compose -f $(COMPOSE_LOCAL) logs --tail=50 data_collector 2>/dev/null || echo "No local data collector running"
	@echo ""
	@echo "$(BLUE)📋 Data Collector Logs (Production):$(NC)"
	@ssh -i $(SSH_KEY) root@$(SERVER) 'cd $(REMOTE_PATH)/docker && docker-compose --env-file .env.prod -f $(COMPOSE_PROD) logs --tail=50 data_collector' 2>/dev/null || echo "Cannot access production logs"

debug: ## Debug: Show comprehensive diagnostic information
	@echo "$(BLUE)🔍 System Diagnostic Information$(NC)"
	@echo "$(BLUE)================================$(NC)"
	@echo ""
	@echo "$(YELLOW)Environment:$(NC)"
	@echo "  Docker Version: $$(docker --version 2>/dev/null || echo 'Not installed')"
	@echo "  Docker Compose: $$(docker-compose --version 2>/dev/null || echo 'Not installed')"
	@echo "  Local Path: $(LOCAL_PATH)"
	@echo "  Server: $(SERVER)"
	@echo ""
	@echo "$(YELLOW)Local Docker Resources:$(NC)"
	@docker system df 2>/dev/null || echo "Cannot access Docker"
	@echo ""
	@echo "$(YELLOW)Local Networks:$(NC)"
	@docker network ls | grep arbitrage 2>/dev/null || echo "No arbitrage networks found"
	@echo ""
	@echo "$(YELLOW)Local Volumes:$(NC)"
	@docker volume ls | grep -E "(grafana|pgadmin|postgres)" 2>/dev/null || echo "No data volumes found"
	@echo ""
	@echo "$(YELLOW)Configuration Files:$(NC)"
	@ls -la .env.* 2>/dev/null || echo "No environment files found"

# =============================================================================
# Quick Access Shortcuts
# =============================================================================

open-grafana: ## Monitoring: Open Grafana in browser
	@echo "$(BLUE)🌐 Opening Grafana...$(NC)"
	@echo "URL: http://localhost:3000"
	@echo "Login: admin / local_grafana_2024"
	@open http://localhost:3000 2>/dev/null || xdg-open http://localhost:3000 2>/dev/null || echo "Open http://localhost:3000 manually"

open-pgadmin: ## Monitoring: Open PgAdmin in browser
	@echo "$(BLUE)🌐 Opening PgAdmin...$(NC)"
	@echo "URL: http://localhost:8080"
	@echo "Login: admin@localhost.com / local_pgadmin_2024"
	@open http://localhost:8080 2>/dev/null || xdg-open http://localhost:8080 2>/dev/null || echo "Open http://localhost:8080 manually"

# =============================================================================
# Advanced Operations
# =============================================================================

reset: ## Maintenance: DANGER - Reset all local containers and data
	@echo "$(RED)⚠️  DANGER: This will reset all local containers and data$(NC)"
	@echo "Are you sure? Press Ctrl+C to cancel, Enter to continue..."
	@read dummy
	@echo "$(RED)🗑️  Stopping and removing all arbitrage containers...$(NC)"
	@docker-compose -f $(COMPOSE_MONITOR) down -v || true
	@docker-compose -f $(COMPOSE_LOCAL) down -v || true
	@docker stop arbitrage_grafana arbitrage_pgadmin 2>/dev/null || true
	@docker rm arbitrage_grafana arbitrage_pgadmin 2>/dev/null || true
	@echo "$(RED)🧹 Cleaning up volumes...$(NC)"
	@docker volume prune -f
	@echo "$(GREEN)✅ Reset complete - all local data removed$(NC)"

docs: ## Debug: Show detailed documentation
	@echo "$(BLUE)📚 CEX Arbitrage Infrastructure Documentation$(NC)"
	@echo "$(BLUE)=============================================$(NC)"
	@echo ""
	@if [ -f "README.md" ]; then \
		echo "$(YELLOW)📖 Infrastructure README:$(NC)"; \
		head -20 README.md; \
		echo "..."; \
		echo "$(BLUE)Full documentation: docker/README.md$(NC)"; \
	else \
		echo "$(RED)❌ README.md not found$(NC)"; \
	fi
	@echo ""
	@if [ -f "DEPLOYMENT_GUIDE.md" ]; then \
		echo "$(YELLOW)📖 Deployment Guide:$(NC)"; \
		head -10 DEPLOYMENT_GUIDE.md; \
		echo "..."; \
		echo "$(BLUE)Full guide: docker/DEPLOYMENT_GUIDE.md$(NC)"; \
	fi

# =============================================================================
# Internal Helpers (not shown in help)
# =============================================================================

_check-env:
	@if [ ! -f ".env.local" ] && [ ! -f ".env.prod" ]; then \
		echo "$(RED)❌ No environment files found. Run 'make setup-env' first$(NC)"; \
		exit 1; \
	fi

_health-check:
	@echo "$(BLUE)🏥 Running health checks...$(NC)"
	@docker ps --filter "name=arbitrage_db" --filter "health=healthy" --quiet | grep -q . && echo "$(GREEN)✅ Database healthy$(NC)" || echo "$(YELLOW)⚠️  Database not healthy$(NC)"
	@docker ps --filter "name=arbitrage_collector" --filter "health=healthy" --quiet | grep -q . && echo "$(GREEN)✅ Data collector healthy$(NC)" || echo "$(YELLOW)⚠️  Data collector not healthy$(NC)"