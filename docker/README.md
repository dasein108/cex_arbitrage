# CEX Arbitrage Deployment System

Comprehensive Docker-based deployment system for the high-frequency trading (HFT) arbitrage engine. This system supports both local development/monitoring and production deployment with full automation.

## 🚀 Quick Start

```bash
# Local development monitoring
make local-monitoring     # Start Grafana + PgAdmin → connects to remote DB

# Production deployment
make deploy              # Full production deployment
make deploy-sync         # Quick sync with smart restart
make deploy-update       # Quick updates after code changes
make deploy-fix          # Complete fix (cleanup + sync + update)
```

## 📋 Table of Contents

- [System Architecture](#system-architecture)
- [Local Development](#local-development)
- [Production Deployment](#production-deployment)
- [Container Management](#container-management)
- [Monitoring & Access](#monitoring--access)
- [Maintenance & Cleanup](#maintenance--cleanup)
- [Development Tools](#development-tools)
- [Configuration Files](#configuration-files)
- [Troubleshooting](#troubleshooting)

## 🏗️ System Architecture

### Local Development Setup
- **Grafana**: Web-based analytics and monitoring (localhost:3000)
- **PgAdmin**: PostgreSQL administration tool (localhost:8080)
- **Remote Database**: Connects to production database on 31.192.233.13:5432

### Production Environment
- **Database**: PostgreSQL with TimescaleDB for time-series data
- **Data Collector**: High-performance arbitrage data collection service
- **Monitoring**: Optional Grafana and PgAdmin services
- **Networking**: Optimized for 4GB server with memory management

---

## 🏠 Local Development

### Start Local Monitoring
```bash
make local-monitoring
```
**What it does:**
- Starts Grafana and PgAdmin containers locally
- Connects to remote production database (31.192.233.13:5432)
- Provides web interfaces for monitoring and database management
- Uses docker-compose.local-monitoring.yml configuration

**Access URLs:**
- Grafana: http://localhost:3000 (admin/local_grafana_2024)
- PgAdmin: http://localhost:8080 (admin@localhost.com/local_pgadmin_2024)

### Full Development Environment
```bash
make dev
```
**What it does:**
- Runs start-dev.sh script for complete development setup
- Includes database, data collector, and monitoring services
- Uses development configuration with debug logging
- Suitable for local testing and development

### Stop Local Services
```bash
make stop-local
```
**What it does:**
- Stops all local monitoring containers
- Stops development environment containers
- Cleans up running arbitrage-related containers
- Preserves data volumes for next startup

---

## 🚀 Production Deployment

### Full Deployment
```bash
make deploy
# OR use the legacy alias from root directory:
# cd .. && make deploy (redirects to docker/make deploy)
```
**What it does:**
- Syncs code from local machine to production server (31.192.233.13)
- Installs Docker and Docker Compose if needed
- Sets up swap space for memory optimization
- Generates secure passwords in .env.prod
- Creates required data directories with proper permissions
- Initializes database schema with constraints
- Starts core services (database + data collector)
- Provides instructions for optional monitoring services

### Quick Update
```bash
make update
# OR use the deployment alias:
make deploy-update
```
**What it does:**
- Syncs code changes to production server
- Performs smart auto-restart of running services
- Executes comprehensive service restart cycle
- Reloads configuration without full redeployment
- Ideal for code changes and configuration updates

### Rebuild Images
```bash
make rebuild
```
**What it does:**
- Syncs latest code to server
- Stops data collector service
- Rebuilds Docker image with --no-cache flag
- Incorporates new dependencies and code changes
- Restarts data collector with fresh image
- Use after dependency changes in requirements.txt

### Smart Sync
```bash
make sync
# OR use the deployment alias:
make deploy-sync
```
**What it does:**
- Syncs code files to production server using rsync
- Automatically detects running services
- Restarts only active services (skips stopped ones)
- Provides fast iteration cycle for development
- Includes safety checks for Docker Compose availability

---

## 🔧 Container Management

### Local Container Rebuild
```bash
make rebuild-local
```
**What it does:**
- Executes rebuild.sh restart-local command
- Rebuilds local development containers
- Restarts services with fresh images
- Maintains data persistence across rebuilds

### Server Container Rebuild
```bash
make rebuild-server
```
**What it does:**
- Executes rebuild.sh restart-server command
- Rebuilds containers on production server
- Handles remote Docker operations
- Ensures service availability during rebuild

### View Logs
```bash
make logs
```
**What it does:**
- Shows data collector logs from production server
- Displays latest 50 log entries
- Provides real-time insight into system operation
- Uses rebuild.sh logs command for log access

### Check Status
```bash
make status
```
**What it does:**
- Shows container status and health information
- Displays service availability and resource usage
- Provides overview of system operational state
- Uses rebuild.sh status command for comprehensive status

### Container List
```bash
make ps
```
**What it does:**
- Shows formatted table of Docker containers
- Displays container names, status, and port mappings
- Filters for arbitrage-related containers
- Includes both local and production container status

---

## 🧹 Maintenance & Cleanup

### Clean Local Resources
```bash
make clean
```
**What it does:**
- Removes unused Docker containers and images
- Cleans up local development artifacts
- Frees disk space used by Docker
- Uses rebuild.sh clean command for thorough cleanup

### Clean Server Resources
```bash
make clean-server
```
**What it does:**
- Executes cleanup-server.sh all command
- Removes obsolete files and containers on server
- Cleans up log files and temporary data
- Optimizes server disk usage

### Clean Docker on Server
```bash
make clean-docker-server
```
**What it does:**
- Executes cleanup-server.sh docker command
- Specifically targets Docker resources on server
- Removes unused images, containers, and volumes
- Preserves active services and persistent data

### Analyze Database
```bash
make analyze-db
```
**What it does:**
- Executes cleanup-server.sh database command
- Analyzes PostgreSQL database space usage
- Shows table sizes, index usage, and performance metrics
- Identifies optimization opportunities

### Deep Server Analysis
```bash
make analyze-server
```
**What it does:**
- Executes cleanup-server.sh analyze command
- Comprehensive server performance analysis
- Shows disk usage, memory consumption, CPU utilization
- Provides detailed system health report

## 📊 Monitoring & Access

### Open Grafana
```bash
make grafana
```
**What it does:**
- Opens Grafana web interface in default browser
- Provides login credentials (admin/local_grafana_2024)
- Works on macOS, Linux, and Windows
- Fallback instruction if browser doesn't open automatically

### Open PgAdmin
```bash
make pgadmin
```
**What it does:**
- Opens PgAdmin web interface in default browser
- Provides login credentials (admin@localhost.com/local_pgadmin_2024)
- Cross-platform browser opening
- Manual URL provided if automatic opening fails

### Production Monitoring
```bash
make prod-monitoring
```
**What it does:**
- Starts Grafana service on production server
- Uses SSH to execute remote Docker commands
- Enables production monitoring dashboard access
- Uses monitoring profile for resource optimization

### Production Admin
```bash
make prod-admin
```
**What it does:**
- Starts PgAdmin service on production server
- Provides database administration access for production
- Uses admin profile for controlled access
- Enables remote database management

### Production Status
```bash
make prod-status
```
**What it does:**
- Shows status of all production services
- Uses SSH to query remote Docker Compose
- Displays service health and availability
- Provides overview of production system state

### Production Logs
```bash
make prod-logs
```
**What it does:**
- Shows latest 50 entries from production data collector
- Uses SSH to access remote container logs
- Provides real-time production system monitoring
- Essential for troubleshooting production issues

## 🔧 Development Tools

### Configuration Validation
```bash
make config-check
```
**What it does:**
- Validates all Docker Compose configuration files
- Checks base, development, production, and monitoring configs
- Uses docker-compose config --quiet for validation
- Ensures configuration integrity before deployment

### Environment Setup
```bash
make setup-env
```
**What it does:**
- Creates .env.local file with default values
- Sets up Grafana and PgAdmin passwords
- Provides template for database connection
- Ensures local environment is properly configured

### Debug Information
```bash
make debug
```
**What it does:**
- Shows comprehensive system debug information
- Displays Docker and Docker Compose versions
- Lists running containers and their status
- Shows network and volume information
- Essential for troubleshooting deployment issues

### Reset Local Environment
```bash
make reset
```
**What it does:**
- ⚠️ **DANGER**: Completely resets local environment
- Stops and removes all arbitrage containers
- Removes all data volumes (irreversible)
- Requires confirmation before execution
- Use only when complete reset is needed

### Documentation
```bash
make docs
```
**What it does:**
- Shows deployment documentation overview
- Displays first 20 lines of DEPLOYMENT_GUIDE.md
- Provides quick access to setup instructions
- References this README.md for complete documentation

## 📁 Configuration Files

### Docker Compose Files
- **docker-compose.yml**: Base service definitions
- **docker-compose.dev.yml**: Development environment overrides
- **docker-compose.prod.yml**: Production environment configuration
- **docker-compose.local-monitoring.yml**: Local monitoring stack
- **docker-compose.prometheus.yml**: Prometheus monitoring (optional)

### Environment Files
- **.env.local**: Local development environment variables
- **.env.prod**: Production environment variables (server-side)
- **.env.local-monitoring**: Local monitoring configuration

### Database Configuration
- **init-db.sql**: Database initialization schema
- **optimize-db.sql**: Database performance optimizations
- **postgres-prod.conf/**: Production PostgreSQL configuration

### Grafana Configuration
- **grafana/provisioning/**: Auto-provisioning configuration
- **grafana/dashboards/**: Dashboard definitions
- **grafana/provisioning/datasources/**: Data source connections

### Scripts
- **deploy.sh**: Main deployment automation script
- **rebuild.sh**: Container rebuild and management
- **cleanup-server.sh**: Server maintenance and cleanup
- **start-dev.sh**: Development environment startup

## 🚨 Troubleshooting

### Common Issues

#### 1. Docker Compose Not Found
```bash
# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
```

#### 2. Permission Denied
```bash
# Fix Docker permissions
sudo usermod -aG docker $USER
# Logout and login again
```

#### 3. Port Already in Use
```bash
# Check what's using the port
sudo lsof -i :3000  # For Grafana
sudo lsof -i :8080  # For PgAdmin

# Stop conflicting services
make stop-local
```

#### 4. Database Connection Issues
```bash
# Check database connectivity
make debug
make prod-status

# Verify environment variables
cat .env.local
```

#### 5. Memory Issues (4GB Server)
```bash
# Check server memory usage
make analyze-server

# Clean up unused resources
make clean-server
```

### Debug Commands

```bash
# Comprehensive system check
make debug

# Validate configurations
make config-check

# Check container status
make ps

# View logs
make logs
make prod-logs

# Server analysis
make analyze-server
make analyze-db
```

### Recovery Procedures

#### Local Environment Recovery
```bash
# Soft reset - stop and restart
make stop-local
make local-monitoring

# Hard reset - complete cleanup
make reset  # ⚠️ DANGER: Removes all data
make setup-env
make local-monitoring
```

#### Production Recovery
```bash
# Quick fix for most issues
make deploy-fix  # From root Makefile

# Or step by step
make clean-server
make sync
make update
```

## 🔗 Related Documentation

- **DEPLOYMENT_GUIDE.md**: Detailed deployment instructions
- **../PROJECT_GUIDES.md**: Development guidelines and patterns
- **../CLAUDE.md**: System architecture overview
- **../Makefile**: Root-level development commands

## 📞 Support

For issues and questions:
1. Check this documentation first
2. Run `make debug` for system diagnostics
3. Review logs with `make logs` or `make prod-logs`
4. Use `make config-check` to validate configurations
5. Try `make deploy-fix` for common production issues

---

*Last Updated: October 2025*
*System Version: HFT Arbitrage Engine v2.0 with Smart Sync*