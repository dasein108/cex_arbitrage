"""
Trading Signals V2 - Core Entity Definitions

This module contains the core data structures for cryptocurrency arbitrage trading
between exchanges, including trade tracking, position management, and performance metrics.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Union
from decimal import Decimal

import numpy as np

from exchanges.structs import ExchangeEnum, Side

@dataclass
class ArbitrageTrade:
    """
    Represents a completed arbitrage trade between two exchanges.
    
    Attributes:
        timestamp: When the arbitrage trade was executed
        buy_exchange: Exchange where the asset was purchased
        sell_exchange: Exchange where the asset was sold
        buy_price: Price paid for the asset (including fees)
        sell_price: Price received for the asset (after fees)
        qty: Quantity of asset traded
        pnl_pct: Profit/loss as percentage of invested capital
        pnl_usdt: Profit/loss in USDT terms
    """
    timestamp: datetime
    buy_exchange: ExchangeEnum
    sell_exchange: ExchangeEnum
    buy_price: float
    sell_price: float
    qty: float
    pnl_pct: float
    pnl_usdt: float

class PerformanceMetrics:
    """
    Comprehensive performance metrics for arbitrage trading strategies.
    
    This class encapsulates all key performance indicators including profitability,
    risk metrics, and trade statistics for backtesting and live trading analysis.
    """
    
    def __init__(self, total_pnl_usd: float = 0, total_pnl_pct: float = 0, win_rate: float = 0,
                 avg_trade_pnl: float = 0, max_drawdown: float = 0, sharpe_ratio: float = 0,
                 trades: List[ArbitrageTrade] = None, trade_freq: float = 0):
        """
        Initialize performance metrics.
        
        Args:
            total_pnl_usd: Total profit/loss in USD
            total_pnl_pct: Total return as percentage of initial capital
            win_rate: Percentage of profitable trades (0-100)
            avg_trade_pnl: Average profit/loss per trade in USD
            max_drawdown: Maximum drawdown as percentage of capital
            sharpe_ratio: Risk-adjusted return metric
            trades: List of individual arbitrage trades
        """
        self.total_pnl_usd = total_pnl_usd
        self.total_pnl_pct = total_pnl_pct
        self.win_rate = win_rate
        self.avg_trade_pnl = avg_trade_pnl
        self.max_drawdown = max_drawdown
        self.sharpe_ratio = sharpe_ratio
        self.trades = trades or []
        self.trade_freq = trade_freq

    @property
    def total_trades(self) -> int:
        """Total number of completed trades."""
        return len(self.trades)

class TradeEntry:
    """
    Represents a single trade execution on an exchange.
    
    This class models individual buy/sell operations including exchange fees,
    slippage costs, and other execution costs for accurate P&L calculation.
    """
    
    def __init__(self, exchange: ExchangeEnum, side: Side, price: float, qty: float, 
                 fee_pct: float = 0.1, slippage_pct: float = 0.05, transfer_fee_usd: float = 0.0):
        """
        Initialize a trade entry.
        
        Args:
            exchange: Exchange where trade was executed
            side: BUY or SELL
            price: Execution price per unit
            qty: Quantity traded
            fee_pct: Trading fee as percentage (default: 0.1% typical for major exchanges)
            slippage_pct: Price slippage as percentage (default: 0.05%)
            transfer_fee_usd: Fixed transfer fee in USD for cross-exchange moves
        """
        self.exchange = exchange
        self.side = side
        self.price = price
        self.qty = qty
        self.fee_pct = fee_pct
        self.slippage_pct = slippage_pct
        self.transfer_fee_usd = transfer_fee_usd

    @property
    def effective_price(self) -> float:
        """Price after accounting for slippage."""
        slippage_factor = 1 + (self.slippage_pct / 100.0)
        if self.side == Side.BUY:
            return self.price * slippage_factor  # Buy higher due to slippage
        else:
            return self.price / slippage_factor  # Sell lower due to slippage

    @property
    def trading_fees_usd(self) -> float:
        """Trading fees in USD."""
        return self.effective_price * self.qty * self.fee_pct / 100.0

    @property
    def total_fees_usd(self) -> float:
        """Total fees including trading and transfer fees."""
        return self.trading_fees_usd + self.transfer_fee_usd

    @property
    def gross_value(self) -> float:
        """Gross trade value before fees and slippage."""
        return self.price * self.qty

    @property
    def net_value(self) -> float:
        """Net trade value after fees and slippage."""
        if self.side == Side.BUY:
            return -(self.effective_price * self.qty + self.total_fees_usd)  # Cash outflow
        else:
            return self.effective_price * self.qty - self.total_fees_usd  # Cash inflow


class PositionEntry:
    """
    Manages a complete arbitrage position including all trades, transfers, and P&L tracking.
    
    This class handles the complex lifecycle of cross-exchange arbitrage positions,
    including balance management, transfer delays, and accurate profit calculation.
    """

    def __init__(self, entry_time: Optional[datetime] = None):
        """
        Initialize a new arbitrage position.
        
        Args:
            entry_time: When the position was opened (defaults to current time)
        """
        self.entry_time: Optional[datetime] = entry_time
        self.exit_time: Optional[datetime] = None
        self.trades: List[TradeEntry] = []
        self.balances: Dict[ExchangeEnum, float] = {}
        self.transfer_completion_time: Optional[datetime] = None
        self.arbitrage_trades: Dict[datetime, List[TradeEntry]] = {}
        
        # Enhanced tracking for realistic costs
        self.total_transfer_fees: float = 0.0
        self.failed_trades: int = 0
        self.execution_delays: List[float] = []

    def add_trade(self, trade: Union[TradeEntry, List[TradeEntry]]):
        trades = trade if isinstance(trade, list) else [trade]

        for t in trades:
            if t.exchange not in self.balances:
                self.balances[t.exchange] = 0.0

            if t.side == Side.BUY:
                self.balances[t.exchange] += t.qty
            else:
                self.balances[t.exchange] -= t.qty

        self.trades.extend(trades)

        return self

    def add_arbitrage_trade(self, timestamp: datetime, trades: List[TradeEntry]):
        self.arbitrage_trades[timestamp] = trades
        self.add_trade(trades)

        return self

    @property
    def pnl_usd(self) -> float:
        """
        Calculate total P&L in USD using correct arbitrage accounting.
        
        Returns:
            Net profit/loss including all trading fees, slippage, and transfer costs
        """
        # Sum all net cash flows from trades
        total_net_value = sum(trade.net_value for trade in self.trades)
        
        # Subtract additional transfer fees not included in individual trades
        total_net_value -= self.total_transfer_fees
        
        return total_net_value

    @property
    def pnl_pct(self) -> float:
        """
        Calculate P&L percentage based on total capital deployed.
        
        Returns:
            Percentage return on invested capital
        """
        # Calculate total capital invested (absolute value of buy trades)
        total_invested = sum(abs(trade.net_value) for trade in self.trades if trade.side == Side.BUY)
        
        if total_invested == 0:
            return 0.0

        return (self.pnl_usd / total_invested) * 100.0

    def start_transfer(self, transfer_delay_minutes: int, current_time: datetime,
                       from_exchange: ExchangeEnum = None, to_exchange: ExchangeEnum = None,
                       transfer_fee_usd: float = 0.0):
        """
        Initiate asset transfer between exchanges with realistic costs and delays.
        
        Args:
            transfer_delay_minutes: Time for transfer to complete (realistic: 1-5 minutes)
            current_time: Current timestamp
            from_exchange: Source exchange
            to_exchange: Destination exchange  
            transfer_fee_usd: Transfer fee in USD (typical: $1-10)
        """
        self.transfer_completion_time = current_time + timedelta(minutes=transfer_delay_minutes)
        
        # Transfer balance with fees
        transfer_amount = self.balances.get(from_exchange, 0.0)
        if transfer_amount > 0:
            self.balances[to_exchange] = self.balances.get(to_exchange, 0.0) + transfer_amount
            self.balances[from_exchange] = 0.0
            self.total_transfer_fees += transfer_fee_usd
            
        return self

    def is_transfer_in_progress(self, current_time: datetime) -> bool:
        """Check if transfer is in progress."""
        if self.transfer_completion_time is None:
            return False

        return current_time < self.transfer_completion_time

    def complete_transfer(self) -> None:
        """Complete the asset transfer."""
        self.transfer_completion_time = None

    def close_position(self, exit_time: datetime, exit_trades: List[TradeEntry]):
        """Close position with exit trades."""
        self.exit_time = exit_time
        if self.trades is None:
            self.trades = []
        self.trades.extend(exit_trades)

    def get_performance_metrics(self, initial_capital_usd: float) -> PerformanceMetrics:
        """
        Calculate accurate performance metrics for arbitrage trading.
        
        This method provides corrected P&L calculations, realistic win rates,
        and proper risk-adjusted metrics for arbitrage strategies.

        Args:
            initial_capital_usd: Initial capital invested
            
        Returns:
            PerformanceMetrics with corrected calculations
        """

        if not self.arbitrage_trades:
            return PerformanceMetrics()

        trades = []
        total_trade_pnl = 0.0  # Sum of individual arbitrage trade P&Ls
        
        for timestamp, arb_trades_list in self.arbitrage_trades.items():
            if not arb_trades_list or len(arb_trades_list) != 2:
                continue
                
            buy_trade = next((t for t in arb_trades_list if t.side == Side.BUY), None)
            sell_trade = next((t for t in arb_trades_list if t.side == Side.SELL), None)
            
            if not buy_trade or not sell_trade:
                continue
                
            # Calculate correct arbitrage P&L using net values
            trade_pnl = sell_trade.net_value + buy_trade.net_value  # buy_trade.net_value is negative
            total_trade_pnl += trade_pnl  # ✅ FIX: Sum individual trade P&Ls
            
            # Calculate percentage based on invested capital
            invested_capital = abs(buy_trade.net_value)
            pnl_pct = (trade_pnl / invested_capital) * 100 if invested_capital != 0 else 0.0
            
            arbitrage_trade = ArbitrageTrade(
                timestamp=timestamp,
                buy_exchange=buy_trade.exchange,
                sell_exchange=sell_trade.exchange,
                buy_price=buy_trade.effective_price,  # Use effective price including slippage
                sell_price=sell_trade.effective_price,
                qty=buy_trade.qty,
                pnl_pct=pnl_pct,
                pnl_usdt=trade_pnl
            )
            trades.append(arbitrage_trade)

        if not trades:
            return PerformanceMetrics()
            
        # ✅ FIX: Use sum of arbitrage trades P&L, not total portfolio position
        total_arbitrage_pnl = total_trade_pnl - self.total_transfer_fees
        total_pnl_pct = (total_arbitrage_pnl / initial_capital_usd) * 100
        
        # ✅ FIX: Calculate win rate based on actual completed trades only
        successful_trades = [t for t in trades if t.pnl_usdt > 0]
        win_rate = (len(successful_trades) / len(trades)) * 100 if trades else 0
        
        # ✅ FIX: Use total arbitrage P&L for average calculation
        avg_trade_pnl = total_arbitrage_pnl / len(trades) if trades else 0

        # Enhanced drawdown calculation with realistic volatility
        cumulative_pnl = []
        running_pnl = 0
        for trade in trades:
            running_pnl += trade.pnl_usdt
            cumulative_pnl.append(running_pnl)

        max_drawdown = 0
        if cumulative_pnl:
            peak = 0  # Start from break-even
            for pnl in cumulative_pnl:
                peak = max(peak, pnl)
                if peak > 0:  # Only calculate drawdown if there's been profit
                    drawdown = (peak - pnl) / initial_capital_usd * 100
                    max_drawdown = max(max_drawdown, drawdown)
                elif pnl < 0:  # Account for negative cumulative P&L
                    drawdown = abs(pnl) / initial_capital_usd * 100
                    max_drawdown = max(max_drawdown, drawdown)

        # ✅ FIX: Corrected Sharpe ratio calculation 
        if len(trades) > 1 and total_arbitrage_pnl != 0:
            trade_returns = [t.pnl_usdt / initial_capital_usd for t in trades]
            avg_return = np.mean(trade_returns)
            std_return = np.std(trade_returns, ddof=1)  # Sample standard deviation
            
            # Add minimum volatility floor for arbitrage strategies
            min_volatility = 0.001  # 0.1% minimum volatility (reduced for better calculation)
            std_return = max(std_return, min_volatility)
            
            # Calculate Sharpe ratio without annualization for short periods
            sharpe_ratio = avg_return / std_return if std_return > 0 else 0
            
            # Cap Sharpe ratio at reasonable levels for arbitrage (should be 0.5-2.0)
            sharpe_ratio = max(-5.0, min(5.0, sharpe_ratio))
        else:
            sharpe_ratio = 0

        delays = np.diff([t.timestamp.timestamp() for t in trades])  # seconds
        delays_minutes = delays / 60  # convert to minutes

        mean_delay = np.mean(delays_minutes)

        return PerformanceMetrics(
            total_pnl_usd=total_arbitrage_pnl,  # ✅ FIX: Use arbitrage P&L, not position value
            total_pnl_pct=total_pnl_pct,
            win_rate=win_rate,
            avg_trade_pnl=avg_trade_pnl,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            trades=trades,
            trade_freq=mean_delay
        )


@dataclass
class BacktestingParams:
    """
    Configuration parameters for backtesting arbitrage strategies.
    
    These parameters control the simulation environment and should be set to
    realistic values based on actual exchange capabilities and costs.
    """
    initial_balance_usd: float = 1000.0      # Starting capital
    position_size_usd: float = 100.0         # Size per arbitrage opportunity
    transfer_delay_minutes: int = 5           # Realistic transfer time (was 10, now 5)
    transfer_fee_usd: float = 0          # Fixed transfer cost per move
    slippage_pct: float = 0.05               # Expected slippage (0.05% typical)
    execution_failure_rate: float = 0.10     # 10% of trades fail to execute
    custom: Dict[str, float] = field(default_factory=dict)
