"""
Real-time Analytics Engine for Data Collector

Processes book ticker updates to detect arbitrage opportunities and market conditions.
Provides real-time analytics logging for monitoring market health and opportunities.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Set
from dataclasses import dataclass

from structs.common import Symbol, BookTicker
from data_collector.config import AnalyticsConfig


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
        self.logger = logging.getLogger(__name__)
        
        # Latest book ticker data: {exchange_symbol: BookTicker}
        self._latest_tickers: Dict[str, BookTicker] = {}
        
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
        
        return {
            "total_symbols": len(self._active_symbols),
            "cached_tickers": len(self._latest_tickers),
            "total_opportunities": self._opportunity_count,
            "recent_opportunities": len(recent_opportunities),
            "update_count": self._update_count,
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