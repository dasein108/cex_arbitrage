from infrastructure.logging import LoggerFactory


def disable_default_exchange_logging():
    # Reduce noisy exchange logs
    logger_names = [
        "GATEIO_SPOT.ws.private", "GATEIO_SPOT.ws.public",
        "GATEIO_FUTURES.ws.private", "GATEIO_FUTURES.ws.public",
        "MEXC_SPOT.ws.private", "MEXC_SPOT.ws.public",
        "MEXC_SPOT.MEXC_SPOT_private", "GATEIO_FUTURES.GATEIO_FUTURES_private"
                                       "rest.client.gateio", "rest.client.mexc", "rest.client.mexc_spot"
    ]

    for logger_name in logger_names:
        LoggerFactory.override_logger(logger_name, min_level="ERROR")