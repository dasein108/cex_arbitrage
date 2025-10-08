"""
Symbol Analysis Tools Module

Comprehensive analytics tools for arbitrage strategies across any trading symbol.
Provides real-time and historical data analysis for spread-based trading decisions
with agent-friendly interfaces and command-line tools.

Usage Examples:
    # Python API
    from src.applications.tools import MultiSymbolDataFetcher, SpreadAnalyzer
    
    # Command Line (from project root)
    python -m src.applications.tools.analyze_symbol_simplified --symbol NEIROETH --quote USDT
"""

__version__ = "1.0.0"
__author__ = "HFT Trading System"

from .data_fetcher import MultiSymbolDataFetcher, UnifiedSnapshot
from .spread_analyzer_simplified import SpreadAnalyzer  
from .pnl_calculator import PnLCalculator
from .performance_tracker import PerformanceTracker

__all__ = [
    "MultiSymbolDataFetcher",
    "UnifiedSnapshot",
    "SpreadAnalyzer", 
    "PnLCalculator",
    "PerformanceTracker"
]