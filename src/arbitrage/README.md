# HFT Arbitrage Framework

Ultra-high-performance arbitrage engine designed for sub-50ms cryptocurrency trading across multiple exchanges with atomic spot + futures hedge operations.

## Overview

This arbitrage framework provides a complete solution for high-frequency trading (HFT) arbitrage operations with the following key characteristics:

- **Sub-50ms execution targets** for complete arbitrage cycles
- **Atomic spot + futures coordination** for risk-free operations
- **HFT-compliant architecture** with no real-time data caching
- **Comprehensive recovery capabilities** for partial execution handling
- **Cross-exchange precision matching** with decimal accuracy
- **Real-time risk management** with automated circuit breakers

## Architecture

### Core Components

The framework follows an **event-driven architecture with Abstract Factory pattern** for maximum performance and extensibility:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ ArbitrageEngine │────│ OpportunityDetector │────│ MarketDataAggregator │
│   (Orchestrator) │    │  (Detection)      │    │   (Data Sync)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                        │                        │
         ▼                        ▼                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ OrderOrchestrator │  │  PositionManager │    │   RiskManager   │
│  (Execution)     │    │   (Tracking)     │    │  (Limits)       │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                        │                        │
         ▼                        ▼                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  StateController │   │  BalanceMonitor  │    │ RecoveryManager │
│ (State Machine)  │    │  (Balances)      │    │   (Recovery)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### Component Responsibilities

#### 1. **ArbitrageEngine** - Main Orchestrator
- Coordinates all arbitrage operations and components
- Manages engine lifecycle and graceful shutdown
- Executes atomic spot + futures hedge operations
- Provides session management and health monitoring

**Key Methods:**
- `execute_opportunity()` - Execute arbitrage with atomic coordination
- `start()` / `stop()` - Engine lifecycle management
- `session()` - Context manager for complete sessions
- `get_engine_statistics()` - Performance metrics

#### 2. **OpportunityDetector** - Real-time Opportunity Detection
- Continuously scans for cross-exchange price differentials
- Supports multiple arbitrage strategies (spot-spot, spot-futures, triangular)
- Validates opportunity profitability and execution feasibility
- Provides real-time opportunity alerts

**Key Methods:**
- `start_detection()` / `stop_detection()` - Detection lifecycle
- `validate_opportunity_risk()` - Risk validation
- `add_symbol_monitoring()` - Dynamic symbol management

#### 3. **PositionManager** - Atomic Operation Management
- Tracks all positions across multiple exchanges
- Manages atomic spot + futures hedge coordination
- Handles position aging and health monitoring
- Provides real-time P&L calculations

**Key Methods:**
- `create_position()` - Atomic position creation
- `get_positions()` - Position queries with filtering
- `calculate_total_exposure()` - Risk exposure calculation
- `calculate_total_pnl()` - Real-time P&L tracking

#### 4. **OrderOrchestrator** - Execution Layer
- Executes atomic orders across exchanges
- Handles precision decimal matching between exchanges
- Manages execution strategies and timing
- Provides comprehensive execution monitoring

**Key Methods:**
- `execute_opportunity()` - Strategy-specific execution
- `cancel_all_orders()` - Emergency order cancellation
- `get_execution_statistics()` - Performance metrics

#### 5. **StateController** - Finite State Machine
- Manages arbitrage operation state transitions
- Provides atomic state management with audit trails
- Handles recovery state coordination
- Ensures operation consistency and traceability

**Key Methods:**
- `create_operation()` - Initialize operation tracking
- `transition_state()` - Atomic state transitions
- `transition_to_recovery()` - Recovery state management
- `get_operations_by_state()` - State-based queries

#### 6. **RiskManager** - Real-time Risk Management
- Monitors position limits and exposure constraints
- Provides automated circuit breaker functionality
- Calculates real-time risk metrics and P&L
- Handles emergency shutdown procedures

**Key Methods:**
- `validate_opportunity_risk()` - Pre-execution risk checks
- `start_monitoring()` - Risk monitoring lifecycle
- `force_emergency_shutdown()` - Emergency procedures
- `get_current_risk_metrics()` - Real-time risk data

#### 7. **BalanceMonitor** - Balance Tracking
- Provides HFT-compliant balance refresh (no caching)
- Manages cross-exchange balance synchronization
- Handles balance reservation for pending operations
- Monitors balance thresholds and alerts

**Key Methods:**
- `get_balance()` - Real-time balance queries
- `check_sufficient_balance()` - Balance validation
- `reserve_balance()` - Atomic balance reservation
- `start_monitoring()` - Balance monitoring lifecycle

#### 8. **RecoveryManager** - Error Recovery
- Handles partial execution recovery scenarios
- Provides intelligent recovery strategy selection
- Manages automated recovery with manual escalation
- Maintains comprehensive recovery audit trails

**Key Methods:**
- `initiate_recovery()` - Start recovery procedures
- `get_active_recoveries()` - Recovery status monitoring
- `cancel_recovery()` - Manual recovery cancellation

#### 9. **MarketDataAggregator** - Cross-exchange Data Sync
- Provides real-time cross-exchange data synchronization
- Manages WebSocket connections with REST fallback
- Ensures HFT-compliant data handling (no caching)
- Handles sub-millisecond data processing

**Key Methods:**
- `start_aggregation()` - Data aggregation lifecycle
- `get_latest_snapshot()` - Synchronized market data
- `add_symbol_subscription()` - Dynamic symbol management

## Data Structures

### Core Data Types

All data structures use **msgspec.Struct** for optimal performance:

```python
# Arbitrage Opportunity
@dataclass
class ArbitrageOpportunity(Struct, frozen=True):
    opportunity_id: str
    opportunity_type: OpportunityType
    symbol: Symbol
    buy_exchange: ExchangeName
    sell_exchange: ExchangeName
    buy_price: Decimal
    sell_price: Decimal
    max_quantity: Decimal
    profit_margin_bps: int
    # ... comprehensive execution parameters

# Position Entry
@dataclass  
class PositionEntry(Struct, frozen=True):
    position_id: str
    opportunity_id: str
    exchange: ExchangeName
    symbol: Symbol
    side: OrderSide
    quantity: Decimal
    entry_price: Decimal
    # ... execution and recovery metadata

# Risk Limits
@dataclass
class RiskLimits(Struct, frozen=True):
    max_position_size_usd: Decimal
    max_total_exposure_usd: Decimal
    max_daily_loss_usd: Decimal
    min_profit_margin_bps: int
    # ... comprehensive risk parameters
```

### State Management

The framework uses a **finite state machine** for atomic operation tracking:

```
States: IDLE → DETECTING → OPPORTUNITY_FOUND → EXECUTING → COMPLETED/FAILED
                     ↓
                RECOVERING (can transition to any operational state)
```

## Usage Examples

### Basic Arbitrage Engine Setup

```python
import asyncio
from decimal import Decimal

from arbitrage import ArbitrageEngine, ArbitrageConfig, RiskLimits
from exchanges.mexc.private import MexcPrivateExchange
from exchanges.gateio.private import GateioPrivateExchange

async def main():
    # Configure risk limits
    risk_limits = RiskLimits(
        max_position_size_usd=Decimal("10000"),
        max_total_exposure_usd=Decimal("50000"), 
        max_daily_loss_usd=Decimal("5000"),
        min_profit_margin_bps=50,  # 0.5% minimum profit
        max_execution_time_ms=45000,  # 45 second max execution
        max_slippage_bps=20,  # 0.2% max slippage
    )
    
    # Engine configuration
    config = ArbitrageConfig(
        engine_name="hft_arbitrage_v1",
        enabled_opportunity_types=[
            OpportunityType.SPOT_SPOT,
            OpportunityType.SPOT_FUTURES_HEDGE,
        ],
        enabled_exchanges=[ExchangeName.MEXC, ExchangeName.GATEIO],
        target_execution_time_ms=30000,  # 30ms target
        risk_limits=risk_limits,
        enable_risk_checks=True,
        enable_circuit_breakers=True,
    )
    
    # Exchange connections
    mexc_private = MexcPrivateExchange(api_key="...", secret_key="...")
    gateio_private = GateioPrivateExchange(api_key="...", secret_key="...")
    
    private_exchanges = {
        ExchangeName.MEXC: mexc_private,
        ExchangeName.GATEIO: gateio_private,
    }
    
    # Initialize engine
    engine = ArbitrageEngine(
        config=config,
        public_exchanges=public_exchanges,  # From existing setup
        private_exchanges=private_exchanges,
    )
    
    # Run arbitrage session
    async with engine.session() as arb_engine:
        print("Arbitrage engine operational...")
        
        # Engine will automatically detect and execute opportunities
        # Monitor engine statistics
        while True:
            stats = arb_engine.get_engine_statistics()
            print(f"Opportunities: {stats['opportunities_detected']}, "
                  f"Executed: {stats['opportunities_executed']}")
            
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
```

### Manual Opportunity Execution

```python
async def execute_specific_opportunity():
    # Create specific opportunity
    opportunity = ArbitrageOpportunity(
        opportunity_id="manual_btc_usdt_001",
        opportunity_type=OpportunityType.SPOT_SPOT,
        symbol=Symbol("BTC/USDT"),
        buy_exchange=ExchangeName.MEXC,
        sell_exchange=ExchangeName.GATEIO,
        buy_price=Decimal("45000.00"),
        sell_price=Decimal("45100.00"),
        max_quantity=Decimal("0.1"),
        profit_per_unit=Decimal("100.00"),
        total_profit_estimate=Decimal("10.00"),
        profit_margin_bps=22,  # 0.22% profit
        # ... other parameters
    )
    
    # Execute opportunity
    async with engine.session() as arb_engine:
        result = await arb_engine.execute_opportunity(opportunity)
        
        print(f"Execution result: {result.final_state}")
        print(f"Execution time: {result.total_execution_time_ms}ms")
        print(f"Realized profit: ${result.realized_profit}")
```

### Custom Risk Management

```python
def custom_risk_alert(alert_type: str, metrics: RiskMetrics):
    """Custom risk alert handler"""
    if alert_type == "CIRCUIT_BREAKER_TRIGGERED":
        print(f"🚨 CIRCUIT BREAKER: {metrics.total_exposure_usd} USD exposure")
        # Send alert to monitoring system
        # Implement custom risk response

async def setup_custom_risk_monitoring():
    risk_manager = RiskManager(
        config=config,
        risk_alert_callback=custom_risk_alert,
    )
    
    await risk_manager.start_monitoring()
    
    # Monitor custom risk metrics
    while True:
        metrics = risk_manager.get_current_risk_metrics()
        if metrics and metrics.total_exposure_usd > Decimal("40000"):
            print(f"⚠️  High exposure warning: ${metrics.total_exposure_usd}")
        
        await asyncio.sleep(1)
```

## Performance Targets

The framework is designed for **ultra-high-performance** with the following targets:

### Execution Performance
- **Complete arbitrage cycle**: <50ms end-to-end
- **Opportunity detection**: <10ms per scan cycle
- **Order placement**: <20ms cross-exchange
- **Risk validation**: <5ms per opportunity
- **Balance queries**: <5ms per exchange
- **State transitions**: <1ms atomic updates

### Reliability Targets
- **Opportunity accuracy**: >99% profitable opportunities
- **Execution success**: >95% successful completions
- **Recovery success**: >95% automated recovery
- **System uptime**: >99.9% availability
- **Data freshness**: <100ms market data age

## HFT Compliance Requirements

### Critical HFT Rules

1. **NO REAL-TIME DATA CACHING**
   ```python
   # ❌ PROHIBITED - Caching real-time trading data
   cached_orderbook = cache.get("orderbook_btc_usdt")
   
   # ✅ REQUIRED - Always fetch fresh data
   orderbook = await exchange.get_orderbook(symbol)  # Fresh data
   ```

2. **ATOMIC OPERATIONS**
   ```python
   # ✅ REQUIRED - Atomic spot + futures coordination
   async with position_manager.atomic_operation():
       spot_position = await place_spot_order()
       futures_hedge = await place_futures_hedge()
       # Both succeed or both fail - no partial positions
   ```

3. **SUB-50MS EXECUTION TARGETS**
   ```python
   # ✅ Performance monitoring and alerting
   if execution_time_ms > 50:
       logger.warning(f"Slow execution: {execution_time_ms}ms")
       # Trigger performance analysis and optimization
   ```

### Data Freshness Validation

```python
def validate_data_freshness(timestamp: int) -> bool:
    """Validate market data is fresh enough for HFT trading"""
    age_ms = current_time_ms() - timestamp
    return age_ms <= 100  # 100ms maximum age for HFT
```

## Integration with Existing Infrastructure

### Exchange Integration

The arbitrage framework integrates seamlessly with the existing exchange infrastructure:

```python
# Use existing exchange interfaces
from exchanges.interface.public import PublicExchangeInterface
from exchanges.interface.private import PrivateExchangeInterface

# Existing MEXC and Gate.io implementations work directly
from exchanges.mexc import MexcPublicExchange, MexcPrivateExchange  
from exchanges.gateio import GateioPublicExchange, GateioPrivateExchange

# No modifications needed - plug and play integration
```

### Error Handling

Uses the unified exception system:

```python
from common.exceptions import (
    ArbitrageEngineError,
    OrderExecutionError, 
    RiskManagementError,
    RecoveryError
)

try:
    await engine.execute_opportunity(opportunity)
except OrderExecutionError as e:
    # Handle execution failures
    logger.error(f"Execution failed: {e}")
    # Recovery procedures automatically initiated
except RiskManagementError as e:
    # Handle risk limit violations  
    logger.warning(f"Risk limits exceeded: {e}")
```

## Configuration

### Environment Variables

```bash
# Risk Management
ARB_MAX_POSITION_SIZE_USD=10000
ARB_MAX_TOTAL_EXPOSURE_USD=50000
ARB_MIN_PROFIT_MARGIN_BPS=50
ARB_MAX_DAILY_LOSS_USD=5000

# Performance Tuning
ARB_TARGET_EXECUTION_TIME_MS=30
ARB_OPPORTUNITY_SCAN_INTERVAL_MS=100
ARB_BALANCE_REFRESH_INTERVAL_MS=1000

# Safety Features
ARB_ENABLE_CIRCUIT_BREAKERS=true
ARB_ENABLE_RISK_CHECKS=true
ARB_ENABLE_RECOVERY_MODE=true
```

### Configuration File

```python
# arbitrage_config.py
from decimal import Decimal

ARBITRAGE_CONFIG = ArbitrageConfig(
    engine_name="production_arbitrage",
    enabled_opportunity_types=[
        OpportunityType.SPOT_SPOT,
        OpportunityType.SPOT_FUTURES_HEDGE,
    ],
    target_execution_time_ms=30,
    risk_limits=RiskLimits(
        max_position_size_usd=Decimal("25000"),
        max_total_exposure_usd=Decimal("100000"),
        min_profit_margin_bps=75,  # 0.75% minimum
    ),
    enable_dry_run=False,  # Set to True for testing
    enable_detailed_logging=True,
)
```

## Monitoring and Alerting

### Performance Metrics

```python
# Engine performance
engine_stats = engine.get_engine_statistics()
print(f"Success rate: {engine_stats['success_rate']}%")
print(f"Avg execution: {engine_stats['average_execution_time_ms']}ms")

# Risk metrics  
risk_stats = risk_manager.get_risk_statistics()
print(f"Circuit breakers: {risk_stats['circuit_breaker_triggers']}")
print(f"Daily P&L: ${risk_stats['daily_realized_pnl']}")

# Recovery statistics
recovery_stats = recovery_manager.get_recovery_statistics()
print(f"Recovery success: {recovery_stats['success_rate']}%")
```

### Health Monitoring

```python
async def health_monitor():
    """Comprehensive system health monitoring"""
    while True:
        health_checks = {
            "engine": engine.is_healthy,
            "risk_manager": risk_manager.is_monitoring,
            "balance_monitor": balance_monitor.is_monitoring,
            "market_data": market_data_aggregator.is_aggregating,
        }
        
        unhealthy_components = [
            component for component, healthy in health_checks.items() 
            if not healthy
        ]
        
        if unhealthy_components:
            logger.critical(f"Unhealthy components: {unhealthy_components}")
            # Trigger alerts and recovery procedures
            
        await asyncio.sleep(30)  # Health check every 30 seconds
```

## Testing and Validation

### Unit Testing

```python
import pytest
from arbitrage import ArbitrageEngine, ArbitrageConfig

@pytest.mark.asyncio
async def test_opportunity_execution():
    """Test basic opportunity execution"""
    engine = create_test_engine()
    opportunity = create_test_opportunity()
    
    result = await engine.execute_opportunity(opportunity)
    
    assert result.final_state == ArbitrageState.COMPLETED
    assert result.total_execution_time_ms < 50
    assert result.realized_profit > 0

@pytest.mark.asyncio
async def test_risk_validation():
    """Test risk management validation"""
    risk_manager = create_test_risk_manager()
    high_risk_opportunity = create_high_risk_opportunity()
    
    is_valid = await risk_manager.validate_opportunity_risk(high_risk_opportunity)
    
    assert not is_valid  # Should reject high-risk opportunity
```

### Integration Testing

```python
@pytest.mark.integration
async def test_full_arbitrage_cycle():
    """Test complete arbitrage cycle with real exchanges"""
    async with create_test_engine().session() as engine:
        # Monitor for opportunities
        opportunities_detected = 0
        
        async def opportunity_handler(opportunity):
            nonlocal opportunities_detected
            opportunities_detected += 1
            
            if opportunities_detected <= 3:  # Test first 3 opportunities
                result = await engine.execute_opportunity(opportunity)
                assert result.final_state in [ArbitrageState.COMPLETED, ArbitrageState.FAILED]
        
        # Run for test duration
        await asyncio.sleep(300)  # 5 minutes
        
        stats = engine.get_engine_statistics()
        assert stats['opportunities_detected'] > 0
```

## Deployment

### Production Deployment

```yaml
# docker-compose.yml
version: '3.8'
services:
  arbitrage-engine:
    build: .
    environment:
      - ARB_MAX_POSITION_SIZE_USD=50000
      - ARB_ENABLE_CIRCUIT_BREAKERS=true
      - ARB_TARGET_EXECUTION_TIME_MS=25
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
    restart: unless-stopped
    
  monitoring:
    image: grafana/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=secure_password
    ports:
      - "3000:3000"
```

### Kubernetes Deployment

```yaml
# arbitrage-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: arbitrage-engine
spec:
  replicas: 1  # Single instance for atomic operations
  selector:
    matchLabels:
      app: arbitrage-engine
  template:
    metadata:
      labels:
        app: arbitrage-engine
    spec:
      containers:
      - name: arbitrage-engine
        image: arbitrage-engine:latest
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi" 
            cpu: "2000m"
        env:
        - name: ARB_ENABLE_CIRCUIT_BREAKERS
          value: "true"
```

## Security Considerations

### API Key Management

```python
# Use secure key management
import os
from cryptography.fernet import Fernet

def get_encrypted_api_key(exchange_name: str) -> str:
    """Retrieve and decrypt API keys securely"""
    encrypted_key = os.environ.get(f"{exchange_name.upper()}_API_KEY_ENCRYPTED")
    encryption_key = os.environ.get("ENCRYPTION_KEY")
    
    fernet = Fernet(encryption_key.encode())
    return fernet.decrypt(encrypted_key.encode()).decode()
```

### Network Security

```python
# Use VPN and secure connections
EXCHANGE_ENDPOINTS = {
    ExchangeName.MEXC: {
        "rest_url": "https://api.mexc.com",
        "websocket_url": "wss://wbs.mexc.com/ws",
        "verify_ssl": True,
        "timeout": 5.0,
    }
}
```

## Performance Optimization

### Memory Management

```python
# Object pooling for high-frequency operations
from collections import deque

class OrderPool:
    """Object pool for order instances"""
    def __init__(self, size: int = 1000):
        self._pool = deque()
        for _ in range(size):
            self._pool.append(Order(...))  # Pre-allocate orders
    
    def get_order(self) -> Order:
        return self._pool.popleft() if self._pool else Order(...)
    
    def return_order(self, order: Order):
        order.reset()  # Clear order data
        self._pool.append(order)
```

### Connection Optimization

```python
# Connection pooling and keep-alive
import aiohttp

async def create_optimized_session() -> aiohttp.ClientSession:
    """Create optimized HTTP session for trading"""
    connector = aiohttp.TCPConnector(
        limit=100,  # Connection pool size
        limit_per_host=50,
        keepalive_timeout=30,
        enable_cleanup_closed=True,
    )
    
    timeout = aiohttp.ClientTimeout(
        total=5,      # 5 second total timeout
        connect=1,    # 1 second connection timeout  
        sock_read=2,  # 2 second read timeout
    )
    
    return aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        raise_for_status=True,
    )
```

## Troubleshooting

### Common Issues

1. **High Execution Latency**
   ```python
   # Check network latency
   async def diagnose_latency():
       for exchange in exchanges:
           start_time = time.time()
           await exchange.ping()
           latency = (time.time() - start_time) * 1000
           print(f"{exchange}: {latency:.1f}ms")
   ```

2. **Circuit Breaker Triggers**
   ```python
   # Check risk limits and market conditions
   risk_status = risk_manager.get_circuit_breaker_status()
   if risk_status.triggered_breakers:
       print(f"Triggered: {risk_status.triggered_breakers}")
       # Adjust risk limits or wait for market stability
   ```

3. **Recovery Failures**
   ```python
   # Monitor recovery operations
   active_recoveries = recovery_manager.get_active_recoveries()
   for recovery in active_recoveries:
       if recovery.requires_manual_approval:
           print(f"Manual intervention needed: {recovery.recovery_id}")
   ```

### Debug Mode

```python
# Enable comprehensive debugging
import logging

logging.basicConfig(level=logging.DEBUG)

config = ArbitrageConfig(
    enable_detailed_logging=True,
    enable_dry_run=True,  # Paper trading mode
    enable_performance_metrics=True,
)
```

## Contributing

### Development Setup

```bash
# Clone repository
git clone https://github.com/your-org/cex_arbitrage
cd cex_arbitrage

# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest src/arbitrage/tests/

# Run type checking
mypy src/arbitrage/

# Run code formatting
black src/arbitrage/
isort src/arbitrage/
```

### Code Standards

- Follow existing project patterns and HFT compliance requirements
- Use msgspec.Struct for all data structures
- Maintain sub-50ms performance targets
- Include comprehensive TODO comments for implementation
- Follow SOLID principles and Abstract Factory patterns
- Never cache real-time trading data (HFT requirement)

---

**⚠️ Important**: This arbitrage framework is designed for professional high-frequency trading operations. Ensure proper risk management, regulatory compliance, and thorough testing before production deployment.

**🚨 HFT Compliance**: Always maintain HFT compliance requirements - never cache real-time trading data, maintain atomic operations, and ensure sub-50ms execution targets.