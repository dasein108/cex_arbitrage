"""
Real-time Analytics Engine for Data Collector

Processes book ticker updates to detect arbitrage opportunities and market conditions.
Provides real-time analytics logging for monitoring market health and opportunities.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Set
from dataclasses import dataclass

from exchanges.structs.common import Symbol, BookTicker, Trade
from applications.data_collection.config import AnalyticsConfig


@dataclass
class ArbitrageOpportunity:
    """Detected arbitrage opportunity between exchanges."""
    symbol: Symbol
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    price_difference: float
    profit_percentage: float
    timestamp: datetime
    
    def __str__(self) -> str:
        return (
            f"{self.symbol.base}/{self.symbol.quote} - "
            f"{self.buy_exchange}: ${self.buy_price:.4f} vs "
            f"{self.sell_exchange}: ${self.sell_price:.4f} "
            f"(Opportunity: ${self.price_difference:.4f}, {self.profit_percentage:.4f}%)"
        )


@dataclass
class SpreadAnalysis:
    """Spread analysis for a symbol on a specific exchange."""
    symbol: Symbol
    exchange: str
    spread_absolute: float
    spread_percentage: float
    bid_price: float
    ask_price: float
    bid_volume: float
    ask_volume: float
    timestamp: datetime


@dataclass
class VolumeAlert:
    """Volume alert for low liquidity conditions."""
    symbol: Symbol
    exchange: str
    bid_volume_usd: float
    ask_volume_usd: float
    total_volume_usd: float
    threshold_usd: float
    timestamp: datetime


@dataclass
class TradeAnalysis:
    """Trade analysis for volume and momentum tracking."""
    symbol: Symbol
    exchange: str
    total_volume: float
    trade_count: int
    avg_price: float
    price_momentum: float  # Price change rate
    volume_usd: float
    timestamp: datetime


@dataclass
class MarketHealthSummary:
    """Overall market health summary."""
    total_pairs: int
    active_pairs: int
    total_opportunities: int
    avg_spread_percentage: float
    connection_status: Dict[str, bool]
    timestamp: datetime


class RealTimeAnalytics:
    """
    Real-time analytics engine for processing book ticker data.
    
    Features:
    - Detects arbitrage opportunities between exchanges
    - Calculates and alerts on spread conditions
    - Monitors volume and liquidity
    - Processes trade data for momentum analysis
    - Provides market health summaries
    - Logs meaningful analytics information
    """
    
    def __init__(self, config: AnalyticsConfig):
        """
        Initialize real-time analytics engine.
        
        Args:
            config: Analytics configuration
        """
        self.config = config
        from infrastructure.logging import get_logger
        self.logger = get_logger('data_collector.analytics')
        
        # Latest book ticker data: {exchange_symbol: BookTicker}
        self._latest_tickers: Dict[str, BookTicker] = {}
        
        # Recent trade data: {exchange_symbol: List[Trade]} (keep recent trades)
        self._recent_trades: Dict[str, List[Trade]] = {}
        
        # Trade analytics tracking
        self._trade_count = 0
        self._last_trade_cleanup = datetime.now()
        
        # Detected opportunities cache
        self._recent_opportunities: List[ArbitrageOpportunity] = []
        self._last_opportunity_cleanup = datetime.now()
        
        # Statistics tracking
        self._update_count = 0
        self._opportunity_count = 0
        self._last_summary_time = datetime.now()
        
        # Known symbols for cross-exchange analysis
        self._active_symbols: Set[Symbol] = set()
        
        self.logger.info("Real-time analytics engine initialized")
    
    async def on_book_ticker_update(self, exchange: str, symbol: Symbol, book_ticker: BookTicker) -> None:
        """
        Process a book ticker update and perform real-time analysis.
        
        Args:
            exchange: Exchange name
            symbol: Updated symbol
            book_ticker: Book ticker data
        """
        try:
            self._update_count += 1
            
            # Store latest ticker
            cache_key = f"{exchange.lower()}_{symbol}"
            self._latest_tickers[cache_key] = book_ticker
            self._active_symbols.add(symbol)
            
            # Perform analysis
            await self._analyze_spread(exchange, symbol, book_ticker)
            # await self._analyze_volume(exchange, symbol, book_ticker)
            await self._analyze_arbitrage_opportunities(symbol)
            
            # Periodic summary
            if self._should_log_summary():
                await self._log_market_health_summary()
            
        except Exception as e:
            self.logger.error(f"Error processing book ticker update for {exchange}:{symbol}: {e}")
    
    async def on_trade_update(self, exchange: str, symbol: Symbol, trade: Trade) -> None:
        """
        Process a trade update and perform real-time trade analysis.
        
        Args:
            exchange: Exchange name
            symbol: Updated symbol
            trade: Trade data
        """
        try:
            self._trade_count += 1
            
            # Store recent trade
            cache_key = f"{exchange.lower()}_{symbol}"
            if cache_key not in self._recent_trades:
                self._recent_trades[cache_key] = []
            
            self._recent_trades[cache_key].append(trade)
            self._active_symbols.add(symbol)
            
            # Keep only recent trades (last 5 minutes)
            cutoff_time = datetime.now() - timedelta(minutes=5)
            cutoff_timestamp = int(cutoff_time.timestamp() * 1000)
            self._recent_trades[cache_key] = [
                t for t in self._recent_trades[cache_key] 
                if t.timestamp and t.timestamp > cutoff_timestamp
            ]
            
            # Perform trade analysis
            await self._analyze_trade_volume(exchange, symbol)
            await self._analyze_price_momentum(exchange, symbol)
            
            # Periodic cleanup
            if datetime.now() - self._last_trade_cleanup > timedelta(minutes=1):
                await self._cleanup_old_trades()
            
        except Exception as e:
            self.logger.error(f"Error processing trade update for {exchange}:{symbol}: {e}")
    
    async def _analyze_spread(self, exchange: str, symbol: Symbol, book_ticker: BookTicker) -> None:
        """
        Analyze spread conditions for a symbol.
        
        Args:
            exchange: Exchange name
            symbol: Symbol
            book_ticker: Book ticker data
        """
        try:
            spread_absolute = book_ticker.ask_price - book_ticker.bid_price
            spread_percentage = (spread_absolute / book_ticker.bid_price) * 100
            
            # Check for spread alerts
            if spread_percentage > (self.config.spread_alert_threshold * 100):
                self.logger.warning(
                    f"[ANALYTICS] Spread Alert: {symbol.base}/{symbol.quote} on {exchange.upper()} - "
                    f"Spread: {spread_percentage:.3f}% (${spread_absolute:.6f}), "
                    f"Bid: ${book_ticker.bid_price:.6f}, Ask: ${book_ticker.ask_price:.6f}"
                )
        
        except Exception as e:
            self.logger.error(f"Error analyzing spread for {exchange}:{symbol}: {e}")
    
    async def _analyze_volume(self, exchange: str, symbol: Symbol, book_ticker: BookTicker) -> None:
        """
        Analyze volume and liquidity conditions.
        
        Args:
            exchange: Exchange name
            symbol: Symbol
            book_ticker: Book ticker data
        """
        try:
            # Calculate USD volumes (approximate)
            bid_volume_usd = book_ticker.bid_price * book_ticker.bid_quantity
            ask_volume_usd = book_ticker.ask_price * book_ticker.ask_quantity
            total_volume_usd = bid_volume_usd + ask_volume_usd
            
            # Check for low volume alerts
            if total_volume_usd < self.config.volume_threshold:
                self.logger.warning(
                    f"[ANALYTICS] Volume Alert: {symbol.base}/{symbol.quote} on {exchange.upper()} - "
                    f"Low liquidity detected (Bid: ${bid_volume_usd:.0f}, Ask: ${ask_volume_usd:.0f}, "
                    f"Total: ${total_volume_usd:.0f})"
                )
        
        except Exception as e:
            self.logger.error(f"Error analyzing volume for {exchange}:{symbol}: {e}")
    
    async def _analyze_arbitrage_opportunities(self, symbol: Symbol) -> None:
        """
        Analyze arbitrage opportunities for a symbol across exchanges.
        
        Args:
            symbol: Symbol to analyze
        """
        try:
            # Get tickers for this symbol from all exchanges
            symbol_tickers = {}
            for cache_key, ticker in self._latest_tickers.items():
                if ticker.symbol == symbol:
                    exchange = cache_key.split("_", 1)[0]
                    symbol_tickers[exchange] = ticker
            
            # Need at least 2 exchanges for arbitrage
            if len(symbol_tickers) < 2:
                return
            
            # Find best arbitrage opportunities
            opportunities = []
            exchanges = list(symbol_tickers.keys())
            
            for i in range(len(exchanges)):
                for j in range(i + 1, len(exchanges)):
                    exchange1, exchange2 = exchanges[i], exchanges[j]
                    ticker1, ticker2 = symbol_tickers[exchange1], symbol_tickers[exchange2]
                    
                    # Check both directions
                    # Direction 1: Buy on exchange1, sell on exchange2
                    if ticker2.bid_price > ticker1.ask_price:
                        price_diff = ticker2.bid_price - ticker1.ask_price
                        profit_pct = (price_diff / ticker1.ask_price) * 100
                        
                        if profit_pct > (self.config.arbitrage_threshold * 100):
                            opportunity = ArbitrageOpportunity(
                                symbol=symbol,
                                buy_exchange=exchange1.upper(),
                                sell_exchange=exchange2.upper(),
                                buy_price=ticker1.ask_price,
                                sell_price=ticker2.bid_price,
                                price_difference=price_diff,
                                profit_percentage=profit_pct,
                                timestamp=datetime.now()
                            )
                            opportunities.append(opportunity)
                    
                    # Direction 2: Buy on exchange2, sell on exchange1
                    if ticker1.bid_price > ticker2.ask_price:
                        price_diff = ticker1.bid_price - ticker2.ask_price
                        profit_pct = (price_diff / ticker2.ask_price) * 100
                        
                        if profit_pct > (self.config.arbitrage_threshold * 100):
                            opportunity = ArbitrageOpportunity(
                                symbol=symbol,
                                buy_exchange=exchange2.upper(),
                                sell_exchange=exchange1.upper(),
                                buy_price=ticker2.ask_price,
                                sell_price=ticker1.bid_price,
                                price_difference=price_diff,
                                profit_percentage=profit_pct,
                                timestamp=datetime.now()
                            )
                            opportunities.append(opportunity)
            
            # Log opportunities
            for opportunity in opportunities:
                self._opportunity_count += 1
                self._recent_opportunities.append(opportunity)
                
                self.logger.info(f"[ANALYTICS] Arbitrage Alert: {opportunity}")
            
            # Cleanup old opportunities
            await self._cleanup_old_opportunities()
        
        except Exception as e:
            self.logger.error(f"Error analyzing arbitrage opportunities for {symbol}: {e}")
    
    async def _analyze_trade_volume(self, exchange: str, symbol: Symbol) -> None:
        """
        Analyze trade volume patterns for a symbol.
        
        Args:
            exchange: Exchange name
            symbol: Symbol
        """
        try:
            cache_key = f"{exchange.lower()}_{symbol}"
            recent_trades = self._recent_trades.get(cache_key, [])
            
            if not recent_trades:
                return
            
            # Calculate volume metrics for last minute
            one_minute_ago = datetime.now() - timedelta(minutes=1)
            one_minute_timestamp = int(one_minute_ago.timestamp() * 1000)
            
            recent_minute_trades = [
                trade for trade in recent_trades 
                if trade.timestamp and trade.timestamp > one_minute_timestamp
            ]
            
            if not recent_minute_trades:
                return
            
            # Calculate metrics
            total_volume = sum(trade.quantity for trade in recent_minute_trades)
            total_value_usd = sum(trade.price * trade.quantity for trade in recent_minute_trades)
            trade_count = len(recent_minute_trades)
            avg_price = sum(trade.price for trade in recent_minute_trades) / trade_count
            
            # Check for high volume alerts
            if total_value_usd > self.config.volume_threshold * 10:  # 10x normal threshold
                self.logger.info(
                    f"[ANALYTICS] High Volume Alert: {symbol.base}/{symbol.quote} on {exchange.upper()} - "
                    f"Volume: {total_volume:.2f}, Value: ${total_value_usd:.0f}, "
                    f"Trades: {trade_count}, Avg Price: ${avg_price:.6f}"
                )
        
        except Exception as e:
            self.logger.error(f"Error analyzing trade volume for {exchange}:{symbol}: {e}")
    
    async def _analyze_price_momentum(self, exchange: str, symbol: Symbol) -> None:
        """
        Analyze price momentum from recent trades.
        
        Args:
            exchange: Exchange name
            symbol: Symbol
        """
        try:
            cache_key = f"{exchange.lower()}_{symbol}"
            recent_trades = self._recent_trades.get(cache_key, [])
            
            if len(recent_trades) < 10:  # Need sufficient data
                return
            
            # Get trades from last 2 minutes for momentum calculation
            two_minutes_ago = datetime.now() - timedelta(minutes=2)
            two_minutes_timestamp = int(two_minutes_ago.timestamp() * 1000)
            
            momentum_trades = [
                trade for trade in recent_trades 
                if trade.timestamp and trade.timestamp > two_minutes_timestamp
            ]
            
            if len(momentum_trades) < 5:
                return
            
            # Sort by timestamp
            momentum_trades.sort(key=lambda t: t.timestamp or 0)
            
            # Calculate price change rate
            early_trades = momentum_trades[:len(momentum_trades)//2]
            late_trades = momentum_trades[len(momentum_trades)//2:]
            
            early_avg_price = sum(t.price for t in early_trades) / len(early_trades)
            late_avg_price = sum(t.price for t in late_trades) / len(late_trades)
            
            price_change_pct = ((late_avg_price - early_avg_price) / early_avg_price) * 100
            
            # Alert on significant momentum (>1% price change)
            if abs(price_change_pct) > 1.0:
                direction = "UP" if price_change_pct > 0 else "DOWN"
                self.logger.info(
                    f"[ANALYTICS] Price Momentum Alert: {symbol.base}/{symbol.quote} on {exchange.upper()} - "
                    f"Direction: {direction}, Change: {price_change_pct:.2f}%, "
                    f"From: ${early_avg_price:.6f} To: ${late_avg_price:.6f}"
                )
        
        except Exception as e:
            self.logger.error(f"Error analyzing price momentum for {exchange}:{symbol}: {e}")
    
    async def _cleanup_old_trades(self) -> None:
        """Remove trades older than 5 minutes."""
        try:
            cutoff_time = datetime.now() - timedelta(minutes=5)
            cutoff_timestamp = int(cutoff_time.timestamp() * 1000)
            
            for cache_key in list(self._recent_trades.keys()):
                self._recent_trades[cache_key] = [
                    trade for trade in self._recent_trades[cache_key] 
                    if trade.timestamp and trade.timestamp > cutoff_timestamp
                ]
                
                # Remove empty lists
                if not self._recent_trades[cache_key]:
                    del self._recent_trades[cache_key]
            
            self._last_trade_cleanup = datetime.now()
        
        except Exception as e:
            self.logger.error(f"Error cleaning up old trades: {e}")
    
    async def _cleanup_old_opportunities(self) -> None:
        """Remove opportunities older than 1 minute."""
        if datetime.now() - self._last_opportunity_cleanup > timedelta(minutes=1):
            cutoff_time = datetime.now() - timedelta(minutes=1)
            self._recent_opportunities = [
                opp for opp in self._recent_opportunities 
                if opp.timestamp > cutoff_time
            ]
            self._last_opportunity_cleanup = datetime.now()
    
    def _should_log_summary(self) -> bool:
        """Check if it's time to log a market health summary."""
        return datetime.now() - self._last_summary_time > timedelta(seconds=10)
    
    async def _log_market_health_summary(self) -> None:
        """Log a comprehensive market health summary."""
        try:
            # Calculate summary statistics
            total_pairs = len(self._active_symbols)
            active_pairs = len(set(ticker.symbol for ticker in self._latest_tickers.values()))
            recent_opportunities = len([
                opp for opp in self._recent_opportunities 
                if opp.timestamp > datetime.now() - timedelta(minutes=1)
            ])
            
            # Calculate average spread
            spreads = []
            exchange_counts = {}
            for cache_key, ticker in self._latest_tickers.items():
                exchange = cache_key.split("_", 1)[0]
                exchange_counts[exchange] = exchange_counts.get(exchange, 0) + 1
                
                spread_pct = ((ticker.ask_price - ticker.bid_price) / ticker.bid_price) * 100
                spreads.append(spread_pct)
            
            avg_spread = sum(spreads) / len(spreads) if spreads else 0.0
            
            # Log summary
            self.logger.debug(
                f"[ANALYTICS] Market Health: {active_pairs}/{total_pairs} pairs active, "
                f"avg spread: {avg_spread:.3f}%, opportunities: {recent_opportunities}, "
                f"updates: {self._update_count}"
            )
            
            # Log exchange statistics
            for exchange, count in exchange_counts.items():
                updates_per_min = count  # Approximate since last summary
                status_icon = "✓" if updates_per_min > 0 else "✗"
                self.logger.debug(
                    f"[ANALYTICS] Connection Status: {exchange.upper()}: {status_icon} "
                    f"({updates_per_min} updates)"
                )
            
            # Reset counters
            self._last_summary_time = datetime.now()
            self._update_count = 0
        
        except Exception as e:
            self.logger.error(f"Error logging market health summary: {e}")
    
    def get_statistics(self) -> Dict[str, any]:
        """
        Get analytics statistics for monitoring.
        
        Returns:
            Dictionary with analytics statistics
        """
        recent_opportunities = [
            opp for opp in self._recent_opportunities 
            if opp.timestamp > datetime.now() - timedelta(minutes=5)
        ]
        
        # Calculate trade statistics
        total_trades = sum(len(trades) for trades in self._recent_trades.values())
        active_trade_symbols = len([k for k, v in self._recent_trades.items() if v])
        
        return {
            "total_symbols": len(self._active_symbols),
            "cached_tickers": len(self._latest_tickers),
            "total_opportunities": self._opportunity_count,
            "recent_opportunities": len(recent_opportunities),
            "update_count": self._update_count,
            "trade_count": self._trade_count,
            "recent_trades": total_trades,
            "active_trade_symbols": active_trade_symbols,
            "config": {
                "arbitrage_threshold": self.config.arbitrage_threshold,
                "volume_threshold": self.config.volume_threshold,
                "spread_alert_threshold": self.config.spread_alert_threshold
            }
        }
    
    def get_recent_opportunities(self, minutes: int = 5) -> List[ArbitrageOpportunity]:
        """
        Get arbitrage opportunities from the last N minutes.
        
        Args:
            minutes: Number of minutes to look back
            
        Returns:
            List of recent arbitrage opportunities
        """
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        return [
            opp for opp in self._recent_opportunities 
            if opp.timestamp > cutoff_time
        ]
    
    def get_recent_trades(self, exchange: str = None, symbol: Symbol = None, minutes: int = 5) -> List[Trade]:
        """
        Get recent trades with optional filtering.
        
        Args:
            exchange: Optional exchange filter
            symbol: Optional symbol filter
            minutes: Number of minutes to look back
            
        Returns:
            List of recent trades
        """
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        cutoff_timestamp = int(cutoff_time.timestamp() * 1000)
        
        all_trades = []
        for cache_key, trades in self._recent_trades.items():
            key_exchange, key_symbol_str = cache_key.split("_", 1)
            
            # Apply filters
            if exchange and key_exchange.lower() != exchange.lower():
                continue
            if symbol and key_symbol_str != str(symbol):
                continue
            
            # Filter by time
            recent_trades = [
                trade for trade in trades 
                if trade.timestamp and trade.timestamp > cutoff_timestamp
            ]
            all_trades.extend(recent_trades)
        
        return sorted(all_trades, key=lambda t: t.timestamp or 0, reverse=True)
    
    def get_trade_analysis(self, exchange: str, symbol: Symbol, minutes: int = 1) -> TradeAnalysis:
        """
        Get trade analysis for a specific exchange and symbol.
        
        Args:
            exchange: Exchange name
            symbol: Symbol
            minutes: Time window in minutes
            
        Returns:
            TradeAnalysis object
        """
        cache_key = f"{exchange.lower()}_{symbol}"
        recent_trades = self._recent_trades.get(cache_key, [])
        
        # Filter by time window
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        cutoff_timestamp = int(cutoff_time.timestamp() * 1000)
        
        window_trades = [
            trade for trade in recent_trades 
            if trade.timestamp and trade.timestamp > cutoff_timestamp
        ]
        
        if not window_trades:
            return TradeAnalysis(
                symbol=symbol,
                exchange=exchange.upper(),
                total_volume=0.0,
                trade_count=0,
                avg_price=0.0,
                price_momentum=0.0,
                volume_usd=0.0,
                timestamp=datetime.now()
            )
        
        # Calculate metrics
        total_volume = sum(trade.quantity for trade in window_trades)
        trade_count = len(window_trades)
        avg_price = sum(trade.price for trade in window_trades) / trade_count
        volume_usd = sum(trade.price * trade.quantity for trade in window_trades)
        
        # Calculate momentum (price change rate)
        price_momentum = 0.0
        if len(window_trades) >= 2:
            sorted_trades = sorted(window_trades, key=lambda t: t.timestamp or 0)
            early_price = sorted_trades[0].price
            late_price = sorted_trades[-1].price
            price_momentum = ((late_price - early_price) / early_price) * 100
        
        return TradeAnalysis(
            symbol=symbol,
            exchange=exchange.upper(),
            total_volume=total_volume,
            trade_count=trade_count,
            avg_price=avg_price,
            price_momentum=price_momentum,
            volume_usd=volume_usd,
            timestamp=datetime.now()
        )