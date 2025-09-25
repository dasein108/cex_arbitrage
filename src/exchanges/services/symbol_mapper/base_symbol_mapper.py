"""
Base Symbol Mapper Interface

Foundation interface for exchange-specific symbol mappers.
Defines the common contract that all symbol mapper implementations must follow.

HFT COMPLIANCE: Pure interface definition, zero runtime overhead.
"""

from abc import ABC, abstractmethod
from typing import Tuple, Set
from exchanges.structs.common import Symbol


class SymbolMapperInterface(ABC):
    """
    Abstract base class for exchange-specific symbol mappers.
    
    Defines the contract for converting between unified Symbol structs and 
    exchange-specific pair strings. All exchange symbol mappers should inherit 
    from this interface to ensure consistent behavior.
    
    This interface supports the global singleton pattern where each exchange
    has a single mapper instance that can be directly imported and used.
    """
    
    def __init__(self, quote_assets: Tuple[str, ...] = None):
        """
        Initialize with supported quote assets.
        
        Args:
            quote_assets: Tuple of supported quote asset symbols (e.g., ('USDT', 'USDC', 'BTC'))
        """
        self._quote_assets: Set[str] = set(quote_assets or ())
    
    @abstractmethod
    def _symbol_to_string(self, symbol: Symbol) -> str:
        """
        Convert Symbol to exchange-specific string format.
        
        Must be implemented by each exchange to handle their specific format.
        
        Args:
            symbol: Unified Symbol struct
            
        Returns:
            Exchange-specific pair string
        """
        pass
    
    @abstractmethod
    def _string_to_symbol(self, pair: str) -> Symbol:
        """
        Parse exchange-specific pair string to Symbol struct.
        
        Must be implemented by each exchange to handle their specific format.
        
        Args:
            pair: Exchange-specific pair string
            
        Returns:
            Unified Symbol struct
            
        Raises:
            ValueError: If pair format is not recognized
        """
        pass
    
    # Public API methods that use the abstract methods
    def to_pair(self, symbol: Symbol) -> str:
        """Convert Symbol to exchange pair string."""
        return self._symbol_to_string(symbol)
    
    def to_symbol(self, pair: str) -> Symbol:
        """Convert exchange pair string to Symbol."""
        return self._string_to_symbol(pair)
    
    def is_supported_pair(self, pair: str) -> bool:
        """
        Check if pair string is supported by this exchange.
        
        Args:
            pair: Exchange pair string to validate
            
        Returns:
            True if pair format is valid and quote asset is supported
        """
        try:
            symbol = self.to_symbol(pair)
            return symbol.quote in self._quote_assets
        except (ValueError, AttributeError):
            return False
    
    def validate_symbol(self, symbol: Symbol) -> bool:
        """
        Check if symbol is supported by this exchange.
        
        Args:
            symbol: Symbol to validate
            
        Returns:
            True if symbol's quote asset is supported
        """
        if not self._quote_assets:
            return True
        return symbol.quote in self._quote_assets
    
    @property
    def supported_quote_assets(self) -> Set[str]:
        """Get set of supported quote assets."""
        return self._quote_assets.copy()