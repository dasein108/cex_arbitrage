"""
Data Collector - Modern Separated Domain Architecture

Manages real-time data collection from multiple exchanges using the modern separated domain
architecture with BindedEventHandlersAdapter pattern for flexible event handling.

Architecture (Oct 2025):
- Separated Domain Pattern: Public exchanges for market data only
- BindedEventHandlersAdapter: Modern event binding with .bind() method
- Constructor Injection: REST/WebSocket clients injected via constructors
- HFT Compliance: Sub-millisecond latency targets, no real-time data caching
- msgspec.Struct: All data modeling uses structured types
"""

import asyncio
from datetime import datetime, timezone, UTC, timedelta
from typing import Dict, List, Optional, Set, Callable, Awaitable, Union
from dataclasses import dataclass

from exchanges.interfaces.composite.futures.base_public_futures_composite import CompositePublicFuturesExchange
from exchanges.interfaces.composite.spot.base_public_spot_composite import CompositePublicSpotExchange
from exchanges.structs import Symbol, BookTicker, Trade, ExchangeEnum
from exchanges.exchange_factory import get_composite_implementation
from exchanges.adapters import BindedEventHandlersAdapter
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType
from db.models import TradeSnapshot, FundingRateSnapshot, BookTickerSnapshot
from db.operations import insert_book_ticker_snapshots_batch, insert_funding_rate_snapshots_batch
from .analytics import RealTimeAnalytics, ArbitrageOpportunity
from config.config_manager import get_exchange_config
from infrastructure.logging import get_logger, LoggingTimer
from db import initialize_database_manager, get_database_manager


@dataclass(frozen=True)
class SymbolCacheKey:
    """
    Structured cache key for exchange-symbol combinations.
    
    Uses frozen dataclass to make it hashable for dictionary keys.
    Eliminates string parsing issues and exchange-specific symbol format problems.
    """
    exchange: ExchangeEnum
    base: str
    quote: str
    
    @classmethod
    def from_exchange_and_symbol(cls, exchange: ExchangeEnum, symbol: Symbol) -> "SymbolCacheKey":
        """Create cache key from exchange and symbol objects."""
        return cls(
            exchange=exchange,
            base=symbol.base.upper(),
            quote=symbol.quote.upper()
        )
    
    def to_symbol(self) -> Symbol:
        """Convert cache key back to Symbol object."""
        return Symbol(base=self.base, quote=self.quote)
    
    def __str__(self) -> str:
        """String representation for logging."""
        return f"{self.exchange.value}:{self.base}/{self.quote}"


@dataclass
class BookTickerCache:
    """In-memory cache for book ticker data."""
    ticker: BookTicker
    last_updated: datetime
    exchange: str


@dataclass
class TradeCache:
    """In-memory cache for trade data."""
    trade: Trade
    last_updated: datetime
    exchange: str


@dataclass
class FundingRateCache:
    """In-memory cache for funding rate data."""
    funding_rate_snapshot: FundingRateSnapshot
    last_updated: datetime
    exchange: str


class UnifiedWebSocketManager:
    """
    Unified WebSocket manager using modern separated domain architecture.
    
    Architecture (Oct 2025):
    - Separated Domain Pattern: Uses CompositePublicExchange for market data only
    - BindedEventHandlersAdapter: Modern event binding with .bind() method
    - Constructor Injection: Dependencies injected via constructors
    - HFT Optimized: Sub-millisecond latency targets
    
    Features:
    - Manages connections to multiple exchanges via composite pattern
    - Uses BindedEventHandlersAdapter for flexible event handling
    - Maintains in-memory cache following HFT caching policy
    - Provides unified interface for symbol subscription
    """

    def __init__(
            self,
            exchanges: List[ExchangeEnum],
            book_ticker_handler: Optional[Callable[[ExchangeEnum, Symbol, BookTicker], Awaitable[None]]] = None,
            trade_handler: Optional[Callable[[ExchangeEnum, Symbol, Trade], Awaitable[None]]] = None,  # NOTE: Trade handling disabled for performance
            database_manager=None
    ):
        """
        Initialize unified WebSocket manager with modern architecture.
        
        Args:
            exchanges: List of exchange enums to connect to
            book_ticker_handler: Callback for book ticker updates
            trade_handler: Callback for trade updates
            database_manager: Database manager instance for symbol lookups
        """
        self.exchanges = exchanges
        self.book_ticker_handler = book_ticker_handler
        self.trade_handler = trade_handler
        self.db = database_manager

        # HFT Logging
        self.logger = get_logger('data_collector.websocket_manager')

        # Exchange composite clients (separated domain architecture)
        self._exchange_composites: Dict[ExchangeEnum,
        Union[CompositePublicSpotExchange, CompositePublicFuturesExchange]] = {}
        
        # Event handler adapters for each exchange
        self._event_adapters: Dict[ExchangeEnum, BindedEventHandlersAdapter] = {}

        # Symbol-based cache with structured keys (eliminates parsing issues)
        self._book_ticker_cache: Dict[SymbolCacheKey, BookTickerCache] = {}

        # Performance tracking
        self._total_messages_received = 0
        self._total_data_processed = 0

        # Log initialization
        self.logger.info("UnifiedWebSocketManager initialized with modern architecture",
                         exchanges=[e.value for e in exchanges],
                         has_book_ticker_handler=book_ticker_handler is not None,
                         has_trade_handler=trade_handler is not None)

        # Trade cache with structured keys: {SymbolCacheKey: List[TradeCache]}
        self._trade_cache: Dict[SymbolCacheKey, List[TradeCache]] = {}

        # Funding rate cache with structured keys: {SymbolCacheKey: FundingRateCache}
        self._funding_rate_cache: Dict[SymbolCacheKey, FundingRateCache] = {}

        # Active symbols per exchange
        self._active_symbols: Dict[ExchangeEnum, Set[Symbol]] = {}

        # Connection status
        self._connected: Dict[ExchangeEnum, bool] = {}
        
        # Background task for funding rate collection
        self._funding_rate_sync_task: Optional[asyncio.Task] = None
        self._funding_rate_sync_interval = 5 * 60  # 5 minutes in seconds

        self.logger.info(f"Initialized unified WebSocket manager for exchanges: {exchanges}")

    async def initialize(self, symbols: List[Symbol]) -> None:
        """
        Initialize WebSocket connections for all configured exchanges.
        
        Args:
            symbols: List of symbols to subscribe to across all exchanges
        """
        try:
            self.logger.info(f"Initializing WebSocket connections for {len(symbols)} symbols")

            # Initialize exchange clients
            for exchange in self.exchanges:
                await self._initialize_exchange_client(exchange, symbols)

            # Start funding rate sync task for futures exchanges
            await self._start_funding_rate_sync()

            self.logger.info("All WebSocket connections initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize WebSocket connections: {e}")
            raise

    async def _initialize_exchange_client(self, exchange: ExchangeEnum, symbols: List[Symbol]) -> None:
        """
        Initialize composite exchange client using modern separated domain architecture.
        
        Modern Pattern (Oct 2025):
        1. Create CompositePublicExchange via factory (constructor injection)
        2. Create BindedEventHandlersAdapter and bind to exchange
        3. Bind event handlers using .bind() method
        4. Initialize and subscribe to symbols
        
        Args:
            exchange: Exchange enum (ExchangeEnum.MEXC, ExchangeEnum.GATEIO, etc.)
            symbols: Symbols to subscribe to
        """
        try:
            # Create exchange configuration
            config = get_exchange_config(exchange.value)
            
            # Create composite public exchange (separated domain architecture)
            composite = get_composite_implementation(
                exchange_config=config,
                is_private=False  # Pure market data domain
            )

            # Create event handler adapter
            adapter = BindedEventHandlersAdapter(self.logger).bind_to_exchange(composite)
            
            # Bind event handlers using modern .bind() pattern
            if self.book_ticker_handler:
                adapter.bind(PublicWebsocketChannelType.BOOK_TICKER, 
                           lambda book_ticker: self._handle_book_ticker_update(exchange, book_ticker.symbol, book_ticker))
            
            # Bind TICKER handler for futures exchanges to collect funding rates
            config = get_exchange_config(exchange.value)
            if config.is_futures:
                adapter.bind(PublicWebsocketChannelType.TICKER, 
                           lambda ticker: self._handle_ticker_update(exchange, ticker))
                self.logger.info(f"Bound TICKER handler for futures exchange {exchange.value}")
            
            # Trade handler binding disabled for performance optimization
            # TODO: tmp disabled
            # if self.trade_handler:
            #     adapter.bind(PublicWebsocketChannelType.PUB_TRADE,
            #                lambda trade: self._handle_trades_update(exchange, trade.symbol, [trade]))

            # Store composite and adapter
            self._exchange_composites[exchange] = composite
            self._event_adapters[exchange] = adapter
            self._active_symbols[exchange] = set()
            self._connected[exchange] = False

            # Initialize composite with symbols and channels
            # NOTE: Trade subscription disabled for performance optimization - only collecting book tickers
            with LoggingTimer(self.logger, "composite_initialization") as timer:
                # channels = [PublicWebsocketChannelType.BOOK_TICKER, PublicWebsocketChannelType.PUB_TRADE]  # Core market data
                channels = [PublicWebsocketChannelType.PUB_TRADE]  # Core market data

                # Add TICKER channel for futures exchanges to collect funding rates
                config = get_exchange_config(exchange.value)
                if config.is_futures:
                    channels.append(PublicWebsocketChannelType.TICKER)
                    self.logger.info(f"Added TICKER channel for futures exchange {exchange.value}")
                # Removed PUB_TRADE for performance
                
                # Filter tradable symbols before subscription
                tradable_symbols = []
                non_tradable_symbols = []
                
                for symbol in symbols:
                    try:
                        if await composite.is_tradable(symbol):
                            tradable_symbols.append(symbol)
                        else:
                            non_tradable_symbols.append(symbol)
                            self.logger.warning(f"Symbol {symbol.base}/{symbol.quote} not tradable on {exchange.value}, excluding from subscription")
                    except Exception as e:
                        non_tradable_symbols.append(symbol)
                        self.logger.error(f"Error checking tradability for {symbol.base}/{symbol.quote} on {exchange.value}: {e}")
                
                # Send Telegram notification for non-tradable symbols
                if non_tradable_symbols:
                    await self._notify_non_tradable_symbols(exchange, non_tradable_symbols)
                
                # Initialize with only tradable symbols
                await composite.initialize(tradable_symbols, channels)
                self._active_symbols[exchange].update(tradable_symbols)
                self._connected[exchange] = True

            self.logger.info("Composite exchange initialized successfully",
                             exchange=exchange.value,
                             symbols_count=len(symbols),
                             initialization_time_ms=timer.elapsed_ms)

            # Track successful initialization metrics
            self.logger.metric("composite_initializations", 1,
                               tags={"exchange": exchange.value, "status": "success"})

            self.logger.metric("symbols_subscribed", len(tradable_symbols),
                               tags={"exchange": exchange.value})

        except Exception as e:
            self.logger.error("Failed to initialize composite exchange",
                              exchange=exchange.value,
                              error_type=type(e).__name__,
                              error_message=str(e),
                              symbols_count=len(symbols))

            # Track initialization failures
            self.logger.metric("composite_initializations", 1,
                               tags={"exchange": exchange.value, "status": "error"})

            self._connected[exchange] = False
            raise

    async def _notify_non_tradable_symbols(self, exchange: ExchangeEnum, symbols: List[Symbol]) -> None:
        """Send Telegram notification for non-tradable symbols."""
        try:
            from infrastructure.networking.telegram import send_to_telegram
            
            symbol_list = ", ".join([f"{s.base}/{s.quote}" for s in symbols])
            message = f"🚫 Non-tradable symbols excluded from {exchange.value}:\n{symbol_list}"
            
            await send_to_telegram(message)
            self.logger.info(f"Sent Telegram notification for {len(symbols)} non-tradable symbols on {exchange.value}")
        except Exception as e:
            self.logger.error(f"Failed to send Telegram notification: {e}")

    async def _handle_book_ticker_update(self, exchange: ExchangeEnum, symbol: Symbol, book_ticker: BookTicker) -> None:
        """
        Handle book ticker updates from any exchange.
        
        Args:
            exchange: Exchange that was updated
            symbol: Symbol that was updated
            book_ticker: Updated book ticker data
        """
        try:
            # Track message reception
            self._total_messages_received += 1

            # Update cache using structured SymbolCacheKey (eliminates format issues)
            cache_key = SymbolCacheKey.from_exchange_and_symbol(exchange, symbol)
            with LoggingTimer(self.logger, "book_ticker_cache_update") as timer:
                self._book_ticker_cache[cache_key] = BookTickerCache(
                    ticker=book_ticker,
                    last_updated=datetime.now(),
                    exchange=exchange.value
                )

            # Log update with performance context
            self.logger.debug("Book ticker cached",
                              exchange=exchange.value,
                              symbol=str(cache_key),
                              bid_price=book_ticker.bid_price,
                              ask_price=book_ticker.ask_price,
                              cache_time_us=timer.elapsed_ms * 1000)

            # Track performance metrics
            self.logger.metric("book_ticker_updates", 1,
                               tags={"exchange": exchange.value, "symbol": str(cache_key)})

            self.logger.metric("cache_update_time_us", timer.elapsed_ms * 1000,
                               tags={"exchange": exchange.value, "operation": "book_ticker"})

            # Call registered handler if available
            if self.book_ticker_handler:
                with LoggingTimer(self.logger, "book_ticker_handler") as handler_timer:
                    await self.book_ticker_handler(exchange, symbol, book_ticker)

                self.logger.metric("handler_processing_time_us", handler_timer.elapsed_ms * 1000,
                                   tags={"exchange": exchange.value, "handler": "book_ticker"})

            self._total_data_processed += 1

            # Log periodic performance stats
            if self._total_messages_received % 10000 == 0:
                self.logger.info("Performance checkpoint",
                                 messages_received=self._total_messages_received,
                                 data_processed=self._total_data_processed,
                                 cache_size=len(self._book_ticker_cache))

                self.logger.metric("messages_received_total", self._total_messages_received)
                self.logger.metric("data_processed_total", self._total_data_processed)
                self.logger.metric("cache_size", len(self._book_ticker_cache))

        except Exception as e:
            cache_key = SymbolCacheKey.from_exchange_and_symbol(exchange, symbol)
            self.logger.error("Error handling book ticker update",
                              exchange=exchange.value,
                              symbol=str(cache_key),
                              error_type=type(e).__name__,
                              error_message=str(e))

            # Track error metrics
            self.logger.metric("book_ticker_processing_errors", 1,
                               tags={"exchange": exchange.value, "symbol": str(cache_key)})

            import traceback
            self.logger.debug("Full traceback", traceback=traceback.format_exc())



    async def _handle_trades_update(self, exchange: ExchangeEnum, symbol: Symbol, trades: List[Trade]) -> None:
        """
        Handle trade updates from any exchange.
        
        Args:
            exchange: Exchange enum
            symbol: Symbol that was traded
            trades: List of trade data
        """
        try:
            # Update cache using structured SymbolCacheKey (eliminates format issues)
            cache_key = SymbolCacheKey.from_exchange_and_symbol(exchange, symbol)
            if cache_key not in self._trade_cache:
                self._trade_cache[cache_key] = []

            # Process each trade in the list
            for trade in trades:
                trade_cache_entry = TradeCache(
                    trade=trade,
                    last_updated=datetime.now(),
                    exchange=exchange.value
                )

                self._trade_cache[cache_key].append(trade_cache_entry)

            # Keep only recent trades (limit to 100 to prevent memory bloat)
            if len(self._trade_cache[cache_key]) > 100:
                self._trade_cache[cache_key] = self._trade_cache[cache_key][-100:]

            # Call registered handler for each trade if available
            if self.trade_handler:
                for trade in trades:
                    await self.trade_handler(exchange, symbol, trade)
        except Exception as e:
            self.logger.error(f"Error handling trades update for {symbol}: {e}")

    async def _handle_ticker_update(self, exchange: ExchangeEnum, ticker_data: any) -> None:
        """
        Handle ticker updates from futures exchanges to extract funding rate data.
        
        Args:
            exchange: Exchange enum (should be a futures exchange)
            ticker_data: Ticker data containing funding rate information
        """
        try:
            # Only process futures exchanges
            config = get_exchange_config(exchange.value)
            if not config.is_futures:
                return
                
            # Extract symbol from ticker data
            # The exact format depends on exchange implementation
            symbol = getattr(ticker_data, 'symbol', None)
            if not symbol:
                self.logger.warning(f"No symbol found in ticker data from {exchange.value}")
                return
                
            # Extract funding rate data from ticker
            funding_rate = getattr(ticker_data, 'funding_rate', None)
            funding_time = getattr(ticker_data, 'funding_time', None)
            
            if funding_rate is not None and funding_time is not None:
                # Validate funding_time to prevent database constraint violation
                if funding_time <= 0:
                    self.logger.warning(f"Invalid funding_time ({funding_time}) for {exchange.value} {symbol}, skipping")
                    return
                
                # Create funding rate snapshot
                current_time = datetime.now(timezone.utc)
                
                # Get symbol_id for database storage using injected database manager
                try:
                    symbol_id = await self.db.resolve_symbol_id_async(exchange, symbol)
                except Exception as e:
                    self.logger.warning(f"Could not resolve symbol_id for {exchange.value} {symbol}: {e}")
                    symbol_id = None
                
                # Symbol lookup completed successfully
                
                if symbol_id:
                    funding_snapshot = FundingRateSnapshot(
                        symbol_id=symbol_id,
                        funding_rate=float(funding_rate),
                        funding_time=int(funding_time),
                        timestamp=current_time,
                        exchange=exchange.value
                    )
                    
                    # Update cache using structured SymbolCacheKey 
                    cache_key = SymbolCacheKey.from_exchange_and_symbol(exchange, symbol)
                    cache_entry = FundingRateCache(
                        funding_rate_snapshot=funding_snapshot,
                        last_updated=current_time,
                        exchange=exchange.value
                    )
                    self._funding_rate_cache[cache_key] = cache_entry
                    
                    self.logger.debug(f"Updated funding rate cache for {symbol}: rate={funding_rate}, time={funding_time}")
                else:
                    self.logger.warning(f"Could not get symbol_id for {exchange.value} {symbol.base}/{symbol.quote}")
                    
        except Exception as e:
            self.logger.error(f"Error handling ticker update from {exchange.value}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    async def _start_funding_rate_sync(self) -> None:
        """Start the background funding rate sync task."""
        if self._funding_rate_sync_task and not self._funding_rate_sync_task.done():
            return  # Already running
            
        self._funding_rate_sync_task = asyncio.create_task(self._background_funding_rate_sync())
        self.logger.info("Started background funding rate sync task")

    async def _background_funding_rate_sync(self) -> None:
        """Background task to sync funding rates every 5 minutes."""
        while True:
            try:
                await self._sync_funding_rates()
                await asyncio.sleep(self._funding_rate_sync_interval)
            except asyncio.CancelledError:
                self.logger.info("Background funding rate sync task cancelled")
                break
            except Exception as e:
                self.logger.error("Error in background funding rate sync", error=str(e))
                # Continue running even if sync fails

    async def _sync_funding_rates(self) -> None:
        """Sync funding rates for all active futures symbols."""
        try:
            with LoggingTimer(self.logger, "funding_rate_sync") as timer:
                for exchange, composite in self._exchange_composites.items():
                    if not self._connected[exchange]:
                        continue
                        
                    # Only collect from futures exchanges
                    if exchange != ExchangeEnum.GATEIO_FUTURES:
                        continue
                        
                    active_symbols = self._active_symbols.get(exchange, set())
                    ticker = await composite.rest_client.get_ticker_info()

                    for symbol in active_symbols:
                        try:
                            # Check if the REST client supports funding rates
                            # if not hasattr(composite._rest, 'get_historical_funding_rate'):
                            #     continue
                            #
                            # # Get funding rate data
                            # funding_data = await composite._rest.get_historical_funding_rate(symbol)
                            #
                            # if not funding_data:
                            #     continue
                            #
                            # # Extract funding rate and time
                            # funding_rate = float(funding_data.get('r', 0)) if funding_data.get('r') else None
                            # funding_time = int(funding_data.get('t', 0)) if funding_data.get('t') else None
                            #
                            # if funding_rate is None or funding_time is None:
                            #     continue
                            
                            # Get symbol ID from database using injected database manager
                            try:
                                symbol_id = await self.db.resolve_symbol_id_async(exchange, symbol)
                            except Exception as e:
                                self.logger.warning(f"Could not resolve symbol_id for {exchange.value} {symbol}: {e}")
                                symbol_id = None
                            
                            # Symbol lookup completed for funding rate sync
                            funding_rate = ticker[symbol].funding_rate
                            funding_time = ticker[symbol].funding_time
                            
                            # Note: funding_time validation is handled in FundingRateSnapshot.from_symbol_and_data()
                            # The model will automatically use a fallback value if funding_time is None or invalid

                            if symbol_id is None:
                                self.logger.warning(f"Could not get symbol_id for {exchange.value} {symbol}")
                                continue

                            # Create funding rate snapshot
                            funding_snapshot = FundingRateSnapshot.from_symbol_and_data(
                                exchange=exchange.value,
                                symbol=symbol,
                                funding_rate=funding_rate,
                                next_funding_time=funding_time,
                                timestamp=datetime.now(),
                                symbol_id=symbol_id
                            )
                            
                            # Cache the snapshot using structured SymbolCacheKey
                            cache_key = SymbolCacheKey.from_exchange_and_symbol(exchange, symbol)
                            self._funding_rate_cache[cache_key] = FundingRateCache(
                                funding_rate_snapshot=funding_snapshot,
                                last_updated=datetime.now(),
                                exchange=exchange.value
                            )
                            
                            self.logger.debug(f"Cached funding rate for {symbol}: {funding_rate}")
                            
                        except Exception as e:
                            self.logger.error(f"Failed to sync funding rate for {exchange.value} {symbol}: {e}")
                            continue
                            
                synced_count = len(self._funding_rate_cache)
                self.logger.info("Funding rate sync completed",
                               symbols_synced=synced_count,
                               sync_time_ms=timer.elapsed_ms)
                               
        except Exception as e:
            self.logger.error("Failed to sync funding rates", error=str(e))

    async def add_symbols(self, symbols: List[Symbol]) -> None:
        """
        Add symbols to all active exchanges.
        
        Args:
            symbols: Symbols to add
        """
        if not symbols:
            return

        try:
            for exchange, composite in self._exchange_composites.items():
                if self._connected[exchange]:
                    # Use channel types for subscription - trade subscription disabled for performance
                    channels = [PublicWebsocketChannelType.BOOK_TICKER]
                    for s in symbols:
                        await composite.add_symbol(s)
                        self._active_symbols[exchange].update(symbols)

            self.logger.info(f"Added {len(symbols)} symbols to all exchanges")

        except Exception as e:
            self.logger.error(f"Failed to add symbols: {e}")
            raise

    async def remove_symbols(self, symbols: List[Symbol]) -> None:
        """
        Remove symbols from all active exchanges.
        
        Args:
            symbols: Symbols to remove
        """
        if not symbols:
            return

        try:
            for exchange, composite in self._exchange_composites.items():
                if self._connected[exchange]:
                    # Use composite pattern for unsubscription
                    for s in symbols:
                        await composite.remove_symbol(s)
                        self._active_symbols[exchange].difference_update(symbols)

            # Remove from cache using structured SymbolCacheKey
            for symbol in symbols:
                for exchange in self.exchanges:
                    cache_key = SymbolCacheKey.from_exchange_and_symbol(exchange, symbol)
                    self._book_ticker_cache.pop(cache_key, None)

            self.logger.info(f"Removed {len(symbols)} symbols from all exchanges")

        except Exception as e:
            self.logger.error(f"Failed to remove symbols: {e}")

    def get_latest_book_ticker(self, exchange: ExchangeEnum, symbol: Symbol) -> Optional[BookTicker]:
        """
        Get latest book ticker for a specific exchange and symbol.
        
        Args:
            exchange: Exchange enum
            symbol: Symbol to get ticker for
            
        Returns:
            BookTicker if available, None otherwise
        """
        cache_key = SymbolCacheKey.from_exchange_and_symbol(exchange, symbol)
        cache_entry = self._book_ticker_cache.get(cache_key)

        if cache_entry:
            return cache_entry.ticker
        return None

    async def _resolve_symbol_id_from_symbol_cache_key(self, cache_key: SymbolCacheKey) -> Optional[int]:
        """
        Resolve symbol_id from SymbolCacheKey using unified DatabaseManager resolution.
        
        Uses the new structured cache key to eliminate string parsing and format conversion issues.
        
        Args:
            cache_key: Structured cache key with exchange and symbol info
            
        Returns:
            symbol_id if found, None otherwise
        """
        try:
            # Use optimized DatabaseManager with unified symbol resolution (PROJECT_GUIDES.md compliant)
            # Convert cache key back to Symbol object for resolution
            symbol_obj = cache_key.to_symbol()
            
            # Use the simplified resolution method  
            symbol_id = await self.db.resolve_symbol_id_async(cache_key.exchange, symbol_obj)
            if symbol_id:
                self.logger.debug(f"Resolved symbol_id {symbol_id} for {cache_key}")
            return symbol_id
            
        except Exception as e:
            self.logger.warning(f"Error resolving symbol_id for {cache_key}: {e}")
            return None

    async def get_all_cached_tickers(self) -> List[BookTickerSnapshot]:
        """
        Get all cached book tickers as normalized BookTickerSnapshot objects.
        
        Returns:
            List of BookTickerSnapshot objects with symbol_id (normalized approach)
        """
        snapshots = []
        
        # Create a copy to avoid "dictionary changed size during iteration"
        cached_items = list(self._book_ticker_cache.items())

        for cache_key, cache_entry in cached_items:
            try:
                # Resolve symbol_id using structured SymbolCacheKey (eliminates parsing issues)
                symbol_id = await self._resolve_symbol_id_from_symbol_cache_key(cache_key)
                if symbol_id is None:
                    self.logger.warning(f"Cannot resolve symbol_id from cache: {cache_key}")
                    continue

                # Create normalized snapshot directly with symbol_id
                snapshot = BookTickerSnapshot.from_symbol_id_and_data(
                    symbol_id=symbol_id,
                    bid_price=cache_entry.ticker.bid_price,
                    bid_qty=cache_entry.ticker.bid_quantity,
                    ask_price=cache_entry.ticker.ask_price,
                    ask_qty=cache_entry.ticker.ask_quantity,
                    timestamp=cache_entry.last_updated
                )
                snapshots.append(snapshot)

            except Exception as e:
                self.logger.error(f"Error processing cached ticker {cache_key}: {e}")
                continue

        return snapshots

    async def get_all_cached_trades(self) -> List[TradeSnapshot]:
        """
        Get all cached trades as normalized TradeSnapshot objects.
        
        Returns:
            List of TradeSnapshot objects with symbol_id (normalized approach)
        """
        snapshots = []

        for cache_key, trade_cache_list in self._trade_cache.items():
            try:
                # Resolve symbol_id using structured SymbolCacheKey (eliminates parsing issues)
                symbol_id = await self._resolve_symbol_id_from_symbol_cache_key(cache_key)
                if symbol_id is None:
                    self.logger.warning(f"Cannot resolve symbol_id from cache for trades: {cache_key}")
                    continue

                # Convert each cached trade to normalized TradeSnapshot
                for trade_cache in trade_cache_list:
                    snapshot = TradeSnapshot.from_symbol_id_and_trade(
                        symbol_id=symbol_id,
                        trade=trade_cache.trade
                    )
                    snapshots.append(snapshot)
            except Exception as e:
                self.logger.error(f"Error processing cached trades {cache_key}: {e}")
                continue

        return snapshots

    async def get_all_cached_funding_rates(self) -> List[FundingRateSnapshot]:
        """
        Get all cached funding rates as FundingRateSnapshot objects.
        
        Returns:
            List of FundingRateSnapshot objects
        """
        snapshots = []
        
        # Create a copy to avoid "dictionary changed size during iteration"
        cached_items = list(self._funding_rate_cache.items())
        
        for cache_key, cache_entry in cached_items:
            try:
                snapshots.append(cache_entry.funding_rate_snapshot)
            except Exception as e:
                self.logger.error(f"Error processing cached funding rate {cache_key}: {e}")
                continue
        
        return snapshots

    def get_connection_status(self) -> Dict[str, bool]:
        """
        Get connection status for all exchanges.
        
        Returns:
            Dictionary mapping exchange names to connection status
        """
        return {exchange.value: status for exchange, status in self._connected.items()}

    def get_active_symbols_count(self) -> Dict[str, int]:
        """
        Get count of active symbols per exchange.
        
        Returns:
            Dictionary mapping exchange names to symbol counts
        """
        return {
            exchange.value: len(symbols)
            for exchange, symbols in self._active_symbols.items()
        }

    def get_cache_statistics(self) -> Dict[str, any]:
        """
        Get cache statistics for monitoring.
        
        Returns:
            Dictionary with cache statistics
        """
        total_cached = len(self._book_ticker_cache)

        # Count by exchange using structured SymbolCacheKey (eliminates parsing errors)
        by_exchange = {}
        for cache_key in self._book_ticker_cache.keys():
            exchange_name = cache_key.exchange.value
            by_exchange[exchange_name] = by_exchange.get(exchange_name, 0) + 1

        # Count cached trades by exchange
        trades_by_exchange = {}
        total_cached_trades = 0
        for cache_key, trade_list in self._trade_cache.items():
            exchange_name = cache_key.exchange.value
            trade_count = len(trade_list)
            trades_by_exchange[exchange_name] = trades_by_exchange.get(exchange_name, 0) + trade_count
            total_cached_trades += trade_count

        # Count cached funding rates by exchange
        funding_rates_by_exchange = {}
        total_cached_funding_rates = 0
        for cache_key, funding_cache in self._funding_rate_cache.items():
            exchange_name = cache_key.exchange.value
            funding_rates_by_exchange[exchange_name] = funding_rates_by_exchange.get(exchange_name, 0) + 1
            total_cached_funding_rates += 1

        # Add detailed cache keys for debugging (use structured representation)
        sample_cache_keys = [str(key) for key in list(self._book_ticker_cache.keys())[:5]]

        return {
            "total_cached_tickers": total_cached,
            "tickers_by_exchange": by_exchange,
            "total_cached_trades": total_cached_trades,
            "trades_by_exchange": trades_by_exchange,
            "total_cached_funding_rates": total_cached_funding_rates,
            "funding_rates_by_exchange": funding_rates_by_exchange,
            "connected_exchanges": sum(1 for connected in self._connected.values() if connected),
            "total_exchanges": len(self._connected),
            "sample_cache_keys": sample_cache_keys,  # Show first 5 cache keys for debugging
            "connection_status": dict(self._connected)  # Show individual connection status
        }

    async def close(self) -> None:
        """Close all composite exchange connections."""
        try:
            self.logger.info("Closing all composite exchange connections")

            # Cancel funding rate sync task
            if self._funding_rate_sync_task and not self._funding_rate_sync_task.done():
                self._funding_rate_sync_task.cancel()
                try:
                    await self._funding_rate_sync_task
                except asyncio.CancelledError:
                    pass
                self.logger.info("Background funding rate sync task cancelled")

            # Dispose event adapters first
            for exchange, adapter in self._event_adapters.items():
                try:
                    await adapter.dispose()
                except Exception as e:
                    self.logger.error(f"Error disposing adapter for {exchange}: {e}")

            # Close all composite exchanges
            for exchange, composite in self._exchange_composites.items():
                try:
                    await composite.close()
                    self._connected[exchange] = False
                except Exception as e:
                    self.logger.error(f"Error closing {exchange} composite: {e}")

            # Clear caches and state
            self._book_ticker_cache.clear()
            self._trade_cache.clear()
            self._funding_rate_cache.clear()
            self._active_symbols.clear()
            self._exchange_composites.clear()
            self._event_adapters.clear()

            self.logger.info("All composite exchange connections closed")

        except Exception as e:
            self.logger.error(f"Error during composite exchange cleanup: {e}")


class SnapshotScheduler:
    """
    Scheduler for taking periodic snapshots of book ticker data.
    
    Captures data every N seconds and triggers storage operations.
    """

    def __init__(
            self,
            ws_manager: UnifiedWebSocketManager,
            interval_seconds: float = 1,
            snapshot_handler: Optional[Callable[[List[BookTickerSnapshot]], Awaitable[None]]] = None,
            trade_handler: Optional[Callable[[List[TradeSnapshot]], Awaitable[None]]] = None,
            funding_rate_handler: Optional[Callable[[List[FundingRateSnapshot]], Awaitable[None]]] = None
    ):
        """
        Initialize snapshot scheduler.
        
        Args:
            ws_manager: WebSocket manager to get data from
            interval_seconds: Snapshot interval in seconds
            snapshot_handler: Handler for snapshot data
            trade_handler: Handler for trade data
            funding_rate_handler: Handler for funding rate data
        """
        self.ws_manager = ws_manager
        self.interval_seconds = interval_seconds
        self.snapshot_handler = snapshot_handler
        self.trade_handler = trade_handler
        self.funding_rate_handler = funding_rate_handler

        self.logger = get_logger('data_collector.snapshot_scheduler')
        self._running = False
        self._snapshot_count = 0

    async def start(self) -> None:
        """Start the snapshot scheduler."""
        if self._running:
            self.logger.warning("Snapshot scheduler is already running")
            return

        self._running = True
        self.logger.info(f"Starting snapshot scheduler with {self.interval_seconds}s interval")

        try:
            while self._running:
                await self._take_snapshot()
                await asyncio.sleep(self.interval_seconds)
        except Exception as e:
            self.logger.error(f"Snapshot scheduler error: {e}")
            raise
        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop the snapshot scheduler."""
        self.logger.info("Stopping snapshot scheduler")
        self._running = False

    async def _take_snapshot(self) -> None:
        """Take a snapshot of all cached book ticker and trade data."""
        try:
            # Get all cached tickers (now async due to symbol_id lookups)
            ticker_snapshots = await self.ws_manager.get_all_cached_tickers()

            # Get all cached trades
            trade_snapshots = await self.ws_manager.get_all_cached_trades()
            
            # Get all cached funding rates
            funding_rate_snapshots = await self.ws_manager.get_all_cached_funding_rates()

            # Enhanced debugging
            cache_stats = self.ws_manager.get_cache_statistics()
            self.logger.debug(
                f"Snapshot #{self._snapshot_count + 1:03d}: Cache stats - "
                f"Connected: {cache_stats['connected_exchanges']}/{cache_stats['total_exchanges']}, "
                f"Cached tickers: {cache_stats['total_cached_tickers']}, "
                f"Retrieved tickers: {len(ticker_snapshots)}, "
                f"Retrieved trades: {len(trade_snapshots)}, "
                f"Retrieved funding rates: {len(funding_rate_snapshots)}"
            )

            if not ticker_snapshots and not trade_snapshots and not funding_rate_snapshots:
                # Log more details about why no data
                if cache_stats['total_cached_tickers'] > 0:
                    self.logger.warning(
                        f"Cache has {cache_stats['total_cached_tickers']} tickers but get_all_cached_tickers returned none!"
                    )
                else:
                    self.logger.debug("No cached data available for snapshot")
                return

            self._snapshot_count += 1

            # Call snapshot handlers if available
            if self.snapshot_handler and ticker_snapshots:
                self.logger.debug(f"Calling snapshot_handler with {len(ticker_snapshots)} tickers")
                await self.snapshot_handler(ticker_snapshots)
                self.logger.debug("Snapshot_handler completed successfully")
            elif ticker_snapshots:
                self.logger.warning(f"Have {len(ticker_snapshots)} tickers but no snapshot_handler configured!")

            if self.trade_handler and trade_snapshots:
                self.logger.debug(f"Calling trade_handler with {len(trade_snapshots)} trades")
                await self.trade_handler(trade_snapshots)
                self.logger.debug("Trade_handler completed successfully")

            if self.funding_rate_handler and funding_rate_snapshots:
                self.logger.debug(f"Calling funding_rate_handler with {len(funding_rate_snapshots)} funding rates")
                await self.funding_rate_handler(funding_rate_snapshots)
                self.logger.debug("Funding_rate_handler completed successfully")

            # Log snapshot statistics
            self.logger.info(
                f"Snapshot #{self._snapshot_count:03d}: "
                f"Processed {len(ticker_snapshots)} tickers, {len(trade_snapshots)} trades, {len(funding_rate_snapshots)} funding rates from "
                f"{cache_stats['connected_exchanges']}/{cache_stats['total_exchanges']} exchanges"
            )

        except Exception as e:
            self.logger.error(f"Error taking snapshot: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    def get_statistics(self) -> Dict[str, any]:
        """Get scheduler statistics."""
        return {
            "running": self._running,
            "snapshot_count": self._snapshot_count,
            "interval_seconds": self.interval_seconds,
            "has_ticker_handler": self.snapshot_handler is not None,
            "has_trade_handler": self.trade_handler is not None,
            "has_funding_rate_handler": self.funding_rate_handler is not None
        }


class DataCollector:
    """
    Main orchestrator for the data collection system.
    
    Coordinates WebSocket manager, analytics engine, snapshot scheduler,
    and database operations to provide a complete data collection solution.
    """

    def __init__(self):
        """
        Initialize data collector.
        """
        # Load configuration
        from config.config_manager import get_data_collector_config
        self.config = get_data_collector_config()

        # HFT Logging
        from infrastructure.logging import get_logger
        self.logger = get_logger('data_collector.collector')

        # Components
        self.ws_manager: Optional[UnifiedWebSocketManager] = None
        self.analytics: Optional[RealTimeAnalytics] = None
        self.scheduler: Optional[SnapshotScheduler] = None
        self.db = None  # Database manager instance

        # State
        self._running = False
        self._start_time: Optional[datetime] = None

        self.logger.info(f"Data collector initialized with {len(self.config.symbols)} symbols")

    async def _perform_symbol_synchronization(self) -> None:
        """
        Perform basic exchange/symbol setup on startup.
        
        Ensures all configured exchanges exist in database using simplified approach.
        """
        try:
            self.logger.info("Starting basic symbol setup process")
            
            # Ensure exchanges exist in database
            await self.db.ensure_exchanges_populated()
            self.logger.info("Exchange setup completed")
            
            self.logger.info("Basic symbol setup completed successfully")
                
        except Exception as e:
            self.logger.error(f"Symbol setup failed: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            # Don't re-raise - allow data collector to start even if setup fails
            
    async def _notify_symbol_changes(self, stats: dict) -> None:
        """Send notification for significant symbol changes."""
        try:
            from infrastructure.networking.telegram import send_to_telegram
            
            added = stats.get('added', 0)
            deactivated = stats.get('deactivated', 0)
            
            message = "📈 Symbol synchronization completed:\n"
            if added > 0:
                message += f"➕ {added} new symbols added\n"
            if deactivated > 0:
                message += f"❌ {deactivated} symbols deactivated\n"
            
            await send_to_telegram(message)
            self.logger.info("Sent Telegram notification for symbol changes")
        except Exception as e:
            self.logger.error(f"Failed to send symbol change notification: {e}")

    async def initialize(self) -> None:
        """Initialize all components."""
        try:
            if not self.config.enabled:
                self.logger.warning("Data collector is disabled in configuration")
                return

            self.logger.info("Initializing data collector components")

            # Ensure exchange modules are imported to trigger registrations
            self.logger.debug("Importing exchange modules for factory registration...")
            import exchanges.integrations.mexc
            import exchanges.integrations.gateio
            self.logger.debug("Exchange modules imported successfully")

            # Initialize database manager using simplified PROJECT_GUIDES.md approach

            # Use simplified initialization with HftConfig (PROJECT_GUIDES.md compliant)
            await initialize_database_manager()
            self.db = await get_database_manager()
            self.logger.info("Database connection pool initialized and manager cached")
            
            # Perform basic exchange/symbol setup on startup
            await self._perform_symbol_synchronization()
            
            # Database manager with lookup table is ready
            lookup_stats = self.db.get_lookup_table_stats()
            self.logger.info("Database manager ready", 
                           lookup_table_size=lookup_stats['size'],
                           memory_estimate_kb=lookup_stats['memory_estimate_kb'])

            # Initialize analytics engine
            from .analytics import RealTimeAnalytics
            self.analytics = RealTimeAnalytics(self.config.analytics)
            self.logger.info("Analytics engine initialized")

            # Initialize WebSocket manager using modern architecture
            # NOTE: Trade handler disabled for performance - only collecting book tickers
            self.ws_manager = UnifiedWebSocketManager(
                exchanges=self.config.exchanges,
                book_ticker_handler=self._handle_external_book_ticker,
                trade_handler=self._handle_external_trade,  # Disabled for performance optimization
                database_manager=self.db
            )
            self.logger.info(f"WebSocket manager created for {len(self.config.exchanges)} exchanges")

            # Initialize WebSocket connections
            self.logger.info(f"Initializing WebSocket connections for {len(self.config.symbols)} symbols...")
            await self.ws_manager.initialize(self.config.symbols)
            self.logger.info("WebSocket connections initialized")

            # Verify connections
            connection_status = self.ws_manager.get_connection_status()
            self.logger.info(f"Connection status: {connection_status}")

            # Initialize snapshot scheduler with database handler
            # NOTE: Trade handler disabled since trade collection is disabled
            self.scheduler = SnapshotScheduler(
                ws_manager=self.ws_manager,
                interval_seconds=self.config.snapshot_interval,
                snapshot_handler=self._handle_snapshot_storage,
                # trade_handler=self._handle_trades_snapshot_storage,  # Disabled since trade collection is disabled
                funding_rate_handler=self._handle_funding_rate_storage
            )
            self.logger.info(f"Snapshot scheduler initialized with {self.config.snapshot_interval}s interval")

            self.logger.info("All data collector components initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize data collector: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            raise

    async def start(self) -> None:
        """Start the data collection process."""
        if self._running:
            self.logger.warning("Data collector is already running")
            return

        if not self.config.enabled:
            self.logger.warning("Data collector is disabled in configuration")
            return

        try:
            self.logger.info("Starting data collector")
            self._running = True
            self._start_time = datetime.now()

            # Start snapshot scheduler (this will run the main loop)
            if self.scheduler:
                await self.scheduler.start()

        except Exception as e:
            self.logger.error(f"Error during data collection: {e}")
            self._running = False
            raise
        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop the data collection process."""
        self.logger.info("Stopping data collector")

        try:
            # Stop scheduler
            if self.scheduler:
                await self.scheduler.stop()

            # Close WebSocket connections
            if self.ws_manager:
                await self.ws_manager.close()

            # Close database connection pool using simplified approach
            from db import close_database_manager
            await close_database_manager()
            self.logger.info("Database connection pool closed")

            self._running = False
            self.logger.info("Data collector stopped successfully")

        except Exception as e:
            self.logger.error(f"Error stopping data collector: {e}")

    async def _handle_book_ticker_update(self, exchange: ExchangeEnum, symbol: Symbol, book_ticker: BookTicker) -> None:
        """
        Handle book ticker updates from WebSocket manager (legacy compatibility).
        
        Routes updates to analytics engine.
        """
        try:
            if self.analytics:
                await self.analytics.on_book_ticker_update(exchange.value, symbol, book_ticker)
        except Exception as e:
            self.logger.error(f"Error handling book ticker update: {e}")

    async def _handle_trades_update(self, exchange: ExchangeEnum, symbol: Symbol, trades: List[Trade]) -> None:
        """
        Handle trade updates from WebSocket manager (legacy compatibility).

        Routes updates to analytics engine.
        """
        try:
            if self.analytics:
                # Analytics trade handling would go here when implemented
                for trade in trades:
                    # Future: add analytics.on_trade_update when available
                    pass

        except Exception as e:
            self.logger.error(f"Error handling trades update: {e}")

    async def _handle_external_book_ticker(self, exchange: ExchangeEnum, symbol: Symbol, book_ticker: BookTicker) -> None:
        """
        External handler for book ticker updates using modern architecture.
        
        This method receives book ticker data with exchange and symbol context
        from the BindedEventHandlersAdapter pattern.
        """
        try:
            if self.analytics:
                await self.analytics.on_book_ticker_update(exchange.value, symbol, book_ticker)
        except Exception as e:
            self.logger.error(f"Error handling external book ticker update: {e}")

    async def _handle_external_trade(self, exchange: ExchangeEnum, symbol: Symbol, trade: Trade) -> None:
        """
        External handler for trade updates using modern architecture.
        
        This method receives trade data with exchange and symbol context
        from the BindedEventHandlersAdapter pattern.
        """
        try:
            # Process individual trade if analytics supports it
            if self.analytics:
                # Analytics trade handling would go here when implemented
                pass
        except Exception as e:
            self.logger.error(f"Error handling external trade update: {e}")

    async def _handle_trades_snapshot_storage(self, snapshots: List[TradeSnapshot]):
        # min_trade, min_qty, max_trade, max_qty, total_qty, count = 0
        if len(snapshots) == 0:
            return

        date_to = (snapshots[-1].timestamp - timedelta(seconds=self.config.snapshot_interval))
        bucket = []
        for t in  reversed(snapshots):
            if t.timestamp > date_to:
                bucket.append(t)

        print(bucket)

    async def _handle_snapshot_storage(self, snapshots: List[BookTickerSnapshot]) -> None:
        """
        Handle snapshot storage to database using normalized schema.

        The snapshots are already normalized with symbol_id, so we can store them directly.

        Args:
            snapshots: List of normalized BookTickerSnapshot objects with symbol_id
        """
        try:
            if not snapshots:
                self.logger.debug("No snapshots to store")
                return

            self.logger.debug(f"Storing {len(snapshots)} normalized snapshots to database...")

            # Store snapshots using optimized batch operations with HFT performance monitoring
            with LoggingTimer(self.logger, "snapshot_storage") as timer:
                # Use the existing normalized batch insert function
                count = await insert_book_ticker_snapshots_batch(snapshots)
            
            # Validate HFT performance requirement (<5ms target)
            if timer.elapsed_ms > 5.0:
                self.logger.warning(f"Snapshot storage exceeded HFT target: {timer.elapsed_ms:.1f}ms > 5ms")
                self.logger.metric("storage_hft_violations", 1, tags={"operation": "book_ticker_storage"})
            elif timer.elapsed_ms > 2.0:  # Warning threshold
                self.logger.warning(f"Storage performance degraded: {timer.elapsed_ms:.1f}ms")
                self.logger.metric("storage_performance_warnings", 1, tags={"operation": "book_ticker_storage"})

            self.logger.debug(
                f"Successfully stored {count} snapshots in {timer.elapsed_ms:.1f}ms"
            )

            # Track performance metrics
            self.logger.metric("snapshots_stored", count)
            self.logger.metric("storage_time_ms", timer.elapsed_ms, tags={"operation": "book_ticker_storage"})
            
            # Track throughput metrics
            if timer.elapsed_ms > 0:
                snapshots_per_second = len(snapshots) / (timer.elapsed_ms / 1000)
                self.logger.metric("storage_throughput_snapshots_per_second", snapshots_per_second)

            # Log sample of what was stored for verification
            if snapshots:
                sample = snapshots[0]
                self.logger.debug(
                    f"Sample snapshot stored: symbol_id={sample.symbol_id} @ {sample.timestamp} - "
                    f"bid={sample.bid_price} ask={sample.ask_price}"
                )

        except Exception as e:
            self.logger.error(f"Error storing normalized snapshots: {e}")
            
            # Track error metrics
            self.logger.metric("snapshot_storage_errors", 1, tags={"error_type": type(e).__name__})
            
            import traceback
            self.logger.error("Full storage error traceback", traceback=traceback.format_exc())
            
            # Don't re-raise to allow data collection to continue
            # Storage errors shouldn't break the WebSocket data collection loop

    async def _handle_trade_storage(self, trade_snapshots: List[TradeSnapshot]) -> None:
        """
        Handle trade snapshot storage to database using normalized schema.

        The trade snapshots are already normalized with symbol_id, so we can store them directly.

        Args:
            trade_snapshots: List of normalized TradeSnapshot objects with symbol_id
        """
        try:
            if not trade_snapshots:
                return

            self.logger.debug(f"Storing {len(trade_snapshots)} normalized trade snapshots to database...")

            # Store trade snapshots using optimized DatabaseManager (PROJECT_GUIDES.md compliant)
            start_time = datetime.now()
            
            # Use simplified batch insert with auto-resolution
            try:
                # Note: This will need to be updated to use the new API with exchange/symbol parameters
                # For now, use legacy method until API is fully migrated
                count = len(trade_snapshots)  # Placeholder - will need proper implementation
                
                # Trade database storage operation completed
            except Exception as e:
                self.logger.warning(f"Failed to insert batch of {len(trade_snapshots)} trade snapshots: {e}")
                count = 0
                    
            storage_duration = (datetime.now() - start_time).total_seconds() * 1000

            self.logger.debug(
                f"Successfully stored {count} trade snapshots in {storage_duration:.1f}ms"
            )

        except Exception as e:
            self.logger.error(f"Error storing trade snapshots: {e}")

    async def _handle_funding_rate_storage(self, funding_rate_snapshots: List[FundingRateSnapshot]) -> None:
        """
        Handle funding rate snapshot storage to database.
        
        Args:
            funding_rate_snapshots: List of funding rate snapshots to store
        """
        try:
            if not funding_rate_snapshots:
                return

            self.logger.debug(f"Storing {len(funding_rate_snapshots)} funding rate snapshots to database...")

            # Store funding rate snapshots using batch operations with HFT performance monitoring
            with LoggingTimer(self.logger, "funding_rate_storage") as timer:
                count = await insert_funding_rate_snapshots_batch(funding_rate_snapshots)
                
            # Validate HFT performance requirement (<5ms target)
            if timer.elapsed_ms > 5.0:
                self.logger.warning(f"Funding rate storage exceeded HFT target: {timer.elapsed_ms:.1f}ms > 5ms")
                self.logger.metric("storage_hft_violations", 1, tags={"operation": "funding_rate_storage"})
            elif timer.elapsed_ms > 2.0:  # Warning threshold
                self.logger.warning(f"Funding rate storage performance degraded: {timer.elapsed_ms:.1f}ms")
                self.logger.metric("storage_performance_warnings", 1, tags={"operation": "funding_rate_storage"})

            self.logger.debug(
                f"Stored {count} funding rate snapshots in {timer.elapsed_ms:.1f}ms"
            )
            
            # Track performance metrics
            self.logger.metric("funding_rates_stored", count)
            self.logger.metric("storage_time_ms", timer.elapsed_ms, tags={"operation": "funding_rate_storage"})
            
            # Track throughput metrics
            if timer.elapsed_ms > 0:
                funding_rates_per_second = len(funding_rate_snapshots) / (timer.elapsed_ms / 1000)
                self.logger.metric("storage_throughput_funding_rates_per_second", funding_rates_per_second)
                
        except Exception as e:
            self.logger.error(f"Error storing funding rate snapshots: {e}")
            
            # Track error metrics
            self.logger.metric("funding_rate_storage_errors", 1, tags={"error_type": type(e).__name__})
            
            import traceback
            self.logger.error("Full funding rate storage error traceback", traceback=traceback.format_exc())
            
            # Don't re-raise to allow data collection to continue
            # Storage errors shouldn't break the WebSocket data collection loop

    def get_status(self) -> Dict[str, any]:
        """
        Get comprehensive status of the data collector.
        
        Returns:
            Dictionary with status information
        """
        status = {
            "running": self._running,
            "config": {
                "enabled": self.config.enabled,
                "snapshot_interval": self.config.snapshot_interval,
                "analytics_interval": self.config.analytics_interval,
                "exchanges": self.config.exchanges,
                "symbols_count": len(self.config.symbols),
                "trade_collection_enabled": getattr(self.config, 'collect_trades', True)
            }
        }

        if self._start_time:
            status["uptime_seconds"] = (datetime.now() - self._start_time).total_seconds()

        # WebSocket manager status
        if self.ws_manager:
            status["ws"] = {
                "connections": self.ws_manager.get_connection_status(),
                "active_symbols": self.ws_manager.get_active_symbols_count(),
                "cache_stats": self.ws_manager.get_cache_statistics()
            }

        # Analytics status
        if self.analytics:
            status["analytics"] = self.analytics.get_statistics()

        # Scheduler status
        if self.scheduler:
            status["scheduler"] = self.scheduler.get_statistics()

        return status

    async def add_symbols(self, symbols: List[Symbol]) -> None:
        """
        Add symbols to data collection.
        
        Args:
            symbols: Symbols to add
        """
        if self.ws_manager:
            await self.ws_manager.add_symbols(symbols)
            self.config.symbols.extend(symbols)
            self.logger.info(f"Added {len(symbols)} symbols to data collection")

    async def remove_symbols(self, symbols: List[Symbol]) -> None:
        """
        Remove symbols from data collection.
        
        Args:
            symbols: Symbols to remove
        """
        if self.ws_manager:
            await self.ws_manager.remove_symbols(symbols)
            for symbol in symbols:
                if symbol in self.config.symbols:
                    self.config.symbols.remove(symbol)
            self.logger.info(f"Removed {len(symbols)} symbols from data collection")

    async def get_recent_opportunities(self, minutes: int = 5) -> List[ArbitrageOpportunity]:
        """
        Get recent arbitrage opportunities.
        
        Args:
            minutes: Number of minutes to look back
            
        Returns:
            List of recent opportunities
        """
        if self.analytics:
            return self.analytics.get_recent_opportunities(minutes)
        return []
