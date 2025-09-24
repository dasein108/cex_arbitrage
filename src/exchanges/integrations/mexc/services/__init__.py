"""
MEXC Services Auto-Registration

Auto-registers all MEXC service implementations with their respective factories.
Follows the same pattern as the WebSocket strategy registration in @src/exchanges/mexc/ws/__init__.py

Services auto-registered:
- MexcSymbolMapperInterface with ExchangeSymbolMapperFactory
- MexcUnifiedMappings with ExchangeMappingsFactory

Registration happens automatically when this module is imported.
"""

from .symbol_mapper import MexcSymbolMapper
from .mexc_mappings import MexcUnifiedMappings

from infrastructure.data_structures.common import ExchangeEnum

# Import factories to verify registration
from exchanges.services.symbol_mapper.factory import ExchangeSymbolMapperFactory
from exchanges.services.exchange_mapper.factory import ExchangeMapperFactory

ExchangeSymbolMapperFactory.register(ExchangeEnum.MEXC, MexcSymbolMapper)
ExchangeMapperFactory.register(ExchangeEnum.MEXC, MexcUnifiedMappings)

__all__ = [
    'MexcSymbolMapper',
    'MexcUnifiedMappings'
]