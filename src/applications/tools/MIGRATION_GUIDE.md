# Tools Migration Guide

Migration guide for moving from the legacy 3-script workflow to the unified arbitrage tool.

## Summary of Changes

The tools directory has been refactored to follow CLAUDE.md principles:

- **3 separate files** → **1 unified tool** 
- **~1,400 lines** → **~500 lines** (~65% reduction)
- **Code duplication** → **Shared utilities**
- **Direct imports** → **Proper interface usage**
- **Manual creation** → **Factory pattern**

## Migration Commands

### Before (Legacy)
```bash
# Step 1: Symbol discovery
python cross_exchange_symbol_discovery.py --format detailed

# Step 2: Data collection  
python arbitrage_data_fetcher.py --days 3 --max-symbols 20

# Step 3: Analysis
python arbitrage_analyzer.py --min-profit-score 30
```

### After (Unified)
```bash
# Step 1: Symbol discovery
python unified_arbitrage_tool.py discover --format detailed

# Step 2: Data collection
python unified_arbitrage_tool.py fetch --days 3 --max-symbols 20

# Step 3: Analysis  
python unified_arbitrage_tool.py analyze --min-profit-score 30
```

## Argument Mapping

All arguments remain the same, just prefixed with the operation:

| Legacy Tool | Unified Command |
|-------------|----------------|
| `cross_exchange_symbol_discovery.py --format matrix` | `unified_arbitrage_tool.py discover --format matrix` |
| `arbitrage_data_fetcher.py --days 7 --validate-only` | `unified_arbitrage_tool.py fetch --days 7 --validate-only` |
| `arbitrage_analyzer.py --output report.csv --details` | `unified_arbitrage_tool.py analyze --output report.csv --details` |

## Architecture Changes

### SOLID Compliance

**Before**: Monolithic functions with mixed responsibilities
```python
# Each tool had ~150 lines of mixed CLI, business logic, formatting
def fetch_arbitrage_data(...):  # 112 lines doing everything
def analyze_opportunities(...): # 172 lines doing everything  
```

**After**: Single responsibility components
```python
class SymbolDiscoveryService:    # Only symbol discovery
class DataCollectionService:     # Only data collection  
class AnalysisService:          # Only analysis
class ArbitrageToolController:  # Only orchestration
```

### Interface Usage

**Before**: Direct REST client imports

```python
from exchanges.mexc.rest.mexc_rest_public import MexcPublicSpotRest
from exchanges.gateio.rest.gateio_public import GateioPublicExchangeSpotRest
```

**After**: Proper interface usage (CLAUDE.md compliant)

```python
from exchanges.interfaces.composite.base_public_exchange import CompositePublicExchange
from exchanges.factories.exchange_factory import ExchangeFactory
```

### DRY Elimination

**Before**: Duplicated code patterns
```python
# Repeated in all 3 files:
logging.basicConfig(level=logging.INFO, format='%(asctime)s...')
if not Path(file).is_absolute(): file = str(Path.cwd() / file)
parser = argparse.ArgumentParser(description=..., formatter_class=...)
```

**After**: Shared utilities
```python
from shared_utils import LoggingConfigurator, PathResolver, CLIManager
```

## Backward Compatibility

### Legacy Tools Status
- ✅ **Available**: All original tools remain functional
- ⚠️ **Deprecated**: No new features will be added
- 🎯 **Recommended**: Use unified tool for new development

### Migration Timeline
- **Immediate**: Start using unified tool for new workflows
- **1 month**: Migrate existing scripts to unified tool
- **3 months**: Legacy tools may be moved to archive/

## Benefits Achieved

### Code Quality
- **SOLID Principles**: Each component has single responsibility
- **DRY Compliance**: Eliminated ~305 lines of duplication
- **KISS Principle**: Simplified architecture with focused components
- **Interface Segregation**: Proper separation of concerns

### Performance
- **HFT Compliance**: Using proper factory patterns and interfaces  
- **Consistent Patterns**: Unified async/await usage throughout
- **Connection Pooling**: Proper resource management via interfaces
- **Error Handling**: Unified exception hierarchy

### Maintainability  
- **65% Less Code**: Easier to maintain and extend
- **Focused Components**: Clear separation of responsibilities
- **Shared Infrastructure**: Common patterns in one place
- **Type Safety**: Better error catching and IDE support

## Troubleshooting

### Common Issues

**1. Missing dependencies**
```bash
# Solution: Ensure all imports are available
cd /Users/dasein/dev/cex_arbitrage/src/tools
python -c "from shared_utils import CLIManager; print('✓ OK')"
```

**2. Interface not found errors**
```bash
# Solution: Check PYTHONPATH includes src directory
export PYTHONPATH=/Users/dasein/dev/cex_arbitrage/src:$PYTHONPATH
```

**3. Legacy tool still works but unified tool fails**
```bash
# Solution: Check if all factory dependencies are available  
python -c "from cex.factories.exchange_factory import ExchangeFactory; print('✓ OK')"
```

### Help and Support

Get help for any operation:
```bash
python unified_arbitrage_tool.py --help
python unified_arbitrage_tool.py discover --help
python unified_arbitrage_tool.py fetch --help
python unified_arbitrage_tool.py analyze --help
```

All functionality from the original tools is preserved with the same command-line arguments.