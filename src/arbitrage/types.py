"""
Arbitrage Types and Enumerations

Core type definitions for the HFT arbitrage engine.
Provides type-safe enumerations and data structures for arbitrage operations.

HFT COMPLIANT: All structures are immutable and optimized for performance.
"""

from enum import IntEnum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


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