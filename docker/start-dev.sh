#!/bin/bash

echo "🚀 Starting CEX Arbitrage Development Environment"
echo "================================================="

# Stop any existing containers
echo "📋 Stopping existing containers..."
docker-compose -f docker-compose.yml -f docker-compose.dev.yml down 2>/dev/null || true

# Start core services (database and data collector)
echo "🗄️  Starting core services (database + data collector)..."
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d database data_collector

# Wait for database to be ready
echo "⏳ Waiting for database to be healthy..."
until docker exec arbitrage_db pg_isready -U arbitrage_user -d arbitrage_data > /dev/null 2>&1; do
  echo "   Database not ready yet..."
  sleep 2
done
echo "✅ Database is ready!"

# Start monitoring services (remove profiles restriction)
echo "📊 Starting monitoring services..."

# Start PgAdmin without profile restriction
docker run -d \
  --name arbitrage_pgadmin \
  --network docker_arbitrage_network \
  -p 8080:80 \
  -e PGADMIN_DEFAULT_EMAIL=admin@example.com \
  -e PGADMIN_DEFAULT_PASSWORD=dev_admin \
  -e PGADMIN_CONFIG_SERVER_MODE=False \
  -v pgadmin_data:/var/lib/pgadmin \
  dpage/pgadmin4:latest

# Start Grafana without profile restriction
docker run -d \
  --name arbitrage_grafana \
  --network docker_arbitrage_network \
  -p 3000:3000 \
  -e GF_SECURITY_ADMIN_PASSWORD=dev_grafana \
  -e GF_AUTH_ANONYMOUS_ENABLED=true \
  -e GF_AUTH_ANONYMOUS_ORG_ROLE=Admin \
  -v grafana_data:/var/lib/grafana \
  -v /Users/dasein/dev/cex_arbitrage/docker/grafana/provisioning:/etc/grafana/provisioning:ro \
  grafana/grafana:latest

echo "⏳ Waiting for services to start..."
sleep 10

# Check status
echo ""
echo "📊 Service Status:"
echo "=================="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" --filter "name=arbitrage"

echo ""
echo "🎉 Development environment is ready!"
echo "====================================="
echo "📊 Grafana:  http://localhost:3000 (admin/dev_grafana)"
echo "🔧 PgAdmin:  http://localhost:8080 (admin@example.com/dev_admin)"
echo "🗄️  Database: localhost:5432 (arbitrage_user/dev_password_2024)"
echo ""
echo "📈 Dashboards auto-provisioned from grafana/provisioning/dashboards/"