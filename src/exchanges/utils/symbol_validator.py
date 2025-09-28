"""
Simple symbol validation utility for filtering tradable symbols.

This module provides a lightweight solution for validating symbols before 
WebSocket subscription to prevent errors from non-tradable or delisted symbols.
"""

from typing import List, Dict, Set, Optional
from exchanges.structs.common import Symbol, SymbolInfo
from infrastructure.logging import get_logger


class SymbolValidator:
    """
    Validates symbols for tradability before WebSocket subscription.
    
    Filters out:
    - Delisted symbols
    - Symbols not available for spot/futures trading
    - Symbols with trading disabled
    - Invalid or unknown symbols
    """
    
    def __init__(self, logger=None):
        self.logger = logger or get_logger('symbol_validator')
        self._symbol_cache: Dict[str, Dict[Symbol, SymbolInfo]] = {}
        
    def cache_symbol_info(self, exchange: str, symbols_info: Dict[Symbol, SymbolInfo]) -> None:
        """Cache symbol information for an exchange."""
        self._symbol_cache[exchange] = symbols_info
        self.logger.info(f"Cached {len(symbols_info)} symbols for {exchange}")
        
    def filter_tradable_symbols(
        self, 
        exchange: str, 
        symbols: List[Symbol],
        is_futures: bool = False
    ) -> List[Symbol]:
        """
        Filter symbols to only include tradable ones.
        
        Args:
            exchange: Exchange name (e.g., 'mexc', 'gateio')
            symbols: List of symbols to validate
            is_futures: Whether to check for futures trading
            
        Returns:
            List of valid, tradable symbols
        """
        if exchange not in self._symbol_cache:
            self.logger.warning(f"No symbol info cached for {exchange}, returning all symbols")
            return symbols

        valid_symbols = []
        excluded_symbols = []
        
        exchange_symbols = self._symbol_cache[exchange]
        
        for symbol in symbols:
            # Check if symbol exists in exchange
            if symbol not in exchange_symbols:
                excluded_symbols.append(symbol)
                self.logger.debug(f"Symbol {symbol.base}/{symbol.quote} not found on {exchange}")
                continue
                
            symbol_info = exchange_symbols[symbol]
            
            # Check if symbol is tradable
            if not self._is_symbol_tradable(symbol_info, is_futures):
                excluded_symbols.append(symbol)
                self.logger.debug(f"Symbol {symbol.base}/{symbol.quote} not tradable on {exchange}")
                continue
                
            valid_symbols.append(symbol)
            
        if excluded_symbols:
            self.logger.info(
                f"Excluded {len(excluded_symbols)} non-tradable symbols from {exchange}: "
                f"{[f'{s.base}/{s.quote}' for s in excluded_symbols[:5]]}..."
            )
            
        return valid_symbols
    
    def _is_symbol_tradable(self, symbol_info: SymbolInfo, is_futures: bool) -> bool:
        """
        Check if a symbol is tradable based on its info.
        
        Args:
            symbol_info: Symbol information from exchange
            is_futures: Whether checking for futures trading
            
        Returns:
            True if symbol is tradable
        """
        # Check basic tradability
        if hasattr(symbol_info, 'status'):
            status = getattr(symbol_info, 'status', '').upper()
            if status not in ['ENABLED', 'TRADING', 'TRADABLE', 'ACTIVE']:
                return False
                
        # Check if delisted
        if hasattr(symbol_info, 'delisted'):
            if getattr(symbol_info, 'delisted', False):
                return False
                
        # Check futures-specific fields
        if is_futures:
            if hasattr(symbol_info, 'contract_status'):
                contract_status = getattr(symbol_info, 'contract_status', '').upper()
                if contract_status not in ['TRADING', 'ACTIVE']:
                    return False
                    
            if hasattr(symbol_info, 'in_delisting'):
                if getattr(symbol_info, 'in_delisting', False):
                    return False
                    
        # Check spot-specific fields
        else:
            if hasattr(symbol_info, 'is_spot_trading_allowed'):
                if not getattr(symbol_info, 'is_spot_trading_allowed', True):
                    return False
                    
            if hasattr(symbol_info, 'permissions'):
                permissions = getattr(symbol_info, 'permissions', [])
                if isinstance(permissions, list) and 'SPOT' not in permissions:
                    return False
                    
        # Check trading enabled
        if hasattr(symbol_info, 'is_trading'):
            if not getattr(symbol_info, 'is_trading', True):
                return False
                
        if hasattr(symbol_info, 'trade_status'):
            trade_status = getattr(symbol_info, 'trade_status', '').lower()
            if trade_status not in ['tradable', 'enabled', 'active', '']:
                return False
                
        return True
    
    def get_unknown_symbols(self, exchange: str, symbols: List[Symbol]) -> List[Symbol]:
        """Get list of symbols that are not found on the exchange."""
        if exchange not in self._symbol_cache:
            return []
            
        exchange_symbols = self._symbol_cache[exchange]
        unknown = [s for s in symbols if s not in exchange_symbols]
        
        return unknown
    
    def clear_cache(self, exchange: Optional[str] = None) -> None:
        """Clear symbol cache for an exchange or all exchanges."""
        if exchange:
            self._symbol_cache.pop(exchange, None)
            self.logger.info(f"Cleared symbol cache for {exchange}")
        else:
            self._symbol_cache.clear()
            self.logger.info("Cleared all symbol caches")


# Global instance for easy access
_validator = SymbolValidator()


def get_symbol_validator() -> SymbolValidator:
    """Get the global symbol validator instance."""
    return _validator