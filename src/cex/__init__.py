from enum import Enum
from structs.exchange import ExchangeName

class ExchangeEnum(Enum):
    MEXC = ExchangeName("MEXC")
    GATEIO = ExchangeName("GATEIO")