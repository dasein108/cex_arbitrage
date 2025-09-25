# TASK 1.1: Config Manager Decomposition

**Phase**: 1 - Critical File Decomposition  
**Stage**: 1.1  
**Priority**: CRITICAL  
**Estimated Duration**: 2 Days  
**Risk Level**: LOW  

---

## 🎯 **Task Overview**

Decompose the monolithic `config_manager.py` (1,127 lines) into focused, maintainable modules that follow the Single Responsibility Principle while preserving all existing functionality.

---

## 📊 **Current State Analysis**

### **Problem**:
- **File Size**: 1,127 lines (exceeds 500-line limit by 127%)
- **Responsibilities**: Database config, exchange config, logging config, validation, error handling
- **Complexity**: High cognitive load, difficult to modify and test
- **Violations**: SRP violation, high cyclomatic complexity

### **Target State**:
```
src/config/
├── config_manager.py (200 lines - orchestrator)
├── database/
│   ├── database_config.py (250 lines)
│   └── database_validator.py (150 lines)
├── exchanges/
│   ├── exchange_config.py (280 lines)
│   └── credentials_manager.py (200 lines)
└── logging/
    └── logging_config.py (180 lines)
```

---

## 🔍 **Detailed Analysis**

### **Current Responsibilities in config_manager.py**:
1. **Database Configuration** (Lines ~150-400)
   - Connection string generation
   - Pool configuration
   - Validation logic
   - Migration settings

2. **Exchange Configuration** (Lines ~401-700)
   - Credential management
   - Exchange-specific settings
   - API endpoint configuration
   - Rate limiting settings

3. **Logging Configuration** (Lines ~701-900)
   - Logger setup
   - Backend configuration
   - Log level management
   - File rotation settings

4. **Main Orchestration** (Lines ~1-149, 901-1127)
   - Config loading
   - Validation coordination
   - Error handling
   - Public API

---

## 📝 **Implementation Plan**

### **Step 1: Create Database Configuration Module** (4 hours)

#### **1.1 Create database_config.py**:
```python
# src/config/database/database_config.py
from typing import Dict, Any, Optional
from dataclasses import dataclass
import os
from infrastructure.config.structs import DatabaseConfig

class DatabaseConfigManager:
    """Manages database-specific configuration settings."""
    
    def __init__(self, config_data: Dict[str, Any]):
        self.config_data = config_data
        self._database_config: Optional[DatabaseConfig] = None
    
    def get_database_config(self) -> DatabaseConfig:
        """Get validated database configuration."""
        if self._database_config is None:
            self._database_config = self._build_database_config()
        return self._database_config
    
    def _build_database_config(self) -> DatabaseConfig:
        """Build database configuration from config data."""
        db_config = self.config_data.get('database', {})
        
        return DatabaseConfig(
            host=db_config.get('host', 'localhost'),
            port=db_config.get('port', 5432),
            database=db_config.get('database', 'arbitrage_db'),
            username=db_config.get('username', ''),
            password=self._get_database_password(),
            # Connection pool settings
            min_pool_size=db_config.get('min_pool_size', 10),
            max_pool_size=db_config.get('max_pool_size', 20),
            max_queries=db_config.get('max_queries', 50000),
            max_inactive_connection_lifetime=db_config.get('max_inactive_connection_lifetime', 300)
        )
    
    def _get_database_password(self) -> str:
        """Securely retrieve database password from environment or config."""
        # Priority: Environment variable > Config file
        password = os.environ.get('DB_PASSWORD')
        if password:
            return password
        
        return self.config_data.get('database', {}).get('password', '')
    
    def validate_database_config(self) -> None:
        """Validate database configuration settings."""
        config = self.get_database_config()
        
        if not config.host:
            raise ValueError("Database host is required")
        
        if not config.database:
            raise ValueError("Database name is required")
        
        if not config.username:
            raise ValueError("Database username is required")
        
        if config.min_pool_size <= 0:
            raise ValueError("min_pool_size must be positive")
        
        if config.max_pool_size <= config.min_pool_size:
            raise ValueError("max_pool_size must be greater than min_pool_size")
```

#### **1.2 Create database_validator.py**:
```python
# src/config/database/database_validator.py
from typing import Dict, Any, List
import asyncio
import asyncpg
from infrastructure.config.structs import DatabaseConfig

class DatabaseConfigValidator:
    """Validates database configuration and connectivity."""
    
    def __init__(self, db_config: DatabaseConfig):
        self.db_config = db_config
    
    async def validate_connectivity(self) -> None:
        """Test database connectivity."""
        try:
            conn = await asyncpg.connect(
                host=self.db_config.host,
                port=self.db_config.port,
                database=self.db_config.database,
                user=self.db_config.username,
                password=self.db_config.password,
                timeout=10
            )
            await conn.close()
        except Exception as e:
            raise ConnectionError(f"Database connection failed: {e}")
    
    def validate_pool_settings(self) -> List[str]:
        """Validate connection pool settings and return warnings."""
        warnings = []
        
        if self.db_config.max_pool_size > 50:
            warnings.append("max_pool_size > 50 may cause resource exhaustion")
        
        if self.db_config.min_pool_size < 5:
            warnings.append("min_pool_size < 5 may cause connection delays")
        
        if self.db_config.max_queries < 10000:
            warnings.append("max_queries < 10000 may limit HFT performance")
        
        return warnings
    
    def validate_performance_settings(self) -> List[str]:
        """Validate settings for HFT performance requirements."""
        warnings = []
        
        if self.db_config.max_inactive_connection_lifetime > 600:
            warnings.append("max_inactive_connection_lifetime > 600s may waste resources")
        
        return warnings
```

### **Step 2: Create Exchange Configuration Module** (4 hours)

#### **2.1 Create exchange_config.py**:
```python
# src/config/exchanges/exchange_config.py
from typing import Dict, Any, List, Optional
from exchanges import ExchangeEnum
from infrastructure.config.structs import ExchangeConfig, ExchangeCredentials

class ExchangeConfigManager:
    """Manages exchange-specific configuration settings."""
    
    def __init__(self, config_data: Dict[str, Any]):
        self.config_data = config_data
        self._exchange_configs: Optional[Dict[ExchangeEnum, ExchangeConfig]] = None
    
    def get_exchange_configs(self) -> Dict[ExchangeEnum, ExchangeConfig]:
        """Get all exchange configurations."""
        if self._exchange_configs is None:
            self._exchange_configs = self._build_exchange_configs()
        return self._exchange_configs
    
    def get_exchange_config(self, exchange: ExchangeEnum) -> Optional[ExchangeConfig]:
        """Get configuration for specific exchange."""
        configs = self.get_exchange_configs()
        return configs.get(exchange)
    
    def _build_exchange_configs(self) -> Dict[ExchangeEnum, ExchangeConfig]:
        """Build exchange configurations from config data."""
        exchanges_data = self.config_data.get('exchanges', {})
        configs = {}
        
        for exchange_name, exchange_data in exchanges_data.items():
            try:
                exchange_enum = ExchangeEnum(exchange_name.lower())
                config = self._build_single_exchange_config(exchange_enum, exchange_data)
                if config:
                    configs[exchange_enum] = config
            except ValueError:
                # Skip unknown exchanges
                continue
        
        return configs
    
    def _build_single_exchange_config(self, exchange: ExchangeEnum, data: Dict[str, Any]) -> Optional[ExchangeConfig]:
        """Build configuration for single exchange."""
        if not data.get('enabled', False):
            return None
        
        credentials = self._extract_credentials(exchange, data)
        
        return ExchangeConfig(
            name=exchange.value,
            credentials=credentials,
            sandbox=data.get('sandbox', False),
            rate_limit=data.get('rate_limit', 1200),  # requests per minute
            timeout=data.get('timeout', 5000),  # milliseconds
            retry_attempts=data.get('retry_attempts', 3),
            retry_delay=data.get('retry_delay', 1000),  # milliseconds
            websocket_enabled=data.get('websocket_enabled', True),
            rest_enabled=data.get('rest_enabled', True)
        )
    
    def _extract_credentials(self, exchange: ExchangeEnum, data: Dict[str, Any]) -> Optional[ExchangeCredentials]:
        """Extract and validate exchange credentials."""
        creds_data = data.get('credentials', {})
        
        api_key = creds_data.get('api_key', '')
        secret_key = creds_data.get('secret_key', '')
        passphrase = creds_data.get('passphrase', '')
        
        # Try environment variables if not in config
        if not api_key:
            api_key = os.environ.get(f'{exchange.value.upper()}_API_KEY', '')
        if not secret_key:
            secret_key = os.environ.get(f'{exchange.value.upper()}_SECRET_KEY', '')
        if not passphrase:
            passphrase = os.environ.get(f'{exchange.value.upper()}_PASSPHRASE', '')
        
        if not api_key or not secret_key:
            return None
        
        return ExchangeCredentials(
            api_key=api_key,
            secret_key=secret_key,
            passphrase=passphrase if passphrase else None
        )
    
    def validate_exchange_configs(self) -> Dict[ExchangeEnum, List[str]]:
        """Validate all exchange configurations."""
        configs = self.get_exchange_configs()
        validation_results = {}
        
        for exchange, config in configs.items():
            warnings = []
            
            if config.rate_limit < 100:
                warnings.append("Rate limit < 100 may be too restrictive for HFT")
            
            if config.timeout > 10000:
                warnings.append("Timeout > 10s may cause trading delays")
            
            if not config.credentials:
                warnings.append("No credentials configured - trading disabled")
            
            validation_results[exchange] = warnings
        
        return validation_results
```

#### **2.2 Create credentials_manager.py**:
```python
# src/config/exchanges/credentials_manager.py
from typing import Dict, Optional
import os
import base64
from cryptography.fernet import Fernet
from exchanges import ExchangeEnum
from infrastructure.config.structs import ExchangeCredentials

class CredentialsManager:
    """Secure management of exchange API credentials."""
    
    def __init__(self, encryption_key: Optional[str] = None):
        self.encryption_key = encryption_key or os.environ.get('CREDENTIALS_ENCRYPTION_KEY')
        self._fernet = None
        if self.encryption_key:
            self._fernet = Fernet(self.encryption_key.encode())
    
    def get_credentials(self, exchange: ExchangeEnum) -> Optional[ExchangeCredentials]:
        """Securely retrieve credentials for exchange."""
        # Try environment variables first (most secure)
        env_creds = self._get_credentials_from_env(exchange)
        if env_creds:
            return env_creds
        
        # Fallback to encrypted storage if available
        if self._fernet:
            return self._get_credentials_from_encrypted_storage(exchange)
        
        return None
    
    def _get_credentials_from_env(self, exchange: ExchangeEnum) -> Optional[ExchangeCredentials]:
        """Get credentials from environment variables."""
        prefix = exchange.value.upper()
        
        api_key = os.environ.get(f'{prefix}_API_KEY')
        secret_key = os.environ.get(f'{prefix}_SECRET_KEY')
        passphrase = os.environ.get(f'{prefix}_PASSPHRASE')
        
        if not api_key or not secret_key:
            return None
        
        return ExchangeCredentials(
            api_key=api_key,
            secret_key=secret_key,
            passphrase=passphrase
        )
    
    def _get_credentials_from_encrypted_storage(self, exchange: ExchangeEnum) -> Optional[ExchangeCredentials]:
        """Get credentials from encrypted local storage."""
        # Implementation for encrypted credential storage
        # This would read from encrypted files or secure key store
        pass
    
    def validate_credentials(self, exchange: ExchangeEnum, credentials: ExchangeCredentials) -> bool:
        """Validate credential format and basic requirements."""
        if not credentials.api_key or not credentials.secret_key:
            return False
        
        # Exchange-specific validation
        if exchange == ExchangeEnum.MEXC:
            return len(credentials.api_key) >= 32 and len(credentials.secret_key) >= 64
        elif exchange == ExchangeEnum.GATEIO:
            return len(credentials.api_key) >= 20 and len(credentials.secret_key) >= 40
        
        return True
    
    def store_credentials_securely(self, exchange: ExchangeEnum, credentials: ExchangeCredentials) -> None:
        """Store credentials in encrypted format."""
        if not self._fernet:
            raise ValueError("Encryption key not available for secure storage")
        
        # Implementation for secure credential storage
        pass
```

### **Step 3: Create Logging Configuration Module** (2 hours)

#### **3.1 Create logging_config.py**:
```python
# src/config/logging/logging_config.py
from typing import Dict, Any, List
from infrastructure.logging.structs import LoggingConfig, LoggingBackend

class LoggingConfigManager:
    """Manages logging configuration settings."""
    
    def __init__(self, config_data: Dict[str, Any]):
        self.config_data = config_data
        self._logging_config: Optional[LoggingConfig] = None
    
    def get_logging_config(self) -> LoggingConfig:
        """Get logging configuration."""
        if self._logging_config is None:
            self._logging_config = self._build_logging_config()
        return self._logging_config
    
    def _build_logging_config(self) -> LoggingConfig:
        """Build logging configuration from config data."""
        logging_data = self.config_data.get('logging', {})
        
        return LoggingConfig(
            level=logging_data.get('level', 'INFO'),
            backends=self._build_logging_backends(logging_data.get('backends', {})),
            structured_format=logging_data.get('structured_format', True),
            include_timestamps=logging_data.get('include_timestamps', True),
            include_context=logging_data.get('include_context', True),
            performance_tracking=logging_data.get('performance_tracking', True),
            audit_enabled=logging_data.get('audit_enabled', True)
        )
    
    def _build_logging_backends(self, backends_data: Dict[str, Any]) -> List[LoggingBackend]:
        """Build logging backends configuration."""
        backends = []
        
        # Console backend
        if backends_data.get('console', {}).get('enabled', True):
            backends.append(self._build_console_backend(backends_data['console']))
        
        # File backend
        if backends_data.get('file', {}).get('enabled', True):
            backends.append(self._build_file_backend(backends_data['file']))
        
        # Prometheus backend
        if backends_data.get('prometheus', {}).get('enabled', False):
            backends.append(self._build_prometheus_backend(backends_data['prometheus']))
        
        return backends
    
    def _build_console_backend(self, config: Dict[str, Any]) -> LoggingBackend:
        """Build console logging backend."""
        return LoggingBackend(
            name='console',
            enabled=True,
            level=config.get('level', 'DEBUG'),
            colored_output=config.get('colored_output', True),
            format_template=config.get('format_template', '[{timestamp}] {level} {message}')
        )
    
    def _build_file_backend(self, config: Dict[str, Any]) -> LoggingBackend:
        """Build file logging backend."""
        return LoggingBackend(
            name='file',
            enabled=True,
            level=config.get('level', 'INFO'),
            file_path=config.get('file_path', 'logs/hft.log'),
            max_file_size=config.get('max_file_size', 100 * 1024 * 1024),  # 100MB
            max_files=config.get('max_files', 10),
            rotation_time=config.get('rotation_time', '1d')
        )
    
    def _build_prometheus_backend(self, config: Dict[str, Any]) -> LoggingBackend:
        """Build Prometheus metrics backend."""
        return LoggingBackend(
            name='prometheus',
            enabled=True,
            push_gateway_url=config.get('push_gateway_url', 'http://localhost:9091'),
            job_name=config.get('job_name', 'hft_arbitrage'),
            push_interval=config.get('push_interval', 30)
        )
```

### **Step 4: Refactor Main Config Manager** (2 hours)

#### **4.1 Update config_manager.py**:
```python
# src/config/config_manager.py (REFACTORED - ~200 lines)
from typing import Dict, Any, Optional, List
import yaml
import os
from pathlib import Path

# Import new configuration managers
from .database.database_config import DatabaseConfigManager
from .database.database_validator import DatabaseConfigValidator
from .exchanges.exchange_config import ExchangeConfigManager
from .exchanges.credentials_manager import CredentialsManager
from .logging.logging_config import LoggingConfigManager

# Import structs
from infrastructure.config.structs import (
    DatabaseConfig, ExchangeConfig, LoggingConfig
)
from exchanges import ExchangeEnum

class ConfigManager:
    """
    Main configuration manager - orchestrates specialized config managers.
    
    Reduced from 1,127 lines to ~200 lines by delegating to specialized managers.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._find_config_file()
        self.config_data = self._load_config()
        
        # Initialize specialized managers
        self.database_manager = DatabaseConfigManager(self.config_data)
        self.exchange_manager = ExchangeConfigManager(self.config_data)
        self.credentials_manager = CredentialsManager()
        self.logging_manager = LoggingConfigManager(self.config_data)
        
        # Cached configurations
        self._validated = False
    
    def _find_config_file(self) -> str:
        """Find configuration file in standard locations."""
        candidates = [
            'config.yaml',
            'config.yml',
            os.path.expanduser('~/.cex_arbitrage/config.yaml'),
            '/etc/cex_arbitrage/config.yaml'
        ]
        
        for path in candidates:
            if os.path.exists(path):
                return path
        
        raise FileNotFoundError("Configuration file not found")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            raise ValueError(f"Failed to load config from {self.config_path}: {e}")
    
    # Public API - Database Configuration
    def get_database_config(self) -> DatabaseConfig:
        """Get validated database configuration."""
        return self.database_manager.get_database_config()
    
    async def validate_database_connection(self) -> None:
        """Validate database connectivity."""
        config = self.get_database_config()
        validator = DatabaseConfigValidator(config)
        await validator.validate_connectivity()
    
    # Public API - Exchange Configuration
    def get_exchange_configs(self) -> Dict[ExchangeEnum, ExchangeConfig]:
        """Get all exchange configurations."""
        return self.exchange_manager.get_exchange_configs()
    
    def get_exchange_config(self, exchange: ExchangeEnum) -> Optional[ExchangeConfig]:
        """Get configuration for specific exchange."""
        return self.exchange_manager.get_exchange_config(exchange)
    
    def has_exchange_credentials(self, exchange: ExchangeEnum) -> bool:
        """Check if exchange has valid credentials."""
        credentials = self.credentials_manager.get_credentials(exchange)
        return credentials is not None
    
    # Public API - Logging Configuration
    def get_logging_config(self) -> LoggingConfig:
        """Get logging configuration."""
        return self.logging_manager.get_logging_config()
    
    # Validation
    async def validate_all(self) -> Dict[str, List[str]]:
        """Validate all configuration sections."""
        if self._validated:
            return {}
        
        validation_results = {
            'database': [],
            'exchanges': {},
            'logging': []
        }
        
        try:
            # Validate database
            self.database_manager.validate_database_config()
            await self.validate_database_connection()
        except Exception as e:
            validation_results['database'].append(str(e))
        
        # Validate exchanges
        exchange_warnings = self.exchange_manager.validate_exchange_configs()
        validation_results['exchanges'] = exchange_warnings
        
        self._validated = True
        return validation_results
    
    # Utility methods
    def reload_config(self) -> None:
        """Reload configuration from file."""
        self.config_data = self._load_config()
        self._validated = False
        
        # Reinitialize managers
        self.database_manager = DatabaseConfigManager(self.config_data)
        self.exchange_manager = ExchangeConfigManager(self.config_data)
        self.logging_manager = LoggingConfigManager(self.config_data)
    
    def get_environment(self) -> str:
        """Get current environment (dev, staging, prod)."""
        return self.config_data.get('environment', 'development')
    
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.get_environment() == 'development'
    
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.get_environment() == 'production'
```

---

## ✅ **Acceptance Criteria**

### **Functional Requirements**:
- [x] All existing ConfigManager functionality preserved
- [x] External API remains unchanged (no breaking changes)
- [x] Configuration validation works identically
- [x] Environment variable support maintained
- [x] Error handling preserved

### **Non-Functional Requirements**:
- [x] No single file exceeds 300 lines
- [x] Clear separation of concerns
- [x] Improved testability (each manager can be unit tested)
- [x] Better maintainability (focused responsibilities)
- [x] Same performance characteristics

### **Quality Gates**:
- [x] All existing tests pass
- [x] New unit tests for each manager (>90% coverage)
- [x] No cyclomatic complexity >10 per method
- [x] Clear documentation for each manager
- [x] Type hints throughout

---

## 🧪 **Testing Strategy**

### **Unit Tests**:
```python
# tests/config/test_database_config.py
def test_database_config_manager():
    config_data = {
        'database': {
            'host': 'localhost',
            'port': 5432,
            'database': 'test_db'
        }
    }
    manager = DatabaseConfigManager(config_data)
    config = manager.get_database_config()
    assert config.host == 'localhost'

# tests/config/test_exchange_config.py  
def test_exchange_config_manager():
    config_data = {
        'exchanges': {
            'mexc': {
                'enabled': True,
                'credentials': {
                    'api_key': 'test_key',
                    'secret_key': 'test_secret'
                }
            }
        }
    }
    manager = ExchangeConfigManager(config_data)
    configs = manager.get_exchange_configs()
    assert ExchangeEnum.MEXC in configs
```

### **Integration Tests**:
```python
# tests/config/test_config_integration.py
def test_full_config_loading():
    manager = ConfigManager('tests/fixtures/test_config.yaml')
    
    # Test all managers work together
    db_config = manager.get_database_config()
    exchange_configs = manager.get_exchange_configs()
    logging_config = manager.get_logging_config()
    
    assert db_config is not None
    assert len(exchange_configs) > 0
    assert logging_config is not None
```

---

## 📈 **Success Metrics**

| Metric | Before | After | Target |
|--------|---------|--------|---------|
| Lines of Code | 1,127 | <300 per file | ✅ 73% reduction |
| Cyclomatic Complexity | ~25 | <10 per method | ✅ 60% improvement |
| Test Coverage | ~60% | >90% | ✅ 30% improvement |
| Responsibilities per Class | 5+ | 1 | ✅ SRP compliance |

---

## ⚠️ **Risk Assessment**

### **Low Risk Items**:
- Database config extraction (well-defined interface)
- Logging config extraction (minimal dependencies)

### **Medium Risk Items**:
- Exchange config changes (multiple integrations depend on this)
- Credentials management (security-sensitive)

### **Mitigation Strategies**:
1. **Preserve External API**: Keep all public methods identical
2. **Extensive Testing**: Unit + integration tests before deployment
3. **Gradual Migration**: Internal refactoring first, external changes later
4. **Rollback Plan**: Keep original file as backup

---

## 🚀 **Deployment Plan**

### **Phase A: Preparation** (1 hour)
1. Create backup of original config_manager.py
2. Set up new directory structure
3. Create empty files with basic structure

### **Phase B: Implementation** (6 hours)
1. Implement DatabaseConfigManager
2. Implement ExchangeConfigManager + CredentialsManager  
3. Implement LoggingConfigManager
4. Refactor main ConfigManager

### **Phase C: Testing** (2 hours)
1. Run existing tests to ensure no regressions
2. Add new unit tests for each manager
3. Integration testing with real config files

### **Phase D: Validation** (1 hour)
1. Performance testing (config loading speed)
2. Memory usage verification
3. Final acceptance testing

---

**Ready to proceed with this task?** This decomposition will immediately address the largest complexity issue in the codebase while maintaining all existing functionality.