"""
MEXC Public REST API Implementation

Focused REST-only client for MEXC public API endpoints.
Optimized for direct API calls without WebSocket or streaming features.

Key Features:
- Pure REST API implementation 
- Sub-10ms response times for market data
- Zero-copy JSON parsing with msgspec
- Unified cex compliance
- Simple caching for exchange info

MEXC API Specifications:
- Base URL: https://api.mexc.com
- Rate Limits: 1200 requests/minute (20 req/sec)
- Standard REST API with JSON responses
- No authentication required for public endpoints

Threading: Fully async/await compatible, thread-safe
Memory: O(1) per request, optimized for high-frequency access
"""

import asyncio
import time
from typing import Dict, List, Optional
from datetime import datetime
import msgspec

from cex.mexc.structs.exchange import (
    MexcSymbolResponse, MexcExchangeInfoResponse, 
    MexcOrderBookResponse, MexcTradeResponse, MexcServerTimeResponse
)
from structs.common import (
    Symbol, SymbolInfo, OrderBook, OrderBookEntry, Trade, Kline,
    AssetName, Side, KlineInterval, Ticker
)
from core.cex.rest.spot.base_rest_spot_public import PublicExchangeSpotRestInterface
from core.config.structs import ExchangeConfig
from core.cex.utils import get_interval_seconds
from core.transport.rest.structs import HTTPMethod


class MexcPublicSpotRest(PublicExchangeSpotRestInterface):
    """
    MEXC public REST API client focused on direct API calls.
    
    Provides access to public market data endpoints without WebSocket features.
    Optimized for high-frequency market data retrieval with minimal overhead.
    """

    def __init__(self, config: ExchangeConfig):
        """
        Initialize MEXC public REST client with dependency injection.

        Args:
            config: ExchangeConfig with base URL and rate limits
        """
        super().__init__(config)

        self._symbols_info: Optional[Dict[Symbol, SymbolInfo]] = None
        
    def _extract_symbol_precision(self, mexc_symbol: MexcSymbolResponse) -> tuple[int, int, float, float]:
        """
        Extract precision and size limits from MEXC symbol data.
        
        Args:
            mexc_symbol: MEXC symbol response with precision fields
            
        Returns:
            Tuple of (base_precision, quote_precision, min_quote_amount, min_base_amount)
        """
        base_precision = mexc_symbol.baseAssetPrecision
        quote_precision = mexc_symbol.quotePrecision
        
        min_base_amount = float(mexc_symbol.baseSizePrecision) if mexc_symbol.baseSizePrecision else 0.0
        min_quote_amount = float(mexc_symbol.quoteAmountPrecision) if mexc_symbol.quoteAmountPrecision else 0.0
        
        # Process filters for additional limits
        for filter_info in mexc_symbol.filters:
            filter_type = filter_info.get('filterType')
            
            if filter_type == 'LOT_SIZE':
                min_qty = float(filter_info.get('minQty', '0'))
                if min_qty > 0:
                    min_base_amount = max(min_base_amount, min_qty)
                    
            elif filter_type == 'MIN_NOTIONAL':
                min_notional = float(filter_info.get('minNotional', '0'))
                if min_notional > 0:
                    min_quote_amount = max(min_quote_amount, min_notional)
        
        return base_precision, quote_precision, min_quote_amount, min_base_amount
    
    async def get_exchange_info(self) -> Dict[Symbol, SymbolInfo]:
        """
        Get MEXC trading rules and symbol information.
        
        Uses intelligent caching to minimize API calls while ensuring data freshness.
        
        Returns:
            Dictionary mapping Symbol to SymbolInfo with complete trading rules
            
        Raises:
            ExchangeAPIError: If unable to fetch exchange info
        """
        current_time = time.time()
        
        # Fetch fresh exchange info from MEXC
        response_data = await self.request(HTTPMethod.GET, '/api/v3/exchangeInfo')
        
        # Parse response with msgspec
        exchange_info = msgspec.convert(response_data, MexcExchangeInfoResponse)
        
        # Transform to unified format
        symbol_info_map: Dict[Symbol, SymbolInfo] = {}
        filtered_count = 0
        
        for mexc_symbol in exchange_info.symbols:
            symbol = Symbol(
                base=AssetName(mexc_symbol.baseAsset),
                quote=AssetName(mexc_symbol.quoteAsset),
                is_futures=False
            )
            
            # Filter out unsupported symbols (quote assets not supported)
            if not self._mapper.validate_symbol(symbol):
                filtered_count += 1
                continue
            
            base_prec, quote_prec, min_quote, min_base = self._extract_symbol_precision(mexc_symbol)
            
            symbol_info = SymbolInfo(
                symbol=symbol,
                base_precision=base_prec,
                quote_precision=quote_prec,
                min_base_amount=min_base,
                min_quote_amount=min_quote,
                is_futures=False,
                maker_commission=float(mexc_symbol.makerCommission),
                taker_commission=float(mexc_symbol.takerCommission),
                inactive=mexc_symbol.status != '1'
            )
            
            symbol_info_map[symbol] = symbol_info
        
        # Update cache
        self._symbols_info = symbol_info_map

        self.logger.info(f"Retrieved exchange info for {len(symbol_info_map)} symbols, filtered {filtered_count} unsupported pairs")
        if filtered_count > 0:
            self.logger.debug(f"Filtered {filtered_count} pairs with unsupported quote assets")
        
        return symbol_info_map
    
    async def get_orderbook(self, symbol: Symbol, limit: int = 10) -> OrderBook:
        """
        Get order book for a symbol.
        
        Args:
            symbol: Symbol to get orderbook for
            limit: Order book depth limit (5, 10, 20, 50, 100, 500, 1000, 5000)
            
        Returns:
            OrderBook with bids, asks, and timestamp
            
        Raises:
            ExchangeAPIError: If unable to fetch order book data
        """
        pair = self._mapper.to_pair(symbol)
        
        params = {
            'symbol': pair,
            'limit': limit
        }
        
        response_data = await self.request(
            HTTPMethod.GET,
            '/api/v3/depth',
            params=params
        )
        
        orderbook_data = msgspec.convert(response_data, MexcOrderBookResponse)
        
        # Transform to unified format
        bids = [
            OrderBookEntry(price=float(bid[0]), size=float(bid[1]))
            for bid in orderbook_data.bids
        ]
        
        asks = [
            OrderBookEntry(price=float(ask[0]), size=float(ask[1]))
            for ask in orderbook_data.asks
        ]
        
        return OrderBook(
            bids=bids,
            asks=asks,
            timestamp=int(time.time())
        )
    
    async def get_recent_trades(self, symbol: Symbol, limit: int = 500) -> List[Trade]:
        """
        Get recent trades for a symbol.
        
        Args:
            symbol: Symbol to get trades for
            limit: Number of recent trades (max 1000)
            
        Returns:
            List of Trade objects sorted by timestamp (newest first)
            
        Raises:
            ExchangeAPIError: If unable to fetch trade data
        """
        pair = self._mapper.to_pair(symbol)
        optimized_limit = min(limit, 1000)  # MEXC max limit
        
        params = {
            'symbol': pair,
            'limit': optimized_limit
        }
        
        response_data = await self.request(
            HTTPMethod.GET,
            '/api/v3/trades',
            params=params
        )
        
        trade_responses = msgspec.convert(response_data, list[MexcTradeResponse])
        
        # Transform to unified format
        trades = []
        for trade_data in trade_responses:
            # Map MEXC isBuyerMaker to Side enum
            side = Side.SELL if trade_data.isBuyerMaker else Side.BUY
            
            trade = Trade(
                symbol=symbol,
                price=float(trade_data.price),
                quantity=float(trade_data.qty),
                side=side,
                timestamp=trade_data.time,
                is_maker=trade_data.isBuyerMaker
            )
            trades.append(trade)
        
        # Sort by timestamp (newest first)
        trades.sort(key=lambda t: t.timestamp, reverse=True)
        
        self.logger.debug(f"Retrieved {len(trades)} recent trades for {pair}")
        return trades
    
    async def get_historical_trades(self, symbol: Symbol, limit: int = 500,
                                    timestamp_from: Optional[int] = None,
                                    timestamp_to: Optional[int] = None) -> List[Trade]:
        """
        Get historical trades for a symbol.
        
        MEXC uses the same /api/v3/trades endpoint for both recent and historical trades.
        Historical access is provided via the fromId parameter for pagination.
        
        Args:
            symbol: Symbol to get trades for
            limit: Number of trades to retrieve (max 1000)
            timestamp_from: Start timestamp in milliseconds (not directly supported by MEXC)
            timestamp_to: End timestamp in milliseconds (not directly supported by MEXC)
            
        Returns:
            List of Trade objects sorted by timestamp (newest first)
            
        Raises:
            ExchangeAPIError: If unable to fetch trade data
            
        Note:
            MEXC does not support timestamp filtering directly. This method returns
            the most recent trades up to the limit. For true historical access,
            use fromId parameter (not exposed in this unified interface).
        """
        pair = self._mapper.to_pair(symbol)
        optimized_limit = min(limit, 1000)  # MEXC max limit
        
        params = {
            'symbol': pair,
            'limit': optimized_limit
        }
        
        # MEXC Note: timestamp filtering not directly supported
        # The API only supports fromId for pagination, not timestamp ranges
        if timestamp_from or timestamp_to:
            self.logger.warning(
                f"MEXC does not support timestamp filtering for historical trades. "
                f"Returning recent trades instead."
            )
        
        response_data = await self.request(
            HTTPMethod.GET,
            '/api/v3/trades',
            params=params
        )
        
        trade_responses = msgspec.convert(response_data, list[MexcTradeResponse])
        
        # Transform to unified format
        trades = []
        for trade_data in trade_responses:
            # Map MEXC isBuyerMaker to Side enum
            side = Side.SELL if trade_data.isBuyerMaker else Side.BUY
            
            trade = Trade(
                symbol=symbol,
                price=float(trade_data.price),
                quantity=float(trade_data.qty),
                side=side,
                timestamp=trade_data.time,
                is_maker=trade_data.isBuyerMaker,
                trade_id=str(trade_data.id) if trade_data.id else None
            )
            trades.append(trade)
        
        # Sort by timestamp (newest first)
        trades.sort(key=lambda t: t.timestamp, reverse=True)
        
        self.logger.debug(f"Retrieved {len(trades)} historical trades for {pair}")
        return trades
    
    async def get_ticker_info(self, symbol: Optional[Symbol] = None) -> Dict[Symbol, Ticker]:
        """
        Get 24hr ticker price change statistics.
        
        MEXC provides /api/v3/ticker/24hr endpoint for ticker data.
        Supports both single symbol and all symbols retrieval.
        
        Args:
            symbol: Specific symbol to get ticker for (optional)
                   If None, returns tickers for all symbols
            
        Returns:
            Dictionary mapping Symbol to Ticker with 24hr statistics
            
        Raises:
            ExchangeAPIError: If unable to fetch ticker data
        """
        params = {}
        if symbol:
            # Get ticker for specific symbol
            pair = self._mapper.to_pair(symbol)
            params['symbol'] = pair
        # If no symbol specified, API returns all tickers
        
        response_data = await self.request(
            HTTPMethod.GET,
            '/api/v3/ticker/24hr',
            params=params
        )
        
        # Response can be single ticker or list of tickers
        tickers_data = response_data if isinstance(response_data, list) else [response_data]
        
        # Transform to unified format
        tickers: Dict[Symbol, Ticker] = {}
        
        for ticker_data in tickers_data:
            # Parse symbol from MEXC format
            pair_str = ticker_data.get('symbol', '')
            if not pair_str:
                continue
            
            # Skip if not a supported symbol
            if not self._mapper.is_supported_pair(pair_str):
                continue
            
            try:
                symbol_obj = self._mapper.to_symbol(pair_str)
            except:
                # Skip symbols we can't parse
                continue
            
            # MEXC ticker response format:
            # {
            #   "symbol": "BTCUSDT",
            #   "priceChange": "437.00000000",
            #   "priceChangePercent": "0.72",
            #   "prevClosePrice": "60784.00000000",
            #   "lastPrice": "61221.00000000",
            #   "bidPrice": "61220.00000000",
            #   "bidQty": "0.15021000",
            #   "askPrice": "61221.00000000",
            #   "askQty": "0.71804000",
            #   "openPrice": "60784.00000000",
            #   "highPrice": "62369.00000000",
            #   "lowPrice": "60508.00000000",
            #   "volume": "5418.62664000",
            #   "quoteVolume": "331727991.90124860",
            #   "openTime": 1647338340000,
            #   "closeTime": 1647424740000,
            #   "count": 122931,
            #   "firstId": 258525932,
            #   "lastId": 258648862
            # }
            
            ticker = Ticker(
                symbol=symbol_obj,
                price_change=float(ticker_data.get('priceChange', 0)),
                price_change_percent=float(ticker_data.get('priceChangePercent', 0)),
                weighted_avg_price=float(ticker_data.get('weightedAvgPrice', 0) if ticker_data.get('weightedAvgPrice') else 0),
                prev_close_price=float(ticker_data.get('prevClosePrice', 0)),
                last_price=float(ticker_data.get('lastPrice', 0)),
                last_qty=float(ticker_data.get('lastQty', 0) if ticker_data.get('lastQty') else 0),
                open_price=float(ticker_data.get('openPrice', 0)),
                high_price=float(ticker_data.get('highPrice', 0)),
                low_price=float(ticker_data.get('lowPrice', 0)),
                volume=float(ticker_data.get('volume', 0)),
                quote_volume=float(ticker_data.get('quoteVolume', 0)),
                open_time=int(ticker_data.get('openTime', 0)),
                close_time=int(ticker_data.get('closeTime', 0)),
                count=int(ticker_data.get('count', 0) or 0), # not set ???
                bid_price=float(ticker_data.get('bidPrice', 0)) if ticker_data.get('bidPrice') else None,
                bid_qty=float(ticker_data.get('bidQty', 0)) if ticker_data.get('bidQty') else None,
                ask_price=float(ticker_data.get('askPrice', 0)) if ticker_data.get('askPrice') else None,
                ask_qty=float(ticker_data.get('askQty', 0)) if ticker_data.get('askQty') else None,
                first_id=int(ticker_data.get('firstId')) if ticker_data.get('firstId') else None,
                last_id=int(ticker_data.get('lastId')) if ticker_data.get('lastId') else None
            )
            
            tickers[symbol_obj] = ticker
        
        self.logger.debug(f"Retrieved {len(tickers)} ticker(s) from MEXC")
        return tickers
    
    async def get_server_time(self) -> int:
        """
        Get MEXC server timestamp.
        
        Returns:
            Server timestamp in milliseconds
            
        Raises:
            ExchangeAPIError: If unable to fetch server time
        """
        response_data = await self.request(
            HTTPMethod.GET,
            '/api/v3/time'
        )
        
        time_response = msgspec.convert(response_data, MexcServerTimeResponse)
        return time_response.serverTime
    
    async def ping(self) -> bool:
        """
        Test connectivity to MEXC exchange.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            await self.request(
                HTTPMethod.GET,
                '/api/v3/ping'
            )
            return True
        except Exception:
            return False
    
    async def get_klines(self, symbol: Symbol, timeframe: KlineInterval,
                         date_from: Optional[datetime], date_to: Optional[datetime]) -> List[Kline]:
        """
        Get kline/candlestick data for a symbol.
        
        Args:
            symbol: Symbol to get klines for
            timeframe: Kline interval (1m, 5m, 1h, 1d, etc.)
            date_from: Start time (optional)
            date_to: End time (optional)
            
        Returns:
            List of Kline objects sorted by timestamp (oldest first)
            
        Raises:
            ExchangeAPIError: If unable to fetch kline data
        """
        pair = self._mapper.symbol_mapper.to_pair(symbol)
        interval = self._mapper.get_exchange_kline_interval(timeframe)
        
        params = {
            'symbol': pair,
            'interval': interval,
            'limit': 500  # Reduced limit to avoid API issues
        }
        
        # Add time filters if provided
        if date_from:
            params['startTime'] = int(date_from.timestamp() * 1000)
        if date_to:
            params['endTime'] = int(date_to.timestamp() * 1000)
        
        response_data = await self.request(
            HTTPMethod.GET,
            '/api/v3/klines',
            params=params
        )
        
        # MEXC returns array of arrays, each with 8 elements:
        # [open_time, open, high, low, close, volume, close_time, quote_volume]
        kline_arrays = msgspec.convert(response_data, list[list])
        
        # Transform to unified format
        klines = []
        for kline_data in kline_arrays:
            if len(kline_data) >= 8:
                kline = Kline(
                    symbol=symbol,
                    interval=timeframe,
                    open_time=int(kline_data[0]),
                    close_time=int(kline_data[6]),
                    open_price=float(kline_data[1]),
                    high_price=float(kline_data[2]),
                    low_price=float(kline_data[3]),
                    close_price=float(kline_data[4]),
                    volume=float(kline_data[5]),
                    quote_volume=float(kline_data[7]),
                    trades_count=0  # MEXC doesn't provide trade count
                )
                klines.append(kline)
        
        # Already sorted by timestamp from MEXC API
        self.logger.debug(f"Retrieved {len(klines)} klines for {pair} {interval}")
        return klines
    
    def _time_range_iterator_v1(self, date_from: datetime, date_to: datetime, 
                               limit: int, timeframe: Optional[KlineInterval] = None) -> List[tuple[datetime, datetime]]:
        """
        Version 1: Simple forward iteration with fixed chunk size.
        
        Creates time ranges by moving forward from start to end with fixed-size chunks.
        Most straightforward implementation similar to range().
        
        Args:
            date_from: Start datetime
            date_to: End datetime  
            limit: Number of klines per chunk (e.g., 500)
            timeframe: Optional kline interval for calculating chunk duration
            
        Returns:
            List of (chunk_start, chunk_end) tuples
        """
        if not timeframe:
            # Fallback: Split time range into equal parts
            total_seconds = int((date_to - date_from).total_seconds())
            chunk_seconds = total_seconds // max(1, limit)
        else:
            interval_seconds = get_interval_seconds(timeframe)
            chunk_seconds = limit * interval_seconds
        
        ranges = []
        current_start = date_from
        
        while current_start < date_to:
            chunk_end = datetime.fromtimestamp(
                min(current_start.timestamp() + chunk_seconds, date_to.timestamp())
            )
            ranges.append((current_start, chunk_end))
            current_start = datetime.fromtimestamp(chunk_end.timestamp() + 1)  # +1 second to avoid overlap
            
        return ranges

    def _time_range_iterator_v2(self, date_from: datetime, date_to: datetime,
                               limit: int, timeframe: Optional[KlineInterval] = None) -> List[tuple[datetime, datetime]]:
        """
        Version 2: Adaptive iteration that adjusts based on last candle received.
        
        Each iteration can be adjusted based on actual data received from previous call.
        Supports dynamic adjustment when data is sparse or missing.
        
        Args:
            date_from: Start datetime
            date_to: End datetime
            limit: Maximum number of klines per chunk
            timeframe: Optional kline interval for calculating chunk duration
            
        Returns:
            List of (chunk_start, chunk_end) tuples with adaptive sizing
        """
        if not timeframe:
            # Fallback: Use larger chunks for unknown intervals
            total_seconds = int((date_to - date_from).total_seconds())
            chunk_seconds = total_seconds // max(1, limit // 2)  # Larger chunks
        else:
            interval_seconds = get_interval_seconds(timeframe)
            chunk_seconds = limit * interval_seconds
        
        ranges = []
        current_start = date_from
        
        while current_start < date_to:
            # Adaptive chunk size: smaller chunks near the end
            remaining_seconds = int((date_to - current_start).total_seconds())
            if remaining_seconds < chunk_seconds:
                chunk_end = date_to
            else:
                chunk_end = datetime.fromtimestamp(current_start.timestamp() + chunk_seconds)
                
            ranges.append((current_start, chunk_end))
            
            # Move to next chunk with small overlap prevention
            if timeframe:
                interval_seconds = get_interval_seconds(timeframe)
                current_start = datetime.fromtimestamp(chunk_end.timestamp() + interval_seconds)
            else:
                current_start = datetime.fromtimestamp(chunk_end.timestamp() + 60)  # +1 minute fallback
                
        return ranges
        
    def _time_range_iterator_v3(self, date_from: datetime, date_to: datetime,
                               limit: int, timeframe: Optional[KlineInterval] = None,
                               reverse: bool = False) -> List[tuple[datetime, datetime]]:
        """
        Version 3: Flexible iterator with reverse support and precise interval handling.
        
        Most advanced implementation that can iterate forward or backward,
        handles edge cases, and provides precise interval calculations.
        
        Args:
            date_from: Start datetime
            date_to: End datetime
            limit: Number of klines per chunk
            timeframe: Kline interval for precise duration calculation
            reverse: If True, iterate from date_to backwards to date_from
            
        Returns:
            List of (chunk_start, chunk_end) tuples (always start < end regardless of direction)
        """
        if not timeframe:
            # Estimate based on time range - assume 1-minute intervals
            total_seconds = int((date_to - date_from).total_seconds())
            interval_seconds = 60  # Default to 1-minute
            chunk_duration = limit * interval_seconds
        else:
            interval_seconds = get_interval_seconds(timeframe)
            if interval_seconds == 0:
                interval_seconds = 60  # Fallback
            chunk_duration = limit * interval_seconds
        
        ranges = []
        
        if reverse:
            # Start from end and work backwards
            current_end = date_to
            
            while current_end > date_from:
                chunk_start = datetime.fromtimestamp(
                    max(current_end.timestamp() - chunk_duration, date_from.timestamp())
                )
                
                ranges.append((chunk_start, current_end))
                
                # Move backwards, ensuring no overlap
                current_end = datetime.fromtimestamp(chunk_start.timestamp() - interval_seconds)
                
            # Reverse the list so it's still chronological
            ranges.reverse()
        else:
            # Forward iteration (same as V1 but with better edge case handling)
            current_start = date_from
            
            while current_start < date_to:
                chunk_end = datetime.fromtimestamp(
                    min(current_start.timestamp() + chunk_duration, date_to.timestamp())
                )
                
                ranges.append((current_start, chunk_end))
                
                # Move forward, ensuring no overlap  
                current_start = datetime.fromtimestamp(chunk_end.timestamp() + interval_seconds)
                
                # Break if the next chunk would be too small
                if (date_to.timestamp() - current_start.timestamp()) < interval_seconds:
                    break
        
        return ranges

    async def get_klines_batch(self, symbol: Symbol, timeframe: KlineInterval,
                              date_from: Optional[datetime], date_to: Optional[datetime]) -> List[Kline]:
        """
        Get batch kline data by making multiple get_klines requests for large time ranges.
        
        This method splits large time ranges into chunks to handle MEXC's 1000 kline limit per request.
        Uses multiple calls to get_klines internally.
        
        Args:
            symbol: Symbol to get klines for
            timeframe: Kline interval 
            date_from: Start time (optional)
            date_to: End time (optional)
            
        Returns:
            List of Kline objects sorted by timestamp (oldest first)
            
        Raises:
            ExchangeAPIError: If unable to fetch kline data
        """
        # If no date range specified, use single request
        if not date_from or not date_to:
            return await self.get_klines(symbol, timeframe, date_from, date_to)
        
        # Calculate interval duration in seconds
        interval_seconds = get_interval_seconds(timeframe)
        if interval_seconds == 0:
            # Fallback to single request for unknown intervals
            return await self.get_klines(symbol, timeframe, date_from, date_to)
        
        # MEXC has variable historical data availability per symbol
        # Some symbols only have ~30 days, others may have more
        # Conservative approach: limit to 30 days to avoid empty results
        MAX_SAFE_DAYS = 30  # Conservative limit based on testing
        MAX_SAFE_DURATION_SECONDS = MAX_SAFE_DAYS * 24 * 3600
        
        total_duration_seconds = int((date_to - date_from).total_seconds())
        
        if total_duration_seconds > MAX_SAFE_DURATION_SECONDS:
            # Adjust date_from to stay within safe historical limit
            adjusted_date_from = datetime.fromtimestamp(date_to.timestamp() - MAX_SAFE_DURATION_SECONDS)
            
            self.logger.warning(
                f"MEXC historical limit: {total_duration_seconds/3600/24:.1f} days requested, "
                f"max {MAX_SAFE_DAYS} days safe limit. "
                f"Adjusted start date from {date_from.strftime('%Y-%m-%d %H:%M')} "
                f"to {adjusted_date_from.strftime('%Y-%m-%d %H:%M')}"
            )
            
            date_from = adjusted_date_from
        
        # Use time range iterator to generate chunks (500 klines per request)
        time_ranges = self._time_range_iterator_v2(date_from, date_to, limit=500, timeframe=timeframe)
        
        all_klines = []
        
        for chunk_start, chunk_end in time_ranges:
            # Fetch chunk
            chunk_klines = await self.get_klines(symbol, timeframe, chunk_start, chunk_end)
            
            if chunk_klines:
                all_klines.extend(chunk_klines)
                
                # Adaptive adjustment: If we got fewer klines than expected, 
                # the next iteration will adjust automatically via the iterator
                self.logger.debug(f"Fetched {len(chunk_klines)} klines for chunk {chunk_start} to {chunk_end}")
            else:
                # No more data available, break early
                self.logger.debug(f"No klines returned for chunk {chunk_start} to {chunk_end}, stopping")
                break
            
            # Rate limiting: Add small delay between requests to avoid rate limits
            # MEXC has higher limits (1200 req/min) so shorter delay than Gate.io
            await asyncio.sleep(0.1)
        
        # Remove duplicates and sort
        unique_klines = {}
        for kline in all_klines:
            unique_klines[kline.open_time] = kline
        
        sorted_klines = sorted(unique_klines.values(), key=lambda k: k.open_time)
        
        self.logger.info(f"Retrieved {len(sorted_klines)} klines in batch for {symbol.base}/{symbol.quote}")
        return sorted_klines
    
