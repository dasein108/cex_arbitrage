from exchanges.structs import ExchangeEnum


def get_column_key(exchange_key: ExchangeEnum, col_name: str) -> str:
    return f'{exchange_key.value}:{col_name}'