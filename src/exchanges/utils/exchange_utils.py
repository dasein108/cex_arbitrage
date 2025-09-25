from exchanges.structs import ExchangeEnum

def get_exchange_enum(exchange_name: str) -> ExchangeEnum:
    try:
        return ExchangeEnum(exchange_name.upper())
    except ValueError:
        raise ValueError(f"Exchange '{exchange_name}' is not supported.")