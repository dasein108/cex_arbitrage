from .gateio_mappings import GateioMappings
from .mapping_configuration import create_gateio_mapping_configuration


class GateioFuturesMappings(GateioMappings):
    """
    Gate.io futures-specific mapping implementation.
    
    Uses GateioFuturesSymbolMapperInterface for proper futures contract handling.
    Inherits all mapping functionality from GateioMappings but ensures
    futures-specific symbol processing.
    """
    
    def __init__(self, symbol_mapper):
        """
        Initialize Gate.io futures mappings.
        
        Args:
            symbol_mapper: Should be GateioFuturesSymbolMapperInterface instance
        """
        # Use the same configuration as spot for now
        # Could be extended to futures-specific config if needed
        config = create_gateio_mapping_configuration()
        
        # Initialize base mapper with futures symbol mapper
        from core.exchanges.services.exchange_mapper.base_exchange_mapper import BaseExchangeMapper
        BaseExchangeMapper.__init__(self, symbol_mapper, config)
        
        # Verify we have the futures symbol mapper
        from .futures_symbol_mapper import GateioFuturesSymbolMapperInterface
        if not isinstance(symbol_mapper, GateioFuturesSymbolMapperInterface):
            import logging
            logging.getLogger(__name__).warning(
                f"Expected GateioFuturesSymbolMapperInterface, got {type(symbol_mapper)}"
            )
