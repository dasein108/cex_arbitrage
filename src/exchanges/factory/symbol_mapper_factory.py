from exchanges.structs import ExchangeEnum
from exchanges.structs.common import Symbol
from exchanges.structs.types import ExchangeName
from exchanges.services import SymbolMapperInterface


def get_symbol_mapper(exchange: ExchangeEnum) -> SymbolMapperInterface:
    """Factory function to get the appropriate SymbolMapper class based on the exchange name."""
    if exchange == ExchangeEnum.MEXC:
        from exchanges.integrations.mexc.services.symbol_mapper import MexcSymbolMapper
        return MexcSymbolMapper()
    elif exchange == ExchangeEnum.GATEIO:
        from exchanges.integrations.gateio.services.spot_symbol_mapper import GateioSymbolMapper
        return GateioSymbolMapper()
    elif exchange == ExchangeEnum.GATEIO_FUTURES:
        from exchanges.integrations.gateio.services.futures_symbol_mapper import GateioFuturesSymbolMapper
        return GateioFuturesSymbolMapper()
    else:
        raise ValueError(f"Unsupported exchange: {exchange}")