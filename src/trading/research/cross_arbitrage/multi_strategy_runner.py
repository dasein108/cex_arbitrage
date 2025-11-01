"""
Comprehensive Multi-Strategy Analysis Runner

Runs multiple backtesting strategies and generates comparative analysis
"""

import asyncio
import pandas as pd
from datetime import datetime, UTC, timedelta

from config import HftConfig
from exchanges.structs import Symbol
from exchanges.structs.common import AssetName
from exchanges.structs.enums import ExchangeEnum, KlineInterval
from infrastructure.logging import get_logger
from trading.research.cross_arbitrage.multi_candles_source import MultiCandlesSource

# Local imports
from advanced_backtester import AdvancedBacktester

pd.set_option('display.precision', 12)
pd.set_option('display.float_format', None)


class MultiStrategyAnalyzer:
    """Comprehensive multi-strategy backtesting and analysis"""
    
    def __init__(self):
        self.config = HftConfig()
        self.logger = get_logger("MultiStrategyAnalyzer")
        self.candles_source = MultiCandlesSource()
        self.backtester = AdvancedBacktester(
            mexc_fee=0.10,
            gateio_fee=0.15,
            futures_fee=0.05,
            slippage_estimate=0.05
        )
        
        self.exchanges = [
            ExchangeEnum.MEXC,
            ExchangeEnum.GATEIO,
            ExchangeEnum.GATEIO_FUTURES
        ]
    
    async def load_and_prepare_data(self, symbol: Symbol, hours: int = 24) -> pd.DataFrame:
        """Load candle data and calculate all indicators"""
        
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(hours=hours)
        
        self.logger.info(f"📊 Loading {hours}h of data for {symbol}")
        
        df = await self.candles_source.get_multi_candles_df(
            exchanges=self.exchanges,
            symbol=symbol,
            date_to=end_time,
            hours=hours,
            timeframe=KlineInterval.MINUTE_1
        )
        
        if df.empty:
            self.logger.warning(f"⚠️ No data available")
            return df
        
        # Prepare all indicators
        df = self._calculate_indicators(df)
        
        self.logger.info(f"✅ Loaded {len(df)} candles")
        return df
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical indicators needed for strategies"""
        
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
        
        # Store column names in DataFrame attributes
        df.attrs['mexc_c_col'] = mexc_c_col
        df.attrs['gateio_c_col'] = gateio_c_col
        df.attrs['mexc_h_col'] = mexc_h_col
        df.attrs['mexc_l_col'] = mexc_l_col
        df.attrs['gateio_h_col'] = gateio_h_col
        df.attrs['gateio_l_col'] = gateio_l_col
        
        def diff_perc(col1, col2):
            denom = df[col2]
            num = df[col1] - denom
            pct = num.div(denom).mul(100)
            pct = pct.where(denom != 0, 0).fillna(0)
            return pct
        
        # Basic spreads
        df['mexc_vs_gateio_pct'] = diff_perc(mexc_c_col, gateio_c_col)
        df['mexc_vs_gateio_fut_pct'] = diff_perc(mexc_c_col, gateio_fut_c_col)
        df['gateio_vs_gateio_fut_pct'] = diff_perc(gateio_c_col, gateio_fut_c_col)
        
        # Intrabar metrics
        df['mexc_range'] = (df[mexc_h_col] - df[mexc_l_col]) / df[mexc_c_col] * 100
        df['gateio_range'] = (df[gateio_h_col] - df[gateio_l_col]) / df[gateio_c_col] * 100
        
        # Rolling indicators
        window = 20
        df['mexc_vol'] = df['mexc_range'].rolling(window).std()
        df['gateio_vol'] = df['gateio_range'].rolling(window).std()
        df['vol_ratio'] = df['mexc_vol'] / df['gateio_vol']
        
        # Liquidity indicators
        df['mexc_static'] = ((df[mexc_h_col] == df[mexc_l_col]).rolling(window).mean() * 100)
        df['gateio_static'] = ((df[gateio_h_col] == df[gateio_l_col]).rolling(window).mean() * 100)
        
        # Spread statistics
        df['spread_mean'] = df['mexc_vs_gateio_pct'].rolling(window).mean()
        df['spread_std'] = df['mexc_vs_gateio_pct'].rolling(window).std()
        df['spread_z_score'] = (df['mexc_vs_gateio_pct'] - df['spread_mean']) / df['spread_std']
        
        # Spread dynamics
        df['spread_velocity'] = df['mexc_vs_gateio_pct'].diff()
        df['spread_acceleration'] = df['spread_velocity'].diff()
        
        # Execution risk
        execution_window = 3
        df['mexc_max_adverse'] = df['mexc_range'].rolling(execution_window).max()
        df['gateio_max_adverse'] = df['gateio_range'].rolling(execution_window).max()
        
        # Correlation
        df['rolling_corr'] = df[mexc_c_col].rolling(window).corr(df[gateio_c_col])
        
        # Triangular edge
        df['triangular_edge'] = (
            df['mexc_vs_gateio_pct'] + 
            df['gateio_vs_gateio_fut_pct']
        )
        
        return df
    
    async def run_all_strategies(self, symbol: Symbol, hours: int = 24):
        """Run all strategies and compare results"""
        
        df = await self.load_and_prepare_data(symbol, hours)
        
        if df.empty:
            return
        
        self.logger.info("\n" + "=" * 80)
        self.logger.info("🚀 Running Multiple Strategies")
        self.logger.info("=" * 80)
        
        results = []
        
        # Strategy 1: Spike Capture
        self.logger.info("\n📍 Strategy 1: Spike Capture")
        spike_results = self.backtester.backtest_spike_capture(df)
        results.append(spike_results)
        self._print_single_result(spike_results)
        
        # Strategy 2: Triangular Arbitrage
        self.logger.info("\n📍 Strategy 2: Triangular Arbitrage")
        triangular_results = self.backtester.backtest_triangular_arbitrage(df)
        results.append(triangular_results)
        self._print_single_result(triangular_results)
        
        # Strategy 3: Adaptive Threshold
        self.logger.info("\n📍 Strategy 3: Adaptive Threshold")
        adaptive_results = self.backtester.backtest_adaptive_threshold(df)
        results.append(adaptive_results)
        self._print_single_result(adaptive_results)
        
        # Print comparison
        AdvancedBacktester.print_comparison(results)
        
        # Generate detailed analysis
        self._generate_detailed_analysis(df, results)
        
        return df, results
    
    def _print_single_result(self, result: dict):
        """Print single strategy results"""
        
        if result['total_trades'] == 0:
            self.logger.warning(f"  ⚠️ {result.get('message', 'No trades generated')}")
            return
        
        self.logger.info(f"  Trades: {result['total_trades']} | "
                        f"Win Rate: {result['win_rate']:.1f}% | "
                        f"Total P&L: {result['total_pnl_pct']:.3f}% | "
                        f"Sharpe: {result['sharpe_ratio']:.2f}")
    
    def _generate_detailed_analysis(self, df: pd.DataFrame, results: list):
        """Generate detailed market analysis"""
        
        self.logger.info("\n" + "=" * 80)
        self.logger.info("📈 MARKET ANALYSIS")
        self.logger.info("=" * 80)
        
        # Spread statistics
        spread_stats = df['mexc_vs_gateio_pct'].describe()
        self.logger.info(f"\n💱 Spread Statistics (MEXC vs Gate.io):")
        self.logger.info(f"  Mean:           {spread_stats['mean']:.4f}%")
        self.logger.info(f"  Std Dev:        {spread_stats['std']:.4f}%")
        self.logger.info(f"  Min:            {spread_stats['min']:.4f}%")
        self.logger.info(f"  Max:            {spread_stats['max']:.4f}%")
        self.logger.info(f"  Median:         {spread_stats['50%']:.4f}%")
        
        # Volatility comparison
        mexc_avg_vol = df['mexc_range'].mean()
        gateio_avg_vol = df['gateio_range'].mean()
        self.logger.info(f"\n📊 Volatility Comparison:")
        self.logger.info(f"  MEXC avg range:     {mexc_avg_vol:.4f}%")
        self.logger.info(f"  Gate.io avg range:  {gateio_avg_vol:.4f}%")
        self.logger.info(f"  Ratio:              {mexc_avg_vol/gateio_avg_vol:.2f}x")
        
        # Liquidity analysis
        mexc_static_pct = ((df[df.attrs['mexc_h_col']] == df[df.attrs['mexc_l_col']]).sum() / len(df) * 100)
        gateio_static_pct = ((df[df.attrs['gateio_h_col']] == df[df.attrs['gateio_l_col']]).sum() / len(df) * 100)
        self.logger.info(f"\n💧 Liquidity Analysis:")
        self.logger.info(f"  MEXC static candles:    {mexc_static_pct:.1f}%")
        self.logger.info(f"  Gate.io static candles: {gateio_static_pct:.1f}%")
        
        # Correlation
        correlation = df[df.attrs['mexc_c_col']].corr(df[df.attrs['gateio_c_col']])
        self.logger.info(f"\n🔗 Price Correlation:")
        self.logger.info(f"  MEXC vs Gate.io:    {correlation:.4f}")
        
        # Triangular edge analysis
        tri_edge_stats = df['triangular_edge'].describe()
        self.logger.info(f"\n🔺 Triangular Edge Statistics:")
        self.logger.info(f"  Mean:           {tri_edge_stats['mean']:.4f}%")
        self.logger.info(f"  Std Dev:        {tri_edge_stats['std']:.4f}%")
        self.logger.info(f"  Max:            {tri_edge_stats['max']:.4f}%")
        
        # Opportunity frequency
        high_z_score_pct = ((df['spread_z_score'].abs() > 2.0).sum() / len(df) * 100)
        self.logger.info(f"\n🎯 Opportunity Frequency:")
        self.logger.info(f"  |Z-score| > 2.0:      {high_z_score_pct:.1f}% of time")
        
        self.logger.info("=" * 80)


async def main():
    """Main execution"""
    
    analyzer = MultiStrategyAnalyzer()
    
    # Test symbol
    symbol = Symbol(base=AssetName("QUBIC"), quote=AssetName("USDT"))
    
    try:
        df, results = await analyzer.run_all_strategies(symbol, hours=8)
        
        # Optionally save results to CSV
        if results and results[0]['total_trades'] > 0:
            print("\n💾 Saving detailed trade logs...")
            for result in results:
                if result['total_trades'] > 0 and 'trades_df' in result:
                    filename = f"trades_{result['strategy'].replace(' ', '_').lower()}.csv"
                    result['trades_df'].to_csv(filename, index=False)
                    print(f"  ✓ {filename}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
