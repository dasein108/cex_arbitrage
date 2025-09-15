from core.cex.services.symbol_mapper.symbol_mapper_factory import ExchangeSymbolMapperFactory
from exchanges.mexc.common.mexc_symbol_mapper import MexcSymbolMapper  # Import to register mappers
from exchanges.gateio.common.gateio_symbol_mapper import GateioSymbolMapper  # Import
from config import config

SYMBOL_MAPPERS = {
    "MEXC": MexcSymbolMapper,
    "GATEIO": GateioSymbolMapper,
    # Add other exchange mappers here
}

global_logger = config.get_logger('global')

def install_exchange_dependencies():
    """Ensure all enabled exchanges have their symbol mappers registered."""
    global_logger.info("🔧 Installing Exchange Dependencies")
    exchanges = config.get_all_exchange_configs()

    for exchange_name, exchange_cfg in exchanges.items():
        if exchange_cfg.enabled:
            try:
                ExchangeSymbolMapperFactory.register_mapper(exchange_name, SYMBOL_MAPPERS[exchange_name.upper()])
                global_logger.info(f"✅ Successfully registered symbol mapper for {exchange_name}")
            except ValueError as e:
                global_logger.info(f"❌ Error registering symbol mapper for {exchange_name}: {e}")

