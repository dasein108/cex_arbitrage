# 🚀 CEX Arbitrage Docker Deployment

Simple deployment system for CEX Arbitrage with both local development and production environments.

## 📋 Table of Contents
- [Quick Start](#-quick-start)
- [Local Development](#-local-development)
- [Production Deployment](#-production-deployment)
- [Database Management](#-database-management)
- [Monitoring](#-monitoring)
- [Troubleshooting](#-troubleshooting)

---

## ⚡ Quick Start

### Local Development
```bash
cd docker
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### Production Deployment
```bash
cd docker
./deploy.sh deploy
```

---

## 🔧 Local Development

### Prerequisites
- Docker & Docker Compose installed
- 4GB RAM minimum
- 10GB free disk space

### Setup

1. **Navigate to docker directory:**
```bash
cd cex_arbitrage/docker
```

2. **Start services with hot-reload:**
```bash
# Start all services including monitoring
COMPOSE_PROFILES=admin,monitoring docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

3. **Access services locally:**

| Service | URL | Credentials |
|---------|-----|-------------|
| **Grafana** | http://localhost:3000 | admin / dev_grafana |
| **PgAdmin** | http://localhost:8080 | admin@example.com / dev_admin |
| **PostgreSQL** | localhost:5432 | arbitrage_user / dev_password_2024 |

### Development Features
- ✅ **Hot Reload**: Source code mounted as volume - changes apply instantly
- ✅ **Debug Logging**: Enhanced logging with DEBUG level
- ✅ **All Ports Exposed**: Direct access to all services
- ✅ **Auto-Restart**: Services restart on crash

### Development Commands
```bash
# View logs
docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f data_collector

# Restart service
docker-compose -f docker-compose.yml -f docker-compose.dev.yml restart data_collector

# Stop all
docker-compose -f docker-compose.yml -f docker-compose.dev.yml down

# Database shell
docker exec -it arbitrage_db psql -U arbitrage_user -d arbitrage_data
```

---

## 🚀 Production Deployment

### Server Configuration
- **Server IP**: 31.192.233.13
- **SSH Key**: ~/.ssh/deploy_ci
- **Path**: /opt/arbitrage

### One-Command Deployment

The `deploy.sh` script handles everything:

```bash
# Full deployment (first time)
./deploy.sh deploy

# Update code only
./deploy.sh update

# Sync code without deploying
./deploy.sh sync
```

### What Deploy Script Does

1. **Syncs code** via rsync (excludes .git, __pycache__, .venv, etc.)
2. **Installs Docker** and Docker Compose if needed
3. **Generates secure passwords** automatically
4. **Initializes database** with schema from `init-db.sql`
5. **Starts all services** with production configuration

### Production Access

After deployment, access services at:

| Service | URL | Notes |
|---------|-----|-------|
| **Grafana** | http://31.192.233.13:3000 | Monitoring dashboard |
| **PgAdmin** | http://31.192.233.13:8080 | Database management |

Check `.env.prod` on server for generated passwords.

### Production Features
- ✅ **Resource Limits**: CPU/Memory constraints
- ✅ **Health Checks**: Automatic recovery
- ✅ **Log Rotation**: Prevent disk filling
- ✅ **No Exposed Database**: Internal access only

---

## 🗄️ Database Management

### Schema Initialization

Database schema is automatically initialized from `init-db.sql` which includes:
- TimescaleDB hypertables for time-series data
- Optimized indexes for query performance
- 30-day data retention policy
- Continuous aggregates for 1-minute and 5-minute intervals

### Schema Updates

Apply safe schema updates from `schema-updates.sql`:

```bash
# On server
cd /opt/arbitrage/docker
docker exec -i $(docker-compose -f docker-compose.yml -f docker-compose.prod.yml ps -q database) \
  psql -U arbitrage_user -d arbitrage_data < schema-updates.sql
```

### Database Commands

```bash
# Check data collection
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c \
  "SELECT exchange, COUNT(*) as records, MAX(timestamp) as latest 
   FROM book_ticker_snapshots 
   WHERE timestamp > NOW() - INTERVAL '5 minutes' 
   GROUP BY exchange;"

# Database size
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c \
  "SELECT pg_size_pretty(pg_database_size('arbitrage_data'));"

# Backup database
docker exec arbitrage_db pg_dump -U arbitrage_user -d arbitrage_data | gzip > backup_$(date +%Y%m%d).sql.gz
```

---

## 📊 Monitoring

### Grafana Dashboard

1. Access Grafana (see URLs above)
2. Login with credentials
3. Navigate to Dashboards → Browse
4. View "Arbitrage Data Monitoring"

### PgAdmin Database Management

1. Access PgAdmin (see URLs above)
2. Login with credentials
3. Add server connection:
   - **Host**: `database`
   - **Port**: `5432`
   - **Database**: `arbitrage_data`
   - **Username**: `arbitrage_user`
   - **Password**: (from .env or .env.prod)

### Health Checks

```bash
# Check all services
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Test database connection
docker exec arbitrage_db pg_isready -U arbitrage_user

# View collector logs
docker logs arbitrage_collector --tail 50
```

---

## 🚨 Troubleshooting

### Docker Compose Not Found

If you see `docker-compose: command not found`:

```bash
# Install via curl
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Or install via pip
pip3 install docker-compose
```

### Database Connection Failed

```bash
# Check if database is running
docker ps | grep database

# Check database logs
docker logs arbitrage_db --tail 50

# Verify environment variables
cat .env.prod  # Production
cat .env       # Development
```

### Data Collector Not Working

```bash
# Check collector logs
docker logs arbitrage_collector --tail 100

# Verify API credentials in .env.prod
grep -E "MEXC_|GATEIO_" .env.prod

# Restart collector
docker-compose -f docker-compose.yml -f docker-compose.prod.yml restart data_collector
```

### Services Not Starting

```bash
# Check disk space
df -h

# Check memory
free -h

# Clean Docker resources
docker system prune -a

# Restart all services
docker-compose -f docker-compose.yml -f docker-compose.prod.yml down
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### PgAdmin: No Servers Configured

Manually add server with:
- **Host**: `database` (not localhost!)
- **Port**: `5432`
- **Database**: `arbitrage_data`
- **Username**: `arbitrage_user`
- **Password**: Check `.env` or `.env.prod`

---

## 📁 File Structure

```
docker/
├── deploy.sh                 # Production deployment script
├── docker-compose.yml        # Base configuration
├── docker-compose.dev.yml    # Development overrides
├── docker-compose.prod.yml   # Production configuration
├── Dockerfile               # Data collector image
├── init-db.sql             # Database schema
├── schema-updates.sql      # Schema migrations
├── generate-passwords.sh   # Password generator
├── .env                    # Development environment
├── .env.prod              # Production environment (generated)
└── .rsync-exclude         # Rsync exclusion patterns
```

---

## 🔐 Security

### Development
- Uses default passwords for convenience
- All services exposed on localhost
- Debug logging enabled

### Production
- Auto-generated secure passwords
- Database not exposed externally
- Resource limits applied
- Log rotation configured

### Important Files
- **Never commit** `.env.prod` to version control
- **Keep backups** of production passwords
- **Rotate passwords** quarterly

---

## 🔄 Updating

### Update Code Only
```bash
# From local machine
./deploy.sh update
```

This will:
1. Sync latest code to server
2. Restart data collector
3. Keep database and monitoring running

### Update Everything
```bash
# Full redeployment
./deploy.sh deploy
```

---

## 📞 Support

For issues:
1. Check logs: `docker logs [container_name]`
2. Verify environment variables
3. Check service health: `docker ps`
4. Review troubleshooting section above

**Remember**: Keep your production passwords secure!