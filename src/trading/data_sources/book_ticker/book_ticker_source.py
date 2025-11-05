from typing import Optional, Protocol, Union
from datetime import datetime, UTC
import asyncio

from db import get_database_manager
from exchanges.structs import ExchangeEnum, Symbol, AssetName
import pandas as pd

from exchanges.structs.enums import KlineInterval
# Temporarily commented out to fix imports
# from trading.analysis.book_ticker import BookTickerSnapshotLoader, CandlesLoader

from utils.kline_utils import get_interval_seconds
from ..db_book_ticker_loader import BookTickerSnapshotLoader
from ..candles_loader import CandlesLoader

class BookTickerSourceProtocol(Protocol):
    """Protocol for book ticker data sources."""
    async def get_multi_exchange_data(
        self,
        exchanges: list[ExchangeEnum],
        symbol: Symbol,
        date_to: Optional[datetime] = None,
        hours: int = 24,
        timeframe: Union[KlineInterval, int] = KlineInterval.MINUTE_1
    ) -> pd.DataFrame:
        """Fetch book ticker data from multiple exchanges."""
        ...


class BookTickerDbSource(BookTickerSourceProtocol):
    """Book ticker data source using snapshot loader and candles loader."""

    def __init__(self, window_minutes: int = 1):
        self.window_minutes = window_minutes
        self.snapshot_loader = BookTickerSnapshotLoader()

    async def get_multi_exchange_data(
        self,
        exchanges: list[ExchangeEnum],
        symbol: Symbol,
        date_to: Optional[datetime] = None,
        hours: int = 24,
        timeframe: Union[KlineInterval, int] = KlineInterval.MINUTE_1
    ) -> pd.DataFrame:
        """Fetch book ticker data from multiple exchanges."""


        await get_database_manager()

        end_time = datetime.now(UTC) if date_to is None else date_to
        start_time = end_time - pd.Timedelta(hours=hours)
        if isinstance(timeframe, int):
            timeframe_seconds = timeframe
        else:
            timeframe_seconds = get_interval_seconds(timeframe)
        tasks = [
            self.snapshot_loader.get_book_ticker_dataframe(
                exchange=exchange.value,
                symbol_base=symbol.base,
                symbol_quote=symbol.quote,
                start_time=start_time,
                end_time=end_time,
                rounding_seconds=timeframe_seconds
            )
            for exchange in exchanges
        ]
        results = await asyncio.gather(*tasks)

        exchange_df_map: dict[ExchangeEnum, Optional[pd.DataFrame]] = {}
        merged_df = pd.DataFrame()

        for exchange, df in zip(exchanges, results):
            if df is None or df.empty:
                 exchange_df_map[exchange] = None
                 continue
            # Prefix all column names with the exchange key (use enum name)
            prefixed = df.copy()
            prefixed = prefixed[["bid_price", "ask_price"]]
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
        self.window_minutes = window_minutes
        self.candles_loader = CandlesLoader()

    # async def download_exchange_data(self, exchange: ExchangeEnum, symbol,
    #                                  start_time: datetime, end_time: datetime,
    #                                  timeframe: KlineInterval) -> Optional[pd.DataFrame]:
    #     df = await self.candles_loader.download_candles(
    #         exchange=exchange,
    #         symbol=symbol,
    #         timeframe=timeframe,
    #         start_date=start_time,
    #         end_date=end_time,
    #     )
    #     return df

    async def get_multi_exchange_data(
        self,
        exchanges: list[ExchangeEnum],
        symbol: Symbol,
        date_to: Optional[datetime] = None,
        hours: int = 24,
        timeframe: KlineInterval = KlineInterval.MINUTE_1
    ) -> pd.DataFrame:
        """Fetch book ticker data from multiple exchanges."""
        end_time = datetime.now(UTC) if date_to is None else date_to
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
            prefixed["timestamp"] = pd.to_datetime(prefixed["timestamp"], unit="ms", utc=True)
            prefixed.set_index("timestamp", inplace=True)
            prefixed.columns = [f"{exchange.value}_{col}" for col in prefixed.columns]
            exchange_df_map[exchange] = prefixed

        # Merge all available dataframes into a single dataframe (outer join on index)
        available = [df for df in exchange_df_map.values() if df is not None]
        merged_df = pd.concat(available, axis=1, join="outer") if available else pd.DataFrame()
        merged_df.sort_index(inplace=True)

        return merged_df

    async def get_multi_exchange_candles_data(
            self,
            exchanges: list[ExchangeEnum],
            symbol: Symbol,
            date_to: Optional[datetime] = None,
            hours: int = 24,
            timeframe: KlineInterval = KlineInterval.MINUTE_1
    ) -> pd.DataFrame:
        """Fetch book ticker data from multiple exchanges."""
        end_time = datetime.now(UTC) if date_to is None else date_to
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
            prefixed = df[['open', 'high', 'low', 'close', 'volume']].copy()
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
        # source = CandlesBookTickerSource()
        await get_database_manager()
        source = CandlesBookTickerSource()
        symbol = Symbol(base=AssetName("F"), quote=AssetName("USDT"))
        df = await source.get_multi_exchange_candles_data(
            exchanges=[ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES],
            symbol=symbol,
            hours=24,
            timeframe=KlineInterval.MINUTE_5
        )
        print(df)

    asyncio.run(main())

