"""
Structs package for CEX arbitrage system.

This package provides all data structures used throughout the system:
- common.py: Core shared structures
- exchange.py: Legacy exchange structures (deprecated - use common.py)
"""

# Import all common structures for easy access
from .common import (
    # Type aliases
    ExchangeName,
    AssetName, 
    OrderId,
    Symbol,
    
    # Enums
    ExchangeEnum,
    ExchangeStatus,
    OrderStatus,
    OrderType,
    Side,
    OrderSide,  # Backward compatibility
    TimeInForce,
    OrderbookUpdateType,
    KlineInterval,
    OpportunityType,
    
    # Core structures
    OrderBookEntry,
    OrderBook,
    Order,
    AssetBalance,
    Position,
    SymbolInfo,
    SymbolsInfo,
    Trade,
    Ticker,
    Kline,
    TradingFee,
    
    # Configuration
    ExchangeCredentials,
    ExchangeConfig,
    
    # Arbitrage
    ArbitrageOpportunity,
    ArbitrageExecution,
)

__all__ = [
    # Type aliases
    'ExchangeName',
    'AssetName',
    'OrderId', 
    'Symbol',
    
    # Enums
    'ExchangeEnum',
    'ExchangeStatus',
    'OrderStatus',
    'OrderType',
    'Side',
    'OrderSide',
    'TimeInForce',
    'OrderbookUpdateType', 
    'KlineInterval',
    'OpportunityType',
    
    # Core structures
    'OrderBookEntry',
    'OrderBook',
    'Order',
    'AssetBalance',
    'Position',
    'SymbolInfo',
    'SymbolsInfo',
    'Trade',
    'Ticker', 
    'Kline',
    'TradingFee',
    
    # Configuration
    'ExchangeCredentials',
    'ExchangeConfig',
    
    # Arbitrage
    'ArbitrageOpportunity',
    'ArbitrageExecution',
]