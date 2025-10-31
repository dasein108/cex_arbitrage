from config import HftConfig
from exchanges.exchange_factory import get_rest_implementation
from exchanges.structs import SymbolInfo, Symbol
from exchanges.structs.common import AssetInfo
from exchanges.structs.enums import ExchangeEnum, KlineInterval
from typing import List, Optional, Dict, Any, NamedTuple, Tuple
import asyncio
from datetime import datetime, UTC, timedelta
import pandas as pd
import numpy as np
import json
from pathlib import Path
from dataclasses import dataclass, field
from infrastructure.logging import get_logger
from trading.analysis.data_sources import CandlesLoader
from trading.research.cross_arbitrage.book_ticker_source import BookTickerDbSource, CandlesBookTickerSource
from trading.research.cross_arbitrage.hedged_cross_arbitrage_backtest import HedgedCrossArbitrageBacktest, BacktestConfig
from trading.research.cross_arbitrage.arbitrage_analyzer import ArbitrageAnalyzer, AnalyzerKeys
from db import get_database_manager
from scipy import stats
from enum import Enum
import warnings
warnings.filterwarnings('ignore')

ANALYZER_TF = KlineInterval.MINUTE_1





class MakerOrderCandidateAnalyzer:
    """Enhanced arbitrage candidate analyzer with multi-stage pipeline."""
    
    def __init__(self, spot_ex: ExchangeEnum, futures_ex: ExchangeEnum, output_dir: str = "results"):
        self.spot_ex = spot_ex
        self.futures_ex = futures_ex
        self.config = HftConfig()
        self.logger = get_logger("SpotFuturesArbitrageCandidateAnalyzer")
        # self.candle_loader = CandlesLoader(logger=self.logger)
        
        # Output configuration
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        

        self.clients = {exchange: self._get_exchange_client(exchange) for exchange in [spot_ex, futures_ex]}
        self.symbol_df_cache: Dict[Symbol, pd.DataFrame] = {}
        self.candles_loader = CandlesLoader()
        self.fees: Dict[ExchangeEnum, float] = {ExchangeEnum.MEXC: 0.0,
                                                ExchangeEnum.GATEIO_FUTURES: 0.0005}


    def _get_exchange_client(self, exchange: ExchangeEnum):
        return get_rest_implementation(self.config.get_exchange_config(exchange.value), False)

    async def get_tradable_pairs(self):
        si_result = await asyncio.gather(*[c.get_symbols_info() for c in self.clients.values()])

        symbols_info: Dict[ExchangeEnum, SymbolInfo] = {}
        symbol_exchanges: Dict[Symbol, List[ExchangeEnum]] = {}
        for exchange, symbols in zip(self.clients.keys(), si_result):
            symbols_info[exchange] = symbols
            for symbol in symbols.keys():
                if symbol not in symbol_exchanges:
                    symbol_exchanges[symbol] = []
                symbol_exchanges[symbol].append(exchange)


        tradable_pairs = [symbol for symbol, exchanges in symbol_exchanges.items() if len(exchanges) > 1]

        return tradable_pairs

    async def get_candles(self, exchanges: List[ExchangeEnum], symbol: Symbol, tf: KlineInterval,
                            start_date: datetime, end_date: datetime):
        tasks = [
            self.candles_loader.download_candles(
                exchange=exchange,
                symbol=symbol,
                timeframe=tf,
                start_date=start_date,
                end_date=end_date,
            )
            for exchange in exchanges
        ]

        results = await asyncio.gather(*tasks)

        exchange_df_map: dict[ExchangeEnum, Optional[pd.DataFrame]] = {}
        for exchange, df in zip(exchanges, results):
            exchange_df_map[exchange] = df

        return exchange_df_map


    def calculate_volatility_metrics(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate comprehensive volatility metrics for strategy analysis"""
        try:
            spot_close = df[f'{self.spot_ex.value}_close']
            futures_close = df[f'{self.futures_ex.value}_close']
            spot_high = df[f'{self.spot_ex.value}_high']
            spot_low = df[f'{self.spot_ex.value}_low']
            futures_high = df[f'{self.futures_ex.value}_high']
            futures_low = df[f'{self.futures_ex.value}_low']
            
            # Relative volatility (spot vs futures)
            spot_returns = spot_close.pct_change().dropna()
            futures_returns = futures_close.pct_change().dropna()
            
            spot_volatility = spot_returns.std()
            futures_volatility = futures_returns.std()
            volatility_ratio = spot_volatility / futures_volatility if futures_volatility > 0 else 0
            
            # Intraday volatility (high-low normalized)
            spot_hl_ratio = ((spot_high - spot_low) / spot_close).dropna()
            futures_hl_ratio = ((futures_high - futures_low) / futures_close).dropna()
            
            # Spike detection metrics
            spike_threshold = spot_returns.std() * 2.5  # 2.5 sigma events
            spike_frequency = (abs(spot_returns) > spike_threshold).mean() if len(spot_returns) > 0 else 0
            
            # Price gap analysis (between candles)
            spot_gaps = abs((spot_close - spot_close.shift(1)) / spot_close.shift(1)).dropna()
            avg_gap = spot_gaps.mean()
            max_gap = spot_gaps.max()
            
            return {
                'volatility_ratio': volatility_ratio,
                'spot_volatility': spot_volatility,
                'futures_volatility': futures_volatility,
                'avg_spot_hl_ratio': spot_hl_ratio.mean(),
                'avg_futures_hl_ratio': futures_hl_ratio.mean(),
                'hl_ratio_difference': spot_hl_ratio.mean() - futures_hl_ratio.mean(),
                'spike_frequency': spike_frequency,
                'spike_threshold': spike_threshold,
                'avg_price_gap': avg_gap,
                'max_price_gap': max_gap
            }
        except Exception as e:
            self.logger.error(f"Error calculating volatility metrics: {e}")
            return {}

    def calculate_spread_metrics(self, df: pd.DataFrame) -> Dict[str, float]:
        """Analyze spread patterns and calculate optimal offset parameters"""
        try:
            spot_close = df[f'{self.spot_ex.value}_close']
            futures_close = df[f'{self.futures_ex.value}_close']
            spot_volume = df[f'{self.spot_ex.value}_volume']
            futures_volume = df[f'{self.futures_ex.value}_volume']
            
            # Price correlation (how tight is the basis?)
            correlation = spot_close.corr(futures_close)
            
            # Basis analysis (futures - spot)
            basis = futures_close - spot_close
            basis_volatility = basis.std()
            basis_mean = basis.mean()
            basis_pct = (basis / spot_close * 100).dropna()
            
            # Volume ratio analysis
            avg_spot_volume = spot_volume.mean()
            avg_futures_volume = futures_volume.mean()
            volume_ratio = avg_spot_volume / avg_futures_volume if avg_futures_volume > 0 else 0
            
            # Calculate safe offset based on volatility
            avg_price = spot_close.mean()
            safe_offset_bps = (basis_volatility / avg_price) * 10000 if avg_price > 0 else 0
            
            # Price efficiency metrics
            price_diff_pct = abs(basis_pct).mean()
            max_basis_pct = abs(basis_pct).max()
            
            return {
                'correlation': correlation,
                'basis_volatility': basis_volatility,
                'basis_mean': basis_mean,
                'basis_pct_mean': basis_pct.mean(),
                'basis_pct_std': basis_pct.std(),
                'volume_ratio': volume_ratio,
                'avg_spot_volume': avg_spot_volume,
                'avg_futures_volume': avg_futures_volume,
                'safe_offset_bps': safe_offset_bps,
                'price_diff_pct': price_diff_pct,
                'max_basis_pct': max_basis_pct,
                'avg_price': avg_price
            }
        except Exception as e:
            self.logger.error(f"Error calculating spread metrics: {e}")
            return {}

    def detect_market_regime(self, df: pd.DataFrame) -> Dict[str, float]:
        """Identify market regime: trending vs mean-reverting"""
        try:
            spot_close = df[f'{self.spot_ex.value}_close']
            spot_high = df[f'{self.spot_ex.value}_high']
            spot_low = df[f'{self.spot_ex.value}_low']
            
            # Trend analysis
            sma_20 = spot_close.rolling(20, min_periods=1).mean()
            sma_50 = spot_close.rolling(50, min_periods=1).mean()
            
            current_price = spot_close.iloc[-1]
            trend_direction = (current_price - sma_20.iloc[-1]) / sma_20.iloc[-1] if len(sma_20) > 0 else 0
            trend_strength = abs(trend_direction)
            
            # SMA slope analysis
            sma_20_slope = (sma_20.iloc[-1] - sma_20.iloc[-10]) / sma_20.iloc[-10] if len(sma_20) >= 10 else 0
            
            # RSI calculation for mean reversion detection
            delta = spot_close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(14, min_periods=1).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=1).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-1] if len(rsi) > 0 else 50
            
            # Bollinger Bands for volatility regime
            bb_period = 20
            bb_std = 2
            bb_middle = spot_close.rolling(bb_period, min_periods=1).mean()
            bb_std_dev = spot_close.rolling(bb_period, min_periods=1).std()
            bb_upper = bb_middle + (bb_std_dev * bb_std)
            bb_lower = bb_middle - (bb_std_dev * bb_std)
            
            bb_position = ((current_price - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1])) if len(bb_upper) > 0 else 0.5
            bb_width = ((bb_upper.iloc[-1] - bb_lower.iloc[-1]) / bb_middle.iloc[-1]) if len(bb_middle) > 0 else 0
            
            # Market regime classification
            is_trending = trend_strength > 0.02  # 2% trend
            is_mean_reverting = trend_strength < 0.01 and 30 < current_rsi < 70
            is_high_volatility = bb_width > 0.1  # 10% BB width
            
            return {
                'trend_direction': trend_direction,
                'trend_strength': trend_strength,
                'sma_20_slope': sma_20_slope,
                'rsi': current_rsi,
                'bb_position': bb_position,
                'bb_width': bb_width,
                'is_trending': is_trending,
                'is_mean_reverting': is_mean_reverting,
                'is_high_volatility': is_high_volatility
            }
        except Exception as e:
            self.logger.error(f"Error detecting market regime: {e}")
            return {}

    def calculate_optimal_offset(self, volatility_metrics: Dict, spread_metrics: Dict, regime_metrics: Dict) -> Dict[str, float]:
        """Calculate dynamic offset based on market conditions and liquidity"""
        try:
            # Get liquidity characteristics
            liquidity_metrics = self.calculate_liquidity_metrics(spread_metrics)
            liquidity_tier = liquidity_metrics.get('liquidity_tier', 'MEDIUM')
            
            # Base offset varies by liquidity tier
            if liquidity_tier == 'ULTRA_LOW':
                base_offset_ticks = 3  # More conservative for ultra-low liquidity
            elif liquidity_tier == 'LOW':
                base_offset_ticks = 2.5  # Slightly more conservative
            else:
                base_offset_ticks = 2  # Standard for higher liquidity
            
            # Increase offset during high volatility
            volatility_ratio = volatility_metrics.get('volatility_ratio', 1.0)
            volatility_multiplier = min(volatility_ratio, 3.0)
            
            # Adjust for market regime
            if regime_metrics.get('is_mean_reverting', False):
                regime_multiplier = 0.7  # More aggressive in mean-reverting markets
            elif regime_metrics.get('is_trending', False):
                regime_multiplier = 1.5  # More conservative in trending markets
            else:
                regime_multiplier = 1.0
            
            # Account for basis volatility
            avg_price = spread_metrics.get('avg_price', 1.0)
            basis_volatility = spread_metrics.get('basis_volatility', 0.0)
            basis_multiplier = 1 + (basis_volatility / avg_price * 100) if avg_price > 0 else 1.0
            
            # High volatility adjustment
            if regime_metrics.get('is_high_volatility', False):
                volatility_adjustment = 1.3
            else:
                volatility_adjustment = 1.0
            
            # Liquidity-specific adjustments
            liquidity_offset_multiplier = liquidity_metrics.get('offset_multiplier', 1.0)
            
            optimal_offset = (base_offset_ticks * volatility_multiplier * regime_multiplier * 
                            basis_multiplier * volatility_adjustment * liquidity_offset_multiplier)
            
            # Calculate position sizing factor based on risk and liquidity
            risk_score = self._calculate_risk_score(volatility_metrics, spread_metrics, regime_metrics)
            liquidity_risk_multiplier = liquidity_metrics.get('risk_multiplier', 1.0)
            
            # Adjust position size for liquidity tier
            base_position_factor = 1.0 - (risk_score * 0.6)  # Less aggressive risk reduction
            if liquidity_tier == 'ULTRA_LOW':
                liquidity_position_factor = 0.3  # Very small positions
            elif liquidity_tier == 'LOW':
                liquidity_position_factor = 0.5  # Small positions
            elif liquidity_tier == 'MEDIUM':
                liquidity_position_factor = 0.8  # Normal positions
            else:
                liquidity_position_factor = 1.0  # Full positions
            
            final_position_factor = min(base_position_factor, liquidity_position_factor)
            position_size_factor = max(0.05, final_position_factor)  # Minimum 5% position
            
            return {
                'optimal_offset_ticks': max(1, min(optimal_offset, 15)),  # Cap between 1-15 ticks (wider for low liquidity)
                'volatility_multiplier': volatility_multiplier,
                'regime_multiplier': regime_multiplier,
                'basis_multiplier': basis_multiplier,
                'liquidity_offset_multiplier': liquidity_offset_multiplier,
                'position_size_factor': position_size_factor,
                'risk_score': risk_score,
                'liquidity_tier': liquidity_tier,
                'base_offset_ticks': base_offset_ticks
            }
        except Exception as e:
            self.logger.error(f"Error calculating optimal offset: {e}")
            return {'optimal_offset_ticks': 2, 'position_size_factor': 0.5, 'risk_score': 0.5}

    def _calculate_risk_score(self, volatility_metrics: Dict, spread_metrics: Dict, regime_metrics: Dict) -> float:
        """Calculate overall risk score (0-1, higher = riskier)"""
        try:
            risk_factors = []
            
            # Volatility risk
            vol_ratio = volatility_metrics.get('volatility_ratio', 1.0)
            if vol_ratio > 2.0:
                risk_factors.append(0.3)  # High vol ratio risk
            
            # Correlation risk
            correlation = spread_metrics.get('correlation', 1.0)
            if correlation < 0.7:
                risk_factors.append(0.4)  # Low correlation risk
            
            # Trending market risk
            if regime_metrics.get('is_trending', False):
                risk_factors.append(0.2)  # Trending market risk
            
            # High volatility risk
            if regime_metrics.get('is_high_volatility', False):
                risk_factors.append(0.2)  # High volatility risk
            
            # Volume imbalance risk
            volume_ratio = spread_metrics.get('volume_ratio', 1.0)
            if volume_ratio < 0.1 or volume_ratio > 10:  # Extreme volume imbalance
                risk_factors.append(0.3)
            
            # Basis volatility risk
            basis_pct_std = spread_metrics.get('basis_pct_std', 0)
            if basis_pct_std > 5.0:  # >5% basis volatility
                risk_factors.append(0.2)
            
            return min(1.0, sum(risk_factors))
        except Exception as e:
            self.logger.error(f"Error calculating risk score: {e}")
            return 0.5

    def calculate_liquidity_metrics(self, spread_metrics: Dict) -> Dict[str, Any]:
        """Analyze liquidity characteristics for different volume tiers"""
        try:
            avg_spot_volume = spread_metrics.get('avg_spot_volume', 0)
            avg_futures_volume = spread_metrics.get('avg_futures_volume', 0)
            
            # Convert to hourly volume estimates (assuming 5-min candles)
            hourly_spot_volume = avg_spot_volume * 12  # 12 x 5-min periods per hour
            hourly_futures_volume = avg_futures_volume * 12
            
            # Liquidity tier classification
            if hourly_futures_volume < 50000:  # <50k/hour
                liquidity_tier = "ULTRA_LOW"
                risk_multiplier = 2.0
                offset_multiplier = 1.5
            elif hourly_futures_volume < 100000:  # 50k-100k/hour
                liquidity_tier = "LOW"
                risk_multiplier = 1.5
                offset_multiplier = 1.3
            elif hourly_futures_volume < 500000:  # 100k-500k/hour
                liquidity_tier = "MEDIUM"
                risk_multiplier = 1.0
                offset_multiplier = 1.0
            else:  # >500k/hour
                liquidity_tier = "HIGH"
                risk_multiplier = 0.8
                offset_multiplier = 0.8
            
            # Volume imbalance analysis
            volume_ratio = spread_metrics.get('volume_ratio', 1.0)
            volume_imbalance = abs(1.0 - volume_ratio)
            
            # Liquidity risk assessment
            liquidity_risks = []
            if hourly_futures_volume < 25000:  # Very low liquidity
                liquidity_risks.append("Extreme low futures liquidity")
            if volume_imbalance > 5.0:  # >5x imbalance
                liquidity_risks.append("Severe volume imbalance")
            if hourly_spot_volume < 10000:  # Very low spot volume
                liquidity_risks.append("Ultra-low spot liquidity")
            
            return {
                'hourly_spot_volume': hourly_spot_volume,
                'hourly_futures_volume': hourly_futures_volume,
                'liquidity_tier': liquidity_tier,
                'risk_multiplier': risk_multiplier,
                'offset_multiplier': offset_multiplier,
                'volume_imbalance': volume_imbalance,
                'liquidity_risks': liquidity_risks,
                'is_ultra_low_liquidity': hourly_futures_volume < 50000,
                'is_low_liquidity': hourly_futures_volume < 100000
            }
        except Exception as e:
            self.logger.error(f"Error calculating liquidity metrics: {e}")
            return {'liquidity_tier': 'UNKNOWN', 'risk_multiplier': 1.0, 'offset_multiplier': 1.0}

    def should_enter_position(self, volatility_metrics: Dict, spread_metrics: Dict, regime_metrics: Dict) -> Dict[str, Any]:
        """Decision framework for position entry with flexible liquidity handling"""
        try:
            should_enter = True
            reasons = []
            warnings = []
            
            # Calculate liquidity characteristics
            liquidity_metrics = self.calculate_liquidity_metrics(spread_metrics)
            
            # Check trend strength
            trend_strength = regime_metrics.get('trend_strength', 0)
            if trend_strength > 0.05:  # 5% trend
                should_enter = False
                reasons.append(f"Strong trend detected ({trend_strength:.2%})")
            
            # Require minimum correlation
            correlation = spread_metrics.get('correlation', 0)
            if correlation < 0.7:
                should_enter = False
                reasons.append(f"Low correlation ({correlation:.3f})")
            
            # Flexible volume validation based on strategy focus
            hourly_futures_volume = liquidity_metrics.get('hourly_futures_volume', 0)
            liquidity_tier = liquidity_metrics.get('liquidity_tier', 'UNKNOWN')
            
            # Only block extremely low liquidity (not low liquidity as you want to trade it)
            if hourly_futures_volume < 5000:  # <5k/hour - truly dangerous
                should_enter = False
                reasons.append(f"Extremely dangerous liquidity ({hourly_futures_volume:.0f}/hour)")
            elif hourly_futures_volume < 25000:  # 5k-25k/hour - high risk but tradeable
                warnings.append(f"Ultra-low liquidity tier ({hourly_futures_volume:.0f}/hour)")
            elif hourly_futures_volume < 100000:  # 25k-100k/hour - your target range
                warnings.append(f"Low liquidity tier ({hourly_futures_volume:.0f}/hour) - TARGET RANGE")
            
            # Check basis volatility with liquidity adjustment
            avg_price = spread_metrics.get('avg_price', 1)
            basis_volatility = spread_metrics.get('basis_volatility', 0)
            # More permissive for low liquidity pairs
            basis_threshold = 0.15 if liquidity_tier in ['ULTRA_LOW', 'LOW'] else 0.1
            if basis_volatility > avg_price * basis_threshold:
                should_enter = False
                reasons.append(f"Excessive basis volatility ({basis_volatility/avg_price:.2%})")
            
            # Check spike frequency (opportunity indicator)
            spike_frequency = volatility_metrics.get('spike_frequency', 0)
            if spike_frequency < 0.005:  # Less than 0.5% spike frequency (more lenient)
                warnings.append(f"Very low spike frequency ({spike_frequency:.1%})")
            elif spike_frequency < 0.01:  # Less than 1% spike frequency
                warnings.append(f"Low spike frequency ({spike_frequency:.1%})")
            
            # Check volatility ratio (more lenient for low liquidity)
            volatility_ratio = volatility_metrics.get('volatility_ratio', 1)
            min_vol_ratio = 1.1 if liquidity_tier in ['ULTRA_LOW', 'LOW'] else 1.2
            if volatility_ratio < min_vol_ratio:
                warnings.append(f"Low volatility advantage ({volatility_ratio:.2f})")
            
            # Check RSI for extreme conditions
            rsi = regime_metrics.get('rsi', 50)
            if rsi < 15 or rsi > 85:  # More extreme thresholds for low liquidity
                warnings.append(f"Extreme RSI condition ({rsi:.1f})")
            
            # Add liquidity-specific warnings
            for risk in liquidity_metrics.get('liquidity_risks', []):
                warnings.append(risk)
            
            # Determine risk level with liquidity consideration
            base_risk_factors = len(reasons)
            liquidity_risk_bonus = 1 if liquidity_tier == 'ULTRA_LOW' else 0
            warning_factors = len(warnings)
            
            if base_risk_factors > 1:
                risk_level = 'HIGH'
            elif base_risk_factors > 0 or liquidity_risk_bonus > 0:
                risk_level = 'MEDIUM'
            elif warning_factors > 2:
                risk_level = 'MEDIUM'
            else:
                risk_level = 'LOW'
            
            return {
                'should_enter': should_enter,
                'reasons': reasons,
                'warnings': warnings,
                'risk_level': risk_level,
                'liquidity_metrics': liquidity_metrics
            }
        except Exception as e:
            self.logger.error(f"Error in position entry decision: {e}")
            return {'should_enter': False, 'reasons': ['Analysis error'], 'warnings': [], 'risk_level': 'HIGH'}

    async def quick_screening(self, symbol: Symbol, date_to: Optional[datetime]=None, hours: int = 24) -> Optional[Dict]:
        """
        Enhanced quick screening for spot-futures arbitrage opportunities.
        
        Args:
            symbol: symbol to analyze
            date_to: Optional end date for data loading
            hours: Hours of historical data to analyze
        """
        try:
            if date_to is None:
                date_to = datetime.now(UTC)
                
            date_from = date_to - timedelta(hours=hours)
            
            # Load candles for both exchanges
            candles = await self.get_candles(
                [self.spot_ex, self.futures_ex],
                symbol, 
                KlineInterval.MINUTE_5,
                date_from, 
                date_to
            )

            spot_df = candles.get(self.spot_ex)
            futures_df = candles.get(self.futures_ex)
            
            if spot_df is None or futures_df is None or spot_df.empty or futures_df.empty:
                self.logger.warning(f"No data for {symbol} on {self.spot_ex}/{self.futures_ex}")
                return None

            # Merge dataframes on timestamp
            df = self._merge_candle_data(spot_df, futures_df, self.spot_ex, self.futures_ex)
            
            if len(df) < 20:  # Need minimum data points
                self.logger.warning(f"Insufficient data points for {symbol}: {len(df)}")
                return None
            
            # Calculate comprehensive metrics
            volatility_metrics = self.calculate_volatility_metrics(df)
            spread_metrics = self.calculate_spread_metrics(df)
            regime_metrics = self.detect_market_regime(df)
            
            # Calculate optimal parameters
            offset_params = self.calculate_optimal_offset(volatility_metrics, spread_metrics, regime_metrics)
            
            # Entry decision analysis
            entry_analysis = self.should_enter_position(volatility_metrics, spread_metrics, regime_metrics)
            
            # Calculate overall candidate score
            candidate_score = self._calculate_candidate_score(volatility_metrics, spread_metrics, regime_metrics, offset_params)
            
            # Generate trading recommendation
            recommendation = self._generate_recommendation(candidate_score, entry_analysis, offset_params)
            
            result = {
                'symbol': symbol,
                'timestamp': date_to,
                'data_points': len(df),
                'score': candidate_score,
                'volatility_metrics': volatility_metrics,
                'spread_metrics': spread_metrics,
                'regime_metrics': regime_metrics,
                'offset_params': offset_params,
                'entry_analysis': entry_analysis,
                'recommendation': recommendation
            }
            
            self.logger.info(f"✅ Screened {symbol}: Score={candidate_score:.2f}, Entry={entry_analysis['should_enter']}")
            return result

        except Exception as e:
            self.logger.warning(f"Failed quick screening for {symbol}: {e}")
            return None

    def _merge_candle_data(self, spot_df: pd.DataFrame, futures_df: pd.DataFrame, 
                          spot_ex: ExchangeEnum, futures_ex: ExchangeEnum) -> pd.DataFrame:
        """Merge spot and futures candle data with proper naming."""
        # Rename columns to avoid conflicts
        spot_df = spot_df.copy()
        futures_df = futures_df.copy()
        
        spot_cols = {
            'open': f'{spot_ex.value}_open',
            'high': f'{spot_ex.value}_high',
            'low': f'{spot_ex.value}_low',
            'close': f'{spot_ex.value}_close',
            'volume': f'{spot_ex.value}_volume'
        }
        
        futures_cols = {
            'open': f'{futures_ex.value}_open',
            'high': f'{futures_ex.value}_high',
            'low': f'{futures_ex.value}_low',
            'close': f'{futures_ex.value}_close',
            'volume': f'{futures_ex.value}_volume'
        }
        
        spot_df.rename(columns=spot_cols, inplace=True)
        futures_df.rename(columns=futures_cols, inplace=True)
        
        # Merge on timestamp
        df = pd.merge(spot_df, futures_df, on='timestamp', how='inner')
        df.sort_values('timestamp', inplace=True)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        df.reset_index(drop=True, inplace=True)
        
        return df

    def _calculate_candidate_score(self, volatility_metrics: Dict, spread_metrics: Dict, 
                                  regime_metrics: Dict, offset_params: Dict) -> float:
        """Calculate overall candidate score (0-10, higher = better opportunity)"""
        try:
            score = 0.0
            max_score = 10.0
            
            # Get liquidity characteristics
            liquidity_tier = offset_params.get('liquidity_tier', 'MEDIUM')
            
            # Volatility advantage (0-2.5 points) - more lenient for low liquidity
            volatility_ratio = volatility_metrics.get('volatility_ratio', 1.0)
            if volatility_ratio > 2.0:
                score += 2.5
            elif volatility_ratio > 1.5:
                score += 2.0
            elif volatility_ratio > 1.2:
                score += 1.5
            elif volatility_ratio > 1.1:  # More lenient threshold
                score += 1.0
            elif volatility_ratio > 1.0:
                score += 0.5
            
            # Correlation quality (0-2 points)
            correlation = spread_metrics.get('correlation', 0)
            if correlation > 0.9:
                score += 2.0
            elif correlation > 0.8:
                score += 1.5
            elif correlation > 0.7:
                score += 1.0
            elif correlation > 0.6:
                score += 0.5
            
            # Liquidity tier scoring (0-2 points) - reward target range
            if liquidity_tier == 'LOW':  # Your target range (25k-100k/hour)
                score += 2.0  # Bonus for target liquidity tier
            elif liquidity_tier == 'ULTRA_LOW':  # <50k/hour
                score += 1.5  # Still valuable but higher risk
            elif liquidity_tier == 'MEDIUM':  # 100k-500k/hour
                score += 1.0  # Standard scoring
            else:  # HIGH liquidity >500k/hour
                score += 0.5  # Lower opportunity in high liquidity
            
            # Spike frequency (opportunity indicator) (0-1.5 points) - more lenient
            spike_frequency = volatility_metrics.get('spike_frequency', 0)
            if spike_frequency > 0.05:  # >5% spike frequency
                score += 1.5
            elif spike_frequency > 0.03:  # >3% spike frequency
                score += 1.0
            elif spike_frequency > 0.01:  # >1% spike frequency
                score += 0.7
            elif spike_frequency > 0.005:  # >0.5% spike frequency (more lenient)
                score += 0.3
            
            # Market regime bonus/penalty (0-1.5 points)
            if regime_metrics.get('is_mean_reverting', False):
                score += 1.5  # Ideal for market making
            elif regime_metrics.get('is_trending', False):
                score -= 1.0  # Penalty for trending markets
            elif regime_metrics.get('is_high_volatility', False):
                score += 0.5  # Some bonus for volatility opportunities
            
            # Spread efficiency (0-1 point) - more generous for low liquidity
            price_diff_pct = spread_metrics.get('price_diff_pct', 0)
            min_spread_threshold = 0.5 if liquidity_tier in ['ULTRA_LOW', 'LOW'] else 1.0
            if price_diff_pct > min_spread_threshold * 2:
                score += 1.0
            elif price_diff_pct > min_spread_threshold:
                score += 0.5
            
            # Low liquidity bonus (0-0.5 points) - reward your target market
            if liquidity_tier in ['LOW', 'ULTRA_LOW']:
                avg_hl_ratio_diff = volatility_metrics.get('hl_ratio_difference', 0)
                if avg_hl_ratio_diff > 0.005:  # Spot more volatile intraday
                    score += 0.5  # Bonus for good intraday volatility difference
            
            # Risk penalty - less harsh for low liquidity since that's the target
            risk_score = offset_params.get('risk_score', 0.5)
            risk_penalty = 0.2 if liquidity_tier in ['LOW', 'ULTRA_LOW'] else 0.3
            score *= (1.0 - risk_score * risk_penalty)
            
            return min(max_score, max(0.0, score))
        except Exception as e:
            self.logger.error(f"Error calculating candidate score: {e}")
            return 0.0

    def _generate_recommendation(self, candidate_score: float, entry_analysis: Dict, offset_params: Dict) -> Dict[str, Any]:
        """Generate comprehensive trading recommendation"""
        try:
            # Determine overall recommendation
            if not entry_analysis.get('should_enter', False):
                overall_rec = "AVOID"
                confidence = "HIGH"
            elif candidate_score >= 7.0:
                overall_rec = "STRONG BUY"
                confidence = "HIGH"
            elif candidate_score >= 5.0:
                overall_rec = "BUY"
                confidence = "MEDIUM"
            elif candidate_score >= 3.0:
                overall_rec = "WEAK BUY"
                confidence = "LOW"
            else:
                overall_rec = "AVOID"
                confidence = "MEDIUM"
            
            # Generate specific trading parameters
            optimal_offset = offset_params.get('optimal_offset_ticks', 2)
            position_size = offset_params.get('position_size_factor', 0.5)
            
            # Risk management parameters
            risk_level = entry_analysis.get('risk_level', 'MEDIUM')
            
            # Generate action items
            action_items = []
            if overall_rec in ["STRONG BUY", "BUY"]:
                action_items.extend([
                    f"Place limit orders {optimal_offset:.1f} ticks from best bid/ask",
                    f"Use {position_size:.1%} of normal position size",
                    "Monitor correlation closely during execution",
                    "Ensure futures hedge liquidity before entry"
                ])
            elif overall_rec == "WEAK BUY":
                action_items.extend([
                    "Consider small test position only",
                    f"Use conservative {optimal_offset*1.5:.1f} tick offset",
                    "Monitor for regime change",
                    "Reduce position size significantly"
                ])
            else:
                action_items.extend([
                    "Wait for better market conditions",
                    "Monitor for regime change to mean-reverting",
                    "Check for correlation improvement"
                ])
            
            return {
                'overall_recommendation': overall_rec,
                'confidence': confidence,
                'score': candidate_score,
                'optimal_offset_ticks': optimal_offset,
                'position_size_factor': position_size,
                'risk_level': risk_level,
                'action_items': action_items,
                'warnings': entry_analysis.get('warnings', []),
                'blocking_reasons': entry_analysis.get('reasons', [])
            }
        except Exception as e:
            self.logger.error(f"Error generating recommendation: {e}")
            return {
                'overall_recommendation': 'ERROR',
                'confidence': 'LOW',
                'score': 0.0,
                'action_items': ['Analysis failed - manual review required']
            }

    async def pick_candidates(self, date_to: datetime, hours: int = 24) -> List[Dict]:
        """Stage 1: Screen all common symbols and identify candidates."""
        self.logger.info("🔍 Stage 1: Picking candidates...")
        
        # Get all tradable exchanges for arbitrage by symbol
        tradable_pairs = await self.get_tradable_pairs()
        self.logger.info(f"Found {len(tradable_pairs)} tradable pairs...")
        
        # Process symbols with concurrency limit
        semaphore = asyncio.Semaphore(5)  # Limit concurrent processing
        
        async def process_symbol(pair):
            async with semaphore:
                return await self.quick_screening(pair, date_to, hours)
        
        # Process all symbols in parallel
        tasks = [process_symbol(pair) for pair in tradable_pairs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter and sort candidates
        candidates = []
        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"Error processing symbol: {result}")
                continue
            if result is not None:
                candidates.append(result)
        
        # Sort by score (highest first)
        candidates.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        self.logger.info(f"📊 Found {len(candidates)} viable candidates")
        return candidates

    def save_results(self, candidates: List[Dict], analysis_summary: Dict):
        """Save analysis results to files"""
        try:
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            
            # Save detailed candidate analysis
            candidates_file = self.output_dir / f"candidates_{timestamp}.json"
            with open(candidates_file, 'w') as f:
                json.dump({
                    'analysis_timestamp': timestamp,
                    'analysis_summary': analysis_summary,
                    'candidates': candidates
                }, f, indent=2, default=str)
            
            # Save summary CSV for quick review
            if candidates:
                summary_data = []
                for candidate in candidates:
                    liquidity_metrics = candidate['entry_analysis'].get('liquidity_metrics', {})
                    summary_data.append({
                        'symbol': str(candidate['symbol']),
                        'score': candidate['score'],
                        'recommendation': candidate['recommendation']['overall_recommendation'],
                        'confidence': candidate['recommendation']['confidence'],
                        'risk_level': candidate['recommendation']['risk_level'],
                        'liquidity_tier': candidate['offset_params'].get('liquidity_tier', 'UNKNOWN'),
                        'hourly_futures_volume': liquidity_metrics.get('hourly_futures_volume', 0),
                        'correlation': candidate['spread_metrics']['correlation'],
                        'volatility_ratio': candidate['volatility_metrics']['volatility_ratio'],
                        'spike_frequency': candidate['volatility_metrics']['spike_frequency'],
                        'optimal_offset_ticks': candidate['offset_params']['optimal_offset_ticks'],
                        'position_size_factor': candidate['offset_params']['position_size_factor'],
                        'should_enter': candidate['entry_analysis']['should_enter']
                    })
                
                summary_df = pd.DataFrame(summary_data)
                summary_file = self.output_dir / f"summary_{timestamp}.csv"
                summary_df.to_csv(summary_file, index=False)
                
                self.logger.info(f"💾 Results saved to {candidates_file} and {summary_file}")
        except Exception as e:
            self.logger.error(f"Error saving results: {e}")

    def print_analysis_summary(self, candidates: List[Dict]):
        """Print comprehensive analysis summary"""
        if not candidates:
            print("❌ No candidates found")
            return
        
        print(f"\n🎯 MARKET MAKING CANDIDATE ANALYSIS SUMMARY")
        print("=" * 80)
        
        # Overall statistics
        total_candidates = len(candidates)
        strong_buys = len([c for c in candidates if c['recommendation']['overall_recommendation'] == 'STRONG BUY'])
        buys = len([c for c in candidates if c['recommendation']['overall_recommendation'] == 'BUY'])
        tradeable = len([c for c in candidates if c['entry_analysis']['should_enter']])
        
        print(f"📊 Total Candidates: {total_candidates}")
        print(f"🚀 Strong Buy: {strong_buys}")
        print(f"📈 Buy: {buys}")
        print(f"✅ Tradeable (passed entry criteria): {tradeable}")
        print(f"📉 Success Rate: {(strong_buys + buys)/total_candidates:.1%}")
        
        # Top candidates
        print(f"\n🏆 TOP 10 CANDIDATES")
        print("-" * 95)
        print(f"{'Symbol':<15} {'Score':<8} {'Rec':<12} {'Risk':<8} {'Liquidity':<12} {'Vol/hr':<8} {'Corr':<8} {'VolRatio':<9} {'Offset':<8}")
        print("-" * 95)
        
        for candidate in candidates[:10]:
            symbol = str(candidate['symbol'])[:14]
            score = f"{candidate['score']:.2f}"
            rec = candidate['recommendation']['overall_recommendation'][:11]
            risk = candidate['recommendation']['risk_level']
            liquidity_tier = candidate['offset_params'].get('liquidity_tier', 'UNKNOWN')[:11]
            
            # Get hourly volume
            liquidity_metrics = candidate['entry_analysis'].get('liquidity_metrics', {})
            hourly_vol = liquidity_metrics.get('hourly_futures_volume', 0)
            if hourly_vol >= 1000000:
                vol_display = f"{hourly_vol/1000000:.1f}M"
            elif hourly_vol >= 1000:
                vol_display = f"{hourly_vol/1000:.0f}k"
            else:
                vol_display = f"{hourly_vol:.0f}"
            
            corr = f"{candidate['spread_metrics']['correlation']:.3f}"
            vol_ratio = f"{candidate['volatility_metrics']['volatility_ratio']:.2f}"
            offset = f"{candidate['offset_params']['optimal_offset_ticks']:.1f}"
            
            print(f"{symbol:<15} {score:<8} {rec:<12} {risk:<8} {liquidity_tier:<12} {vol_display:<8} {corr:<8} {vol_ratio:<9} {offset:<8}")
        
        # Risk analysis
        print(f"\n⚠️  RISK ANALYSIS")
        print("-" * 40)
        high_risk = len([c for c in candidates if c['recommendation']['risk_level'] == 'HIGH'])
        medium_risk = len([c for c in candidates if c['recommendation']['risk_level'] == 'MEDIUM'])
        low_risk = len([c for c in candidates if c['recommendation']['risk_level'] == 'LOW'])
        
        print(f"🔴 High Risk: {high_risk} ({high_risk/total_candidates:.1%})")
        print(f"🟡 Medium Risk: {medium_risk} ({medium_risk/total_candidates:.1%})")
        print(f"🟢 Low Risk: {low_risk} ({low_risk/total_candidates:.1%})")
        
        # Liquidity analysis
        print(f"\n💧 LIQUIDITY ANALYSIS")
        print("-" * 40)
        ultra_low = len([c for c in candidates if c['offset_params'].get('liquidity_tier') == 'ULTRA_LOW'])
        low = len([c for c in candidates if c['offset_params'].get('liquidity_tier') == 'LOW'])
        medium = len([c for c in candidates if c['offset_params'].get('liquidity_tier') == 'MEDIUM'])
        high = len([c for c in candidates if c['offset_params'].get('liquidity_tier') == 'HIGH'])
        
        print(f"🟣 Ultra-Low (<50k/hr): {ultra_low} ({ultra_low/total_candidates:.1%})")
        print(f"🔵 Low (50k-100k/hr): {low} ({low/total_candidates:.1%}) - TARGET RANGE")
        print(f"🟡 Medium (100k-500k/hr): {medium} ({medium/total_candidates:.1%})")
        print(f"🟢 High (>500k/hr): {high} ({high/total_candidates:.1%})")
        
        # Target range opportunities
        target_opportunities = low + ultra_low
        print(f"🎯 Target Low-Liquidity Opportunities: {target_opportunities} ({target_opportunities/total_candidates:.1%})")
        
        # Common blocking reasons
        all_reasons = []
        for candidate in candidates:
            if not candidate['entry_analysis']['should_enter']:
                all_reasons.extend(candidate['entry_analysis']['reasons'])
        
        if all_reasons:
            from collections import Counter
            reason_counts = Counter(all_reasons)
            print(f"\n🚫 COMMON BLOCKING REASONS")
            print("-" * 40)
            for reason, count in reason_counts.most_common(5):
                print(f"• {reason}: {count} times")

    async def analyze(self, date_to: datetime, hours: int, max_backtests: int = 10):
        """Complete analysis pipeline with comprehensive reporting."""
        try:
            start_time = datetime.now(UTC)
            self.logger.info(f"🚀 Starting analysis at {start_time}")
            
            # Stage 1: Pick candidates
            candidates = await self.pick_candidates(date_to, hours)
            
            if not candidates:
                self.logger.warning("No candidates found during screening")
                return
            
            # Create analysis summary
            analysis_summary = {
                'analysis_start': start_time,
                'analysis_end': datetime.now(UTC),
                'spot_exchange': self.spot_ex.value,
                'futures_exchange': self.futures_ex.value,
                'date_range': {
                    'from': date_to - timedelta(hours=hours),
                    'to': date_to
                },
                'total_candidates': len(candidates),
                'strong_buy_count': len([c for c in candidates if c['recommendation']['overall_recommendation'] == 'STRONG BUY']),
                'buy_count': len([c for c in candidates if c['recommendation']['overall_recommendation'] == 'BUY']),
                'tradeable_count': len([c for c in candidates if c['entry_analysis']['should_enter']]),
                'avg_score': sum(c['score'] for c in candidates) / len(candidates),
                'avg_correlation': sum(c['spread_metrics']['correlation'] for c in candidates) / len(candidates),
                'avg_volatility_ratio': sum(c['volatility_metrics']['volatility_ratio'] for c in candidates) / len(candidates)
            }
            
            # Print analysis summary
            self.print_analysis_summary(candidates)
            
            # Save results
            self.save_results(candidates, analysis_summary)
            
            self.logger.info(f"✅ Analysis completed in {(datetime.now(UTC) - start_time).total_seconds():.1f}s")
            return candidates, analysis_summary

        except Exception as e:
            self.logger.error(f"Analysis failed: {e}")
            raise
    


if __name__ == "__main__":
    async def main():
        """Example usage of the enhanced analyzer."""
        analyzer = MakerOrderCandidateAnalyzer(
            spot_ex=ExchangeEnum.MEXC,
            futures_ex=ExchangeEnum.GATEIO_FUTURES,
            output_dir="../arbitrage_results"
        )
        
        # end_time = datetime.now(UTC)
        hours = 24

        end_time = datetime.fromisoformat("2025-10-30 03:00:00+00:00")
        start_time = end_time - pd.Timedelta(hours=hours)

        print("🚀 Starting Arbitrage Candidate Analysis")
        print(f"📅 Analysis Period: {start_time} to {end_time}")

        await analyzer.analyze(end_time, hours, max_backtests=50)
        
        print("\n✅ Analysis completed successfully!")
    
    asyncio.run(main())

