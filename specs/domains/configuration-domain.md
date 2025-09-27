# Configuration Domain Implementation Guide

Business-focused implementation patterns for system configuration, exchange settings, and performance tuning optimized for operational excellence in the CEX Arbitrage Engine.

## Domain Overview

### **Primary Business Responsibility**
Unified configuration management enabling dynamic exchange support, environment isolation, and HFT performance optimization across all system domains.

### **Core Business Value**
- **Dynamic exchange integration** - Add new exchanges without code changes
- **Environment isolation** - Secure dev/prod/test configuration separation
- **Performance optimization** - HFT-tuned settings for sub-millisecond operations
- **Operational flexibility** - Hot-reload capabilities for non-critical settings

## Implementation Architecture

### **Domain Component Structure**

```
Configuration Domain (Business Logic Focus)
├── Unified Configuration Manager
│   ├── YAML configuration parsing (<10ms)
│   ├── Environment variable injection
│   ├── Schema validation and compliance
│   └── Hot-reload for runtime updates
│
├── Exchange Configuration System
│   ├── Multi-exchange credential management
│   ├── API endpoint configuration
│   ├── Trading rule specifications
│   └── Fee structure definitions
│
├── Performance Tuning Engine
│   ├── HFT-optimized parameter sets
│   ├── Latency target configurations
│   ├── Connection pool sizing
│   └── Timeout and retry settings
│
└── Environment Management System
    ├── Development environment configs
    ├── Production security settings
    ├── Test environment isolation
    └── Configuration validation pipelines
```

### **Core Implementation Patterns**

#### **1. Unified Configuration Management**

```python
# Central configuration manager with business logic focus
class ConfigurationManager:
    def __init__(self):
        self._config_cache = {}  # Static config only - NO trading data
        self._environment = self._detect_environment()
        self._config_file_path = self._get_config_file_path()
        
    async def initialize(self) -> None:
        """Initialize configuration system with performance monitoring"""
        start_time = time.time()
        
        # Load and validate configuration
        await self._load_base_configuration()
        await self._inject_environment_variables()
        await self._validate_configuration_schema()
        await self._apply_environment_specific_overrides()
        
        load_time_ms = (time.time() - start_time) * 1000
        
        # Monitor configuration loading performance
        if load_time_ms > 10:  # Target: <10ms
            await self.logger.warning(
                "Configuration loading exceeded target",
                tags={'load_time_ms': load_time_ms, 'target_ms': 10}
            )
        else:
            await self.logger.info(
                "Configuration loaded successfully",
                tags={'load_time_ms': load_time_ms, 'environment': self._environment}
            )
            
    async def get_exchange_config(self, exchange_name: str) -> ExchangeConfig:
        """Get exchange-specific configuration with business validation"""
        
        if exchange_name not in self._config_cache['exchanges']:
            raise ConfigurationError(f"Exchange '{exchange_name}' not configured")
            
        exchange_data = self._config_cache['exchanges'][exchange_name]
        
        # Create validated exchange configuration
        config = ExchangeConfig(
            name=exchange_name,
            api_key=exchange_data.get('api_key'),
            secret_key=exchange_data.get('secret_key'),
            base_url=exchange_data['base_url'],
            testnet=exchange_data.get('testnet', False),
            rate_limits=exchange_data.get('rate_limits', {}),
            trading_fees=exchange_data.get('trading_fees', {}),
            minimum_trade_amounts=exchange_data.get('minimum_trade_amounts', {})
        )
        
        # Validate business requirements
        await self._validate_exchange_config(config)
        
        return config
        
    async def _validate_exchange_config(self, config: ExchangeConfig) -> None:
        """Business logic validation for exchange configuration"""
        
        # 1. API credential validation (if provided)
        if config.api_key and config.secret_key:
            if not self._is_valid_credential_format(config.api_key, config.secret_key):
                raise ConfigurationError(f"Invalid credential format for {config.name}")
                
        # 2. URL validation
        if not self._is_valid_url(config.base_url):
            raise ConfigurationError(f"Invalid base URL for {config.name}: {config.base_url}")
            
        # 3. Business rule validation
        if config.testnet and self._environment == 'production':
            raise ConfigurationError(f"Testnet config not allowed in production: {config.name}")
            
        # 4. Performance validation
        if not config.rate_limits:
            await self.logger.warning(
                "No rate limits configured - may impact performance",
                tags={'exchange': config.name}
            )

# SAFE: Static configuration caching (NO trading data)
# config_cache['exchanges'] = static_exchange_configs  # OK
# config_cache['symbol_mappings'] = static_mappings   # OK

# PROHIBITED: Trading data caching
# config_cache['balances'] = balance_data  # NEVER
# config_cache['orders'] = order_data      # NEVER
```

#### **2. Environment Variable Injection System**

```python
# Secure environment variable injection for credentials
class EnvironmentInjector:
    def __init__(self):
        self._env_pattern = re.compile(r'\$\{([^}]+)\}')
        self._required_vars = set()
        self._optional_vars = set()
        
    def inject_environment_variables(self, config_data: dict) -> dict:
        """Recursively inject environment variables into configuration"""
        return self._inject_recursive(config_data)
        
    def _inject_recursive(self, obj):
        """Recursive environment variable injection"""
        if isinstance(obj, dict):
            return {key: self._inject_recursive(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._inject_recursive(item) for item in obj]
        elif isinstance(obj, str):
            return self._inject_string_variables(obj)
        else:
            return obj
            
    def _inject_string_variables(self, value: str) -> str:
        """Inject environment variables in string values"""
        
        def replace_var(match):
            var_name = match.group(1)
            
            # Check for default value syntax: ${VAR_NAME:default_value}
            if ':' in var_name:
                var_name, default_value = var_name.split(':', 1)
                env_value = os.getenv(var_name, default_value)
            else:
                env_value = os.getenv(var_name)
                
                if env_value is None:
                    raise ConfigurationError(
                        f"Required environment variable '{var_name}' not set"
                    )
                    
            # Track variable usage for validation
            if env_value == os.getenv(var_name):
                self._required_vars.add(var_name)
            else:
                self._optional_vars.add(var_name)
                
            return env_value
            
        return self._env_pattern.sub(replace_var, value)
        
    def validate_environment_completeness(self) -> ValidationResult:
        """Validate all required environment variables are available"""
        
        missing_vars = []
        for var_name in self._required_vars:
            if not os.getenv(var_name):
                missing_vars.append(var_name)
                
        if missing_vars:
            return ValidationResult(
                success=False,
                message=f"Missing required environment variables: {', '.join(missing_vars)}"
            )
            
        return ValidationResult(success=True)

# Example configuration with environment injection
"""
exchanges:
  mexc:
    api_key: "${MEXC_API_KEY}"
    secret_key: "${MEXC_SECRET_KEY}"
    base_url: "${MEXC_BASE_URL:https://api.mexc.com}"
    testnet: "${MEXC_TESTNET:false}"
"""
```

#### **3. HFT Performance Configuration**

```python
# HFT-optimized configuration management
class HFTPerformanceConfig:
    def __init__(self):
        self.performance_targets = {
            'symbol_resolution_us': 1.0,       # <1μs target
            'logging_latency_us': 1000.0,      # <1ms target  
            'execution_latency_ms': 50.0,      # <50ms target
            'api_response_ms': 100.0,          # <100ms target
            'config_load_ms': 10.0             # <10ms target
        }
        
    def get_hft_optimized_settings(self, component: str) -> dict:
        """Get HFT-optimized settings for specific components"""
        
        if component == 'networking':
            return {
                'connection_pool_size': 100,
                'connection_timeout_ms': 5000,
                'read_timeout_ms': 10000,
                'keepalive_timeout_ms': 30000,
                'max_retries': 3,
                'retry_backoff_ms': 100
            }
            
        elif component == 'logging':
            return {
                'ring_buffer_size': 10000,
                'batch_size': 100,
                'flush_interval_ms': 100,
                'async_dispatch': True,
                'compression_enabled': False  # Optimize for speed over space
            }
            
        elif component == 'websocket':
            return {
                'ping_interval_s': 30,
                'ping_timeout_s': 10,
                'close_timeout_s': 5,
                'auto_reconnect': True,
                'reconnect_backoff_ms': 1000,
                'max_reconnect_attempts': 10
            }
            
        elif component == 'caching':
            return {
                'symbol_cache_size': 10000,
                'symbol_cache_ttl_s': 3600,     # 1 hour for static data
                'config_cache_ttl_s': 86400,    # 24 hours for config data
                # NO caching for trading data - handled by policy
            }
            
        else:
            raise ConfigurationError(f"No HFT settings for component: {component}")
            
    def validate_performance_compliance(self, metrics: dict) -> ComplianceResult:
        """Validate system performance against HFT targets"""
        
        violations = []
        
        for metric_name, target_value in self.performance_targets.items():
            actual_value = metrics.get(metric_name)
            
            if actual_value is None:
                violations.append(f"Missing metric: {metric_name}")
                continue
                
            if actual_value > target_value:
                violations.append(
                    f"{metric_name}: {actual_value:.2f} exceeds target {target_value:.2f}"
                )
                
        if violations:
            return ComplianceResult(
                compliant=False,
                violations=violations,
                recommendation="Review performance optimization settings"
            )
            
        return ComplianceResult(compliant=True)
```

#### **4. Dynamic Exchange Configuration**

```python
# Dynamic exchange addition without code changes
class DynamicExchangeManager:
    def __init__(self, config_manager: ConfigurationManager):
        self.config_manager = config_manager
        self.supported_exchanges = {}
        
    async def register_exchange(self, 
                               exchange_name: str, 
                               implementation_class: str,
                               config_template: dict) -> None:
        """Dynamically register new exchange implementation"""
        
        # Validate implementation class exists
        if not self._validate_implementation_class(implementation_class):
            raise ConfigurationError(f"Implementation class not found: {implementation_class}")
            
        # Validate configuration template
        template_validation = self._validate_config_template(config_template)
        if not template_validation.valid:
            raise ConfigurationError(f"Invalid config template: {template_validation.errors}")
            
        # Register exchange
        self.supported_exchanges[exchange_name] = {
            'implementation_class': implementation_class,
            'config_template': config_template,
            'registration_time': time.time()
        }
        
        await self.logger.info(
            "Exchange registered successfully",
            tags={
                'exchange_name': exchange_name,
                'implementation_class': implementation_class
            }
        )
        
    def get_exchange_implementation_class(self, exchange_name: str) -> str:
        """Get implementation class for exchange"""
        
        if exchange_name not in self.supported_exchanges:
            raise ConfigurationError(f"Exchange not registered: {exchange_name}")
            
        return self.supported_exchanges[exchange_name]['implementation_class']
        
    def create_exchange_config_template(self, exchange_name: str) -> dict:
        """Create configuration template for new exchange"""
        
        template = {
            'api_key': f"${{{exchange_name.upper()}_API_KEY}}",
            'secret_key': f"${{{exchange_name.upper()}_SECRET_KEY}}",
            'base_url': f"${{{exchange_name.upper()}_BASE_URL}}",
            'testnet': f"${{{exchange_name.upper()}_TESTNET:false}}",
            'rate_limits': {
                'requests_per_second': 10,
                'orders_per_second': 5
            },
            'trading_fees': {
                'maker': 0.001,
                'taker': 0.001
            },
            'minimum_trade_amounts': {}
        }
        
        return template

# Example: Adding new exchange through configuration
"""
# In config.yaml
exchanges:
  new_exchange:
    api_key: "${NEW_EXCHANGE_API_KEY}"
    secret_key: "${NEW_EXCHANGE_SECRET_KEY}"
    base_url: "https://api.newexchange.com"
    testnet: false
    
# In factory registration
factory.register_exchange(
    'new_exchange',
    'exchanges.integrations.new_exchange.NewExchangeUnifiedExchange'
)
"""
```

## Business Logic Validation Patterns

### **Configuration Validation Rules**

```python
class ConfigurationValidator:
    def __init__(self):
        self.business_rules = [
            self._validate_security_requirements,
            self._validate_performance_requirements,
            self._validate_trading_requirements,
            self._validate_operational_requirements
        ]
        
    async def validate_complete_configuration(self, config: dict) -> ValidationResult:
        """Comprehensive configuration validation"""
        
        validation_results = []
        
        # Run all business rule validations
        for rule in self.business_rules:
            result = await rule(config)
            validation_results.append(result)
            
        # Aggregate results
        failed_validations = [r for r in validation_results if not r.success]
        
        if failed_validations:
            error_messages = [r.message for r in failed_validations]
            return ValidationResult(
                success=False,
                message=f"Configuration validation failed: {'; '.join(error_messages)}"
            )
            
        return ValidationResult(success=True, message="Configuration validated successfully")
        
    async def _validate_security_requirements(self, config: dict) -> ValidationResult:
        """Validate security-related configuration"""
        
        # 1. Credential management validation
        for exchange_name, exchange_config in config.get('exchanges', {}).items():
            if 'api_key' in exchange_config:
                # Ensure credentials use environment variables
                if not exchange_config['api_key'].startswith('${'):
                    return ValidationResult(
                        success=False,
                        message=f"API key for {exchange_name} must use environment variable"
                    )
                    
        # 2. Production security validation
        if config.get('environment') == 'production':
            # Ensure no testnet configurations in production
            for exchange_name, exchange_config in config.get('exchanges', {}).items():
                if exchange_config.get('testnet', False):
                    return ValidationResult(
                        success=False,
                        message=f"Testnet configuration not allowed in production: {exchange_name}"
                    )
                    
        return ValidationResult(success=True)
        
    async def _validate_performance_requirements(self, config: dict) -> ValidationResult:
        """Validate HFT performance configuration"""
        
        # Validate connection pool sizes
        networking_config = config.get('networking', {})
        pool_size = networking_config.get('connection_pool_size', 0)
        
        if pool_size < 50:
            return ValidationResult(
                success=False,
                message=f"Connection pool size too small for HFT: {pool_size} (minimum: 50)"
            )
            
        # Validate timeout settings
        timeouts = networking_config.get('timeouts', {})
        api_timeout = timeouts.get('api_timeout_ms', float('inf'))
        
        if api_timeout > 5000:  # 5 second max for HFT
            return ValidationResult(
                success=False,
                message=f"API timeout too high for HFT: {api_timeout}ms (maximum: 5000ms)"
            )
            
        return ValidationResult(success=True)
        
    async def _validate_trading_requirements(self, config: dict) -> ValidationResult:
        """Validate trading-specific configuration"""
        
        trading_config = config.get('trading', {})
        
        # Validate minimum profit thresholds
        min_profit = trading_config.get('min_profit_threshold', 0)
        if min_profit <= 0:
            return ValidationResult(
                success=False,
                message="Minimum profit threshold must be positive"
            )
            
        # Validate risk limits
        risk_limits = trading_config.get('risk_limits', {})
        max_position = risk_limits.get('max_position_per_asset', 0)
        
        if max_position <= 0:
            return ValidationResult(
                success=False,
                message="Maximum position per asset must be positive"
            )
            
        return ValidationResult(success=True)
```

## Hot-Reload and Runtime Configuration

### **Safe Configuration Updates**

```python
# Safe configuration hot-reload for non-critical settings
class ConfigurationHotReloader:
    def __init__(self, config_manager: ConfigurationManager):
        self.config_manager = config_manager
        self.hot_reload_enabled_sections = {
            'logging',          # Safe to update logging levels
            'monitoring',       # Safe to update monitoring settings
            'risk_limits',      # Safe to update risk parameters
            'performance_tuning'  # Safe to update performance parameters
        }
        self.requires_restart_sections = {
            'exchanges',        # Exchange config requires restart
            'networking',       # Connection changes require restart
            'security'          # Security changes require restart
        }
        
    async def update_configuration(self, 
                                 section: str, 
                                 new_config: dict) -> UpdateResult:
        """Update configuration section with safety validation"""
        
        # 1. Validate update safety
        if section in self.requires_restart_sections:
            return UpdateResult(
                success=False,
                message=f"Section '{section}' requires system restart",
                restart_required=True
            )
            
        if section not in self.hot_reload_enabled_sections:
            return UpdateResult(
                success=False,
                message=f"Hot-reload not supported for section '{section}'"
            )
            
        # 2. Validate new configuration
        validation_result = await self._validate_section_config(section, new_config)
        if not validation_result.success:
            return UpdateResult(
                success=False,
                message=f"Configuration validation failed: {validation_result.message}"
            )
            
        # 3. Apply configuration update
        try:
            old_config = await self.config_manager.get_section_config(section)
            await self.config_manager.update_section_config(section, new_config)
            
            # 4. Notify affected components
            await self._notify_configuration_change(section, old_config, new_config)
            
            await self.logger.info(
                "Configuration updated successfully",
                tags={
                    'section': section,
                    'update_time': time.time()
                }
            )
            
            return UpdateResult(success=True, message="Configuration updated")
            
        except Exception as e:
            # Rollback on failure
            await self.config_manager.update_section_config(section, old_config)
            
            return UpdateResult(
                success=False,
                message=f"Configuration update failed: {str(e)}"
            )
            
    async def _notify_configuration_change(self, 
                                         section: str,
                                         old_config: dict,
                                         new_config: dict) -> None:
        """Notify components of configuration changes"""
        
        change_event = ConfigurationChangeEvent(
            section=section,
            old_config=old_config,
            new_config=new_config,
            timestamp=time.time()
        )
        
        # Publish to event bus for component updates
        await self.event_bus.publish('config.section_updated', change_event)
```

## Integration with Other Domains

### **Configuration → All Domains Integration**

```python
# Configuration provides settings to all other domains
class DomainConfigurationProvider:
    def __init__(self, config_manager: ConfigurationManager):
        self.config_manager = config_manager
        
    async def get_market_data_config(self) -> MarketDataConfig:
        """Provide configuration for Market Data Domain"""
        
        config_data = await self.config_manager.get_section_config('market_data')
        
        return MarketDataConfig(
            max_data_age_seconds=config_data.get('max_data_age_seconds', 5),
            symbol_cache_size=config_data.get('symbol_cache_size', 10000),
            websocket_ping_interval=config_data.get('websocket_ping_interval', 30),
            opportunity_detection_threshold=config_data.get('opportunity_threshold', 0.50)
        )
        
    async def get_trading_config(self) -> TradingConfig:
        """Provide configuration for Trading Domain"""
        
        config_data = await self.config_manager.get_section_config('trading')
        
        return TradingConfig(
            max_position_per_asset=config_data.get('max_position_per_asset', 10000.0),
            max_total_exposure=config_data.get('max_total_exposure', 50000.0),
            execution_timeout_ms=config_data.get('execution_timeout_ms', 30000),
            max_slippage_percent=config_data.get('max_slippage_percent', 2.0),
            circuit_breaker_loss_limit=config_data.get('circuit_breaker_loss_limit', 1000.0)
        )
        
    async def get_infrastructure_config(self) -> InfrastructureConfig:
        """Provide configuration for Infrastructure Domain"""
        
        config_data = await self.config_manager.get_section_config('infrastructure')
        
        return InfrastructureConfig(
            logging_performance_target_us=config_data.get('logging_target_us', 1000),
            connection_pool_size=config_data.get('connection_pool_size', 100),
            retry_attempts=config_data.get('retry_attempts', 3),
            circuit_breaker_threshold=config_data.get('circuit_breaker_threshold', 0.01)
        )
```

## Performance Monitoring and Optimization

### **Configuration Performance Tracking**

```python
# Configuration domain performance monitoring
class ConfigurationMetrics:
    def __init__(self, hft_logger: HFTLogger):
        self.logger = hft_logger
        self.metrics = {
            'config_load_time': TimingMetric(),
            'validation_time': TimingMetric(),
            'hot_reload_time': TimingMetric(),
            'environment_injection_time': TimingMetric()
        }
        
    async def record_configuration_load(self, load_time_ms: float, success: bool):
        """Track configuration loading performance"""
        
        self.metrics['config_load_time'].record(load_time_ms)
        
        # Alert on performance degradation
        if load_time_ms > 10:  # Target: <10ms
            await self.logger.warning(
                "Configuration loading performance degraded",
                tags={
                    'load_time_ms': load_time_ms,
                    'target_ms': 10,
                    'success': success
                }
            )
        else:
            await self.logger.info(
                "Configuration loaded within target",
                tags={
                    'load_time_ms': load_time_ms,
                    'success': success
                }
            )
            
    async def record_validation_performance(self, validation_time_ms: float):
        """Track configuration validation performance"""
        
        self.metrics['validation_time'].record(validation_time_ms)
        
        # Business impact monitoring
        await self.logger.info(
            "Configuration validation completed",
            tags={'validation_time_ms': validation_time_ms}
        )
```

---

*This Configuration Domain implementation guide focuses on business-driven configuration management, dynamic exchange support, and HFT performance optimization for the CEX Arbitrage Engine.*

**Domain Focus**: Configuration management → Environment isolation → Performance optimization  
**Performance**: <10ms loading → Dynamic updates → HFT compliance  
**Business Value**: Operational flexibility → Security compliance → System reliability