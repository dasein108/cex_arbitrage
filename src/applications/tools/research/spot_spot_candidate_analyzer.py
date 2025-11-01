"""
Minimal Cross-Exchange Candle Data Loader with Backtesting

Downloads candles for a specific symbol from multiple exchanges and merges into single DataFrame.
Includes comprehensive backtesting framework for mean reversion strategies.
"""

import asyncio
import pandas as pd
from datetime import datetime, UTC, timedelta
from pathlib import Path

from config import HftConfig
from exchanges.exchange_factory import get_rest_implementation
from exchanges.structs import Symbol
from exchanges.structs.common import AssetName
from exchanges.structs.enums import ExchangeEnum, KlineInterval
from infrastructure.logging import get_logger
from trading.research.cross_arbitrage.multi_candles_source import MultiCandlesSource

pd.set_option('display.precision', 12)
pd.set_option('display.float_format', None)

class SpotSpotArbitrageAnalyzer:
    """Minimal candle loader for cross-exchange analysis"""

    def __init__(self):
        self.config = HftConfig()
        self.logger = get_logger("SpotSpotArbitrageAnalyzer")
        self.candles_source = MultiCandlesSource()

        # Exchanges to fetch data from
        self.exchanges = [
            ExchangeEnum.MEXC,
            ExchangeEnum.GATEIO,
            ExchangeEnum.GATEIO_FUTURES
        ]

    async def load_symbol_data(self, symbol: Symbol, hours: int = 24) -> pd.DataFrame:
        """Load candle data for symbol from all exchanges and merge into single DataFrame"""

        # Time range
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(hours=hours)

        self.logger.info(f"📊 Loading candle data for {symbol} from {start_time} to {end_time}")

        df = await self.candles_source.get_multi_candles_df(
            exchanges=self.exchanges,
            symbol=symbol,
            date_to=end_time,
            hours=hours,
            timeframe=KlineInterval.MINUTE_1)

        return df

    async def analyze_symbol(self, symbol: Symbol, hours: int = 24):
        """Analyze loaded candle data for arbitrage opportunities"""
        df = await self.load_symbol_data(symbol, hours)

        if df.empty:
            self.logger.warning(f"⚠️ No candle data available for {symbol}")
            return

        self.logger.info(f"✅ Loaded candle data for {symbol}")

        # Column names
        mexc_c_col = f'{ExchangeEnum.MEXC.value}_close'
        gateio_c_col = f'{ExchangeEnum.GATEIO.value}_close'
        gateio_fut_c_col = f'{ExchangeEnum.GATEIO_FUTURES.value}_close'

        mexc_l_col = f'{ExchangeEnum.MEXC.value}_low'
        gateio_l_col = f'{ExchangeEnum.GATEIO.value}_low'
        gateio_fut_l_col = f'{ExchangeEnum.GATEIO_FUTURES.value}_low'

        mexc_h_col = f'{ExchangeEnum.MEXC.value}_high'
        gateio_h_col = f'{ExchangeEnum.GATEIO.value}_high'
        gateio_fut_h_col = f'{ExchangeEnum.GATEIO_FUTURES.value}_high'

        def diff_perc(col1, col2):
            denom = df[col2]
            num = df[col1] - denom
            pct = num.div(denom).mul(100)
            # avoid division-by-zero and replace NaN/inf with 0
            pct = pct.where(denom != 0, 0).fillna(0)
            return pct

        # Basic spread calculations
        df['mexc_vs_gateio_pct'] = diff_perc(mexc_c_col, gateio_c_col)
        df['mexc_vs_gateio_fut_pct'] = diff_perc(mexc_c_col, gateio_fut_c_col)
        df['gateio_vs_gateio_fut_pct'] = diff_perc(gateio_c_col, gateio_fut_c_col)
        df['mexc_cl'] = diff_perc(mexc_c_col, mexc_l_col)
        df['gateio_cl'] = diff_perc(gateio_c_col, gateio_l_col)
        df['gateio_fut_cl'] = diff_perc(gateio_fut_c_col, gateio_fut_l_col)
        df['mexc_ch'] = diff_perc(mexc_c_col, mexc_h_col)
        df['gateio_ch'] = diff_perc(gateio_c_col, gateio_h_col)
        df['gateio_fut_ch'] = diff_perc(gateio_fut_c_col, gateio_fut_h_col)

        # Store column names for later use
        df.attrs['mexc_c_col'] = mexc_c_col
        df.attrs['gateio_c_col'] = gateio_c_col
        df.attrs['mexc_h_col'] = mexc_h_col
        df.attrs['mexc_l_col'] = mexc_l_col
        df.attrs['gateio_h_col'] = gateio_h_col
        df.attrs['gateio_l_col'] = gateio_l_col

        # Intrabar volatility (proxy for execution risk)
        df['mexc_range'] = (df[mexc_h_col] - df[mexc_l_col]) / df[mexc_c_col] * 100
        df['gateio_range'] = (df[gateio_h_col] - df[gateio_l_col]) / df[gateio_c_col] * 100

        # Rolling volatility ratio (find which venue is more reactive)
        window = 20
        df['mexc_vol'] = df['mexc_range'].rolling(window).std()
        df['gateio_vol'] = df['gateio_range'].rolling(window).std()
        df['vol_ratio'] = df['mexc_vol'] / df['gateio_vol']  # >1 means MEXC more volatile

        # Liquidity score (% of candles with 0 movement)
        df['mexc_static'] = ((df[mexc_h_col] == df[mexc_l_col]).rolling(window).mean() * 100)
        df['gateio_static'] = ((df[gateio_h_col] == df[gateio_l_col]).rolling(window).mean() * 100)

        # Rolling spread statistics
        df['spread_mean'] = df['mexc_vs_gateio_pct'].rolling(window).mean()
        df['spread_std'] = df['mexc_vs_gateio_pct'].rolling(window).std()
        df['spread_z_score'] = (df['mexc_vs_gateio_pct'] - df['spread_mean']) / df['spread_std']

        # Spread velocity (rate of change)
        df['spread_velocity'] = df['mexc_vs_gateio_pct'].diff()
        df['spread_acceleration'] = df['spread_velocity'].diff()

        # Maximum adverse excursion during execution window
        # Assume 2-3 second execution time = 1-3 candles at 1min
        execution_window = 3
        df['mexc_max_adverse'] = df['mexc_range'].rolling(execution_window).max()
        df['gateio_max_adverse'] = df['gateio_range'].rolling(execution_window).max()

        # Realized slippage proxy
        df['mexc_close_to_high'] = (df[mexc_h_col] - df[mexc_c_col]) / df[mexc_c_col] * 100
        df['mexc_close_to_low'] = (df[mexc_c_col] - df[mexc_l_col]) / df[mexc_c_col] * 100

        # Identify low-liquidity regimes (your spike hunting opportunity)
        df['low_liq_regime'] = (df['mexc_static'] > 50) | (df['gateio_static'] > 50)

        # Correlation breakdown (decorrelation = opportunity)
        df['rolling_corr'] = df[mexc_c_col].rolling(window).corr(df[gateio_c_col])
        df['decorrelation_event'] = df['rolling_corr'] < 0.8  # threshold to tune

        # Signal for spike capture strategy
        df['signal'] = (
            (df['spread_z_score'].abs() > 2.0) &  # Spread deviation
            (df['vol_ratio'] > 1.2) &  # MEXC more volatile
            (df['mexc_static'] > 40) &  # Low liquidity
            (df['spread_velocity'].abs() > 0.1)  # Momentum
        )

        # Triangular opportunity
        df['triangular_edge'] = (
                df['mexc_vs_gateio_pct'] +  # Buy MEXC, sell Gate.io spot
                df['gateio_vs_gateio_fut_pct']  # Futures hedge
        )

        # Mean reversion signal components
        entry_threshold = df['spread_mean'] + 1.5 * df['spread_std']
        exit_threshold = df['spread_mean']

        df['mean_rev_signal'] = (
                (df['mexc_vs_gateio_pct'] > entry_threshold) &
                (df['spread_velocity'] < 0)  # Spread expanding
        )

        # Run backtest
        backtest_results = self.backtest_mean_reversion(df)
        self.print_backtest_results(backtest_results)

        # Print basic statistics
        for e in ['mexc', 'gateio', 'gateio_fut']:
            for col in ['_ch', '_cl']:
                full_col = f'{e}{col}'
                print(f'{full_col} {df[full_col].describe()}')

        return df, backtest_results

    def backtest_mean_reversion(self, df: pd.DataFrame) -> dict:
        """
        Backtest mean reversion strategy with realistic execution

        Strategy:
        - Enter: When spread Z-score > threshold and spread contracting
        - Exit: When spread returns to mean or stop-loss hit
        - Execution: Simulate limit orders with realistic fill assumptions
        """

        # Strategy parameters
        entry_z_threshold = 1.5
        exit_z_threshold = 0.5
        stop_loss_pct = 0.5  # Stop if spread moves 0.5% against us

        # Exchange parameters
        mexc_fee = 0.10  # 0.10% taker fee
        gateio_fee = 0.15  # 0.15% taker fee
        futures_fee = 0.05  # 0.05% futures fee
        slippage_estimate = 0.05  # 0.05% slippage per leg

        total_entry_cost = mexc_fee + gateio_fee + futures_fee + 3 * slippage_estimate
        total_exit_cost = total_entry_cost

        # Get column names from DataFrame attributes
        mexc_c_col = df.attrs.get('mexc_c_col', 'mexc_close')
        gateio_c_col = df.attrs.get('gateio_c_col', 'gateio_close')

        # Position tracking
        position = None  # {entry_idx, entry_spread, entry_price_mexc, entry_price_gateio, entry_time}
        trades = []

        for idx in range(len(df)):
            if idx < 20:  # Skip until indicators are ready
                continue

            row = df.iloc[idx]

            # Skip if any critical data is missing
            if pd.isna(row['spread_z_score']) or pd.isna(row['spread_mean']):
                continue

            current_spread = row['mexc_vs_gateio_pct']
            z_score = row['spread_z_score']
            spread_velocity = row['spread_velocity']

            # ENTRY LOGIC
            if position is None:
                # Enter when spread is wide and starting to contract
                entry_signal = (
                    abs(z_score) > entry_z_threshold and
                    spread_velocity < 0 and  # Spread contracting (converging)
                    row['rolling_corr'] > 0.7  # Venues still correlated
                )

                if entry_signal:
                    position = {
                        'entry_idx': idx,
                        'entry_time': row.name if hasattr(row, 'name') else idx,
                        'entry_spread': current_spread,
                        'entry_z_score': z_score,
                        'entry_price_mexc': row[mexc_c_col],
                        'entry_price_gateio': row[gateio_c_col],
                        'direction': 'long' if current_spread > 0 else 'short',  # Long MEXC if it's expensive
                    }

            # EXIT LOGIC
            else:
                hold_time = idx - position['entry_idx']
                spread_change = current_spread - position['entry_spread']

                # Profit target: spread returned to mean
                profit_target = abs(z_score) < exit_z_threshold

                # Stop loss: spread moved against us
                stop_loss = abs(spread_change) > stop_loss_pct

                # Time stop: held too long (120 minutes = 2 hours)
                time_stop = hold_time > 120

                # Correlation breakdown: venues decorrelated
                correlation_stop = row['rolling_corr'] < 0.6

                exit_signal = profit_target or stop_loss or time_stop or correlation_stop

                if exit_signal:
                    # Calculate P&L
                    # If we longed MEXC (expecting it to fall relative to gateio):
                    # PnL = entry_spread - exit_spread - costs
                    raw_pnl = position['entry_spread'] - current_spread

                    # Adjust for direction
                    if position['direction'] == 'short':
                        raw_pnl = -raw_pnl

                    net_pnl = raw_pnl - total_entry_cost - total_exit_cost

                    # Record trade
                    trade = {
                        'entry_idx': position['entry_idx'],
                        'exit_idx': idx,
                        'entry_time': position['entry_time'],
                        'exit_time': row.name if hasattr(row, 'name') else idx,
                        'hold_time': hold_time,
                        'entry_spread': position['entry_spread'],
                        'exit_spread': current_spread,
                        'entry_z_score': position['entry_z_score'],
                        'exit_z_score': z_score,
                        'raw_pnl_pct': raw_pnl,
                        'net_pnl_pct': net_pnl,
                        'exit_reason': (
                            'profit_target' if profit_target else
                            'stop_loss' if stop_loss else
                            'time_stop' if time_stop else
                            'correlation_stop'
                        ),
                        'direction': position['direction'],
                    }
                    trades.append(trade)
                    position = None

        # Calculate performance metrics
        if not trades:
            return {
                'total_trades': 0,
                'message': 'No trades generated'
            }

        trades_df = pd.DataFrame(trades)

        winning_trades = trades_df[trades_df['net_pnl_pct'] > 0]
        losing_trades = trades_df[trades_df['net_pnl_pct'] <= 0]

        total_pnl = trades_df['net_pnl_pct'].sum()
        avg_pnl = trades_df['net_pnl_pct'].mean()
        median_pnl = trades_df['net_pnl_pct'].median()

        win_rate = len(winning_trades) / len(trades_df) * 100 if len(trades_df) > 0 else 0

        avg_win = winning_trades['net_pnl_pct'].mean() if len(winning_trades) > 0 else 0
        avg_loss = losing_trades['net_pnl_pct'].mean() if len(losing_trades) > 0 else 0

        profit_factor = (
            abs(winning_trades['net_pnl_pct'].sum() / losing_trades['net_pnl_pct'].sum())
            if len(losing_trades) > 0 and losing_trades['net_pnl_pct'].sum() != 0
            else float('inf') if len(winning_trades) > 0 else 0
        )

        avg_hold_time = trades_df['hold_time'].mean()

        # Sharpe-like ratio (return / volatility)
        returns_std = trades_df['net_pnl_pct'].std()
        sharpe_ratio = avg_pnl / returns_std if returns_std > 0 else 0

        # Max drawdown
        cumulative_pnl = trades_df['net_pnl_pct'].cumsum()
        running_max = cumulative_pnl.expanding().max()
        drawdown = cumulative_pnl - running_max
        max_drawdown = drawdown.min()

        return {
            'total_trades': len(trades_df),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'total_pnl_pct': total_pnl,
            'avg_pnl_pct': avg_pnl,
            'median_pnl_pct': median_pnl,
            'avg_win_pct': avg_win,
            'avg_loss_pct': avg_loss,
            'profit_factor': profit_factor,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown_pct': max_drawdown,
            'avg_hold_time_minutes': avg_hold_time,
            'trades_df': trades_df,
            'entry_costs_pct': total_entry_cost,
            'exit_costs_pct': total_exit_cost,
        }

    def print_backtest_results(self, results: dict):
        """Pretty print backtest results"""
        if results['total_trades'] == 0:
            self.logger.warning("⚠️ No trades generated in backtest")
            return

        self.logger.info("=" * 80)
        self.logger.info("📊 BACKTEST RESULTS - Mean Reversion Strategy")
        self.logger.info("=" * 80)

        self.logger.info(f"\n📈 TRADE STATISTICS:")
        self.logger.info(f"  Total Trades:        {results['total_trades']}")
        self.logger.info(f"  Winning Trades:      {results['winning_trades']} ({results['win_rate']:.1f}%)")
        self.logger.info(f"  Losing Trades:       {results['losing_trades']}")

        self.logger.info(f"\n💰 P&L METRICS:")
        self.logger.info(f"  Total P&L:           {results['total_pnl_pct']:.3f}%")
        self.logger.info(f"  Average P&L:         {results['avg_pnl_pct']:.3f}%")
        self.logger.info(f"  Median P&L:          {results['median_pnl_pct']:.3f}%")
        self.logger.info(f"  Average Win:         {results['avg_win_pct']:.3f}%")
        self.logger.info(f"  Average Loss:        {results['avg_loss_pct']:.3f}%")

        self.logger.info(f"\n📊 RISK METRICS:")
        self.logger.info(f"  Profit Factor:       {results['profit_factor']:.2f}")
        self.logger.info(f"  Sharpe Ratio:        {results['sharpe_ratio']:.2f}")
        self.logger.info(f"  Max Drawdown:        {results['max_drawdown_pct']:.3f}%")

        self.logger.info(f"\n⏱️  EXECUTION:")
        self.logger.info(f"  Avg Hold Time:       {results['avg_hold_time_minutes']:.1f} minutes")
        self.logger.info(f"  Entry Costs:         {results['entry_costs_pct']:.2f}%")
        self.logger.info(f"  Exit Costs:          {results['exit_costs_pct']:.2f}%")
        self.logger.info(f"  Total Round Trip:    {results['entry_costs_pct'] + results['exit_costs_pct']:.2f}%")

        # Exit reason breakdown
        if 'trades_df' in results:
            self.logger.info(f"\n🚪 EXIT REASONS:")
            exit_reasons = results['trades_df']['exit_reason'].value_counts()
            for reason, count in exit_reasons.items():
                pct = count / results['total_trades'] * 100
                self.logger.info(f"  {reason:20s} {count:3d} ({pct:5.1f}%)")

        self.logger.info("=" * 80)


async def main():
    """Main execution"""

    # Initialize loader
    analyzer = SpotSpotArbitrageAnalyzer()
    symbol = Symbol(base=AssetName("QUBIC"), quote=AssetName("USDT"))

    try:
        await analyzer.analyze_symbol(symbol, 8)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
