from exchanges.services.symbol_mapper.base_symbol_mapper import SymbolMapperInterface
from exchanges.structs import Symbol, AssetName


class GateioFuturesSymbolMapper(SymbolMapperInterface):
    """
    Gate.io futures-specific symbol mapper implementation.

    Converts between unified Symbol structs and Gate.io futures contract names.

    Gate.io Futures Format:
    - Perpetual: "BTC_USDT" (for perpetual contracts)
    - Delivery: "BTC_USDT_20241225" (for delivery/dated contracts with expiry date)

    Supported Quote Assets: USDT, USDC, BTC, ETH, DAI, USD
    Contract Types: Perpetual swaps (USDT-margined) and delivery contracts
    HFT Performance: <0.5μs conversion with caching
    """
    def __init__(self):
        super().__init__(quote_assets=('USDT', 'USDC', 'BTC', 'ETH', 'DAI', 'USD'))
    
    def _symbol_to_string(self, symbol: Symbol) -> str:
        """
        Symbol -> строка Gate.io futures.
        """
        pair = f"{symbol.base}_{symbol.quote}"
        # if getattr(symbol, "expiry", None):
        #     return f"{pair}_{symbol.expiry}"
        return pair
    
    def _string_to_symbol(self, contract: str) -> Symbol:
        """
        Строка Gate.io futures -> Symbol.
        """
        contract = contract.upper()
        parts = contract.split("_")
        
        if len(parts) == 2:
            base, quote = parts
            if quote in self._quote_assets:
                return Symbol(base=AssetName(base), quote=AssetName(quote), is_futures=True)
        
        elif len(parts) == 3:
            base, quote, expiry = parts
            if quote in self._quote_assets:
                symbol = Symbol(base=AssetName(base), quote=AssetName(quote), is_futures=True)
                if hasattr(symbol, "expiry"):
                    symbol.expiry = expiry
                return symbol
        
        raise ValueError(
            f"Unrecognized Gate.io futures contract format: {contract}. "
            f"Expected BASE_QUOTE or BASE_QUOTE_YYYYMMDD. Supported quotes: {self._quote_assets}"
        )

    def is_perpetual(self, contract: str) -> bool:

        return len(contract.split("_")) == 2
    
    def is_delivery(self, contract: str) -> bool:

        return len(contract.split("_")) == 3



# Global singleton instance for direct usage - use GateioFuturesSymbol.method() directly
GateioFuturesSymbol = GateioFuturesSymbolMapper()
