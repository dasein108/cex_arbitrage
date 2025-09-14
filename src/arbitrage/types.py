"""
Arbitrage Types and Enumerations

Core type definitions for the HFT arbitrage engine.
Provides type-safe enumerations and data structures for arbitrage operations.

HFT COMPLIANT: All structures are immutable and optimized for performance.
"""

from __future__ import annotations
from enum import IntEnum
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from decimal import Decimal


class OpportunityType(IntEnum):
    """Types of arbitrage opportunities the engine can detect and execute."""
    SPOT_SPOT = 1  # Price differences between spot markets on different exchanges
    SPOT_FUTURES_HEDGE = 2  # Spot vs futures arbitrage with hedging
    TRIANGULAR = 3  # Three-way arbitrage within single exchange
    FUNDING_RATE = 4  # Funding rate arbitrage in perpetual futures
    OPTIONS_PARITY = 5  # Put-call parity arbitrage


class ExchangeName(IntEnum):
    """Supported cryptocurrency exchanges."""
    MEXC = 1
    GATEIO = 2
    BINANCE = 3  # Future expansion
    OKX = 4  # Future expansion
    
    @classmethod
    def from_string(cls, name: str) -> 'ExchangeName':
        """Convert string to ExchangeName enum."""
        mapping = {
            "MEXC": cls.MEXC,
            "GATEIO": cls.GATEIO,
            "BINANCE": cls.BINANCE,
            "OKX": cls.OKX
        }
        if name not in mapping:
            raise ValueError(f"Unknown exchange name: {name}")
        return mapping[name]
    
    def to_string(self) -> str:
        """Convert enum to string representation."""
        return self.name


@dataclass(frozen=True)
class RiskLimits:
    """Risk management limits for arbitrage operations."""
    max_position_size_usd: float = 5000.0
    max_total_exposure_usd: float = 25000.0
    max_exchange_exposure_usd: float = 15000.0
    max_symbol_exposure_usd: float = 10000.0
    max_daily_loss_usd: float = 2500.0
    max_single_loss_usd: float = 500.0
    min_profit_margin_bps: int = 50  # Minimum profit in basis points
    stop_loss_threshold_bps: int = 200
    max_execution_time_ms: int = 45000
    max_slippage_bps: int = 25
    max_partial_fill_ratio: float = 0.1
    max_concurrent_operations: int = 3
    max_price_deviation_bps: int = 100
    min_market_depth_usd: float = 50000.0
    max_spread_bps: int = 500
    volatility_circuit_breaker_bps: int = 1000
    max_recovery_attempts: int = 3
    recovery_timeout_seconds: int = 300
    emergency_close_threshold_bps: int = 500


@dataclass
class ArbitrageConfig:
    """Complete arbitrage engine configuration."""
    engine_name: str = 'hft_arbitrage_main'
    enabled_opportunity_types: List[OpportunityType] = field(default_factory=list)
    enabled_exchanges: List[str] = field(default_factory=list)
    
    # Arbitrage pairs configuration
    arbitrage_pairs: List[ArbitragePair] = field(default_factory=list)
    pair_map: Optional[ArbitragePairMap] = None  # Built after loading pairs
    target_execution_time_ms: int = 30
    opportunity_scan_interval_ms: int = 100
    position_monitor_interval_ms: int = 1000
    balance_refresh_interval_ms: int = 5000
    risk_limits: RiskLimits = field(default_factory=RiskLimits)
    enable_risk_checks: bool = True
    enable_circuit_breakers: bool = True
    enable_websocket_feeds: bool = True
    websocket_fallback_to_rest: bool = True
    market_data_staleness_ms: int = 100
    exchange_specific_configs: Dict[str, Any] = field(default_factory=dict)
    enable_dry_run: bool = True
    enable_detailed_logging: bool = True
    enable_performance_metrics: bool = True
    enable_recovery_mode: bool = True
    
    def validate(self) -> List[str]:
        """
        Validate configuration parameters.
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        if self.target_execution_time_ms <= 0:
            errors.append("target_execution_time_ms must be positive")
        
        if not self.enabled_exchanges:
            errors.append("At least one exchange must be enabled")
        
        if self.opportunity_scan_interval_ms <= 0:
            errors.append("opportunity_scan_interval_ms must be positive")
        
        if self.target_execution_time_ms > 50:
            errors.append("target_execution_time_ms exceeds HFT requirement (50ms)")
        
        # Validate risk limits
        if self.risk_limits.max_position_size_usd <= 0:
            errors.append("max_position_size_usd must be positive")
        
        if self.risk_limits.min_profit_margin_bps < 0:
            errors.append("min_profit_margin_bps cannot be negative")
        
        return errors
    
    @property
    def is_hft_compliant(self) -> bool:
        """Check if configuration meets HFT requirements."""
        return (
            self.target_execution_time_ms <= 50 and
            self.market_data_staleness_ms <= 100 and
            self.opportunity_scan_interval_ms <= 100
        )


@dataclass
class EngineStatistics:
    """Real-time statistics for the arbitrage engine."""
    opportunities_detected: int = 0
    opportunities_executed: int = 0
    total_realized_profit: float = 0.0
    average_execution_time_ms: float = 0.0
    success_rate: float = 0.0
    uptime_seconds: float = 0.0
    last_opportunity_time: Optional[float] = None
    active_positions: int = 0
    total_volume_traded: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert statistics to dictionary for logging."""
        return {
            'opportunities_detected': self.opportunities_detected,
            'opportunities_executed': self.opportunities_executed,
            'total_realized_profit': str(self.total_realized_profit),
            'average_execution_time_ms': self.average_execution_time_ms,
            'success_rate': self.success_rate,
            'uptime_seconds': self.uptime_seconds,
            'active_positions': self.active_positions,
            'total_volume_traded': self.total_volume_traded
        }


@dataclass(frozen=True)
class ExchangePairConfig:
    """
    Configuration for a trading pair on a specific exchange.
    
    HFT COMPLIANT: Immutable configuration loaded once at startup.
    """
    symbol: str  # Exchange-specific symbol format (e.g., "BTCUSDT" on MEXC, "BTC_USDT" on Gate.io)
    min_amount: Decimal  # Minimum trading amount in base asset
    max_amount: Decimal  # Maximum trading amount in base asset
    min_notional: Optional[Decimal] = None  # Minimum order value in quote asset
    price_precision: int = 8  # Decimal places for price
    amount_precision: int = 8  # Decimal places for amount
    maker_fee_bps: int = 10  # Maker fee in basis points (0.10% = 10 bps)
    taker_fee_bps: int = 10  # Taker fee in basis points
    is_active: bool = True  # Whether the pair is actively traded on this exchange
    
    def validate(self) -> List[str]:
        """Validate exchange pair configuration."""
        errors = []
        if self.min_amount <= 0:
            errors.append(f"min_amount must be positive: {self.min_amount}")
        if self.max_amount <= self.min_amount:
            errors.append(f"max_amount ({self.max_amount}) must be greater than min_amount ({self.min_amount})")
        if self.price_precision < 0 or self.price_precision > 18:
            errors.append(f"price_precision must be between 0 and 18: {self.price_precision}")
        if self.amount_precision < 0 or self.amount_precision > 18:
            errors.append(f"amount_precision must be between 0 and 18: {self.amount_precision}")
        if self.maker_fee_bps < 0:
            errors.append(f"maker_fee_bps cannot be negative: {self.maker_fee_bps}")
        if self.taker_fee_bps < 0:
            errors.append(f"taker_fee_bps cannot be negative: {self.taker_fee_bps}")
        return errors


@dataclass(frozen=True)
class ArbitragePair:
    """
    Definition of an arbitrage trading pair across multiple exchanges.
    
    HFT COMPLIANT: Immutable pair definition with pre-validated configurations.
    """
    id: str  # Unique identifier for the pair (e.g., "btc_usdt_arb_1")
    base_asset: str  # Base asset (e.g., "BTC")
    quote_asset: str  # Quote asset (e.g., "USDT")
    exchanges: Dict[str, ExchangePairConfig]  # Exchange-specific configurations
    opportunity_type: OpportunityType = OpportunityType.SPOT_SPOT  # Type of arbitrage
    min_profit_bps: int = 30  # Minimum profit threshold in basis points
    max_exposure_usd: Decimal = Decimal('10000')  # Maximum exposure for this pair
    is_enabled: bool = True  # Whether this pair is enabled for trading
    priority: int = 1  # Execution priority (lower = higher priority)
    
    def validate(self) -> List[str]:
        """Validate arbitrage pair configuration."""
        errors = []
        
        # Basic validation
        if not self.id:
            errors.append("Pair ID cannot be empty")
        if not self.base_asset:
            errors.append("Base asset cannot be empty")
        if not self.quote_asset:
            errors.append("Quote asset cannot be empty")
        
        # Exchange configuration validation
        if len(self.exchanges) < 2:
            errors.append(f"At least 2 exchanges required for arbitrage, got {len(self.exchanges)}")
        
        for exchange_name, config in self.exchanges.items():
            config_errors = config.validate()
            if config_errors:
                errors.extend([f"{exchange_name}: {error}" for error in config_errors])
        
        # Risk validation
        if self.min_profit_bps <= 0:
            errors.append(f"min_profit_bps must be positive: {self.min_profit_bps}")
        if self.max_exposure_usd <= 0:
            errors.append(f"max_exposure_usd must be positive: {self.max_exposure_usd}")
        
        return errors
    
    def get_exchange_symbols(self) -> Dict[str, str]:
        """Get exchange-specific symbols for this pair."""
        return {exchange: config.symbol for exchange, config in self.exchanges.items()}
    
    def get_min_trade_amount(self) -> Decimal:
        """Get the minimum trade amount across all exchanges."""
        return max(config.min_amount for config in self.exchanges.values())
    
    def get_max_trade_amount(self) -> Decimal:
        """Get the maximum trade amount across all exchanges."""
        return min(config.max_amount for config in self.exchanges.values())
    
    def get_active_exchanges(self) -> List[str]:
        """Get list of active exchanges for this pair."""
        return [name for name, config in self.exchanges.items() if config.is_active]


@dataclass
class ArbitragePairMap:
    """
    Optimized mapping structure for HFT pair lookups.
    
    HFT COMPLIANT: O(1) lookups for all pair queries.
    """
    pairs_by_id: Dict[str, ArbitragePair] = field(default_factory=dict)
    pairs_by_exchange: Dict[str, List[ArbitragePair]] = field(default_factory=dict)
    symbol_to_pairs: Dict[tuple[str, str], List[ArbitragePair]] = field(default_factory=dict)
    active_pair_ids: Set[str] = field(default_factory=set)
    
    def add_pair(self, pair: ArbitragePair) -> None:
        """Add a pair to the mapping structures."""
        # Add to ID map
        self.pairs_by_id[pair.id] = pair
        
        # Add to exchange map
        for exchange in pair.exchanges.keys():
            if exchange not in self.pairs_by_exchange:
                self.pairs_by_exchange[exchange] = []
            self.pairs_by_exchange[exchange].append(pair)
        
        # Add to symbol map
        for exchange, config in pair.exchanges.items():
            key = (exchange, config.symbol)
            if key not in self.symbol_to_pairs:
                self.symbol_to_pairs[key] = []
            self.symbol_to_pairs[key].append(pair)
        
        # Track active pairs
        if pair.is_enabled:
            self.active_pair_ids.add(pair.id)
    
    def get_pair(self, pair_id: str) -> Optional[ArbitragePair]:
        """Get pair by ID (O(1) lookup)."""
        return self.pairs_by_id.get(pair_id)
    
    def get_pairs_for_exchange(self, exchange: str) -> List[ArbitragePair]:
        """Get all pairs for an exchange (O(1) lookup)."""
        return self.pairs_by_exchange.get(exchange, [])
    
    def get_pairs_for_symbol(self, exchange: str, symbol: str) -> List[ArbitragePair]:
        """Get pairs for a specific symbol on an exchange (O(1) lookup)."""
        return self.symbol_to_pairs.get((exchange, symbol), [])
    
    def get_active_pairs(self) -> List[ArbitragePair]:
        """Get all active pairs."""
        return [self.pairs_by_id[pair_id] for pair_id in self.active_pair_ids if pair_id in self.pairs_by_id]


@dataclass
class PairValidationResult:
    """
    Result of pair validation against exchange capabilities.
    
    HFT COMPLIANT: Validation performed once at startup.
    """
    pair_id: str
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    validated_exchanges: Dict[str, bool] = field(default_factory=dict)  # Exchange -> validation status
    
    def add_error(self, error: str) -> None:
        """Add a validation error."""
        self.errors.append(error)
        self.is_valid = False
    
    def add_warning(self, warning: str) -> None:
        """Add a validation warning."""
        self.warnings.append(warning)