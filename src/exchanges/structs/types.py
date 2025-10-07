from typing import NewType, Literal

ExchangeName = NewType('Exchange', str)
AssetName = NewType('AssetName', str)
OrderId = NewType("OrderId", str)
SettleCurrency = Literal["usdt", "btc"]
