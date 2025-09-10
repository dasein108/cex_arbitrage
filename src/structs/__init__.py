"""
Unified data structures for the CEX arbitrage system.

This module provides msgspec-based data structures used throughout the system
for maximum performance and type safety:
- Exchange data structures (Symbol, SymbolInfo, OrderBook, Trade)
- Trading data structures (Order, Balance, Position)
- Unified enums and types
"""

from .exchange import *

__all__ = [
    # Core data structures
    'Symbol', 'SymbolInfo', 'OrderBook', 'OrderBookEntry', 'Trade',
    
    # Enums and types
    'ExchangeName', 'AssetName', 'Side', 'OrderType', 'OrderStatus',
    
    # Type aliases
    'Price', 'Amount', 'Timestamp'
]