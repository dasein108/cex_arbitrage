"""
Modern Vectorized Strategy Backtester

"""
import asyncio
import pandas as pd
import time
from datetime import datetime
from typing import List, Dict, Optional, Literal, Union

from exchanges.structs import Symbol, ExchangeEnum, AssetName, Fees
from exchanges.structs.enums import KlineInterval
from trading.data_sources.candles_loader import CandlesLoader

# Import strategy signal architecture
from trading.signals_v2.implementation.inventory_spot_strategy_signal import InventorySpotStrategySignal
from trading.signals_v2.implementation.spike_catching_strategy_signal import SpikeCatchingStrategySignal
from trading.signals_v2.implementation.mexc_gateio_futures_arbitrage_signal import MexcGateioFuturesArbitrageSignal
from trading.signals_v2.implementation.cross_exchange_parity_signal import CrossExchangeParitySignal
from trading.signals_v2.entities import BacktestingParams, PerformanceMetrics
from trading.signals_v2.strategy_signal import StrategySignal
from trading.data_sources.book_ticker.book_ticker_source import (BookTickerDbSource, CandlesBookTickerSource,
                                                                 BookTickerSourceProtocol)

from trading.signals_v2.report_utils import arbitrage_trade_to_table, performance_metrics_table, generate_generic_report
from trading.signals_v2.visualization import visualize_arbitrage_results

type BacktestDataSource = Literal['candles_book_ticker', 'snapshot_book_ticker', 'candles']

TRADING_FEES = {
    ExchangeEnum.MEXC: Fees(taker_fee=0.05, maker_fee=0.0),
    ExchangeEnum.GATEIO: Fees(taker_fee=0.1, maker_fee=0.1),
    ExchangeEnum.GATEIO_FUTURES: Fees(taker_fee=0.05, maker_fee=0.05),
}


class SignalBacktester:
    """
    Modern Vectorized Strategy Backtester with Parameter Optimization
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
        self.data_source: Dict[BacktestDataSource, BookTickerSourceProtocol] = {'candles_book_ticker': CandlesBookTickerSource(),
                                                                                'snapshot_book_ticker': BookTickerDbSource(),
                                                                                'candles': CandlesLoader()}
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
        return performance

    async def optimize_strategy_parameters(self, 
                                          symbol: Symbol,
                                          data_source: BacktestDataSource,
                                          hours: int = 24,
                                          end_date: Optional[datetime] = None) -> Dict:
        """
        Systematic parameter optimization using grid search.
        
        Returns:
            Dict containing best parameters and optimization results
        """
        print(f"🔧 Starting parameter optimization for {symbol}")
        
        # Load data once for all parameter combinations
        timeframe = self.candles_timeframe if data_source == 'candles' else self.snapshot_seconds
        

        df = await self.data_source[data_source].get_multi_exchange_data(
            self.exchanges, symbol, hours=hours, date_to=end_date, timeframe=timeframe)

        if df.empty:
            return {'error': 'No data available for optimization'}

        # Split data: 70% training, 30% validation
        split_idx = int(len(df) * 0.7)
        train_df = df.iloc[:split_idx]
        validation_df = df.iloc[split_idx:]
        
        print(f"📊 Data split: {len(train_df)} training rows, {len(validation_df)} validation rows")

        # Parameter grid based on debug analysis findings
        param_grid = {
            'spike_offset_multiplier': [2.0, 3.0, 4.0, 5.0, 6.0],  # Handle high volatility
            'stabilization_threshold': [1.0, 1.5, 2.0, 2.5, 3.0],  # Exit condition sensitivity
            'max_position_time_minutes': [10, 15, 20, 25, 30]       # Position holding time
        }
        
        print(f"🎯 Testing {len(param_grid['spike_offset_multiplier']) * len(param_grid['stabilization_threshold']) * len(param_grid['max_position_time_minutes'])} parameter combinations")

        # Enhanced backtesting parameters
        backtesting_params = BacktestingParams(
            initial_balance_usd=self.initial_capital_usdt,
            position_size_usd=self.position_size_usdt,
            transfer_delay_minutes=8,
            transfer_fee_usd=0.0,
            slippage_pct=0.05,
            execution_failure_rate=0.10,
        )

        best_params = None
        best_score = float('-inf')
        optimization_results = []

        # Grid search with progress tracking
        total_combinations = len(param_grid['spike_offset_multiplier']) * len(param_grid['stabilization_threshold']) * len(param_grid['max_position_time_minutes'])
        current_combination = 0

        for spike_offset in param_grid['spike_offset_multiplier']:
            for stabilization_threshold in param_grid['stabilization_threshold']:
                for max_position_time in param_grid['max_position_time_minutes']:
                    current_combination += 1
                    
                    # Create strategy with current parameters
                    strategy = SpikeCatchingStrategySignal(
                        symbol=symbol,
                        spike_offset_multiplier=spike_offset,
                        stabilization_threshold=stabilization_threshold,
                        max_position_time_minutes=max_position_time,
                        backtesting_params=backtesting_params,
                        fees=TRADING_FEES
                    )

                    try:
                        # Test on training data
                        train_performance = await self.run_single_backtest(strategy, train_df)
                        
                        # Calculate composite score (prioritize profitable trades with good win rate)
                        if train_performance.total_trades > 0:
                            # Score combines profitability, win rate, and risk-adjusted returns
                            profit_score = train_performance.total_pnl_pct
                            win_rate_score = train_performance.win_rate
                            risk_adjusted_score = train_performance.sharpe_ratio * 10  # Scale Sharpe ratio
                            
                            # Composite score with weights
                            composite_score = (
                                profit_score * 0.4 +           # 40% weight on profitability
                                win_rate_score * 0.3 +         # 30% weight on win rate
                                risk_adjusted_score * 0.2 +    # 20% weight on risk-adjusted returns
                                train_performance.total_trades * 0.1  # 10% weight on trade frequency
                            )
                        else:
                            composite_score = -1000  # Penalty for no trades
                        
                        # Track results
                        result = {
                            'spike_offset_multiplier': spike_offset,
                            'stabilization_threshold': stabilization_threshold,
                            'max_position_time_minutes': max_position_time,
                            'total_trades': train_performance.total_trades,
                            'total_pnl_pct': train_performance.total_pnl_pct,
                            'win_rate': train_performance.win_rate,
                            'sharpe_ratio': train_performance.sharpe_ratio,
                            'composite_score': composite_score
                        }
                        
                        optimization_results.append(result)
                        
                        # Update best parameters
                        if composite_score > best_score:
                            best_score = composite_score
                            best_params = result.copy()
                        
                        # Progress update
                        if current_combination % 5 == 0 or current_combination == total_combinations:
                            print(f"⚡ Progress: {current_combination}/{total_combinations} | "
                                  f"Current: P&L={train_performance.total_pnl_pct:.2f}%, "
                                  f"Trades={train_performance.total_trades}, "
                                  f"Score={composite_score:.2f}")
                    
                    except Exception as e:
                        print(f"❌ Error testing params {spike_offset}, {stabilization_threshold}, {max_position_time}: {e}")
                        continue

        if not best_params:
            return {'error': 'No valid parameter combinations found'}

        print(f"\n🏆 Best parameters found:")
        print(f"   Spike Offset Multiplier: {best_params['spike_offset_multiplier']}")
        print(f"   Stabilization Threshold: {best_params['stabilization_threshold']}%")
        print(f"   Max Position Time: {best_params['max_position_time_minutes']} minutes")
        print(f"   Training Score: {best_params['composite_score']:.2f}")
        print(f"   Training P&L: {best_params['total_pnl_pct']:.2f}%")
        print(f"   Training Trades: {best_params['total_trades']}")

        # Validate on out-of-sample data
        print(f"\n🧪 Validating on out-of-sample data...")
        validation_strategy = SpikeCatchingStrategySignal(
            symbol=symbol,
            spike_offset_multiplier=best_params['spike_offset_multiplier'],
            stabilization_threshold=best_params['stabilization_threshold'],
            max_position_time_minutes=best_params['max_position_time_minutes'],
            backtesting_params=backtesting_params,
            fees=TRADING_FEES
        )
        
        validation_performance = await self.run_single_backtest(validation_strategy, validation_df)
        
        print(f"📊 Validation Results:")
        print(f"   P&L: {validation_performance.total_pnl_pct:.2f}%")
        print(f"   Trades: {validation_performance.total_trades}")
        print(f"   Win Rate: {validation_performance.win_rate:.1f}%")
        print(f"   Sharpe Ratio: {validation_performance.sharpe_ratio:.2f}")

        # Sort all results by score for analysis
        optimization_results.sort(key=lambda x: x['composite_score'], reverse=True)
        
        return {
            'best_params': best_params,
            'validation_performance': {
                'total_pnl_pct': validation_performance.total_pnl_pct,
                'total_trades': validation_performance.total_trades,
                'win_rate': validation_performance.win_rate,
                'sharpe_ratio': validation_performance.sharpe_ratio
            },
            'top_10_results': optimization_results[:10],
            'total_combinations_tested': len(optimization_results),
            'data_split': {
                'train_samples': len(train_df),
                'validation_samples': len(validation_df)
            }
        }


    async def run_backtest(self, symbol: Symbol,
                           data_source: BacktestDataSource,
                           hours: int = 24,
                           end_date: Optional[datetime] = None,
                           strategy_type: str = "inventory_spot"
                           ):
        # Load data once for all strategies
        timeframe = self.snapshot_seconds if data_source == 'snapshot_book_ticker' else self.candles_timeframe
        print(f"🚀 Starting vectorized backtesting for {symbol} with data source: {data_source}")

        # Use candles data for spike catching strategy, book ticker for others

        df = await self.data_source[data_source].get_multi_exchange_data(self.exchanges,
                                                                         symbol, hours=hours,
                                                                         date_to=end_date,
                                                                         timeframe=timeframe)


        df.dropna(inplace=True)
        # df.to_csv('debug_backtest_data.csv')
        if df.empty:
            print(f"❌ No data available for {data_source}: {symbol}")
            return {'error': 'No data available'}

        print(f"✅ Data loaded: {len(df)} rows, from {df.index[0]} to {df.index[-1]}")

        # Enhanced backtesting parameters with realistic costs
        backtesting_params = BacktestingParams(
            initial_balance_usd=self.initial_capital_usdt,
            position_size_usd=self.position_size_usdt,
            transfer_delay_minutes=8,  # More realistic transfer time
            transfer_fee_usd=0.0,  # Realistic transfer cost
            slippage_pct=0.05,  # 0.05% slippage
            execution_failure_rate=0.10,  # 10% failure rate

        )

        # Choose strategy type and optimization parameters
        if strategy_type == "spot_futures":
            strategy = MexcGateioFuturesArbitrageSignal()
        elif strategy_type == "spike_catching":
            # OPTIMIZED PARAMETERS based on debug analysis
            strategy = SpikeCatchingStrategySignal(
                symbol=symbol,
                spike_offset_multiplier=2.0,  # Increased from 2.5 to handle high volatility
                stabilization_threshold=2.0,  # Increased from 0.5% to 2% for volatile conditions
                max_position_time_minutes=60,  # Reduced from 30 to 15 minutes for faster exits
                backtesting_params=backtesting_params,
                fees=TRADING_FEES
            )
        elif strategy_type == "cross_exchange_parity":
            strategy = CrossExchangeParitySignal(
                params=dict(
                    parity_threshold_bps=5.0,
                    lookback_periods=50,
                    divergence_multiplier=2.5,
                    position_size_usd=self.position_size_usdt,
                    max_position_time_minutes=120,
                    min_hold_time_minutes=5,
                    max_spread_bps=50.0,
                    take_profit_bps=15.0,
                    max_daily_positions=5
                ),
                backtesting_params=backtesting_params,
                fees=TRADING_FEES
            )
        else:
            strategy = InventorySpotStrategySignal(
                params=dict(
                    mexc_spread_threshold_bps=30,
                    gateio_spread_threshold_bps=30
                ),
                backtesting_params=backtesting_params,
                fees=TRADING_FEES
            )

        result = await self.run_single_backtest(strategy, df)
        print(f'* STRATEGY: {strategy.name}')
        print('*' * 20)
        print(f"Analysis:")
        print(generate_generic_report(strategy.analysis_results))
        print(f"Performance:")
        print(performance_metrics_table([result], True))
        print("Trades")
        print(arbitrage_trade_to_table(result.trades, include_header=True))

        # Generate comprehensive visualization
        print(f"\n📊 Generating visualization for {symbol} trading analysis...")
        base_name = symbol.base.value if hasattr(symbol.base, 'value') else str(symbol.base)
        quote_name = symbol.quote.value if hasattr(symbol.quote, 'value') else str(symbol.quote)
        symbol_name = f"{base_name}/{quote_name}"
        visualize_arbitrage_results(
            df=df,
            trades=result.trades,
            performance_metrics=result,
            symbol_name=symbol_name,
            save_path=f"arbitrage_analysis_{base_name}_{quote_name}_{data_source}.png"
        )
        print(f"✅ Visualization saved: arbitrage_analysis_{base_name}_{quote_name}_{data_source}.png")


if __name__ == "__main__":
    async def main():
        backtester = SignalBacktester(initial_capital_usdt=1000.0,
                                      position_size_usdt=100.0,
                                      candles_timeframe=KlineInterval.MINUTE_1,
                                      snapshot_seconds=60)

        asset_name = 'U'
        symbol = Symbol(base=AssetName(asset_name), quote=AssetName('USDT'))
        
        # Choose mode: 'optimize' or 'backtest'
        mode = 'backtest'  # Set to 'backtest' for regular backtesting
        
        if mode == 'optimize':
            print("🚀 Running parameter optimization...")
            optimization_results = await backtester.optimize_strategy_parameters(
                symbol=symbol,
                data_source='candles',
                hours=24  # Use more data for optimization
            )
            
            if 'error' in optimization_results:
                print(f"❌ Optimization failed: {optimization_results['error']}")
                return
            
            print(f"\n📈 OPTIMIZATION SUMMARY")
            print(f"=" * 50)
            print(f"Total combinations tested: {optimization_results['total_combinations_tested']}")
            print(f"Data split: {optimization_results['data_split']['train_samples']} train, {optimization_results['data_split']['validation_samples']} validation")
            
            best = optimization_results['best_params']
            validation = optimization_results['validation_performance']
            
            print(f"\n🏆 OPTIMAL PARAMETERS:")
            print(f"   Spike Offset Multiplier: {best['spike_offset_multiplier']}")
            print(f"   Stabilization Threshold: {best['stabilization_threshold']}%")
            print(f"   Max Position Time: {best['max_position_time_minutes']} minutes")
            
            print(f"\n📊 VALIDATION PERFORMANCE:")
            print(f"   P&L: {validation['total_pnl_pct']:.2f}%")
            print(f"   Total Trades: {validation['total_trades']}")
            print(f"   Win Rate: {validation['win_rate']:.1f}%")
            print(f"   Sharpe Ratio: {validation['sharpe_ratio']:.2f}")
            
            print(f"\n🎯 TOP 5 PARAMETER COMBINATIONS:")
            for i, result in enumerate(optimization_results['top_10_results'][:5], 1):
                print(f"   {i}. Offset={result['spike_offset_multiplier']}, "
                      f"Threshold={result['stabilization_threshold']}%, "
                      f"Time={result['max_position_time_minutes']}min | "
                      f"P&L={result['total_pnl_pct']:.2f}%, "
                      f"Trades={result['total_trades']}, "
                      f"Score={result['composite_score']:.2f}")
                      
        else:
            print("🚀 Running regular backtesting...")
            await backtester.run_backtest(symbol=symbol,
                                          data_source='snapshot_book_ticker',
                                          # cross_exchange_parity, inventory_spot, spike_catching
                                          strategy_type = "spot_futures",# "inventory_spot",
                                          hours=24)


    asyncio.run(main())
