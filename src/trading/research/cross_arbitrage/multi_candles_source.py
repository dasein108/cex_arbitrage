from typing import Optional
from datetime import datetime, UTC
from exchanges.structs import ExchangeEnum, Symbol, AssetName
import pandas as pd
import asyncio
from exchanges.structs.enums import KlineInterval
from trading.analysis.data_sources import CandlesLoader
from utils.kline_utils import get_interval_seconds



class MultiCandlesSource:
    """Book ticker data source using candles loader."""
    def __init__(self):
        self.candles_loader = CandlesLoader()

    async def get_multi_candles_df(
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
        source = MultiCandlesSource()
        symbol = Symbol(base=AssetName("F"), quote=AssetName("USDT"))
        df = await source.get_multi_candles_df(
            exchanges=[ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES],
            symbol=symbol,
            hours=24,
            timeframe=KlineInterval.MINUTE_5
        )
        print(df)

    asyncio.run(main())

