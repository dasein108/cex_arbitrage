"""
Unified Data Manager for Example Scripts

Consolidates orderbook, trade, and balance data management functionality
that was duplicated across OrderBookManager, AccountDataManager, and WebSocketDataCollector.
"""

import time
from typing import Dict, List, Any, Optional
from collections import defaultdict

from exchanges.structs.common import Symbol, OrderBook, Trade, AssetBalance, BookTicker
from exchanges.structs.types import AssetName
from infrastructure.logging import HFTLoggerInterface, get_logger


class UnifiedDataManager:
    """Single data manager for all types of exchange data."""
    
    def __init__(self, exchange_name: str, logger: Optional[HFTLoggerInterface] = None):
        self.exchange_name = exchange_name.upper()
        self.logger = logger or get_logger(f'data_manager.{exchange_name.lower()}')
        
        # Data storage
        self.orderbooks: Dict[Symbol, OrderBook] = {}
        self.trades: Dict[Symbol, List[Trade]] = {}
        self.balances: Dict[AssetName, AssetBalance] = {}
        self.book_tickers: Dict[Symbol, BookTicker] = {}
        
        # Metrics tracking
        self.update_counts = defaultdict(lambda: defaultdict(int))
        self.error_count = 0
        self.connection_events = []
        
        # Settings
        self.max_trades_per_symbol = 100
        self.max_connection_events = 50

    async def handle_orderbook_update(self, orderbook: OrderBook) -> None:
        """Handle orderbook updates and collect metrics."""
        symbol = orderbook.symbol
        
        # Store latest orderbook
        self.orderbooks[symbol] = orderbook
        
        # Track update counts
        self.update_counts[symbol]["orderbook"] += 1
        
        # Log periodic updates (every 10th update to reduce verbosity)
        if self.update_counts[symbol]["orderbook"] % 10 == 1:
            spread = None
            if orderbook.bids and orderbook.asks:
                spread = orderbook.asks[0].price - orderbook.bids[0].price
            
            self.logger.info("📊 Orderbook update",
                           exchange=self.exchange_name,
                           symbol=f"{symbol.base}/{symbol.quote}",
                           update_number=self.update_counts[symbol]["orderbook"],
                           best_bid=orderbook.bids[0].price if orderbook.bids else None,
                           best_ask=orderbook.asks[0].price if orderbook.asks else None,
                           spread=spread,
                           bid_count=len(orderbook.bids),
                           ask_count=len(orderbook.asks))

    async def handle_trade_update(self, trade: Trade) -> None:
        """Handle trade updates and collect metrics."""
        symbol = trade.symbol
        
        # Initialize trade list if needed
        if symbol not in self.trades:
            self.trades[symbol] = []
        
        # Add trade
        self.trades[symbol].append(trade)
        
        # Limit trade history
        if len(self.trades[symbol]) > self.max_trades_per_symbol:
            self.trades[symbol] = self.trades[symbol][-self.max_trades_per_symbol:]
        
        # Track update counts
        self.update_counts[symbol]["trades"] += 1
        
        # Log trade
        self.logger.info("💹 Trade update",
                       exchange=self.exchange_name,
                       symbol=f"{symbol.base}/{symbol.quote}",
                       side=trade.side.name,
                       quantity=trade.quantity,
                       price=trade.price,
                       timestamp=trade.timestamp)

    async def handle_balance_update(self, balance: AssetBalance) -> None:
        """Handle balance updates and collect metrics."""
        asset = balance.asset
        
        # Store balance
        self.balances[asset] = balance
        
        # Track update counts
        self.update_counts[asset]["balance"] += 1
        
        # Log balance changes (only non-zero balances)
        if balance.free > 0 or balance.locked > 0:
            self.logger.info("💰 Balance update",
                           exchange=self.exchange_name,
                           asset=asset,
                           free=balance.free,
                           locked=balance.locked,
                           total=balance.total)

    async def handle_book_ticker_update(self, book_ticker: BookTicker) -> None:
        """Handle book ticker updates and collect metrics."""
        symbol = book_ticker.symbol
        
        # Store book ticker
        self.book_tickers[symbol] = book_ticker
        
        # Track update counts
        self.update_counts[symbol]["book_ticker"] += 1
        
        # Log periodic updates (every 5th update to reduce verbosity)
        if self.update_counts[symbol]["book_ticker"] % 5 == 1:
            spread = book_ticker.ask_price - book_ticker.bid_price
            spread_percentage = (spread / book_ticker.bid_price) * 100 if book_ticker.bid_price else 0
            
            self.logger.info("📈 Book ticker update",
                           exchange=self.exchange_name,
                           symbol=f"{symbol.base}/{symbol.quote}",
                           update_number=self.update_counts[symbol]["book_ticker"],
                           bid_price=book_ticker.bid_price,
                           bid_quantity=book_ticker.bid_quantity,
                           ask_price=book_ticker.ask_price,
                           ask_quantity=book_ticker.ask_quantity,
                           spread=spread,
                           spread_percentage=spread_percentage)

    def handle_connection_event(self, event_type: str, details: Any = None) -> None:
        """Handle connection state changes."""
        event = {
            "timestamp": time.time(),
            "event_type": event_type,
            "details": details
        }
        
        self.connection_events.append(event)
        
        # Limit connection event history
        if len(self.connection_events) > self.max_connection_events:
            self.connection_events = self.connection_events[-self.max_connection_events:]
        
        self.logger.info("🔗 Connection event",
                       exchange=self.exchange_name,
                       event_type=event_type,
                       details=details)

    def handle_error(self, error: Exception, context: str = "") -> None:
        """Handle errors and update error count."""
        self.error_count += 1
        self.logger.error("❌ Error occurred",
                        exchange=self.exchange_name,
                        error_type=type(error).__name__,
                        error_message=str(error),
                        context=context,
                        total_errors=self.error_count)

    # Data retrieval methods
    
    def get_orderbook(self, symbol: Symbol) -> Optional[OrderBook]:
        """Get latest orderbook for symbol."""
        return self.orderbooks.get(symbol)
    
    def get_trades(self, symbol: Symbol, limit: int = 10) -> List[Trade]:
        """Get recent trades for symbol."""
        trades = self.trades.get(symbol, [])
        return trades[-limit:] if trades else []
    
    def get_balance(self, asset: AssetName) -> Optional[AssetBalance]:
        """Get balance for asset."""
        return self.balances.get(asset)
    
    def get_all_balances(self) -> Dict[AssetName, AssetBalance]:
        """Get all balances."""
        return self.balances.copy()
    
    def get_book_ticker(self, symbol: Symbol) -> Optional[BookTicker]:
        """Get book ticker for symbol."""
        return self.book_tickers.get(symbol)
    
    def get_non_zero_balances(self) -> Dict[AssetName, AssetBalance]:
        """Get only balances with non-zero amounts."""
        return {
            asset: balance for asset, balance in self.balances.items()
            if balance.free > 0 or balance.locked > 0
        }
    
    def get_recent_connection_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent connection events."""
        return self.connection_events[-limit:] if self.connection_events else []
    
    def get_summary(self) -> Dict[str, Any]:
        """Get comprehensive summary of all collected data."""
        total_orderbook_updates = sum(
            counts["orderbook"] for counts in self.update_counts.values()
        )
        total_trade_updates = sum(
            counts["trades"] for counts in self.update_counts.values()  
        )
        total_balance_updates = sum(
            counts["balance"] for counts in self.update_counts.values()
        )
        total_book_ticker_updates = sum(
            counts["book_ticker"] for counts in self.update_counts.values()
        )
        
        return {
            'exchange': self.exchange_name,
            'orderbook_symbols': len(self.orderbooks),
            'trade_symbols': len(self.trades),
            'balance_assets': len(self.balances),
            'book_ticker_symbols': len(self.book_tickers),
            'non_zero_balances': len(self.get_non_zero_balances()),
            'total_orderbook_updates': total_orderbook_updates,
            'total_trade_updates': total_trade_updates,
            'total_balance_updates': total_balance_updates,
            'total_book_ticker_updates': total_book_ticker_updates,
            'total_trades': sum(len(trades) for trades in self.trades.values()),
            'error_count': self.error_count,
            'connection_events': len(self.connection_events)
        }
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance-focused summary for monitoring."""
        recent_events = len([
            event for event in self.connection_events
            if time.time() - event['timestamp'] < 300  # Last 5 minutes
        ])
        
        return {
            'data_collection_active': len(self.orderbooks) > 0 or len(self.trades) > 0,
            'recent_connection_events': recent_events,
            'error_rate': self.error_count / max(1, len(self.connection_events)),
            'symbols_with_data': len(set(self.orderbooks.keys()) | set(self.trades.keys())),
            'last_update_time': max(
                [ob.timestamp for ob in self.orderbooks.values()] + [0]
            ) if self.orderbooks else 0
        }