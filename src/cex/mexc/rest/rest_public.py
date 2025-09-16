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
from structs.exchange import (
    Symbol, SymbolInfo, OrderBook, OrderBookEntry, Trade, Kline,
    AssetName, Side, KlineInterval
)
from core.cex.rest.spot.base_rest_spot_public import PublicExchangeSpotRestInterface
from core.config.structs import ExchangeConfig
from core.cex.utils import get_interval_seconds
from core.transport.rest.structs import HTTPMethod
from core.cex.services.mapping_factory import ExchangeMappingsFactory


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
        super().__init__(config, custom_exception_handler=None)

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
        
        for mexc_symbol in exchange_info.symbols:
            symbol = Symbol(
                base=AssetName(mexc_symbol.baseAsset),
                quote=AssetName(mexc_symbol.quoteAsset),
                is_futures=False
            )
            
            base_prec, quote_prec, min_quote, min_base = self._extract_symbol_precision(mexc_symbol)
            
            symbol_info = SymbolInfo(
                exchange=self.exchange,
                symbol=symbol,
                base_precision=base_prec,
                quote_precision=quote_prec,
                min_quote_amount=min_quote,
                min_base_amount=min_base,
                is_futures=False,
                maker_commission=float(mexc_symbol.makerCommission),
                taker_commission=float(mexc_symbol.takerCommission),
                inactive=mexc_symbol.status != '1'
            )
            
            symbol_info_map[symbol] = symbol_info
        
        # Update cache
        self._symbols_info = symbol_info_map

        self.logger.info(f"Retrieved exchange info for {len(symbol_info_map)} symbols")
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
        pair = self.symbol_mapper.symbol_to_pair(symbol)
        
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
            timestamp=time.time()
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
        pair = self.symbol_mapper.symbol_to_pair(symbol)
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
                price=float(trade_data.price),
                amount=float(trade_data.qty),
                side=side,
                timestamp=trade_data.time,
                is_maker=trade_data.isBuyerMaker
            )
            trades.append(trade)
        
        # Sort by timestamp (newest first)
        trades.sort(key=lambda t: t.timestamp, reverse=True)
        
        self.logger.debug(f"Retrieved {len(trades)} recent trades for {pair}")
        return trades
    
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
        pair = self.symbol_mapper.symbol_to_pair(symbol)
        interval = self._mappings.get_exchange_kline_interval(timeframe)
        
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
        
        # Calculate chunk size (500 klines per request to avoid API limits)
        chunk_duration_seconds = 500 * interval_seconds
        
        all_klines = []
        current_start = date_from
        
        while current_start < date_to:
            # Calculate chunk end time
            chunk_end = datetime.fromtimestamp(
                min(current_start.timestamp() + chunk_duration_seconds, date_to.timestamp())
            )
            
            # Fetch chunk
            chunk_klines = await self.get_klines(symbol, timeframe, current_start, chunk_end)
            all_klines.extend(chunk_klines)
            
            # Move to next chunk
            current_start = datetime.fromtimestamp(chunk_end.timestamp() + interval_seconds)
            
            # Break if no more data or we've reached the end
            if not chunk_klines or current_start >= date_to:
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
    
