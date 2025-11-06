from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Union

import numpy as np

from exchanges.structs import ExchangeEnum, Side

@dataclass
class ArbitrageTrade:
    timestamp: datetime
    buy_exchange: ExchangeEnum
    sell_exchange: ExchangeEnum
    buy_price: float
    sell_price: float
    qty: float
    pnl_pct: float
    pnl_usdt: float

class PerformanceMetrics:
    def __init__(self, total_pnl_usd: float = 0, total_pnl_pct: float = 0, win_rate: float = 0,
                 avg_trade_pnl: float = 0, max_drawdown: float = 0, sharpe_ratio: float = 0,
                 trades: List[ArbitrageTrade]=[]):
        self.total_pnl_usd = total_pnl_usd
        self.total_pnl_pct = total_pnl_pct
        self.win_rate = win_rate
        self.avg_trade_pnl = avg_trade_pnl
        self.max_drawdown = max_drawdown
        self.sharpe_ratio = sharpe_ratio
        self.trades = trades

    @property
    def total_trades(self):
        return len(self.trades)

class TradeEntry:
    def __init__(self, exchange: ExchangeEnum, side: Side, price: float, qty: float, fee_pct: float = 0.0):
        self.exchange = exchange
        self.side = side
        self.price = price
        self.fee_pct = fee_pct
        self.qty = qty

    @property
    def fees_usd(self) -> float:
        return self.price * self.qty * self.fee_pct / 100.0

    @property
    def cost(self) -> float:
        return self.price * self.qty


#             trades.append({
#                 'timestamp': timestamp,
#                 'buy_exchange': buy_trade.exchange,
#                 'sell_exchange': sell_trade.exchange,
#                 'buy_price': buy_trade.price,
#                 'sell_price': sell_trade.price,
#                 'qty': buy_trade.qty,
#                 'pnl_usd': pnl,
#                 'pnl_pct': pnl_pct
#             })



class PositionEntry:

    def __init__(self, entry_time: [datetime] = None):

        self.entry_time: datetime = Optional[entry_time]
        self.exit_time: Optional[datetime] = None
        self.trades: List[TradeEntry] = []

        self.balances: Dict[ExchangeEnum, float] = {}

        self.transfer_completion_time: Optional[datetime] = None
        self.arbitrage_trades: Dict[datetime, List[TradeEntry]] = {}

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
        """Calculate P&L in USD."""
        total_cost = 0.0
        total_proceeds = 0.0

        for t in self.trades:
            if t.side == Side.BUY:
                total_cost = t.cost + t.fees_usd
            else:
                total_proceeds = t.cost - t.fees_usd

        return total_proceeds - total_cost

    @property
    def pnl_pct(self) -> float:
        """Calculate P&L percentage."""
        total_cost = 0.0

        for t in self.trades:
            if t.side == Side.BUY:
                total_cost += t.cost + t.fees_usd

        if total_cost == 0:
            return 0.0

        return (self.pnl_usd / total_cost) * 100.0

    def start_transfer(self, transfer_delay_minutes: int, current_time: datetime,
                       from_exchange: ExchangeEnum = None, to_exchange: ExchangeEnum = None):
        """Initiate asset transfer with delay."""
        self.transfer_completion_time = current_time + timedelta(minutes=transfer_delay_minutes)
        self.balances[to_exchange] += self.balances.get(from_exchange, 0.0)
        self.balances[from_exchange] = 0.0
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
        DEPRECATED: Legacy performance metrics calculation.

        Performance metrics are now calculated internally by strategy signals_v2.
        This method is kept for backward compatibility only.


        Returns:
            Dictionary with performance metrics
        """

        if not self.arbitrage_trades:
            return PerformanceMetrics()

        # Calculate basic metrics
        total_pnl = self.pnl_usd
        total_pnl_pct = (self.pnl_usd / initial_capital_usd) * 100

        trades = []
        for timestamp, arb_trade in self.arbitrage_trades.items():
            if not arb_trade or len(arb_trade) != 2:
                continue
            buy_trade = next((t for t in arb_trade if t.side == Side.BUY), None)
            sell_trade = next((t for t in arb_trade if t.side == Side.SELL), None)
            pnl =  sell_trade.cost - sell_trade.fees_usd - buy_trade.cost - buy_trade.fees_usd
            pnl_pct = (pnl / buy_trade.cost) * 100 if buy_trade.cost != 0 else 0.0
            arb_trade = ArbitrageTrade(timestamp, buy_trade.exchange, sell_trade.exchange, buy_trade.price,
                                       sell_trade.price, buy_trade.qty, pnl, pnl_pct)
            trades.append(arb_trade)

        winning_trades = [t for t in trades if t.pnl_usdt > 0]
        win_rate = len(winning_trades) / len(trades) * 100

        avg_trade_pnl = total_pnl / len(trades)

        # Calculate drawdown (simplified)
        cumulative_pnl = []
        running_pnl = 0
        for trade in trades:
            running_pnl += trade.pnl_usdt
            cumulative_pnl.append(running_pnl)

        if cumulative_pnl:
            peak = cumulative_pnl[0]
            max_drawdown = 0
            for pnl in cumulative_pnl:
                if pnl > peak:
                    peak = pnl
                drawdown = (peak - pnl) / initial_capital_usd * 100
                max_drawdown = max(max_drawdown, drawdown)
        else:
            max_drawdown = 0

        # Simplified Sharpe ratio calculation
        if len(trades) > 1:
            trade_returns = [t.pnl_usdt / initial_capital_usd for t in trades]
            avg_return = np.mean(trade_returns)
            std_return = np.std(trade_returns)
            sharpe_ratio = avg_return / std_return if std_return > 0 else 0
        else:
            sharpe_ratio = 0

        return PerformanceMetrics(
            total_pnl_usd=total_pnl,
            total_pnl_pct=total_pnl_pct,
            win_rate=win_rate,
            avg_trade_pnl=avg_trade_pnl,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            trades=trades
        )


@dataclass
class BacktestingParams:
    initial_balance_usd: float = 1000.0
    position_size_usd: float = 100.0
    transfer_delay_minutes: int = 10
