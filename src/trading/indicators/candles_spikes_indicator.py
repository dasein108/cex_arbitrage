from exchanges.structs import ExchangeEnum, Symbol, AssetName
from exchanges.structs.enums import KlineInterval
from trading.data_sources.candles_loader import CandlesLoader
import pandas as pd
import numpy as np
from trading.data_sources.column_utils import get_column_key
from typing import Dict, List
from trading.signals_v2.report_utils import generate_generic_report
class CandlesIndicator:
    def __init__(self, exchanges: List[ExchangeEnum], symbol: Symbol, timeframe: KlineInterval,
                 lookback_period_hours: int):
        self.candles_loader = CandlesLoader()
        self.df: pd.DataFrame = pd.DataFrame()
        self.exchanges = exchanges
        self.timeframe = timeframe
        self.lookback_period_hours = lookback_period_hours
        self.symbol = symbol

    async def update(self):
        self.df = await self.candles_loader.get_multi_candles_df(self.exchanges, self.symbol, hours=self.lookback_period_hours,
                                                 timeframe=self.timeframe)
        return self.df

class CandlesSpikeIndicator(CandlesIndicator):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stats: Dict[ExchangeEnum, dict] = {}

    async def update(self):
        await super().update()
        for exchange in self.exchanges:
            self.df = self._detect_adaptive_spikes(exchange, price_col='close', window=50, quantile_range=(0.01, 0.99))
        return self.df

    def _detect_adaptive_spikes(self, exchange: ExchangeEnum, price_col='close', window=50, quantile_range=(0.01, 0.99)):
        """
        Detects adaptive outliers (spikes) and computes volatility metrics.

        Parameters
        ----------
        exchange: ExchangeEnum
        price_col : str
            Column name with prices (e.g., 'close').
        window : int
            Rolling window for adaptive calculations.
        quantile_range : tuple
            Lower and upper quantiles for dynamic outlier thresholding.

        Returns
        -------
        pd.DataFrame : with columns:
            - true_price : adaptive moving average (volatility-adjusted)
            - upper_q, lower_q : dynamic quantile thresholds
            - deviation : price - true_price
            - is_spike : boolean spike flag
            - volatility : rolling std deviation of deviations
        """

        df = self.df # .copy()
        price_col = get_column_key(exchange, price_col)
        true_price_col =  get_column_key(exchange, 'true_price')
        deviation_col = get_column_key(exchange, 'deviation')
        deviation_pct_col = get_column_key(exchange, 'deviation_pct')

        volatility_col = get_column_key(exchange, 'volatility')
        upper_q_col = get_column_key(exchange, 'upper_q')
        lower_q_col = get_column_key(exchange, 'lower_q')
        is_spike_col = get_column_key(exchange, 'is_spike')
        price = df[price_col]

        # Compute short-term volatility
        vol = price.rolling(window).std().bfill()
        vol_norm = vol / vol.mean()

        # Adaptive smoothing: faster EMA when volatility is low
        alpha = (1 / window) * (1 / (1 + vol_norm))
        df[true_price_col] = price.ewm(alpha=alpha.mean(), adjust=False).mean()

        # Deviation from true price
        df[deviation_col] = price - df[true_price_col]
        df[deviation_pct_col] = df[deviation_col] / df[true_price_col] * 100

        # Dynamic quantiles based on rolling window
        df[upper_q_col] = df[deviation_pct_col].rolling(window).quantile(quantile_range[1]).bfill()
        df[lower_q_col] = df[deviation_pct_col].rolling(window).quantile(quantile_range[0]).bfill()

        # Spike flag
        df[is_spike_col] = (df[deviation_pct_col] > df[upper_q_col]) | (df[deviation_pct_col] < df[lower_q_col])

        # Rolling volatility metric (price fluctuation around true price)
        df[volatility_col] = df[deviation_pct_col].rolling(window).std().bfill()

        q_low, q_high = df[deviation_pct_col].quantile(quantile_range)
        up_spikes = df.loc[df[deviation_pct_col] > q_high, deviation_pct_col]
        down_spikes = df.loc[df[deviation_pct_col] < q_low, deviation_pct_col]

        # Helper for most frequent spike level (rounded)
        def spike_mode(series):
            if series.empty:
                return None
            rounded = np.round(series, 1)  # group similar magnitudes
            return rounded.value_counts().idxmax(), rounded.value_counts().max()

        up_mode_val, up_mode_count = spike_mode(up_spikes)
        down_mode_val, down_mode_count = spike_mode(down_spikes)

        stats = {
            "volatility_std": df[deviation_pct_col].std(),
            "mean_abs_dev": df[deviation_pct_col].abs().mean(),
            "spike_count": int(df[is_spike_col].sum()),
            "up_spikes": len(up_spikes),
            "down_spikes": len(down_spikes),
            "avg_volatility": df[volatility_col].mean(),
            "max_spike_dev_pct": df.loc[df[is_spike_col], deviation_pct_col].abs().max() if df[is_spike_col].any() else 0,
            # spike-specific
            "mean_up_spike": up_spikes.mean() if not up_spikes.empty else 0,
            "mean_down_spike": down_spikes.mean() if not down_spikes.empty else 0,
            "most_common_up_spike": up_mode_val,
            "most_common_up_spike_count": up_mode_count,
            "most_common_down_spike": down_mode_val,
            "most_common_down_spike_count": down_mode_count,
        }

        self.stats[exchange] = stats
        return df




def plot_multi_exchange_spikes(exchanges: List[ExchangeEnum], df: pd.DataFrame, price_col='close', window=200):
    """
    Visualizes adaptive true price, volatility bands, and spikes for multiple exchanges.

    Parameters
    ----------
    exchanges : list[ExchangeEnum]
        Exchanges to visualize (must already have columns in self.df).
    price_col : str
        Base column name, e.g., 'close'.
    window : int
        Smoothing window for rolling averages of displayed values.
    """
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    EXCHANGE_COLORS = {
        ExchangeEnum.GATEIO: "#1f77b4",  # blue
        ExchangeEnum.GATEIO_FUTURES: "#ff7f0e",  # orange
        ExchangeEnum.MEXC: "#2ca02c",  # green
    }

    fig, ax = plt.subplots(figsize=(14, 7))

    for exchange in exchanges:
        color =EXCHANGE_COLORS[exchange]

        dev_key = get_column_key(exchange, 'deviation_pct')
        upper_q_key = get_column_key(exchange, 'upper_q')
        lower_q_key = get_column_key(exchange, 'lower_q')
        is_spike_key = get_column_key(exchange, 'is_spike')

        # plot deviation line
        ax.plot(df.index, df[dev_key], lw=1.2, label=f'{exchange.name} Deviation %', color=color)

        # quantile band (volatility envelope)
        ax.fill_between(
            df.index,
            df[lower_q_key],
            df[upper_q_key],
            alpha=0.15,
            label=f'{exchange.name} Quantile Band',
            color=color
        )

        # mark spikes
        spikes = df[df[is_spike_key]]
        ax.scatter(
            spikes.index,
            df.loc[spikes.index, dev_key],
            s=25, alpha=0.7, label=f'{exchange.name} Spikes',
            color=color
        )

        for idx, row in spikes.iterrows():
            spike_size = row[dev_key]
            ax.text(
                idx,
                row[dev_key],
                f"{spike_size:.1f}%",
                fontsize=7,
                color=color,
                alpha=0.8,
                ha='center',
                va='bottom'
            )
    ax.axhline(0, color='black', lw=0.8, ls='--')
    ax.set_title("Adaptive Spike Detection (Deviation from True Price)", fontsize=14)
    ax.set_ylabel("Deviation % from True Price")
    ax.legend(ncol=2)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    from exchanges.structs.enums import ExchangeEnum
    from exchanges.structs import Symbol
    import asyncio

    async def main():
        exchanges = [ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES, ExchangeEnum.MEXC]
        asset_name = 'FLK'
        indicator = CandlesSpikeIndicator(
            exchanges=exchanges,
            symbol=Symbol(base=AssetName(asset_name), quote=AssetName("USDT")),
            timeframe=KlineInterval.MINUTE_1,
            lookback_period_hours=24
        )
        df = await indicator.update()
        print(df.tail())
        for ex, stats in indicator.stats.items():
            print(f"Stats for {ex.value}: {stats}")

        plot_multi_exchange_spikes(exchanges, df, price_col='close', window=200)

    asyncio.run(main())