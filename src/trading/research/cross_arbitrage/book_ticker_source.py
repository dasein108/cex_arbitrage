from typing import Optional, Protocol
from datetime import datetime, UTC
import asyncio

from db import get_database_manager
from exchanges.structs import ExchangeEnum, Symbol, AssetName
import pandas as pd

from exchanges.structs.enums import KlineInterval
from trading.analysis.data_sources import BookTickerSnapshotLoader, CandlesLoader
from utils.kline_utils import get_interval_seconds


class BookTickerSourceProtocol(Protocol):
    """Protocol for book ticker data sources."""
    async def get_multi_exchange_data(
        self,
        exchanges: list[ExchangeEnum],
        symbol: Symbol,
        hours: int,
        timeframe: KlineInterval
    ) -> pd.DataFrame:
        """Fetch book ticker data from multiple exchanges."""
        ...


class BookTickerDbSource(BookTickerSourceProtocol):
    """Book ticker data source using snapshot loader and candles loader."""

    def __init__(self, window_minutes: int = 1):
        super().__init__(window_minutes)
        self.snapshot_loader = BookTickerSnapshotLoader()

    async def get_multi_exchange_data(
        self,
        exchanges: list[ExchangeEnum],
        symbol: Symbol,
        hours: int,
        timeframe: KlineInterval
    ) -> pd.DataFrame:
        """Fetch book ticker data from multiple exchanges."""
        end_time = datetime.now(UTC)
        start_time = end_time - pd.Timedelta(hours=hours)
        timeframe_minutes = get_interval_seconds(timeframe)
        tasks = [
            self.snapshot_loader.get_book_ticker_dataframe(
                exchange=exchange.value,
                symbol_base=symbol.base,
                symbol_quote=symbol.quote,
                start_time=start_time,
                end_time=end_time,
                rounding_seconds=timeframe_minutes * 60
            )
            for exchange in exchanges
        ]
        results = await asyncio.gather(*tasks)

        exchange_df_map: dict[ExchangeEnum, Optional[pd.DataFrame]] = {}

        for exchange, df in zip(exchanges, results):
         if df is None or df.empty:
             exchange_df_map[exchange] = None
             continue
         # Prefix all column names with the exchange key (use enum name)
         prefixed = df.copy()
         cols_to_keep = ["timeframe", "bid_price", "ask_price"]
         prefixed = prefixed[cols_to_keep]
         prefixed.set_index("timestamp", inplace=True)
         prefixed.columns = [f"{exchange.value}_{col}" for col in prefixed.columns]
         exchange_df_map[exchange] = prefixed

        # Merge all available dataframes into a single dataframe (outer join on index)
        available = [df for df in exchange_df_map.values() if df is not None]
        merged_df = pd.concat(available, axis=1, join="outer") if available else pd.DataFrame()
        merged_df.sort_index(inplace=True)

        return merged_df

class CandlesBookTickerSource(BookTickerSourceProtocol):
    """Book ticker data source using candles loader."""
    SPREAD_FACTOR = 0.0005  # 0.05% spread assumption for bid/ask simulation
    def __init__(self, window_minutes: int = 1):
        super().__init__(window_minutes)
        self.candles_loader = CandlesLoader()

    async def get_multi_exchange_data(
        self,
        exchanges: list[ExchangeEnum],
        symbol: Symbol,
        hours: int,
        timeframe: KlineInterval
    ) -> pd.DataFrame:
        """Fetch book ticker data from multiple exchanges."""
        end_time = datetime.now(UTC)
        start_time = end_time - pd.Timedelta(hours=hours)
        tasks = [
            self.candles_loader.download_candles(
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_time,
                end_date=end_time,
            )
            for exchange in exchanges
        ]
        results = await asyncio.gather(*tasks)

        exchange_df_map: dict[ExchangeEnum, Optional[pd.DataFrame]] = {}

        for exchange, df in zip(exchanges, results):
            if df is None or df.empty:
                 exchange_df_map[exchange] = None
                 continue
            # Prefix all column names with the exchange key (use enum name)
            prefixed = df.copy()
            prefixed[f"bid_price"] = prefixed['close'] * (1 - self.SPREAD_FACTOR)
            prefixed[f"ask_price"] = prefixed['close'] * (1 + self.SPREAD_FACTOR)
            prefixed = prefixed[["timestamp", "bid_price", "ask_price"]]
            prefixed.set_index("timestamp", inplace=True)
            prefixed.columns = [f"{exchange.value}_{col}" for col in prefixed.columns]
            exchange_df_map[exchange] = prefixed

        # Merge all available dataframes into a single dataframe (outer join on index)
        available = [df for df in exchange_df_map.values() if df is not None]
        merged_df = pd.concat(available, axis=1, join="outer") if available else pd.DataFrame()
        merged_df.sort_index(inplace=True)

        return merged_df

if __name__ == "__main__":
    import asyncio
    from exchanges.structs import Symbol

    async def main():
        # await get_database_manager()
        source = CandlesBookTickerSource()
        symbol = Symbol(base=AssetName("F"), quote=AssetName("USDT"))
        df = await source.get_multi_exchange_data(
            exchanges=[ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES],
            symbol=symbol,
            hours=1,
            timeframe=KlineInterval.MINUTE_5
        )
        print(df)

    asyncio.run(main())

