"""
Configuration Manager

Handles all configuration loading, validation, and management for the arbitrage engine.
Follows Single Responsibility Principle - focused solely on configuration concerns.

HFT COMPLIANT: Fast configuration loading with validation caching.
"""

import logging
from typing import Dict, Any, List, Optional
from common.config import config, ConfigurationError
from arbitrage.types import (
    ArbitrageConfig, RiskLimits, OpportunityType, ExchangeName
)

logger = logging.getLogger(__name__)


class ConfigurationManager:
    """
    Manages arbitrage engine configuration lifecycle.
    
    Responsibilities:
    - Load configuration from various sources
    - Validate configuration parameters
    - Provide configuration access to other components
    """
    
    def __init__(self):
        self._config: Optional[ArbitrageConfig] = None
        self._raw_config: Dict[str, Any] = {}
        
    async def load_configuration(self, dry_run: bool = True) -> ArbitrageConfig:
        """
        Load and validate arbitrage configuration.
        
        HFT COMPLIANT: Configuration is loaded once and cached.
        
        Args:
            dry_run: Enable dry run mode (default: True for safety)
            
        Returns:
            Validated ArbitrageConfig instance
            
        Raises:
            ConfigurationError: If configuration is invalid
        """
        logger.info("Loading arbitrage engine configuration...")
        
        try:
            # Load from config system
            if not config.has_arbitrage_config():
                logger.warning("No arbitrage configuration found, using defaults")
                self._raw_config = self._get_default_config()
            else:
                self._raw_config = config.get_arbitrage_config()
            
            # Build configuration object
            self._config = self._build_config(self._raw_config, dry_run)
            
            # Validate configuration
            errors = self._config.validate()
            if errors:
                raise ConfigurationError(f"Configuration validation failed: {errors}")
            
            # Log configuration summary
            self._log_configuration_summary()
            
            return self._config
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise ConfigurationError(f"Configuration loading failed: {e}")
    
    def _build_config(self, raw_config: Dict[str, Any], dry_run: bool) -> ArbitrageConfig:
        """Build ArbitrageConfig from raw configuration dictionary."""
        
        # Extract risk limits
        risk_limits_dict = raw_config.get('risk_limits', {})
        risk_limits = RiskLimits(**{
            k: v for k, v in risk_limits_dict.items() 
            if k in RiskLimits.__dataclass_fields__
        })
        
        # Map opportunity types
        opportunity_types = []
        for ot_str in raw_config.get('enabled_opportunity_types', ['SPOT_SPOT']):
            try:
                opportunity_types.append(OpportunityType[ot_str])
            except KeyError:
                logger.warning(f"Unknown opportunity type: {ot_str}")
        
        # Get enabled exchanges
        enabled_exchanges = raw_config.get('enabled_exchanges', ['MEXC', 'GATEIO'])
        
        return ArbitrageConfig(
            engine_name=raw_config.get('engine_name', 'hft_arbitrage_main'),
            enabled_opportunity_types=opportunity_types,
            enabled_exchanges=enabled_exchanges,
            target_execution_time_ms=raw_config.get('target_execution_time_ms', 30),
            opportunity_scan_interval_ms=raw_config.get('opportunity_scan_interval_ms', 100),
            position_monitor_interval_ms=raw_config.get('position_monitor_interval_ms', 1000),
            balance_refresh_interval_ms=raw_config.get('balance_refresh_interval_ms', 5000),
            risk_limits=risk_limits,
            enable_risk_checks=raw_config.get('enable_risk_checks', True),
            enable_circuit_breakers=raw_config.get('enable_circuit_breakers', True),
            enable_websocket_feeds=raw_config.get('enable_websocket_feeds', True),
            websocket_fallback_to_rest=raw_config.get('websocket_fallback_to_rest', True),
            market_data_staleness_ms=raw_config.get('market_data_staleness_ms', 100),
            exchange_specific_configs=raw_config.get('exchange_configs', {}),
            enable_dry_run=dry_run if dry_run is not None else raw_config.get('enable_dry_run', True),
            enable_detailed_logging=raw_config.get('enable_detailed_logging', True),
            enable_performance_metrics=raw_config.get('enable_performance_metrics', True),
            enable_recovery_mode=raw_config.get('enable_recovery_mode', True),
        )
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration when no config file is present."""
        return {
            'engine_name': 'hft_arbitrage_default',
            'enabled_opportunity_types': ['SPOT_SPOT'],
            'enabled_exchanges': ['MEXC', 'GATEIO'],
            'target_execution_time_ms': 30,
            'opportunity_scan_interval_ms': 100,
            'enable_dry_run': True,
            'risk_limits': {
                'max_position_size_usd': 5000.0,
                'min_profit_margin_bps': 50,
            }
        }
    
    def _log_configuration_summary(self):
        """Log configuration summary for operational visibility."""
        if not self._config:
            return
            
        logger.info("Configuration loaded successfully:")
        logger.info(f"  Engine Name: {self._config.engine_name}")
        logger.info(f"  Dry Run Mode: {self._config.enable_dry_run}")
        logger.info(f"  Target Execution Time: {self._config.target_execution_time_ms}ms")
        logger.info(f"  Enabled Exchanges: {self._config.enabled_exchanges}")
        logger.info(f"  Max Position Size: ${self._config.risk_limits.max_position_size_usd:,.2f}")
        logger.info(f"  Min Profit Margin: {self._config.risk_limits.min_profit_margin_bps} bps")
        
        if self._config.enable_dry_run:
            logger.warning("DRY RUN MODE ENABLED - No real trades will be executed")
        else:
            logger.warning("LIVE TRADING MODE ENABLED - Real trades will be executed")
        
        if not self._config.is_hft_compliant:
            logger.warning("Configuration is NOT HFT compliant - performance may be impacted")
    
    @property
    def config(self) -> Optional[ArbitrageConfig]:
        """Get current configuration."""
        return self._config
    
    def get_exchange_config(self, exchange_name: str) -> Dict[str, Any]:
        """Get exchange-specific configuration."""
        if not self._config:
            return {}
        return self._config.exchange_specific_configs.get(exchange_name, {})