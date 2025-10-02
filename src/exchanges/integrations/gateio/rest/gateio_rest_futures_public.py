import asyncio
import time
from typing import Dict, List, Optional, Any
from datetime import datetime

from exchanges.interfaces.rest import PublicFuturesRestInterface
from exchanges.structs.common import (
    Symbol, SymbolInfo, OrderBook, OrderBookEntry, Trade, Kline,
    Ticker
)
from exchanges.structs.enums import KlineInterval
from exchanges.structs import Side
from infrastructure.logging import HFTLoggerInterface
# Removed BaseExchangeMapper import - using direct utility functions
from infrastructure.networking.http.structs import HTTPMethod
from config.structs import ExchangeConfig
from infrastructure.exceptions.exchange import ExchangeRestError
# Inline utility function to avoid import issues
def get_minimal_step(precision: int) -> float:
    return 10**-precision

# Import direct utility functions
from exchanges.integrations.gateio.services.futures_symbol_mapper import GateioFuturesSymbol
from exchanges.integrations.gateio.services.spot_symbol_mapper import get_exchange_interval


from .gateio_base_futures_rest import GateioBaseFuturesRestInterface

class GateioPublicFuturesRestInterface(GateioBaseFuturesRestInterface, PublicFuturesRestInterface):
    """
    Gate.io public REST client for futures (USDT-settled) — rewritten in the same
    architecture/style as GateioPublicSpotRest.

    Notes:
    - Uses injected mapper for symbol <-> contract conversion.
    - Endpoints under '/futures/usdt/*'.
    - Robust parsing: supports both array and dict payload shapes.
    """

    def __init__(self, config: ExchangeConfig, logger: HFTLoggerInterface = None, **kwargs):
        """
        Initialize Gate.io public futures REST client with simplified constructor.
        
        Args:
            config: ExchangeConfig with Gate.io configuration
            logger: HFT logger instance (injected)
            **kwargs: Additional parameters for compatibility
        """
        # Initialize base REST client (rate_limiter created internally)
        super().__init__(config, logger, is_private=False)

        # caching for contract info (only config data)
        self._exchange_info: Optional[Dict[Symbol, SymbolInfo]] = None
        self._cache_timestamp: float = 0.0
        self._cache_ttl: float = 300.0  # 5 minutes

    async def get_symbols_info(self) -> Dict[Symbol, SymbolInfo]:
        """
        Get futures contract information and map to SymbolInfo.
        Cached for _cache_ttl seconds.
        """
        current_time = time.time()
        if self._exchange_info is not None and (current_time - self._cache_timestamp) < self._cache_ttl:
            return self._exchange_info

        try:
            response_data = await self.request(
                HTTPMethod.GET,
                '/futures/usdt/contracts'  # futures contracts list
            )

            if not isinstance(response_data, list):
                raise ExchangeRestError(500, "Invalid contracts response format")

            symbol_info_map: Dict[Symbol, SymbolInfo] = {}
            filtered_count = 0

            for c in response_data:
                # The contract identifier might be in different fields ('name' or 'contract' or 'id')
                contract_name = c.get('name') or c.get('contract') or c.get('id') or ''
                if not contract_name:
                    filtered_count += 1
                    continue

                # Use shared mapper - it must support futures contract format
                if not GateioFuturesSymbol.is_supported_pair(contract_name):
                    filtered_count += 1
                    continue

                try:
                    symbol = GateioFuturesSymbol.to_symbol(contract_name)
                except Exception:
                    filtered_count += 1
                    continue

                quote_prec = base_prec = 2
                min_base = min_quote =  float(c.get('order_size_min', 3))

                is_inactive = c.get('status', '') != 'trading' and c.get('trade_status', '') != 'tradable'

                #TODO: save funding rate, for get_funding_rate()
                # c.get('funding_interval', 0)
                # c.get('funding_rate', 0)
                # c.get('funding_next_apply', 0)
                # funding_rate_indicative, funding_offset, funding_impact_value, funding_cap_ratio

                # Build SymbolInfo (futures)
                symbol_info = SymbolInfo(
                    symbol=symbol,
                    base_precision=base_prec,
                    quote_precision=quote_prec,
                    min_base_quantity=min_base,
                    min_quote_quantity=min_quote,
                    is_futures=True,
                    maker_commission=float(c.get('maker_fee', 0)) if c.get('maker_fee') else 0.0,
                    taker_commission=float(c.get('taker_fee', 0)) if c.get('taker_fee') else 0.0,
                    inactive=is_inactive,
                    tick=get_minimal_step(quote_prec),
                    step=get_minimal_step(base_prec),
                )
                symbol_info_map[symbol] = symbol_info

            self._exchange_info = symbol_info_map
            self._cache_timestamp = current_time

            self.logger.info(f"Retrieved futures contract info for {len(symbol_info_map)} contracts, filtered {filtered_count}")
            return symbol_info_map

        except Exception as e:
            self.logger.error(f"Failed to get futures exchange info: {e}")
            raise ExchangeRestError(500, f"Futures exchange info fetch failed: {str(e)}")

    async def get_orderbook(self, symbol: Symbol, limit: int = 100) -> OrderBook:
        """
        Get futures order book. Endpoint: /futures/usdt/order_book
        """
        try:
            contract = GateioFuturesSymbol.to_pair(symbol)  # should output e.g. "BTC_USDT" or "BTC_USDT_20241225"

            optimized_limit = max(1, min(100, limit))
            params = {
                'contract': contract,
                'limit': optimized_limit,
                'with_id': 'false'
            }

            response_data = await self.request(
                HTTPMethod.GET,
                '/futures/usdt/order_book',
                params=params
            )

            # Support both formats: list of pairs or dict entries with keys 'p'/'s' or arrays
            def parse_side(entries) -> List[OrderBookEntry]:
                result = []
                for e in entries:
                    try:
                        if isinstance(e, (list, tuple)) and len(e) >= 2:
                            price = float(e[0])
                            size = float(e[1])
                        elif isinstance(e, dict):
                            # some endpoints use {'p': price, 's': size} or {'price':..., 'size':...}
                            price = float(e.get('p') or e.get('price') or 0)
                            size = float(e.get('s') or e.get('size') or 0)
                        else:
                            continue
                        result.append(OrderBookEntry(price=price, size=abs(size)))
                    except Exception:
                        continue
                return result

            bids = parse_side(response_data.get('bids', []))
            asks = parse_side(response_data.get('asks', []))

            timestamp_val = response_data.get('current') or response_data.get('timestamp') or response_data.get('time')
            timestamp = float(timestamp_val) / 1000.0 if timestamp_val else time.time()

            orderbook = OrderBook(symbol=symbol, bids=bids, asks=asks, timestamp=timestamp)
            self.logger.debug(f"Retrieved futures orderbook for {symbol}: {len(bids)} bids, {len(asks)} asks")
            return orderbook

        except Exception as e:
            self.logger.error(f"Failed to get futures orderbook for {symbol}: {e}")
            raise ExchangeRestError(500, f"Futures orderbook fetch failed: {str(e)}")

    async def get_recent_trades(self, symbol: Symbol, limit: int = 500) -> List[Trade]:
        """
        Get recent trades for futures symbol. Endpoint: /futures/usdt/trades
        Gate.io futures may use signed 'size' (positive buy, negative sell).
        """
        try:
            contract = GateioFuturesSymbol.to_pair(symbol)
            optimized_limit = max(1, min(1000, limit))
            params = {'contract': contract, 'limit': optimized_limit}

            response_data = await self.request(
                HTTPMethod.GET,
                '/futures/usdt/trades',
                params=params
            )

            if not isinstance(response_data, list):
                raise ExchangeRestError(500, "Invalid futures trades response format")

            trades: List[Trade] = []
            for td in response_data:
                try:
                    # Support multiple field names
                    size_val = td.get('size') or td.get('amount') or td.get('qty') or 0
                    size = float(size_val)
                    side = Side.BUY if size > 0 else Side.SELL if size < 0 else to_side(td.get('side', 'buy'))

                    price = float(td.get('price', td.get('p', 0)))
                    ts = td.get('create_time_ms') or td.get('create_time') or td.get('t') or int(time.time() * 1000)
                    ts = int(ts) if isinstance(ts, (int, float)) else int(float(ts))

                    trade = Trade(
                        symbol=symbol,
                        price=price,
                        quantity=abs(size),
                        side=side,
                        timestamp=ts,
                        is_maker=False,
                        trade_id=td.get('id')
                    )
                    trades.append(trade)
                except Exception:
                    self.logger.debug(f"Failed to parse futures trade item: {td}")
                    continue

            self.logger.debug(f"Retrieved {len(trades)} futures recent trades for {symbol}")
            return trades

        except Exception as e:
            self.logger.error(f"Failed to get futures recent trades for {symbol}: {e}")
            raise ExchangeRestError(500, f"Futures recent trades fetch failed: {str(e)}")

    async def get_historical_trades(self, symbol: Symbol, limit: int = 500,
                                    timestamp_from: Optional[int] = None,
                                    timestamp_to: Optional[int] = None) -> List[Trade]:
        """
        Get historical trades for futures with optional timestamp filtering.
        Gate.io expects seconds for 'from'/'to'.
        """
        try:
            contract = GateioFuturesSymbol.to_pair(symbol)
            optimized_limit = max(1, min(1000, limit))
            params = {'contract': contract, 'limit': optimized_limit}
            if timestamp_from:
                params['from'] = timestamp_from // 1000
            if timestamp_to:
                params['to'] = timestamp_to // 1000

            response_data = await self.request(
                HTTPMethod.GET,
                '/futures/usdt/trades',
                params=params
            )

            if not isinstance(response_data, list):
                raise ExchangeRestError(500, "Invalid futures historical trades format")

            trades: List[Trade] = []
            for td in response_data:
                try:
                    size = float(td.get('size', td.get('amount', 0)))
                    side = Side.BUY if size > 0 else Side.SELL if size < 0 else to_side(td.get('side', 'buy'))
                    ts = td.get('create_time_ms') or td.get('create_time') or int(time.time() * 1000)
                    ts = int(ts) if isinstance(ts, (int, float)) else int(float(ts))

                    trade = Trade(
                        symbol=symbol,
                        price=float(td.get('price', td.get('p', 0))),
                        quantity=abs(size),
                        side=side,
                        timestamp=ts,
                        is_maker=False,
                        trade_id=td.get('id')
                    )
                    trades.append(trade)
                except Exception:
                    self.logger.debug(f"Failed to parse historical trade: {td}")
                    continue

            # sort newest first like spot implementation
            trades.sort(key=lambda t: t.timestamp, reverse=True)
            self.logger.debug(f"Retrieved {len(trades)} futures historical trades for {symbol}")
            return trades

        except Exception as e:
            self.logger.error(f"Failed to get futures historical trades for {symbol}: {e}")
            raise ExchangeRestError(500, f"Futures historical trades fetch failed: {str(e)}")

    async def get_ticker_info(self, symbol: Optional[Symbol] = None) -> Dict[Symbol, Ticker]:
        """
        Get futures tickers. Endpoint: /futures/usdt/tickers
        Can request single symbol via 'contract' param or get all tickers.
        Returns mapping Symbol -> Ticker (similar to spot signature).
        """
        try:
            params = {}
            if symbol:
                params['contract'] = GateioFuturesSymbol.to_pair(symbol)

            response_data = await self.request(
                HTTPMethod.GET,
                '/futures/usdt/tickers',
                params=params
            )

            tickers_data = response_data if isinstance(response_data, list) else [response_data]
            tickers: Dict[Symbol, Ticker] = {}

            for td in tickers_data:
                pair_str = td.get('contract') or td.get('name') or td.get('currency_pair') or ''
                if not pair_str:
                    continue
                if not GateioFuturesSymbol.is_supported_pair(pair_str):
                    continue
                try:
                    symbol_obj = GateioFuturesSymbol.to_symbol(pair_str)
                except Exception:
                    continue

                last_price = float(td.get('last', td.get('last_price', 0)))
                change_24h = float(td.get('change', td.get('change_utc0', 0)))
                base_volume = float(td.get('base_volume', 0))
                quote_volume = float(td.get('quote_volume', 0))
                current_time = int(time.time() * 1000)
                open_time = current_time - (24 * 60 * 60 * 1000)
                close_time = current_time

                ticker = Ticker(
                    symbol=symbol_obj,
                    price_change=change_24h,
                    price_change_percent=float(td.get('change_percentage', 0)),
                    weighted_avg_price=(quote_volume / base_volume) if base_volume > 0 else last_price,
                    prev_close_price=last_price - change_24h if last_price and change_24h else last_price,
                    last_price=last_price,
                    last_qty=0.0,
                    open_price=last_price - change_24h if last_price and change_24h else last_price,
                    high_price=float(td.get('high', td.get('high_24h', 0))),
                    low_price=float(td.get('low', td.get('low_24h', 0))),
                    volume=base_volume,
                    quote_volume=quote_volume,
                    open_time=open_time,
                    close_time=close_time,
                    count=0,
                    bid_price=float(td.get('highest_bid', td.get('bid', 0))) if td.get('highest_bid') or td.get('bid') else None,
                    bid_qty=None,
                    ask_price=float(td.get('lowest_ask', td.get('ask', 0))) if td.get('lowest_ask') or td.get('ask') else None,
                    ask_qty=None,
                    first_id=None,
                    last_id=None
                )

                tickers[symbol_obj] = ticker

            self.logger.debug(f"Retrieved {len(tickers)} futures ticker(s)")
            return tickers

        except Exception as e:
            self.logger.error(f"Failed to get futures ticker info: {e}")
            raise ExchangeRestError(500, f"Futures ticker info fetch failed: {str(e)}")

    async def get_funding_rate(self, symbol: Symbol) -> Dict[str, Any]:
        """
        Get funding rate for a contract. Endpoint: /futures/usdt/funding_rate
        Returns raw dict (public-only).
        """
        try:
            contract = GateioFuturesSymbol.to_pair(symbol)
            params = {'contract': contract}
            response_data = await self.request(
                HTTPMethod.GET,
                '/futures/usdt/funding_rate',
                params=params
            )
            # Accept list or single object
            if isinstance(response_data, list) and response_data:
                return response_data[0]
            return response_data

        except Exception as e:
            self.logger.error(f"Failed to get funding rate for {symbol}: {e}")
            raise ExchangeRestError(500, f"Futures funding rate fetch failed: {str(e)}")

    async def get_klines(self, symbol: Symbol, timeframe: KlineInterval, date_from: Optional[datetime],
        date_to: Optional[datetime] ) -> List[Kline]:
        """
        Get futures candlesticks. Endpoint: /futures/usdt/candlesticks
        Gate.io returns array of dicts: {'o', 'h', 'l', 'c', 'v', 't', 'sum'}
        """
        try:
            contract = GateioFuturesSymbol.to_pair(symbol)
            interval = get_exchange_interval(timeframe)

            params = {'contract': contract, 'interval': interval}
            if date_from:
                params['from'] = int(date_from.timestamp())
            if date_to:
                params['to'] = int(date_to.timestamp())
            else:
                params['limit'] = 500

            response_data = await self.request(
                HTTPMethod.GET,
                '/futures/usdt/candlesticks',
                params=params
            )

            if not isinstance(response_data, list):
                raise ExchangeRestError(500, "Invalid futures candlesticks response format")

            klines: List[Kline] = []
            for k in response_data:
                try:
                    # Поддержка формата dict
                    ts = int(k.get("t", 0)) * 1000
                    open_price = float(k.get("o", 0))
                    high_price = float(k.get("h", 0))
                    low_price = float(k.get("l", 0))
                    close_price = float(k.get("c", 0))
                    volume = float(k.get("v", 0))
                    quote_volume = float(k.get("sum", 0))

                    kline = Kline(
                        symbol=symbol,
                        interval=timeframe,
                        open_time=ts,
                        close_time=ts + self._get_interval_milliseconds(timeframe),
                        open_price=open_price,
                        high_price=high_price,
                        low_price=low_price,
                        close_price=close_price,
                        volume=volume,
                        quote_volume=quote_volume,
                        trades_count=0
                    )
                    klines.append(kline)
                except Exception:
                    self.logger.debug(f"Failed to parse futures kline: {k}")
                    continue

            self.logger.debug(f"Retrieved {len(klines)} futures klines for {contract}")
            return klines

        except Exception as e:
            self.logger.error(f"Failed to get futures klines for {symbol}: {e}")
            raise ExchangeRestError(500, f"Futures klines fetch failed: {str(e)}")

    async def get_klines_batch(self, symbol: Symbol, timeframe: KlineInterval,
                               date_from: Optional[datetime], date_to: Optional[datetime]) -> List[Kline]:
        """
        Batch klines retrieval. Delegates to get_klines for single-range requests.
        """
        if not date_from or not date_to:
            return await self.get_klines(symbol, timeframe, date_from, date_to)

        # Reuse spot-like batching logic (conservative limits)
        interval_seconds = self._get_interval_seconds(timeframe)
        if interval_seconds == 0:
            return await self.get_klines(symbol, timeframe, date_from, date_to)

        # Conservative safety window similar to spot implementation
        MAX_SAFE_DAYS = 2
        MAX_SAFE_DURATION_SECONDS = MAX_SAFE_DAYS * 24 * 3600
        total_duration_seconds = int((date_to - date_from).total_seconds())

        if total_duration_seconds > MAX_SAFE_DURATION_SECONDS:
            adjusted_date_from = datetime.fromtimestamp(date_to.timestamp() - MAX_SAFE_DURATION_SECONDS)
            self.logger.warning(
                f"Adjusted futures start date from {date_from} to {adjusted_date_from} due to API historical limits"
            )
            date_from = adjusted_date_from
            total_duration_seconds = MAX_SAFE_DURATION_SECONDS

        # Compute batch size similar to spot conservative defaults
        batch_size = 500  # Fixed batch size for simplicity, same as spot implementation
        chunk_duration_seconds = batch_size * interval_seconds

        all_klines: List[Kline] = []
        current_start = date_from

        while current_start < date_to:
            chunk_end = datetime.fromtimestamp(min(current_start.timestamp() + chunk_duration_seconds, date_to.timestamp()))
            chunk = await self.get_klines(symbol, timeframe, current_start, chunk_end)
            all_klines.extend(chunk)
            current_start = datetime.fromtimestamp(chunk_end.timestamp() + interval_seconds)
            if not chunk or current_start >= date_to:
                break
            await asyncio.sleep(0.3)  # rate limit guard

        # Remove duplicates and sort oldest first
        unique = {k.open_time: k for k in all_klines}
        sorted_klines = sorted(unique.values(), key=lambda k: k.open_time)
        self.logger.info(f"Retrieved {len(sorted_klines)} futures klines in batch for {symbol}")
        return sorted_klines

    async def get_server_time(self) -> int:
        """
        Return server time in milliseconds. Use spot time endpoint (shared) if available, otherwise local time.
        """
        try:
            response_data = await self.request(HTTPMethod.GET, '/spot/time')
            server_time = response_data.get('server_time', int(time.time()))
            if server_time < 1e10:
                server_time *= 1000
            return int(server_time)
        except Exception:
            # Fallback to local system time
            return int(time.time() * 1000)

    async def ping(self) -> bool:
        """
        Ping futures API by requesting a light-weight endpoint.
        """
        try:
            # small call to contracts with limit=1
            await self.request(HTTPMethod.GET, '/futures/usdt/contracts', params={'limit': 1})
            return True
        except Exception as e:
            self.logger.debug(f"Futures ping failed: {e}")
            return False

    # Lifecycle & helpers (initialize / start / stop similar to spot)
    async def init(self, symbols: List[Symbol]) -> None:
        self.logger.info(f"Initializing Gate.io Futures client with {len(symbols)} symbols")
        for s in symbols:
            # prime mapper conversions / validation
            try:
                GateioFuturesSymbol.to_pair(s)
            except Exception as e:
                self.logger.debug(f"Failed to pre-cache symbol {s}: {e}")
        self.logger.info("Gate.io Futures initialization complete")

    async def start_symbol(self, symbol: Symbol) -> None:
        contract = GateioFuturesSymbol.to_pair(symbol)
        self.logger.debug(f"Start symbol requested for {contract} (public-only no-op)")

    async def stop_symbol(self, symbol: Symbol) -> None:
        contract = GateioFuturesSymbol.to_pair(symbol)
        self.logger.debug(f"Stop symbol requested for {contract} (public-only no-op)")

    def _get_interval_seconds(self, interval: KlineInterval) -> int:
        """Get interval duration in seconds for batch processing."""
        interval_map = {
            KlineInterval.MINUTE_1: 60,
            KlineInterval.MINUTE_5: 300,
            KlineInterval.MINUTE_15: 900,
            KlineInterval.MINUTE_30: 1800,
            KlineInterval.HOUR_1: 3600,
            KlineInterval.HOUR_4: 14400,
            KlineInterval.HOUR_12: 43200,
            KlineInterval.DAY_1: 86400,
            KlineInterval.WEEK_1: 604800,
            KlineInterval.MONTH_1: 2592000  # 30 days approximation
        }
        return interval_map.get(interval, 0)

    def _get_interval_milliseconds(self, interval: KlineInterval) -> int:
        """Get interval duration in milliseconds for close time calculation."""
        return self._get_interval_seconds(interval) * 1000

    async def close(self):
        self.logger.info("Closed Gate.io futures public client")

    def __repr__(self) -> str:
        return f"GateioPublicFuturesRest(base_url={self.base_url})"
