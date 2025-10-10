"""
Delta-Neutral Strategy Analyzer for Low-Liquidity Crypto Markets
Comprehensive analysis tools for spot-futures arbitrage strategy
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
import warnings
warnings.filterwarnings('ignore')


@dataclass
class LiquidityProfile:
    """Liquidity metrics for a trading pair"""
    symbol: str
    avg_spread_bps: float
    avg_depth_usd: float
    volume_24h: float
    liquidity_score: float  # 0-1 scale
    tier: str  # 'high', 'medium', 'low'
    
    
@dataclass
class ArbitrageSignal:
    """Arbitrage opportunity signal"""
    timestamp: datetime
    symbol: str
    spot_price: float
    futures_price: float
    spread_bps: float
    liquidity_score: float
    position_size: float
    expected_profit_bps: float
    confidence: float


class DeltaNeutralAnalyzer:
    """
    Comprehensive analyzer for delta-neutral spot-futures strategy
    Designed for low-liquidity cryptocurrency markets
    """
    
    def __init__(self, db_config: Dict[str, str]):
        """Initialize analyzer with database connection"""
        self.conn = psycopg2.connect(**db_config)
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        # Strategy parameters (adaptive)
        self.base_offset_pct = 0.005  # 0.5% default
        self.min_spread_bps = 30  # Minimum 30 bps to enter
        self.max_position_pct = 0.02  # Max 2% of capital per position
        self.liquidity_tiers = {
            'high': {'min_depth': 100000, 'min_volume': 1000000},
            'medium': {'min_depth': 30000, 'min_volume': 300000},
            'low': {'min_depth': 10000, 'min_volume': 50000}
        }
        
    def analyze_liquidity_profile(self, symbol: str, exchange: str, 
                                 lookback_hours: int = 24) -> LiquidityProfile:
        """
        Analyze liquidity characteristics of a trading pair
        Critical for position sizing and risk management
        """
        query = """
        WITH depth_analysis AS (
            SELECT 
                AVG((ask_price - bid_price) / bid_price * 10000) as avg_spread_bps,
                AVG((bid_qty * bid_price + ask_qty * ask_price)) as avg_depth_usd,
                PERCENTILE_CONT(0.1) WITHIN GROUP (ORDER BY bid_qty * bid_price) as p10_depth,
                PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY bid_qty * bid_price) as p90_depth
            FROM book_ticker_snapshots
            WHERE symbol_base = %s 
                AND exchange = %s
                AND timestamp > NOW() - INTERVAL '%s hours'
        ),
        volume_analysis AS (
            SELECT 
                SUM(ts.quantity * ts.price) as volume_24h,
                COUNT(*) as trade_count,
                AVG(ts.quantity * ts.price) as avg_trade_size
            FROM trade_snapshots ts
            JOIN symbols s ON ts.symbol_id = s.id
            JOIN exchanges e ON s.exchange_id = e.id
            WHERE s.symbol_base = %s 
                AND e.enum_value = %s
                AND ts.timestamp > NOW() - INTERVAL '%s hours'
        )
        SELECT * FROM depth_analysis CROSS JOIN volume_analysis
        """
        
        self.cursor.execute(query, (symbol, exchange, lookback_hours, 
                                   symbol, exchange, lookback_hours))
        result = self.cursor.fetchone()
        
        if not result:
            return None
            
        # Calculate liquidity score (0-1 scale)
        liquidity_score = self._calculate_liquidity_score(
            result['avg_spread_bps'],
            result['avg_depth_usd'],
            result['volume_24h']
        )
        
        # Determine liquidity tier
        tier = self._assign_liquidity_tier(
            result['avg_depth_usd'],
            result['volume_24h']
        )
        
        return LiquidityProfile(
            symbol=symbol,
            avg_spread_bps=float(result['avg_spread_bps']),
            avg_depth_usd=float(result['avg_depth_usd']),
            volume_24h=float(result['volume_24h']),
            liquidity_score=liquidity_score,
            tier=tier
        )
    
    def detect_spike_opportunities(self, symbol: str, spot_exchange: str,
                                  futures_exchange: str, 
                                  window_minutes: int = 5) -> List[ArbitrageSignal]:
        """
        Detect price spike opportunities for delta-neutral strategy
        Identifies moments when spot price deviates from futures
        """
        query = """
        WITH spot_data AS (
            SELECT 
                timestamp,
                symbol_base,
                (bid_price + ask_price) / 2 as spot_mid,
                bid_qty,
                ask_qty
            FROM book_ticker_snapshots
            WHERE exchange = %s 
                AND symbol_base = %s
                AND timestamp > NOW() - INTERVAL '%s minutes'
        ),
        futures_data AS (
            SELECT 
                timestamp,
                symbol_base,
                (bid_price + ask_price) / 2 as futures_mid,
                bid_qty as fut_bid_qty,
                ask_qty as fut_ask_qty
            FROM book_ticker_snapshots
            WHERE exchange = %s 
                AND symbol_base = %s
                AND timestamp > NOW() - INTERVAL '%s minutes'
        ),
        spread_analysis AS (
            SELECT 
                s.timestamp,
                s.spot_mid,
                f.futures_mid,
                (f.futures_mid - s.spot_mid) / s.spot_mid * 10000 as spread_bps,
                s.bid_qty,
                s.ask_qty,
                f.fut_bid_qty,
                f.fut_ask_qty
            FROM spot_data s
            JOIN futures_data f 
                ON s.timestamp = f.timestamp 
                AND s.symbol_base = f.symbol_base
        )
        SELECT 
            timestamp,
            spot_mid,
            futures_mid,
            spread_bps,
            bid_qty,
            ask_qty,
            fut_bid_qty,
            fut_ask_qty,
            AVG(spread_bps) OVER (ORDER BY timestamp ROWS BETWEEN 20 PRECEDING AND CURRENT ROW) as ma_spread,
            STDDEV(spread_bps) OVER (ORDER BY timestamp ROWS BETWEEN 20 PRECEDING AND CURRENT ROW) as std_spread
        FROM spread_analysis
        WHERE ABS(spread_bps) > %s
        ORDER BY timestamp DESC
        """
        
        self.cursor.execute(query, (spot_exchange, symbol, window_minutes,
                                   futures_exchange, symbol, window_minutes,
                                   self.min_spread_bps))
        results = self.cursor.fetchall()
        
        signals = []
        for row in results:
            # Check if spread is significant (> 2 std deviations)
            if row['std_spread'] and row['std_spread'] > 0:
                z_score = (row['spread_bps'] - row['ma_spread']) / row['std_spread']
                if abs(z_score) > 2:
                    signal = self._create_arbitrage_signal(row, symbol)
                    if signal:
                        signals.append(signal)
                        
        return signals
    
    def backtest_strategy(self, symbol: str, spot_exchange: str,
                         futures_exchange: str, start_date: str,
                         end_date: str, initial_capital: float = 100000) -> Dict:
        """
        Comprehensive backtest of delta-neutral strategy
        Includes realistic execution assumptions for low-liquidity markets
        """
        # Fetch historical data
        query = """
        WITH combined_data AS (
            SELECT 
                t1.timestamp,
                t1.bid_price as spot_bid,
                t1.ask_price as spot_ask,
                t1.bid_qty as spot_bid_qty,
                t1.ask_qty as spot_ask_qty,
                t2.bid_price as fut_bid,
                t2.ask_price as fut_ask,
                t2.bid_qty as fut_bid_qty,
                t2.ask_qty as fut_ask_qty
            FROM book_ticker_snapshots t1
            JOIN book_ticker_snapshots t2 
                ON t1.timestamp = t2.timestamp 
                AND t1.symbol_base = t2.symbol_base
            WHERE t1.exchange = %s 
                AND t2.exchange = %s
                AND t1.symbol_base = %s
                AND t1.timestamp BETWEEN %s AND %s
            ORDER BY t1.timestamp
        )
        SELECT * FROM combined_data
        """
        
        self.cursor.execute(query, (spot_exchange, futures_exchange, 
                                   symbol, start_date, end_date))
        data = pd.DataFrame(self.cursor.fetchall())
        
        if data.empty:
            return {'error': 'No data available for backtest period'}
        
        # Initialize backtest state
        capital = initial_capital
        positions = []
        trades = []
        
        # Calculate adaptive offset based on volatility
        data['spot_mid'] = (data['spot_bid'] + data['spot_ask']) / 2
        data['fut_mid'] = (data['fut_bid'] + data['fut_ask']) / 2
        data['spread_bps'] = (data['fut_mid'] - data['spot_mid']) / data['spot_mid'] * 10000
        data['volatility'] = data['spot_mid'].pct_change().rolling(20).std()
        
        # Simulate strategy
        for i in range(20, len(data)):
            row = data.iloc[i]
            
            # Check for entry signal
            if abs(row['spread_bps']) > self.min_spread_bps:
                # Calculate dynamic offset based on volatility
                offset = self._calculate_dynamic_offset(row['volatility'])
                
                # Check liquidity constraints
                min_liquidity = min(row['spot_bid_qty'] * row['spot_bid'],
                                   row['fut_ask_qty'] * row['fut_ask'])
                
                if min_liquidity > 1000:  # Minimum $1000 liquidity
                    # Simulate entry
                    position_size = self._calculate_backtest_position_size(
                        capital, min_liquidity, row['volatility']
                    )
                    
                    # Account for slippage
                    spot_entry = row['spot_ask'] * 1.001  # 0.1% slippage
                    futures_entry = row['fut_bid'] * 0.999  # 0.1% slippage
                    
                    positions.append({
                        'entry_time': row['timestamp'],
                        'spot_entry': spot_entry,
                        'futures_entry': futures_entry,
                        'size': position_size,
                        'entry_spread_bps': row['spread_bps']
                    })
            
            # Check for exit signals on existing positions
            positions_to_close = []
            for idx, pos in enumerate(positions):
                hold_time = (row['timestamp'] - pos['entry_time']).total_seconds() / 3600
                
                # Exit conditions
                exit_signal = (
                    abs(row['spread_bps']) < 10 or  # Spread compressed
                    hold_time > 24 or  # Max hold time
                    row['spread_bps'] * pos['entry_spread_bps'] < 0  # Spread reversed
                )
                
                if exit_signal:
                    # Calculate PnL
                    spot_exit = row['spot_bid'] * 0.999  # 0.1% slippage
                    futures_exit = row['fut_ask'] * 1.001  # 0.1% slippage
                    
                    spot_pnl = (spot_exit - pos['spot_entry']) / pos['spot_entry']
                    futures_pnl = -(futures_exit - pos['futures_entry']) / pos['futures_entry']
                    total_pnl = (spot_pnl + futures_pnl) * pos['size']
                    
                    # Account for fees (0.1% each leg)
                    fees = pos['size'] * 0.004  # 0.1% * 4 trades
                    net_pnl = total_pnl - fees
                    
                    capital += net_pnl
                    trades.append({
                        'entry_time': pos['entry_time'],
                        'exit_time': row['timestamp'],
                        'hold_hours': hold_time,
                        'entry_spread_bps': pos['entry_spread_bps'],
                        'exit_spread_bps': row['spread_bps'],
                        'pnl': net_pnl,
                        'return_pct': net_pnl / pos['size'] * 100
                    })
                    positions_to_close.append(idx)
            
            # Remove closed positions
            for idx in sorted(positions_to_close, reverse=True):
                del positions[idx]
        
        # Calculate performance metrics
        if trades:
            trades_df = pd.DataFrame(trades)
            returns = trades_df['return_pct'].values
            
            metrics = {
                'total_trades': len(trades),
                'win_rate': len(trades_df[trades_df['pnl'] > 0]) / len(trades) * 100,
                'avg_return_pct': returns.mean(),
                'total_return_pct': (capital - initial_capital) / initial_capital * 100,
                'sharpe_ratio': returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0,
                'max_drawdown_pct': self._calculate_max_drawdown(trades_df),
                'avg_hold_hours': trades_df['hold_hours'].mean(),
                'best_trade_pct': returns.max(),
                'worst_trade_pct': returns.min(),
                'final_capital': capital
            }
        else:
            metrics = {'error': 'No trades executed during backtest period'}
            
        return metrics
    
    def calculate_optimal_offset(self, symbol: str, exchange: str,
                                lookback_days: int = 30) -> Dict[str, float]:
        """
        Calculate optimal offset parameter for limit orders
        Based on historical fill probability and profit analysis
        """
        query = """
        WITH price_movements AS (
            SELECT 
                timestamp,
                symbol_base,
                (bid_price + ask_price) / 2 as mid_price,
                LAG((bid_price + ask_price) / 2, 1) OVER (ORDER BY timestamp) as prev_mid,
                bid_qty,
                ask_qty
            FROM book_ticker_snapshots
            WHERE symbol_base = %s 
                AND exchange = %s
                AND timestamp > NOW() - INTERVAL '%s days'
        ),
        spike_analysis AS (
            SELECT 
                timestamp,
                ABS(mid_price - prev_mid) / prev_mid * 100 as price_move_pct,
                bid_qty * mid_price as bid_liquidity,
                ask_qty * mid_price as ask_liquidity
            FROM price_movements
            WHERE prev_mid IS NOT NULL
        )
        SELECT 
            price_move_pct,
            COUNT(*) as frequency,
            AVG(bid_liquidity) as avg_liquidity,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY bid_liquidity) as median_liquidity
        FROM spike_analysis
        WHERE price_move_pct BETWEEN 0.1 AND 2.0
        GROUP BY ROUND(price_move_pct * 100) / 100
        ORDER BY price_move_pct
        """
        
        self.cursor.execute(query, (symbol, exchange, lookback_days))
        results = pd.DataFrame(self.cursor.fetchall())
        
        if results.empty:
            return {'error': 'Insufficient data for offset calculation'}
        
        # Calculate fill probability for different offsets
        offset_analysis = []
        for offset in np.arange(0.002, 0.015, 0.001):  # 0.2% to 1.5%
            fill_prob = len(results[results['price_move_pct'] >= offset * 100]) / len(results)
            avg_liquidity = results[results['price_move_pct'] >= offset * 100]['avg_liquidity'].mean()
            
            offset_analysis.append({
                'offset_pct': offset * 100,
                'fill_probability': fill_prob,
                'avg_liquidity_usd': avg_liquidity,
                'expected_value': fill_prob * offset * 100  # Simplified EV
            })
        
        offset_df = pd.DataFrame(offset_analysis)
        optimal = offset_df.loc[offset_df['expected_value'].idxmax()]
        
        return {
            'optimal_offset_pct': optimal['offset_pct'],
            'fill_probability': optimal['fill_probability'],
            'expected_liquidity_usd': optimal['avg_liquidity_usd'],
            'expected_value': optimal['expected_value'],
            'analysis': offset_df.to_dict('records')
        }
    
    def monitor_real_time_risks(self, active_positions: List[Dict]) -> Dict[str, any]:
        """
        Real-time risk monitoring for active positions
        Critical for low-liquidity market safety
        """
        risk_report = {
            'timestamp': datetime.now(),
            'total_positions': len(active_positions),
            'alerts': [],
            'risk_scores': {}
        }
        
        for position in active_positions:
            symbol = position['symbol']
            exchange = position['exchange']
            
            # Check current liquidity
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
            current = self.cursor.fetchone()
            
            if current:
                # Calculate exit liquidity
                exit_liquidity = min(
                    current['bid_qty'] * current['bid_price'],
                    position['size']
                )
                
                # Risk scoring
                risk_score = 0
                
                # Liquidity risk
                if exit_liquidity < position['size'] * 0.5:
                    risk_score += 40
                    risk_report['alerts'].append(
                        f"CRITICAL: Low exit liquidity for {symbol} - Only {exit_liquidity/position['size']*100:.1f}% available"
                    )
                
                # Spread risk
                if current['spread_bps'] > 50:
                    risk_score += 20
                    risk_report['alerts'].append(
                        f"WARNING: Wide spread on {symbol} - {current['spread_bps']:.1f} bps"
                    )
                
                # Position age risk
                hold_time = (datetime.now() - position['entry_time']).total_seconds() / 3600
                if hold_time > 12:
                    risk_score += 20
                    risk_report['alerts'].append(
                        f"WARNING: Stale position {symbol} - {hold_time:.1f} hours old"
                    )
                
                risk_report['risk_scores'][symbol] = {
                    'score': risk_score,
                    'exit_liquidity_pct': exit_liquidity / position['size'] * 100,
                    'current_spread_bps': current['spread_bps'],
                    'hold_hours': hold_time
                }
        
        return risk_report
    
    def _calculate_liquidity_score(self, spread_bps: float, 
                                  depth_usd: float, volume_24h: float) -> float:
        """Calculate normalized liquidity score (0-1)"""
        spread_score = max(0, 1 - (spread_bps / 100))  # Lower spread = higher score
        depth_score = min(1, depth_usd / 100000)  # Normalize to $100k
        volume_score = min(1, volume_24h / 1000000)  # Normalize to $1M
        
        # Weighted average
        return (spread_score * 0.3 + depth_score * 0.4 + volume_score * 0.3)
    
    def _assign_liquidity_tier(self, depth_usd: float, volume_24h: float) -> str:
        """Assign liquidity tier based on depth and volume"""
        if depth_usd >= 100000 and volume_24h >= 1000000:
            return 'high'
        elif depth_usd >= 30000 and volume_24h >= 300000:
            return 'medium'
        else:
            return 'low'
    
    def _calculate_dynamic_offset(self, volatility: float) -> float:
        """Calculate adaptive offset based on market volatility"""
        if pd.isna(volatility):
            return self.base_offset_pct
            
        # Higher volatility = larger offset needed
        if volatility < 0.01:
            return self.base_offset_pct * 0.6
        elif volatility < 0.02:
            return self.base_offset_pct
        elif volatility < 0.04:
            return self.base_offset_pct * 1.5
        else:
            return self.base_offset_pct * 2.0
    
    def _calculate_backtest_position_size(self, capital: float, 
                                         liquidity: float, volatility: float) -> float:
        """Calculate position size for backtesting"""
        base_size = capital * self.max_position_pct
        
        # Limit by available liquidity
        max_size = min(base_size, liquidity * 0.1)  # Max 10% of available liquidity
        
        # Adjust for volatility
        if volatility > 0.03:
            max_size *= 0.5
            
        return max_size
    
    def _create_arbitrage_signal(self, data: Dict, symbol: str) -> Optional[ArbitrageSignal]:
        """Create arbitrage signal from data row"""
        # Calculate position size based on liquidity
        min_liquidity = min(
            data['bid_qty'] * data['spot_mid'],
            data['fut_bid_qty'] * data['futures_mid']
        )
        
        if min_liquidity < 1000:  # Skip if liquidity too low
            return None
            
        position_size = min(10000, min_liquidity * 0.05)  # Max 5% of liquidity
        
        # Estimate profit potential
        expected_profit_bps = abs(data['spread_bps']) - 40  # Account for fees and slippage
        
        if expected_profit_bps < 0:
            return None
            
        return ArbitrageSignal(
            timestamp=data['timestamp'],
            symbol=symbol,
            spot_price=data['spot_mid'],
            futures_price=data['futures_mid'],
            spread_bps=data['spread_bps'],
            liquidity_score=min(1.0, min_liquidity / 50000),
            position_size=position_size,
            expected_profit_bps=expected_profit_bps,
            confidence=min(0.95, expected_profit_bps / 100)
        )
    
    def _calculate_max_drawdown(self, trades_df: pd.DataFrame) -> float:
        """Calculate maximum drawdown from trades"""
        cumulative = trades_df['pnl'].cumsum()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max.abs() * 100
        return drawdown.min() if len(drawdown) > 0 else 0


# Usage example
if __name__ == "__main__":
    # Database configuration
    db_config = {
        'host': 'localhost',
        'database': 'trading',
        'user': 'your_user',
        'password': 'your_password',
        'port': 5432
    }
    
    # Initialize analyzer
    analyzer = DeltaNeutralAnalyzer(db_config)
    
    # Example: Analyze liquidity profile
    profile = analyzer.analyze_liquidity_profile('BTC', 'binance-spot')
    print(f"Liquidity Profile: {profile}")
    
    # Example: Detect spike opportunities
    signals = analyzer.detect_spike_opportunities('BTC', 'binance-spot', 'binance-futures')
    print(f"Found {len(signals)} arbitrage signals")
    
    # Example: Run backtest
    backtest_results = analyzer.backtest_strategy(
        'BTC', 'binance-spot', 'binance-futures',
        '2024-01-01', '2024-12-31', 100000
    )
    print(f"Backtest Results: {backtest_results}")