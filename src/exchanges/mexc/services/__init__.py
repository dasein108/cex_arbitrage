"""
MEXC Services Auto-Registration

Auto-registers all MEXC service implementations with their respective factories.
Follows the same pattern as the WebSocket strategy registration in @src/exchanges/mexc/ws/__init__.py

Services auto-registered:
- MexcSymbolMapperInterface with ExchangeSymbolMapperFactory
- MexcMappings with ExchangeMappingsFactory

Registration happens automatically when this module is imported.
"""

from .symbol_mapper import MexcSymbolMapper
from .mapper import MexcMappings

from structs.common import ExchangeEnum

# Import factories to verify registration
from core.exchanges.services.symbol_mapper.factory import ExchangeSymbolMapperFactory
from core.exchanges.services.unified_mapper.factory import ExchangeMappingsFactory

ExchangeSymbolMapperFactory.register(ExchangeEnum.MEXC, MexcSymbolMapper)
ExchangeMappingsFactory.register(ExchangeEnum.MEXC, MexcMappings)

__all__ = [
    'MexcSymbolMapper',
    'MexcMappings'
]