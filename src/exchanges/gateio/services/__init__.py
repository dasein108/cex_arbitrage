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
from .gateio_mappings import GateioMappings
from .gateio_funtures_mappings import GateioFuturesMappings
from structs.common import ExchangeEnum

# Import factories to verify registration
from core.exchanges.services import ExchangeSymbolMapperFactory, ExchangeMapperFactory

ExchangeSymbolMapperFactory.register(ExchangeEnum.GATEIO, GateioSymbolMapperInterface)
ExchangeMapperFactory.register(ExchangeEnum.GATEIO, GateioMappings)

ExchangeSymbolMapperFactory.register(ExchangeEnum.GATEIO_FUTURES, GateioFuturesSymbolMapperInterface)
ExchangeMapperFactory.register(ExchangeEnum.GATEIO_FUTURES, GateioFuturesMappings)


__all__ = [
    'GateioSymbolMapperInterface',
    'GateioMappings',
    'GateioFuturesSymbolMapperInterface',
    'GateioFuturesMappings'
]