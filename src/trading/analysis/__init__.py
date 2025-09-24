"""
Arbitrage Analysis Module

High-performance arbitrage analysis system for cross-exchange opportunities.
Implements HFT-compliant data collection, spread analysis, and reporting.

Architecture:
- Event-driven async processing with msgspec optimization
- Memory-efficient streaming analysis for large datasets
- Zero-copy data processing with sub-millisecond precision
- Integration with existing symbol discovery and candles downloader

Performance Targets:
- <2GB memory usage during analysis
- <50ms latency per spread calculation
- Process 3 months of 1-minute data efficiently
"""

from .collect_arbitrage_data import ArbitrageDataPipeline
from .spread_analyzer import SpreadAnalyzer, ArbitrageMetrics

__all__ = [
    'ArbitrageDataPipeline',
    'SpreadAnalyzer', 
    'ArbitrageMetrics'
]