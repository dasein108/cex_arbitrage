"""
Modern Vectorized Strategy Backtester

"""
import asyncio
import pandas as pd
import time
from datetime import datetime
from typing import List, Dict, Optional, Literal

from exchanges.structs import Symbol, ExchangeEnum, AssetName
from exchanges.structs.enums import KlineInterval

# Import strategy signal architecture
from trading.signals_v2.implementation.inventory_spot_strategy_signal import InventorySpotStrategySignal
from trading.signals_v2.entities import BacktestingParams, PerformanceMetrics
from trading.signals_v2.strategy_signal import StrategySignal
from trading.data_sources.book_ticker.book_ticker_source import (BookTickerDbSource, CandlesBookTickerSource,
                                                            BookTickerSourceProtocol)

from trading.signals_v2.report_utils import arbitrage_trade_to_table, performance_metrics_table
type BacktestDataSource = Literal['candles', 'snapshot']


class SignalBacktester:
    """
    Modern Vectorized Strategy Backtester
    """

    def __init__(self,
                 initial_capital_usdt: float = 1000.0,
                 position_size_usdt: float = 100.0,
                 candles_timeframe=KlineInterval.MINUTE_1,
                 snapshot_seconds: int = 60):
        """
        Initialize vectorized backtester using strategy signal architecture.
        
        Args:
            initial_capital_usdt: Starting capital
            position_size_usdt: Default position size
        """
        self.initial_capital_usdt = initial_capital_usdt
        self.position_size_usdt = position_size_usdt
        self.exchanges: List[ExchangeEnum] = [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]
        self.data_source: Dict[BacktestDataSource, BookTickerSourceProtocol] = {'candles': CandlesBookTickerSource(),
                                                                                'snapshot': BookTickerDbSource()}
        self.candles_timeframe = candles_timeframe
        self.snapshot_seconds = snapshot_seconds

    async def run_single_backtest(self,
                        strategy: StrategySignal,
                        df: pd.DataFrame) -> PerformanceMetrics:
        """
        Run backtests for multiple strategies using strategy signal architecture.
        


        Returns:
            Dictionary with results for each strategy
        """

        start_time = time.perf_counter()
        performance = strategy.backtest(df)
        # Update performance stats
        end_time = time.perf_counter()
        backtest_time_ms = (end_time - start_time) * 1000

        print(f"✅ Backtesting completed in {backtest_time_ms:.2f}ms")
        return  performance

    async def run_backtest(self, symbol: Symbol,
                            data_source: BacktestDataSource,
                            hours: int = 24,
                            end_date: Optional[datetime] = None
                            ):
        # Load data once for all strategies
        timeframe = self.candles_timeframe if data_source == 'candles' else self.snapshot_seconds
        print(f"🚀 Starting vectorized backtesting for {symbol} with data source: {data_source}")

        df = await self.data_source[data_source].get_multi_exchange_data(self.exchanges,
                                                                         symbol, hours=hours,
                                                                         date_to=end_date,
                                                                         timeframe=timeframe)

        if df.empty:
            print(f"❌ No data available for {data_source}: {symbol}")
            return {'error': 'No data available'}

        print(f"✅ Data loaded: {len(df)} rows, from {df.index[0]} to {df.index[-1]}")

        backtesting_params = BacktestingParams(initial_balance_usd=self.initial_capital_usdt,
                                               position_size_usd=self.position_size_usdt)

        strategy=InventorySpotStrategySignal(min_profit_bps=30,
                                             backtesting_params=backtesting_params)

        result = await self.run_single_backtest(strategy, df)
        print(f"{strategy.name} Performance:")
        print(performance_metrics_table([result], True))
        print("Trades")
        print(arbitrage_trade_to_table(result.trades, include_header=True))


if __name__ == "__main__":
    async def main():
        backtester = SignalBacktester(initial_capital_usdt=1000.0,
                                      position_size_usdt=100.0,
                                      candles_timeframe=KlineInterval.MINUTE_1,
                                      snapshot_seconds=60)

        asset_name = 'FLK'
        await backtester.run_backtest(symbol=Symbol(base=AssetName(asset_name), quote=AssetName('USDT')),
                                      data_source='candles',
                                      hours=24)

    asyncio.run(main())