# Grafana Dashboard Variables Configuration

Configure these variables in your Grafana dashboard to make the arbitrage monitoring queries dynamic and parameter-aware.

## Dashboard Variables Setup

### 1. Core Trading Parameters

```yaml
# Variable: symbol_base
Type: Textbox
Name: symbol_base
Label: Symbol Base
Default: BTC
Description: Base asset for arbitrage monitoring (e.g., BTC, ETH, BNB)

# Variable: max_entry_cost_pct  
Type: Textbox
Name: max_entry_cost_pct
Label: Max Entry Cost %
Default: 0.5
Description: Maximum entry cost threshold (default: 0.5%)

# Variable: min_profit_pct
Type: Textbox  
Name: min_profit_pct
Label: Min Profit %
Default: 0.58
Description: Minimum profit threshold for exit (default: 0.58%)

# Variable: max_hours
Type: Textbox
Name: max_hours  
Label: Max Hours
Default: 6.0
Description: Maximum position holding time before timeout (default: 6.0)
```

### 2. Fee Configuration

```yaml
# Variable: spot_fee
Type: Textbox
Name: spot_fee
Label: Spot Exchange Fee
Default: 0.0005
Description: Spot trading fee rate (default: 0.05%)

# Variable: futures_fee
Type: Textbox
Name: futures_fee  
Label: Futures Exchange Fee
Default: 0.0005
Description: Futures trading fee rate (default: 0.05%)
```

### 3. Position Tracking Variables

```yaml
# Variable: has_position
Type: Custom
Name: has_position
Label: Has Active Position
Options: true,false
Default: false
Description: Whether there is currently an active arbitrage position

# Variable: entry_spot_ask
Type: Textbox
Name: entry_spot_ask
Label: Entry Spot Ask Price  
Default: 50000.0
Description: Spot ask price when position was entered (required for exit monitoring)

# Variable: entry_futures_bid
Type: Textbox
Name: entry_futures_bid
Label: Entry Futures Bid Price
Default: 49750.0  
Description: Futures bid price when position was entered (required for exit monitoring)

# Variable: position_start_time
Type: Textbox
Name: position_start_time
Label: Position Start Time (Unix)
Default: 0
Description: Unix timestamp when position was opened (for timeout alerts)
```

### 4. Risk Management Variables

```yaml
# Variable: min_order_size_usdt
Type: Textbox
Name: min_order_size_usdt
Label: Min Order Size (USDT)
Default: 100
Description: Minimum order size in USDT for volume validation
```

## Panel Configurations

### Entry Opportunities Panel
```sql
-- Query: grafana_arbitrage_entry_points.sql
-- Visualization: Time series
-- Y-Axis: Entry Cost %
-- Alert Condition: value <= $max_entry_cost_pct AND value > 0
```

### Exit Opportunities Panel  
```sql
-- Query: grafana_arbitrage_exit_points.sql
-- Visualization: Time series  
-- Y-Axis: P&L %
-- Alert Condition: value >= $min_profit_pct
-- Display: Only when $has_position = true
```

### Combined Dashboard Panel
```sql  
-- Query: grafana_arbitrage_dashboard.sql
-- Visualization: Time series (multi-series)
-- Series:
--   - ENTRY_SPREAD: Entry cost percentage
--   - EXIT_SPREAD: Exit cost percentage  
--   - SPREAD_ADVANTAGE: Difference between entry and exit
--   - POSITION_PNL: Current position P&L (if active)
```

## Alert Rules Configuration

### Entry Signal Alert
```yaml
Query: grafana_arbitrage_alerts.sql (Alert 1)
Condition: entry_signals_count > 0
Frequency: 10s
Message: "Arbitrage entry opportunity detected for ${symbol_base}: ${best_entry_cost_pct}% entry cost"
```

### Exit Signal Alert  
```yaml
Query: grafana_arbitrage_alerts.sql (Alert 2)
Condition: exit_signals_count > 0 AND has_position = true
Frequency: 10s  
Message: "Arbitrage exit target reached for ${symbol_base}: ${best_pnl_pct}% profit"
```

### Timeout Warning Alert
```yaml
Query: grafana_arbitrage_alerts.sql (Alert 3)
Condition: timeout_alert = 1
Frequency: 60s
Message: "Position timeout warning for ${symbol_base}: ${hours_held}h / ${max_hours_threshold}h"
```

### Volume Alert
```yaml
Query: grafana_arbitrage_alerts.sql (Alert 4)  
Condition: avg_entry_volume < min_required_quantity
Frequency: 30s
Message: "Low volume warning for ${symbol_base}: ${avg_entry_volume} < ${min_required_quantity}"
```

## Usage Examples

### Manual Position Tracking
When opening a position manually, update these variables:
- `has_position`: true
- `entry_spot_ask`: actual entry spot price
- `entry_futures_bid`: actual entry futures price  
- `position_start_time`: current unix timestamp

### Automated Integration
For live trading integration, variables can be updated via:
- Grafana API calls from trading system
- Database triggers updating variable tables
- External scripts synchronizing position state

### Different Trading Strategies
Create multiple dashboard copies with different parameter sets:
- Conservative: `max_entry_cost_pct=0.3, min_profit_pct=0.8`
- Aggressive: `max_entry_cost_pct=0.8, min_profit_pct=0.4`
- High-frequency: `max_hours=2, min_order_size_usdt=50`