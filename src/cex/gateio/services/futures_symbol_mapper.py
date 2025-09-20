"""
Gate.io Futures Symbol Mapper Implementation

Factory-pattern symbol mapper for Gate.io futures exchange.
Converts between unified Symbol structs and Gate.io futures contract names.

Gate.io Futures Format:
- Perpetual: "BTC_USDT" (for perpetual contracts)
- Delivery: "BTC_USDT_20241225" (for delivery/dated contracts)

Contract Name Field: Gate.io futures API responses use the "contract" or "name" field
Supported Quote Assets: USDT, USDC, BTC, ETH, DAI, USD
Contract Types: Perpetual swaps and delivery contracts

Integration with existing symbol mapper pattern while handling futures specifics.
"""

import re
from core.cex.services.symbol_mapper.base_symbol_mapper import SymbolMapperInterface
from core.cex.services.symbol_mapper.factory import ExchangeSymbolMapperFactory
from structs.common import Symbol, AssetName


class GateioFuturesSymbolMapperInterface(SymbolMapperInterface):
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
        # Gate.io futures-specific quote assets (USDT is primary for perpetuals)
        super().__init__(quote_assets=('USDT', 'USDC', 'BTC', 'ETH', 'DAI', 'USD'))

        # Regex pattern for delivery contracts (BASE_QUOTE_YYYYMMDD)
        self._delivery_pattern = re.compile(r'^(.+)_([A-Z]+)_(\d{8})$')
        # Regex pattern for perpetual contracts (BASE_QUOTE)
        self._perpetual_pattern = re.compile(r'^(.+)_([A-Z]+)$')

    def _symbol_to_string(self, symbol: Symbol) -> str:
        """
        Convert Symbol to Gate.io futures contract name format.

        Args:
            symbol: Unified Symbol struct

        Returns:
            Gate.io contract name string

        Examples:
            Symbol(BTC, USDT, is_futures=True) -> "BTC_USDT" (perpetual)
            Symbol(BTC, USDT, is_futures=True, expiry="20241225") -> "BTC_USDT_20241225" (delivery)
        """
        base_format = f"{symbol.base}_{symbol.quote}"

        # Check if this is a delivery contract with expiry date
        if hasattr(symbol, 'expiry') and symbol.expiry:
            # Delivery contract format: BASE_QUOTE_YYYYMMDD
            return f"{base_format}_{symbol.expiry}"
        else:
            # Perpetual contract format: BASE_QUOTE
            return base_format

    def _string_to_symbol(self, contract_name: str) -> Symbol:
        """
        Parse Gate.io futures contract name to Symbol struct.

        Args:
            contract_name: Gate.io contract name (e.g., "BTC_USDT" or "BTC_USDT_20241225")

        Returns:
            Symbol struct with base and quote assets, is_futures=True

        Raises:
            ValueError: If contract name format is not recognized
        """
        contract_name = contract_name.upper()  # Normalize to uppercase

        # Try to match delivery contract pattern first (BASE_QUOTE_YYYYMMDD)
        delivery_match = self._delivery_pattern.match(contract_name)
        if delivery_match:
            base, quote, expiry_date = delivery_match.groups()

            # Validate quote asset is supported for futures
            if quote in self._quote_assets:
                # Create Symbol with expiry information for delivery contracts
                symbol = Symbol(
                    base=AssetName(base),
                    quote=AssetName(quote),
                    is_futures=True
                )
                # Add expiry as additional attribute (if Symbol supports it)
                # Note: This depends on Symbol struct definition supporting expiry
                if hasattr(symbol, 'expiry'):
                    symbol.expiry = expiry_date
                return symbol

        # Try to match perpetual contract pattern (BASE_QUOTE)
        perpetual_match = self._perpetual_pattern.match(contract_name)
        if perpetual_match:
            base, quote = perpetual_match.groups()

            # Validate quote asset is supported for futures
            if quote in self._quote_assets:
                return Symbol(
                    base=AssetName(base),
                    quote=AssetName(quote),
                    is_futures=True  # KEY DIFFERENCE: Always True for futures
                )

        # Fallback: Try original underscore-based parsing for edge cases
        if '_' in contract_name:
            parts = contract_name.split('_')
            if len(parts) >= 2:
                base = parts[0]
                quote = parts[1]

                # Validate quote asset is supported
                if quote in self._quote_assets:
                    symbol = Symbol(
                        base=AssetName(base),
                        quote=AssetName(quote),
                        is_futures=True
                    )

                    # If there's a third part, it might be expiry date
                    if len(parts) == 3 and parts[2].isdigit() and len(parts[2]) == 8:
                        if hasattr(symbol, 'expiry'):
                            symbol.expiry = parts[2]

                    return symbol

        # Final fallback: Try suffix matching for contracts without underscores
        for quote in self._quote_assets:
            if contract_name.endswith(quote):
                base = contract_name[:-len(quote)]
                if base and base != contract_name:  # Ensure base is not empty and different
                    return Symbol(
                        base=AssetName(base),
                        quote=AssetName(quote),
                        is_futures=True
                    )

        raise ValueError(
            f"Unrecognized Gate.io futures contract format: {contract_name}. "
            f"Expected format: BASE_QUOTE (perpetual) or BASE_QUOTE_YYYYMMDD (delivery). "
            f"Supported quotes: {self._quote_assets}"
        )

    def is_perpetual_contract(self, contract_name: str) -> bool:
        """
        Check if a contract name represents a perpetual contract.

        Args:
            contract_name: Gate.io contract name

        Returns:
            True if perpetual, False if delivery contract
        """
        contract_name = contract_name.upper()

        # Delivery contracts have date suffix (8 digits)
        if self._delivery_pattern.match(contract_name):
            return False

        # Perpetual contracts are just BASE_QUOTE
        if self._perpetual_pattern.match(contract_name):
            return True

        # Default assumption for unknown formats
        return True

    def is_delivery_contract(self, contract_name: str) -> bool:
        """
        Check if a contract name represents a delivery contract.

        Args:
            contract_name: Gate.io contract name

        Returns:
            True if delivery, False if perpetual contract
        """
        return not self.is_perpetual_contract(contract_name)

    def extract_expiry_date(self, contract_name: str) -> str | None:
        """
        Extract expiry date from delivery contract name.

        Args:
            contract_name: Gate.io contract name

        Returns:
            Expiry date string (YYYYMMDD) if delivery contract, None if perpetual
        """
        contract_name = contract_name.upper()

        delivery_match = self._delivery_pattern.match(contract_name)
        if delivery_match:
            return delivery_match.group(3)  # Return the date part

        return None


# Register Gate.io futures mapper with factory
ExchangeSymbolMapperFactory.register('GATEIO_FUTURES', GateioFuturesSymbolMapperInterface)

# Convenience instance using factory pattern
gateio_futures_symbol_mapper = ExchangeSymbolMapperFactory.inject('GATEIO_FUTURES')