"""
Symbol extraction utilities with strategy pattern for exchange-specific logic.

Provides common symbol extraction patterns while delegating exchange-specific
logic to strategy implementations.
"""

from typing import Optional, List, Dict, Any, Callable
import re
from abc import ABC, abstractmethod

from exchanges.structs.common import Symbol


class SymbolExtractionStrategy(ABC):
    """Strategy interface for exchange-specific symbol extraction."""
    
    @abstractmethod
    def extract_from_data(self, data: Dict[str, Any], fields: List[str]) -> Optional[str]:
        """Extract symbol string from message data."""
        pass
    
    @abstractmethod  
    def extract_from_channel(self, channel: str) -> Optional[str]:
        """Extract symbol string from channel name."""
        pass
    
    @abstractmethod
    def convert_to_symbol(self, symbol_str: str) -> Optional[Symbol]:
        """Convert symbol string to unified Symbol object."""
        pass


class GateioSymbolExtraction(SymbolExtractionStrategy):
    """Gate.io-specific symbol extraction logic."""
    
    def __init__(self, symbol_converter: Callable[[str], Optional[Symbol]]):
        """Initialize with Gate.io symbol conversion function."""
        self.convert_symbol = symbol_converter
    
    def extract_from_data(self, data: Dict[str, Any], fields: List[str]) -> Optional[str]:
        """Extract symbol from Gate.io message data."""
        # Gate.io uses different fields for different message types
        for field in fields:
            symbol_str = data.get(field)
            if symbol_str and isinstance(symbol_str, str):
                return symbol_str
        return None
    
    def extract_from_channel(self, channel: str) -> Optional[str]:
        """Extract symbol from Gate.io channel name."""
        # Gate.io format: "spot.trades.BTC_USDT" or "futures.book_ticker.BTC_USD"
        if '.' in channel:
            parts = channel.split('.')
            if len(parts) >= 3:
                return parts[-1]  # Last part is symbol
        return None
    
    def convert_to_symbol(self, symbol_str: str) -> Optional[Symbol]:
        """Convert Gate.io symbol string to unified Symbol."""
        return self.convert_symbol(symbol_str)


class MexcSymbolExtraction(SymbolExtractionStrategy):
    """MEXC-specific symbol extraction logic."""
    
    def __init__(self, symbol_converter: Callable[[str], Optional[Symbol]]):
        """Initialize with MEXC symbol conversion function."""
        self.convert_symbol = symbol_converter
    
    def extract_from_data(self, data: Dict[str, Any], fields: List[str]) -> Optional[str]:
        """Extract symbol from MEXC message data."""
        # MEXC typically uses 'symbol' or 's' fields
        for field in fields:
            symbol_str = data.get(field)
            if symbol_str and isinstance(symbol_str, str):
                return symbol_str
        return None
    
    def extract_from_channel(self, channel: str) -> Optional[str]:
        """Extract symbol from MEXC channel name."""
        # MEXC format: "spot@public.bookTicker.v3.api@BTCUSDT"
        if '@' in channel and not channel.endswith(')'):
            # Look for symbol pattern at the end
            parts = channel.split('@')
            if parts:
                last_part = parts[-1]
                # MEXC symbols are typically all caps, no separators
                if re.match(r'^[A-Z]{2,10}USDT?$', last_part):
                    return last_part
        return None
    
    def convert_to_symbol(self, symbol_str: str) -> Optional[Symbol]:
        """Convert MEXC symbol string to unified Symbol."""
        return self.convert_symbol(symbol_str)


class UniversalSymbolExtractor:
    """
    Universal symbol extractor that works with any exchange strategy.
    
    Provides common extraction patterns while delegating exchange-specific
    logic to strategy implementations.
    """
    
    def __init__(self, strategy: SymbolExtractionStrategy):
        """Initialize with exchange-specific extraction strategy."""
        self.strategy = strategy
        
        # Common symbol field names (in priority order)
        self.default_fields = [
            's',           # Short symbol field (common)
            'symbol',      # Full symbol field
            'currency_pair',  # Gate.io format
            'contract',    # Futures format
            'pair',        # Alternative naming
            'market'       # Alternative naming
        ]
    
    def extract_symbol(self, 
                      data: Dict[str, Any],
                      channel: str = "",
                      symbol_fields: Optional[List[str]] = None) -> Optional[Symbol]:
        """
        Extract symbol using strategy pattern with common fallback logic.
        
        Args:
            data: Message data to extract symbol from
            channel: Channel name for fallback extraction
            symbol_fields: Custom symbol fields (uses defaults if None)
            
        Returns:
            Unified Symbol object or None if extraction fails
        """
        fields_to_try = symbol_fields or self.default_fields
        
        # Try extracting from data fields
        symbol_str = self.strategy.extract_from_data(data, fields_to_try)
        if symbol_str:
            symbol = self.strategy.convert_to_symbol(symbol_str)
            if symbol:
                return symbol
        
        # Fallback: try extracting from channel
        if channel:
            channel_symbol_str = self.strategy.extract_from_channel(channel)
            if channel_symbol_str:
                return self.strategy.convert_to_symbol(channel_symbol_str)
        
        return None
    
    def extract_multiple_symbols(self, 
                                data: Dict[str, Any],
                                channels: List[str] = None) -> List[Symbol]:
        """Extract multiple symbols from data or channel list."""
        symbols = []
        
        # Try data extraction first
        symbol = self.extract_symbol(data)
        if symbol:
            symbols.append(symbol)
        
        # Try channel extraction for each channel
        if channels:
            for channel in channels:
                symbol = self.extract_symbol({}, channel=channel)
                if symbol and symbol not in symbols:
                    symbols.append(symbol)
        
        return symbols