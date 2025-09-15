# Arbitrage Detector Implementation - Detailed Task List

## Overview

This document provides a comprehensive task breakdown for implementing the HFT-compliant arbitrage detector system. The implementation leverages existing `SymbolInfo.fees_maker` and `fees_taker` fields for fee calculations, simplifying the architecture significantly.

## Architecture Foundation

**Current Status**: ✅ **SUFFICIENT** - No BaseExchangeInterface extensions needed
- Fees available via `BaseExchangeInterface.symbol_info[symbol].fees_maker/fees_taker`
- Orderbook data available via `BaseExchangeInterface.orderbook`
- Symbol information complete via `BaseExchangeInterface.symbol_info`

## Phase 1: Core Detection Infrastructure

### Task 1.1: Market Data Integration Setup
**Priority**: HIGH | **Estimated Time**: 4 hours | **HFT Compliance**: Critical

#### Subtasks:
- [ ] **1.1.1** Connect detector to `MarketDataAggregator` real-time feeds
  - Integrate with existing WebSocket streams from MEXC/Gate.io
  - Ensure <100ms data staleness compliance (HFT requirement)
  - Implement event-driven price update handling
  
- [ ] **1.1.2** Initialize symbol monitoring system
  - Load monitored symbols from `ArbitrageConfig.enabled_exchanges`
  - Set up symbol-to-exchange mapping using O(1) symbol resolver
  - Configure initial symbol set (recommend: BTC/USDT, ETH/USDT, BNB/USDT)

- [ ] **1.1.3** Implement real-time data validation
  - Validate orderbook data freshness (<100ms staleness)
  - Ensure bid < ask price consistency
  - Filter out empty or invalid orderbook entries

**Acceptance Criteria**:
- Real-time price updates flowing to detector
- Symbol monitoring active for configured pairs
- Data validation preventing stale/invalid data processing

---

### Task 1.2: Fee Calculation System Integration
**Priority**: HIGH | **Estimated Time**: 3 hours | **HFT Compliance**: Critical

#### Subtasks:
- [ ] **1.2.1** Implement fee lookup from SymbolInfo
  ```python
  def get_trading_fees(self, symbol: Symbol, exchange: ExchangeName) -> Tuple[float, float]:
      """Get maker/taker fees from symbol_info[symbol].fees_maker/fees_taker"""
      symbol_info = self.market_data_aggregator.get_symbol_info(exchange, symbol)
      return symbol_info.fees_maker, symbol_info.fees_taker
  ```

- [ ] **1.2.2** Create profit calculation with fees
  ```python
  def calculate_net_profit(self, buy_price: float, sell_price: float, 
                          quantity: float, buy_fees: Tuple[float, float],
                          sell_fees: Tuple[float, float]) -> float:
      """Calculate net profit including maker/taker fees"""
      # Assume taker fees for market orders (conservative approach)
      buy_fee_cost = buy_price * quantity * buy_fees[1]  # taker fee
      sell_fee_cost = sell_price * quantity * sell_fees[1]  # taker fee
      gross_profit = (sell_price - buy_price) * quantity
      return gross_profit - buy_fee_cost - sell_fee_cost
  ```

- [ ] **1.2.3** Implement basis points calculation
  ```python
  def calculate_profit_margin_bps(self, net_profit: float, trade_value: float) -> int:
      """Calculate profit margin in basis points (1 bps = 0.01%)"""
      if trade_value <= 0:
          return 0
      margin_ratio = net_profit / trade_value
      return int(margin_ratio * 10000)  # Convert to basis points
  ```

**Acceptance Criteria**:
- Fee data correctly retrieved from existing SymbolInfo structure
- Profit calculations include maker/taker fees accurately
- Basis points calculation matches HFT precision requirements

---

## Phase 2: Core Detection Logic Implementation

### Task 2.1: Cross-Exchange Price Comparison Engine
**Priority**: HIGH | **Estimated Time**: 6 hours | **Performance Target**: <5ms per symbol

#### Subtasks:
- [ ] **2.1.1** Implement `_compare_cross_exchange_prices()` method
  ```python
  async def _compare_cross_exchange_prices(self, symbol: Symbol) -> List[PriceComparison]:
      """
      Compare prices across all enabled exchanges for given symbol.
      
      Performance Target: <5ms per symbol comparison
      HFT Compliance: Fresh data only, no caching
      """
      comparisons = []
      exchanges = self.websocket_config.enabled_exchanges
      
      # Get fresh orderbook data from all exchanges (concurrent)
      orderbook_tasks = [
          self.market_data_aggregator.get_current_orderbook(exchange, symbol)
          for exchange in exchanges
      ]
      orderbooks = await asyncio.gather(*orderbook_tasks)
      
      # Create all exchange pair combinations
      for i, buy_exchange in enumerate(exchanges):
          for j, sell_exchange in enumerate(exchanges):
              if i != j and orderbooks[i] and orderbooks[j]:
                  comparison = await self._create_price_comparison(
                      symbol, buy_exchange, sell_exchange, 
                      orderbooks[i], orderbooks[j]
                  )
                  if comparison.profit_margin_bps > 0:
                      comparisons.append(comparison)
      
      return sorted(comparisons, key=lambda x: x.profit_margin_bps, reverse=True)
  ```

- [ ] **2.1.2** Implement price comparison creation logic
  ```python
  async def _create_price_comparison(self, symbol: Symbol, 
                                   buy_exchange: ExchangeName, sell_exchange: ExchangeName,
                                   buy_orderbook: OrderBook, sell_orderbook: OrderBook) -> PriceComparison:
      """Create detailed price comparison with fees and profit calculations"""
      
      # Get best prices (HFT optimized: direct array access)
      buy_price = buy_orderbook.asks[0].price  # Best ask (buy from)
      sell_price = sell_orderbook.bids[0].price  # Best bid (sell to)
      
      # Calculate maximum tradeable quantity (market depth validation)
      max_quantity = min(
          buy_orderbook.asks[0].size,
          sell_orderbook.bids[0].size
      )
      
      # Get trading fees for both exchanges
      buy_fees = await self.get_trading_fees(symbol, buy_exchange)
      sell_fees = await self.get_trading_fees(symbol, sell_exchange)
      
      # Calculate net profit including fees
      net_profit = self.calculate_net_profit(
          buy_price, sell_price, max_quantity, buy_fees, sell_fees
      )
      
      # Calculate profit margin in basis points
      trade_value = buy_price * max_quantity
      profit_margin_bps = self.calculate_profit_margin_bps(net_profit, trade_value)
      
      return PriceComparison(
          symbol=symbol,
          buy_exchange=buy_exchange,
          sell_exchange=sell_exchange,
          buy_price=buy_price,
          sell_price=sell_price,
          price_difference=net_profit / max_quantity,  # Per-unit profit
          profit_margin_bps=profit_margin_bps,
          max_quantity=max_quantity
      )
  ```

**Acceptance Criteria**:
- Cross-exchange price comparisons completing in <5ms per symbol
- All exchange pair combinations evaluated concurrently
- Profit calculations include fees and market depth validation

---

### Task 2.2: Opportunity Validation Engine
**Priority**: HIGH | **Estimated Time**: 4 hours | **Performance Target**: <2ms per validation

#### Subtasks:
- [ ] **2.2.1** Enhance `_validate_spot_opportunity()` method
  ```python
  async def _validate_spot_opportunity(self, comparison: PriceComparison) -> bool:
      """
      Comprehensive opportunity validation for execution feasibility.
      
      Performance Target: <2ms per opportunity validation
      """
      
      # 1. Profit margin threshold check (O(1) - fastest)
      if comparison.profit_margin_bps < self.websocket_config.risk_limits.min_profit_margin_bps:
          return False
      
      # 2. Minimum quantity check
      min_trade_value = comparison.buy_price * comparison.max_quantity
      if min_trade_value < self.websocket_config.risk_limits.max_position_size_usd * 0.01:  # 1% of max position
          return False
      
      # 3. Price deviation check (prevent execution on extreme prices)
      price_spread_bps = ((comparison.sell_price - comparison.buy_price) / comparison.buy_price) * 10000
      if price_spread_bps > self.websocket_config.risk_limits.max_spread_bps:
          return False
      
      # 4. Market depth validation (ensure sufficient liquidity)
      required_depth_usd = self.websocket_config.risk_limits.min_market_depth_usd
      buy_depth_usd = comparison.buy_price * comparison.max_quantity
      sell_depth_usd = comparison.sell_price * comparison.max_quantity
      
      if min(buy_depth_usd, sell_depth_usd) < required_depth_usd:
          return False
      
      # 5. Exchange connectivity check
      buy_exchange_healthy = await self._check_exchange_health(comparison.buy_exchange)
      sell_exchange_healthy = await self._check_exchange_health(comparison.sell_exchange)
      
      return buy_exchange_healthy and sell_exchange_healthy
  ```

- [ ] **2.2.2** Implement exchange health checking
  ```python
  async def _check_exchange_health(self, exchange: ExchangeName) -> bool:
      """Fast exchange connectivity and health check"""
      try:
          # Get exchange instance from aggregator
          exchange_instance = self.market_data_aggregator.get_exchange(exchange)
          
          # Check WebSocket connection status
          if hasattr(exchange_instance, 'status'):
              return exchange_instance.status == ExchangeStatus.ACTIVE
          
          return True  # Assume healthy if no status available
          
      except Exception as e:
          logger.warning(f"Exchange health check failed for {exchange}: {e}")
          return False
  ```

**Acceptance Criteria**:
- Multi-layer validation completing in <2ms per opportunity
- Health checks for exchange connectivity
- Configurable risk thresholds properly applied

---

### Task 2.3: Spot Arbitrage Detection Core
**Priority**: HIGH | **Estimated Time**: 5 hours | **Performance Target**: <20ms for all symbols

#### Subtasks:
- [ ] **2.3.1** Complete `_detect_spot_arbitrage()` implementation
  ```python
  async def _detect_spot_arbitrage(self) -> None:
      """
      Detect cross-exchange spot arbitrage opportunities.
      
      Performance Target: <20ms for all symbol/exchange combinations
      HFT Critical: Use only fresh market data, no caching
      """
      
      # Get fresh orderbook data for all monitored symbols (concurrent)
      symbol_comparison_tasks = [
          self._compare_cross_exchange_prices(symbol)
          for symbol in self._monitored_symbols
      ]
      
      # Execute all price comparisons concurrently
      all_comparisons = await asyncio.gather(*symbol_comparison_tasks)
      
      # Flatten and process all opportunities
      for symbol_comparisons in all_comparisons:
          for comparison in symbol_comparisons:
              # Validate opportunity for execution feasibility
              if await self._validate_spot_opportunity(comparison):
                  # Create and process opportunity
                  opportunity = await self._create_spot_opportunity(comparison)
                  await self._process_opportunity(opportunity)
  ```

- [ ] **2.3.2** Enhance `_create_spot_opportunity()` implementation
  ```python
  async def _create_spot_opportunity(self, comparison: PriceComparison) -> ArbitrageOpportunity:
      """
      Create comprehensive ArbitrageOpportunity from validated price comparison.
      
      Performance: <1ms opportunity creation using HFT-optimized calculations
      """
      
      # Generate unique opportunity ID with timestamp
      opportunity_id = f"spot_{comparison.symbol.base}_{comparison.symbol.quote}_{int(asyncio.get_event_loop().time() * 1000)}"
      
      # Calculate execution parameters
      total_profit_estimate = comparison.price_difference * comparison.max_quantity
      required_balance_buy = comparison.buy_price * comparison.max_quantity
      required_balance_sell = comparison.max_quantity
      
      # Estimate price impact (simple linear model)
      price_impact_estimate = min(0.001, comparison.max_quantity * 0.0001)  # HFT optimized: float literals
      
      # Set execution window based on profit margin (higher profit = longer window)
      base_window_ms = self.websocket_config.target_execution_time_ms
      profit_multiplier = max(1.0, comparison.profit_margin_bps / 50.0)  # Scale with profit
      execution_window_ms = min(int(base_window_ms * profit_multiplier), base_window_ms * 3)
      
      return ArbitrageOpportunity(
          opportunity_id=opportunity_id,
          opportunity_type=OpportunityType.SPOT_SPOT,
          symbol=comparison.symbol,
          buy_exchange=comparison.buy_exchange,
          sell_exchange=comparison.sell_exchange,
          buy_price=comparison.buy_price,
          sell_price=comparison.sell_price,
          max_quantity=comparison.max_quantity,
          profit_per_unit=comparison.price_difference,
          total_profit_estimate=total_profit_estimate,
          profit_margin_bps=comparison.profit_margin_bps,
          price_impact_estimate=price_impact_estimate,
          execution_time_window_ms=execution_window_ms,
          required_balance_buy=required_balance_buy,
          required_balance_sell=required_balance_sell,
          timestamp_detected=int(asyncio.get_event_loop().time() * 1000),
          market_depth_validated=True,
          balance_validated=False,  # TODO: Implement in Phase 3
          risk_approved=True,       # Already validated in _validate_spot_opportunity
      )
  ```

**Acceptance Criteria**:
- Spot arbitrage detection completing in <20ms for all symbols
- Comprehensive opportunity objects with all required parameters
- HFT-compliant performance with concurrent processing

---

## Phase 3: Advanced Features and Integration

### Task 3.1: Balance Validation Integration
**Priority**: MEDIUM | **Estimated Time**: 4 hours

#### Subtasks:
- [ ] **3.1.1** Implement balance checking
  ```python
  async def _validate_account_balances(self, opportunity: ArbitrageOpportunity) -> bool:
      """
      Validate sufficient balances for opportunity execution.
      
      Performance Target: <5ms per balance check
      """
      try:
          # Get current balances from both exchanges (concurrent)
          buy_exchange_instance = self.market_data_aggregator.get_exchange(opportunity.buy_exchange)
          sell_exchange_instance = self.market_data_aggregator.get_exchange(opportunity.sell_exchange)
          
          balance_tasks = [
              self._get_exchange_balance(buy_exchange_instance, opportunity.symbol.quote),  # Need quote for buying
              self._get_exchange_balance(sell_exchange_instance, opportunity.symbol.base)   # Need cex for selling
          ]
          
          buy_balance, sell_balance = await asyncio.gather(*balance_tasks)
          
          # Check sufficient balances
          has_buy_balance = buy_balance >= opportunity.required_balance_buy
          has_sell_balance = sell_balance >= opportunity.required_balance_sell
          
          return has_buy_balance and has_sell_balance
          
      except Exception as e:
          logger.warning(f"Balance validation failed for {opportunity.opportunity_id}: {e}")
          return False
  ```

- [ ] **3.1.2** Update opportunity creation to include balance validation
  - Modify `_create_spot_opportunity()` to call balance validation
  - Set `balance_validated=True` only when balances are sufficient
  - Add balance validation timing to performance metrics

**Acceptance Criteria**:
- Balance validation integrated into opportunity creation
- <5ms validation time maintained
- Insufficient balance opportunities properly filtered

---

### Task 3.2: Performance Monitoring and Metrics
**Priority**: MEDIUM | **Estimated Time**: 3 hours

#### Subtasks:
- [ ] **3.2.1** Enhance detection performance tracking
  ```python
  def _update_detection_performance(self, scan_start_time: float, opportunities_found: int) -> None:
      """Track detailed detection performance metrics"""
      
      scan_duration_ms = (asyncio.get_event_loop().time() - scan_start_time) * 1000
      
      # Update performance metrics
      self._scan_times.append(scan_duration_ms)
      if len(self._scan_times) > 100:
          self._scan_times.pop(0)  # Keep rolling window
      
      # Calculate performance statistics
      avg_scan_time = sum(self._scan_times) / len(self._scan_times)
      max_scan_time = max(self._scan_times)
      
      # Alert if performance degrading
      if scan_duration_ms > 100:  # HFT threshold
          logger.warning(f"Slow detection scan: {scan_duration_ms:.1f}ms (avg: {avg_scan_time:.1f}ms)")
      
      # Update success metrics
      self._detection_success_rate = opportunities_found / max(self._scans_completed, 1)
  ```

- [ ] **3.2.2** Add HFT compliance monitoring
  - Track data staleness across all exchanges
  - Monitor WebSocket connection health
  - Alert on HFT threshold violations (>100ms data age)

**Acceptance Criteria**:
- Comprehensive performance metrics collection
- Real-time HFT compliance monitoring
- Performance degradation alerts

---

### Task 3.3: Error Handling and Recovery
**Priority**: MEDIUM | **Estimated Time**: 3 hours

#### Subtasks:
- [ ] **3.3.1** Implement robust error handling in detection loop
  ```python
  async def _detection_loop(self) -> None:
      """
      Main detection loop with comprehensive error handling and recovery.
      """
      consecutive_errors = 0
      max_consecutive_errors = 5
      
      while self._is_detecting and not self._shutdown_event.is_set():
          scan_start_time = asyncio.get_event_loop().time()
          
          try:
              # Perform market scan with timeout
              await asyncio.wait_for(
                  self._scan_for_opportunities(),
                  timeout=self.websocket_config.opportunity_scan_interval_ms / 1000.0 * 0.8  # 80% of interval
              )
              
              # Reset error counter on success
              consecutive_errors = 0
              
              # Update performance metrics
              scan_time_ms = (asyncio.get_event_loop().time() - scan_start_time) * 1000
              self._update_scan_metrics(scan_time_ms)
              
          except asyncio.TimeoutError:
              logger.error("Detection scan timeout exceeded")
              consecutive_errors += 1
              
          except Exception as e:
              logger.error(f"Error in detection loop: {e}")
              consecutive_errors += 1
              
              # Circuit breaker: stop detection if too many consecutive errors
              if consecutive_errors >= max_consecutive_errors:
                  logger.critical(f"Too many consecutive errors ({consecutive_errors}), stopping detection")
                  await self.stop_detection()
                  break
          
          # Adaptive sleep based on error rate
          sleep_duration = self.websocket_config.opportunity_scan_interval_ms / 1000.0
          if consecutive_errors > 0:
              sleep_duration *= (1.5 ** consecutive_errors)  # Exponential backoff
          
          await asyncio.sleep(sleep_duration)
  ```

- [ ] **3.3.2** Add graceful degradation for exchange failures
  - Continue detection with remaining healthy exchanges
  - Implement automatic reconnection for failed exchanges
  - Maintain detection uptime during partial failures

**Acceptance Criteria**:
- Robust error handling with circuit breaker protection
- Graceful degradation during exchange failures
- Automatic recovery and reconnection logic

---

## Phase 4: Testing and Validation

### Task 4.1: Unit Testing Framework
**Priority**: HIGH | **Estimated Time**: 6 hours

#### Subtasks:
- [ ] **4.1.1** Create comprehensive test suite for detection logic
  ```python
  # tests/test_opportunity_detector.py
  
  import pytest
  from unittest.mock import Mock, AsyncMock
  
  from arbitrage.detector import OpportunityDetector
  from arbitrage.structures import ArbitrageConfig, RiskLimits
  from structs import Symbol, OrderBook, OrderBookEntry
  
  @pytest.fixture
  def mock_config():
      return ArbitrageConfig(
          engine_name="test_engine",
          enabled_opportunity_types=[OpportunityType.SPOT_SPOT],
          enabled_exchanges=[ExchangeName("mexc"), ExchangeName("gateio")],
          target_execution_time_ms=50,
          opportunity_scan_interval_ms=100,
          risk_limits=RiskLimits(
              min_profit_margin_bps=10,
              max_position_size_usd=1000.0,
              # ... other risk parameters
          )
      )
  
  @pytest.mark.asyncio
  async def test_spot_arbitrage_detection(mock_config):
      """Test basic spot arbitrage detection functionality"""
      
      # Setup mock market data aggregator
      mock_aggregator = AsyncMock()
      
      # Create detector
      detector = OpportunityDetector(mock_config, mock_aggregator)
      
      # Setup test data
      symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
      
      # Mock orderbook data with profitable opportunity
      mexc_orderbook = OrderBook(
          bids=[OrderBookEntry(price=50000.0, size=1.0)],
          asks=[OrderBookEntry(price=50050.0, size=1.0)],
          timestamp=time.time()
      )
      
      gateio_orderbook = OrderBook(
          bids=[OrderBookEntry(price=50100.0, size=1.0)],
          asks=[OrderBookEntry(price=50150.0, size=1.0)],
          timestamp=time.time()
      )
      
      # Setup mock responses
      mock_aggregator.get_current_orderbook.side_effect = [mexc_orderbook, gateio_orderbook]
      
      # Execute detection
      comparisons = await detector._compare_cross_exchange_prices(symbol)
      
      # Validate results
      assert len(comparisons) > 0
      assert comparisons[0].profit_margin_bps > 0
      assert comparisons[0].buy_exchange == ExchangeName("mexc")
      assert comparisons[0].sell_exchange == ExchangeName("gateio")
  ```

- [ ] **4.1.2** Performance testing framework
  ```python
  @pytest.mark.asyncio
  async def test_detection_performance(mock_config):
      """Test detection performance meets HFT requirements"""
      
      detector = OpportunityDetector(mock_config, mock_aggregator)
      
      # Setup multiple symbols for realistic testing
      symbols = [
          Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
          Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
          Symbol(base=AssetName("BNB"), quote=AssetName("USDT"))
      ]
      
      detector._monitored_symbols = set(symbols)
      
      # Measure detection performance
      start_time = time.time()
      await detector._detect_spot_arbitrage()
      detection_time_ms = (time.time() - start_time) * 1000
      
      # Verify performance requirements
      assert detection_time_ms < 20  # <20ms for all symbols requirement
  ```

**Acceptance Criteria**:
- Comprehensive unit test coverage (>90%)
- Performance tests validating HFT requirements
- Integration tests with mock market data

---

### Task 4.2: Integration Testing with Live Data
**Priority**: HIGH | **Estimated Time**: 4 hours

#### Subtasks:
- [ ] **4.2.1** Create live data testing environment
  - Setup test configuration with real MEXC/Gate.io connections
  - Use small position sizes for safe testing
  - Implement dry-run mode for opportunity detection

- [ ] **4.2.2** Validate detection accuracy
  - Compare detected opportunities with manual calculations
  - Verify fee calculations against exchange APIs
  - Test edge cases (low liquidity, extreme spreads)

**Acceptance Criteria**:
- Live data integration testing passing
- Detection accuracy validated against manual calculations
- Edge case handling verified

---

## Implementation Timeline

### Week 1: Foundation (40 hours)
- **Days 1-2**: Phase 1 - Core Detection Infrastructure (Tasks 1.1, 1.2)
- **Days 3-5**: Phase 2 - Core Detection Logic (Tasks 2.1, 2.2, 2.3)

### Week 2: Advanced Features (32 hours)
- **Days 1-2**: Phase 3 - Advanced Features (Tasks 3.1, 3.2, 3.3)
- **Days 3-4**: Phase 4 - Testing and Validation (Tasks 4.1, 4.2)

### Total Estimated Effort: 72 hours

## Success Criteria

### Performance Requirements (HFT Compliance)
- [ ] **Detection Latency**: <10ms opportunity detection latency achieved
- [ ] **Scan Performance**: <20ms complete market scan for all symbols
- [ ] **Data Freshness**: <100ms maximum data staleness maintained
- [ ] **Validation Speed**: <2ms per opportunity validation
- [ ] **Memory Efficiency**: <50MB memory usage during operation

### Functional Requirements
- [ ] **Accuracy**: >95% opportunity accuracy rate (manual validation)
- [ ] **Coverage**: All enabled exchanges and symbols monitored
- [ ] **Reliability**: >99% uptime during market hours
- [ ] **Error Handling**: Graceful degradation during exchange failures
- [ ] **Integration**: Seamless integration with existing MarketDataAggregator

### Business Requirements
- [ ] **Profit Threshold**: Configurable minimum profit margins (basis points)
- [ ] **Risk Management**: Full integration with risk limits system
- [ ] **Monitoring**: Real-time performance and health monitoring
- [ ] **Scalability**: Support for additional exchanges and symbols
- [ ] **Documentation**: Complete API documentation and usage examples

## Risk Mitigation

### Technical Risks
- **Performance Degradation**: Continuous monitoring with alerting
- **Exchange API Failures**: Graceful degradation and automatic recovery
- **Data Quality Issues**: Multi-layer validation and filtering
- **Memory Leaks**: Proper resource management and monitoring

### Business Risks
- **False Positives**: Conservative validation thresholds
- **Market Impact**: Position size limits and market depth validation
- **Regulatory Compliance**: Comprehensive audit logging
- **Operational Risk**: Circuit breakers and automatic shutdown

## Conclusion

This implementation plan provides a comprehensive roadmap for building an HFT-compliant arbitrage detector. The existing architecture significantly simplifies the implementation by providing fee data through SymbolInfo, eliminating the need for BaseExchangeInterface extensions.

The phased approach ensures incremental progress with continuous validation, while the detailed task breakdown provides clear implementation guidance for achieving sub-10ms detection latency requirements.