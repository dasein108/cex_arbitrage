# TASK 1.2: Data Collector Decomposition

**Phase**: 1 - Critical File Decomposition  
**Stage**: 1.2  
**Priority**: CRITICAL  
**Estimated Duration**: 3 Days  
**Risk Level**: MEDIUM  

---

## 🎯 **Task Overview**

Decompose the monolithic `collector.py` (1,086 lines) into specialized, focused modules while maintaining the HFT performance requirements and real-time data processing capabilities.

---

## 📊 **Current State Analysis**

### **Problem**:
- **File Size**: 1,086 lines (exceeds 500-line limit by 117%)
- **Responsibilities**: WebSocket management, scheduling, caching, analytics, health monitoring
- **Performance Risk**: Critical path for HFT message processing
- **Complexity**: High coupling between data collection and analysis logic

### **Target State**:
```
src/applications/data_collection/
├── collector.py (200 lines - orchestrator)
├── websocket/
│   ├── unified_manager.py (400 lines - WebSocket management)
│   └── connection_monitor.py (200 lines - health monitoring)  
├── scheduling/
│   └── snapshot_scheduler.py (250 lines - scheduling logic)
├── caching/
│   └── cache_manager.py (200 lines - caching and persistence)
└── analytics/
    └── real_time_processor.py (150 lines - real-time analytics)
```

---

## 🔍 **Detailed Analysis**

### **Current Responsibilities in collector.py**:
1. **WebSocket Management** (Lines ~150-500)
   - Connection initialization
   - Message routing and handling
   - Reconnection logic
   - Health monitoring

2. **Data Processing** (Lines ~501-700)
   - Real-time analytics
   - Orderbook aggregation
   - Trade analysis
   - Arbitrage detection triggers

3. **Caching & Persistence** (Lines ~701-850)
   - In-memory caching
   - Database operations
   - Cache invalidation
   - Snapshot management

4. **Scheduling** (Lines ~851-950)
   - Periodic snapshots
   - Health checks
   - Analytics reporting
   - Cleanup operations

5. **Orchestration** (Lines ~1-149, 951-1086)
   - Component coordination
   - Lifecycle management
   - Configuration handling
   - External API

---

## 📝 **Implementation Plan**

### **Step 1: Extract WebSocket Management** (8 hours)

#### **1.1 Create unified_manager.py**:
```python
# src/applications/data_collection/websocket/unified_manager.py
from typing import Dict, List, Optional, Callable, Any
import asyncio
from dataclasses import dataclass

from exchanges import ExchangeEnum
from exchanges.structs.common import Symbol, OrderBook, Trade, BookTicker
from infrastructure.logging import HFTLoggerInterface, get_logger
from infrastructure.networking.websocket.structs import PublicWebsocketHandlers

@dataclass
class WebSocketConnectionState:
    """State tracking for individual WebSocket connections."""
    exchange: ExchangeEnum
    symbols: List[Symbol]
    connected: bool = False
    last_message_time: float = 0
    message_count: int = 0
    error_count: int = 0
    reconnect_attempts: int = 0

class UnifiedWebSocketManager:
    """
    Centralized WebSocket connection management for all exchanges.
    
    Handles connection lifecycle, message routing, and health monitoring
    for real-time data collection across multiple exchanges.
    """
    
    def __init__(self, 
                 handlers: PublicWebsocketHandlers, 
                 logger: Optional[HFTLoggerInterface] = None):
        """Initialize WebSocket manager with message handlers."""
        self.handlers = handlers
        self.logger = logger or get_logger('websocket.unified_manager')
        
        # Connection state tracking
        self._connections: Dict[ExchangeEnum, WebSocketConnectionState] = {}
        self._exchange_clients: Dict[ExchangeEnum, Any] = {}
        self._reconnection_tasks: Dict[ExchangeEnum, asyncio.Task] = {}
        
        # Performance monitoring
        self._message_processing_times: Dict[ExchangeEnum, List[float]] = {}
        self._health_check_interval = 30  # seconds
        self._health_monitor_task: Optional[asyncio.Task] = None
        
        # Configuration
        self._max_reconnect_attempts = 5
        self._reconnect_delay_base = 1  # seconds (exponential backoff)
        self._message_timeout = 60  # seconds
        
        self.logger.info("UnifiedWebSocketManager initialized",
                        max_reconnect_attempts=self._max_reconnect_attempts)
    
    async def initialize_exchange_client(self, 
                                       exchange: ExchangeEnum, 
                                       symbols: List[Symbol]) -> None:
        """Initialize WebSocket client for specific exchange."""
        start_time = time.perf_counter()
        
        try:
            self.logger.info(f"Initializing {exchange.value} WebSocket client",
                           exchange=exchange.value,
                           symbol_count=len(symbols))
            
            # Track connection state
            self._connections[exchange] = WebSocketConnectionState(
                exchange=exchange,
                symbols=symbols
            )
            
            # Create exchange-specific client
            client = await self._create_exchange_client(exchange, symbols)
            self._exchange_clients[exchange] = client
            
            # Set up message handlers
            await self._setup_message_handlers(exchange, client)
            
            # Start connection
            await client.start()
            self._connections[exchange].connected = True
            
            init_time = (time.perf_counter() - start_time) * 1000
            self.logger.info(f"{exchange.value} WebSocket client initialized",
                           exchange=exchange.value,
                           initialization_time_ms=init_time)
            
            # Track performance metric
            self.logger.metric("websocket_initialization_time_ms", init_time,
                             tags={"exchange": exchange.value})
            
        except Exception as e:
            self.logger.error(f"Failed to initialize {exchange.value} WebSocket client: {e}",
                            exchange=exchange.value,
                            error=str(e))
            raise
    
    async def _create_exchange_client(self, exchange: ExchangeEnum, symbols: List[Symbol]):
        """Create exchange-specific WebSocket client."""
        if exchange == ExchangeEnum.MEXC:
            from exchanges.integrations.mexc.public_exchange import MexcPublicCompositePublicExchange
            return MexcPublicCompositePublicExchange(
                symbols=symbols,
                logger=self.logger.create_child(f"mexc.public")
            )
        elif exchange == ExchangeEnum.GATEIO:
            from exchanges.integrations.gateio.public_exchange import GateioPublicCompositePublicExchange
            return GateioPublicCompositePublicExchange(
                symbols=symbols,
                logger=self.logger.create_child(f"gateio.public")
            )
        else:
            raise ValueError(f"Unsupported exchange: {exchange}")
    
    async def _setup_message_handlers(self, exchange: ExchangeEnum, client) -> None:
        """Set up message handlers for exchange client."""
        # Create exchange-specific handler wrappers
        orderbook_handler = self._create_orderbook_handler(exchange)
        trade_handler = self._create_trade_handler(exchange)
        book_ticker_handler = self._create_book_ticker_handler(exchange)
        
        # Register handlers with client
        await client.set_message_handlers(
            on_orderbook=orderbook_handler,
            on_trade=trade_handler,
            on_book_ticker=book_ticker_handler
        )
    
    def _create_orderbook_handler(self, exchange: ExchangeEnum) -> Callable:
        """Create orderbook message handler for specific exchange."""
        async def handler(symbol: Symbol, orderbook: OrderBook) -> None:
            start_time = time.perf_counter()
            
            try:
                # Update connection state
                self._update_message_stats(exchange)
                
                # Call external handler
                await self.handlers.on_orderbook(exchange, symbol, orderbook)
                
                # Track processing time
                processing_time = (time.perf_counter() - start_time) * 1000
                self._track_processing_time(exchange, processing_time)
                
            except Exception as e:
                self.logger.error(f"Error in orderbook handler: {e}",
                                exchange=exchange.value,
                                symbol=str(symbol),
                                error=str(e))
                self._connections[exchange].error_count += 1
        
        return handler
    
    def _create_trade_handler(self, exchange: ExchangeEnum) -> Callable:
        """Create trade message handler for specific exchange."""
        async def handler(symbol: Symbol, trade: Trade) -> None:
            start_time = time.perf_counter()
            
            try:
                # Update connection state
                self._update_message_stats(exchange)
                
                # Call external handler
                await self.handlers.on_trade(exchange, symbol, trade)
                
                # Track processing time
                processing_time = (time.perf_counter() - start_time) * 1000
                self._track_processing_time(exchange, processing_time)
                
            except Exception as e:
                self.logger.error(f"Error in trade handler: {e}",
                                exchange=exchange.value,
                                symbol=str(symbol),
                                error=str(e))
                self._connections[exchange].error_count += 1
        
        return handler
    
    def _create_book_ticker_handler(self, exchange: ExchangeEnum) -> Callable:
        """Create book ticker message handler for specific exchange."""
        async def handler(symbol: Symbol, book_ticker: BookTicker) -> None:
            start_time = time.perf_counter()
            
            try:
                # Update connection state
                self._update_message_stats(exchange)
                
                # Call external handler
                await self.handlers.on_book_ticker(exchange, symbol, book_ticker)
                
                # Track processing time
                processing_time = (time.perf_counter() - start_time) * 1000
                self._track_processing_time(exchange, processing_time)
                
            except Exception as e:
                self.logger.error(f"Error in book ticker handler: {e}",
                                exchange=exchange.value,
                                symbol=str(symbol),
                                error=str(e))
                self._connections[exchange].error_count += 1
        
        return handler
    
    def _update_message_stats(self, exchange: ExchangeEnum) -> None:
        """Update message statistics for exchange."""
        import time
        connection = self._connections[exchange]
        connection.last_message_time = time.time()
        connection.message_count += 1
    
    def _track_processing_time(self, exchange: ExchangeEnum, processing_time: float) -> None:
        """Track message processing time for performance monitoring."""
        if exchange not in self._message_processing_times:
            self._message_processing_times[exchange] = []
        
        times = self._message_processing_times[exchange]
        times.append(processing_time)
        
        # Keep only recent measurements (last 1000)
        if len(times) > 1000:
            times.pop(0)
        
        # Log performance metrics periodically
        if len(times) % 100 == 0:
            avg_time = sum(times[-100:]) / 100
            self.logger.metric("websocket_processing_time_ms", avg_time,
                             tags={"exchange": exchange.value, "metric": "avg_100"})
    
    async def start_health_monitoring(self) -> None:
        """Start health monitoring for all connections."""
        if self._health_monitor_task:
            return
        
        self._health_monitor_task = asyncio.create_task(self._health_monitor_loop())
        self.logger.info("Health monitoring started",
                        check_interval=self._health_check_interval)
    
    async def _health_monitor_loop(self) -> None:
        """Main health monitoring loop."""
        while True:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self._health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in health monitoring: {e}", error=str(e))
                await asyncio.sleep(5)  # Short delay before retry
    
    async def _perform_health_checks(self) -> None:
        """Perform health checks on all connections."""
        import time
        current_time = time.time()
        
        for exchange, connection in self._connections.items():
            if not connection.connected:
                continue
            
            # Check for message timeout
            time_since_last_message = current_time - connection.last_message_time
            if time_since_last_message > self._message_timeout:
                self.logger.warning(f"{exchange.value} connection appears stale",
                                  exchange=exchange.value,
                                  seconds_since_last_message=time_since_last_message)
                
                # Trigger reconnection
                await self._reconnect_exchange(exchange)
            
            # Log health metrics
            self.logger.metric("websocket_messages_received", connection.message_count,
                             tags={"exchange": exchange.value})
            self.logger.metric("websocket_errors", connection.error_count,
                             tags={"exchange": exchange.value})
    
    async def _reconnect_exchange(self, exchange: ExchangeEnum) -> None:
        """Reconnect specific exchange WebSocket."""
        connection = self._connections.get(exchange)
        if not connection:
            return
        
        # Cancel existing reconnection task if running
        if exchange in self._reconnection_tasks:
            self._reconnection_tasks[exchange].cancel()
        
        # Start reconnection task
        self._reconnection_tasks[exchange] = asyncio.create_task(
            self._reconnection_loop(exchange)
        )
    
    async def _reconnection_loop(self, exchange: ExchangeEnum) -> None:
        """Handle reconnection with exponential backoff."""
        connection = self._connections[exchange]
        
        for attempt in range(self._max_reconnect_attempts):
            try:
                self.logger.info(f"Reconnection attempt {attempt + 1} for {exchange.value}",
                               exchange=exchange.value,
                               attempt=attempt + 1,
                               max_attempts=self._max_reconnect_attempts)
                
                # Close existing connection
                if exchange in self._exchange_clients:
                    await self._exchange_clients[exchange].close()
                
                # Wait with exponential backoff
                delay = self._reconnect_delay_base * (2 ** attempt)
                await asyncio.sleep(delay)
                
                # Reinitialize connection
                await self.initialize_exchange_client(exchange, connection.symbols)
                
                self.logger.info(f"{exchange.value} reconnection successful",
                               exchange=exchange.value,
                               attempt=attempt + 1)
                connection.reconnect_attempts = 0
                return
                
            except Exception as e:
                connection.reconnect_attempts += 1
                self.logger.error(f"Reconnection attempt {attempt + 1} failed for {exchange.value}: {e}",
                                exchange=exchange.value,
                                attempt=attempt + 1,
                                error=str(e))
        
        # All reconnection attempts failed
        self.logger.error(f"All reconnection attempts failed for {exchange.value}",
                        exchange=exchange.value,
                        total_attempts=self._max_reconnect_attempts)
        connection.connected = False
    
    def get_connection_status(self) -> Dict[ExchangeEnum, Dict[str, Any]]:
        """Get current connection status for all exchanges."""
        status = {}
        
        for exchange, connection in self._connections.items():
            # Calculate average processing time
            avg_processing_time = 0
            if exchange in self._message_processing_times:
                times = self._message_processing_times[exchange]
                if times:
                    avg_processing_time = sum(times) / len(times)
            
            status[exchange] = {
                "connected": connection.connected,
                "symbols": len(connection.symbols),
                "messages_received": connection.message_count,
                "errors": connection.error_count,
                "reconnect_attempts": connection.reconnect_attempts,
                "avg_processing_time_ms": round(avg_processing_time, 3),
                "last_message_ago_seconds": time.time() - connection.last_message_time
            }
        
        return status
    
    async def close_all_connections(self) -> None:
        """Close all WebSocket connections and cleanup resources."""
        self.logger.info("Closing all WebSocket connections")
        
        # Stop health monitoring
        if self._health_monitor_task:
            self._health_monitor_task.cancel()
            try:
                await self._health_monitor_task
            except asyncio.CancelledError:
                pass
        
        # Cancel reconnection tasks
        for task in self._reconnection_tasks.values():
            task.cancel()
        
        # Close all connections
        for exchange, client in self._exchange_clients.items():
            try:
                await client.close()
                self._connections[exchange].connected = False
            except Exception as e:
                self.logger.error(f"Error closing {exchange.value} connection: {e}")
        
        self.logger.info("All WebSocket connections closed")
```

#### **1.2 Create connection_monitor.py**:
```python
# src/applications/data_collection/websocket/connection_monitor.py
from typing import Dict, Any, Optional, List
import asyncio
import time
from dataclasses import dataclass

from exchanges import ExchangeEnum
from infrastructure.logging import HFTLoggerInterface, get_logger

@dataclass
class ConnectionHealth:
    """Health metrics for a WebSocket connection."""
    exchange: ExchangeEnum
    is_healthy: bool
    last_message_time: float
    messages_per_minute: float
    error_rate: float
    latency_ms: float
    uptime_percentage: float
    issues: List[str]

class ConnectionMonitor:
    """
    Advanced health monitoring and alerting for WebSocket connections.
    
    Tracks connection health, performance metrics, and triggers
    alerts/recovery actions based on configurable thresholds.
    """
    
    def __init__(self, logger: Optional[HFTLoggerInterface] = None):
        """Initialize connection monitor."""
        self.logger = logger or get_logger('websocket.connection_monitor')
        
        # Health thresholds
        self._message_timeout_seconds = 60
        self._min_messages_per_minute = 10
        self._max_error_rate = 0.05  # 5%
        self._max_latency_ms = 1000
        self._min_uptime_percentage = 95.0
        
        # Monitoring data
        self._connection_metrics: Dict[ExchangeEnum, Dict[str, Any]] = {}
        self._health_history: Dict[ExchangeEnum, List[ConnectionHealth]] = {}
        self._monitoring_task: Optional[asyncio.Task] = None
        
        # Alerts
        self._alert_callbacks: List[callable] = []
        self._last_alert_time: Dict[str, float] = {}
        self._alert_cooldown_seconds = 300  # 5 minutes
        
        self.logger.info("ConnectionMonitor initialized")
    
    def start_monitoring(self, check_interval: int = 30) -> None:
        """Start continuous health monitoring."""
        if self._monitoring_task:
            return
        
        self._monitoring_task = asyncio.create_task(
            self._monitoring_loop(check_interval)
        )
        self.logger.info("Connection monitoring started",
                        check_interval=check_interval)
    
    async def _monitoring_loop(self, check_interval: int) -> None:
        """Main monitoring loop."""
        while True:
            try:
                await self._perform_health_assessment()
                await asyncio.sleep(check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)
    
    def update_connection_metrics(self, 
                                exchange: ExchangeEnum,
                                message_count: int,
                                error_count: int,
                                last_message_time: float,
                                connected: bool) -> None:
        """Update metrics for specific connection."""
        current_time = time.time()
        
        if exchange not in self._connection_metrics:
            self._connection_metrics[exchange] = {
                'start_time': current_time,
                'total_downtime': 0,
                'last_disconnect_time': None
            }
        
        metrics = self._connection_metrics[exchange]
        
        # Update basic metrics
        metrics.update({
            'message_count': message_count,
            'error_count': error_count,
            'last_message_time': last_message_time,
            'connected': connected,
            'last_update_time': current_time
        })
        
        # Track downtime
        if not connected and metrics.get('last_disconnect_time') is None:
            metrics['last_disconnect_time'] = current_time
        elif connected and metrics.get('last_disconnect_time'):
            downtime = current_time - metrics['last_disconnect_time']
            metrics['total_downtime'] += downtime
            metrics['last_disconnect_time'] = None
    
    async def _perform_health_assessment(self) -> None:
        """Assess health of all monitored connections."""
        current_time = time.time()
        
        for exchange, metrics in self._connection_metrics.items():
            health = await self._assess_connection_health(exchange, metrics, current_time)
            
            # Store health history
            if exchange not in self._health_history:
                self._health_history[exchange] = []
            
            self._health_history[exchange].append(health)
            
            # Keep only recent history (last 24 hours = 2880 checks at 30s intervals)
            if len(self._health_history[exchange]) > 2880:
                self._health_history[exchange].pop(0)
            
            # Log health status
            self._log_health_status(health)
            
            # Trigger alerts if needed
            if not health.is_healthy:
                await self._trigger_health_alert(health)
    
    async def _assess_connection_health(self, 
                                     exchange: ExchangeEnum,
                                     metrics: Dict[str, Any],
                                     current_time: float) -> ConnectionHealth:
        """Assess health of individual connection."""
        issues = []
        is_healthy = True
        
        # Check if connected
        if not metrics.get('connected', False):
            issues.append("Connection is down")
            is_healthy = False
        
        # Check message recency
        last_message_time = metrics.get('last_message_time', 0)
        time_since_last_message = current_time - last_message_time
        if time_since_last_message > self._message_timeout_seconds:
            issues.append(f"No messages for {time_since_last_message:.1f}s")
            is_healthy = False
        
        # Calculate messages per minute
        start_time = metrics.get('start_time', current_time)
        runtime_minutes = max((current_time - start_time) / 60, 1)
        message_count = metrics.get('message_count', 0)
        messages_per_minute = message_count / runtime_minutes
        
        if messages_per_minute < self._min_messages_per_minute:
            issues.append(f"Low message rate: {messages_per_minute:.1f}/min")
            is_healthy = False
        
        # Calculate error rate
        error_count = metrics.get('error_count', 0)
        error_rate = error_count / max(message_count, 1)
        if error_rate > self._max_error_rate:
            issues.append(f"High error rate: {error_rate*100:.1f}%")
            is_healthy = False
        
        # Calculate uptime percentage
        total_downtime = metrics.get('total_downtime', 0)
        if metrics.get('last_disconnect_time'):
            total_downtime += current_time - metrics['last_disconnect_time']
        
        total_runtime = current_time - start_time
        uptime_percentage = max(0, (total_runtime - total_downtime) / total_runtime * 100)
        
        if uptime_percentage < self._min_uptime_percentage:
            issues.append(f"Low uptime: {uptime_percentage:.1f}%")
            is_healthy = False
        
        # Estimate latency (simplified - would need actual ping measurements)
        # For now, use processing time as proxy
        latency_ms = 0  # Would be calculated from actual measurements
        
        return ConnectionHealth(
            exchange=exchange,
            is_healthy=is_healthy,
            last_message_time=last_message_time,
            messages_per_minute=messages_per_minute,
            error_rate=error_rate,
            latency_ms=latency_ms,
            uptime_percentage=uptime_percentage,
            issues=issues
        )
    
    def _log_health_status(self, health: ConnectionHealth) -> None:
        """Log connection health status."""
        status = "HEALTHY" if health.is_healthy else "UNHEALTHY"
        
        log_data = {
            "exchange": health.exchange.value,
            "status": status,
            "messages_per_minute": health.messages_per_minute,
            "error_rate_percent": health.error_rate * 100,
            "uptime_percent": health.uptime_percentage
        }
        
        if health.is_healthy:
            self.logger.debug(f"{health.exchange.value} connection healthy", **log_data)
        else:
            self.logger.warning(f"{health.exchange.value} connection unhealthy: {', '.join(health.issues)}", 
                              issues=health.issues, **log_data)
        
        # Log metrics
        self.logger.metric("websocket_health_score", 1 if health.is_healthy else 0,
                         tags={"exchange": health.exchange.value})
        self.logger.metric("websocket_messages_per_minute", health.messages_per_minute,
                         tags={"exchange": health.exchange.value})
        self.logger.metric("websocket_error_rate", health.error_rate,
                         tags={"exchange": health.exchange.value})
        self.logger.metric("websocket_uptime_percent", health.uptime_percentage,
                         tags={"exchange": health.exchange.value})
    
    async def _trigger_health_alert(self, health: ConnectionHealth) -> None:
        """Trigger alert for unhealthy connection."""
        alert_key = f"{health.exchange.value}_unhealthy"
        current_time = time.time()
        
        # Check cooldown
        last_alert = self._last_alert_time.get(alert_key, 0)
        if current_time - last_alert < self._alert_cooldown_seconds:
            return
        
        self._last_alert_time[alert_key] = current_time
        
        alert_data = {
            "type": "connection_health",
            "exchange": health.exchange.value,
            "issues": health.issues,
            "metrics": {
                "messages_per_minute": health.messages_per_minute,
                "error_rate": health.error_rate,
                "uptime_percentage": health.uptime_percentage
            }
        }
        
        # Call alert callbacks
        for callback in self._alert_callbacks:
            try:
                await callback(alert_data)
            except Exception as e:
                self.logger.error(f"Error in alert callback: {e}")
        
        self.logger.error(f"ALERT: {health.exchange.value} connection is unhealthy",
                        alert_data=alert_data)
    
    def add_alert_callback(self, callback: callable) -> None:
        """Add callback function for health alerts."""
        self._alert_callbacks.append(callback)
    
    def get_health_summary(self) -> Dict[ExchangeEnum, Dict[str, Any]]:
        """Get current health summary for all connections."""
        summary = {}
        current_time = time.time()
        
        for exchange in self._connection_metrics.keys():
            if exchange in self._health_history and self._health_history[exchange]:
                latest_health = self._health_history[exchange][-1]
                
                # Calculate recent trend (last 10 checks)
                recent_checks = self._health_history[exchange][-10:]
                healthy_count = sum(1 for h in recent_checks if h.is_healthy)
                health_trend = healthy_count / len(recent_checks) * 100
                
                summary[exchange] = {
                    "is_healthy": latest_health.is_healthy,
                    "issues": latest_health.issues,
                    "messages_per_minute": latest_health.messages_per_minute,
                    "error_rate": latest_health.error_rate,
                    "uptime_percentage": latest_health.uptime_percentage,
                    "health_trend_10checks": health_trend,
                    "last_check_time": latest_health.last_message_time
                }
        
        return summary
    
    async def stop_monitoring(self) -> None:
        """Stop health monitoring."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
        
        self.logger.info("Connection monitoring stopped")
```

### **Step 2: Extract Scheduling Logic** (4 hours)

#### **2.1 Create snapshot_scheduler.py**:
```python
# src/applications/data_collection/scheduling/snapshot_scheduler.py
from typing import Optional, Dict, Any, Callable, List
import asyncio
from datetime import datetime, timedelta
from dataclasses import dataclass

from infrastructure.logging import HFTLoggerInterface, get_logger

@dataclass
class ScheduledTask:
    """Configuration for a scheduled task."""
    name: str
    interval_seconds: int
    callback: Callable
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    error_count: int = 0

class SnapshotScheduler:
    """
    Manages periodic tasks for data collection system.
    
    Handles snapshot creation, health checks, analytics reporting,
    and other scheduled maintenance operations.
    """
    
    def __init__(self, 
                 snapshot_interval: int = 30,
                 logger: Optional[HFTLoggerInterface] = None):
        """Initialize scheduler with default snapshot interval."""
        self.logger = logger or get_logger('data_collection.scheduler')
        
        # Core settings
        self.snapshot_interval = snapshot_interval
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        
        # Task management
        self._scheduled_tasks: Dict[str, ScheduledTask] = {}
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._worker_tasks: List[asyncio.Task] = []
        self._max_workers = 3
        
        # Performance tracking
        self._total_tasks_executed = 0
        self._total_task_errors = 0
        
        self.logger.info("SnapshotScheduler initialized",
                        snapshot_interval=snapshot_interval,
                        max_workers=self._max_workers)
    
    def add_task(self, 
                 name: str, 
                 interval_seconds: int, 
                 callback: Callable,
                 enabled: bool = True) -> None:
        """Add a scheduled task."""
        task = ScheduledTask(
            name=name,
            interval_seconds=interval_seconds,
            callback=callback,
            enabled=enabled,
            next_run=datetime.now() + timedelta(seconds=interval_seconds)
        )
        
        self._scheduled_tasks[name] = task
        
        self.logger.info(f"Added scheduled task: {name}",
                        task_name=name,
                        interval=interval_seconds,
                        enabled=enabled)
    
    def remove_task(self, name: str) -> bool:
        """Remove a scheduled task."""
        if name in self._scheduled_tasks:
            del self._scheduled_tasks[name]
            self.logger.info(f"Removed scheduled task: {name}", task_name=name)
            return True
        return False
    
    def enable_task(self, name: str) -> bool:
        """Enable a scheduled task."""
        if name in self._scheduled_tasks:
            self._scheduled_tasks[name].enabled = True
            self.logger.info(f"Enabled scheduled task: {name}", task_name=name)
            return True
        return False
    
    def disable_task(self, name: str) -> bool:
        """Disable a scheduled task."""
        if name in self._scheduled_tasks:
            self._scheduled_tasks[name].enabled = False
            self.logger.info(f"Disabled scheduled task: {name}", task_name=name)
            return True
        return False
    
    async def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            return
        
        self._running = True
        
        # Start scheduler task
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        
        # Start worker tasks
        for i in range(self._max_workers):
            worker_task = asyncio.create_task(self._worker_loop(f"worker-{i}"))
            self._worker_tasks.append(worker_task)
        
        self.logger.info("Scheduler started",
                        worker_count=len(self._worker_tasks),
                        task_count=len(self._scheduled_tasks))
    
    async def stop(self) -> None:
        """Stop the scheduler."""
        if not self._running:
            return
        
        self._running = False
        
        # Cancel scheduler task
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        
        # Cancel worker tasks
        for worker_task in self._worker_tasks:
            worker_task.cancel()
        
        # Wait for workers to finish
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        
        self._worker_tasks.clear()
        
        self.logger.info("Scheduler stopped",
                        total_tasks_executed=self._total_tasks_executed,
                        total_errors=self._total_task_errors)
    
    async def _scheduler_loop(self) -> None:
        """Main scheduler loop - checks for due tasks."""
        while self._running:
            try:
                await self._check_and_queue_due_tasks()
                await asyncio.sleep(1)  # Check every second
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in scheduler loop: {e}")
                await asyncio.sleep(5)
    
    async def _check_and_queue_due_tasks(self) -> None:
        """Check for tasks that are due and queue them for execution."""
        current_time = datetime.now()
        
        for task_name, task in self._scheduled_tasks.items():
            if not task.enabled:
                continue
            
            if task.next_run and current_time >= task.next_run:
                # Queue task for execution
                await self._task_queue.put((task_name, task))
                
                # Schedule next run
                task.next_run = current_time + timedelta(seconds=task.interval_seconds)
                
                self.logger.debug(f"Queued task for execution: {task_name}",
                                task_name=task_name,
                                next_run=task.next_run.isoformat())
    
    async def _worker_loop(self, worker_name: str) -> None:
        """Worker loop - executes queued tasks."""
        self.logger.info(f"Worker {worker_name} started")
        
        while self._running:
            try:
                # Get task from queue with timeout
                task_name, task = await asyncio.wait_for(
                    self._task_queue.get(), 
                    timeout=1.0
                )
                
                # Execute task
                await self._execute_task(task_name, task, worker_name)
                
            except asyncio.TimeoutError:
                # No tasks available, continue
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in worker {worker_name}: {e}")
        
        self.logger.info(f"Worker {worker_name} stopped")
    
    async def _execute_task(self, task_name: str, task: ScheduledTask, worker_name: str) -> None:
        """Execute a single task."""
        start_time = datetime.now()
        
        try:
            self.logger.debug(f"Executing task: {task_name}",
                            task_name=task_name,
                            worker=worker_name,
                            run_count=task.run_count + 1)
            
            # Execute the task callback
            if asyncio.iscoroutinefunction(task.callback):
                await task.callback()
            else:
                task.callback()
            
            # Update task statistics
            task.last_run = start_time
            task.run_count += 1
            self._total_tasks_executed += 1
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            self.logger.debug(f"Task completed: {task_name}",
                            task_name=task_name,
                            execution_time=execution_time,
                            worker=worker_name)
            
            # Log performance metrics
            self.logger.metric("scheduled_task_execution_time", execution_time,
                             tags={"task_name": task_name, "worker": worker_name})
            
        except Exception as e:
            task.error_count += 1
            self._total_task_errors += 1
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            self.logger.error(f"Task failed: {task_name}: {e}",
                            task_name=task_name,
                            error=str(e),
                            worker=worker_name,
                            execution_time=execution_time)
            
            # Log error metrics
            self.logger.metric("scheduled_task_errors", 1,
                             tags={"task_name": task_name, "error_type": type(e).__name__})
    
    def get_task_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all scheduled tasks."""
        status = {}
        current_time = datetime.now()
        
        for task_name, task in self._scheduled_tasks.items():
            next_run_in = None
            if task.next_run:
                next_run_delta = task.next_run - current_time
                next_run_in = max(0, next_run_delta.total_seconds())
            
            status[task_name] = {
                "enabled": task.enabled,
                "interval_seconds": task.interval_seconds,
                "run_count": task.run_count,
                "error_count": task.error_count,
                "last_run": task.last_run.isoformat() if task.last_run else None,
                "next_run": task.next_run.isoformat() if task.next_run else None,
                "next_run_in_seconds": next_run_in,
                "error_rate": task.error_count / max(task.run_count, 1)
            }
        
        return status
    
    def get_scheduler_status(self) -> Dict[str, Any]:
        """Get overall scheduler status."""
        return {
            "running": self._running,
            "total_tasks": len(self._scheduled_tasks),
            "enabled_tasks": sum(1 for t in self._scheduled_tasks.values() if t.enabled),
            "worker_count": len(self._worker_tasks),
            "queue_size": self._task_queue.qsize(),
            "total_executions": self._total_tasks_executed,
            "total_errors": self._total_task_errors,
            "overall_error_rate": self._total_task_errors / max(self._total_tasks_executed, 1)
        }
    
    async def run_task_now(self, task_name: str) -> bool:
        """Manually trigger a task to run immediately."""
        if task_name not in self._scheduled_tasks:
            return False
        
        task = self._scheduled_tasks[task_name]
        if not task.enabled:
            return False
        
        # Queue task for immediate execution
        await self._task_queue.put((task_name, task))
        
        self.logger.info(f"Manually triggered task: {task_name}", task_name=task_name)
        return True
```

### **Step 3: Extract Caching Logic** (3 hours)

I'll continue with the remaining implementation steps to complete the Data Collector Decomposition task. Would you like me to continue with the caching logic and the final orchestrator refactoring?