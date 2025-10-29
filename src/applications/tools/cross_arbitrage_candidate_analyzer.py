from config import HftConfig
from exchanges.exchange_factory import get_rest_implementation
from exchanges.structs import SymbolInfo, Symbol
from exchanges.structs.common import AssetInfo
from exchanges.structs.enums import ExchangeEnum, KlineInterval
from typing import List, Optional, Dict
import asyncio
from datetime import datetime, UTC
import pandas as pd
from infrastructure.logging import get_logger
from trading.analysis.data_sources import CandlesLoader

ANALYZER_TF = KlineInterval.MINUTE_5


class CrossArbitrageCandidateAnalyzer:
    def __init__(self,  exchanges: Optional[List[ExchangeEnum]] = None):
        self.exchanges = exchanges
        self.config = HftConfig()
        self.logger = get_logger("CrossArbitrageCandidateAnalyzer")
        self.candle_loader = CandlesLoader(logger=self.logger)

        self.clients = {exchange: self._get_exchange_client(exchange) for exchange in exchanges}


    def _get_exchange_client(self, exchange: ExchangeEnum):
        return get_rest_implementation(self.config.get_exchange_config(exchange.value), False)

    async def get_common_symbols(self, exchanges_count: int = 3):
        si_result = await asyncio.gather(*[c.get_symbols_info() for c in self.clients.values()])

        symbols_info: Dict[ExchangeEnum, SymbolInfo] = {}
        symbol_exchanges: Dict[Symbol, List[ExchangeEnum]] = {}
        for exchange, symbols in zip(self.clients.keys(), si_result):
            symbols_info[exchange] = symbols
            for symbol in symbols.keys():
                if symbol not in symbol_exchanges:
                    symbol_exchanges[symbol] = []
                symbol_exchanges[symbol].append(exchange)


        common_symbols = {symbol: exchanges for symbol, exchanges in symbol_exchanges.items() if len(exchanges) >= exchanges_count}
        return common_symbols, symbols_info

    async def get_candles(self, exchanges: List[ExchangeEnum], symbol: Symbol,  tf: KlineInterval,
                            start_date: datetime, end_date: datetime ):
        tasks = [
            self.candle_loader.download_candles(
                exchange=exchange,
                symbol=symbol,
                timeframe=tf,
                start_date=start_date,
                end_date=end_date,
            )
            for exchange in exchanges
        ]

        results = await asyncio.gather(*tasks)

        exchange_df_map: dict[ExchangeEnum, Optional[pd.DataFrame]] = {}
        for exchange, df in zip(exchanges, results):
            exchange_df_map[exchange] = df

    async def analyze_symbol(self, symbol: Symbol, exchanges: List[ExchangeEnum],
                             date_from: datetime, date_to: datetime):
        candles_by_exchange = await self.get_candles(
            exchanges=self.exchanges,
            symbol=symbol,
            tf=ANALYZER_TF,
            start_date=date_from,
            end_date=date_to
        )

    async def analyze(self, date_from: datetime, date_to: datetime):
        common_symbols, symbols_info = await self.get_common_symbols(exchanges_count=len(self.exchanges))
        self.logger.info(f"Found {len(common_symbols)} common symbols across exchanges.")
        for symbol, exchanges in common_symbols.items():
            await self.analyze_symbol(symbol, exchanges, date_from, date_to)

if __name__ == "__main__":
    analyzer = CrossArbitrageCandidateAnalyzer(
        exchanges=[ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]
    )

    async  def main():
        end_time = datetime.now(UTC)
        start_time = end_time - pd.Timedelta(hours=24)
        await analyzer.analyze(start_time, end_time)
        
    asyncio.run(main())

