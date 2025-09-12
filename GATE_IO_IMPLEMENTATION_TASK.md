# Gate.io Exchange Integration Task

## Overview
Implement Gate.io exchange integration following CLAUDE.md standards and EXCHANGE_INTEGRATION_GUIDE.md patterns. This is a JSON-based API (Pattern A) integration that must comply with HFT safety standards.

## PRIMARY PRIORITY ORDER (As Per Agent Configuration):
1. **FIRST**: Ensure code follows CLAUDE.md architectural guidelines and SOLID principles
2. **SECOND**: Apply KISS/YAGNI principles - implement only what's needed
3. **THIRD**: Structure code with proper separation of concerns and clear interfaces
4. **FOURTH**: Implement comprehensive error handling using unified exception system
5. **FIFTH**: Consider performance optimizations without compromising simplicity

## PHASE 1: Research & Setup (2-4 hours)

### Task 1.1: Legacy Code Analysis
**Priority**: CRITICAL
**Description**: Analyze existing Gate.io implementation at `raw/gateio_api/`
**Acceptance Criteria**:
- [ ] Document reusable authentication patterns
- [ ] Identify existing symbol mapping logic
- [ ] Extract working WebSocket connection patterns
- [ ] Document current error handling approaches
- [ ] Create modernization recommendations

### Task 1.2: API Documentation Research
**Priority**: CRITICAL
**Description**: Deep dive into official Gate.io API v4 documentation
**Resources**:
- Spot API: https://www.gate.com/docs/developers/apiv4/en/#spot
- WebSocket: https://www.gate.com/docs/developers/apiv4/ws/en/
**Acceptance Criteria**:
- [ ] Document authentication (API key + signature generation)
- [ ] Map all required public endpoints (market data, symbols, orderbook)
- [ ] Map all required private endpoints (balance, orders, trades)
- [ ] Document WebSocket subscription patterns
- [ ] Document rate limiting policies (10 requests/second default)
- [ ] Create symbol format conversion matrix (ETH_USDT ↔ Symbol)

### Task 1.3: Directory Structure Creation
**Priority**: HIGH
**Description**: Set up Gate.io directory structure following EXCHANGE_INTEGRATION_GUIDE.md
**Acceptance Criteria**:
- [ ] Create `src/exchanges/gateio/` structure
- [ ] Set up `common/`, `rest/`, `ws/` subdirectories
- [ ] Create empty module files with basic structure
- [ ] Update `__init__.py` files for proper imports

## PHASE 2: Core Implementation (6-8 hours)

### Task 2.1: Configuration Module
**Priority**: CRITICAL
**File**: `src/exchanges/gateio/common/gateio_config.py`
**Acceptance Criteria**:
- [ ] Define all API endpoints (REST + WebSocket)
- [ ] Set rate limiting parameters (10 req/sec, weight limits)
- [ ] Configure timeouts and retry policies
- [ ] Follow MEXC pattern but adapt for Gate.io specifics

### Task 2.2: Utility Functions
**Priority**: HIGH
**File**: `src/exchanges/gateio/common/gateio_utils.py`
**Acceptance Criteria**:
- [ ] Symbol conversion: `ETH_USDT` ↔ `Symbol(base=AssetName("ETH"), quote=AssetName("USDT"))`
- [ ] HMAC-SHA512 signature generation for authentication
- [ ] Order side/type conversions (Gate.io ↔ unified enums)
- [ ] Timestamp utilities for API requests
- [ ] **CRITICAL**: Only cache static data (symbol mappings, exchange info)

### Task 2.3: Symbol Mappings
**Priority**: HIGH  
**File**: `src/exchanges/gateio/common/gateio_mappings.py`
**Acceptance Criteria**:
- [ ] Order status mappings (Gate.io ↔ OrderStatus enum)
- [ ] Order type mappings (Gate.io ↔ OrderType enum)
- [ ] Side mappings (Gate.io ↔ Side enum)
- [ ] Error code mappings (Gate.io ↔ unified exceptions)

### Task 2.4: Public REST API Implementation
**Priority**: CRITICAL
**File**: `src/exchanges/gateio/rest/gateio_public.py`
**Interface**: Must implement `PublicExchangeInterface`
**Acceptance Criteria**:
- [ ] `get_symbols()` - Fetch trading pairs
- [ ] `get_symbol_info()` - Get symbol details
- [ ] `get_orderbook()` - Fetch orderbook snapshot
- [ ] `get_recent_trades()` - Get recent trades
- [ ] `get_ticker()` - Get 24hr ticker stats
- [ ] Use `RestClient` from `src/common/rest_client.py`
- [ ] Return `msgspec.Struct` objects only
- [ ] **NO CACHING** of real-time data

### Task 2.5: Private REST API Implementation
**Priority**: CRITICAL
**File**: `src/exchanges/gateio/rest/gateio_private.py`
**Interface**: Must implement `PrivateExchangeInterface`
**Acceptance Criteria**:
- [ ] `get_account_balance()` - Fetch account balances
- [ ] `place_order()` - Place limit/market orders
- [ ] `cancel_order()` - Cancel specific order
- [ ] `get_order_status()` - Get order details
- [ ] `get_open_orders()` - Get open orders
- [ ] `get_order_history()` - Get completed orders
- [ ] HMAC-SHA512 authentication with proper headers
- [ ] **NO CACHING** of balances or order status

### Task 2.6: Public WebSocket Implementation
**Priority**: HIGH
**File**: `src/exchanges/gateio/ws/gateio_ws_public.py`
**Acceptance Criteria**:
- [ ] Real-time orderbook updates (spot.order_book channel)
- [ ] Real-time trades stream (spot.trades channel)
- [ ] Real-time ticker updates (spot.tickers channel)
- [ ] Proper subscription/unsubscription management
- [ ] JSON message parsing with msgspec
- [ ] Auto-reconnection with exponential backoff
- [ ] **Stream-only data** - no persistence

### Task 2.7: Private WebSocket Implementation  
**Priority**: MEDIUM (if supported by Gate.io)
**File**: `src/exchanges/gateio/ws/gateio_ws_private.py`
**Acceptance Criteria**:
- [ ] Account balance updates (if available)
- [ ] Order status updates (if available)  
- [ ] Trade execution notifications (if available)
- [ ] Proper authentication for private streams
- [ ] **Stream-only data** - no persistence

### Task 2.8: Main Exchange Interface
**Priority**: CRITICAL
**File**: `src/exchanges/gateio/gateio_exchange.py`
**Interface**: Must implement `BaseExchangeInterface`
**Acceptance Criteria**:
- [ ] Composition pattern: integrate public + private + WebSocket
- [ ] Context manager support (`async with`)
- [ ] Proper resource cleanup (`close()` method)
- [ ] Performance monitoring and metrics
- [ ] **NO CACHING** of real-time trading data
- [ ] Follow MEXC architectural pattern but without protobuf complexity

## PHASE 3: Integration & Testing (3-4 hours)

### Task 3.1: Configuration Integration
**Priority**: HIGH
**Files**: `src/common/config.py`, `config.yaml`
**Acceptance Criteria**:
- [ ] Add `GATEIO_API_KEY` and `GATEIO_SECRET_KEY` configuration
- [ ] Add Gate.io-specific settings (rate limits, timeouts)
- [ ] Environment variable support
- [ ] Credential validation

### Task 3.2: Public Integration Examples
**Priority**: HIGH
**File**: `src/examples/gateio/public_rest_checks.py`
**Acceptance Criteria**:
- [ ] Test market data fetching (symbols, orderbook, trades)
- [ ] Validate symbol conversion logic
- [ ] Test error handling and rate limiting
- [ ] Performance timing validation (<50ms target)

### Task 3.3: Private Integration Examples
**Priority**: HIGH
**File**: `src/examples/gateio/private_rest_checks.py`
**Acceptance Criteria**:
- [ ] Test account balance fetching
- [ ] Test order placement (small test orders)
- [ ] Test order cancellation
- [ ] Test authentication and signature generation
- [ ] **Use small amounts for safety**

### Task 3.4: WebSocket Examples
**Priority**: MEDIUM
**Files**: `src/examples/gateio/ws_public_simple_check.py`, `ws_private_simple_check.py`
**Acceptance Criteria**:
- [ ] Test WebSocket connection and subscription
- [ ] Test real-time data streaming
- [ ] Test reconnection handling
- [ ] Test message parsing and validation

## PHASE 4: Documentation & Validation (2-3 hours)

### Task 4.1: Documentation Creation
**Priority**: HIGH
**File**: `src/exchanges/gateio/README.md`
**Acceptance Criteria**:
- [ ] Architecture overview and design decisions
- [ ] Usage examples and integration patterns
- [ ] Performance characteristics and optimizations
- [ ] Configuration and setup guide
- [ ] Follow MEXC README.md as template

### Task 4.2: Integration Validation
**Priority**: CRITICAL
**Acceptance Criteria**:
- [ ] All abstract interfaces properly implemented
- [ ] HFT caching policy compliance verified
- [ ] SOLID principles adherence validated
- [ ] Performance targets met (<50ms latency)
- [ ] Error handling comprehensive and tested

## CRITICAL REQUIREMENTS:

### HFT Caching Policy Compliance:
- ❌ **NEVER CACHE**: Orderbook data, account balances, order status, trade data
- ✅ **SAFE TO CACHE**: Symbol mappings, exchange info, static configuration

### Architectural Standards:
- ✅ Use unified interfaces from `src/exchanges/interface/`
- ✅ Use msgspec.Struct for all data structures
- ✅ Use unified exceptions from `src/common/exceptions.py`
- ✅ Follow JSON API Pattern A from EXCHANGE_INTEGRATION_GUIDE.md

### Performance Targets:
- ✅ <50ms REST API latency
- ✅ <1ms JSON parsing per message
- ✅ >1000 messages/second WebSocket throughput
- ✅ Proper memory management and cleanup

## RISK MITIGATION:

1. **Authentication Complexity**: Use legacy code patterns as reference
2. **Rate Limiting**: Conservative approach (8 req/sec vs 10 limit)
3. **Symbol Formats**: Comprehensive mapping with validation
4. **WebSocket Stability**: Robust reconnection with exponential backoff
5. **Error Handling**: Map all Gate.io error codes to unified exceptions

## SUCCESS CRITERIA:

- [ ] All 12 tasks completed with acceptance criteria met
- [ ] Integration examples running successfully
- [ ] Performance targets achieved
- [ ] HFT safety compliance verified
- [ ] Documentation complete and accurate
- [ ] Ready for production HFT trading environment

**Total Estimated Effort**: 16-20 hours across 2 weeks
**Priority**: HFT safety → Architecture → Performance
**Pattern**: JSON API (Pattern A) - no protobuf complexity needed