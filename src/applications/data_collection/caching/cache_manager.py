"""
Cache Manager - Simplified In-Memory Caching

Manages in-memory caching for book tickers and trades.
Focuses on fast access and snapshot generation.
"""

from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass

from exchanges.structs import Symbol, BookTicker, Trade, ExchangeEnum
from db import BookTickerSnapshot
from db.models import TradeSnapshot
from infrastructure.logging import get_logger


@dataclass
class BookTickerCache:
    """Cache entry for book ticker data."""
    ticker: BookTicker
    last_updated: datetime
    exchange: str


@dataclass
class TradeCache:
    """Cache entry for trade data."""
    trade: Trade
    last_updated: datetime
    exchange: str


class CacheManager:
    """
    Simplified cache manager for market data.
    
    Responsibilities:
    - Store latest book ticker data per exchange/symbol
    - Store recent trades with automatic cleanup
    - Generate snapshots for persistence
    - Provide cache statistics
    """

    def __init__(self, max_trades_per_symbol: int = 100):
        """Initialize cache manager."""
        self.max_trades_per_symbol = max_trades_per_symbol
        self.logger = get_logger('data_collection.cache_manager')

        # Caches
        self._book_ticker_cache: Dict[str, BookTickerCache] = {}
        self._trade_cache: Dict[str, List[TradeCache]] = {}
        self._active_symbols: Set[Symbol] = set()

        # Statistics
        self._total_updates = 0
        self._total_trades = 0

        self.logger.info("CacheManager initialized", 
                        max_trades_per_symbol=max_trades_per_symbol)

    def update_book_ticker(self, exchange: ExchangeEnum, symbol: Symbol, book_ticker: BookTicker) -> None:
        """Update book ticker in cache."""
        try:
            cache_key = f"{exchange.value}_{symbol}"
            
            self._book_ticker_cache[cache_key] = BookTickerCache(
                ticker=book_ticker,
                last_updated=datetime.now(),
                exchange=exchange.value
            )
            
            self._active_symbols.add(symbol)
            self._total_updates += 1

        except Exception as e:
            self.logger.error(f"Error updating book ticker cache: {e}")

    def update_trade(self, exchange: ExchangeEnum, symbol: Symbol, trade: Trade) -> None:
        """Update trade in cache."""
        try:
            cache_key = f"{exchange.value}_{symbol}"
            
            if cache_key not in self._trade_cache:
                self._trade_cache[cache_key] = []

            # Add new trade
            trade_entry = TradeCache(
                trade=trade,
                last_updated=datetime.now(),
                exchange=exchange.value
            )
            
            self._trade_cache[cache_key].append(trade_entry)
            
            # Keep only recent trades (limit per symbol)
            if len(self._trade_cache[cache_key]) > self.max_trades_per_symbol:
                self._trade_cache[cache_key] = self._trade_cache[cache_key][-self.max_trades_per_symbol:]

            self._active_symbols.add(symbol)
            self._total_trades += 1

        except Exception as e:
            self.logger.error(f"Error updating trade cache: {e}")

    def get_book_ticker(self, exchange: ExchangeEnum, symbol: Symbol) -> Optional[BookTicker]:
        """Get latest book ticker for exchange/symbol."""
        cache_key = f"{exchange.value}_{symbol}"
        cache_entry = self._book_ticker_cache.get(cache_key)
        return cache_entry.ticker if cache_entry else None

    def get_all_cached_tickers(self) -> List[BookTickerSnapshot]:
        """Get all cached book tickers as snapshots."""
        snapshots = []

        for cache_key, cache_entry in self._book_ticker_cache.items():
            try:
                exchange, symbol_str = self._parse_cache_key(cache_key)
                symbol = self._resolve_symbol(symbol_str)
                
                if symbol is None:
                    continue

                snapshot = BookTickerSnapshot.from_symbol_and_data(
                    exchange=exchange.upper(),
                    symbol=symbol,
                    bid_price=cache_entry.ticker.bid_price,
                    bid_qty=cache_entry.ticker.bid_quantity,
                    ask_price=cache_entry.ticker.ask_price,
                    ask_qty=cache_entry.ticker.ask_quantity,
                    timestamp=cache_entry.last_updated
                )
                snapshots.append(snapshot)

            except Exception as e:
                self.logger.error(f"Error creating snapshot for {cache_key}: {e}")
                continue

        return snapshots

    def get_all_cached_trades(self) -> List[TradeSnapshot]:
        """Get all cached trades as snapshots."""
        snapshots = []

        for cache_key, trade_list in self._trade_cache.items():
            try:
                exchange, _ = self._parse_cache_key(cache_key)
                
                for trade_cache in trade_list:
                    snapshot = TradeSnapshot.from_trade_struct(
                        exchange=exchange.upper(),
                        trade=trade_cache.trade
                    )
                    snapshots.append(snapshot)
                    
            except Exception as e:
                self.logger.error(f"Error creating trade snapshot for {cache_key}: {e}")
                continue

        return snapshots

    def _parse_cache_key(self, cache_key: str) -> Tuple[str, str]:
        """Parse cache key into exchange and symbol."""
        parts = cache_key.rsplit("_", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid cache key format: {cache_key}")
        return parts[0], parts[1]

    def _resolve_symbol(self, symbol_str: str) -> Optional[Symbol]:
        """Resolve symbol string to Symbol object."""
        # Try to find in active symbols first
        for symbol in self._active_symbols:
            if str(symbol) == symbol_str:
                return symbol

        # Create fallback symbol for common patterns
        if symbol_str.endswith('USDT') and len(symbol_str) >= 6:
            try:
                from exchanges.structs.common import Symbol
                from exchanges.structs.types import AssetName
                base = symbol_str[:-4]  # Remove USDT
                return Symbol(base=AssetName(base), quote=AssetName('USDT'), is_futures=False)
            except:
                pass

        return None

    def get_statistics(self) -> Dict[str, any]:
        """Get cache statistics."""
        total_trades = sum(len(trades) for trades in self._trade_cache.values())
        
        return {
            "cached_tickers": len(self._book_ticker_cache),
            "cached_trades": total_trades,
            "active_symbols": len(self._active_symbols),
            "total_updates": self._total_updates,
            "total_trades_processed": self._total_trades,
            "trade_cache_keys": len(self._trade_cache)
        }

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._book_ticker_cache.clear()
        self._trade_cache.clear()
        self._active_symbols.clear()
        self.logger.info("Cache cleared")