#!/bin/bash

# =============================================================================
# Production Password Generator for CEX Arbitrage System
# =============================================================================
# This script generates secure random passwords for production deployment

set -e

echo "🔐 Generating Production Passwords for CEX Arbitrage System"
echo "==========================================================="

# Function to generate secure password
generate_password() {
    local length=${1:-32}
    openssl rand -base64 $length | tr -d "=+/" | cut -c1-$length
}

# Generate passwords
DB_PASSWORD=$(generate_password 24)
PGADMIN_PASSWORD=$(generate_password 20)
GRAFANA_PASSWORD=$(generate_password 20)
GRAFANA_SECRET_KEY=$(openssl rand -hex 32)
NGINX_PASSWORD=$(generate_password 16)

# Create production .env file
cat > .env.prod << EOF
# =============================================================================
# PRODUCTION ENVIRONMENT CONFIGURATION
# Generated on: $(date)
# =============================================================================
# 🔒 CRITICAL: Keep this file secure and never commit to version control!

# PostgreSQL Database Configuration
POSTGRES_PASSWORD=${DB_PASSWORD}
POSTGRES_DB=arbitrage_data
POSTGRES_USER=arbitrage_user
DB_PASSWORD=${DB_PASSWORD}

# PgAdmin Configuration
PGADMIN_EMAIL=admin@yourdomain.com
PGADMIN_PASSWORD=${PGADMIN_PASSWORD}

# Grafana Configuration
GRAFANA_PASSWORD=${GRAFANA_PASSWORD}
GRAFANA_SECRET_KEY=${GRAFANA_SECRET_KEY}

# =============================================================================
# Exchange API Credentials (REPLACE WITH REAL VALUES)
# =============================================================================
MEXC_API_KEY=your_production_mexc_api_key_here
MEXC_SECRET_KEY=your_production_mexc_secret_key_here
GATEIO_API_KEY=your_production_gateio_api_key_here
GATEIO_SECRET_KEY=your_production_gateio_secret_key_here

# Application Settings
ENVIRONMENT=production
LOG_LEVEL=INFO
EOF

# Create nginx htpasswd file
echo "admin:$(openssl passwd -apr1 ${NGINX_PASSWORD})" > nginx/htpasswd

# Create SSL directory structure
mkdir -p nginx/ssl ssl

echo ""
echo "✅ Production passwords generated successfully!"
echo "=============================================="
echo ""
echo "📁 Files created:"
echo "   - .env.prod          (Environment variables)"
echo "   - nginx/htpasswd     (Nginx authentication)"
echo "   - nginx/ssl/         (SSL certificate directory)"
echo "   - ssl/               (Application SSL directory)"
echo ""
echo "🔑 Generated passwords:"
echo "   Database:      ${DB_PASSWORD}"
echo "   PgAdmin:       ${PGADMIN_PASSWORD}"
echo "   Grafana:       ${GRAFANA_PASSWORD}"
echo "   Nginx (admin): ${NGINX_PASSWORD}"
echo ""
echo "⚠️  IMPORTANT NEXT STEPS:"
echo "   1. Update .env.prod with your real exchange API credentials"
echo "   2. Place SSL certificates in nginx/ssl/ directory:"
echo "      - fullchain.pem (certificate)"
echo "      - privkey.pem (private key)"
echo "   3. Update your-domain.com in nginx/nginx.conf"
echo "   4. Run: ./deploy-production.sh"
echo ""
echo "🔒 SECURITY: Store these passwords securely and delete this output!"