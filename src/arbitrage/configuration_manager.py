"""
Configuration Manager

Handles all configuration loading, validation, and management for the arbitrage engine.
Follows Single Responsibility Principle - focused solely on configuration concerns.

HFT COMPLIANT: Fast configuration loading with validation caching.
"""

import logging
from typing import Dict, Any, List, Optional
from decimal import Decimal
from common.config import config, ConfigurationError
from arbitrage.types import (
    ArbitrageConfig, RiskLimits, OpportunityType, ExchangeName,
    ArbitragePair, ExchangePairConfig, ArbitragePairMap, PairValidationResult
)
from arbitrage.symbol_resolver import SymbolResolver

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
        self._symbol_resolver: Optional[SymbolResolver] = None
        self._raw_pairs_config: List[Dict[str, Any]] = []
        
    async def load_configuration(self, dry_run: Optional[bool] = None) -> ArbitrageConfig:
        """
        Load and validate arbitrage configuration.
        
        HFT COMPLIANT: Configuration is loaded once and cached.
        
        Args:
            dry_run: Override dry run mode (default: None, uses config.yaml setting)
            
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
            
            # Load and validate arbitrage pairs
            self._load_arbitrage_pairs()
            
            # Build optimized pair map for HFT lookups
            self._build_pair_map()
            
            # Validate configuration
            errors = self._config.validate()
            if errors:
                raise ConfigurationError(f"Configuration validation failed: {errors}")
            
            # Validate all pairs
            pair_errors = self._validate_all_pairs()
            if pair_errors:
                raise ConfigurationError(f"Pair validation failed: {pair_errors}")
            
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
            enable_dry_run=raw_config.get('enable_dry_run', True) if dry_run is None else dry_run,
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
            },
            'arbitrage_pairs': []  # Empty pairs by default
        }
    
    def _load_arbitrage_pairs(self) -> None:
        """Load arbitrage pairs from simplified configuration."""
        # Note: Symbol resolver needs to be set up by controller after exchanges are initialized
        pairs_config = self._raw_config.get('arbitrage_pairs', [])
        
        # Store raw config for later processing
        self._raw_pairs_config = pairs_config
        logger.info(f"Found {len(pairs_config)} arbitrage pairs in config (pending symbol resolution)")
        for pair_dict in pairs_config[:3]:  # Log first 3
            logger.info(f"  - {pair_dict.get('id', 'unknown')}: {pair_dict.get('base_asset')}/{pair_dict.get('quote_asset')}")
    
    async def resolve_arbitrage_pairs(self, symbol_resolver: SymbolResolver) -> None:
        """
        Resolve arbitrage pairs using symbol resolver after exchanges are initialized.
        
        Args:
            symbol_resolver: Initialized symbol resolver with exchange info
        """
        logger.info("Resolving arbitrage pairs with auto-discovered symbol info...")
        self._symbol_resolver = symbol_resolver
        
        # Clear any existing pairs
        self._config.arbitrage_pairs = []
        
        for pair_dict in self._raw_pairs_config:
            try:
                pair = await self._symbol_resolver.build_arbitrage_pair(pair_dict)
                if pair:
                    self._config.arbitrage_pairs.append(pair)
                    logger.info(
                        f"Resolved pair: {pair.id} ({pair.base_asset}/{pair.quote_asset}) "
                        f"on {len(pair.exchanges)} exchanges"
                    )
                else:
                    logger.warning(f"Could not resolve pair: {pair_dict.get('id', 'unknown')}")
            except Exception as e:
                logger.error(f"Failed to resolve pair {pair_dict.get('id', 'unknown')}: {e}")
        
        # Rebuild pair map with resolved pairs
        self._build_pair_map()
        
        logger.info(f"Resolved {len(self._config.arbitrage_pairs)} arbitrage pairs successfully")
        if self._config.arbitrage_pairs:
            for pair in self._config.arbitrage_pairs[:3]:  # Log first 3
                logger.info(f"  ✅ {pair.id}: {pair.base_asset}/{pair.quote_asset} on {len(pair.exchanges)} exchanges")
    
    # Note: _build_arbitrage_pair is now handled by SymbolResolver.build_arbitrage_pair()
    
    def _build_pair_map(self) -> None:
        """Build optimized pair map for HFT lookups."""
        pair_map = ArbitragePairMap()
        
        for pair in self._config.arbitrage_pairs:
            pair_map.add_pair(pair)
        
        self._config.pair_map = pair_map
        logger.info(f"Built pair map with {len(pair_map.pairs_by_id)} pairs")
        logger.info(f"Active pairs: {len(pair_map.active_pair_ids)}")
    
    def _validate_all_pairs(self) -> List[str]:
        """Validate all arbitrage pairs."""
        all_errors = []
        
        for pair in self._config.arbitrage_pairs:
            errors = pair.validate()
            if errors:
                all_errors.extend([f"Pair {pair.id}: {error}" for error in errors])
        
        # Check for duplicate pair IDs
        pair_ids = [pair.id for pair in self._config.arbitrage_pairs]
        if len(pair_ids) != len(set(pair_ids)):
            all_errors.append("Duplicate pair IDs found")
        
        # Validate pairs against enabled exchanges
        for pair in self._config.arbitrage_pairs:
            for exchange in pair.exchanges.keys():
                if exchange not in self._config.enabled_exchanges:
                    all_errors.append(
                        f"Pair {pair.id} references exchange {exchange} which is not enabled"
                    )
        
        return all_errors
    
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
        
        # Log arbitrage pairs
        if self._config.arbitrage_pairs:
            logger.info(f"  Arbitrage Pairs: {len(self._config.arbitrage_pairs)} configured")
            for pair in self._config.arbitrage_pairs:
                if pair.is_enabled:
                    logger.info(f"    - {pair.id}: {pair.base_asset}/{pair.quote_asset} "
                              f"(min profit: {pair.min_profit_bps} bps, "
                              f"exchanges: {', '.join(pair.get_active_exchanges())})")
        else:
            logger.warning("  No arbitrage pairs configured")
        
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