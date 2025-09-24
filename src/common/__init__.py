"""
Common utilities and shared components for the CEX arbitrage system.

This module provides shared components used across the arbitrage trading system:
- Ring buffer for high-performance logging
- HFT orderbook management
- Orderbook processing utilities
- Common iterators and managers
"""

# Export available modules without importing to avoid circular dependencies
__all__ = [
    'ring_buffer',
    'hft_orderbook',
    'orderbook_manager',
    'orderbook_diff_processor',
    'orderbook_entry_pool',
    'iterators'
]