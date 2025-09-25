"""
Gate.io Symbol Mapper Implementation

Direct utility functions for Gate.io exchange symbol mapping.
Converts between unified Symbol structs and Gate.io trading pair format.

Gate.io Format: Underscore-separated (e.g., "BTC_USDT")
Supported Quote Assets: USDT, USDC, BTC, ETH, DAI, USD

HFT COMPLIANT: Direct function calls, no factories, no dependency injection.
"""

from exchanges.services.symbol_mapper.base_symbol_mapper import SymbolMapperInterface
from exchanges.structs import Symbol, AssetName


class GateioSymbolMapperInterface(SymbolMapperInterface):
    """
    Gate.io-specific symbol mapper implementation.
    
    Converts between unified Symbol structs and Gate.io trading pair format.
    Gate.io Format: Underscore-separated (e.g., "BTC_USDT")
    
    Supported Quote Assets: USDT, USDC, BTC, ETH, DAI, USD
    HFT Performance: <0.5μs conversion with caching
    """
    
    def __init__(self):
        # Gate.io-specific quote assets (more extensive than MEXC)
        super().__init__(quote_assets=('USDT', 'USDC', 'BTC', 'ETH', 'DAI', 'USD'))
    
    def _symbol_to_string(self, symbol: Symbol) -> str:
        """
        Convert Symbol to Gate.io pair format.
        
        Gate.io Format: {exchanges}_{quote} (underscore separator)
        Example: Symbol(BTC, USDT) -> "BTC_USDT"
        """
        return f"{symbol.base}_{symbol.quote}"
    
    def _string_to_symbol(self, pair: str) -> Symbol:
        """
        Parse Gate.io pair string to Symbol struct.
        
        Args:
            pair: Gate.io trading pair (e.g., "BTC_USDT")
            
        Returns:
            Symbol struct with exchanges and quote assets
            
        Raises:
            ValueError: If pair format is not recognized
        """
        pair = pair.upper()  # Normalize to uppercase
        
        # Gate.io uses underscore separator
        if '_' in pair:
            parts = pair.split('_')
            if len(parts) == 2:
                base, quote = parts
                
                # Validate quote asset is supported
                if quote in self._quote_assets:
                    return Symbol(
                        base=AssetName(base),
                        quote=AssetName(quote),
                        is_futures=False
                    )
        
        # Fallback: Try suffix matching for pairs without underscore
        for quote in self._quote_assets:
            if pair.endswith(quote):
                base = pair[:-len(quote)]
                if base and base != pair:  # Ensure exchanges is not empty and different
                    return Symbol(
                        base=AssetName(base),
                        quote=AssetName(quote),
                        is_futures=False
                    )
        
        raise ValueError(f"Unrecognized Gate.io pair format: {pair}. Expected format: BASE_QUOTE. Supported quotes: {self._quote_assets}")


# Global singleton instance for direct usage - use GateioSpotSymbol.method() directly
GateioSpotSymbol = GateioSymbolMapperInterface()

# Convenience functions remain for non-symbol operations
def get_exchange_interval(interval) -> str:
    """Convert unified KlineInterval to Gate.io format."""
    from exchanges.integrations.gateio.services.gateio_classifiers import KLINE_INTERVAL_MAPPING
    return KLINE_INTERVAL_MAPPING.get(interval, "1m")

