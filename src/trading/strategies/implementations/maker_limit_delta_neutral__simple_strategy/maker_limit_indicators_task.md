# Maker Limit Indicators Task Implementation Plan

## Overview
Add minimal, bulletproof market indicators to the simplified maker limit delta neutral strategy to prevent losses and optimize execution parameters dynamically.

## Core Principles
- **Minimal LOC**: Each feature adds <50 lines of code
- **Fail-safe defaults**: Conservative parameters when uncertain
- **Real-time updates**: Load initial DB data, then update with live book tickers
- **Fast execution**: All indicator checks complete in <5ms

## Phase 1: Safety First (~100 LOC total)

### 1. Initial Data Loading System
```python
class SimpleMarketDataLoader:
    def __init__(self):
        self.book_ticker_source = BookTickerDbSource()
        self.historical_loaded = False
        
    async def load_initial_data(self, exchanges, symbol, hours=12):
        """Load initial historical data from DB, fallback to real-time only"""
        try:
            df = await self.book_ticker_source.get_multi_exchange_data(
                exchanges=exchanges,
                symbol=symbol,
                hours=hours,
                timeframe='1m'  # 1-minute timeframe
            )
            self.historical_loaded = True
            return self._process_initial_data(df)
        except Exception:
            # Fallback: start with empty history, use real-time only
            self.historical_loaded = False
            return self._create_empty_history()
            
    def _process_initial_data(self, df):
        """Extract price history and spread history from DB data"""
        # Return processed price/spread arrays for indicators
        pass
```

### 2. Minimal Market State Tracker
```python
class SimpleMarketState:
    def __init__(self, max_history_minutes=120):  # 2 hours
        # Price tracking (for volatility)
        self.spot_prices = deque(maxlen=max_history_minutes)
        self.futures_prices = deque(maxlen=max_history_minutes)
        
        # Spread tracking (for safety)
        self.spot_spreads = deque(maxlen=max_history_minutes)
        self.futures_spreads = deque(maxlen=max_history_minutes)
        
        # Update timestamps
        self.last_update = 0
        self.update_interval = 60  # Update indicators every 60 seconds
        
    def update_real_time(self, spot_book: BookTicker, futures_book: BookTicker):
        """Update with real-time book ticker data"""
        current_time = time.time()
        if current_time - self.last_update < self.update_interval:
            return  # Skip update if too frequent
            
        # Calculate mid prices and spreads
        spot_mid = (spot_book.bid_price + spot_book.ask_price) / 2
        futures_mid = (futures_book.bid_price + futures_book.ask_price) / 2
        spot_spread_pct = (spot_book.ask_price - spot_book.bid_price) / spot_mid * 100
        futures_spread_pct = (futures_book.ask_price - futures_book.bid_price) / futures_mid * 100
        
        # Append to rolling history
        self.spot_prices.append(spot_mid)
        self.futures_prices.append(futures_mid)
        self.spot_spreads.append(spot_spread_pct)
        self.futures_spreads.append(futures_spread_pct)
        
        self.last_update = current_time
```

### 3. Core Safety Indicators
```python
class SafetyIndicators:
    def __init__(self, market_state: SimpleMarketState, config):
        self.state = market_state
        self.max_volatility_threshold = config.get('max_volatility_pct', 2.0)  # 2%
        self.max_spread_ratio = config.get('max_spread_ratio', 1.5)  # futures_spread <= 1.5x spot_spread
        
    def is_safe_to_trade(self) -> tuple[bool, str]:
        """Single method to check all safety conditions"""
        
        # 1. Check spread inversion (most critical)
        if self.spreads_inverted():
            return False, "spreads_inverted"
            
        # 2. Check excessive volatility
        if self.is_too_volatile():
            return False, "high_volatility"
            
        # 3. Check insufficient data
        if len(self.state.spot_prices) < 10:
            return False, "insufficient_data"
            
        return True, "safe"
    
    def spreads_inverted(self) -> bool:
        """Check if futures spread is significantly wider than spot spread"""
        if not self.state.spot_spreads or not self.state.futures_spreads:
            return True  # Conservative: block if no spread data
            
        avg_spot_spread = sum(list(self.state.spot_spreads)[-5:]) / 5  # Last 5 minutes
        avg_futures_spread = sum(list(self.state.futures_spreads)[-5:]) / 5
        
        return avg_futures_spread > (avg_spot_spread * self.max_spread_ratio)
    
    def is_too_volatile(self) -> bool:
        """Check if recent price volatility is too high"""
        if len(self.state.spot_prices) < 20:  # Need at least 20 minutes of data
            return True  # Conservative: block if insufficient data
            
        recent_prices = list(self.state.spot_prices)[-20:]  # Last 20 minutes
        price_range = max(recent_prices) - min(recent_prices)
        current_price = recent_prices[-1]
        volatility_pct = (price_range / current_price) * 100
        
        return volatility_pct > self.max_volatility_threshold
```

### 4. Dynamic Parameter Optimizer
```python
class DynamicParameters:
    def __init__(self, market_state: SimpleMarketState, base_config):
        self.state = market_state
        self.base_tick_offset = base_config['ticks_offset']
        self.base_tick_tolerance = base_config['tick_tolerance']
        
    def get_dynamic_tick_offset(self) -> int:
        """Adjust tick offset based on market conditions"""
        base = self.base_tick_offset
        
        # More aggressive in low volatility
        if self._is_low_volatility():
            return max(1, base - 1)
            
        # More conservative in high volatility  
        if self._is_medium_volatility():
            return base + 1
            
        return base
    
    def get_dynamic_tick_tolerance(self) -> int:
        """Adjust tick tolerance based on price movement patterns"""
        base = self.base_tick_tolerance
        
        # Allow more movement if trending
        if self._is_trending():
            return base + 2
            
        return base
    
    def _is_low_volatility(self) -> bool:
        """Check if volatility is below normal"""
        # Implementation using recent price history
        pass
        
    def _is_medium_volatility(self) -> bool:
        """Check if volatility is elevated but not extreme"""
        # Implementation using recent price history  
        pass
        
    def _is_trending(self) -> bool:
        """Simple trend detection using price slopes"""
        # Implementation using recent price history
        pass
```

### 5. Integration into Main Strategy
```python
# In MakerLimitDeltaNeutralTask.__init__()
async def _initialize_indicators(self):
    """Initialize market data and indicators"""
    # Load initial historical data
    data_loader = SimpleMarketDataLoader()
    initial_data = await data_loader.load_initial_data(
        exchanges=[self.context.spot_exchange, self.context.futures_exchange],
        symbol=self.context.symbol,
        hours=12
    )
    
    # Initialize market state tracker
    self.market_state = SimpleMarketState()
    self.market_state.load_initial_data(initial_data)
    
    # Initialize indicators
    safety_config = {
        'max_volatility_pct': 2.0,
        'max_spread_ratio': 1.5
    }
    self.safety_indicators = SafetyIndicators(self.market_state, safety_config)
    self.dynamic_params = DynamicParameters(self.market_state, self.context.settings['spot'])

# In _manage_positions() method
async def _manage_positions(self):
    """Enhanced position management with safety checks"""
    
    # Update market state with real-time data
    spot_book = self._get_book_ticker('spot')
    futures_book = self._get_book_ticker('futures')
    self.market_state.update_real_time(spot_book, futures_book)
    
    # Safety check - halt trading if unsafe
    is_safe, reason = self.safety_indicators.is_safe_to_trade()
    if not is_safe:
        await self._cancel_all_orders()
        self.logger.warning(f"🛑 Trading halted: {reason}")
        return
    
    # Update dynamic parameters
    dynamic_offset = self.dynamic_params.get_dynamic_tick_offset()
    dynamic_tolerance = self.dynamic_params.get_dynamic_tick_tolerance()
    
    # Apply dynamic parameters to settings (temporary override)
    original_offset = self.context.settings['spot'].ticks_offset
    original_tolerance = self.context.settings['spot'].tick_tolerance
    
    self.context.settings['spot'].ticks_offset = dynamic_offset
    self.context.settings['spot'].tick_tolerance = dynamic_tolerance
    
    try:
        # Existing position management logic
        await self._manage_spot_limit_order_place()
        await self._manage_spot_order_cancel()
        await self._adjust_futures_position()
        await self.handle_spot_mode()
    finally:
        # Restore original settings
        self.context.settings['spot'].ticks_offset = original_offset
        self.context.settings['spot'].tick_tolerance = original_tolerance
```

## Phase 2: Advanced Optimization (~50 LOC)

### 6. Volume-Based Execution Sizing
- Adjust order quantity based on order book depth
- Reduce size during low liquidity periods

### 7. Regime Detection
- Simple trend/mean-reversion detection
- Adjust strategy aggressiveness based on market regime

### 8. Performance Feedback Loop
- Track execution quality (slippage, fill rates)
- Automatically tune parameters based on performance

## Implementation Timeline

1. **Week 1**: Implement Phase 1 (Safety First)
2. **Week 2**: Testing and optimization of safety indicators
3. **Week 3**: Implement Phase 2 (Advanced features) if needed

## Risk Management

- **Graceful fallback**: If DB data unavailable, start with real-time only
- **Conservative defaults**: Block trading when uncertain
- **Circuit breakers**: Automatic halt on abnormal conditions
- **Logging**: Comprehensive logging of all indicator decisions

## Success Metrics

- **Reduced losses**: Fewer trades during adverse conditions
- **Improved fill rates**: Better execution through dynamic parameters
- **System stability**: No crashes due to data unavailability
- **Performance**: All indicator calculations < 5ms

## File Structure
```
maker_limit_delta_neutral__simple_strategy/
├── maker_limit_simple_delta_neutral_task.py  # Main strategy (existing)
├── indicators/
│   ├── __init__.py
│   ├── market_data_loader.py                 # Data loading from DB + real-time
│   ├── market_state_tracker.py               # Rolling price/spread history
│   ├── safety_indicators.py                  # Core safety checks
│   └── dynamic_parameters.py                 # Parameter optimization
└── maker_limit_indicators_task.md            # This plan document
```

This plan adds essential market intelligence to the strategy while maintaining simplicity and reliability. All components are designed to fail safely and require minimal maintenance.