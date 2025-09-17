from core.cex.services.symbol_mapper.base_symbol_mapper import SymbolMapperInterface
from structs.exchange import Symbol, AssetName


class MexcSymbolMapper(SymbolMapperInterface):
    """
    MEXC-specific symbol mapper implementation.
    
    Converts between unified Symbol structs and MEXC trading pair format.
    MEXC Format: Concatenated without separator (e.g., "BTCUSDT")
    
    Supported Quote Assets: USDT, USDC
    HFT Performance: <0.5μs conversion with caching
    """
    
    def __init__(self):
        # MEXC-specific quote assets
        super().__init__(quote_assets=('USDT', 'USDC'))
    
    def _symbol_to_string(self, symbol: Symbol) -> str:
        """
        Convert Symbol to MEXC pair format.
        
        MEXC Format: {cex}{quote} (no separator)
        Example: Symbol(BTC, USDT) -> "BTCUSDT"
        """
        return f"{symbol.base}{symbol.quote}"
    
    def _string_to_symbol(self, pair: str) -> Symbol:
        """
        Parse MEXC pair string to Symbol struct.
        
        Args:
            pair: MEXC trading pair (e.g., "BTCUSDT")
            
        Returns:
            Symbol struct with cex and quote assets
            
        Raises:
            ValueError: If pair format is not recognized
        """
        pair = pair.upper()  # Normalize to uppercase
        
        # Try each supported quote asset
        for quote in self._quote_assets:
            if pair.endswith(quote):
                base = pair[:-len(quote)]
                if base:  # Ensure cex is not empty
                    return Symbol(
                        base=AssetName(base),
                        quote=AssetName(quote),
                        is_futures=False
                    )
        
        raise ValueError(f"Unrecognized MEXC pair format: {pair}. Supported quotes: {self._quote_assets}")


