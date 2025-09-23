# Prometheus Monitoring Setup for HFT Arbitrage Engine

This directory contains a complete Prometheus monitoring stack specifically configured for the HFT arbitrage engine.

## Quick Start

### 1. Start the Monitoring Stack

```bash
# Navigate to the docker directory
cd docker

# Start all monitoring services
docker-compose -f docker-compose.prometheus.yml up -d

# Check service status
docker-compose -f docker-compose.prometheus.yml ps
```

### 2. Enable Prometheus in Application

Update your `.env` file:

```bash
# Enable Prometheus metrics collection
LOGGING_PROMETHEUS_ENABLED=true
PROMETHEUS_PUSH_GATEWAY_URL=http://localhost:9091
PROMETHEUS_JOB_NAME=hft_arbitrage_dev
```

### 3. Access the Monitoring Stack

- **Prometheus**: http://localhost:9090 - Query metrics and view targets
- **Push Gateway**: http://localhost:9091 - Metrics endpoint for HFT logging
- **Grafana**: http://localhost:3000 - Visualization (admin/admin)
- **AlertManager**: http://localhost:9093 - Alert management

## Architecture Overview

### Components

1. **Prometheus Server** (port 9090)
   - Collects and stores metrics
   - Scrapes Push Gateway every 5 seconds
   - 7-day retention period

2. **Push Gateway** (port 9091) 
   - **Critical component** for HFT logging system
   - Receives metrics pushed from the arbitrage engine
   - Allows Prometheus to scrape metrics from short-lived processes

3. **Grafana** (port 3000)
   - Visualization and dashboards
   - Pre-configured with Prometheus datasource
   - Ready for HFT dashboard creation

4. **AlertManager** (port 9093)
   - Alert routing and management
   - Pre-configured with HFT-specific alert rules
   - Supports multiple notification channels

### Data Flow

```
HFT Arbitrage Engine → Push Gateway → Prometheus → Grafana
                                    ↓
                               AlertManager
```

## Configuration Files

### Core Configuration
- `prometheus/prometheus.yml` - Prometheus server configuration
- `prometheus/rules/hft_alerts.yml` - HFT-specific alert rules
- `alertmanager/alertmanager.yml` - Alert routing configuration

### Grafana Setup
- `grafana/provisioning/datasources/prometheus.yml` - Auto-configure Prometheus datasource
- `grafana/provisioning/dashboards/hft_dashboards.yml` - Dashboard provisioning

## Metrics Available

The HFT logging system automatically sends these metrics:

### Trading Metrics
```
hft_execution_latency_ms{operation="place_order", exchange="mexc"}
hft_orders_placed_total{exchange="mexc", symbol="BTC_USDT"}
hft_orders_failed_total{exchange="mexc", symbol="BTC_USDT"}
hft_opportunities_detected_total{source_exchange="mexc", target_exchange="gateio"}
hft_spread_bps{symbol="BTC_USDT", opportunity_type="simple"}
```

### System Metrics
```
hft_websocket_connected{exchange="mexc", channel="orderbook"}
hft_websocket_messages_per_second{exchange="mexc", channel="orderbook"}
hft_rest_request_latency_ms{exchange="gateio", endpoint="orders"}
hft_memory_usage_bytes{component="arbitrage_engine"}
```

## Alert Rules

Pre-configured alerts for:

### Critical Alerts
- **HighExecutionLatency**: >100ms execution time
- **CriticalExecutionLatency**: >500ms execution time
- **ArbitrageEngineDown**: Engine unreachable
- **PushGatewayDown**: Metrics collection failing

### Warning Alerts
- **WebSocketDisconnected**: Connection loss
- **HighOrderFailureRate**: >10% order failures
- **LowOpportunityDetection**: <0.01 opportunities/sec
- **HighMemoryUsage**: >2GB memory usage

## Custom Dashboards

Create custom Grafana dashboards for:

### 1. Trading Performance
```
Execution Latency: avg(hft_execution_latency_ms)
Orders Per Second: rate(hft_orders_placed_total[1m])
Success Rate: rate(hft_orders_placed_total[1m]) / (rate(hft_orders_placed_total[1m]) + rate(hft_orders_failed_total[1m]))
```

### 2. Opportunity Analysis
```
Opportunities Detected: rate(hft_opportunities_detected_total[1m])
Average Spread: avg(hft_spread_bps)
Exchange Distribution: count by (source_exchange)(hft_opportunities_detected_total)
```

### 3. System Health
```
WebSocket Status: hft_websocket_connected
Message Throughput: rate(hft_websocket_messages_per_second[1m])
Memory Usage: hft_memory_usage_bytes / 1024 / 1024 / 1024
```

## Management Commands

### View Logs
```bash
# View all service logs
docker-compose -f docker-compose.prometheus.yml logs -f

# View specific service logs
docker-compose -f docker-compose.prometheus.yml logs -f prometheus
docker-compose -f docker-compose.prometheus.yml logs -f pushgateway
```

### Service Management
```bash
# Restart services
docker-compose -f docker-compose.prometheus.yml restart

# Stop services
docker-compose -f docker-compose.prometheus.yml down

# Update services
docker-compose -f docker-compose.prometheus.yml pull
docker-compose -f docker-compose.prometheus.yml up -d
```

### Data Management
```bash
# View volume usage
docker volume ls | grep prometheus

# Backup Prometheus data
docker run --rm -v prometheus_data:/source -v $(pwd):/backup alpine tar czf /backup/prometheus-backup.tar.gz -C /source .

# Clean up old data (if needed)
docker volume rm prometheus_data grafana_data alertmanager_data
```

## Troubleshooting

### Common Issues

1. **Push Gateway not receiving metrics**
   ```bash
   # Check if Push Gateway is accessible
   curl http://localhost:9091/metrics
   
   # Verify HFT logging configuration
   grep PROMETHEUS .env
   ```

2. **Prometheus not scraping Push Gateway**
   ```bash
   # Check Prometheus targets
   curl http://localhost:9090/api/v1/targets
   
   # Check configuration
   docker-compose -f docker-compose.prometheus.yml exec prometheus cat /etc/prometheus/prometheus.yml
   ```

3. **High resource usage**
   ```bash
   # Monitor container resources
   docker stats hft_prometheus hft_pushgateway hft_grafana
   
   # Adjust retention in prometheus.yml if needed
   ```

### Health Checks

All services include health checks:
```bash
# Check service health
docker-compose -f docker-compose.prometheus.yml ps

# Manual health check
curl http://localhost:9090/-/healthy  # Prometheus
curl http://localhost:9091/metrics    # Push Gateway
curl http://localhost:3000/api/health # Grafana
```

## Production Considerations

### Security
- Change default Grafana admin password
- Configure proper AlertManager notification channels
- Use environment-specific job names in Push Gateway
- Consider enabling HTTPS with reverse proxy

### Performance
- Monitor disk usage for Prometheus data
- Adjust retention period based on requirements
- Consider using remote storage for long-term retention
- Scale Push Gateway if handling high metric volume

### Backup
- Regular backup of Grafana dashboards and configuration
- Export important Prometheus rules and alerts
- Monitor alertmanager configurations

## Integration with HFT Logging

The monitoring stack is fully integrated with the HFT logging system:

1. **Automatic Metrics**: All logger calls automatically send metrics
2. **Zero Configuration**: Works out-of-the-box with default settings
3. **Performance Optimized**: <1μs overhead per metric call
4. **Graceful Degradation**: System continues if monitoring unavailable

For detailed configuration options, see `PROMETHEUS_CONFIGURATION_GUIDE.md`.