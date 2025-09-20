# 🚀 Production Deployment Guide

Complete guide for deploying the CEX Arbitrage system to production with enterprise-grade security.

## 📋 Quick Start

```bash
# 1. Generate secure passwords
./generate-passwords.sh

# 2. Configure your API credentials
nano .env.prod

# 3. Deploy to production
./deploy-production.sh
```

## 🔐 Security Features

### ✅ **Password Management**
- **Strong auto-generated passwords** (24+ characters)
- **Environment variable isolation** (`.env.prod`)
- **No hardcoded credentials** in any files
- **Secure storage recommendations**

### ✅ **Network Security**
- **No exposed database ports** (internal access only)
- **Nginx reverse proxy** with SSL termination
- **HTTP authentication** for admin interfaces
- **Rate limiting** on all endpoints

### ✅ **SSL/TLS Encryption**
- **HTTPS-only access** with automatic HTTP redirect
- **TLS 1.2+ only** with secure cipher suites
- **SSL certificate management** ready
- **HSTS headers** for browser security

### ✅ **Access Control**
- **Authentication required** for all admin interfaces
- **Role-based access** via Nginx basic auth
- **Session security** with secure cookies
- **Anonymous access disabled** in production

## 📁 File Structure

```
docker/
├── .env.prod                    # 🔑 Production passwords (KEEP SECRET)
├── docker-compose.yml           # Base configuration
├── docker-compose.prod.yml      # Production overrides
├── generate-passwords.sh        # Password generator
├── deploy-production.sh         # Deployment script
├── nginx/
│   ├── nginx.conf              # Reverse proxy config
│   ├── htpasswd                # HTTP auth passwords
│   └── ssl/                    # SSL certificates
│       ├── fullchain.pem       # SSL certificate
│       └── privkey.pem         # SSL private key
└── backups/                    # Database backups
```

## 🛠️ Production Setup

### 1. **Generate Passwords**

```bash
cd docker
./generate-passwords.sh
```

This creates:
- ✅ `.env.prod` with secure passwords
- ✅ `nginx/htpasswd` for web authentication  
- ✅ Directory structure for SSL certificates

### 2. **Configure API Credentials**

Edit `.env.prod` and replace placeholder values:

```bash
# Exchange API Credentials (REPLACE WITH REAL VALUES)
MEXC_API_KEY=your_actual_mexc_api_key
MEXC_SECRET_KEY=your_actual_mexc_secret_key
GATEIO_API_KEY=your_actual_gateio_api_key
GATEIO_SECRET_KEY=your_actual_gateio_secret_key
```

### 3. **SSL Certificates** (Recommended)

Place your SSL certificates:
```bash
# Copy your SSL certificates
cp your-certificate.pem nginx/ssl/fullchain.pem
cp your-private-key.pem nginx/ssl/privkey.pem

# Update domain in nginx.conf
sed -i 's/your-domain.com/yourdomain.com/g' nginx/nginx.conf
```

### 4. **Deploy to Production**

```bash
./deploy-production.sh
```

This will:
- ✅ Check prerequisites and validate configuration
- ✅ Create data directories with proper permissions
- ✅ Deploy core services (database + data collector)  
- ✅ Optionally deploy management services
- ✅ Run health checks and setup monitoring
- ✅ Configure automated backups

## 🔗 Access Your System

### **With SSL/Nginx (Recommended)**
- 📊 **Grafana**: `https://yourdomain.com/grafana/`
- 🔧 **PgAdmin**: `https://yourdomain.com/pgadmin/`
- 🔐 **Login**: `admin` / `[generated nginx password]`

### **Direct Access** (if no reverse proxy)
- 📊 **Grafana**: `http://server-ip:3000`
- 🔧 **PgAdmin**: `http://server-ip:8080`

## 📊 Management Commands

```bash
# Check service status
./deploy-production.sh status

# View logs
./deploy-production.sh logs
./deploy-production.sh logs data_collector

# Backup database
./deploy-production.sh backup

# Restart services  
./deploy-production.sh restart

# Stop all services
./deploy-production.sh stop
```

## 🎯 Production Profiles

The system uses Docker Compose profiles for different deployment scenarios:

```bash
# Core only (database + data collector)
COMPOSE_PROFILES=production docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# With admin tools
COMPOSE_PROFILES=production,admin docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Full stack (everything)
COMPOSE_PROFILES=production,admin,monitoring,management docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## 🔧 Database Configuration

### **Connection Details**
```
Host: database (internal) or server-ip (external)
Port: 5432 (internal only)
Database: arbitrage_data
Username: arbitrage_user
Password: [from .env.prod]
```

### **PgAdmin Server Setup**
1. Login to PgAdmin with generated credentials
2. Add server with these settings:
   - **Name**: Production Arbitrage DB
   - **Host**: `database`
   - **Port**: `5432`
   - **Database**: `arbitrage_data`
   - **Username**: `arbitrage_user`
   - **Password**: `[from .env.prod POSTGRES_PASSWORD]`

## 🚨 Security Checklist

### ✅ **Before Going Live**
- [ ] Generated strong passwords with `generate-passwords.sh`
- [ ] Updated `.env.prod` with real API credentials
- [ ] Configured SSL certificates in `nginx/ssl/`
- [ ] Updated domain name in `nginx/nginx.conf`
- [ ] Tested all services are running and accessible
- [ ] Verified database backups are working
- [ ] Configured firewall rules for your server
- [ ] Documented password storage location

### ✅ **Ongoing Security**
- [ ] Monitor logs regularly: `./deploy-production.sh logs`
- [ ] Run backups: `./deploy-production.sh backup`
- [ ] Update Docker images monthly
- [ ] Review access logs for suspicious activity
- [ ] Rotate passwords quarterly

## 📈 Monitoring

### **Grafana Dashboard**
- Real-time arbitrage data monitoring
- System health metrics
- Performance monitoring
- Alert configuration

### **Database Monitoring**
- PgAdmin for query analysis
- Table statistics and performance
- Connection monitoring

### **System Monitoring**
- Docker container health
- Resource usage metrics
- Error rate monitoring

## 🆘 Troubleshooting

### **Services Won't Start**
```bash
# Check logs
./deploy-production.sh logs

# Check environment variables
cat .env.prod

# Verify permissions
ls -la /opt/arbitrage/data/
```

### **Database Connection Issues**
```bash
# Test database connectivity
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "SELECT 1;"

# Check database logs
docker logs arbitrage_db
```

### **SSL Certificate Issues**
```bash
# Verify certificates exist
ls -la nginx/ssl/

# Test certificate validity
openssl x509 -in nginx/ssl/fullchain.pem -text -noout
```

## 🔄 Updates and Maintenance

### **Update Application**
```bash
# Pull latest code
git pull origin main

# Rebuild and redeploy
./deploy-production.sh
```

### **Update Docker Images**
```bash
# Update images
docker-compose -f docker-compose.yml -f docker-compose.prod.yml pull

# Restart with new images
./deploy-production.sh restart
```

---

## 📞 Support

For issues with production deployment:
1. Check logs: `./deploy-production.sh logs`
2. Verify configuration: `cat .env.prod`
3. Test connectivity: `./deploy-production.sh status`
4. Review this guide for troubleshooting steps

**Remember**: Keep your `.env.prod` file secure and never commit it to version control!