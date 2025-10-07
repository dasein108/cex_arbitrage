# Specific Action Items - Detailed Implementation Guide

## 🎯 Phase 1 Actions: Critical Fixes

### Action 1.1: Eliminate Wildcard Imports

**Command to Find Issues**:
```bash
# Find all wildcard imports
grep -r "from .* import \*" src/ --include="*.py"
grep -r "from typing import \*" src/ --include="*.py"  
grep -r "from config.structs import \*" src/ --include="*.py"
```

**Example Fix - exchanges/interfaces/composite/base_public_composite.py**:
```python
# ❌ Before (Line 7)
from exchanges.structs.enums import *

# ✅ After  
from exchanges.structs.enums import (
    ExchangeEnum,
    MarketType, 
    OrderType,
    OrderSide,
    OrderStatus
)
```

**Implementation Steps**:
1. **Scan file for wildcard import**
2. **Find actual usage** with `grep -n "ExchangeEnum\|MarketType\|OrderType" filename.py`
3. **Replace wildcard with explicit imports**
4. **Test file functionality**
5. **Run type checker**: `mypy filename.py`

**Verification Script**:
```bash
#!/bin/bash
# verify_imports.sh
echo "Checking for remaining wildcard imports..."
WILDCARDS=$(grep -r "import \*" src/ --include="*.py" | wc -l)
if [ $WILDCARDS -eq 0 ]; then
    echo "✅ No wildcard imports found"
else
    echo "❌ Found $WILDCARDS wildcard imports"
    grep -r "import \*" src/ --include="*.py"
fi
```

### Action 1.2: Replace Hardcoded Paths

**Command to Find Issues**:
```bash
# Find hardcoded paths
grep -r "/Users\|/home\|/var\|C:\\\|D:\\\\" src/ --include="*.py"
grep -r "\.log\|\.json\|\.yaml" src/ --include="*.py" | grep -v "import"
```

**Example Fix - config/config_manager.py**:
```python
# ❌ Before
CONFIG_PATH = "/Users/dasein/dev/cex_arbitrage/config"
LOG_PATH = "/var/logs/trading"

# ✅ After
import os
from pathlib import Path

# Get project root dynamically
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = os.getenv("CEX_CONFIG_PATH", PROJECT_ROOT / "config")
LOG_PATH = os.getenv("CEX_LOG_PATH", PROJECT_ROOT / "logs")
```

**Environment Configuration File**:
```bash
# .env.example
CEX_CONFIG_PATH=/app/config
CEX_LOG_PATH=/app/logs
CEX_DATA_PATH=/app/data
CEX_ENV=development
CEX_DEBUG=true
```

**Path Resolution Utility**:
```python
# common/utils/path_utils.py
import os
from pathlib import Path
from typing import Union

def get_project_root() -> Path:
    """Get the project root directory"""
    return Path(__file__).parent.parent.parent

def resolve_config_path(relative_path: str) -> Path:
    """Resolve configuration file path"""
    config_root = os.getenv("CEX_CONFIG_PATH", get_project_root() / "config")
    return Path(config_root) / relative_path

def resolve_log_path(filename: str) -> Path:
    """Resolve log file path"""
    log_root = os.getenv("CEX_LOG_PATH", get_project_root() / "logs")
    return Path(log_root) / filename
```

---

## 🏗️ Phase 2 Actions: Configuration Restructuring

### Action 2.1: Create New Configuration Structure

**Directory Structure Creation**:
```bash
# Create new configuration structure
mkdir -p config/core
mkdir -p config/exchanges  
mkdir -p config/infrastructure
```

**Base Configuration Class**:
```python
# config/core/base_config.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from msgspec import Struct
import os
from pathlib import Path

class BaseConfig(Struct, ABC):
    """Abstract base class for all configuration objects"""
    
    @classmethod
    @abstractmethod
    def from_env(cls) -> 'BaseConfig':
        """Load configuration from environment variables"""
        pass
    
    @classmethod  
    @abstractmethod
    def from_file(cls, file_path: Path) -> 'BaseConfig':
        """Load configuration from file"""
        pass
    
    @abstractmethod
    def validate(self) -> None:
        """Validate configuration values"""
        pass
```

**Exchange Configuration Example**:
```python
# config/exchanges/mexc_config.py
from typing import Optional
from msgspec import Struct
from ..core.base_config import BaseConfig
from ..core.validation import validate_url, validate_positive_int

class MexcConfig(BaseConfig):
    base_url: str = "https://api.mexc.com"
    websocket_url: str = "wss://wbs.mexc.com/ws"
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    requests_per_second: int = 10
    max_connections: int = 5
    
    @classmethod
    def from_env(cls) -> 'MexcConfig':
        return cls(
            api_key=os.getenv("MEXC_API_KEY"),
            secret_key=os.getenv("MEXC_SECRET_KEY"),
            requests_per_second=int(os.getenv("MEXC_RPS", "10")),
            max_connections=int(os.getenv("MEXC_MAX_CONN", "5"))
        )
    
    def validate(self) -> None:
        validate_url(self.base_url, "base_url")
        validate_url(self.websocket_url, "websocket_url") 
        validate_positive_int(self.requests_per_second, "requests_per_second")
        validate_positive_int(self.max_connections, "max_connections")
```

### Action 2.2: Configuration Migration Script

**Migration Utility**:
```python
# scripts/migrate_config.py
import json
import yaml
from pathlib import Path
from config.core.base_config import BaseConfig
from config.exchanges.mexc_config import MexcConfig
from config.exchanges.gateio_config import GateioConfig

def migrate_old_config() -> None:
    """Migrate from old configuration format to new structure"""
    
    # Load old configuration
    old_config_path = Path("config/trading_config.json")
    if not old_config_path.exists():
        print("No old configuration found")
        return
        
    with open(old_config_path) as f:
        old_config = json.load(f)
    
    # Extract MEXC configuration
    mexc_data = old_config.get("exchanges", {}).get("mexc", {})
    mexc_config = MexcConfig(
        api_key=mexc_data.get("api_key"),
        secret_key=mexc_data.get("secret_key"),
        requests_per_second=mexc_data.get("rate_limit", 10)
    )
    
    # Save new configuration
    new_config_path = Path("config/exchanges/mexc.yaml")
    with open(new_config_path, 'w') as f:
        yaml.dump(mexc_config.to_dict(), f)
    
    print(f"Migrated MEXC configuration to {new_config_path}")

if __name__ == "__main__":
    migrate_old_config()
```

---

## 🔧 Phase 3 Actions: Architectural Improvements

### Action 3.1: Refactor MexcPublicExchange

**Current Structure Analysis**:
```bash
# Analyze current class size
wc -l src/exchanges/integrations/mexc/mexc_public.py
# Count methods
grep -c "def " src/exchanges/integrations/mexc/mexc_public.py
```

**Decomposition Plan**:
```python
# Step 1: Extract WebSocket management
# exchanges/integrations/mexc/components/websocket_manager.py
class MexcWebSocketManager:
    """Handles WebSocket connection lifecycle for MEXC"""
    
    def __init__(self, config: MexcConfig):
        self.config = config
        self._connection: Optional[websockets.WebSocketServerProtocol] = None
        self._reconnect_attempts = 0
        
    async def connect(self) -> None:
        """Establish WebSocket connection"""
        # Extract connection logic from main class
        
    async def disconnect(self) -> None:
        """Close WebSocket connection"""
        # Extract disconnection logic
        
    async def send_message(self, message: Dict[str, Any]) -> None:
        """Send message through WebSocket"""
        # Extract message sending logic

# Step 2: Extract data parsing
# exchanges/integrations/mexc/components/data_parser.py  
class MexcDataParser:
    """Handles message parsing and data transformation for MEXC"""
    
    def parse_orderbook_message(self, raw_message: bytes) -> OrderbookUpdate:
        """Parse orderbook update message"""
        # Extract parsing logic
        
    def parse_trade_message(self, raw_message: bytes) -> TradeUpdate:
        """Parse trade update message"""
        # Extract parsing logic

# Step 3: Refactored main class
# exchanges/integrations/mexc/mexc_public.py
class MexcPublicExchange:
    """Coordinated MEXC public exchange operations"""
    
    def __init__(self, config: MexcConfig, rest_client: MexcRest, websocket_client: MexcWebSocket):
        self.config = config
        self.rest_client = rest_client
        self.websocket_client = websocket_client
        
        # Inject components
        self._ws_manager = MexcWebSocketManager(config)
        self._data_parser = MexcDataParser()
        self._connection_handler = MexcConnectionHandler(config)
    
    # Coordination methods only - delegate to components
```

**Refactoring Steps**:
1. **Create component directory**: `mkdir -p exchanges/integrations/mexc/components`
2. **Extract WebSocket management** to separate class
3. **Extract data parsing** to separate class  
4. **Extract connection handling** to separate class
5. **Update main class** to use components
6. **Test each component** individually
7. **Integration test** the refactored system

### Action 3.2: Factory Pattern Enhancement

**Component Registry Implementation**:
```python
# exchanges/factory/component_registry.py
from typing import Dict, Type, TypeVar, Callable
from exchanges.interfaces.base_rest import BaseRestClient
from exchanges.interfaces.base_websocket import BaseWebSocketClient
from exchanges.interfaces.base_composite import BaseCompositeExchange

T = TypeVar('T')

class ComponentRegistry:
    """Registry for exchange components using type-safe registration"""
    
    _rest_clients: Dict[str, Type[BaseRestClient]] = {}
    _websocket_clients: Dict[str, Type[BaseWebSocketClient]] = {}
    _composite_exchanges: Dict[str, Type[BaseCompositeExchange]] = {}
    
    @classmethod
    def register_rest_client(cls, exchange_name: str, client_class: Type[BaseRestClient]) -> None:
        """Register REST client implementation for exchange"""
        cls._rest_clients[exchange_name] = client_class
    
    @classmethod
    def get_rest_client(cls, exchange_name: str) -> Type[BaseRestClient]:
        """Get REST client class for exchange"""
        if exchange_name not in cls._rest_clients:
            raise ValueError(f"No REST client registered for {exchange_name}")
        return cls._rest_clients[exchange_name]
    
    # Similar methods for websocket_clients and composite_exchanges

# Auto-registration decorator
def register_rest_client(exchange_name: str):
    def decorator(cls: Type[BaseRestClient]) -> Type[BaseRestClient]:
        ComponentRegistry.register_rest_client(exchange_name, cls)
        return cls
    return decorator

# Usage in exchange implementations
@register_rest_client("mexc_public")
class MexcPublicRest(BaseRestClient):
    pass
```

**Enhanced Factory Implementation**:
```python
# exchanges/factory/factory_manager.py
from typing import Optional, Union
from .component_registry import ComponentRegistry
from ..interfaces.base_composite import BaseCompositeExchange
from config.exchanges.base_exchange_config import ExchangeConfig

class ExchangeFactoryManager:
    """Main factory coordinator using component registry"""
    
    def __init__(self):
        self._registry = ComponentRegistry()
    
    def create_exchange(
        self, 
        exchange_name: str, 
        config: ExchangeConfig,
        is_private: bool = False
    ) -> BaseCompositeExchange:
        """Create exchange using registered components"""
        
        # Determine component key
        component_key = f"{exchange_name}_{'private' if is_private else 'public'}"
        
        # Get component classes from registry
        rest_class = self._registry.get_rest_client(component_key)
        ws_class = self._registry.get_websocket_client(component_key)
        exchange_class = self._registry.get_composite_exchange(component_key)
        
        # Create components
        rest_client = rest_class(config)
        ws_client = ws_class(config)
        
        # Create exchange with injected dependencies
        return exchange_class(
            config=config,
            rest_client=rest_client,
            websocket_client=ws_client
        )
```

---

## 📦 Phase 4 Actions: Standardization

### Action 4.1: Import Pattern Standardization

**Import Standards Definition**:
```python
# standards/import_patterns.py
"""
Standard import patterns for the CEX Arbitrage Engine

1. Standard library imports (first)
2. Third-party imports (second)  
3. Local package imports (third)
4. Relative imports (last)

Within each group, sort alphabetically.
"""

# ✅ Correct pattern example
import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
import msgspec
from websockets import WebSocketServerProtocol

from config.exchanges.mexc_config import MexcConfig
from common.exceptions.exchange import ExchangeException
from exchanges.structs.enums import ExchangeEnum

from .base_exchange import BaseExchange
from ..structs.orderbook import OrderbookUpdate
```

**Automated Import Formatter**:
```python
# scripts/format_imports.py
import ast
import sys
from pathlib import Path
from typing import List, Set

class ImportStandardizer:
    """Standardize import patterns across the codebase"""
    
    def __init__(self):
        self.stdlib_modules = self._get_stdlib_modules()
        self.local_packages = {'config', 'common', 'exchanges', 'trading'}
    
    def standardize_file(self, file_path: Path) -> None:
        """Standardize imports in a single file"""
        with open(file_path, 'r') as f:
            content = f.read()
            
        tree = ast.parse(content)
        imports = self._extract_imports(tree)
        standardized = self._standardize_imports(imports)
        
        # Replace imports in file
        new_content = self._replace_imports(content, standardized)
        
        with open(file_path, 'w') as f:
            f.write(new_content)
    
    def _extract_imports(self, tree: ast.AST) -> List[ast.stmt]:
        """Extract all import statements from AST"""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(node)
        return imports
    
    def _standardize_imports(self, imports: List[ast.stmt]) -> str:
        """Group and sort imports according to standards"""
        stdlib_imports = []
        third_party_imports = []
        local_imports = []
        relative_imports = []
        
        for imp in imports:
            if isinstance(imp, ast.ImportFrom) and imp.level > 0:
                relative_imports.append(imp)
            elif self._is_stdlib_import(imp):
                stdlib_imports.append(imp)
            elif self._is_local_import(imp):
                local_imports.append(imp)
            else:
                third_party_imports.append(imp)
        
        # Sort each group and format
        groups = [
            self._format_import_group(stdlib_imports),
            self._format_import_group(third_party_imports),
            self._format_import_group(local_imports),
            self._format_import_group(relative_imports)
        ]
        
        return '\n\n'.join(filter(None, groups))

# Usage script
def standardize_all_imports():
    standardizer = ImportStandardizer()
    
    for py_file in Path('src').rglob('*.py'):
        print(f"Standardizing {py_file}")
        standardizer.standardize_file(py_file)

if __name__ == "__main__":
    standardize_all_imports()
```

### Action 4.2: Exception Handling Standardization

**Exception Hierarchy Implementation**:
```python
# common/exceptions/base.py
from datetime import datetime
from typing import Optional, Dict, Any
import uuid

class CexArbitrageException(Exception):
    """Base exception for all CEX arbitrage operations"""
    
    def __init__(
        self, 
        message: str, 
        correlation_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.timestamp = datetime.utcnow()
        self.context = context or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging"""
        return {
            'exception_type': self.__class__.__name__,
            'message': self.message,
            'correlation_id': self.correlation_id,
            'timestamp': self.timestamp.isoformat(),
            'context': self.context
        }

# common/exceptions/exchange.py
class ExchangeException(CexArbitrageException):
    """Base for all exchange-related exceptions"""
    
    def __init__(
        self, 
        message: str, 
        exchange: str,
        operation: Optional[str] = None,
        correlation_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, correlation_id, context)
        self.exchange = exchange
        self.operation = operation

class ExchangeConnectionException(ExchangeException):
    """WebSocket/REST connection issues"""
    pass

class ExchangeAuthenticationException(ExchangeException):
    """Authentication and authorization issues"""
    pass

class ExchangeDataException(ExchangeException):
    """Data parsing and validation issues"""
    pass

class ExchangeRateLimitException(ExchangeException):
    """Rate limiting and quota issues"""
    pass
```

**Standard Error Handler Implementation**:
```python
# common/utils/error_handler.py
import logging
from typing import Type, Callable, Any
from functools import wraps
from .exceptions.base import CexArbitrageException
from .exceptions.exchange import (
    ExchangeConnectionException,
    ExchangeDataException,
    ExchangeRateLimitException
)

class StandardErrorHandler:
    """Standard error handling patterns for the application"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def handle_exchange_error(
        self, 
        error: Exception, 
        exchange: str, 
        operation: str,
        correlation_id: str
    ) -> None:
        """Standard exchange error handling"""
        
        context = {
            'exchange': exchange,
            'operation': operation,
            'original_error': str(error),
            'error_type': type(error).__name__
        }
        
        if isinstance(error, aiohttp.ClientError):
            raise ExchangeConnectionException(
                f"Connection failed during {operation} on {exchange}",
                exchange=exchange,
                operation=operation,
                correlation_id=correlation_id,
                context=context
            ) from error
            
        elif isinstance(error, json.JSONDecodeError):
            raise ExchangeDataException(
                f"Invalid JSON response during {operation} on {exchange}",
                exchange=exchange,
                operation=operation,
                correlation_id=correlation_id,
                context=context
            ) from error
            
        elif "rate limit" in str(error).lower():
            raise ExchangeRateLimitException(
                f"Rate limit exceeded during {operation} on {exchange}",
                exchange=exchange,
                operation=operation,
                correlation_id=correlation_id,
                context=context
            ) from error
            
        else:
            # Generic exchange exception
            raise ExchangeException(
                f"Unexpected error during {operation} on {exchange}: {error}",
                exchange=exchange,
                operation=operation,
                correlation_id=correlation_id,
                context=context
            ) from error

# Decorator for automatic error handling
def handle_exchange_errors(exchange: str, operation: str):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            correlation_id = kwargs.get('correlation_id', str(uuid.uuid4()))
            error_handler = StandardErrorHandler(logging.getLogger(__name__))
            
            try:
                return await func(*args, **kwargs)
            except CexArbitrageException:
                # Re-raise our own exceptions
                raise
            except Exception as e:
                # Handle external exceptions
                error_handler.handle_exchange_error(e, exchange, operation, correlation_id)
                
        return wrapper
    return decorator

# Usage example
class MexcPublicExchange:
    @handle_exchange_errors(exchange="mexc", operation="get_orderbook")
    async def get_orderbook(self, symbol: str) -> OrderbookSnapshot:
        # Implementation that may raise various exceptions
        pass
```

---

## ✅ Validation Scripts

### Comprehensive Validation Script
```bash
#!/bin/bash
# scripts/validate_refactoring.sh

echo "🔍 Running comprehensive refactoring validation..."

# Check 1: No wildcard imports
echo "Checking for wildcard imports..."
WILDCARDS=$(grep -r "import \*" src/ --include="*.py" | wc -l)
if [ $WILDCARDS -eq 0 ]; then
    echo "✅ No wildcard imports found"
else
    echo "❌ Found $WILDCARDS wildcard imports"
    exit 1
fi

# Check 2: No hardcoded paths  
echo "Checking for hardcoded paths..."
HARDCODED=$(grep -r "/Users\|/home\|/var\|C:\\\|D:\\\\" src/ --include="*.py" | wc -l)
if [ $HARDCODED -eq 0 ]; then
    echo "✅ No hardcoded paths found"
else
    echo "❌ Found $HARDCODED hardcoded paths"
    exit 1
fi

# Check 3: Class size limits
echo "Checking class sizes..."
python scripts/check_class_sizes.py

# Check 4: Import pattern consistency
echo "Checking import patterns..."
python scripts/check_import_patterns.py

# Check 5: Exception hierarchy usage
echo "Checking exception usage..."
python scripts/check_exception_usage.py

# Check 6: Run tests
echo "Running test suite..."
python -m pytest tests/ -v

# Check 7: Performance benchmarks
echo "Running performance benchmarks..."
python scripts/run_benchmarks.py

echo "🎉 All validation checks passed!"
```

---

*These specific actions provide concrete, step-by-step implementation guidance for the complete refactoring plan.*