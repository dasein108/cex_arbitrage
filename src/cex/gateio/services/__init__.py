"""
Gate.io Services Auto-Registration

Auto-registers all Gate.io service implementations with their respective factories.
Follows the same pattern as the MEXC service registration.

Services auto-registered:
- GateioSymbolMapper with ExchangeSymbolMapperFactory
- GateioMappings with ExchangeMappingsFactory

Registration happens automatically when this module is imported.
"""

from .symbol_mapper import GateioSymbolMapperInterface
from .futures_symbol_mapper import GateioFuturesSymbolMapperInterface
from .mapper import GateioUnifiedMappings

from cex.consts import ExchangeEnum

# Import factories to verify registration
from core.cex.services.symbol_mapper.factory import ExchangeSymbolMapperFactory
from core.cex.services.unified_mapper.factory import ExchangeMappingsFactory

ExchangeSymbolMapperFactory.register(ExchangeEnum.GATEIO.value, GateioSymbolMapperInterface)
ExchangeMappingsFactory.register(ExchangeEnum.GATEIO.value, GateioUnifiedMappings)

ExchangeSymbolMapperFactory.register(ExchangeEnum.GATEIO_FUTURES.value, GateioFuturesSymbolMapperInterface)
ExchangeMappingsFactory.register(ExchangeEnum.GATEIO_FUTURES.value, GateioUnifiedMappings)


__all__ = [
    'GateioSymbolMapperInterface',
    'GateioUnifiedMappings',
    'GateioFuturesSymbolMapperInterface'
]