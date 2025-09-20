# 🚀 CEX Arbitrage Docker Deployment Guide

Complete guide for running the CEX Arbitrage system in both development and production environments.

## 📋 Table of Contents
- [Quick Start](#-quick-start)
- [Development Setup](#-development-setup)
- [Production Setup](#-production-setup)
- [Service Architecture](#-service-architecture)
- [Management Commands](#-management-commands)
- [Troubleshooting](#-troubleshooting)

---

## ⚡ Quick Start

### Development Environment
```bash
cd docker
# Start all services including monitoring tools
COMPOSE_PROFILES=admin,monitoring docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Or use the convenience script
./start-all.sh
```

### Production Environment
```bash
cd docker
# Generate secure passwords
./generate-passwords.sh

# Configure API credentials
nano .env.prod

# Deploy to production
./deploy-production.sh
```

---

## 🔧 Development Setup

### Prerequisites
- Docker & Docker Compose installed
- 4GB RAM minimum
- 10GB free disk space

### Step 1: Clone and Navigate
```bash
git clone <repository>
cd cex_arbitrage/docker
```

### Step 2: Configure Environment
The development environment uses `.env` file with default passwords for convenience:

```bash
# Default development passwords (already configured)
POSTGRES_PASSWORD=dev_password_2024
PGADMIN_EMAIL=admin@example.com
PGADMIN_PASSWORD=dev_admin
GRAFANA_PASSWORD=dev_grafana
```

### Step 3: Start Services

#### Option A: Start All Services (Recommended)
```bash
# This starts database, data collector, PgAdmin, and Grafana
COMPOSE_PROFILES=admin,monitoring docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

#### Option B: Use Convenience Script
```bash
./start-all.sh
```

#### Option C: Start Core Services Only
```bash
# Just database and data collector
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### Step 4: Access Services

| Service | URL | Credentials |
|---------|-----|-------------|
| **Grafana** | http://localhost:3000 | admin / dev_grafana |
| **PgAdmin** | http://localhost:8080 | admin@example.com / dev_admin |
| **PostgreSQL** | localhost:5432 | arbitrage_user / dev_password_2024 |

### Step 5: Configure PgAdmin Database Connection

1. Open http://localhost:8080
2. Login with `admin@example.com` / `dev_admin`
3. Right-click "Servers" → "Register" → "Server"
4. **General Tab**: Name = `Arbitrage Database`
5. **Connection Tab**:
   - Host: `database`
   - Port: `5432`
   - Database: `arbitrage_data`
   - Username: `arbitrage_user`
   - Password: `dev_password_2024`
6. Click "Save"

### Step 6: Access Grafana Dashboard

1. Open http://localhost:3000
2. Login with `admin` / `dev_grafana`
3. Go to Dashboards → Browse
4. Click "Arbitrage Data Monitoring"

If dashboard is missing, import it:
```bash
curl -X POST \
  http://localhost:3000/api/dashboards/db \
  -H 'Content-Type: application/json' \
  --user admin:dev_grafana \
  -d @grafana/dashboard-import.json
```

### Development Features

- ✅ **Hot Reload**: Source code mounted as volume - changes apply without rebuild
- ✅ **Debug Logging**: Enhanced logging with DEBUG level
- ✅ **Exposed Ports**: Direct access to all services
- ✅ **Auto-Restart**: Services restart on crash
- ✅ **Anonymous Access**: Grafana allows anonymous viewing

---

## 🔒 Production Setup

### Prerequisites
- Linux server (Ubuntu/Debian recommended)
- Docker & Docker Compose installed
- SSL certificates (for HTTPS)
- Domain name configured
- 8GB RAM minimum
- 50GB free disk space

### Step 1: Prepare Server
```bash
# Create application directory
sudo mkdir -p /opt/arbitrage
cd /opt/arbitrage

# Clone repository
git clone <repository> .
cd docker
```

### Step 2: Generate Secure Passwords
```bash
# This creates .env.prod with strong passwords
./generate-passwords.sh
```

Output example:
```
🔑 Generated passwords:
   Database:      xY9#mK2$vL8@nP4&qR6!
   PgAdmin:       aB3*fG7^jK9(mN2@
   Grafana:       cD5%hJ8&kL1#pQ4$
   Nginx (admin): eF6!jM9@nR3*tY7%
```

**⚠️ IMPORTANT**: Save these passwords securely!

### Step 3: Configure API Credentials
```bash
# Edit production environment file
nano .env.prod
```

Replace placeholder values with your actual API keys:
```bash
# Exchange API Credentials (REPLACE WITH REAL VALUES)
MEXC_API_KEY=your_actual_mexc_api_key
MEXC_SECRET_KEY=your_actual_mexc_secret_key
GATEIO_API_KEY=your_actual_gateio_api_key
GATEIO_SECRET_KEY=your_actual_gateio_secret_key
```

### Step 4: Setup SSL Certificates

#### Option A: Using Let's Encrypt
```bash
# Install certbot
sudo apt install certbot

# Generate certificates
sudo certbot certonly --standalone -d yourdomain.com

# Copy certificates
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem nginx/ssl/
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem nginx/ssl/
```

#### Option B: Using Custom Certificates
```bash
# Copy your certificates
cp /path/to/your/certificate.crt nginx/ssl/fullchain.pem
cp /path/to/your/private.key nginx/ssl/privkey.pem
```

### Step 5: Configure Domain
```bash
# Update domain in nginx config
sed -i 's/your-domain.com/yourdomain.com/g' nginx/nginx.conf
```

### Step 6: Deploy to Production
```bash
# Full deployment with all checks
./deploy-production.sh
```

The script will:
1. Check prerequisites
2. Create data directories
3. Deploy core services
4. Optionally deploy management tools
5. Setup automated backups
6. Run health checks

### Step 7: Verify Deployment

Check service status:
```bash
./deploy-production.sh status
```

View logs:
```bash
./deploy-production.sh logs
```

### Production Features

- ✅ **SSL/TLS Encryption**: HTTPS-only access
- ✅ **Authentication**: HTTP basic auth for admin tools
- ✅ **No Exposed Ports**: Database internal only
- ✅ **Rate Limiting**: DDoS protection
- ✅ **Auto Backups**: Daily database backups
- ✅ **Resource Limits**: CPU/Memory constraints
- ✅ **Health Checks**: Automatic recovery
- ✅ **Log Rotation**: Prevent disk filling

---

## 🏗️ Service Architecture

### Services Overview

| Service | Purpose | Dev Ports | Prod Ports |
|---------|---------|-----------|------------|
| **database** | PostgreSQL + TimescaleDB | 5432 | Internal only |
| **data_collector** | Real-time data collection | - | - |
| **pgadmin** | Database management | 8080 | Via Nginx |
| **grafana** | Monitoring dashboard | 3000 | Via Nginx |
| **nginx** | Reverse proxy (prod only) | - | 80, 443 |

### Docker Compose Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Base configuration |
| `docker-compose.dev.yml` | Development overrides |
| `docker-compose.prod.yml` | Production overrides |

### Environment Variables

| Variable | Development | Production |
|----------|------------|------------|
| `POSTGRES_PASSWORD` | dev_password_2024 | Auto-generated |
| `PGADMIN_PASSWORD` | dev_admin | Auto-generated |
| `GRAFANA_PASSWORD` | dev_grafana | Auto-generated |
| `MEXC_API_KEY` | Optional | Required |
| `GATEIO_API_KEY` | Optional | Required |

---

## 🗄️ External TimescaleDB Setup

If you have an existing TimescaleDB instance and want to use it instead of the containerized database:

### Step 1: Configure External Database
```bash
cd docker
# Create configuration from template
cp .env.external-db .env.external

# Edit with your database details
nano .env.external
```

Update these settings in `.env.external`:
```bash
EXTERNAL_DB_HOST=your-timescale-host.com
EXTERNAL_DB_PORT=5432
EXTERNAL_DB_NAME=arbitrage_data
EXTERNAL_DB_USER=arbitrage_user
EXTERNAL_DB_PASSWORD=your_secure_password
```

### Step 2: Setup Database Schema
Run the initialization script on your external database:
```bash
# Connect to your external TimescaleDB
psql -h your-host -U arbitrage_user -d arbitrage_data

# Create the required tables and extensions
\i init-db.sql
```

### Step 3: Deploy with External Database
```bash
# Automated setup (recommended)
./external-db-setup.sh

# Or manual deployment
docker-compose --env-file .env.external \
  -f docker-compose.yml \
  -f docker-compose.external-db.yml up -d
```

### External Database Features
- ✅ **No local database container** - Uses your existing TimescaleDB
- ✅ **SSL/TLS support** - Secure connections to external database
- ✅ **Connection pooling** - Optimized for external database performance
- ✅ **Health checks** - Validates external database connectivity
- ✅ **PgAdmin pre-configured** - Automatic server setup for external DB

### External Database Commands
```bash
# Check status
docker-compose -f docker-compose.yml -f docker-compose.external-db.yml ps

# View logs
docker-compose -f docker-compose.yml -f docker-compose.external-db.yml logs -f

# Stop services
docker-compose -f docker-compose.yml -f docker-compose.external-db.yml down

# Test database connection
docker exec arbitrage_collector python -c "
import asyncpg, asyncio, os
async def test():
    conn = await asyncpg.connect(
        host=os.getenv('EXTERNAL_DB_HOST'),
        port=int(os.getenv('EXTERNAL_DB_PORT', 5432)),
        database=os.getenv('EXTERNAL_DB_NAME'),
        user=os.getenv('EXTERNAL_DB_USER'),
        password=os.getenv('EXTERNAL_DB_PASSWORD')
    )
    print('✅ External database connection successful!')
    await conn.close()
asyncio.run(test())
"
```

---

## 🛠️ Management Commands

### Development Commands

```bash
# Start all services
COMPOSE_PROFILES=admin,monitoring docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Stop all services
docker-compose -f docker-compose.yml -f docker-compose.dev.yml down

# View logs
docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f

# Restart service
docker-compose -f docker-compose.yml -f docker-compose.dev.yml restart data_collector

# Check status
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Database shell
docker exec -it arbitrage_db psql -U arbitrage_user -d arbitrage_data

# Quick data check
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c \
  "SELECT COUNT(*) as records, MAX(timestamp) as latest FROM book_ticker_snapshots;"
```

### Production Commands

```bash
# Deploy/Update
./deploy-production.sh

# Check status
./deploy-production.sh status

# View logs
./deploy-production.sh logs
./deploy-production.sh logs data_collector

# Restart services
./deploy-production.sh restart

# Stop services
./deploy-production.sh stop

# Backup database
./deploy-production.sh backup

# Manual database backup
docker exec arbitrage_db pg_dump -U arbitrage_user -d arbitrage_data > backup.sql

# Restore database
docker exec -i arbitrage_db psql -U arbitrage_user -d arbitrage_data < backup.sql
```

---

## 🚨 Troubleshooting

### Common Issues and Solutions

#### 1. PgAdmin: No Servers Configured
**Solution**: Manually add server with these settings:
- Host: `database` (not localhost!)
- Port: `5432`
- Database: `arbitrage_data`
- Username: `arbitrage_user`
- Password: Check `.env` or `.env.prod`

#### 2. Grafana: Dashboard Missing
**Solution**: Import dashboard manually:
```bash
curl -X POST http://localhost:3000/api/dashboards/db \
  -H 'Content-Type: application/json' \
  --user admin:dev_grafana \
  -d @grafana/dashboard-import.json
```

#### 3. Data Collector: Connection Failed
**Solution**: Check API credentials:
```bash
# Development
cat .env

# Production
cat .env.prod

# Test connection
docker logs arbitrage_collector --tail 50
```

#### 4. Database: Password Authentication Failed
**Solution**: Ensure environment variables match:
```bash
# Check current password
docker exec arbitrage_db env | grep POSTGRES_PASSWORD

# Restart with correct password
docker-compose -f docker-compose.yml -f docker-compose.dev.yml down
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

#### 5. Services Not Starting
**Solution**: Check Docker resources:
```bash
# Check disk space
df -h

# Check memory
free -h

# Check Docker status
docker system df
docker system prune -a  # Clean up unused resources
```

#### 6. SSL Certificate Issues (Production)
**Solution**: Verify certificates:
```bash
# Check certificate exists
ls -la nginx/ssl/

# Test certificate
openssl x509 -in nginx/ssl/fullchain.pem -text -noout

# Check expiry
openssl x509 -in nginx/ssl/fullchain.pem -noout -dates
```

---

## 📊 Monitoring & Maintenance

### Health Checks

```bash
# Check all services are running
docker ps --filter "name=arbitrage" --format "table {{.Names}}\t{{.Status}}"

# Test database connection
docker exec arbitrage_db pg_isready -U arbitrage_user

# Check data collection
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c \
  "SELECT exchange, COUNT(*) as records, MAX(timestamp) as latest 
   FROM book_ticker_snapshots 
   WHERE timestamp > NOW() - INTERVAL '5 minutes' 
   GROUP BY exchange;"
```

### Performance Monitoring

```bash
# Container resource usage
docker stats --no-stream

# Database size
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c \
  "SELECT pg_size_pretty(pg_database_size('arbitrage_data'));"

# Table sizes
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c \
  "SELECT tablename, pg_size_pretty(pg_total_relation_size(tablename::regclass)) as size 
   FROM pg_tables 
   WHERE schemaname = 'public' 
   ORDER BY pg_total_relation_size(tablename::regclass) DESC;"
```

### Backup & Recovery

```bash
# Manual backup
DATE=$(date +%Y%m%d_%H%M%S)
docker exec arbitrage_db pg_dump -U arbitrage_user -d arbitrage_data | gzip > backup_${DATE}.sql.gz

# Scheduled backups (production)
crontab -e
# Add: 0 2 * * * /opt/arbitrage/docker/backup-database.sh

# Restore from backup
gunzip -c backup_20240101_020000.sql.gz | docker exec -i arbitrage_db psql -U arbitrage_user -d arbitrage_data
```

---

## 🔐 Security Best Practices

### Development
- ✅ Use `.env` for local development only
- ✅ Never expose development instance to internet
- ✅ Regularly update Docker images

### Production
- ✅ Use strong generated passwords
- ✅ Keep `.env.prod` secure and backed up
- ✅ Enable SSL/TLS for all connections
- ✅ Restrict firewall to necessary ports only
- ✅ Monitor logs for suspicious activity
- ✅ Rotate passwords quarterly
- ✅ Keep backups in separate location
- ✅ Update Docker images monthly

---

## 📚 Additional Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [TimescaleDB Documentation](https://docs.timescale.com/)
- [Grafana Documentation](https://grafana.com/docs/)
- [PgAdmin Documentation](https://www.pgadmin.org/docs/)

---

## 📞 Support

For issues:
1. Check logs: `docker-compose logs -f [service_name]`
2. Review this README
3. Check service health: `docker ps`
4. Verify environment variables: `cat .env` or `cat .env.prod`

**Remember**: Never commit `.env.prod` or any file with real passwords to version control!