"""
Cross-Exchange Delta-Neutral Arbitrage Analyzer

This analyzer implements the cross-exchange arbitrage strategy:
1. Monitor same symbol (e.g., BTC/USDT) across MEXC_SPOT and GATEIO_SPOT
2. Detect bid/ask spikes and arbitrage opportunities
3. Execute delta-neutral position switches between exchanges
4. Maintain hedge via GATEIO_FUTURES

Strategy Flow:
- Initial: 0 GATEIO, 0 GATEIO_FUTURES, 0 MEXC
- Signal → Hedge: 0 GATEIO, 10 GATEIO_FUTURES (short), 10 MEXC (long)
- Opportunities:
  * GATEIO bid spike → Sell MEXC, Buy GATEIO
  * MEXC ask spike → Sell MEXC, Buy GATEIO  
- Result: 10 GATEIO, 10 GATEIO_FUTURES, 0 MEXC
"""

from config import HftConfig
from exchanges.exchange_factory import get_rest_implementation
from exchanges.structs import Symbol
from exchanges.structs.common import AssetName
from exchanges.structs.enums import ExchangeEnum, KlineInterval
from typing import List, Optional, Dict, Any, Tuple
import asyncio
from datetime import datetime, UTC, timedelta
import pandas as pd
import json
from pathlib import Path
from dataclasses import dataclass
from infrastructure.logging import get_logger
from trading.data_sources.candles_loader import CandlesLoader

ANALYZER_TF = KlineInterval.MINUTE_1  # Use 1-minute for more granular analysis


@dataclass
class CrossExchangeOpportunity:
    """Cross-exchange arbitrage opportunity"""
    timestamp: datetime
    symbol: str
    opportunity_type: str  # 'market_market', 'limit_market'
    action: str  # 'gateio_bid_spike', 'mexc_ask_spike'
    
    # Exchange data
    mexc_bid: float
    mexc_ask: float
    gateio_bid: float
    gateio_ask: float
    
    # Opportunity metrics
    spread_bps: float  # Spread in basis points
    safe_offset: float  # Required safety margin
    execution_confidence: float  # 0.0 to 1.0
    expected_profit_bps: float  # Expected profit in basis points
    
    # Risk metrics
    volatility_risk: float
    liquidity_risk: float
    timing_risk: float


@dataclass
class PositionState:
    """Current position state across exchanges"""
    gateio_spot: float = 0.0
    gateio_futures: float = 0.0  # Negative = short hedge
    mexc_spot: float = 0.0
    
    @property
    def is_delta_neutral(self) -> bool:
        """Check if positions are delta neutral"""
        total_exposure = self.gateio_spot + self.mexc_spot + self.gateio_futures
        return abs(total_exposure) < 0.01  # Within 1% tolerance
    
    @property
    def total_spot_exposure(self) -> float:
        """Total spot exposure across exchanges"""
        return self.gateio_spot + self.mexc_spot


class SafeOffsetCalculator:
    """Calculate statistically safe offsets for limit orders"""
    
    def __init__(self, confidence_level: float = 0.95):
        self.confidence_level = confidence_level
    
    def calculate_volatility_metrics(self, df: pd.DataFrame, window: int = 20) -> Dict[str, float]:
        """Calculate volatility metrics from OHLCV data"""
        if len(df) < window:
            return {'volatility': 0.02, 'avg_spread': 0.001, 'max_adverse_move': 0.005}
        
        # Calculate returns volatility
        returns = df['close'].pct_change().dropna()
        volatility = returns.std()
        
        # Calculate average spread (proxy from high-low)
        spreads = (df['high'] - df['low']) / df['close']
        avg_spread = spreads.mean()
        
        # Calculate maximum adverse movement (95th percentile)
        adverse_moves = abs(returns).rolling(window).max()
        max_adverse_move = adverse_moves.quantile(self.confidence_level)
        
        return {
            'volatility': volatility,
            'avg_spread': avg_spread,
            'max_adverse_move': max_adverse_move
        }
    
    def calculate_safe_offset(self, mexc_data: pd.DataFrame, gateio_data: pd.DataFrame, 
                            order_type: str = 'limit') -> float:
        """
        Calculate safe offset for limit orders based on volatility analysis
        
        Args:
            mexc_data: MEXC OHLCV data
            gateio_data: Gate.io OHLCV data  
            order_type: 'limit' or 'market'
            
        Returns:
            Safe offset as percentage (e.g., 0.001 = 0.1%)
        """
        mexc_metrics = self.calculate_volatility_metrics(mexc_data)
        gateio_metrics = self.calculate_volatility_metrics(gateio_data)
        
        # Take the higher volatility for safety
        volatility = max(mexc_metrics['volatility'], gateio_metrics['volatility'])
        avg_spread = max(mexc_metrics['avg_spread'], gateio_metrics['avg_spread'])
        max_adverse = max(mexc_metrics['max_adverse_move'], gateio_metrics['max_adverse_move'])
        
        if order_type == 'limit':
            # For limit orders: volatility + spread + adverse movement buffer
            safe_offset = volatility * 2 + avg_spread + max_adverse * 1.5
        else:
            # For market orders: spread + slippage buffer
            safe_offset = avg_spread + volatility * 0.5
        
        # Minimum safety margin of 0.05% (5 bps)
        return max(safe_offset, 0.0005)


class OpportunityDetector:
    """Detect cross-exchange arbitrage opportunities"""
    
    def __init__(self, min_profit_bps: float = 10.0):
        self.min_profit_bps = min_profit_bps
        self.safe_calculator = SafeOffsetCalculator()
    
    def analyze_current_prices(self, mexc_data: pd.DataFrame, gateio_data: pd.DataFrame) -> Tuple[float, float, float, float]:
        """Get current bid/ask prices from latest candle data"""
        if mexc_data.empty or gateio_data.empty:
            return 0, 0, 0, 0
        
        # Use close price as mid, estimate bid/ask from spread
        mexc_close = mexc_data['close'].iloc[-1]
        gateio_close = gateio_data['close'].iloc[-1]
        
        # Estimate spread as 0.05% for now (could be improved with real bid/ask data)
        spread_factor = 0.0005
        
        mexc_bid = mexc_close * (1 - spread_factor)
        mexc_ask = mexc_close * (1 + spread_factor)
        gateio_bid = gateio_close * (1 - spread_factor)
        gateio_ask = gateio_close * (1 + spread_factor)
        
        return mexc_bid, mexc_ask, gateio_bid, gateio_ask
    
    def detect_market_market_opportunity(self, mexc_bid: float, mexc_ask: float, 
                                       gateio_bid: float, gateio_ask: float,
                                       safe_offset: float) -> Optional[CrossExchangeOpportunity]:
        """Detect direct market-to-market arbitrage opportunities"""
        
        # Check GATEIO bid > MEXC ask (sell MEXC, buy GATEIO)
        if gateio_bid > mexc_ask:
            spread_bps = ((gateio_bid - mexc_ask) / mexc_ask) * 10000
            expected_profit = spread_bps - (safe_offset * 10000)
            
            if expected_profit > self.min_profit_bps:
                return CrossExchangeOpportunity(
                    timestamp=datetime.now(UTC),
                    symbol="ANALYZED_SYMBOL",
                    opportunity_type="market_market",
                    action="gateio_bid_spike",
                    mexc_bid=mexc_bid,
                    mexc_ask=mexc_ask,
                    gateio_bid=gateio_bid,
                    gateio_ask=gateio_ask,
                    spread_bps=spread_bps,
                    safe_offset=safe_offset,
                    execution_confidence=0.9,  # High confidence for market orders
                    expected_profit_bps=expected_profit,
                    volatility_risk=0.3,
                    liquidity_risk=0.2,
                    timing_risk=0.1
                )
        
        # Check MEXC bid > GATEIO ask (sell GATEIO, buy MEXC) - reverse direction
        if mexc_bid > gateio_ask:
            spread_bps = ((mexc_bid - gateio_ask) / gateio_ask) * 10000
            expected_profit = spread_bps - (safe_offset * 10000)
            
            if expected_profit > self.min_profit_bps:
                return CrossExchangeOpportunity(
                    timestamp=datetime.now(UTC),
                    symbol="ANALYZED_SYMBOL", 
                    opportunity_type="market_market",
                    action="mexc_bid_spike",
                    mexc_bid=mexc_bid,
                    mexc_ask=mexc_ask,
                    gateio_bid=gateio_bid,
                    gateio_ask=gateio_ask,
                    spread_bps=spread_bps,
                    safe_offset=safe_offset,
                    execution_confidence=0.9,
                    expected_profit_bps=expected_profit,
                    volatility_risk=0.3,
                    liquidity_risk=0.2,
                    timing_risk=0.1
                )
        
        return None
    
    def detect_limit_market_opportunity(self, mexc_data: pd.DataFrame, gateio_data: pd.DataFrame,
                                      mexc_bid: float, mexc_ask: float,
                                      gateio_bid: float, gateio_ask: float) -> Optional[CrossExchangeOpportunity]:
        """Detect limit-to-market arbitrage opportunities"""
        
        safe_offset = self.safe_calculator.calculate_safe_offset(mexc_data, gateio_data, 'limit')
        
        # Check if we can place a safe limit buy on GATEIO and sell market on MEXC
        gateio_limit_buy_price = gateio_ask * (1 + safe_offset)
        
        if mexc_bid > gateio_limit_buy_price:
            spread_bps = ((mexc_bid - gateio_limit_buy_price) / gateio_limit_buy_price) * 10000
            
            if spread_bps > self.min_profit_bps:
                return CrossExchangeOpportunity(
                    timestamp=datetime.now(UTC),
                    symbol="ANALYZED_SYMBOL",
                    opportunity_type="limit_market",
                    action="gateio_limit_mexc_market",
                    mexc_bid=mexc_bid,
                    mexc_ask=mexc_ask,
                    gateio_bid=gateio_bid,
                    gateio_ask=gateio_ask,
                    spread_bps=spread_bps,
                    safe_offset=safe_offset,
                    execution_confidence=0.7,  # Lower confidence for limit orders
                    expected_profit_bps=spread_bps,
                    volatility_risk=0.4,
                    liquidity_risk=0.3,
                    timing_risk=0.5
                )
        
        # Check reverse direction: limit sell on MEXC, market buy on GATEIO
        mexc_limit_sell_price = mexc_bid * (1 - safe_offset)
        
        if mexc_limit_sell_price > gateio_ask:
            spread_bps = ((mexc_limit_sell_price - gateio_ask) / gateio_ask) * 10000
            
            if spread_bps > self.min_profit_bps:
                return CrossExchangeOpportunity(
                    timestamp=datetime.now(UTC),
                    symbol="ANALYZED_SYMBOL",
                    opportunity_type="limit_market", 
                    action="mexc_limit_gateio_market",
                    mexc_bid=mexc_bid,
                    mexc_ask=mexc_ask,
                    gateio_bid=gateio_bid,
                    gateio_ask=gateio_ask,
                    spread_bps=spread_bps,
                    safe_offset=safe_offset,
                    execution_confidence=0.7,
                    expected_profit_bps=spread_bps,
                    volatility_risk=0.4,
                    liquidity_risk=0.3,
                    timing_risk=0.5
                )
        
        return None


class CrossExchangeArbitrageAnalyzer:
    """Main analyzer for cross-exchange delta-neutral arbitrage"""
    
    def __init__(self, symbol: Symbol, output_dir: str = "cross_exchange_results"):
        self.symbol = symbol
        self.config = HftConfig()
        self.logger = get_logger("CrossExchangeArbitrageAnalyzer")
        self.candles_loader = CandlesLoader(logger=self.logger)
        self.opportunity_detector = OpportunityDetector()
        
        # Initialize exchange clients
        self.mexc_client = get_rest_implementation(self.config.get_exchange_config('mexc'), False)
        self.gateio_client = get_rest_implementation(self.config.get_exchange_config('gateio'), False)
        
        # Cache and output
        self.candles_cache: Dict[ExchangeEnum, pd.DataFrame] = {}
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Position tracking
        self.position_state = PositionState()
    
    async def load_exchange_data(self, end_time: datetime, hours: int = 24) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Load candle data for the symbol from both exchanges"""
        start_time = end_time - timedelta(hours=hours)
        
        self.logger.info(f"Loading data for {self.symbol.base}/{self.symbol.quote}")
        
        # Load MEXC data
        mexc_data = await self.candles_loader.download_candles(
            exchange=ExchangeEnum.MEXC,
            symbol=self.symbol,
            timeframe=ANALYZER_TF,
            start_date=start_time,
            end_date=end_time,
            force_download=False
        )
        
        # Load GATEIO data
        gateio_data = await self.candles_loader.download_candles(
            exchange=ExchangeEnum.GATEIO,
            symbol=self.symbol,
            timeframe=ANALYZER_TF,
            start_date=start_time,
            end_date=end_time,
            force_download=False
        )
        
        if mexc_data is not None and not mexc_data.empty:
            self.logger.info(f"Loaded {len(mexc_data)} MEXC candles")
            self.candles_cache[ExchangeEnum.MEXC] = mexc_data
        else:
            self.logger.warning("No MEXC data loaded")
            mexc_data = pd.DataFrame()
        
        if gateio_data is not None and not gateio_data.empty:
            self.logger.info(f"Loaded {len(gateio_data)} GATEIO candles")
            self.candles_cache[ExchangeEnum.GATEIO] = gateio_data
        else:
            self.logger.warning("No GATEIO data loaded")
            gateio_data = pd.DataFrame()
        
        return mexc_data, gateio_data
    
    def analyze_price_patterns(self, mexc_data: pd.DataFrame, gateio_data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze price patterns and volatility characteristics"""
        if mexc_data.empty or gateio_data.empty:
            return {'error': 'Insufficient data'}
        
        # Align timestamps for comparison
        common_index = mexc_data.index.intersection(gateio_data.index)
        if len(common_index) < 10:
            return {'error': 'Insufficient overlapping data'}
        
        mexc_aligned = mexc_data.loc[common_index]
        gateio_aligned = gateio_data.loc[common_index]
        
        # Calculate spread statistics
        mexc_prices = mexc_aligned['close']
        gateio_prices = gateio_aligned['close']
        spreads = (mexc_prices - gateio_prices) / gateio_prices
        
        # Volatility analysis
        mexc_returns = mexc_prices.pct_change().dropna()
        gateio_returns = gateio_prices.pct_change().dropna()
        
        analysis = {
            'data_points': len(common_index),
            'time_range': f"{common_index.min()} to {common_index.max()}",
            
            # Spread analysis
            'avg_spread_bps': spreads.mean() * 10000,
            'spread_std_bps': spreads.std() * 10000,
            'max_spread_bps': spreads.max() * 10000,
            'min_spread_bps': spreads.min() * 10000,
            
            # Volatility analysis
            'mexc_volatility': mexc_returns.std(),
            'gateio_volatility': gateio_returns.std(),
            'correlation': mexc_returns.corr(gateio_returns) if len(mexc_returns) == len(gateio_returns) else 0.0,
            
            # Current prices
            'mexc_current': mexc_prices.iloc[-1],
            'gateio_current': gateio_prices.iloc[-1],
            'current_spread_bps': spreads.iloc[-1] * 10000
        }
        
        return analysis
    
    def scan_opportunities(self, mexc_data: pd.DataFrame, gateio_data: pd.DataFrame) -> List[CrossExchangeOpportunity]:
        """Scan for arbitrage opportunities in the data"""
        opportunities = []
        
        if mexc_data.empty or gateio_data.empty:
            return opportunities
        
        # Get current prices
        mexc_bid, mexc_ask, gateio_bid, gateio_ask = self.opportunity_detector.analyze_current_prices(
            mexc_data, gateio_data
        )
        
        if mexc_bid == 0 or gateio_bid == 0:
            return opportunities
        
        # Calculate safe offset
        safe_offset = self.opportunity_detector.safe_calculator.calculate_safe_offset(
            mexc_data, gateio_data, 'market'
        )
        
        # Check for market-market opportunities
        market_opp = self.opportunity_detector.detect_market_market_opportunity(
            mexc_bid, mexc_ask, gateio_bid, gateio_ask, safe_offset
        )
        
        if market_opp:
            market_opp.symbol = f"{self.symbol.base}/{self.symbol.quote}"
            opportunities.append(market_opp)
        
        # Check for limit-market opportunities
        limit_opp = self.opportunity_detector.detect_limit_market_opportunity(
            mexc_data, gateio_data, mexc_bid, mexc_ask, gateio_bid, gateio_ask
        )
        
        if limit_opp:
            limit_opp.symbol = f"{self.symbol.base}/{self.symbol.quote}"
            opportunities.append(limit_opp)
        
        return opportunities
    
    def save_analysis_report(self, analysis: Dict[str, Any], opportunities: List[CrossExchangeOpportunity]) -> Path:
        """Save comprehensive analysis report"""
        report = {
            'symbol': f"{self.symbol.base}/{self.symbol.quote}",
            'timestamp': datetime.now(UTC).isoformat(),
            'analysis': analysis,
            'position_state': {
                'gateio_spot': self.position_state.gateio_spot,
                'gateio_futures': self.position_state.gateio_futures,
                'mexc_spot': self.position_state.mexc_spot,
                'is_delta_neutral': self.position_state.is_delta_neutral,
                'total_spot_exposure': self.position_state.total_spot_exposure
            },
            'opportunities': [
                {
                    'timestamp': opp.timestamp.isoformat(),
                    'type': opp.opportunity_type,
                    'action': opp.action,
                    'spread_bps': opp.spread_bps,
                    'expected_profit_bps': opp.expected_profit_bps,
                    'execution_confidence': opp.execution_confidence,
                    'safe_offset': opp.safe_offset,
                    'mexc_bid': opp.mexc_bid,
                    'mexc_ask': opp.mexc_ask,
                    'gateio_bid': opp.gateio_bid,
                    'gateio_ask': opp.gateio_ask,
                    'risks': {
                        'volatility': opp.volatility_risk,
                        'liquidity': opp.liquidity_risk,
                        'timing': opp.timing_risk
                    }
                }
                for opp in opportunities
            ]
        }
        
        filename = f"cross_exchange_analysis_{self.symbol.base}_{self.symbol.quote}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
        output_path = self.output_dir / filename
        
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        self.logger.info(f"Analysis report saved to {output_path}")
        return output_path
    
    async def analyze(self, end_time: datetime = None, hours: int = 24) -> Dict[str, Any]:
        """Main analysis pipeline"""
        end_time = end_time or datetime.now(UTC)
        
        self.logger.info(f"🚀 Starting Cross-Exchange Arbitrage Analysis for {self.symbol.base}/{self.symbol.quote}")
        self.logger.info(f"📅 Analysis Period: {end_time - timedelta(hours=hours)} to {end_time}")
        self.logger.info(f"🏢 Exchanges: MEXC_SPOT vs GATEIO_SPOT")
        self.logger.info(f"🎯 Strategy: Delta-neutral cross-exchange arbitrage")
        
        # Load data from both exchanges
        mexc_data, gateio_data = await self.load_exchange_data(end_time, hours)
        
        if mexc_data.empty or gateio_data.empty:
            self.logger.error("❌ Insufficient data from exchanges")
            return {'error': 'Insufficient data'}
        
        # Analyze price patterns
        self.logger.info("📊 Analyzing price patterns and volatility")
        analysis = self.analyze_price_patterns(mexc_data, gateio_data)
        
        if 'error' in analysis:
            self.logger.error(f"❌ Analysis failed: {analysis['error']}")
            return analysis
        
        # Scan for opportunities
        self.logger.info("🔍 Scanning for arbitrage opportunities")
        opportunities = self.scan_opportunities(mexc_data, gateio_data)
        
        # Log results
        if opportunities:
            self.logger.info(f"🎯 Found {len(opportunities)} arbitrage opportunities:")
            for i, opp in enumerate(opportunities):
                self.logger.info(f"  {i+1}. {opp.opportunity_type.upper()}: {opp.action}")
                self.logger.info(f"     Expected Profit: {opp.expected_profit_bps:.1f} bps")
                self.logger.info(f"     Confidence: {opp.execution_confidence:.1%}")
                self.logger.info(f"     Safe Offset: {opp.safe_offset:.4f}")
        else:
            self.logger.info("📊 No arbitrage opportunities found in current market conditions")
        
        # Save report
        report_path = self.save_analysis_report(analysis, opportunities)
        
        return {
            'symbol': f"{self.symbol.base}/{self.symbol.quote}",
            'opportunities_count': len(opportunities),
            'opportunities': opportunities,
            'analysis': analysis,
            'report_path': report_path
        }


if __name__ == "__main__":
    async def main():
        """Example usage of the cross-exchange arbitrage analyzer"""
        
        # Analyze BTC/USDT cross-exchange arbitrage
        symbol = Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
        analyzer = CrossExchangeArbitrageAnalyzer(symbol)
        
        print("🚀 Starting Cross-Exchange Arbitrage Analysis")
        print(f"🎯 Symbol: {symbol.base}/{symbol.quote}")
        print(f"🏢 Strategy: MEXC_SPOT vs GATEIO_SPOT with GATEIO_FUTURES hedge")
        
        try:
            results = await analyzer.analyze(hours=48)
            
            if 'error' not in results:
                print(f"\n📊 Analysis Results:")
                print(f"   Opportunities Found: {results['opportunities_count']}")
                print(f"   Data Points: {results['analysis']['data_points']}")
                print(f"   Current Spread: {results['analysis']['current_spread_bps']:.1f} bps")
                print(f"   MEXC-GATEIO Correlation: {results['analysis']['correlation']:.3f}")
                
                if results['opportunities']:
                    print(f"\n🎯 Best Opportunities:")
                    for opp in results['opportunities'][:3]:
                        print(f"   • {opp.opportunity_type}: {opp.expected_profit_bps:.1f} bps profit")
                        print(f"     Action: {opp.action}")
                        print(f"     Confidence: {opp.execution_confidence:.1%}")
                
                print(f"\n📄 Full report: {results['report_path']}")
            else:
                print(f"\n❌ Analysis failed: {results['error']}")
            
        except Exception as e:
            print(f"\n❌ Analysis failed: {e}")
            print("💡 Make sure exchange connections are properly configured")
    
    asyncio.run(main())