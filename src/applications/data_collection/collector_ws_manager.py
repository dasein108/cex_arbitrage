import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Union, Set

from config import get_exchange_config
from db import BookTickerSnapshot, TradeSnapshot
from db.models import FundingRateSnapshot
from exchanges.adapters import BindedEventHandlersAdapter
from exchanges.exchange_factory import get_composite_implementation
from exchanges.interfaces.composite.futures.base_public_futures_composite import CompositePublicFuturesExchange
from exchanges.interfaces.composite.spot.base_public_spot_composite import CompositePublicSpotExchange
from exchanges.structs import ExchangeEnum, Symbol, BookTicker, Trade
from infrastructure.logging import get_logger
from infrastructure.networking.websocket.structs import PublicWebsocketChannelType
from dataclasses import dataclass

@dataclass
class DataCache:
    """Simple cache for collected data."""
    book_tickers: List[BookTickerSnapshot]
    trades: List[TradeSnapshot]
    funding_rates: List[FundingRateSnapshot]

    def __init__(self):
        self.book_tickers = []
        self.last_book_ticker: Dict[Symbol, BookTicker] = {}
        self.trades = []
        self.funding_rates = []

    def clear(self):
        """Clear all cached data."""
        self.book_tickers.clear()
        self.trades.clear()
        self.funding_rates.clear()



class CollectorWebSocketManager:
    """Simple WebSocket manager for collecting market data."""

    def __init__(self, exchanges: List[ExchangeEnum], database_manager=None):
        """Initialize WebSocket manager."""
        self.exchanges = exchanges
        self.db = database_manager
        self.logger = get_logger('data_collector')

        # Exchange clients
        self._exchanges: Dict[ExchangeEnum, Union[CompositePublicSpotExchange, CompositePublicFuturesExchange]] = {}
        self._event_adapters: Dict[ExchangeEnum, BindedEventHandlersAdapter] = {}
        self._active_symbols: Dict[ExchangeEnum, Set[Symbol]] = {}
        self._connected: Dict[ExchangeEnum, bool] = {}

        # Data cache
        self.cache = DataCache()

        # Background tasks
        self._funding_rate_sync_task: Optional[asyncio.Task] = None

    async def initialize(self, symbols: List[Symbol]) -> None:
        """Initialize WebSocket connections."""
        self.logger.info(f"Initializing {len(symbols)} symbols on {len(self.exchanges)} exchanges")

        for exchange in self.exchanges:
            await self._initialize_exchange_client(exchange, symbols)

        # Start funding rate collection for futures exchanges
        self._funding_rate_sync_task = asyncio.create_task(self._funding_rate_sync_loop())



        self.logger.info("WebSocket connections initialized")

    async def _initialize_exchange_client(self, exchange: ExchangeEnum, symbols: List[Symbol]) -> None:
        """Initialize exchange client for data collection."""
        try:
            config = get_exchange_config(exchange.value)
            public_exchange = get_composite_implementation(exchange_config=config, is_private=False)

            # Create event adapter
            # adapter = BindedEventHandlersAdapter(self.logger).bind_to_exchange(public_exchange)

            # Bind handlers
            public_exchange.bind(PublicWebsocketChannelType.BOOK_TICKER,
                        lambda book_ticker: self._handle_book_ticker_update(exchange, book_ticker.symbol, book_ticker))
            public_exchange.bind(PublicWebsocketChannelType.PUB_TRADE,
                        lambda trade: self._handle_trade_update(exchange, trade.symbol, trade))

            # adapter.bind(PublicWebsocketChannelType.TICKER,
            #            lambda ticker: self._handle_ticker_update(exchange, ticker))
            #
            # Store components
            self._exchanges[exchange] = public_exchange
            # self._event_adapters[exchange] = adapter
            self._active_symbols[exchange] = set()

            # Initialize
            channels = [PublicWebsocketChannelType.BOOK_TICKER, PublicWebsocketChannelType.PUB_TRADE]
            # if config.is_futures:
            #     channels.append(PublicWebsocketChannelType.TICKER)

            await public_exchange.initialize(symbols, channels, ensure_connection=True)
            self._active_symbols[exchange].update(symbols)
            self._connected[exchange] = True

            self.logger.info(f"Initialized {exchange.value} with {len(symbols)} symbols")

        except Exception as e:
            self.logger.error(f"Failed to initialize {exchange.value}: {e}")
            self._connected[exchange] = False
            raise

    async def _handle_book_ticker_update(self, exchange: ExchangeEnum, symbol: Symbol, book_ticker: BookTicker) -> None:
        """Handle book ticker updates."""
        try:
            # Get symbol_id for database storage
            symbol_id = await self.db.resolve_symbol_id_async(exchange, symbol)
            if not symbol_id:
                self.logger.warning(f"Cannot resolve symbol_id for {exchange.value} {symbol.base}/{symbol.quote}")
                return

            last_book_ticker = self.cache.last_book_ticker.get(symbol)
            if (last_book_ticker and last_book_ticker.bid_price == book_ticker.bid_price and
                    last_book_ticker.ask_price == book_ticker.ask_price):
                # No change in prices, skip
                return

            # Update last book ticker
            self.cache.last_book_ticker[symbol] = book_ticker
            # Create snapshot
            snapshot = BookTickerSnapshot.from_symbol_id_and_data(
                symbol_id=symbol_id,
                bid_price=book_ticker.bid_price,
                bid_qty=book_ticker.bid_quantity,
                ask_price=book_ticker.ask_price,
                ask_qty=book_ticker.ask_quantity,
                timestamp=datetime.now(timezone.utc)
            )

            # Add to cache
            self.cache.book_tickers.append(snapshot)

        except Exception as e:
            self.logger.error(f"Error handling book ticker for {exchange.value} {symbol}: {e}")

    async def _handle_trade_update(self, exchange: ExchangeEnum, symbol: Symbol, trade: Trade) -> None:
        """Handle trade updates."""
        try:
            # Get symbol_id for database storage
            symbol_id = await self.db.resolve_symbol_id_async(exchange, symbol)
            if not symbol_id:
                return

            # Create snapshot
            snapshot = TradeSnapshot.from_symbol_id_and_trade(symbol_id=symbol_id, trade=trade)

            # Add to cache
            self.cache.trades.append(snapshot)

        except Exception as e:
            self.logger.error(f"Error handling trade for {exchange.value} {symbol}: {e}")


    # async def _handle_ticker_update(self, exchange: ExchangeEnum, ticker_data: any) -> None:
    #     """Handle ticker updates for funding rate data."""
    #     try:
    #         config = get_exchange_config(exchange.value)
    #         if not config.is_futures:
    #             return
    #
    #         # Extract data from ticker
    #         symbol = getattr(ticker_data, 'symbol', None)
    #         funding_rate = getattr(ticker_data, 'funding_rate', None)
    #         funding_time = getattr(ticker_data, 'funding_time', None)
    #
    #         if not symbol or funding_rate is None:
    #             return
    #
    #         # Get symbol_id
    #         symbol_id = await self.db.resolve_symbol_id_async(exchange, symbol)
    #         if not symbol_id:
    #             return
    #
    #         # Create funding rate snapshot
    #         snapshot = FundingRateSnapshot.from_symbol_and_data(
    #             exchange=exchange.value,
    #             symbol=symbol,
    #             funding_rate=funding_rate,
    #             next_funding_time=funding_time,
    #             timestamp=datetime.now(timezone.utc),
    #             symbol_id=symbol_id
    #         )
    #
    #         # Add to cache
    #         self.cache.funding_rates.append(snapshot)
    #
    #     except Exception as e:
    #         self.logger.error(f"Error handling ticker from {exchange.value}: {e}")

    async def _funding_rate_sync_loop(self) -> None:
        """Background funding rate sync loop."""
        while True:
            try:
                await asyncio.sleep(300)  # 5 minutes
                await self._sync_funding_rates()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in funding rate sync: {e}")

    async def _sync_funding_rates(self) -> None:
        """Sync funding rates from REST APIs."""
        for exchange, composite in self._exchanges.items():
            if not self._connected.get(exchange, False):
                continue

            config = get_exchange_config(exchange.value)
            if not config.is_futures:
                continue

            try:
                # Get active symbols for this exchange
                active_symbols = self._active_symbols.get(exchange, set())

                # Get ticker info from REST API
                ticker_info = await composite.rest_client.get_ticker_info()

                for symbol in active_symbols:
                    try:
                        symbol_id = await self.db.resolve_symbol_id_async(exchange, symbol)
                        if not symbol_id:
                            continue

                        # Get funding rate from ticker data
                        symbol_ticker = ticker_info.get(symbol)
                        if not symbol_ticker:
                            continue

                        snapshot = FundingRateSnapshot.from_symbol_and_data(
                            exchange=exchange.value,
                            symbol=symbol,
                            funding_rate=symbol_ticker.funding_rate,
                            next_funding_time=symbol_ticker.funding_time,
                            timestamp=datetime.now(timezone.utc),
                            symbol_id=symbol_id
                        )

                        self.cache.funding_rates.append(snapshot)

                    except Exception as e:
                        self.logger.error(f"Error syncing funding rate for {exchange.value} {symbol}: {e}")

            except Exception as e:
                self.logger.error(f"Error syncing funding rates for {exchange.value}: {e}")

    async def close(self) -> None:
        """Close connections and cleanup."""
        if self._funding_rate_sync_task:
            self._funding_rate_sync_task.cancel()

        for adapter in self._event_adapters.values():
            try:
                await adapter.dispose()
            except Exception:
                pass

        for exchange_client in self._exchanges.values():
            try:
                await exchange_client.close()
            except Exception:
                pass

        self.cache.clear()
