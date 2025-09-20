#!/bin/bash

echo "🚀 Starting Complete CEX Arbitrage Stack"
echo "========================================"

cd "$(dirname "$0")"

# Start all services including PgAdmin and Grafana
COMPOSE_PROFILES=admin,monitoring docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

echo ""
echo "⏳ Waiting for services to start..."
sleep 10

echo ""
echo "📊 Service Status:"
echo "=================="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" --filter "name=arbitrage"

echo ""
echo "🎉 All services are ready!"
echo "=========================="
echo "📊 Grafana:    http://localhost:3000"
echo "🔧 PgAdmin:    http://localhost:8080"
echo "🗄️  Database:   localhost:5432"
echo ""
echo "📈 Dashboard: http://localhost:3000/d/arbitrage-monitor/arbitrage-data-monitoring"