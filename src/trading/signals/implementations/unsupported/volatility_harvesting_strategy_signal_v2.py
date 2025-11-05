"""
Volatility Harvesting Strategy Signal V2

Enhanced volatility harvesting strategy that matches 1-to-1 with trading logic
from arbitrage_analyzer.py, incorporating cross-exchange opportunity detection,
safe offset calculation, and execution confidence scoring.

This implementation combines volatility analysis with the exact arbitrage
detection logic to capture profits from volatile cross-exchange spreads.
"""

from typing import Dict, Any, Tuple, Union, Optional
import pandas as pd
import numpy as np
from datetime import datetime
from dataclasses import dataclass

from trading.strategies.base.base_strategy_signal import BaseStrategySignal
from trading.signals.types.signal_types import Signal


@dataclass
class VolatilityOpportunity:
    """Volatility-based arbitrage opportunity matching CrossExchangeOpportunity logic."""
    opportunity_type: str
    sell_exchange: str
    buy_exchange: str
    sell_price: float
    buy_price: float
    spread_bps: float
    expected_profit_bps: float
    execution_confidence: float
    volatility_score: float
    timestamp: datetime


@dataclass
class VolatilityMetrics:
    """Volatility analysis metrics matching SafeOffsetCalculator patterns."""
    current_volatility: float
    volatility_percentile: float
    rolling_volatility: float
    volatility_z_score: float
    safe_offset: float
    mean_reversion_strength: float
    momentum_score: float


class VolatilityHarvestingStrategySignalV2(BaseStrategySignal):
    """
    Volatility harvesting strategy V2 implementation matching arbitrage_analyzer.py logic.
    
    Strategy Logic (matching CrossExchangeArbitrageAnalyzer):
    - ENTER: High volatility periods with profitable cross-exchange opportunities
    - EXIT: Volatility subsides or profit targets reached
    - Uses same opportunity detection and safe offset calculation as arbitrage analyzer
    """
    
    def __init__(self, 
                 strategy_type: str = 'volatility_harvesting_v2',
                 volatility_threshold: float = 2.0,
                 min_profit_bps: float = 20.0,
                 min_execution_confidence: float = 0.6,
                 volatility_window: int = 50,
                 safe_offset_percentile: float = 75.0,
                 **params):
        """
        Initialize volatility harvesting strategy V2.
        
        Args:
            strategy_type: Strategy identifier
            volatility_threshold: Volatility z-score threshold for entry
            min_profit_bps: Minimum profit in basis points (matching analyzer)
            min_execution_confidence: Minimum execution confidence (matching analyzer)
            volatility_window: Window for volatility calculations
            safe_offset_percentile: Percentile for safe offset calculation
            **params: Additional parameters passed to base class
        """
        self.volatility_threshold = volatility_threshold
        self.min_profit_bps = min_profit_bps
        self.min_execution_confidence = min_execution_confidence
        self.volatility_window = volatility_window
        self.safe_offset_percentile = safe_offset_percentile
        
        super().__init__(
            strategy_type=strategy_type,
            volatility_threshold=volatility_threshold,
            min_profit_bps=min_profit_bps,
            min_execution_confidence=min_execution_confidence,
            volatility_window=volatility_window,
            safe_offset_percentile=safe_offset_percentile,
            **params
        )
        
        # Historical data for safe offset calculation (matching SafeOffsetCalculator)
        self.historical_spreads = []
        self.historical_volatility = []
        self.execution_history = []
        
        # Current state tracking
        self.current_volatility_metrics: Optional[VolatilityMetrics] = None
        self.last_opportunity: Optional[VolatilityOpportunity] = None
    
    def generate_live_signal(self, market_data: Dict[str, Any], **params) -> Tuple[Signal, float]:
        """
        Generate live trading signal for volatility harvesting strategy V2.
        
        Uses the same opportunity detection logic as CrossExchangeArbitrageAnalyzer
        combined with volatility analysis for enhanced timing.
        
        Args:
            market_data: Current market data snapshot
            **params: Override parameters
            
        Returns:
            Tuple of (Signal, confidence_score)
        """
        # Validate market data
        if not self.validate_market_data(market_data):
            return Signal.HOLD, 0.0
        
        # Extract prices - handle both DataFrame column names and manual data
        mexc_bid = market_data.get('mexc_bid', market_data.get('MEXC_SPOT_bid_price', 0))
        mexc_ask = market_data.get('mexc_ask', market_data.get('MEXC_SPOT_ask_price', 0))
        gateio_spot_bid = market_data.get('gateio_spot_bid', market_data.get('gateio_bid', market_data.get('GATEIO_SPOT_bid_price', 0)))
        gateio_spot_ask = market_data.get('gateio_spot_ask', market_data.get('gateio_ask', market_data.get('GATEIO_SPOT_ask_price', 0)))
        gateio_futures_bid = market_data.get('gateio_futures_bid', market_data.get('GATEIO_FUTURES_bid_price', 0))
        gateio_futures_ask = market_data.get('gateio_futures_ask', market_data.get('GATEIO_FUTURES_ask_price', 0))
        
        if not all([mexc_bid, mexc_ask, gateio_futures_bid, gateio_futures_ask]):
            return Signal.HOLD, 0.0
        
        # Calculate spreads for volatility analysis
        spreads = self._calculate_spread_from_market_data(market_data)
        
        # Update historical data and calculate volatility metrics
        self._update_historical_data(spreads)
        volatility_metrics = self._calculate_volatility_metrics(spreads)
        
        if not volatility_metrics:
            return Signal.HOLD, 0.0
        
        self.current_volatility_metrics = volatility_metrics
        
        # Check if we have enough history
        if len(self.historical_spreads) < self.min_history:
            return Signal.HOLD, 0.0
        
        # Override parameters
        vol_thresh = params.get('volatility_threshold', self.volatility_threshold)
        min_profit = params.get('min_profit_bps', self.min_profit_bps)
        min_confidence = params.get('min_execution_confidence', self.min_execution_confidence)
        
        # Detect cross-exchange opportunities using arbitrage analyzer logic
        opportunity = self._detect_volatility_arbitrage_opportunity(
            mexc_bid, mexc_ask, gateio_futures_bid, gateio_futures_ask,
            volatility_metrics, min_profit
        )
        
        if opportunity:
            self.last_opportunity = opportunity
            
            # Generate signal based on volatility and opportunity quality
            signal = self._generate_volatility_arbitrage_signal(
                opportunity, volatility_metrics, vol_thresh, min_confidence
            )
            
            # Calculate confidence using arbitrage analyzer patterns
            confidence = self._calculate_execution_confidence(opportunity, volatility_metrics)
        else:
            signal = Signal.HOLD
            confidence = 0.0
        
        # Update tracking
        self.last_signal = signal
        self.last_signal_time = datetime.now()
        self.signal_count += 1
        
        return signal, confidence
    
    def apply_signal_to_backtest(self, df: pd.DataFrame, **params) -> pd.DataFrame:
        """
        Apply strategy signals to historical data for backtesting.
        
        Uses vectorized implementation of the arbitrage analyzer logic
        combined with volatility analysis.
        
        Args:
            df: Historical market data DataFrame with indicators
            **params: Override parameters
            
        Returns:
            DataFrame with added signal columns
        """
        # Ensure we have required spread columns
        if 'mexc_vs_gateio_futures_spread' not in df.columns:
            df = self._calculate_common_indicators(df)
        
        # Calculate volatility indicators (vectorized)
        df = self._calculate_volatility_indicators_vectorized(df)
        
        # Calculate safe offsets (vectorized version of SafeOffsetCalculator)
        df = self._calculate_safe_offsets_vectorized(df)
        
        # Detect opportunities (vectorized version of OpportunityDetector)
        df = self._detect_opportunities_vectorized(df, **params)
        
        # Override parameters
        vol_thresh = params.get('volatility_threshold', self.volatility_threshold)
        min_profit = params.get('min_profit_bps', self.min_profit_bps)
        min_confidence = params.get('min_execution_confidence', self.min_execution_confidence)
        
        # Initialize signal columns
        df['signal'] = Signal.HOLD.value
        df['confidence'] = 0.0
        
        # Vectorized signal generation matching arbitrage analyzer logic
        high_volatility = df['volatility_z_score'] > vol_thresh
        profitable_opportunity = df['expected_profit_bps'] > min_profit
        sufficient_confidence = df['execution_confidence'] > min_confidence
        volatility_opportunity = df['volatility_score'] > 0.5
        
        # Entry conditions (volatility + arbitrage opportunity)
        enter_condition = (
            high_volatility & 
            profitable_opportunity & 
            sufficient_confidence & 
            volatility_opportunity
        )
        
        # Exit conditions (volatility subsides or profit taken)
        exit_condition = (
            (df['volatility_z_score'] < vol_thresh * 0.5) |
            (df['profit_reached_bps'] > min_profit) |
            (df['execution_confidence'] < min_confidence * 0.7)
        )
        
        # Apply signals
        df.loc[enter_condition, 'signal'] = Signal.ENTER.value
        df.loc[exit_condition, 'signal'] = Signal.EXIT.value
        
        # Use execution confidence as signal confidence
        df['confidence'] = df['execution_confidence']
        
        return df
    
    def open_position(self, signal: Signal, market_data: Dict[str, Any], **params) -> Dict[str, Any]:
        """
        Calculate position opening details for volatility harvesting strategy V2.
        
        Uses the same position calculation logic as arbitrage analyzer with
        volatility-based position sizing.
        
        Args:
            signal: Trading signal (should be ENTER)
            market_data: Current market data
            **params: Position parameters
            
        Returns:
            Position details dictionary
        """
        if signal != Signal.ENTER or not self.last_opportunity:
            return {}
        
        opportunity = self.last_opportunity
        volatility_metrics = self.current_volatility_metrics
        position_size = params.get('position_size_usd', self.position_size_usd)
        
        # Volatility-based position sizing (matching analyzer risk management)
        volatility_multiplier = self._calculate_volatility_position_multiplier(volatility_metrics)
        adjusted_position_size = position_size * volatility_multiplier
        
        # Position details matching arbitrage analyzer patterns
        position = {
            'strategy_type': self.strategy_type,
            'signal': signal.value,
            'timestamp': datetime.now(),
            'position_size_usd': adjusted_position_size,
            'volatility_multiplier': volatility_multiplier,
            
            # Opportunity details (matching CrossExchangeOpportunity)
            'opportunity_type': opportunity.opportunity_type,
            'sell_exchange': opportunity.sell_exchange,
            'buy_exchange': opportunity.buy_exchange,
            'sell_price': opportunity.sell_price,
            'buy_price': opportunity.buy_price,
            'spread_bps': opportunity.spread_bps,
            'expected_profit_bps': opportunity.expected_profit_bps,
            'execution_confidence': opportunity.execution_confidence,
            'volatility_score': opportunity.volatility_score,
            
            # Entry prices for trade execution
            'mexc_entry_price': opportunity.sell_price if opportunity.sell_exchange == 'MEXC' else opportunity.buy_price,
            'gateio_futures_entry_price': opportunity.buy_price if opportunity.buy_exchange == 'GATEIO_FUTURES' else opportunity.sell_price,
            
            # Volatility metrics at entry
            'entry_volatility': volatility_metrics.current_volatility if volatility_metrics else 0,
            'volatility_z_score': volatility_metrics.volatility_z_score if volatility_metrics else 0,
            'safe_offset': volatility_metrics.safe_offset if volatility_metrics else 0,
            'mean_reversion_strength': volatility_metrics.mean_reversion_strength if volatility_metrics else 0,
            
            # Risk management (matching analyzer)
            'max_loss_bps': -200,  # 2% max loss
            'target_profit_bps': opportunity.expected_profit_bps,
            'stop_loss_confidence': 0.3,  # Exit if confidence drops below 30%
        }
        
        self.current_position = position
        return position
    
    def close_position(self, position: Dict[str, Any], market_data: Dict[str, Any], **params) -> Dict[str, Any]:
        """
        Calculate position closing details and P&L.
        
        Uses the same P&L calculation patterns as arbitrage analyzer.
        
        Args:
            position: Current position details
            market_data: Current market data
            **params: Exit parameters
            
        Returns:
            Trade closure details with P&L
        """
        # Extract current prices - handle both DataFrame column names and manual data
        mexc_bid = market_data.get('mexc_bid', market_data.get('MEXC_SPOT_bid_price', 0))
        mexc_ask = market_data.get('mexc_ask', market_data.get('MEXC_SPOT_ask_price', 0))
        gateio_futures_bid = market_data.get('gateio_futures_bid', market_data.get('GATEIO_FUTURES_bid_price', 0))
        gateio_futures_ask = market_data.get('gateio_futures_ask', market_data.get('GATEIO_FUTURES_ask_price', 0))
        
        if not all([mexc_bid, mexc_ask, gateio_futures_bid, gateio_futures_ask]):
            return {}
        
        # Determine exit prices based on original opportunity
        opportunity_type = position.get('opportunity_type', '')
        sell_exchange = position.get('sell_exchange', '')
        buy_exchange = position.get('buy_exchange', '')
        
        # Calculate exit prices (reverse of entry)
        if sell_exchange == 'MEXC' and buy_exchange == 'GATEIO_FUTURES':
            # Original: sell MEXC, buy GATEIO_FUTURES
            # Exit: buy MEXC, sell GATEIO_FUTURES
            mexc_exit_price = mexc_ask  # Buy at ask
            gateio_exit_price = gateio_futures_bid  # Sell at bid
        elif sell_exchange == 'GATEIO_FUTURES' and buy_exchange == 'MEXC':
            # Original: sell GATEIO_FUTURES, buy MEXC
            # Exit: buy GATEIO_FUTURES, sell MEXC
            mexc_exit_price = mexc_bid  # Sell at bid
            gateio_exit_price = gateio_futures_ask  # Buy at ask
        else:
            # Default to mid-prices if opportunity type unclear
            mexc_exit_price = (mexc_bid + mexc_ask) / 2
            gateio_exit_price = (gateio_futures_bid + gateio_futures_ask) / 2
        
        # Calculate P&L using arbitrage analyzer patterns
        mexc_entry = position['mexc_entry_price']
        gateio_entry = position['gateio_futures_entry_price']
        
        # P&L calculation matching arbitrage analyzer
        if sell_exchange == 'MEXC':
            # Sold MEXC at entry, buy back at exit
            mexc_pnl_per_unit = mexc_entry - mexc_exit_price
            # Bought GATEIO at entry, sell at exit
            gateio_pnl_per_unit = gateio_exit_price - gateio_entry
        else:
            # Bought MEXC at entry, sell at exit
            mexc_pnl_per_unit = mexc_exit_price - mexc_entry
            # Sold GATEIO at entry, buy back at exit
            gateio_pnl_per_unit = gateio_entry - gateio_exit_price
        
        # Total P&L per unit
        total_pnl_per_unit = mexc_pnl_per_unit + gateio_pnl_per_unit
        
        # Scale to position size
        position_size = position['position_size_usd']
        entry_price = mexc_entry
        units = position_size / entry_price if entry_price > 0 else 0
        
        total_pnl_usd = total_pnl_per_unit * units
        
        # Calculate fees (matching analyzer fee structure)
        fees_usd = position_size * self.total_fees
        net_pnl_usd = total_pnl_usd - fees_usd
        
        # Calculate current volatility for analysis
        spreads = self._calculate_spread_from_market_data(market_data)
        exit_volatility_metrics = self._calculate_volatility_metrics(spreads)
        
        trade_result = {
            'strategy_type': self.strategy_type,
            'entry_timestamp': position.get('timestamp'),
            'exit_timestamp': datetime.now(),
            'position_size_usd': position_size,
            'volatility_multiplier': position.get('volatility_multiplier', 1.0),
            
            # Opportunity details
            'opportunity_type': opportunity_type,
            'sell_exchange': sell_exchange,
            'buy_exchange': buy_exchange,
            'entry_spread_bps': position.get('spread_bps', 0),
            'expected_profit_bps': position.get('expected_profit_bps', 0),
            
            # Entry details
            'mexc_entry_price': mexc_entry,
            'gateio_futures_entry_price': gateio_entry,
            
            # Exit details
            'mexc_exit_price': mexc_exit_price,
            'gateio_futures_exit_price': gateio_exit_price,
            
            # P&L breakdown (matching analyzer structure)
            'mexc_pnl_per_unit': mexc_pnl_per_unit,
            'gateio_futures_pnl_per_unit': gateio_pnl_per_unit,
            'total_pnl_per_unit': total_pnl_per_unit,
            'total_pnl_usd': total_pnl_usd,
            'fees_usd': fees_usd,
            'net_pnl_usd': net_pnl_usd,
            'pnl_percentage': (net_pnl_usd / position_size) * 100 if position_size > 0 else 0,
            'realized_profit_bps': (net_pnl_usd / position_size) * 10000 if position_size > 0 else 0,
            
            # Volatility analysis
            'entry_volatility': position.get('entry_volatility', 0),
            'exit_volatility': exit_volatility_metrics.current_volatility if exit_volatility_metrics else 0,
            'entry_execution_confidence': position.get('execution_confidence', 0),
            'entry_volatility_score': position.get('volatility_score', 0),
        }
        
        self.current_position = None
        return trade_result
    
    # Private helper methods matching arbitrage analyzer patterns
    
    def _detect_volatility_arbitrage_opportunity(self, 
                                               mexc_bid: float, mexc_ask: float,
                                               gateio_futures_bid: float, gateio_futures_ask: float,
                                               volatility_metrics: VolatilityMetrics,
                                               min_profit_bps: float) -> Optional[VolatilityOpportunity]:
        """
        Detect volatility-based arbitrage opportunities using analyzer logic.
        
        This method matches the detect_market_market_opportunity logic from
        CrossExchangeArbitrageAnalyzer but includes volatility analysis.
        """
        if not volatility_metrics:
            return None
        
        safe_offset = volatility_metrics.safe_offset
        
        opportunities = []
        
        # Check GATEIO_FUTURES bid > MEXC ask (sell MEXC, buy GATEIO_FUTURES)
        if gateio_futures_bid > mexc_ask:
            spread_bps = ((gateio_futures_bid - mexc_ask) / mexc_ask) * 10000
            expected_profit = spread_bps - (safe_offset * 10000)
            
            if expected_profit > min_profit_bps:
                execution_confidence = self._calculate_opportunity_confidence(
                    spread_bps, safe_offset, volatility_metrics
                )
                
                volatility_score = self._calculate_volatility_score(volatility_metrics)
                
                opportunity = VolatilityOpportunity(
                    opportunity_type='market_market_volatility',
                    sell_exchange='MEXC',
                    buy_exchange='GATEIO_FUTURES',
                    sell_price=mexc_ask,
                    buy_price=gateio_futures_bid,
                    spread_bps=spread_bps,
                    expected_profit_bps=expected_profit,
                    execution_confidence=execution_confidence,
                    volatility_score=volatility_score,
                    timestamp=datetime.now()
                )
                opportunities.append(opportunity)
        
        # Check MEXC bid > GATEIO_FUTURES ask (sell GATEIO_FUTURES, buy MEXC)
        if mexc_bid > gateio_futures_ask:
            spread_bps = ((mexc_bid - gateio_futures_ask) / gateio_futures_ask) * 10000
            expected_profit = spread_bps - (safe_offset * 10000)
            
            if expected_profit > min_profit_bps:
                execution_confidence = self._calculate_opportunity_confidence(
                    spread_bps, safe_offset, volatility_metrics
                )
                
                volatility_score = self._calculate_volatility_score(volatility_metrics)
                
                opportunity = VolatilityOpportunity(
                    opportunity_type='market_market_volatility',
                    sell_exchange='GATEIO_FUTURES',
                    buy_exchange='MEXC',
                    sell_price=gateio_futures_ask,
                    buy_price=mexc_bid,
                    spread_bps=spread_bps,
                    expected_profit_bps=expected_profit,
                    execution_confidence=execution_confidence,
                    volatility_score=volatility_score,
                    timestamp=datetime.now()
                )
                opportunities.append(opportunity)
        
        # Return best opportunity (highest expected profit)
        if opportunities:
            return max(opportunities, key=lambda x: x.expected_profit_bps)
        
        return None
    
    def _calculate_volatility_metrics(self, spreads: Dict[str, float]) -> Optional[VolatilityMetrics]:
        """
        Calculate volatility metrics matching SafeOffsetCalculator patterns.
        """
        if not spreads or len(self.historical_spreads) < self.volatility_window:
            return None
        
        # Get main spread for analysis
        main_spread = spreads.get('mexc_vs_gateio_futures', 0)
        
        # Calculate current volatility
        recent_spreads = self.historical_spreads[-self.volatility_window:]
        current_volatility = np.std(recent_spreads)
        rolling_volatility = np.mean([np.std(self.historical_spreads[i:i+self.volatility_window]) 
                                    for i in range(max(0, len(self.historical_spreads)-100), 
                                                  len(self.historical_spreads)-self.volatility_window+1)])
        
        # Calculate volatility percentile (matching analyzer percentile logic)
        if len(self.historical_volatility) >= 50:
            volatility_percentile = (
                sum(v <= current_volatility for v in self.historical_volatility[-100:]) / 
                len(self.historical_volatility[-100:]) * 100
            )
        else:
            volatility_percentile = 50.0
        
        # Calculate volatility z-score
        if len(self.historical_volatility) >= 20:
            vol_mean = np.mean(self.historical_volatility[-50:])
            vol_std = np.std(self.historical_volatility[-50:])
            volatility_z_score = (current_volatility - vol_mean) / (vol_std + 1e-8)
        else:
            volatility_z_score = 0.0
        
        # Calculate safe offset (matching SafeOffsetCalculator logic)
        safe_offset = self._calculate_safe_offset(recent_spreads)
        
        # Calculate mean reversion strength
        mean_spread = np.mean(recent_spreads)
        spread_deviation = main_spread - mean_spread
        mean_reversion_strength = abs(spread_deviation) / (current_volatility + 1e-8)
        
        # Calculate momentum score
        if len(recent_spreads) >= 10:
            momentum_score = (recent_spreads[-1] - recent_spreads[-10]) / (current_volatility + 1e-8)
        else:
            momentum_score = 0.0
        
        return VolatilityMetrics(
            current_volatility=current_volatility,
            volatility_percentile=volatility_percentile,
            rolling_volatility=rolling_volatility,
            volatility_z_score=volatility_z_score,
            safe_offset=safe_offset,
            mean_reversion_strength=mean_reversion_strength,
            momentum_score=momentum_score
        )
    
    def _calculate_safe_offset(self, spreads: list) -> float:
        """
        Calculate safe offset using SafeOffsetCalculator logic.
        """
        if len(spreads) < 20:
            return 0.01  # Default 1% offset
        
        # Calculate various risk metrics (matching analyzer)
        volatility_risk = np.std(spreads)
        
        # Liquidity risk (simplified)
        liquidity_risk = np.mean([abs(s) for s in spreads[-10:]])
        
        # Timing risk (spread momentum)
        if len(spreads) >= 5:
            timing_risk = abs(spreads[-1] - spreads[-5]) / 5
        else:
            timing_risk = 0
        
        # Combined offset (matching analyzer percentile approach)
        risk_scores = [volatility_risk, liquidity_risk, timing_risk]
        percentile_offset = np.percentile(risk_scores, self.safe_offset_percentile)
        
        # Ensure minimum offset
        safe_offset = max(percentile_offset, 0.002)  # Minimum 0.2%
        
        return safe_offset
    
    def _calculate_opportunity_confidence(self, spread_bps: float, safe_offset: float, 
                                        volatility_metrics: VolatilityMetrics) -> float:
        """
        Calculate execution confidence matching arbitrage analyzer patterns.
        """
        # Base confidence from spread size
        base_confidence = min(spread_bps / 50.0, 1.0)  # 50 bps = 100% base confidence
        
        # Adjust for volatility (high volatility reduces confidence)
        volatility_adjustment = 1.0 - min(volatility_metrics.volatility_z_score / 5.0, 0.5)
        
        # Adjust for safe offset (larger offset reduces confidence)
        offset_adjustment = 1.0 - min(safe_offset * 100, 0.3)  # Max 30% reduction
        
        # Adjust for mean reversion (stronger mean reversion increases confidence)
        mean_reversion_adjustment = 1.0 + min(volatility_metrics.mean_reversion_strength / 10.0, 0.2)
        
        # Combined confidence
        confidence = base_confidence * volatility_adjustment * offset_adjustment * mean_reversion_adjustment
        
        return max(min(confidence, 1.0), 0.0)
    
    def _calculate_volatility_score(self, volatility_metrics: VolatilityMetrics) -> float:
        """
        Calculate volatility opportunity score.
        """
        # Higher volatility = higher opportunity score
        volatility_component = min(volatility_metrics.volatility_z_score / 3.0, 1.0)
        
        # High percentile volatility increases score
        percentile_component = volatility_metrics.volatility_percentile / 100.0
        
        # Strong mean reversion increases score
        mean_reversion_component = min(volatility_metrics.mean_reversion_strength / 5.0, 1.0)
        
        # Combined score
        score = (volatility_component * 0.4 + 
                percentile_component * 0.3 + 
                mean_reversion_component * 0.3)
        
        return max(min(score, 1.0), 0.0)
    
    def _calculate_volatility_position_multiplier(self, volatility_metrics: Optional[VolatilityMetrics]) -> float:
        """
        Calculate position size multiplier based on volatility.
        """
        if not volatility_metrics:
            return 1.0
        
        # Higher volatility = smaller position (risk management)
        volatility_factor = max(0.5, 1.0 - volatility_metrics.volatility_z_score / 10.0)
        
        # High confidence opportunities can have larger positions
        confidence_factor = 1.0 + (volatility_metrics.volatility_percentile - 50) / 100.0
        
        multiplier = volatility_factor * confidence_factor
        
        # Constrain to reasonable range
        return max(min(multiplier, 2.0), 0.3)
    
    def _update_historical_data(self, spreads: Dict[str, float]) -> None:
        """
        Update historical data for calculations.
        """
        main_spread = spreads.get('mexc_vs_gateio_futures', 0)
        
        # Update spread history
        self.historical_spreads.append(main_spread)
        if len(self.historical_spreads) > self.lookback_periods:
            self.historical_spreads.pop(0)
        
        # Update volatility history
        if len(self.historical_spreads) >= self.volatility_window:
            recent_volatility = np.std(self.historical_spreads[-self.volatility_window:])
            self.historical_volatility.append(recent_volatility)
            if len(self.historical_volatility) > self.lookback_periods:
                self.historical_volatility.pop(0)
    
    def _generate_volatility_arbitrage_signal(self, opportunity: VolatilityOpportunity,
                                            volatility_metrics: VolatilityMetrics,
                                            vol_thresh: float, min_confidence: float) -> Signal:
        """
        Generate signal based on opportunity and volatility conditions.
        """
        # Check volatility threshold
        if volatility_metrics.volatility_z_score <= vol_thresh:
            return Signal.HOLD
        
        # Check execution confidence
        if opportunity.execution_confidence < min_confidence:
            return Signal.HOLD
        
        # Check volatility score
        if opportunity.volatility_score < 0.4:
            return Signal.HOLD
        
        # All conditions met
        return Signal.ENTER
    
    def _calculate_execution_confidence(self, opportunity: VolatilityOpportunity, 
                                      volatility_metrics: Optional[VolatilityMetrics]) -> float:
        """
        Calculate overall execution confidence.
        """
        if not volatility_metrics:
            return opportunity.execution_confidence * 0.5
        
        # Combine opportunity confidence with volatility score
        combined_confidence = (opportunity.execution_confidence * 0.6 + 
                              opportunity.volatility_score * 0.4)
        
        return max(min(combined_confidence, 1.0), 0.0)
    
    # Vectorized methods for backtesting
    
    def _calculate_volatility_indicators_vectorized(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate volatility indicators for entire DataFrame.
        """
        # Ensure we have the spread column
        if 'mexc_vs_gateio_futures_spread' not in df.columns:
            df['mexc_vs_gateio_futures_spread'] = df['mexc_vs_gateio_futures']
        
        # Calculate rolling volatility
        vol_window = min(self.volatility_window, len(df))
        df['spread_volatility'] = df['mexc_vs_gateio_futures_spread'].rolling(window=vol_window).std()
        df['spread_mean'] = df['mexc_vs_gateio_futures_spread'].rolling(window=vol_window).mean()
        
        # Calculate volatility z-score
        lookback = min(self.lookback_periods, len(df))
        df['volatility_mean'] = df['spread_volatility'].rolling(window=lookback).mean()
        df['volatility_std'] = df['spread_volatility'].rolling(window=lookback).std()
        df['volatility_z_score'] = (
            (df['spread_volatility'] - df['volatility_mean']) / 
            (df['volatility_std'] + 1e-8)
        )
        
        # Calculate volatility percentile
        df['volatility_percentile'] = df['spread_volatility'].rolling(window=100).rank(pct=True) * 100
        
        # Calculate mean reversion strength
        df['spread_deviation'] = df['mexc_vs_gateio_futures_spread'] - df['spread_mean']
        df['mean_reversion_strength'] = (
            df['spread_deviation'].abs() / (df['spread_volatility'] + 1e-8)
        )
        
        return df
    
    def _calculate_safe_offsets_vectorized(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate safe offsets for entire DataFrame.
        """
        # Simple vectorized safe offset (could be enhanced)
        df['volatility_risk'] = df['spread_volatility']
        df['liquidity_risk'] = df['mexc_vs_gateio_futures_spread'].abs().rolling(window=10).mean()
        df['timing_risk'] = df['mexc_vs_gateio_futures_spread'].diff(5).abs() / 5
        
        # Calculate safe offset as percentile of risks
        df['safe_offset'] = df[['volatility_risk', 'liquidity_risk', 'timing_risk']].quantile(
            self.safe_offset_percentile / 100.0, axis=1
        ).clip(lower=0.002)  # Minimum 0.2%
        
        return df
    
    def _detect_opportunities_vectorized(self, df: pd.DataFrame, **params) -> pd.DataFrame:
        """
        Detect opportunities for entire DataFrame.
        """
        min_profit = params.get('min_profit_bps', self.min_profit_bps)
        
        # Calculate spreads in basis points
        mexc_gateio_spread = ((df['GATEIO_FUTURES_bid_price'] - df['MEXC_SPOT_ask_price']) / 
                             df['MEXC_SPOT_ask_price']) * 10000
        gateio_mexc_spread = ((df['MEXC_SPOT_bid_price'] - df['GATEIO_FUTURES_ask_price']) / 
                             df['GATEIO_FUTURES_ask_price']) * 10000
        
        # Calculate expected profits
        mexc_gateio_profit = mexc_gateio_spread - (df['safe_offset'] * 10000)
        gateio_mexc_profit = gateio_mexc_spread - (df['safe_offset'] * 10000)
        
        # Take best opportunity
        df['spread_bps'] = np.maximum(mexc_gateio_spread, gateio_mexc_spread)
        df['expected_profit_bps'] = np.maximum(mexc_gateio_profit, gateio_mexc_profit)
        
        # Calculate execution confidence (simplified)
        df['base_confidence'] = np.minimum(df['spread_bps'] / 50.0, 1.0)
        df['volatility_adjustment'] = 1.0 - np.minimum(df['volatility_z_score'] / 5.0, 0.5).clip(lower=0)
        df['execution_confidence'] = (df['base_confidence'] * df['volatility_adjustment']).clip(0.0, 1.0)
        
        # Calculate volatility score
        df['volatility_score'] = (
            (np.minimum(df['volatility_z_score'] / 3.0, 1.0) * 0.4) +
            (df['volatility_percentile'] / 100.0 * 0.3) +
            (np.minimum(df['mean_reversion_strength'] / 5.0, 1.0) * 0.3)
        ).clip(0.0, 1.0)
        
        # Mark profitable opportunities
        df['profitable_opportunity'] = df['expected_profit_bps'] > min_profit
        
        # Simple profit reached calculation
        df['profit_reached_bps'] = df['expected_profit_bps'].rolling(window=5).max()
        
        return df
    
    def update_indicators(self, new_data: Union[Dict[str, Any], pd.DataFrame]) -> None:
        """
        Update rolling indicators with new market data.
        
        Args:
            new_data: New market data (single row or snapshot)
        """
        # Extract spread data from new_data
        if isinstance(new_data, dict):
            spreads = self._calculate_spread_from_market_data(new_data)
        else:  # DataFrame
            if len(new_data) > 0:
                latest_row = new_data.iloc[-1].to_dict()
                spreads = self._calculate_spread_from_market_data(latest_row)
            else:
                return
        
        # Update historical data
        self._update_historical_data(spreads)
        
        # Update current volatility metrics
        self.current_volatility_metrics = self._calculate_volatility_metrics(spreads)
    
    def get_required_lookback(self) -> int:
        """
        Get the minimum lookback period required for the strategy.
        
        Returns:
            Number of historical periods needed for indicator calculation
        """
        return max(self.lookback_periods, self.volatility_window * 2)
    

    def validate_market_data(self, data: Union[Dict[str, Any], pd.DataFrame]) -> bool:
        """
        Validate that market data has required fields for the strategy.
        
        Args:
            data: Market data to validate
            
        Returns:
            True if data is valid, False otherwise
        """
        if isinstance(data, dict):
            # Check for required price fields (either format)
            required_fields = [
                ('mexc_bid', 'MEXC_SPOT_bid_price'),
                ('mexc_ask', 'MEXC_SPOT_ask_price'),
                ('gateio_futures_bid', 'GATEIO_FUTURES_bid_price'),
                ('gateio_futures_ask', 'GATEIO_FUTURES_ask_price')
            ]
            
            for field_pair in required_fields:
                if not any(field in data and data[field] > 0 for field in field_pair):
                    return False
            
            return True
        
        elif isinstance(data, pd.DataFrame):
            if data.empty:
                return False
            
            # Check for required columns
            required_columns = [
                'MEXC_SPOT_bid_price', 'MEXC_SPOT_ask_price',
                'GATEIO_FUTURES_bid_price', 'GATEIO_FUTURES_ask_price'
            ]
            
            for col in required_columns:
                if col not in data.columns:
                    return False
                if data[col].isna().all() or (data[col] <= 0).all():
                    return False
            
            return True
        
        return False
    
    def calculate_signal_confidence(self, indicators: Dict[str, float]) -> float:
        """
        Calculate confidence score for the current signal.
        
        Args:
            indicators: Current indicator values
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        if not indicators:
            return 0.0
        
        # Extract key indicators
        volatility_z_score = indicators.get('volatility_z_score', 0)
        execution_confidence = indicators.get('execution_confidence', 0)
        volatility_score = indicators.get('volatility_score', 0)
        expected_profit_bps = indicators.get('expected_profit_bps', 0)
        
        # Base confidence from execution confidence
        base_confidence = execution_confidence
        
        # Adjust for volatility strength
        volatility_adjustment = min(abs(volatility_z_score) / 3.0, 1.0)
        
        # Adjust for profit potential
        profit_adjustment = min(expected_profit_bps / 50.0, 1.0)
        
        # Adjust for volatility opportunity score
        opportunity_adjustment = volatility_score
        
        # Combined confidence
        total_confidence = (
            base_confidence * 0.4 +
            volatility_adjustment * 0.2 +
            profit_adjustment * 0.2 +
            opportunity_adjustment * 0.2
        )
        
        return max(min(total_confidence, 1.0), 0.0)
    
    def _calculate_spread_from_market_data(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate spreads from market data.
        
        Args:
            market_data: Market data dictionary
            
        Returns:
            Dictionary of calculated spreads
        """
        # Extract prices - handle both DataFrame column names and manual data
        mexc_bid = market_data.get('mexc_bid', market_data.get('MEXC_SPOT_bid_price', 0))
        mexc_ask = market_data.get('mexc_ask', market_data.get('MEXC_SPOT_ask_price', 0))
        gateio_futures_bid = market_data.get('gateio_futures_bid', market_data.get('GATEIO_FUTURES_bid_price', 0))
        gateio_futures_ask = market_data.get('gateio_futures_ask', market_data.get('GATEIO_FUTURES_ask_price', 0))
        
        if not all([mexc_bid, mexc_ask, gateio_futures_bid, gateio_futures_ask]):
            return {}
        
        # Calculate spreads matching arbitrage analyzer logic
        mexc_mid = (mexc_bid + mexc_ask) / 2
        gateio_futures_mid = (gateio_futures_bid + gateio_futures_ask) / 2
        
        # Main spread for volatility analysis
        mexc_vs_gateio_futures = (mexc_mid - gateio_futures_mid) / gateio_futures_mid
        
        # Additional spreads for comprehensive analysis
        mexc_spread = (mexc_ask - mexc_bid) / mexc_mid
        gateio_futures_spread = (gateio_futures_ask - gateio_futures_bid) / gateio_futures_mid
        
        return {
            'mexc_vs_gateio_futures': mexc_vs_gateio_futures,
            'mexc_spread': mexc_spread,
            'gateio_futures_spread': gateio_futures_spread,
            'mexc_mid': mexc_mid,
            'gateio_futures_mid': gateio_futures_mid
        }
    
    def _calculate_common_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate common indicators needed for strategy.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with added indicators
        """
        # Calculate basic spreads
        df['mexc_mid'] = (df['MEXC_SPOT_bid_price'] + df['MEXC_SPOT_ask_price']) / 2
        df['gateio_futures_mid'] = (df['GATEIO_FUTURES_bid_price'] + df['GATEIO_FUTURES_ask_price']) / 2
        
        # Main spread for analysis
        df['mexc_vs_gateio_futures_spread'] = (
            (df['mexc_mid'] - df['gateio_futures_mid']) / df['gateio_futures_mid']
        )
        
        # Individual exchange spreads
        df['mexc_spread'] = (df['MEXC_SPOT_ask_price'] - df['MEXC_SPOT_bid_price']) / df['mexc_mid']
        df['gateio_futures_spread'] = (
            (df['GATEIO_FUTURES_ask_price'] - df['GATEIO_FUTURES_bid_price']) / df['gateio_futures_mid']
        )
        
        return df