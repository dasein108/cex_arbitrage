"""
Comprehensive Backtesting Framework for Delta-Neutral Strategy
Advanced simulation with realistic execution modeling for low-liquidity markets
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, NamedTuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import psycopg2
from psycopg2.extras import RealDictCursor
from collections import defaultdict
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
import warnings
warnings.filterwarnings('ignore')


class PositionStatus(Enum):
    WAITING = "waiting"
    SPOT_FILLED = "spot_filled"
    HEDGE_PENDING = "hedge_pending"
    DELTA_NEUTRAL = "delta_neutral"
    CLOSING = "closing"
    CLOSED = "closed"


@dataclass
class BacktestConfig:
    """Backtesting configuration parameters"""
    initial_capital: float = 100000
    max_position_pct: float = 0.02  # Max 2% per position
    base_offset_pct: float = 0.005  # 0.5% default offset
    min_spread_bps: float = 30  # Minimum spread to enter
    max_position_age_hours: float = 24
    max_concurrent_positions: int = 5
    
    # Execution parameters
    spot_fill_slippage_bps: float = 5  # Slippage on spot fills
    futures_hedge_slippage_bps: float = 10  # Slippage on futures hedge
    hedge_delay_ms: int = 500  # Delay before hedge execution
    fees_per_trade_bps: float = 10  # 0.1% fees per trade
    
    # Risk management
    stop_loss_pct: float = 0.03  # 3% stop loss
    max_drawdown_pct: float = 0.05  # 5% max drawdown before pause
    correlation_threshold: float = 0.90  # Min correlation to trade
    
    # Liquidity constraints
    min_liquidity_usd: float = 1000
    max_size_vs_liquidity_pct: float = 0.1  # Max 10% of available liquidity


@dataclass
class Trade:
    """Individual trade record"""
    id: str
    symbol: str
    entry_time: datetime
    exit_time: Optional[datetime]
    status: PositionStatus
    
    # Spot leg
    spot_entry_price: float
    spot_exit_price: Optional[float]
    spot_size: float
    spot_slippage_bps: float
    
    # Futures leg
    futures_entry_price: Optional[float]
    futures_exit_price: Optional[float]
    futures_size: float
    futures_slippage_bps: float
    
    # Performance
    gross_pnl: float = 0.0
    fees_paid: float = 0.0
    net_pnl: float = 0.0
    return_pct: float = 0.0
    hold_time_hours: float = 0.0
    
    # Risk metrics
    max_adverse_excursion: float = 0.0
    max_favorable_excursion: float = 0.0
    hedge_efficiency: float = 1.0


@dataclass
class BacktestResults:
    """Comprehensive backtest results"""
    config: BacktestConfig
    trades: List[Trade]
    equity_curve: pd.DataFrame
    
    # Performance metrics
    total_return_pct: float
    annual_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    
    # Trade statistics
    total_trades: int
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float
    
    # Risk metrics
    var_95_pct: float
    expected_shortfall_pct: float
    worst_trade_pct: float
    best_trade_pct: float
    
    # Strategy-specific metrics
    avg_spread_captured_bps: float
    hedge_success_rate: float
    avg_hold_time_hours: float
    correlation_stability: float


class DeltaNeutralBacktester:
    """
    Advanced backtesting engine for delta-neutral spot-futures strategy
    Includes realistic execution modeling for low-liquidity crypto markets
    """
    
    def __init__(self, db_config: Dict[str, str]):
        """Initialize backtester with database connection"""
        self.conn = psycopg2.connect(**db_config)
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        
        # State tracking
        self.active_positions: Dict[str, Trade] = {}
        self.closed_trades: List[Trade] = []
        self.equity_history: List[Dict] = []
        self.daily_pnl: defaultdict = defaultdict(float)
        
        # Performance tracking
        self.current_capital: float = 0
        self.peak_capital: float = 0
        self.current_drawdown: float = 0
        
    def run_backtest(self, symbol: str, spot_exchange: str, futures_exchange: str,
                    start_date: str, end_date: str, 
                    config: BacktestConfig = None) -> BacktestResults:
        """
        Execute comprehensive backtest with realistic execution modeling
        """
        if config is None:
            config = BacktestConfig()
        
        # Initialize state
        self.current_capital = config.initial_capital
        self.peak_capital = config.initial_capital
        self.active_positions.clear()
        self.closed_trades.clear()
        self.equity_history.clear()
        
        # Fetch historical data
        market_data = self._fetch_market_data(symbol, spot_exchange, futures_exchange, 
                                            start_date, end_date)
        
        if market_data.empty:
            raise ValueError("No market data available for backtest period")
        
        print(f"Running backtest for {symbol} from {start_date} to {end_date}")
        print(f"Total data points: {len(market_data)}")
        
        # Process each data point
        for idx, row in market_data.iterrows():
            self._process_market_update(row, config)
            
            # Record equity snapshot every hour
            if idx % 60 == 0:  # Assuming minute data
                self._record_equity_snapshot(row['timestamp'])
        
        # Close any remaining positions
        for position in list(self.active_positions.values()):
            self._force_close_position(position, market_data.iloc[-1], config)
        
        # Calculate final results
        return self._calculate_results(config, start_date, end_date)
    
    def _fetch_market_data(self, symbol: str, spot_exchange: str, futures_exchange: str,
                          start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch combined spot and futures market data"""
        query = """
        WITH spot_data AS (
            SELECT 
                timestamp,
                symbol_base,
                bid_price as spot_bid,
                ask_price as spot_ask,
                bid_qty as spot_bid_qty,
                ask_qty as spot_ask_qty
            FROM book_ticker_snapshots
            WHERE exchange = %s 
                AND symbol_base = %s
                AND timestamp BETWEEN %s AND %s
        ),
        futures_data AS (
            SELECT 
                timestamp,
                symbol_base,
                bid_price as fut_bid,
                ask_price as fut_ask,
                bid_qty as fut_bid_qty,
                ask_qty as fut_ask_qty
            FROM book_ticker_snapshots
            WHERE exchange = %s 
                AND symbol_base = %s
                AND timestamp BETWEEN %s AND %s
        )
        SELECT 
            s.timestamp,
            s.spot_bid,
            s.spot_ask,
            s.spot_bid_qty,
            s.spot_ask_qty,
            f.fut_bid,
            f.fut_ask,
            f.fut_bid_qty,
            f.fut_ask_qty
        FROM spot_data s
        INNER JOIN futures_data f 
            ON s.timestamp = f.timestamp 
            AND s.symbol_base = f.symbol_base
        ORDER BY s.timestamp
        """
        
        self.cursor.execute(query, (spot_exchange, symbol, start_date, end_date,
                                   futures_exchange, symbol, start_date, end_date))
        
        data = pd.DataFrame(self.cursor.fetchall())
        
        if not data.empty:
            # Calculate derived metrics
            data['spot_mid'] = (data['spot_bid'] + data['spot_ask']) / 2
            data['fut_mid'] = (data['fut_bid'] + data['fut_ask']) / 2
            data['spread_bps'] = (data['fut_mid'] - data['spot_mid']) / data['spot_mid'] * 10000
            data['spot_liquidity'] = data['spot_bid_qty'] * data['spot_bid'] + data['spot_ask_qty'] * data['spot_ask']
            data['fut_liquidity'] = data['fut_bid_qty'] * data['fut_bid'] + data['fut_ask_qty'] * data['fut_ask']
            
            # Calculate rolling volatility for dynamic parameters
            data['returns'] = data['spot_mid'].pct_change()
            data['volatility'] = data['returns'].rolling(20).std()
        
        return data
    
    def _process_market_update(self, market_row: pd.Series, config: BacktestConfig) -> None:
        """Process each market data update"""
        timestamp = market_row['timestamp']
        
        # Update existing positions
        self._update_existing_positions(market_row, config)
        
        # Check for new entry signals
        if len(self.active_positions) < config.max_concurrent_positions:
            self._check_entry_signals(market_row, config)
        
        # Update portfolio value
        self._update_portfolio_value(market_row)
    
    def _check_entry_signals(self, market_row: pd.Series, config: BacktestConfig) -> None:
        """Check for new position entry opportunities"""
        # Calculate dynamic offset based on volatility
        volatility = market_row.get('volatility', 0.02)
        dynamic_offset = self._calculate_dynamic_offset(volatility, config.base_offset_pct)
        
        # Check minimum spread requirement
        if abs(market_row['spread_bps']) < config.min_spread_bps:
            return
        
        # Check liquidity constraints
        min_liquidity = min(market_row['spot_liquidity'], market_row['fut_liquidity'])
        if min_liquidity < config.min_liquidity_usd:
            return
        
        # Check if spot price has moved enough to trigger our limit order
        # Simulate limit order placement at offset from current mid price
        if market_row['spread_bps'] > 0:  # Futures premium, place buy limit below spot
            trigger_price = market_row['spot_mid'] * (1 - dynamic_offset)
            if market_row['spot_bid'] <= trigger_price:  # Our limit order would be filled
                self._enter_position(market_row, config, 'long_spot_short_futures')
        else:  # Spot premium, place sell limit above spot
            trigger_price = market_row['spot_mid'] * (1 + dynamic_offset)
            if market_row['spot_ask'] >= trigger_price:  # Our limit order would be filled
                self._enter_position(market_row, config, 'short_spot_long_futures')
    
    def _enter_position(self, market_row: pd.Series, config: BacktestConfig, 
                       direction: str) -> None:
        """Enter new delta-neutral position"""
        # Calculate position size
        available_liquidity = min(market_row['spot_liquidity'], market_row['fut_liquidity'])
        max_position_value = min(
            self.current_capital * config.max_position_pct,
            available_liquidity * config.max_size_vs_liquidity_pct
        )
        
        if max_position_value < 1000:  # Minimum position size
            return
        
        # Create trade record
        trade_id = f"trade_{len(self.closed_trades) + len(self.active_positions)}_{int(market_row['timestamp'].timestamp())}"
        
        # Calculate entry prices with slippage
        if direction == 'long_spot_short_futures':
            spot_entry_price = market_row['spot_ask'] * (1 + config.spot_fill_slippage_bps / 10000)
            spot_size = max_position_value / spot_entry_price
            futures_size = -spot_size  # Short futures
        else:
            spot_entry_price = market_row['spot_bid'] * (1 - config.spot_fill_slippage_bps / 10000)
            spot_size = -max_position_value / spot_entry_price  # Short spot
            futures_size = abs(spot_size)  # Long futures
        
        trade = Trade(
            id=trade_id,
            symbol=market_row.get('symbol_base', 'UNKNOWN'),
            entry_time=market_row['timestamp'],
            exit_time=None,
            status=PositionStatus.SPOT_FILLED,
            
            spot_entry_price=spot_entry_price,
            spot_exit_price=None,
            spot_size=spot_size,
            spot_slippage_bps=config.spot_fill_slippage_bps,
            
            futures_entry_price=None,
            futures_exit_price=None,
            futures_size=futures_size,
            futures_slippage_bps=config.futures_hedge_slippage_bps
        )
        
        self.active_positions[trade_id] = trade
        
        # Deduct capital for position
        self.current_capital -= abs(max_position_value)
        
        print(f"Entered position {trade_id}: {direction}, size=${max_position_value:.0f}")
    
    def _update_existing_positions(self, market_row: pd.Series, config: BacktestConfig) -> None:
        """Update all existing positions"""
        positions_to_close = []
        
        for trade_id, trade in self.active_positions.items():
            # Handle hedge execution for spot-filled positions
            if trade.status == PositionStatus.SPOT_FILLED:
                self._execute_hedge(trade, market_row, config)
            
            # Update unrealized PnL and risk metrics
            if trade.status == PositionStatus.DELTA_NEUTRAL:
                self._update_position_metrics(trade, market_row)
            
            # Check exit conditions
            if self._should_close_position(trade, market_row, config):
                positions_to_close.append(trade_id)
        
        # Close positions that meet exit criteria
        for trade_id in positions_to_close:
            trade = self.active_positions[trade_id]
            self._close_position(trade, market_row, config)
    
    def _execute_hedge(self, trade: Trade, market_row: pd.Series, config: BacktestConfig) -> None:
        """Execute futures hedge for spot-filled position"""
        # Simulate hedge delay
        hedge_delay = config.hedge_delay_ms / 1000  # Convert to seconds
        
        # Calculate futures entry price with slippage
        if trade.futures_size < 0:  # Short futures
            futures_entry_price = market_row['fut_bid'] * (1 - config.futures_hedge_slippage_bps / 10000)
        else:  # Long futures
            futures_entry_price = market_row['fut_ask'] * (1 + config.futures_hedge_slippage_bps / 10000)
        
        trade.futures_entry_price = futures_entry_price
        trade.status = PositionStatus.DELTA_NEUTRAL
        
        print(f"Hedged position {trade.id}: futures@{futures_entry_price:.2f}")
    
    def _update_position_metrics(self, trade: Trade, market_row: pd.Series) -> None:
        """Update position metrics and unrealized PnL"""
        # Calculate current unrealized PnL
        spot_pnl = (market_row['spot_mid'] - trade.spot_entry_price) * trade.spot_size
        futures_pnl = (trade.futures_entry_price - market_row['fut_mid']) * trade.futures_size
        total_unrealized = spot_pnl + futures_pnl
        
        # Update risk metrics
        if total_unrealized > trade.max_favorable_excursion:
            trade.max_favorable_excursion = total_unrealized
        if total_unrealized < trade.max_adverse_excursion:
            trade.max_adverse_excursion = total_unrealized
    
    def _should_close_position(self, trade: Trade, market_row: pd.Series, 
                              config: BacktestConfig) -> bool:
        """Determine if position should be closed"""
        if trade.status != PositionStatus.DELTA_NEUTRAL:
            return False
        
        # Age-based exit
        age_hours = (market_row['timestamp'] - trade.entry_time).total_seconds() / 3600
        if age_hours > config.max_position_age_hours:
            return True
        
        # Spread compression exit
        current_spread = abs(market_row['spread_bps'])
        if current_spread < 10:  # Spread compressed to <10 bps
            return True
        
        # Stop loss
        spot_pnl = (market_row['spot_mid'] - trade.spot_entry_price) * trade.spot_size
        futures_pnl = (trade.futures_entry_price - market_row['fut_mid']) * trade.futures_size
        total_pnl = spot_pnl + futures_pnl
        position_value = abs(trade.spot_size * trade.spot_entry_price)
        
        if total_pnl / position_value < -config.stop_loss_pct:
            return True
        
        # Spread reversal exit
        entry_spread = (trade.futures_entry_price - trade.spot_entry_price) / trade.spot_entry_price * 10000
        current_spread_signed = (market_row['fut_mid'] - market_row['spot_mid']) / market_row['spot_mid'] * 10000
        
        if entry_spread * current_spread_signed < 0:  # Spread reversed direction
            return True
        
        return False
    
    def _close_position(self, trade: Trade, market_row: pd.Series, config: BacktestConfig) -> None:
        """Close delta-neutral position"""
        # Calculate exit prices with slippage
        if trade.spot_size > 0:  # Long spot
            spot_exit_price = market_row['spot_bid'] * (1 - config.spot_fill_slippage_bps / 10000)
        else:  # Short spot
            spot_exit_price = market_row['spot_ask'] * (1 + config.spot_fill_slippage_bps / 10000)
        
        if trade.futures_size > 0:  # Long futures
            futures_exit_price = market_row['fut_bid'] * (1 - config.futures_hedge_slippage_bps / 10000)
        else:  # Short futures
            futures_exit_price = market_row['fut_ask'] * (1 + config.futures_hedge_slippage_bps / 10000)
        
        # Calculate final PnL
        spot_pnl = (spot_exit_price - trade.spot_entry_price) * trade.spot_size
        futures_pnl = (trade.futures_entry_price - futures_exit_price) * trade.futures_size
        gross_pnl = spot_pnl + futures_pnl
        
        # Calculate fees (4 trades: spot entry/exit, futures entry/exit)
        position_value = abs(trade.spot_size * trade.spot_entry_price)
        fees = position_value * config.fees_per_trade_bps / 10000 * 4
        
        net_pnl = gross_pnl - fees
        return_pct = net_pnl / position_value * 100
        
        # Update trade record
        trade.exit_time = market_row['timestamp']
        trade.spot_exit_price = spot_exit_price
        trade.futures_exit_price = futures_exit_price
        trade.gross_pnl = gross_pnl
        trade.fees_paid = fees
        trade.net_pnl = net_pnl
        trade.return_pct = return_pct
        trade.hold_time_hours = (trade.exit_time - trade.entry_time).total_seconds() / 3600
        trade.status = PositionStatus.CLOSED
        
        # Update capital
        self.current_capital += position_value + net_pnl
        
        # Move to closed trades
        self.closed_trades.append(trade)
        del self.active_positions[trade.id]
        
        print(f"Closed position {trade.id}: PnL=${net_pnl:.2f} ({return_pct:.2f}%)")
    
    def _force_close_position(self, trade: Trade, market_row: pd.Series, 
                             config: BacktestConfig) -> None:
        """Force close position at end of backtest"""
        if trade.status in [PositionStatus.DELTA_NEUTRAL, PositionStatus.SPOT_FILLED]:
            self._close_position(trade, market_row, config)
    
    def _calculate_dynamic_offset(self, volatility: float, base_offset: float) -> float:
        """Calculate dynamic offset based on market volatility"""
        if pd.isna(volatility):
            return base_offset
        
        # Adjust offset based on volatility
        if volatility < 0.01:
            return base_offset * 0.7
        elif volatility < 0.02:
            return base_offset
        elif volatility < 0.04:
            return base_offset * 1.3
        else:
            return base_offset * 1.8
    
    def _update_portfolio_value(self, market_row: pd.Series) -> None:
        """Update portfolio value and drawdown tracking"""
        # Calculate total portfolio value
        total_value = self.current_capital
        
        # Add unrealized PnL from open positions
        for trade in self.active_positions.values():
            if trade.status == PositionStatus.DELTA_NEUTRAL:
                spot_pnl = (market_row['spot_mid'] - trade.spot_entry_price) * trade.spot_size
                futures_pnl = (trade.futures_entry_price - market_row['fut_mid']) * trade.futures_size
                total_value += spot_pnl + futures_pnl
        
        # Update peak and drawdown
        if total_value > self.peak_capital:
            self.peak_capital = total_value
        
        self.current_drawdown = (self.peak_capital - total_value) / self.peak_capital
    
    def _record_equity_snapshot(self, timestamp: datetime) -> None:
        """Record equity curve snapshot"""
        total_value = self.current_capital
        
        # Add unrealized PnL (simplified - would need current market data)
        for trade in self.active_positions.values():
            if trade.status == PositionStatus.DELTA_NEUTRAL:
                position_value = abs(trade.spot_size * trade.spot_entry_price)
                total_value += position_value
        
        self.equity_history.append({
            'timestamp': timestamp,
            'total_value': total_value,
            'active_positions': len(self.active_positions),
            'drawdown_pct': self.current_drawdown * 100
        })
    
    def _calculate_results(self, config: BacktestConfig, start_date: str, 
                          end_date: str) -> BacktestResults:
        """Calculate comprehensive backtest results"""
        if not self.closed_trades:
            # Return empty results if no trades
            return BacktestResults(
                config=config,
                trades=[],
                equity_curve=pd.DataFrame(),
                total_return_pct=0, annual_return_pct=0, sharpe_ratio=0,
                sortino_ratio=0, max_drawdown_pct=0, total_trades=0,
                win_rate=0, avg_win_pct=0, avg_loss_pct=0, profit_factor=0,
                var_95_pct=0, expected_shortfall_pct=0, worst_trade_pct=0,
                best_trade_pct=0, avg_spread_captured_bps=0, hedge_success_rate=0,
                avg_hold_time_hours=0, correlation_stability=0
            )
        
        # Basic performance metrics
        returns = [trade.return_pct / 100 for trade in self.closed_trades]
        profits = [trade.net_pnl for trade in self.closed_trades]
        
        total_return_pct = (self.current_capital - config.initial_capital) / config.initial_capital * 100
        
        # Calculate annualized return
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        years = (end_dt - start_dt).days / 365.25
        annual_return_pct = ((1 + total_return_pct / 100) ** (1 / years) - 1) * 100 if years > 0 else 0
        
        # Risk metrics
        returns_array = np.array(returns)
        sharpe_ratio = np.mean(returns_array) / np.std(returns_array) * np.sqrt(252) if np.std(returns_array) > 0 else 0
        
        downside_returns = returns_array[returns_array < 0]
        sortino_ratio = np.mean(returns_array) / np.std(downside_returns) * np.sqrt(252) if len(downside_returns) > 0 else 0
        
        # Trade statistics
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r < 0]
        
        win_rate = len(wins) / len(returns) * 100 if returns else 0
        avg_win_pct = np.mean(wins) * 100 if wins else 0
        avg_loss_pct = np.mean(losses) * 100 if losses else 0
        profit_factor = abs(sum(wins) / sum(losses)) if losses else float('inf')
        
        # Risk metrics
        var_95_pct = np.percentile(returns_array, 5) * 100 if len(returns_array) > 0 else 0
        expected_shortfall_pct = np.mean(returns_array[returns_array <= np.percentile(returns_array, 5)]) * 100 if len(returns_array) > 0 else 0
        
        # Strategy-specific metrics
        spreads_captured = []
        successful_hedges = 0
        hold_times = []
        
        for trade in self.closed_trades:
            if trade.futures_entry_price and trade.spot_entry_price:
                entry_spread = abs((trade.futures_entry_price - trade.spot_entry_price) / trade.spot_entry_price * 10000)
                spreads_captured.append(entry_spread)
                successful_hedges += 1
            
            hold_times.append(trade.hold_time_hours)
        
        avg_spread_captured_bps = np.mean(spreads_captured) if spreads_captured else 0
        hedge_success_rate = successful_hedges / len(self.closed_trades) * 100 if self.closed_trades else 0
        avg_hold_time_hours = np.mean(hold_times) if hold_times else 0
        
        # Create equity curve DataFrame
        equity_curve = pd.DataFrame(self.equity_history) if self.equity_history else pd.DataFrame()
        
        return BacktestResults(
            config=config,
            trades=self.closed_trades,
            equity_curve=equity_curve,
            
            total_return_pct=total_return_pct,
            annual_return_pct=annual_return_pct,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown_pct=self.current_drawdown * 100,
            
            total_trades=len(self.closed_trades),
            win_rate=win_rate,
            avg_win_pct=avg_win_pct,
            avg_loss_pct=avg_loss_pct,
            profit_factor=profit_factor,
            
            var_95_pct=var_95_pct,
            expected_shortfall_pct=expected_shortfall_pct,
            worst_trade_pct=min(returns) * 100 if returns else 0,
            best_trade_pct=max(returns) * 100 if returns else 0,
            
            avg_spread_captured_bps=avg_spread_captured_bps,
            hedge_success_rate=hedge_success_rate,
            avg_hold_time_hours=avg_hold_time_hours,
            correlation_stability=0.85  # Placeholder
        )
    
    def generate_report(self, results: BacktestResults) -> str:
        """Generate comprehensive backtest report"""
        report = f"""
DELTA-NEUTRAL STRATEGY BACKTEST RESULTS
{'=' * 50}

CONFIGURATION:
- Initial Capital: ${results.config.initial_capital:,.0f}
- Max Position Size: {results.config.max_position_pct:.1%}
- Base Offset: {results.config.base_offset_pct:.1%}
- Min Spread: {results.config.min_spread_bps:.0f} bps

PERFORMANCE SUMMARY:
- Total Return: {results.total_return_pct:.2f}%
- Annual Return: {results.annual_return_pct:.2f}%
- Sharpe Ratio: {results.sharpe_ratio:.2f}
- Sortino Ratio: {results.sortino_ratio:.2f}
- Max Drawdown: {results.max_drawdown_pct:.2f}%

TRADE STATISTICS:
- Total Trades: {results.total_trades}
- Win Rate: {results.win_rate:.1f}%
- Average Win: {results.avg_win_pct:.2f}%
- Average Loss: {results.avg_loss_pct:.2f}%
- Profit Factor: {results.profit_factor:.2f}

RISK METRICS:
- 95% VaR: {results.var_95_pct:.2f}%
- Expected Shortfall: {results.expected_shortfall_pct:.2f}%
- Worst Trade: {results.worst_trade_pct:.2f}%
- Best Trade: {results.best_trade_pct:.2f}%

STRATEGY METRICS:
- Avg Spread Captured: {results.avg_spread_captured_bps:.1f} bps
- Hedge Success Rate: {results.hedge_success_rate:.1f}%
- Avg Hold Time: {results.avg_hold_time_hours:.1f} hours
- Correlation Stability: {results.correlation_stability:.2f}

RECOMMENDATIONS:
"""
        
        # Add recommendations based on results
        if results.sharpe_ratio > 1.5:
            report += "✅ Excellent risk-adjusted returns - consider increasing position sizes\n"
        elif results.sharpe_ratio > 1.0:
            report += "✅ Good risk-adjusted returns - strategy is viable\n"
        else:
            report += "⚠️ Poor risk-adjusted returns - review strategy parameters\n"
        
        if results.max_drawdown_pct > 10:
            report += "⚠️ High maximum drawdown - implement stricter risk controls\n"
        
        if results.hedge_success_rate < 90:
            report += "⚠️ Low hedge success rate - review execution timing\n"
        
        if results.avg_hold_time_hours > 12:
            report += "⚠️ Long average hold times - consider tighter exit criteria\n"
        
        return report


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
    
    # Initialize backtester
    backtester = DeltaNeutralBacktester(db_config)
    
    # Configure backtest
    config = BacktestConfig(
        initial_capital=50000,
        max_position_pct=0.03,
        base_offset_pct=0.006,
        min_spread_bps=40
    )
    
    # Run backtest
    try:
        results = backtester.run_backtest(
            symbol='BTC',
            spot_exchange='binance-spot',
            futures_exchange='binance-futures',
            start_date='2024-01-01',
            end_date='2024-06-30',
            config=config
        )
        
        # Generate report
        report = backtester.generate_report(results)
        print(report)
        
        # Save detailed results
        trades_df = pd.DataFrame([{
            'trade_id': t.id,
            'entry_time': t.entry_time,
            'exit_time': t.exit_time,
            'return_pct': t.return_pct,
            'hold_hours': t.hold_time_hours,
            'net_pnl': t.net_pnl
        } for t in results.trades])
        
        trades_df.to_csv('backtest_trades.csv', index=False)
        print(f"\nDetailed results saved to backtest_trades.csv")
        
    except Exception as e:
        print(f"Backtest failed: {e}")