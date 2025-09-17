"""
MEXC Services Auto-Registration

Auto-registers all MEXC service implementations with their respective factories.
Follows the same pattern as the WebSocket strategy registration in @src/cex/mexc/ws/__init__.py

Services auto-registered:
- MexcSymbolMapperInterface with ExchangeSymbolMapperFactory
- MexcMappings with ExchangeMappingsFactory

Registration happens automatically when this module is imported.
"""

from .symbol_mapper import MexcSymbolMapper
from .mexc_mappings import MexcMappings

from cex import ExchangeEnum

# Import factories to verify registration
from core.cex.services.symbol_mapper.factory import ExchangeSymbolMapperFactory
from core.cex.services.unified_mapper.factory import ExchangeMappingsFactory

ExchangeSymbolMapperFactory.register(ExchangeEnum.MEXC.value, MexcSymbolMapper)
ExchangeMappingsFactory.register(ExchangeEnum.MEXC.value, MexcMappings)

__all__ = [
    'MexcSymbolMapper',
    'MexcMappings'
]