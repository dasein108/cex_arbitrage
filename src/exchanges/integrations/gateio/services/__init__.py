"""
Gate.io Services Auto-Registration

Auto-registers all Gate.io service implementations with their respective factories.
Follows the same pattern as the MEXC service registration.

Services auto-registered:
- GateioSymbolMapper with ExchangeSymbolMapperFactory
- GateioMappings with ExchangeMappingsFactory

Registration happens automatically when this module is imported.
"""

from .spot_symbol_mapper import GateioSymbolMapperInterface
from .futures_symbol_mapper import GateioFuturesSymbolMapperInterface
from .gateio_mapper import GateioMapper
from .gateio_funtures_mappings import GateioFuturesMapper
from exchanges.structs.enums import ExchangeEnum

# Import factories to verify registration
from exchanges.services import ExchangeSymbolMapperFactory, ExchangeMapperFactory

ExchangeSymbolMapperFactory.register(ExchangeEnum.GATEIO, GateioSymbolMapperInterface)
ExchangeMapperFactory.register(ExchangeEnum.GATEIO, GateioMapper)

ExchangeSymbolMapperFactory.register(ExchangeEnum.GATEIO_FUTURES, GateioFuturesSymbolMapperInterface)
ExchangeMapperFactory.register(ExchangeEnum.GATEIO_FUTURES, GateioFuturesMapper)


__all__ = [
    'GateioSymbolMapperInterface',
    'GateioMapper',
    'GateioFuturesSymbolMapperInterface',
    'GateioFuturesMapper'
]