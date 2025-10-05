"""
Market Microstructure Analysis for Delta-Neutral Strategy
Specialized tools for low-liquidity crypto market analysis
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
from scipy import stats
from scipy.optimize import minimize_scalar
import warnings
warnings.filterwarnings('ignore')


@dataclass
class MicrostructureMetrics:
    """Market microstructure analysis results"""
    symbol: str
    exchange: str
    timestamp: datetime
    
    # Liquidity metrics
    bid_ask_spread_bps: float
    effective_spread_bps: float
    quoted_depth_usd: float
    market_impact_bps: float
    
    # Order flow metrics
    ofi_score: float  # Order Flow Imbalance
    trade_intensity: float
    price_impact_decay: float
    liquidity_resilience: float
    
    # Volatility and efficiency
    realized_volatility: float
    tick_efficiency: float
    market_quality_score: float
    
    # Risk indicators
    manipulation_score: float
    liquidity_risk_score: float
    execution_risk_score: float


@dataclass
class OptimalTiming:
    """Optimal execution timing analysis"""
    symbol: str
    recommended_delay_ms: int
    confidence: float
    expected_slippage_bps: float
    liquidity_window_sec: int


class MicrostructureAnalyzer:
    """
    Advanced market microstructure analysis for delta-neutral strategy
    Focuses on execution timing, liquidity dynamics, and manipulation detection
    """
    
    def __init__(self, db_config: Dict[str, str]):
        """Initialize analyzer with database connection"""
        self.conn = psycopg2.connect(**db_config)
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        # Analysis parameters
        self.tick_size = 0.01  # Default tick size
        self.min_trade_size = 100  # Minimum trade size for analysis
        self.liquidity_depth_levels = [0.1, 0.25, 0.5, 1.0]  # % levels for depth analysis
    
    def analyze_market_microstructure(self, symbol: str, exchange: str,
                                    lookback_minutes: int = 60) -> MicrostructureMetrics:
        """
        Comprehensive microstructure analysis for a trading pair
        Critical for understanding execution dynamics in low-liquidity markets
        """
        # Fetch orderbook and trade data
        orderbook_data = self._fetch_orderbook_data(symbol, exchange, lookback_minutes)
        trade_data = self._fetch_trade_data(symbol, exchange, lookback_minutes)
        
        if orderbook_data.empty or trade_data.empty:
            return None
        
        # Calculate core metrics
        liquidity_metrics = self._calculate_liquidity_metrics(orderbook_data, trade_data)
        order_flow_metrics = self._calculate_order_flow_metrics(orderbook_data, trade_data)
        volatility_metrics = self._calculate_volatility_metrics(trade_data)
        risk_metrics = self._calculate_risk_metrics(orderbook_data, trade_data)
        
        return MicrostructureMetrics(
            symbol=symbol,
            exchange=exchange,
            timestamp=datetime.now(),
            
            # Liquidity metrics
            bid_ask_spread_bps=liquidity_metrics['bid_ask_spread_bps'],
            effective_spread_bps=liquidity_metrics['effective_spread_bps'],
            quoted_depth_usd=liquidity_metrics['quoted_depth_usd'],
            market_impact_bps=liquidity_metrics['market_impact_bps'],
            
            # Order flow metrics
            ofi_score=order_flow_metrics['ofi_score'],
            trade_intensity=order_flow_metrics['trade_intensity'],
            price_impact_decay=order_flow_metrics['price_impact_decay'],
            liquidity_resilience=order_flow_metrics['liquidity_resilience'],
            
            # Volatility and efficiency
            realized_volatility=volatility_metrics['realized_volatility'],
            tick_efficiency=volatility_metrics['tick_efficiency'],
            market_quality_score=volatility_metrics['market_quality_score'],
            
            # Risk indicators
            manipulation_score=risk_metrics['manipulation_score'],
            liquidity_risk_score=risk_metrics['liquidity_risk_score'],
            execution_risk_score=risk_metrics['execution_risk_score']
        )
    
    def find_optimal_execution_timing(self, symbol: str, spot_exchange: str,
                                     futures_exchange: str, position_size_usd: float,
                                     lookback_hours: int = 24) -> OptimalTiming:
        """
        Find optimal timing for futures hedge execution after spot fill
        Minimizes slippage and execution risk in low-liquidity environment
        """
        # Analyze historical execution patterns
        query = """
        WITH execution_analysis AS (
            SELECT 
                extract(epoch from timestamp) * 1000 as ts_ms,
                (bid_price + ask_price) / 2 as mid_price,
                bid_qty * bid_price + ask_qty * ask_price as total_depth,
                (ask_price - bid_price) / bid_price * 10000 as spread_bps
            FROM book_ticker_snapshots
            WHERE symbol_base = %s 
                AND exchange = %s
                AND timestamp > NOW() - INTERVAL '%s hours'
            ORDER BY timestamp
        ),
        price_impact AS (
            SELECT 
                ts_ms,
                mid_price,
                total_depth,
                spread_bps,
                ABS(mid_price - LAG(mid_price, 1) OVER (ORDER BY ts_ms)) / LAG(mid_price, 1) OVER (ORDER BY ts_ms) * 10000 as price_change_bps,
                ts_ms - LAG(ts_ms, 1) OVER (ORDER BY ts_ms) as time_diff_ms
            FROM execution_analysis
        )
        SELECT 
            time_diff_ms,
            price_change_bps,
            total_depth,
            spread_bps
        FROM price_impact
        WHERE time_diff_ms BETWEEN 100 AND 10000  -- 100ms to 10s
            AND total_depth > %s  -- Minimum liquidity threshold
        """
        
        self.cursor.execute(query, (symbol, futures_exchange, lookback_hours, position_size_usd))
        data = pd.DataFrame(self.cursor.fetchall())
        
        if data.empty:
            return OptimalTiming(
                symbol=symbol,
                recommended_delay_ms=500,  # Default safe delay
                confidence=0.5,
                expected_slippage_bps=50,
                liquidity_window_sec=5
            )
        
        # Analyze slippage vs delay relationship
        delay_buckets = np.arange(100, 5000, 200)  # 100ms to 5s in 200ms buckets
        slippage_by_delay = []
        
        for delay in delay_buckets:
            delay_data = data[
                (data['time_diff_ms'] >= delay - 100) & 
                (data['time_diff_ms'] <= delay + 100)
            ]
            
            if len(delay_data) > 10:
                # Calculate expected slippage (price impact + spread)
                avg_price_impact = delay_data['price_change_bps'].mean()
                avg_spread = delay_data['spread_bps'].mean()
                expected_slippage = avg_price_impact + (avg_spread / 2)
                
                slippage_by_delay.append({
                    'delay_ms': delay,
                    'expected_slippage_bps': expected_slippage,
                    'sample_size': len(delay_data),
                    'liquidity_score': delay_data['total_depth'].mean()
                })
        
        if not slippage_by_delay:
            return OptimalTiming(
                symbol=symbol,
                recommended_delay_ms=500,
                confidence=0.3,
                expected_slippage_bps=75,
                liquidity_window_sec=5
            )
        
        # Find optimal delay (minimize slippage while ensuring adequate liquidity)
        slippage_df = pd.DataFrame(slippage_by_delay)
        
        # Weight by sample size and liquidity
        slippage_df['weighted_score'] = (
            slippage_df['expected_slippage_bps'] * 
            (1 / np.sqrt(slippage_df['sample_size'])) *
            (position_size_usd / slippage_df['liquidity_score'])
        )
        
        optimal_idx = slippage_df['weighted_score'].idxmin()
        optimal_row = slippage_df.iloc[optimal_idx]
        
        # Calculate confidence based on sample size and consistency
        confidence = min(0.95, optimal_row['sample_size'] / 100)
        
        return OptimalTiming(
            symbol=symbol,
            recommended_delay_ms=int(optimal_row['delay_ms']),
            confidence=confidence,
            expected_slippage_bps=optimal_row['expected_slippage_bps'],
            liquidity_window_sec=int(optimal_row['delay_ms'] / 1000) + 2
        )
    
    def detect_market_manipulation(self, symbol: str, exchange: str,
                                  lookback_minutes: int = 30) -> Dict[str, any]:
        """
        Detect potential market manipulation patterns
        Critical for avoiding toxic fills in low-liquidity markets
        """
        # Fetch recent trade and orderbook data
        trade_data = self._fetch_trade_data(symbol, exchange, lookback_minutes)
        orderbook_data = self._fetch_orderbook_data(symbol, exchange, lookback_minutes)
        
        manipulation_signals = {
            'timestamp': datetime.now(),
            'symbol': symbol,
            'exchange': exchange,
            'manipulation_score': 0,
            'detected_patterns': [],
            'recommendation': 'SAFE_TO_TRADE'
        }
        
        if trade_data.empty or orderbook_data.empty:
            manipulation_signals['recommendation'] = 'INSUFFICIENT_DATA'
            return manipulation_signals
        
        # 1. Wash trading detection
        wash_score = self._detect_wash_trading(trade_data)
        if wash_score > 0.7:
            manipulation_signals['manipulation_score'] += 30
            manipulation_signals['detected_patterns'].append('WASH_TRADING')
        
        # 2. Spoofing detection (large orders that get cancelled quickly)
        spoofing_score = self._detect_spoofing(orderbook_data)
        if spoofing_score > 0.6:
            manipulation_signals['manipulation_score'] += 25
            manipulation_signals['detected_patterns'].append('SPOOFING')
        
        # 3. Layering detection (multiple orders at similar prices)
        layering_score = self._detect_layering(orderbook_data)
        if layering_score > 0.5:
            manipulation_signals['manipulation_score'] += 20
            manipulation_signals['detected_patterns'].append('LAYERING')
        
        # 4. Momentum ignition (sudden volume spikes followed by reversals)
        momentum_score = self._detect_momentum_ignition(trade_data)
        if momentum_score > 0.8:
            manipulation_signals['manipulation_score'] += 35
            manipulation_signals['detected_patterns'].append('MOMENTUM_IGNITION')
        
        # 5. Artificial volume patterns
        volume_score = self._detect_artificial_volume(trade_data)
        if volume_score > 0.6:
            manipulation_signals['manipulation_score'] += 15
            manipulation_signals['detected_patterns'].append('ARTIFICIAL_VOLUME')
        
        # Determine recommendation
        if manipulation_signals['manipulation_score'] > 70:
            manipulation_signals['recommendation'] = 'AVOID_TRADING'
        elif manipulation_signals['manipulation_score'] > 40:
            manipulation_signals['recommendation'] = 'TRADE_WITH_CAUTION'
        else:
            manipulation_signals['recommendation'] = 'SAFE_TO_TRADE'
        
        return manipulation_signals
    
    def analyze_liquidity_resilience(self, symbol: str, exchange: str,
                                   shock_size_bps: float = 10) -> Dict[str, float]:
        """
        Analyze how quickly liquidity recovers after market shocks
        Critical for understanding exit risk in low-liquidity markets
        """
        query = """
        WITH price_shocks AS (
            SELECT 
                timestamp,
                (bid_price + ask_price) / 2 as mid_price,
                bid_qty * bid_price + ask_qty * ask_price as total_depth,
                ABS(
                    ((bid_price + ask_price) / 2) - 
                    LAG((bid_price + ask_price) / 2, 5) OVER (ORDER BY timestamp)
                ) / LAG((bid_price + ask_price) / 2, 5) OVER (ORDER BY timestamp) * 10000 as price_shock_bps
            FROM book_ticker_snapshots
            WHERE symbol_base = %s 
                AND exchange = %s
                AND timestamp > NOW() - INTERVAL '6 hours'
            ORDER BY timestamp
        ),
        shock_events AS (
            SELECT 
                timestamp,
                mid_price,
                total_depth,
                price_shock_bps,
                LEAD(total_depth, 1) OVER (ORDER BY timestamp) as depth_1min,
                LEAD(total_depth, 5) OVER (ORDER BY timestamp) as depth_5min,
                LEAD(total_depth, 10) OVER (ORDER BY timestamp) as depth_10min
            FROM price_shocks
            WHERE price_shock_bps > %s
        )
        SELECT * FROM shock_events WHERE depth_1min IS NOT NULL
        """
        
        self.cursor.execute(query, (symbol, exchange, shock_size_bps))
        shock_data = pd.DataFrame(self.cursor.fetchall())
        
        if shock_data.empty:
            return {
                'resilience_score': 0.5,
                'recovery_time_minutes': 10,
                'depth_recovery_1min': 0.5,
                'depth_recovery_5min': 0.8,
                'depth_recovery_10min': 0.9
            }
        
        # Calculate recovery metrics
        shock_data['recovery_1min'] = shock_data['depth_1min'] / shock_data['total_depth']
        shock_data['recovery_5min'] = shock_data['depth_5min'] / shock_data['total_depth']
        shock_data['recovery_10min'] = shock_data['depth_10min'] / shock_data['total_depth']
        
        # Overall resilience score (0-1, higher is better)
        resilience_score = (
            shock_data['recovery_1min'].mean() * 0.5 +
            shock_data['recovery_5min'].mean() * 0.3 +
            shock_data['recovery_10min'].mean() * 0.2
        )
        
        # Estimate recovery time
        recovery_times = []
        for _, row in shock_data.iterrows():
            if row['recovery_1min'] > 0.9:
                recovery_times.append(1)
            elif row['recovery_5min'] > 0.9:
                recovery_times.append(5)
            elif row['recovery_10min'] > 0.9:
                recovery_times.append(10)
            else:
                recovery_times.append(15)  # Assume >10 minutes
        
        return {
            'resilience_score': resilience_score,
            'recovery_time_minutes': np.mean(recovery_times),
            'depth_recovery_1min': shock_data['recovery_1min'].mean(),
            'depth_recovery_5min': shock_data['recovery_5min'].mean(),
            'depth_recovery_10min': shock_data['recovery_10min'].mean(),
            'shock_frequency': len(shock_data) / 6  # Shocks per hour
        }
    
    def calculate_optimal_order_size(self, symbol: str, exchange: str,
                                   max_market_impact_bps: float = 20) -> Dict[str, float]:
        """
        Calculate optimal order size to stay below market impact threshold
        """
        # Get current orderbook depth
        query = """
        SELECT 
            bid_price, bid_qty, ask_price, ask_qty,
            (ask_price - bid_price) / bid_price * 10000 as spread_bps
        FROM book_ticker_snapshots
        WHERE symbol_base = %s AND exchange = %s
        ORDER BY timestamp DESC
        LIMIT 1
        """
        
        self.cursor.execute(query, (symbol, exchange))
        current_book = self.cursor.fetchone()
        
        if not current_book:
            return {'error': 'No current orderbook data available'}
        
        # Calculate market impact for different order sizes
        mid_price = (current_book['bid_price'] + current_book['ask_price']) / 2
        available_liquidity = min(
            current_book['bid_qty'] * current_book['bid_price'],
            current_book['ask_qty'] * current_book['ask_price']
        )
        
        # Simple market impact model: sqrt(size / liquidity) * volatility_multiplier
        volatility_mult = max(1.0, current_book['spread_bps'] / 10)
        
        # Find maximum size that keeps market impact below threshold
        max_size_ratio = (max_market_impact_bps / (volatility_mult * 100)) ** 2
        optimal_size_usd = available_liquidity * max_size_ratio
        
        # Conservative adjustment for low-liquidity markets
        if available_liquidity < 10000:  # Very low liquidity
            optimal_size_usd *= 0.3
        elif available_liquidity < 50000:  # Low liquidity
            optimal_size_usd *= 0.5
        
        return {
            'optimal_size_usd': min(optimal_size_usd, available_liquidity * 0.1),
            'available_liquidity_usd': available_liquidity,
            'current_spread_bps': current_book['spread_bps'],
            'expected_market_impact_bps': min(max_market_impact_bps, 
                                            volatility_mult * 100 * np.sqrt(optimal_size_usd / available_liquidity)),
            'max_safe_size_pct': max_size_ratio * 100
        }
    
    # Helper methods for data fetching and calculations
    
    def _fetch_orderbook_data(self, symbol: str, exchange: str, minutes: int) -> pd.DataFrame:
        """Fetch recent orderbook snapshots"""
        query = """
        SELECT 
            timestamp,
            bid_price,
            bid_qty,
            ask_price,
            ask_qty
        FROM book_ticker_snapshots
        WHERE symbol_base = %s 
            AND exchange = %s
            AND timestamp > NOW() - INTERVAL '%s minutes'
        ORDER BY timestamp
        """
        
        self.cursor.execute(query, (symbol, exchange, minutes))
        return pd.DataFrame(self.cursor.fetchall())
    
    def _fetch_trade_data(self, symbol: str, exchange: str, minutes: int) -> pd.DataFrame:
        """Fetch recent trade data"""
        query = """
        SELECT 
            timestamp,
            price,
            quantity,
            side,
            trade_id,
            is_buyer,
            is_maker
        FROM trades
        WHERE symbol_base = %s 
            AND exchange = %s
            AND timestamp > NOW() - INTERVAL '%s minutes'
        ORDER BY timestamp
        """
        
        self.cursor.execute(query, (symbol, exchange, minutes))
        return pd.DataFrame(self.cursor.fetchall())
    
    def _calculate_liquidity_metrics(self, orderbook_data: pd.DataFrame, 
                                   trade_data: pd.DataFrame) -> Dict[str, float]:
        """Calculate liquidity-related metrics"""
        if orderbook_data.empty:
            return {}
        
        # Bid-ask spread
        orderbook_data['mid_price'] = (orderbook_data['bid_price'] + orderbook_data['ask_price']) / 2
        orderbook_data['spread_bps'] = (orderbook_data['ask_price'] - orderbook_data['bid_price']) / orderbook_data['bid_price'] * 10000
        
        # Quoted depth
        orderbook_data['total_depth_usd'] = (
            orderbook_data['bid_qty'] * orderbook_data['bid_price'] +
            orderbook_data['ask_qty'] * orderbook_data['ask_price']
        )
        
        # Effective spread (if we have trade data)
        effective_spread_bps = 0
        if not trade_data.empty and len(orderbook_data) > 0:
            # Match trades to orderbook snapshots (simplified)
            trade_data['effective_spread'] = trade_data['price'] - orderbook_data['mid_price'].iloc[-1]
            effective_spread_bps = abs(trade_data['effective_spread'].mean()) / orderbook_data['mid_price'].iloc[-1] * 10000
        
        return {
            'bid_ask_spread_bps': orderbook_data['spread_bps'].mean(),
            'effective_spread_bps': effective_spread_bps,
            'quoted_depth_usd': orderbook_data['total_depth_usd'].mean(),
            'market_impact_bps': orderbook_data['spread_bps'].std()  # Simplified metric
        }
    
    def _calculate_order_flow_metrics(self, orderbook_data: pd.DataFrame,
                                     trade_data: pd.DataFrame) -> Dict[str, float]:
        """Calculate order flow imbalance and related metrics"""
        if orderbook_data.empty:
            return {}
        
        # Order Flow Imbalance (OFI)
        orderbook_data['bid_depth'] = orderbook_data['bid_qty'] * orderbook_data['bid_price']
        orderbook_data['ask_depth'] = orderbook_data['ask_qty'] * orderbook_data['ask_price']
        orderbook_data['ofi'] = (orderbook_data['bid_depth'] - orderbook_data['ask_depth']) / (orderbook_data['bid_depth'] + orderbook_data['ask_depth'])
        
        # Trade intensity
        trade_intensity = len(trade_data) / (len(orderbook_data) / 60) if len(orderbook_data) > 60 else 0  # Trades per minute
        
        return {
            'ofi_score': orderbook_data['ofi'].mean(),
            'trade_intensity': trade_intensity,
            'price_impact_decay': 0.5,  # Placeholder - needs more complex calculation
            'liquidity_resilience': 0.7  # Placeholder - needs shock analysis
        }
    
    def _calculate_volatility_metrics(self, trade_data: pd.DataFrame) -> Dict[str, float]:
        """Calculate volatility and market efficiency metrics"""
        if trade_data.empty or len(trade_data) < 10:
            return {
                'realized_volatility': 0.02,
                'tick_efficiency': 0.5,
                'market_quality_score': 0.5
            }
        
        # Realized volatility (using log returns)
        trade_data = trade_data.sort_values('timestamp')
        trade_data['log_return'] = np.log(trade_data['price'] / trade_data['price'].shift(1))
        realized_vol = trade_data['log_return'].std() * np.sqrt(1440)  # Annualized
        
        # Tick efficiency (placeholder)
        tick_efficiency = 0.7  # Needs more sophisticated calculation
        
        # Market quality score (composite)
        quality_score = min(1.0, 1.0 / (1.0 + realized_vol))
        
        return {
            'realized_volatility': realized_vol,
            'tick_efficiency': tick_efficiency,
            'market_quality_score': quality_score
        }
    
    def _calculate_risk_metrics(self, orderbook_data: pd.DataFrame,
                               trade_data: pd.DataFrame) -> Dict[str, float]:
        """Calculate manipulation and risk indicators"""
        manipulation_score = 0
        liquidity_risk = 0
        execution_risk = 0
        
        if not orderbook_data.empty:
            # Liquidity risk based on depth variability
            depth_cv = orderbook_data['bid_qty'].std() / orderbook_data['bid_qty'].mean() if orderbook_data['bid_qty'].mean() > 0 else 1
            liquidity_risk = min(1.0, depth_cv)
            
            # Execution risk based on spread variability
            if 'spread_bps' in orderbook_data.columns:
                spread_cv = orderbook_data['spread_bps'].std() / orderbook_data['spread_bps'].mean() if orderbook_data['spread_bps'].mean() > 0 else 1
                execution_risk = min(1.0, spread_cv / 2)
        
        return {
            'manipulation_score': manipulation_score,
            'liquidity_risk_score': liquidity_risk,
            'execution_risk_score': execution_risk
        }
    
    def _detect_wash_trading(self, trade_data: pd.DataFrame) -> float:
        """Detect wash trading patterns"""
        if trade_data.empty or len(trade_data) < 10:
            return 0.0
        
        # Look for trades at identical prices with rapid reversals
        trade_data = trade_data.sort_values('timestamp')
        
        # Count price repetitions
        price_counts = trade_data['price'].value_counts()
        repeated_prices = len(price_counts[price_counts > 1]) / len(price_counts)
        
        # Look for buy/sell pattern at same prices
        same_price_trades = trade_data.groupby('price')['side'].apply(lambda x: len(set(x)) > 1).sum()
        pattern_score = same_price_trades / len(trade_data.groupby('price'))
        
        return min(1.0, (repeated_prices + pattern_score) / 2)
    
    def _detect_spoofing(self, orderbook_data: pd.DataFrame) -> float:
        """Detect spoofing patterns (simplified)"""
        if orderbook_data.empty:
            return 0.0
        
        # Look for sudden changes in order sizes
        orderbook_data['bid_change'] = orderbook_data['bid_qty'].diff().abs()
        orderbook_data['ask_change'] = orderbook_data['ask_qty'].diff().abs()
        
        # High variability in order sizes could indicate spoofing
        bid_variability = orderbook_data['bid_change'].std() / orderbook_data['bid_qty'].mean() if orderbook_data['bid_qty'].mean() > 0 else 0
        ask_variability = orderbook_data['ask_change'].std() / orderbook_data['ask_qty'].mean() if orderbook_data['ask_qty'].mean() > 0 else 0
        
        return min(1.0, (bid_variability + ask_variability) / 4)
    
    def _detect_layering(self, orderbook_data: pd.DataFrame) -> float:
        """Detect layering patterns (simplified)"""
        # Placeholder implementation
        return 0.0
    
    def _detect_momentum_ignition(self, trade_data: pd.DataFrame) -> float:
        """Detect momentum ignition patterns"""
        if trade_data.empty or len(trade_data) < 20:
            return 0.0
        
        # Look for volume spikes followed by price reversals
        trade_data = trade_data.sort_values('timestamp')
        trade_data['volume_spike'] = trade_data['quantity'] > trade_data['quantity'].rolling(10).mean() * 3
        trade_data['price_change'] = trade_data['price'].pct_change()
        
        # Find volume spikes followed by reversals
        spike_reversals = 0
        for i in range(1, len(trade_data) - 5):
            if trade_data.iloc[i]['volume_spike']:
                # Check if price reverses in next 5 trades
                price_changes = trade_data.iloc[i+1:i+6]['price_change']
                if len(price_changes) > 0 and price_changes.sum() * trade_data.iloc[i]['price_change'] < 0:
                    spike_reversals += 1
        
        return min(1.0, spike_reversals / max(1, trade_data['volume_spike'].sum()))
    
    def _detect_artificial_volume(self, trade_data: pd.DataFrame) -> float:
        """Detect artificial volume patterns"""
        if trade_data.empty:
            return 0.0
        
        # Look for unusually round trade sizes
        round_sizes = trade_data['quantity'].apply(lambda x: x == round(x, 2)).sum()
        round_ratio = round_sizes / len(trade_data)
        
        # High proportion of round sizes might indicate artificial trading
        return min(1.0, round_ratio)


# Example usage
if __name__ == "__main__":
    # Database configuration
    db_config = {
        'host': 'localhost',
        'database': 'trading',
        'user': 'your_user',
        'password': 'your_password',
        'port': 5432
    }
    
    analyzer = MicrostructureAnalyzer(db_config)
    
    # Analyze market microstructure
    metrics = analyzer.analyze_market_microstructure('BTC', 'binance-spot')
    print(f"Microstructure Metrics: {metrics}")
    
    # Find optimal execution timing
    timing = analyzer.find_optimal_execution_timing('BTC', 'binance-spot', 'binance-futures', 10000)
    print(f"Optimal Timing: {timing}")
    
    # Check for manipulation
    manipulation = analyzer.detect_market_manipulation('BTC', 'binance-spot')
    print(f"Manipulation Analysis: {manipulation}")
    
    # Analyze liquidity resilience
    resilience = analyzer.analyze_liquidity_resilience('BTC', 'binance-spot')
    print(f"Liquidity Resilience: {resilience}")