"""HFT Arbitrage Framework - Refactored Components

Refactored arbitrage framework with clean architecture following SOLID principles.
Focuses on the components needed for the new main entry point.

Refactored Components:
- ArbitrageController: Main orchestrator following SOLID principles  
- SimpleArbitrageEngine: Clean engine implementation for demonstration
- ConfigurationManager: Dedicated configuration loading and validation
- ExchangeFactory: Factory pattern for exchange creation
- PerformanceMonitor: HFT-compliant performance tracking
- ShutdownManager: Graceful shutdown coordination

Architecture Principles:
- SOLID principles compliance
- Clean separation of concerns
- Event-driven async/await design
- HFT compliance: NO real-time data caching
- Factory pattern for extensibility
- Graceful shutdown and resource management
"""

# Import only the refactored components needed for main.py
from .controller import ArbitrageController
from .simple_engine import SimpleArbitrageEngine
from .configuration_manager import ConfigurationManager
from .exchange_factory import ExchangeFactory
from .performance_monitor import PerformanceMonitor
from .shutdown_manager import ShutdownManager, ShutdownReason
from .types import (
    ArbitrageConfig,
    EngineStatistics,
    OpportunityType,
    ExchangeName,
    RiskLimits,
)

__all__ = [
    # Refactored Core Components
    "ArbitrageController",
    "SimpleArbitrageEngine",
    "ConfigurationManager", 
    "ExchangeFactory",
    "PerformanceMonitor",
    "ShutdownManager",
    "ShutdownReason",
    
    # Data Structures
    "ArbitrageConfig",
    "EngineStatistics",
    "OpportunityType",
    "ExchangeName",
    "RiskLimits",
]