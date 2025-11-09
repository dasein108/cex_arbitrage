from config import HftConfig
from exchanges.exchange_factory import get_rest_implementation
from exchanges.structs import SymbolInfo, Symbol
from exchanges.structs.enums import ExchangeEnum, KlineInterval
from typing import List, Optional, Dict
import asyncio
from datetime import datetime, UTC
import pandas as pd
import numpy as np
import json
from pathlib import Path
from dataclasses import dataclass
from infrastructure.logging import get_logger
from trading.data_sources.book_ticker.book_ticker_source import CandlesBookTickerSource
from trading.research.cross_arbitrage.hedged_cross_arbitrage_backtest import HedgedCrossArbitrageBacktest, BacktestConfig
from trading.research.cross_arbitrage.arbitrage_analyzer import AnalyzerKeys
from trading.signals_v2.entities import PerformanceMetrics
from trading.signals.backtesting.vectorized_strategy_backtester import StrategyBacktester, VectorizedStrategyBacktester
ANALYZER_TF = KlineInterval.MINUTE_5


@dataclass
class CandidateMetrics:
    """Quick screening metrics for a symbol."""
    symbol: Symbol
    avg_spread: float
    max_spread: float
    spread_std: float
    positive_spread_pct: float  # % of periods with positive spread
    opportunity_count: int
    score: float
    data_points: int


class InventorySpotArbitrageCandidateAnalyzer:
    """Enhanced arbitrage candidate analyzer with multi-stage pipeline."""
    
    def __init__(self, exchanges: Optional[List[ExchangeEnum]] = None, output_dir: str = "results"):
        self.exchanges = exchanges or [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]
        self.config = HftConfig()
        self.logger = get_logger("InventorySpotArbitrageCandidateAnalyzer")
        # self.candle_loader = CandlesLoader(logger=self.logger)
        
        # Output configuration
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Results storage
        self.screening_results: List[CandidateMetrics] = []
        self.backtest_results: List[PerformanceMetrics] = []

        self.clients = {exchange: self._get_exchange_client(exchange) for exchange in self.exchanges}
        self.symbol_df_cache: Dict[Symbol, pd.DataFrame] = {}
        self.source = CandlesBookTickerSource()


    def _get_exchange_client(self, exchange: ExchangeEnum):
        return get_rest_implementation(self.config.get_exchange_config(exchange.value), False)

    async def get_common_symbols(self, exchanges_count: int = 3):
        si_result = await asyncio.gather(*[c.get_symbols_info() for c in self.clients.values()])
        inactive = set()
        symbols_info: Dict[ExchangeEnum, SymbolInfo] = {}
        symbol_exchanges: Dict[Symbol, List[ExchangeEnum]] = {}
        for exchange, symbols in zip(self.clients.keys(), si_result):
            symbols_info[exchange] = symbols
            for symbol in symbols.keys():
                if  symbols[symbol].inactive or symbol in inactive:
                    inactive.add(symbol)
                    continue

                if symbol not in symbol_exchanges:
                    symbol_exchanges[symbol] = []

                symbol_exchanges[symbol].append(exchange)


        common_symbols = {symbol: exchanges for symbol, exchanges in symbol_exchanges.items() if len(exchanges) >= exchanges_count}
        return common_symbols, symbols_info


    def calculate_quick_metrics(self, df: pd.DataFrame, symbol: Symbol) -> Optional[CandidateMetrics]:
        """Calculate quick screening metrics for a symbol."""
        try:
            if df.empty or len(df) < 10:
                return None
            
            # Calculate spreads between exchanges
            spreads = []
            
            # MEXC vs GATEIO_FUTURES arbitrage (primary strategy)
            mexc_bid_col = AnalyzerKeys.mexc_bid
            mexc_ask_col = AnalyzerKeys.mexc_ask
            gateio_fut_bid_col = AnalyzerKeys.gateio_futures_bid
            gateio_fut_ask_col = AnalyzerKeys.gateio_futures_ask
            
            if all([mexc_bid_col, mexc_ask_col, gateio_fut_bid_col, gateio_fut_ask_col]):
                # Use execution prices: Buy MEXC (at ask), Sell Gate.io futures (at bid)
                # Spread = (selling_price - buying_price) / selling_price * 100
                spread = ((df[gateio_fut_bid_col] - df[mexc_ask_col]) / df[gateio_fut_bid_col] * 100).dropna()
                spreads.extend(spread.tolist())
            
            # GATEIO spot vs GATEIO_FUTURES arbitrage (hedging leg)
            gateio_spot_bid_col = AnalyzerKeys.gateio_spot_bid
            gateio_spot_ask_col = AnalyzerKeys.gateio_spot_ask
            
            if all([gateio_spot_bid_col, gateio_spot_ask_col, gateio_fut_bid_col, gateio_fut_ask_col]):
                # Use execution prices: Buy Gate.io spot (at ask), Sell Gate.io futures (at bid)
                # Spread = (selling_price - buying_price) / selling_price * 100  
                spread = ((df[gateio_fut_bid_col] - df[gateio_spot_ask_col]) / df[gateio_fut_bid_col] * 100).dropna()
                spreads.extend(spread.tolist())
            
            if not spreads:
                return None
                
            spreads = np.array(spreads)
            
            # Calculate metrics
            avg_spread = float(np.mean(spreads))
            max_spread = float(np.max(spreads))
            spread_std = float(np.std(spreads))
            positive_spread_pct = float(np.mean(spreads > 0.2) * 100)  # >0.2% spread threshold
            opportunity_count = int(np.sum(spreads > 0.2))
            
            # Calculate composite score
            score = avg_spread * positive_spread_pct * (1 + min(spread_std, 0.5))  # Favor volatility but cap it
            
            return CandidateMetrics(
                symbol=symbol,
                avg_spread=avg_spread,
                max_spread=max_spread,
                spread_std=spread_std,
                positive_spread_pct=positive_spread_pct,
                opportunity_count=opportunity_count,
                score=score,
                data_points=len(df)
            )
            
        except Exception as e:
            self.logger.error(f"Error calculating metrics for {symbol}: {e}")
            return None
    
    async def quick_screening(self, symbol: Symbol, date_to: Optional[datetime]=None,
                              hours: int = 24) -> Optional[CandidateMetrics]:
        """Stage 1: Quick screening using optimized data source."""
        try:
            # Get best available data source

            # Use 5-minute intervals for quick screening
            df = await self.source.get_multi_exchange_data(
                exchanges=self.exchanges,
                symbol=symbol,
                date_to=date_to,
                hours=hours,
                timeframe=KlineInterval.MINUTE_1
            )
            
            if df.empty:
                return None

            self.symbol_df_cache[symbol] = df

            return self.calculate_quick_metrics(df, symbol)
            
        except Exception as e:
            self.logger.warning(f"Failed quick screening for {symbol}: {e}")
            return None
    
    async def pick_candidates(self, date_to: datetime, hours: int = 24) -> List[CandidateMetrics]:
        """Stage 1: Screen all common symbols and identify candidates."""
        self.logger.info("🔍 Stage 1: Picking candidates...")
        
        # Get all common symbols
        common_symbols, _ = await self.get_common_symbols(exchanges_count=len(self.exchanges))
        self.logger.info(f"Found {len(common_symbols)} common symbols across {len(self.exchanges)} exchanges")
        
        # # Limit to manageable number for testing
        # symbols_to_test = list(common_symbols.keys())[:50]  # Limit to first 50 symbols
        # self.logger.info(f"Testing {len(symbols_to_test)} symbols")
        #
        # Process symbols with concurrency limit
        semaphore = asyncio.Semaphore(5)  # Limit concurrent processing
        
        async def process_symbol(symbol):
            async with semaphore:
                return await self.quick_screening(symbol, date_to, hours)
        
        # Process all symbols in parallel
        tasks = [process_symbol(symbol) for symbol in common_symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter valid results
        valid_results = []
        for result in results:
            if isinstance(result, CandidateMetrics) and result is not None:
                valid_results.append(result)
        
        # Filter by minimum criteria
        filtered_results = [
            result for result in valid_results
            if (result.avg_spread > 0.1 and  # Minimum 0.1% average spread
                result.opportunity_count > 2 and  # At least 5 opportunities
                result.data_points > 50)  # Sufficient data points
        ]
        
        # Sort by score
        filtered_results.sort(key=lambda x: x.score, reverse=True)
        
        self.logger.info(f"✅ Found {len(filtered_results)} promising candidates")
        self.screening_results = filtered_results
        
        return filtered_results
    
    async def backtest_candidate(self, candidate: CandidateMetrics, days: int = 7) -> Optional[PerformanceMetrics]:
        """Run full backtest on a single candidate."""
        try:
            # Configure backtest
            config = BacktestConfig(
                symbol=candidate.symbol,
                days=days,
                min_transfer_time_minutes=10,
                position_size_usd=1000,
                max_concurrent_positions=2
            )
            
            # Run backtest
            backtester = HedgedCrossArbitrageBacktest(config)
            cached_data = self.symbol_df_cache.get(candidate.symbol, None)
            results = await backtester.run_backtest(df_data=cached_data)
            
            # Extract performance metrics
            perf = results['performance']
            
            return PerformanceMetrics(
                symbol=str(candidate.symbol),
                screening_score=candidate.score,
                backtest_pnl=perf.total_pnl,
                total_trades=perf.total_trades,
                win_rate=perf.win_rate,
                sharpe_ratio=perf.sharpe_ratio,
                max_drawdown=perf.max_drawdown,
                avg_holding_minutes=perf.avg_holding_period_minutes,
                profit_factor=perf.profit_factor
            )
            
        except Exception as e:
            self.logger.error(f"Backtest failed for {candidate.symbol}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def backtest_candidates(self, candidates: List[CandidateMetrics], max_backtests: int = 10) -> List[PerformanceMetrics]:
        """Stage 2: Run backtests on top candidates."""
        self.logger.info(f"🧪 Stage 2: Backtesting top {min(len(candidates), max_backtests)} candidates...")
        
        # Take only top candidates
        top_candidates = candidates # candidates[:max_backtests]
        
        # Process candidates sequentially to avoid overwhelming the system
        results = []
        for i, candidate in enumerate(top_candidates):
            self.logger.info(f"Backtesting {i+1}/{len(top_candidates)}: {candidate.symbol} (score: {candidate.score:.2f})")
            
            result = await self.backtest_candidate(candidate)
            if result:
                results.append(result)
                self.logger.info(f"  Result: PnL=${result.backtest_pnl:.2f}, Trades={result.total_trades}, Win Rate={result.win_rate:.1f}%")
        
        # Sort by PnL
        results.sort(key=lambda x: x.backtest_pnl, reverse=True)
        
        self.logger.info(f"✅ Completed {len(results)} backtests")
        self.backtest_results = results
        
        return results
    
    async def save_results(self, backtest_results: List[PerformanceMetrics]):
        """Stage 3: Save results to JSON file."""
        self.logger.info("💾 Stage 3: Saving results...")

        # TODO: save results to database
        output = {}
        
        # Save to file
        output_file = self.output_dir / 'arbitrage_candidates.json'
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2, default=str)
        
        self.logger.info(f"✅ Results saved to {output_file}")
        
        # Also save detailed screening results
        screening_file = self.output_dir / 'screening_results.json'
        screening_data = {
        }
        
        with open(screening_file, 'w') as f:
            json.dump(screening_data, f, indent=2, default=str)
        
        self.logger.info(f"📊 Screening results saved to {screening_file}")

    
    async def analyze(self, date_to: datetime, hours: int, max_backtests: int = 10):
        """Complete 3-stage analysis pipeline."""
        try:
            # Initialize database connection
            # await get_database_manager()
            
            # hours = int((date_to - date_from).total_seconds() / 3600)
            # Stage 1: Pick candidates
            candidates = await self.pick_candidates(date_to, hours)
            
            if not candidates:
                self.logger.warning("No candidates found during screening")
                return
            
            # Stage 2: Backtest top candidates
            backtest_results = await self.backtest_candidates(candidates, max_backtests)
            
            # Stage 3: Save results
            await self.save_results(backtest_results)
            
            # Print summary
            self.print_summary(backtest_results)
            
        except Exception as e:
            self.logger.error(f"Analysis failed: {e}")
            raise
    
    def print_summary(self, results: List[PerformanceMetrics]):
        """Print analysis summary to console."""
        print("\n" + "="*80)
        print("🎯 ARBITRAGE CANDIDATE ANALYSIS SUMMARY")
        print("="*80)
        
        if not results:
            print("❌ No profitable candidates found")
            return
        
        print(f"📊 Total Candidates Analyzed: {len(self.screening_results)}")
        print(f"🧪 Backtests Performed: {len(results)}")
        #TODO: add more summary stats


if __name__ == "__main__":
    async def main():
        """Example usage of the enhanced analyzer."""
        analyzer = InventorySpotArbitrageCandidateAnalyzer(
            exchanges=[ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES],
            output_dir="../arbitrage_results"
        )
        
        # end_time = datetime.now(UTC)
        hours = 24

        end_time = datetime.fromisoformat("2025-10-30 03:00:00+00:00")
        start_time = end_time - pd.Timedelta(hours=hours)

        print("🚀 Starting Arbitrage Candidate Analysis")
        print(f"📅 Analysis Period: {start_time} to {end_time}")
        print(f"🏢 Exchanges: {[e.value for e in analyzer.exchanges]}")
        
        await analyzer.analyze(end_time, hours, max_backtests=10)
        
        print("\n✅ Analysis completed successfully!")
    
    asyncio.run(main())

