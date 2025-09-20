import asyncio
import time
from typing import Dict, List, Optional, Any
from datetime import datetime

from structs.common import (
    Symbol, SymbolInfo, OrderBook, OrderBookEntry, Trade, Kline,
    ExchangeName, KlineInterval, Ticker, Side
)
from core.cex.rest.spot.base_rest_spot_public import PublicExchangeSpotRestInterface
from core.transport.rest.structs import HTTPMethod
from core.config.structs import ExchangeConfig
from core.exceptions.exchange import BaseExchangeError


class GateioPublicFuturesRest(PublicExchangeSpotRestInterface):
    """
    Gate.io public REST client for futures (USDT-settled) — rewritten in the same
    architecture/style as GateioPublicSpotRest.

    Notes:
    - Uses shared self._mapper for symbol <-> contract conversion (no separate mapper).
    - Endpoints under '/futures/usdt/*'.
    - Robust parsing: supports both array and dict payload shapes.
    """

    def __init__(self, config: ExchangeConfig):
        super().__init__(config)

        # caching for contract info (only config data)
        self._exchange_info: Optional[Dict[Symbol, SymbolInfo]] = None
        self._cache_timestamp: float = 0.0
        self._cache_ttl: float = 300.0  # 5 minutes

    def _extract_contract_precision(self, contract_data: Dict[str, Any]) -> tuple[int, int, float, float]:
        """
        Extract common precision/limits from a futures contract entry.
        Fields differ across endpoints; provide safe defaults.
        Returns: base_precision, quote_precision, min_quote_amount, min_base_amount
        """
        def precision_to_decimals(value) -> int:
            """Convert precision value to decimal places count."""
            if isinstance(value, (int, float)):
                if value == 0:
                    return 8
                # Count decimal places from scientific notation
                precision_str = f"{float(value):.10f}".rstrip('0')
                if '.' in precision_str:
                    return len(precision_str.split('.')[1])
                return 0
            elif isinstance(value, str):
                try:
                    return precision_to_decimals(float(value))
                except (ValueError, TypeError):
                    return 8
            return 8

        base_prec = precision_to_decimals(contract_data.get('order_price_round', contract_data.get('price_precision', 8)))
        quote_prec = precision_to_decimals(contract_data.get('mark_price_round', contract_data.get('size_precision', 8)))

        min_base = float(contract_data.get('order_size_min', contract_data.get('min_size', 0)))
        min_quote = float(contract_data.get('min_quote_amount', 0))

        return base_prec, quote_prec, min_quote, min_base

    async def get_exchange_info(self) -> Dict[Symbol, SymbolInfo]:
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
                raise BaseExchangeError(500, "Invalid contracts response format")

            symbol_info_map: Dict[Symbol, SymbolInfo] = {}
            filtered_count = 0

            for c in response_data:
                # The contract identifier might be in different fields ('name' or 'contract' or 'id')
                contract_name = c.get('name') or c.get('contract') or c.get('id') or ''
                if not contract_name:
                    filtered_count += 1
                    continue

                # Use shared mapper - it must support futures contract format
                if not self._mapper.is_supported_pair(contract_name):
                    filtered_count += 1
                    continue

                try:
                    symbol = self._mapper.to_symbol(contract_name)
                except Exception:
                    filtered_count += 1
                    continue

                base_prec, quote_prec, min_quote, min_base = self._extract_contract_precision(c)

                is_inactive = c.get('status', '') != 'trading' and c.get('trade_status', '') != 'tradable'

                # Build SymbolInfo (futures)
                symbol_info = SymbolInfo(
                    symbol=symbol,
                    base_precision=base_prec,
                    quote_precision=quote_prec,
                    min_base_amount=min_base,
                    min_quote_amount=min_quote,
                    is_futures=True,
                    maker_commission=float(c.get('maker_fee', 0)) if c.get('maker_fee') else 0.0,
                    taker_commission=float(c.get('taker_fee', 0)) if c.get('taker_fee') else 0.0,
                    inactive=is_inactive
                )
                symbol_info_map[symbol] = symbol_info

            self._exchange_info = symbol_info_map
            self._cache_timestamp = current_time

            self.logger.info(f"Retrieved futures contract info for {len(symbol_info_map)} contracts, filtered {filtered_count}")
            return symbol_info_map

        except Exception as e:
            self.logger.error(f"Failed to get futures exchange info: {e}")
            raise BaseExchangeError(500, f"Futures exchange info fetch failed: {str(e)}")

    async def get_orderbook(self, symbol: Symbol, limit: int = 100) -> OrderBook:
        """
        Get futures order book. Endpoint: /futures/usdt/order_book
        """
        try:
            contract = self._mapper.to_pair(symbol)  # mapper should output e.g. "BTC_USDT" or "BTC_USDT_20241225"

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

            orderbook = OrderBook(bids=bids, asks=asks, timestamp=timestamp)
            self.logger.debug(f"Retrieved futures orderbook for {symbol}: {len(bids)} bids, {len(asks)} asks")
            return orderbook

        except Exception as e:
            self.logger.error(f"Failed to get futures orderbook for {symbol}: {e}")
            raise BaseExchangeError(500, f"Futures orderbook fetch failed: {str(e)}")

    async def get_recent_trades(self, symbol: Symbol, limit: int = 500) -> List[Trade]:
        """
        Get recent trades for futures symbol. Endpoint: /futures/usdt/trades
        Gate.io futures may use signed 'size' (positive buy, negative sell).
        """
        try:
            contract = self._mapper.to_pair(symbol)
            optimized_limit = max(1, min(1000, limit))
            params = {'contract': contract, 'limit': optimized_limit}

            response_data = await self.request(
                HTTPMethod.GET,
                '/futures/usdt/trades',
                params=params
            )

            if not isinstance(response_data, list):
                raise BaseExchangeError(500, "Invalid futures trades response format")

            trades: List[Trade] = []
            for td in response_data:
                try:
                    # Support multiple field names
                    size_val = td.get('size') or td.get('amount') or td.get('qty') or 0
                    size = float(size_val)
                    side = Side.BUY if size > 0 else Side.SELL if size < 0 else self._mapper.get_unified_side(td.get('side', 'buy'))

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
            raise BaseExchangeError(500, f"Futures recent trades fetch failed: {str(e)}")

    async def get_historical_trades(self, symbol: Symbol, limit: int = 500,
                                    timestamp_from: Optional[int] = None,
                                    timestamp_to: Optional[int] = None) -> List[Trade]:
        """
        Get historical trades for futures with optional timestamp filtering.
        Gate.io expects seconds for 'from'/'to'.
        """
        try:
            contract = self._mapper.to_pair(symbol)
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
                raise BaseExchangeError(500, "Invalid futures historical trades format")

            trades: List[Trade] = []
            for td in response_data:
                try:
                    size = float(td.get('size', td.get('amount', 0)))
                    side = Side.BUY if size > 0 else Side.SELL if size < 0 else self._mapper.get_unified_side(td.get('side', 'buy'))
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
            raise BaseExchangeError(500, f"Futures historical trades fetch failed: {str(e)}")

    async def get_ticker_info(self, symbol: Optional[Symbol] = None) -> Dict[Symbol, Ticker]:
        """
        Get futures tickers. Endpoint: /futures/usdt/tickers
        Can request single symbol via 'contract' param or get all tickers.
        Returns mapping Symbol -> Ticker (similar to spot signature).
        """
        try:
            params = {}
            if symbol:
                params['contract'] = self._mapper.to_pair(symbol)

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
                if not self._mapper.is_supported_pair(pair_str):
                    continue
                try:
                    symbol_obj = self._mapper.to_symbol(pair_str)
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
            raise BaseExchangeError(500, f"Futures ticker info fetch failed: {str(e)}")

    async def get_funding_rate(self, symbol: Symbol) -> Dict[str, Any]:
        """
        Get funding rate for a contract. Endpoint: /futures/usdt/funding_rate
        Returns raw dict (public-only).
        """
        try:
            contract = self._mapper.to_pair(symbol)
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
            raise BaseExchangeError(500, f"Futures funding rate fetch failed: {str(e)}")

    async def get_klines(self, symbol: Symbol, timeframe: KlineInterval,
                         date_from: Optional[datetime], date_to: Optional[datetime]) -> List[Kline]:
        """
        Get futures candlesticks. Endpoint: /futures/usdt/candlesticks
        Accepts either array-format klines or dict-format.
        """
        try:
            contract = self._mapper.to_pair(symbol)
            interval = self._mapper.get_exchange_interval(timeframe)

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
                raise BaseExchangeError(500, "Invalid futures candlesticks response format")

            klines: List[Kline] = []
            for k in response_data:
                try:
                    # array format: [time, volume, close, high, low, open] or [time, volume, close, high, low, open, prev_close]
                    if isinstance(k, (list, tuple)) and len(k) >= 6:
                        ts = int(float(k[0])) * 1000
                        volume = float(k[1])
                        close_price = float(k[2])
                        high_price = float(k[3])
                        low_price = float(k[4])
                        open_price = float(k[5])
                    elif isinstance(k, dict):
                        ts = int(k.get('t', k.get('time', 0))) * 1000
                        open_price = float(k.get('o', k.get('open', 0)))
                        high_price = float(k.get('h', k.get('high', 0)))
                        low_price = float(k.get('l', k.get('low', 0)))
                        close_price = float(k.get('c', k.get('close', 0)))
                        volume = float(k.get('v', k.get('volume', 0)))
                    else:
                        continue

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
                        quote_volume=volume * ((open_price + close_price) / 2) if volume and (open_price or close_price) else 0.0,
                        trades_count=0
                    )
                    klines.append(kline)

                except Exception:
                    self.logger.debug(f"Failed to parse futures kline: {k}")
                    continue

            # Gate.io typically returns oldest first
            self.logger.debug(f"Retrieved {len(klines)} futures klines for {contract}")
            return klines

        except Exception as e:
            self.logger.error(f"Failed to get futures klines for {symbol}: {e}")
            raise BaseExchangeError(500, f"Futures klines fetch failed: {str(e)}")

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
        batch_size = self._calculate_optimal_batch_size(timeframe, total_duration_seconds)
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
                self._mapper.to_pair(s)
            except Exception as e:
                self.logger.debug(f"Failed to pre-cache symbol {s}: {e}")
        self.logger.info("Gate.io Futures initialization complete")

    async def start_symbol(self, symbol: Symbol) -> None:
        contract = self._mapper.to_pair(symbol)
        self.logger.debug(f"Start symbol requested for {contract} (public-only no-op)")

    async def stop_symbol(self, symbol: Symbol) -> None:
        contract = self._mapper.to_pair(symbol)
        self.logger.debug(f"Stop symbol requested for {contract} (public-only no-op)")

    async def close(self):
        self.logger.info("Closed Gate.io futures public client")

    def __repr__(self) -> str:
        return f"GateioPublicFuturesRest(base_url={self.base_url})"
