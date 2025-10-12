# Directory Structure & File Organization

## Proposed File Structure

```
delta_arbitrage_to_live_plan/
├── README.md                           # Project overview
├── DIRECTORY_STRUCTURE.md              # This file
├── IMPLEMENTATION_SEQUENCE.md          # Step-by-step implementation guide
├── INTERFACES.md                       # API interfaces and data contracts
├── TESTING_STRATEGY.md                 # Testing approach and validation
│
├── optimization/
│   ├── __init__.py
│   ├── parameter_optimizer.py          # Core optimization engine
│   ├── spread_analyzer.py              # Spread distribution analysis
│   ├── statistical_models.py          # Mean reversion calculations
│   └── optimization_config.py         # Configuration for optimizer
│
├── strategy/
│   ├── __init__.py
│   ├── delta_arbitrage_strategy.py     # Main live trading strategy
│   ├── arbitrage_context.py           # Strategy-specific context
│   └── strategy_config.py             # Strategy configuration
│
├── integration/
│   ├── __init__.py
│   ├── optimizer_bridge.py            # Bridge between optimizer and strategy
│   └── parameter_scheduler.py         # Handles N-minute recalculation
│
├── examples/
│   ├── backtest_with_optimization.py  # Example: Run backtest with optimization
│   ├── live_strategy_demo.py          # Example: Start live strategy
│   └── parameter_analysis_demo.py     # Example: Analyze historical parameters
│
└── tests/
    ├── test_optimizer.py              # Unit tests for optimization engine
    ├── test_strategy.py               # Unit tests for live strategy
    └── test_integration.py            # Integration tests
```

## Core Components Breakdown

### **optimization/** - Parameter Optimization Engine
- **parameter_optimizer.py**: Main optimization class with statistical mean reversion
- **spread_analyzer.py**: Historical spread distribution analysis
- **statistical_models.py**: Mean reversion speed, autocorrelation calculations
- **optimization_config.py**: Configuration parameters for optimization

### **strategy/** - Live Trading Strategy
- **delta_arbitrage_strategy.py**: Simplified version of MexcGateioFuturesStrategy
- **arbitrage_context.py**: Strategy-specific context and state management
- **strategy_config.py**: Strategy configuration and default parameters

### **integration/** - Bridge Components
- **optimizer_bridge.py**: Interface between optimization engine and strategy
- **parameter_scheduler.py**: Handles periodic parameter recalculation

### **examples/** - Demonstration Scripts
- **backtest_with_optimization.py**: Show how to use optimizer in backtesting
- **live_strategy_demo.py**: Complete live trading example
- **parameter_analysis_demo.py**: Historical parameter analysis

### **tests/** - Testing Suite
- Unit tests for each component
- Integration tests for complete workflow
- Performance benchmarks for HFT compliance

## Integration Points with Existing Codebase

### **Reused Components**
- `src/exchanges/` - Exchange infrastructure (MEXC, Gate.io)
- `src/applications/hedged_arbitrage/strategy/base_arbitrage_strategy.py` - Base strategy class
- `src/applications/hedged_arbitrage/strategy/exchange_manager.py` - Exchange management
- `src/trading/research/backtesting_direct_arbitrage.py` - Existing backtest logic

### **New Components Location**
- Main implementation in `delta_arbitrage_to_live_plan/`
- Final integration may move to `src/applications/delta_arbitrage/`
- Configuration in existing config system

## File Size & Complexity Targets

### **Parameter Optimization (Simple & Focused)**
- `parameter_optimizer.py`: ~200-300 lines
- `spread_analyzer.py`: ~150-200 lines
- `statistical_models.py`: ~100-150 lines

### **Live Strategy (Simplified PoC)**
- `delta_arbitrage_strategy.py`: ~400-500 lines (vs 850+ in MexcGateioFuturesStrategy)
- Remove: Complex rebalancing, detailed position tracking, advanced error handling
- Keep: Core arbitrage logic, basic delta neutrality, parameter updates

### **Integration Components (Minimal)**
- `optimizer_bridge.py`: ~100-150 lines
- `parameter_scheduler.py`: ~80-120 lines

## Dependencies

### **Required Libraries**
- `pandas`, `numpy` - Data analysis for optimization
- `scipy` - Statistical calculations
- `asyncio` - Async live trading operations
- Existing exchange infrastructure

### **No New External Dependencies**
- Use existing codebase patterns and libraries
- Maintain compatibility with current HFT infrastructure