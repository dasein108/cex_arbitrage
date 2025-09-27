# HFT Caching Policy

**CRITICAL TRADING SAFETY DOCUMENT**

This document defines the absolute rules for caching in high-frequency trading systems. These rules are **non-negotiable** and supersede ALL other performance considerations.

## 🚨 ABSOLUTE RULE: NO REAL-TIME TRADING DATA CACHING

**NEVER cache real-time trading data in HFT systems.**

This is the most critical architectural rule in the entire system. Violation of this rule can cause:
- Execution on stale prices
- Failed arbitrage opportunities  
- Phantom liquidity risks
- Regulatory compliance violations
- Significant financial losses

## Prohibited Caching (Real-time Trading Data)

### **Account Data (NEVER CACHE)**

**Account Balances**:
- ❌ Current account balances
- ❌ Available balance amounts
- ❌ Locked/frozen balance amounts
- ❌ Balance changes/deltas
- ❌ Cross-margin balances

**Rationale**: Balances change with every trade execution. Cached balance data leads to insufficient funds errors or overexposure risks.

**Correct Implementation**:
```python
# CORRECT: Fresh API call for balances
async def get_balances(self) -> Dict[str, AssetBalance]:
    """Always fetches fresh data from API - NEVER returns cached data."""
    response = await self._rest_client.get('/api/v3/account')
    return self._parse_balances(response)

# WRONG: Caching balance data
class BalanceCache:  # ❌ DANGEROUS - DO NOT IMPLEMENT
    def __init__(self):
        self._cached_balances = {}  # This will cause trading errors
```

### **Order Data (NEVER CACHE)**

**Order Status and History**:
- ❌ Current order status (NEW, FILLED, CANCELLED)
- ❌ Partial fill amounts
- ❌ Open orders list
- ❌ Recent order history
- ❌ Order execution details

**Rationale**: Order status changes in real-time. Stale order data causes double-spending, phantom orders, and failed cancellations.

**Correct Implementation**:
```python
# CORRECT: Fresh API call for order data
async def get_open_orders(self, symbol: Optional[Symbol] = None) -> Dict[Symbol, List[Order]]:
    """Fresh API call for current open orders - NEVER cached."""
    response = await self._rest_client.get('/api/v3/openOrders')
    return self._parse_orders(response)

# CORRECT: Fresh API call for order status
async def get_order(self, order_id: OrderId, symbol: Symbol) -> Optional[Order]:
    """Get fresh order details from API."""
    response = await self._rest_client.get(f'/api/v3/order?orderId={order_id}')
    return self._parse_order(response)
```

### **Position Data (NEVER CACHE)**

**Trading Positions** (Margin/Futures):
- ❌ Current position sizes
- ❌ Position entry prices
- ❌ Unrealized PnL
- ❌ Margin requirements
- ❌ Liquidation prices

**Rationale**: Position data changes with every trade and market movement. Stale position data causes overleverage and liquidation risks.

### **Market Movement Data (NEVER CACHE FOR TRADING)**

**Recent Trading Activity**:
- ❌ Recent trade history for price decisions
- ❌ Last executed prices for order pricing
- ❌ Volume-weighted average prices (VWAP)
- ❌ Price change percentages

**Rationale**: Recent trade data used for pricing decisions must be real-time. Stale data causes execution at unfavorable prices.

**Note**: Historical trade data for backtesting and analysis CAN be cached, but must NEVER be used for real-time trading decisions.

## Permitted Caching (Static Configuration Data)

### **Symbol Information (SAFE TO CACHE)**

**Symbol Metadata**:
- ✅ Symbol mappings (BTC/USDT → BTCUSDT)
- ✅ Trading pair information
- ✅ Base/quote asset definitions
- ✅ Symbol precision requirements
- ✅ Minimum/maximum order sizes

**Rationale**: Symbol information rarely changes and is essential for performance. Safe to cache with periodic refresh.

**Implementation**:
```python
# CORRECT: Symbol mapping cache with refresh
class SymbolMapper:
    def __init__(self):
        self._symbol_cache = {}
        self._last_refresh = 0
        self._refresh_interval = 3600  # 1 hour
        
    def get_exchange_symbol(self, symbol: Symbol, exchange: str) -> str:
        """Get exchange-specific symbol format."""
        self._refresh_cache_if_needed()
        return self._symbol_cache.get((symbol, exchange))
        
    def _refresh_cache_if_needed(self):
        """Refresh symbol cache periodically."""
        now = time.time()
        if now - self._last_refresh > self._refresh_interval:
            self._refresh_symbol_cache()
            self._last_refresh = now
```

### **Exchange Configuration (SAFE TO CACHE)**

**Exchange Settings**:
- ✅ API endpoints and URLs
- ✅ Rate limiting parameters
- ✅ Timeout configurations
- ✅ Authentication methods
- ✅ Supported trading pairs

**Rationale**: Exchange configuration is static operational data that doesn't affect trading decisions.

### **Trading Rules (SAFE TO CACHE)**

**Trading Constraints**:
- ✅ Minimum order quantities
- ✅ Price precision rules
- ✅ Trading hour restrictions
- ✅ Fee schedules and structures
- ✅ Order type availability

**Rationale**: Trading rules change infrequently and are needed for order validation. Safe to cache with periodic refresh.

### **Performance Data (SAFE TO CACHE)**

**System Metrics**:
- ✅ Performance benchmarks
- ✅ Latency statistics
- ✅ Error rate metrics
- ✅ System health indicators

**Rationale**: Performance data is analytical and doesn't affect trading decisions. Safe to cache for monitoring.

## Real-time Streaming Data (SPECIAL CASE)

### **OrderBook Data from WebSocket Streams**

**Real-time Market Data**:
- ✅ Current orderbook snapshots from WebSocket streams
- ✅ Real-time price levels (bids/asks)
- ✅ Live trade streams
- ✅ Ticker data from streaming sources

**Special Rules**:
- ✅ **ONLY from real-time WebSocket streams** - continuously updated
- ✅ **NEVER cache REST API responses** for trading decisions
- ✅ **Must have staleness detection** - discard old data
- ✅ **Connection health monitoring** - detect stream failures

**Implementation**:
```python
# CORRECT: Real-time streaming orderbook cache
class OrderbookManager:
    def __init__(self):
        self._orderbooks = {}  # Only real-time streaming data
        self._last_update = {}
        self._staleness_threshold = 5.0  # 5 seconds
        
    def update_orderbook(self, symbol: Symbol, orderbook: OrderBook):
        """Update orderbook from WebSocket stream."""
        self._orderbooks[symbol] = orderbook
        self._last_update[symbol] = time.time()
        
    def get_orderbook(self, symbol: Symbol) -> Optional[OrderBook]:
        """Get real-time orderbook - with staleness check."""
        orderbook = self._orderbooks.get(symbol)
        if not orderbook:
            return None
            
        # Staleness check - critical for HFT
        last_update = self._last_update.get(symbol, 0)
        if time.time() - last_update > self._staleness_threshold:
            self.logger.warning(f"Stale orderbook data for {symbol}")
            return None  # Don't return stale data
            
        return orderbook

# WRONG: Caching REST API responses for trading
async def get_orderbook_wrong(self, symbol: Symbol) -> OrderBook:  # ❌ DANGEROUS
    # NEVER cache REST responses for trading decisions
    if symbol in self._rest_cache:  # This causes stale price execution
        return self._rest_cache[symbol]
```

## Implementation Guidelines

### **HFT-Safe Exchange Interface**

All exchange implementations must follow these patterns:

```python
class UnifiedCompositeExchange:
    """HFT-safe exchange implementation."""
    
    def __init__(self):
        # CORRECT: Cache for static data only
        self._symbol_info_cache = {}
        self._exchange_config_cache = {}
        
        # CORRECT: Real-time streaming data only  
        self._orderbook_streams = {}  # WebSocket streams only
        
        # WRONG: Never implement these caches
        # self._balance_cache = {}      # ❌ PROHIBITED
        # self._order_cache = {}        # ❌ PROHIBITED  
        # self._position_cache = {}     # ❌ PROHIBITED
    
    # TRADING DATA: Always fresh API calls
    async def get_balances(self) -> Dict[str, AssetBalance]:
        """Fresh API call - NEVER cached."""
        return await self._rest_client.get_account_balances()
        
    async def get_open_orders(self) -> Dict[Symbol, List[Order]]:
        """Fresh API call - NEVER cached."""
        return await self._rest_client.get_open_orders()
    
    # MARKET DATA: Real-time streaming only
    def get_orderbook(self, symbol: Symbol) -> Optional[OrderBook]:
        """Real-time WebSocket data only - with staleness check."""
        return self._get_streaming_orderbook(symbol)
    
    # STATIC DATA: Safe to cache with refresh
    def get_symbol_info(self, symbol: Symbol) -> SymbolInfo:
        """Static symbol information - safe to cache."""
        if symbol not in self._symbol_info_cache:
            self._symbol_info_cache[symbol] = self._fetch_symbol_info(symbol)
        return self._symbol_info_cache[symbol]
```

### **Cache Validation Rules**

**Before implementing ANY cache, ask**:
1. **Does this data affect trading decisions?** If YES → NO CACHING
2. **Does this data change with trades/market movement?** If YES → NO CACHING  
3. **Is this real-time financial data?** If YES → NO CACHING
4. **Could stale data cause financial loss?** If YES → NO CACHING
5. **Is this static configuration/metadata?** If YES → Safe to cache with refresh

### **Code Review Checklist**

**Prohibited Patterns** (Reject in code review):
```python
# ❌ REJECT: Any caching of trading data
class BalanceCache: pass
class OrderCache: pass  
class PositionCache: pass

# ❌ REJECT: REST API response caching for trading
@lru_cache(maxsize=100)
def get_account_balance(): pass

# ❌ REJECT: Storing trading data in memory beyond immediate use
self._last_balance = balance  # Only if used immediately
time.sleep(1) 
return self._last_balance  # ❌ Now stale!

# ❌ REJECT: Time-based caches for trading data
@TTLCache(ttl=1)  # Even 1 second is too old!
def get_order_status(): pass
```

**Required Patterns** (Mandate in code review):
```python
# ✅ REQUIRE: Fresh API calls for all trading data
async def get_balances(self) -> Dict[str, AssetBalance]:
    response = await self._rest_client.get('/api/v3/account')
    return self._parse_balances(response)

# ✅ REQUIRE: Real-time streaming for market data
def get_orderbook(self, symbol: Symbol) -> Optional[OrderBook]:
    return self._websocket_orderbook_manager.get_current(symbol)
    
# ✅ REQUIRE: Staleness detection for streaming data  
if time.time() - orderbook.timestamp > MAX_STALENESS:
    return None  # Don't use stale data
```

## Monitoring and Compliance

### **Cache Usage Monitoring**

**Required Metrics**:
```python
# Monitor cache usage to detect violations
class CacheComplianceMonitor:
    def monitor_cache_access(self, cache_name: str, data_type: str):
        """Monitor cache access for compliance violations."""
        
        # Alert on prohibited cache types
        if data_type in ['balance', 'order', 'position', 'trade']:
            self.logger.critical("PROHIBITED CACHE DETECTED",
                               cache_name=cache_name,
                               data_type=data_type,
                               severity="TRADING_SAFETY_VIOLATION")
            
        # Track cache hit rates for permitted caches
        if data_type in ['symbol_info', 'exchange_config', 'trading_rules']:
            self.logger.info("Permitted cache access",
                           cache_name=cache_name,
                           data_type=data_type)
```

### **Staleness Detection**

**Required for ALL cached data**:
```python
class StalenessDetector:
    """Detect and prevent use of stale data."""
    
    STALENESS_LIMITS = {
        'orderbook': 5.0,      # 5 seconds max for orderbook
        'symbol_info': 3600.0,  # 1 hour for symbol info
        'trading_rules': 1800.0, # 30 minutes for trading rules
        'exchange_config': 86400.0  # 24 hours for config
    }
    
    def is_stale(self, data_type: str, timestamp: float) -> bool:
        """Check if data is too stale to use."""
        max_age = self.STALENESS_LIMITS.get(data_type, 0.0)
        age = time.time() - timestamp
        
        if age > max_age:
            self.logger.warning(f"Stale {data_type} data detected",
                              age_seconds=age,
                              max_age_seconds=max_age)
            return True
        return False
```

## Emergency Procedures

### **Cache Violation Response**

**If prohibited caching is discovered**:

1. **IMMEDIATE ACTION**:
   - Stop all trading operations immediately
   - Disable the violating cache mechanism
   - Switch to fresh API calls for all affected data

2. **ASSESSMENT**:
   - Determine scope of potentially affected trades
   - Calculate exposure from stale data usage
   - Review recent trading decisions for accuracy

3. **REMEDIATION**:
   - Implement proper fresh API calls
   - Add staleness detection where missing
   - Update monitoring to prevent recurrence

4. **VALIDATION**:
   - Verify all trading data comes from fresh sources
   - Test with paper trading before resuming live operations
   - Monitor for any residual caching behavior

### **Example Emergency Response**

```python
class EmergencyResponse:
    """Emergency procedures for cache violations."""
    
    async def handle_cache_violation(self, violation_type: str, affected_component: str):
        """Respond to cache policy violation."""
        
        self.logger.critical("CACHE VIOLATION EMERGENCY RESPONSE",
                           violation_type=violation_type,
                           component=affected_component)
        
        # 1. Stop trading immediately
        await self.trading_engine.emergency_stop()
        
        # 2. Disable violating cache
        await self.disable_cache_component(affected_component)
        
        # 3. Switch to fresh API mode
        await self.enable_fresh_api_mode()
        
        # 4. Validate system safety
        safety_check = await self.validate_no_cached_trading_data()
        
        if safety_check.passed:
            self.logger.info("Emergency response complete - system safe to resume")
        else:
            self.logger.critical("System still unsafe - manual intervention required")
```

## Summary

### **Absolute Rules**
1. **NEVER cache real-time trading data** (balances, orders, positions, recent trades)
2. **ALWAYS use fresh API calls** for trading decisions
3. **ONLY cache static configuration data** with periodic refresh
4. **IMPLEMENT staleness detection** for all cached data
5. **MONITOR cache usage** for compliance violations

### **Safe Caching Categories**
- ✅ Symbol mappings and metadata
- ✅ Exchange configuration and endpoints  
- ✅ Trading rules and constraints
- ✅ Performance metrics and analytics
- ✅ Real-time streaming data (with staleness detection)

### **Prohibited Caching Categories**  
- ❌ Account balances and available funds
- ❌ Order status and execution details
- ❌ Position data and margin requirements
- ❌ Recent trade history for pricing
- ❌ Any financial data used for trading decisions

**Remember**: This policy supersedes ALL performance considerations. Financial safety comes before optimization.

---

*This caching policy is mandatory for all HFT trading systems and must be followed without exception to prevent financial losses and maintain regulatory compliance.*