from typing import Type

def get_exchange_rest_class(exchange_name: str, is_private: bool) -> Type:
    """Get the appropriate REST client class for the exchange."""
    exchange_name_upper = exchange_name.upper()

    if exchange_name_upper == 'MEXC':
        # Import MEXC classes and register strategies/services
        import cex.mexc.rest.strategies  # Triggers strategy registration
        import cex.mexc.services  # Register symbol mapper
        from cex.mexc.rest import MexcPublicSpotRest, MexcPrivateSpotRest
        return MexcPublicSpotRest if not is_private else MexcPrivateSpotRest

    elif exchange_name_upper == 'GATEIO':
        # Import Gate.io classes and register strategies/services
        import cex.gateio.rest.strategies  # Triggers strategy registration
        import cex.gateio.services  # Register symbol mapper
        from cex.gateio.rest import GateioPublicSpotRest, GateioPrivateSpotRest
        return GateioPublicSpotRest if not is_private else GateioPrivateSpotRest

    else:
        raise ValueError(f"Unsupported exchange: {exchange_name} private: {is_private}.")
