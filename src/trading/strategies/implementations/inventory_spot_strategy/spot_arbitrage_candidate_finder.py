"""
Spot Arbitrage Candidate Finder - Phase 1 Implementation

Systematic pipeline to discover and rank optimal spot-spot arbitrage opportunities
between MEXC and Gate.io exchanges.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta, UTC
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from pathlib import Path
import json

from config.config_manager import HftConfig
from exchanges.dual_exchange import DualExchange
from exchanges.exchange_factory import get_rest_implementation, get_composite_implementation
from exchanges.structs import Symbol, AssetName, BookTicker
from exchanges.structs.common import AssetInfo
from exchanges.structs.enums import ExchangeEnum, KlineInterval
from infrastructure.logging import get_logger
from trading.data_sources.book_ticker.book_ticker_source import BookTickerDbSource, CandlesBookTickerSource
from trading.data_sources.column_utils import get_column_key
from trading.signals.backtesting.vectorized_strategy_backtester import VectorizedStrategyBacktester


@dataclass
class ExchangePairMetrics:
    """Metrics for a trading pair across exchanges."""
    symbol: Symbol
    mexc_available: bool
    gateio_available: bool
    mexc_min_notional: float
    gateio_min_notional: float
    price_correlation: float


@dataclass
class ArbitrageOpportunityScore:
    """Multi-factor scoring for arbitrage opportunities."""

    # Profitability Factors
    avg_spread_bps: float                    # Average arbitrage spread
    opportunity_frequency: float             # Opportunities per hour
    # volume_weighted_spread: float            # Size-adjusted profitability
    
    # Risk Factors  
    price_correlation: float                 # Cross-exchange price correlation
    volatility_ratio: float                  # Relative price volatility
    liquidity_depth_score: float            # Market depth availability
    
    # Volume and Volatility Metrics
    avg_volume_per_min: float               # Average trading volume per minute
    price_volatility_bps: float             # Price volatility in basis points
    
    # Execution Factors
    avg_execution_time_ms: float             # Expected execution latency
    slippage_impact_bps: float              # Expected slippage cost
    transfer_viability_score: float         # Transfer feasibility (future)
    
    # Composite Score
    final_score: float                       # Weighted composite ranking
    
    def calculate_composite_score(self) -> float:
        """Calculate risk-adjusted opportunity score."""
        profitability = (self.avg_spread_bps * self.opportunity_frequency) # * self.volume_weighted_spread
        
        risk_adjustment = (self.price_correlation * 
                          (1 - min(self.volatility_ratio, 0.8)) *  # Cap volatility penalty
                          self.liquidity_depth_score)
        
        execution_efficiency = (1 / (1 + self.avg_execution_time_ms/1000) * 
                               (1 - self.slippage_impact_bps/10000))
        
        return profitability * risk_adjustment * execution_efficiency


@dataclass
class CandidateMetrics:
    """Comprehensive metrics for arbitrage candidates."""
    symbol: Symbol
    opportunity_score: ArbitrageOpportunityScore
    backtest_results: Optional[dict] = None
    data_points: int = 0
    analysis_period_hours: int = 24
    last_updated: datetime = None


class SpotArbitrageCandidateFinder:
    """Enhanced candidate discovery system for spot-spot arbitrage."""
    
    def __init__(self, output_dir: str = "arbitrage_results"):
        self.config = HftConfig()
        self.logger = get_logger("SpotArbitrageCandidateFinder")
        
        # Output configuration
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Exchange clients
        self.mexc_client = self._get_exchange_client(ExchangeEnum.MEXC)
        self.gateio_client = self._get_exchange_client(ExchangeEnum.GATEIO)
        self.gateio_fut_client = self._get_exchange_client(ExchangeEnum.GATEIO_FUTURES)
        self.asset_info: Dict[ExchangeEnum, Dict[AssetName, AssetInfo]] = {}
        # Data source
        self.data_source = CandlesBookTickerSource()
        
        # Results storage
        self.candidate_metrics: List[CandidateMetrics] = []
        self.exchange_pair_metrics: Dict[Symbol, ExchangePairMetrics] = {}
        
        # Performance tracking
        self.discovery_stats = {
            'total_symbols_analyzed': 0,
            'viable_candidates_found': 0,
            'analysis_start_time': None,
            'analysis_duration_seconds': 0
        }
    
    def _get_exchange_client(self, exchange: ExchangeEnum):
        """Get REST client for exchange."""
        exchange_config = self.config.get_exchange_config(exchange.value)
        return DualExchange.get_instance(exchange_config)
    
    async def discover_common_symbols(self) -> Dict[Symbol, ExchangePairMetrics]:
        """Find all symbols tradeable on both MEXC and Gate.io spot."""
        self.logger.info("🔍 Discovering common symbols across MEXC and Gate.io...")
        
        # Get symbols from both exchanges
        mexc_symbols_info = await self.mexc_client.public.rest_client.get_symbols_info()
        gateio_symbols_info = await self.gateio_client.public.rest_client.get_symbols_info()
        gateio_fut_symbols_info = await self.gateio_fut_client.public.rest_client.get_symbols_info()

        self.asset_info[ExchangeEnum.MEXC] = await self.mexc_client.private.rest_client.get_assets_info()
        self.asset_info[ExchangeEnum.GATEIO] = await self.gateio_client.private.rest_client.get_assets_info()

        self.logger.info(f"MEXC symbols: {len(mexc_symbols_info)}")
        self.logger.info(f"Gate.io symbols: {len(gateio_symbols_info)}")
        
        common_symbols = {}
        
        for symbol in mexc_symbols_info.keys():
            if symbol in gateio_symbols_info:
                mexc_info = mexc_symbols_info[symbol]
                gateio_info = gateio_symbols_info[symbol]
                gateio_fut_info = gateio_fut_symbols_info.get(symbol, None)

                # Skip inactive symbols
                if mexc_info.inactive or gateio_info.inactive or not gateio_fut_info or gateio_fut_info.inactive:
                    continue
                
                # Create metrics object
                metrics = ExchangePairMetrics(
                    symbol=symbol,
                    mexc_available=True,
                    gateio_available=True,
                    mexc_min_notional=mexc_info.min_base_quantity or 10.0,
                    gateio_min_notional=gateio_info.min_base_quantity or 10.0,
                    price_correlation=0.0  # Will be calculated later
                )
                
                common_symbols[symbol] = metrics
        
        self.logger.info(f"✅ Found {len(common_symbols)} common symbols")
        self.exchange_pair_metrics = common_symbols
        return common_symbols
    
    async def calculate_historical_metrics(self, symbol: Symbol, days: int = 7) -> Optional[ArbitrageOpportunityScore]:
        """Calculate comprehensive arbitrage metrics for a symbol."""
        try:
            # Get historical data
            end_time = datetime.now(UTC)
            start_time = end_time - timedelta(days=days)
            exchanges = [ExchangeEnum.MEXC, ExchangeEnum.GATEIO]
            df = await self.data_source.get_multi_exchange_data(exchanges, symbol,end_time, hours=days*24,
                                                                timeframe=KlineInterval.MINUTE_1)
            
            if df.empty or len(df) < 100:  # Minimum data points
                return None
            
            # Calculate spreads
            mexc_bid_col = get_column_key(ExchangeEnum.MEXC, 'bid_price')
            mexc_ask_col = get_column_key(ExchangeEnum.MEXC, 'ask_price')
            gateio_bid_col =  get_column_key(ExchangeEnum.GATEIO, 'bid_price')
            gateio_ask_col =  get_column_key(ExchangeEnum.GATEIO, 'ask_price')
            
            # Verify columns exist
            required_cols = [mexc_bid_col, mexc_ask_col, gateio_bid_col, gateio_ask_col]
            if not all(col in df.columns for col in required_cols):
                self.logger.warning(f"Missing price columns for {symbol}")
                return None
            
            # Calculate bid-ask spreads for both directions
            # MEXC → Gate.io: Buy on Gate.io (at ask), Sell on MEXC (at bid)
            mexc_to_gateio_spread = ((df[mexc_bid_col] - df[gateio_ask_col]) / df[gateio_ask_col] * 10000).dropna()
            
            # Gate.io → MEXC: Buy on MEXC (at ask), Sell on Gate.io (at bid)  
            gateio_to_mexc_spread = ((df[gateio_bid_col] - df[mexc_ask_col]) / df[mexc_ask_col] * 10000).dropna()
            
            # Combined spread analysis
            all_spreads = pd.concat([mexc_to_gateio_spread, gateio_to_mexc_spread])
            positive_spreads = all_spreads[all_spreads > 20]  # >20 bps threshold
            
            if len(positive_spreads) == 0:
                return None
            
            # Profitability metrics
            avg_spread_bps = float(positive_spreads.mean())
            opportunity_frequency = len(positive_spreads) / (days * 24)  # per hour
            # volume_weighted_spread = self._calculate_volume_weighted_spread(df, positive_spreads)
            
            # Risk metrics
            price_correlation = self._calculate_price_correlation(df, mexc_bid_col, gateio_bid_col)
            volatility_ratio = self._calculate_volatility_ratio(df, mexc_bid_col, gateio_bid_col)
            liquidity_depth_score = self._calculate_liquidity_score(df, mexc_bid_col, mexc_ask_col, 
                                                                   gateio_bid_col, gateio_ask_col)
            
            # Volume and volatility metrics
            avg_volume_per_min = self._calculate_avg_volume_per_min(df, mexc_bid_col, mexc_ask_col, gateio_bid_col, gateio_ask_col)
            price_volatility_bps = self._calculate_price_volatility_bps(df, mexc_bid_col, gateio_bid_col)
            
            # Execution metrics
            avg_execution_time_ms = 250.0  # Estimated based on system performance
            slippage_impact_bps = self._estimate_slippage_impact(df, symbol)
            transfer_viability_score = 0.5  # Placeholder for Phase 2
            
            # Create and calculate composite score
            opportunity_score = ArbitrageOpportunityScore(
                avg_spread_bps=avg_spread_bps,
                opportunity_frequency=opportunity_frequency,
                # volume_weighted_spread=0,#volume_weighted_spread,
                price_correlation=price_correlation,
                volatility_ratio=volatility_ratio,
                liquidity_depth_score=liquidity_depth_score,
                avg_volume_per_min=avg_volume_per_min,
                price_volatility_bps=price_volatility_bps,
                avg_execution_time_ms=avg_execution_time_ms,
                slippage_impact_bps=slippage_impact_bps,
                transfer_viability_score=transfer_viability_score,
                final_score=0.0
            )
            
            opportunity_score.final_score = opportunity_score.calculate_composite_score()
            
            return opportunity_score
            
        except Exception as e:
            self.logger.error(f"Error calculating metrics for {symbol}: {e}")
            return None
    
    # def _calculate_volume_weighted_spread(self, df: pd.DataFrame, spreads: pd.Series) -> float:
    #     """Calculate volume-weighted average spread."""
    #     try:
    #         # Use bid quantities as proxy for available volume
    #         mexc_vol = df['MEXC_SPOT_bid_qty'].fillna(0)
    #         gateio_vol = df['GATEIO_SPOT_bid_qty'].fillna(0)
    #
    #         # Average volume as weight
    #         volumes = (mexc_vol + gateio_vol) / 2
    #
    #         if len(volumes) != len(spreads):
    #             volumes = volumes.iloc[:len(spreads)]
    #
    #         if volumes.sum() == 0:
    #             return float(spreads.mean())
    #
    #         weighted_spread = (spreads * volumes).sum() / volumes.sum()
    #         return float(weighted_spread)
    #
    #     except Exception:
    #         return float(spreads.mean())
    
    def _calculate_price_correlation(self, df: pd.DataFrame, col1: str, col2: str) -> float:
        """Calculate price correlation between exchanges."""
        try:
            correlation = df[col1].corr(df[col2])
            return float(correlation) if not pd.isna(correlation) else 0.5
        except Exception:
            return 0.5
    
    def _calculate_volatility_ratio(self, df: pd.DataFrame, col1: str, col2: str) -> float:
        """Calculate relative volatility between exchanges."""
        try:
            vol1 = df[col1].pct_change().std()
            vol2 = df[col2].pct_change().std()
            
            if vol2 == 0:
                return 0.5
                
            ratio = vol1 / vol2
            return min(float(ratio), 2.0)  # Cap at 2x
            
        except Exception:
            return 0.5
    
    def _calculate_liquidity_score(self, df: pd.DataFrame, mexc_bid: str, mexc_ask: str, 
                                  gateio_bid: str, gateio_ask: str) -> float:
        """Calculate liquidity depth score."""
        try:
            # Calculate average bid-ask spreads as liquidity proxy
            mexc_spread = ((df[mexc_ask] - df[mexc_bid]) / df[mexc_bid] * 10000).mean()
            gateio_spread = ((df[gateio_ask] - df[gateio_bid]) / df[gateio_bid] * 10000).mean()
            
            # Lower spreads = better liquidity
            avg_spread = (mexc_spread + gateio_spread) / 2
            
            # Convert to score (lower spread = higher score)
            liquidity_score = max(0.1, 1.0 / (1.0 + avg_spread / 10))
            
            return float(liquidity_score)
            
        except Exception:
            return 0.5
    
    def _calculate_avg_volume_per_min(self, df: pd.DataFrame, mexc_bid_col: str, mexc_ask_col: str, 
                                     gateio_bid_col: str, gateio_ask_col: str) -> float:
        """Calculate average trading volume per minute."""
        try:
            # Try to get volume columns first
            mexc_vol_col = mexc_bid_col.replace('bid_price', 'bid_qty')
            gateio_vol_col = gateio_bid_col.replace('bid_price', 'bid_qty')
            
            if mexc_vol_col in df.columns and gateio_vol_col in df.columns:
                # Calculate average volume from bid quantities
                mexc_vol = df[mexc_vol_col].fillna(0)
                gateio_vol = df[gateio_vol_col].fillna(0)
                avg_volume = (mexc_vol.mean() + gateio_vol.mean()) / 2
                return float(avg_volume)
            else:
                # Fallback: estimate volume from price movements
                mexc_price_changes = df[mexc_bid_col].diff().abs().mean()
                gateio_price_changes = df[gateio_bid_col].diff().abs().mean()
                # Simple heuristic: more price movement suggests more volume
                estimated_volume = (mexc_price_changes + gateio_price_changes) * 1000
                return float(estimated_volume)
                
        except Exception:
            return 0.0  # Default if calculation fails
    
    def _calculate_price_volatility_bps(self, df: pd.DataFrame, col1: str, col2: str) -> float:
        """Calculate average price volatility in basis points."""
        try:
            # Calculate returns for both exchanges
            returns1 = df[col1].pct_change().dropna()
            returns2 = df[col2].pct_change().dropna()
            
            # Calculate volatility (standard deviation of returns)
            vol1 = returns1.std() * 10000  # Convert to basis points
            vol2 = returns2.std() * 10000
            
            # Return average volatility
            avg_volatility = (vol1 + vol2) / 2
            return float(avg_volatility)
            
        except Exception:
            return 0.0  # Default if calculation fails
    
    def _estimate_slippage_impact(self, df: pd.DataFrame, symbol: Symbol) -> float:
        """Estimate slippage impact based on historical data."""
        try:
            # Use bid-ask spread as slippage proxy
            mexc_spread = ((df['MEXC_SPOT_ask_price'] - df['MEXC_SPOT_bid_price']) / 
                          df['MEXC_SPOT_bid_price'] * 10000).mean()
            gateio_spread = ((df['GATEIO_SPOT_ask_price'] - df['GATEIO_SPOT_bid_price']) / 
                            df['GATEIO_SPOT_bid_price'] * 10000).mean()
            
            # Average spread as slippage estimate
            estimated_slippage = (mexc_spread + gateio_spread) / 2
            
            return min(float(estimated_slippage), 100.0)  # Cap at 1%
            
        except Exception:
            return 20.0  # Default 20 bps
    
    async def quick_screening(self, symbol: Symbol, days: int = 7) -> Optional[CandidateMetrics]:
        """Perform quick screening analysis on a symbol."""
        try:
            opportunity_score = await self.calculate_historical_metrics(symbol, days)
            
            if not opportunity_score:
                return None
            
            metrics = CandidateMetrics(
                symbol=symbol,
                opportunity_score=opportunity_score,
                data_points=0,  # Will be updated with actual data
                analysis_period_hours=days * 24,
                last_updated=datetime.now(UTC)
            )
            
            return metrics
            
        except Exception as e:
            self.logger.warning(f"Quick screening failed for {symbol}: {e}")
            return None
    
    async def discover_candidates(self, days: int = 7, min_score_threshold: float = 10.0) -> List[CandidateMetrics]:
        """Stage 1: Screen all common symbols and identify candidates."""
        self.logger.info("🔍 Stage 1: Discovering arbitrage candidates...")
        self.discovery_stats['analysis_start_time'] = datetime.now(UTC)
        
        # Get common symbols
        common_symbols = await self.discover_common_symbols()

        

        # Process symbols with concurrency limit
        semaphore = asyncio.Semaphore(5)
        
        async def process_symbol(symbol):
            async with semaphore:
                return await self.quick_screening(symbol, days)
        
        # Analyze symbols in parallel
        symbols_to_analyze = list(common_symbols.keys())[:50]  # Limit for testing
        self.discovery_stats['total_symbols_analyzed'] = len(symbols_to_analyze)
        
        self.logger.info(f"Analyzing {len(symbols_to_analyze)} symbols...")
        
        tasks = [process_symbol(symbol) for symbol in symbols_to_analyze]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter valid results
        valid_candidates = []
        for result in results:
            if isinstance(result, CandidateMetrics) and result is not None:
                if result.opportunity_score.final_score >= min_score_threshold:
                    valid_candidates.append(result)
        
        # Sort by composite score
        valid_candidates.sort(key=lambda x: x.opportunity_score.final_score, reverse=True)
        
        self.discovery_stats['viable_candidates_found'] = len(valid_candidates)
        self.discovery_stats['analysis_duration_seconds'] = (
            datetime.now(UTC) - self.discovery_stats['analysis_start_time']
        ).total_seconds()
        
        self.logger.info(f"✅ Found {len(valid_candidates)} viable candidates")
        self.candidate_metrics = valid_candidates
        
        return valid_candidates
    
    async def save_results(self, candidates: List[CandidateMetrics]):
        """Save discovery results to JSON files."""
        self.logger.info("💾 Saving candidate analysis results...")
        
        # Prepare results for JSON serialization
        results_data = {
            'analysis_metadata': {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'total_symbols_analyzed': self.discovery_stats['total_symbols_analyzed'],
                'viable_candidates_found': self.discovery_stats['viable_candidates_found'],
                'analysis_duration_seconds': self.discovery_stats['analysis_duration_seconds'],
                'analysis_start_time': self.discovery_stats['analysis_start_time'].isoformat() if self.discovery_stats['analysis_start_time'] else None
            },
            'top_candidates': []
        }
        
        for candidate in candidates[:20]:  # Top 20 candidates
            candidate_data = {
                'symbol': str(candidate.symbol),
                'final_score': candidate.opportunity_score.final_score,
                'avg_spread_bps': candidate.opportunity_score.avg_spread_bps,
                'opportunity_frequency': candidate.opportunity_score.opportunity_frequency,
                'price_correlation': candidate.opportunity_score.price_correlation,
                'volatility_ratio': candidate.opportunity_score.volatility_ratio,
                'liquidity_depth_score': candidate.opportunity_score.liquidity_depth_score,
                'estimated_slippage_bps': candidate.opportunity_score.slippage_impact_bps,
                'avg_volume_per_min': candidate.opportunity_score.avg_volume_per_min,
                'price_volatility_bps': candidate.opportunity_score.price_volatility_bps,
                'analysis_period_hours': candidate.analysis_period_hours,
                'last_updated': candidate.last_updated.isoformat() if candidate.last_updated else None
            }
            results_data['top_candidates'].append(candidate_data)
        
        # Save to file
        output_file = self.output_dir / f'spot_arbitrage_candidates_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(output_file, 'w') as f:
            json.dump(results_data, f, indent=2, default=str)
        
        self.logger.info(f"✅ Results saved to {output_file}")
        
        # Print summary
        self.print_summary(candidates)
    
    def print_summary(self, candidates: List[CandidateMetrics]):
        """Print analysis summary to console."""
        print("\n" + "="*80)
        print("🎯 SPOT ARBITRAGE CANDIDATE DISCOVERY SUMMARY")
        print("="*80)
        
        print(f"📊 Analysis Statistics:")
        print(f"   Total symbols analyzed: {self.discovery_stats['total_symbols_analyzed']}")
        print(f"   Viable candidates found: {self.discovery_stats['viable_candidates_found']}")
        print(f"   Analysis duration: {self.discovery_stats['analysis_duration_seconds']:.1f} seconds")
        print(f"   Success rate: {(self.discovery_stats['viable_candidates_found'] / max(1, self.discovery_stats['total_symbols_analyzed']) * 100):.1f}%")
        
        if candidates:
            print("LIST:")
            symbols_str = [f"'{s.symbol.base}_{s.symbol.quote}'" for s in candidates[:10]]
            print(f'[{", ".join(symbols_str)}]')

            print(f"\n🏆 Top 10 Arbitrage Candidates:")
            print(f"{'Rank':<4} {'Symbol':<12} {'Score':<8} {'Avg Spread':<12} {'Frequency':<10} {'Vol/Min':<10} {'Volatility':<12} {'Correlation':<12} {'Transfer':<20}")
            print("-" * 95)

            for i, candidate in enumerate(candidates[:10], 1):
                transferable = False
                transfer_info = ""
                for e in [ExchangeEnum.MEXC, ExchangeEnum.GATEIO]:
                    info = self.asset_info[e].get(candidate.symbol.base, None)
                    icon = "✅" if info and info.deposit_enable and info.withdraw_enable else "❌"
                    transfer_info += f"{e.value}:{icon} w:{info.withdraw_enable} d:{info.deposit_enable}  "
                score = candidate.opportunity_score
                print(f"{i:<4} {str(candidate.symbol):<12} {score.final_score:<8.2f} "
                      f"{score.avg_spread_bps:<12.1f} {score.opportunity_frequency:<10.2f} "
                      f"{score.avg_volume_per_min:<10.1f} {score.price_volatility_bps:<12.1f} "
                      f"{score.price_correlation:<12.3f} {transfer_info:<20}")
            
            # Best candidate details
            best = candidates[0]
            print(f"\n🥇 Best Candidate: {best.symbol}")
            print(f"   Final Score: {best.opportunity_score.final_score:.2f}")
            print(f"   Average Spread: {best.opportunity_score.avg_spread_bps:.1f} bps")
            print(f"   Opportunities/Hour: {best.opportunity_score.opportunity_frequency:.2f}")
            print(f"   Volume/Min: {best.opportunity_score.avg_volume_per_min:.1f}")
            print(f"   Price Volatility: {best.opportunity_score.price_volatility_bps:.1f} bps")
            print(f"   Price Correlation: {best.opportunity_score.price_correlation:.3f}")
            print(f"   Liquidity Score: {best.opportunity_score.liquidity_depth_score:.3f}")
        else:
            print("\n❌ No viable candidates found")
            print("   Consider lowering thresholds or increasing analysis period")
    
    async def run_discovery_pipeline(self, days: int = 7, min_score: float = 10.0) -> List[CandidateMetrics]:
        """Run complete candidate discovery pipeline."""
        try:
            self.logger.info("🚀 Starting Spot Arbitrage Candidate Discovery Pipeline")
            
            # Stage 1: Discovery
            candidates = await self.discover_candidates(days, min_score)
            
            # Save results
            if candidates:
                await self.save_results(candidates)
            
            return candidates
            
        except Exception as e:
            self.logger.error(f"Discovery pipeline failed: {e}")
            raise


# Example usage
if __name__ == "__main__":
    async def main():
        finder = SpotArbitrageCandidateFinder(output_dir="spot_arbitrage_results")
        
        # Run discovery pipeline
        candidates = await finder.run_discovery_pipeline(
            days=1,
            min_score=5.0  # Lower threshold for testing
        )
        
        print(f"\n✅ Discovery completed! Found {len(candidates)} candidates")
    
    asyncio.run(main())