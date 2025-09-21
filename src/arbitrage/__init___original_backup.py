"""
HFT Arbitrage Framework

Ultra-high-performance arbitrage engine designed for sub-millisecond cryptocurrency
trading across multiple exchanges with atomic spot + futures hedge operations.

Core Components:
- ArbitrageEngine: Main orchestrator with sub-50ms execution targets
- OpportunityDetector: Real-time cross-exchange opportunity detection
- PositionManager: Atomic operation management with recovery capabilities
- OrderOrchestrator: Precision execution layer with decimal matching
- StateController: Finite state machine for atomic operations
- RiskManager: Real-time risk management and position limits
- BalanceMonitor: Balance tracking with HFT-compliant refresh
- RecoveryManager: Partial execution recovery and error handling
- MarketDataAggregator: Cross-exchange data synchronization

Architecture Principles:
- Event-driven with async/await throughout
- msgspec.Struct for zero-copy data structures
- HFT compliance: NO real-time data caching
- Atomic spot + futures hedge operations
- Extensible for new exchange integrations
- Sub-50ms latency targets for complete arbitrage cycles
"""

from .engine import ArbitrageEngine
from .detector import OpportunityDetector
from .position import PositionManager
from .orchestrator import OrderOrchestrator
from .state import StateController
from .risk import RiskManager
from .balance import BalanceMonitor
from .recovery import RecoveryManager
from .aggregator import MarketDataAggregator
from .structures import (
    ArbitrageOpportunity,
    ArbitrageState,
    PositionEntry,
    ExecutionResult,
    OpportunityType,
    ArbitrageConfig,
    RiskLimits,
)

__all__ = [
    # Core Engine Components
    "ArbitrageEngine",
    "OpportunityDetector", 
    "PositionManager",
    "OrderOrchestrator",
    "StateController",
    "RiskManager",
    "BalanceMonitor",
    "RecoveryManager",
    "MarketDataAggregator",
    
    # Data Structures
    "ArbitrageOpportunity",
    "ArbitrageState",
    "PositionEntry", 
    "ExecutionResult",
    "OpportunityType",
    "ArbitrageConfig",
    "RiskLimits",
]