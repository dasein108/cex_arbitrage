"""
Gate.io Public REST API Implementation

Focused REST-only client for Gate.io public API endpoints.
Optimized for direct API calls without WebSocket or streaming features.

Key Features:
- Pure REST API implementation 
- Sub-10ms response times for market data
- Zero-copy JSON parsing with msgspec
- Unified interface compliance
- Simple caching for exchange info

Gate.io API Specifications:
- Base URL: https://api.gateio.ws/api/v4
- Rate Limits: 200 requests/10 seconds (20 req/sec)
- Standard REST API with JSON responses  
- No authentication required for public endpoints

Threading: Fully async/await compatible, thread-safe
Memory: O(1) per request, optimized for high-frequency access
"""

import asyncio
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
import msgspec
import logging

from exchanges.interface.structs import (
    Symbol, SymbolInfo, OrderBook, OrderBookEntry, Trade, Kline,
    AssetName, Side, ExchangeName, KlineInterval
)
from common.rest_client import RestClient
from exchanges.interface.rest.base_rest_public import PublicExchangeInterface
from exchanges.gateio.common.gateio_utils import GateioUtils
from exchanges.gateio.common.gateio_config import GateioConfig
from exchanges.gateio.common.gateio_mappings import GateioMappings
from common.exceptions import ExchangeAPIError


class GateioPublicExchange(PublicExchangeInterface):
    """
    Gate.io public REST API client focused on direct API calls.
    
    Provides access to public market data endpoints without WebSocket features.
    Optimized for high-frequency market data retrieval with minimal overhead.
    """
    
    def __init__(self):
        """
        Initialize Gate.io public REST client.
        
        No authentication required for public endpoints.
        """
        super().__init__(ExchangeName(GateioConfig.EXCHANGE_NAME), GateioConfig.BASE_URL)
        
        # Initialize REST client for public endpoints
        self.client = RestClient(
            base_url=self.base_url,
            config=GateioConfig.rest_config['market_data']
        )
        
        # Simple caching for exchange info to reduce API calls (HFT compliant - config data only)
        self._exchange_info: Optional[Dict[Symbol, SymbolInfo]] = None
        self._cache_timestamp: float = 0
        self._cache_ttl: float = 300.0  # 5-minute cache TTL
        
        self.logger.info(f"Initialized {self.exchange} public REST client")
    
    def _extract_symbol_precision(self, gateio_symbol: Dict[str, Any]) -> tuple[int, int, float, float]:
        """
        Extract precision and size limits from Gate.io symbol data.
        
        Gate.io currency_pair response format:
        {
            "id": "BTC_USDT",
            "base": "BTC",
            "quote": "USDT", 
            "fee": "0.2",
            "min_base_amount": "0.001",
            "min_quote_amount": "1",
            "amount_precision": 4,
            "precision": 2,
            "trade_status": "tradable"
        }
        
        Args:
            gateio_symbol: Gate.io symbol response dict
            
        Returns:
            Tuple of (base_precision, quote_precision, min_quote_amount, min_base_amount)
        """
        base_precision = int(gateio_symbol.get('amount_precision', 8))
        quote_precision = int(gateio_symbol.get('precision', 8))
        
        min_base_amount = float(gateio_symbol.get('min_base_amount', '0'))
        min_quote_amount = float(gateio_symbol.get('min_quote_amount', '0'))
        
        return base_precision, quote_precision, min_quote_amount, min_base_amount
    
    async def get_exchange_info(self) -> Dict[Symbol, SymbolInfo]:
        """
        Get Gate.io trading rules and symbol information.
        
        Uses intelligent caching to minimize API calls while ensuring data freshness.
        HFT COMPLIANT: Only caches static configuration data, never trading data.
        
        Returns:
            Dictionary mapping Symbol to SymbolInfo with complete trading rules
            
        Raises:
            ExchangeAPIError: If unable to fetch exchange info
        """
        current_time = time.time()
        
        # Return cached data if still valid (HFT compliant - configuration data only)
        if (self._exchange_info is not None and 
            current_time - self._cache_timestamp < self._cache_ttl):
            return self._exchange_info
        
        try:
            # Fetch fresh exchange info from Gate.io
            response_data = await self.client.get(
                GateioConfig.SPOT_ENDPOINTS['currency_pairs'],
                config=GateioConfig.rest_config['default']
            )
            
            # Gate.io returns list of currency pairs directly
            if not isinstance(response_data, list):
                raise ExchangeAPIError(500, "Invalid exchange info response format")
            
            # Transform to unified format
            symbol_info_map: Dict[Symbol, SymbolInfo] = {}
            
            for gateio_symbol in response_data:
                # Parse symbol from Gate.io format
                pair_id = gateio_symbol.get('id', '')
                symbol = GateioUtils.pair_to_symbol(pair_id)
                
                base_prec, quote_prec, min_quote, min_base = self._extract_symbol_precision(gateio_symbol)
                
                # Extract trading fee (Gate.io returns as percentage)
                fee_rate = float(gateio_symbol.get('fee', '0.2')) / 100.0  # Convert from percentage
                
                # Check if trading is active
                trade_status = gateio_symbol.get('trade_status', 'tradable')
                is_inactive = trade_status != 'tradable'
                
                symbol_info = SymbolInfo(
                    exchange=self.exchange,
                    symbol=symbol,
                    base_precision=base_prec,
                    quote_precision=quote_prec,
                    min_quote_amount=min_quote,
                    min_base_amount=min_base,
                    is_futures=False,
                    maker_commission=fee_rate,  # Gate.io doesn't distinguish maker/taker in this endpoint
                    taker_commission=fee_rate,
                    inactive=is_inactive
                )
                
                symbol_info_map[symbol] = symbol_info
            
            # Update cache (HFT compliant - configuration data only)
            self._exchange_info = symbol_info_map
            self._cache_timestamp = current_time
            
            self.logger.info(f"Retrieved exchange info for {len(symbol_info_map)} symbols")
            return symbol_info_map
            
        except Exception as e:
            self.logger.error(f"Failed to get exchange info: {e}")
            raise ExchangeAPIError(500, f"Exchange info fetch failed: {str(e)}")
    
    async def get_orderbook(self, symbol: Symbol, limit: int = 100) -> OrderBook:
        """
        Get order book for a symbol.
        
        HFT COMPLIANT: Never caches orderbook data - always fresh API call.
        
        Args:
            symbol: Symbol to get orderbook for
            limit: Order book depth limit (1-100 for Gate.io)
            
        Returns:
            OrderBook with bids, asks, and timestamp
            
        Raises:
            ExchangeAPIError: If unable to fetch order book data
        """
        try:
            pair = GateioUtils.symbol_to_pair(symbol)
            
            # Validate limit for Gate.io API (1-100)
            optimized_limit = max(1, min(100, limit))
            
            params = {
                'currency_pair': pair,
                'limit': optimized_limit,
                'with_id': 'false'  # Don't need order IDs for performance
            }
            
            response_data = await self.client.get(
                GateioConfig.SPOT_ENDPOINTS['order_book'],
                params=params,
                config=GateioConfig.rest_config['market_data_fast']
            )
            
            # Gate.io orderbook response format:
            # {
            #   "id": 123456789,
            #   "current": 1234567890123,
            #   "update": 1234567890456,
            #   "asks": [["50000", "0.001"], ...],
            #   "bids": [["49999", "0.002"], ...]
            # }
            
            timestamp = float(response_data.get('current', time.time() * 1000)) / 1000.0
            
            # Transform to unified format
            bids = [
                OrderBookEntry(price=float(bid[0]), size=float(bid[1]))
                for bid in response_data.get('bids', [])
            ]
            
            asks = [
                OrderBookEntry(price=float(ask[0]), size=float(ask[1]))  
                for ask in response_data.get('asks', [])
            ]
            
            orderbook = OrderBook(
                bids=bids,
                asks=asks,
                timestamp=timestamp
            )
            
            self.logger.debug(f"Retrieved orderbook for {symbol}: {len(bids)} bids, {len(asks)} asks")
            return orderbook
            
        except Exception as e:
            self.logger.error(f"Failed to get orderbook for {symbol}: {e}")
            raise ExchangeAPIError(500, f"Orderbook fetch failed: {str(e)}")
    
    async def get_recent_trades(self, symbol: Symbol, limit: int = 500) -> List[Trade]:
        """
        Get recent trades for a symbol.
        
        HFT COMPLIANT: Never caches trade data - always fresh API call.
        
        Args:
            symbol: Symbol to get trades for
            limit: Number of trades to retrieve (1-1000 for Gate.io)
            
        Returns:
            List of recent Trade objects
            
        Raises:
            ExchangeAPIError: If unable to fetch trade data
        """
        try:
            pair = GateioUtils.symbol_to_pair(symbol)
            
            # Validate limit for Gate.io API (1-1000)
            optimized_limit = max(1, min(1000, limit))
            
            params = {
                'currency_pair': pair,
                'limit': optimized_limit
            }
            
            response_data = await self.client.get(
                GateioConfig.SPOT_ENDPOINTS['trades'],
                params=params,
                config=GateioConfig.rest_config['market_data_fast']
            )
            
            # Gate.io trades response format:
            # [
            #   {
            #     "id": "12345",
            #     "create_time": "1234567890",
            #     "side": "buy",
            #     "amount": "0.001",
            #     "price": "50000"
            #   }, ...
            # ]
            
            if not isinstance(response_data, list):
                raise ExchangeAPIError(500, "Invalid trades response format")
            
            trades = []
            for trade_data in response_data:
                side = GateioMappings.get_unified_side(trade_data.get('side', 'buy'))
                
                trade = Trade(
                    price=float(trade_data.get('price', '0')),
                    amount=float(trade_data.get('amount', '0')),
                    side=side,
                    timestamp=int(trade_data.get('create_time', '0')),
                    is_maker=False  # Gate.io doesn't provide maker/taker info in this endpoint
                )
                trades.append(trade)
            
            self.logger.debug(f"Retrieved {len(trades)} recent trades for {symbol}")
            return trades
            
        except Exception as e:
            self.logger.error(f"Failed to get recent trades for {symbol}: {e}")
            raise ExchangeAPIError(500, f"Recent trades fetch failed: {str(e)}")
    
    async def get_server_time(self) -> int:
        """
        Get Gate.io server timestamp.
        
        Returns:
            Unix timestamp in milliseconds
            
        Raises:
            ExchangeAPIError: If unable to get server time
        """
        try:
            response_data = await self.client.get(
                '/spot/time',  # Gate.io server time endpoint
                config=GateioConfig.rest_config['default_fast_ping']
            )
            
            # Gate.io time response format: {"server_time": 1234567890}
            server_time = response_data.get('server_time', int(time.time()))
            
            # Convert to milliseconds if needed (Gate.io returns seconds)
            if server_time < 1e10:  # If less than 10 digits, it's in seconds
                server_time *= 1000
                
            self.logger.debug(f"Retrieved server time: {server_time}")
            return int(server_time)
            
        except Exception as e:
            self.logger.error(f"Failed to get server time: {e}")
            raise ExchangeAPIError(500, f"Server time fetch failed: {str(e)}")
    
    async def ping(self) -> bool:
        """
        Test connectivity to Gate.io exchange.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Use server time endpoint for ping test
            await self.get_server_time()
            self.logger.debug("Ping successful")
            return True
            
        except Exception as e:
            self.logger.debug(f"Ping failed: {e}")
            return False
    
    async def get_klines(self, symbol: Symbol, timeframe: KlineInterval,
                         date_from: Optional[datetime], date_to: Optional[datetime]) -> List[Kline]:
        """
        Get kline/candlestick data for a symbol.
        
        HFT COMPLIANT: Never caches kline data - always fresh API call.
        
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
        klines = []
        try:
            pair = GateioUtils.symbol_to_pair(symbol)
            interval = GateioUtils.get_gateio_kline_interval(timeframe)
            
            params = {
                'currency_pair': pair,
                'interval': interval
            }
            
            # Gate.io API: Either use limit OR use from/to, but not both
            if date_from or date_to:
                # Use time range mode
                if date_from:
                    params['from'] = int(date_from.timestamp())
                if date_to:
                    params['to'] = int(date_to.timestamp())
            else:
                # Use limit mode (max 720 klines - Gate.io limit is ~12 hours for 1m data)
                params['limit'] = 720
            
            response_data = await self.client.get(
                GateioConfig.SPOT_ENDPOINTS['candlesticks'],
                params=params,
                config=GateioConfig.rest_config['market_data']
            )
            
            # Gate.io returns array of arrays with different format than MEXC:
            # Each kline: [timestamp, volume, close, high, low, open, previous_close]
            # Note: Gate.io format is: [time, volume, close, high, low, open, previous_close]
            if not isinstance(response_data, list):
                raise ExchangeAPIError(500, "Invalid candlesticks response format")
            
            klines = []
            for kline_data in response_data:
                if len(kline_data) >= 7:
                    # Gate.io format: [time, volume, close, high, low, open, previous_close]
                    timestamp = int(float(kline_data[0]))  # Unix timestamp
                    volume = float(kline_data[1])
                    close_price = float(kline_data[2])
                    high_price = float(kline_data[3])
                    low_price = float(kline_data[4])
                    open_price = float(kline_data[5])
                    # previous_close = float(kline_data[6])  # Not used in unified format
                    
                    # Calculate quote volume (Gate.io doesn't provide it directly)
                    # Estimate as volume * average price
                    avg_price = (high_price + low_price + open_price + close_price) / 4
                    quote_volume = volume * avg_price
                    
                    kline = Kline(
                        symbol=symbol,
                        interval=timeframe,
                        open_time=timestamp * 1000,  # Convert to milliseconds
                        close_time=timestamp * 1000 + self._get_interval_milliseconds(timeframe),
                        open_price=open_price,
                        high_price=high_price,
                        low_price=low_price,
                        close_price=close_price,
                        volume=volume,
                        quote_volume=quote_volume,
                        trades_count=0  # Gate.io doesn't provide trade count
                    )
                    klines.append(kline)
            
            # Gate.io returns oldest first (already sorted correctly)
            self.logger.debug(f"Retrieved {len(klines)} klines for {pair} {interval}")
            return klines
            
        except Exception as e:
            self.logger.error(f"Failed to get klines for {symbol}: {e}")
            raise ExchangeAPIError(500, f"Klines fetch failed: {str(e)}")
    
    def _calculate_optimal_batch_size(self, timeframe: KlineInterval, total_duration_seconds: int) -> int:
        """
        Calculate optimal batch size respecting Gate.io's 10,000 point historical limit.
        
        Args:
            timeframe: Kline interval
            total_duration_seconds: Total duration of requested time range
            
        Returns:
            Optimal batch size for this timeframe
        """
        MAX_HISTORICAL_POINTS = 10000
        interval_seconds = self._get_interval_seconds(timeframe)
        
        # Calculate total points needed
        total_points = int(total_duration_seconds / interval_seconds)
        
        # Gate.io allows max 1000 points per request, but we should be conservative
        # for longer time ranges due to historical access limits
        if total_points <= MAX_HISTORICAL_POINTS:
            # Conservative batch sizing - Gate.io has strict historical limits
            batch_sizes = {
                KlineInterval.MINUTE_1: 720,    # 12 hours per request (safe zone)
                KlineInterval.MINUTE_5: 1000,   # 3.5 days per request  
                KlineInterval.MINUTE_15: 1000,  # 10.4 days per request
                KlineInterval.MINUTE_30: 1000,  # 20.8 days per request
                KlineInterval.HOUR_1: 1000,     # 41.7 days per request
                KlineInterval.HOUR_4: 1000,     # 166 days per request
                KlineInterval.HOUR_12: 1000,    # 500 days per request
                KlineInterval.DAY_1: 1000,      # 2.7 years per request
                KlineInterval.WEEK_1: 1000,     # 19.2 years per request
                KlineInterval.MONTH_1: 1000,    # 83 years per request
            }
            return batch_sizes.get(timeframe, 720)  # Default to 720 (12 hours for 1m)
        else:
            # For very large ranges, use smaller chunks
            return min(720, MAX_HISTORICAL_POINTS // 10)  # Use 1/10 of limit per batch

    async def get_klines_batch(self, symbol: Symbol, timeframe: KlineInterval,
                              date_from: Optional[datetime], date_to: Optional[datetime]) -> List[Kline]:
        """
        Get batch kline data by making multiple get_klines requests for large time ranges.
        
        This method splits large time ranges into chunks to handle Gate.io's API limits:
        - Maximum 500 klines per individual request
        - Maximum 10,000 historical data points total
        - Automatic date range adjustment if needed
        
        HFT COMPLIANT: Never caches kline data - always fresh API calls.
        
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
        interval_seconds = self._get_interval_seconds(timeframe)
        if interval_seconds == 0:
            # Fallback to single request for unknown intervals
            return await self.get_klines(symbol, timeframe, date_from, date_to)
        
        # Gate.io has very restrictive historical access - much more conservative approach needed
        # Based on testing: 2 days works, 3+ days often fail with "too long ago"
        MAX_SAFE_DAYS = 2  # Conservative limit based on actual API testing
        MAX_SAFE_DURATION_SECONDS = MAX_SAFE_DAYS * 24 * 3600
        
        total_duration_seconds = int((date_to - date_from).total_seconds())
        total_points = int(total_duration_seconds / interval_seconds)
        
        if total_duration_seconds > MAX_SAFE_DURATION_SECONDS:
            # Adjust date_from to stay within safe historical limit
            adjusted_date_from = datetime.fromtimestamp(date_to.timestamp() - MAX_SAFE_DURATION_SECONDS)
            
            self.logger.warning(
                f"Gate.io historical limit: {total_duration_seconds/3600:.1f} hours requested, "
                f"max {MAX_SAFE_DURATION_SECONDS/3600:.1f} hours safe limit. "
                f"Adjusted start date from {date_from.strftime('%Y-%m-%d %H:%M')} "
                f"to {adjusted_date_from.strftime('%Y-%m-%d %H:%M')}"
            )
            
            date_from = adjusted_date_from
            total_duration_seconds = MAX_SAFE_DURATION_SECONDS
        
        # Calculate optimal batch size for this timeframe
        batch_size = self._calculate_optimal_batch_size(timeframe, total_duration_seconds)
        chunk_duration_seconds = batch_size * interval_seconds
        
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
            
            # Rate limiting: Add 0.3 second delay between requests to avoid 429 errors
            # Gate.io has strict rate limits: 200 requests/10 seconds (20 req/sec)
            # Only delay if we have more requests to make
            await asyncio.sleep(0.3)
        
        # Remove duplicates and sort
        unique_klines = {}
        for kline in all_klines:
            unique_klines[kline.open_time] = kline
        
        sorted_klines = sorted(unique_klines.values(), key=lambda k: k.open_time)
        
        self.logger.info(f"Retrieved {len(sorted_klines)} klines in batch for {symbol.base}/{symbol.quote}")
        return sorted_klines
    
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
    
    async def close(self) -> None:
        """Close the REST client and clean up resources."""
        try:
            await self.client.close()
            self.logger.info("Closed Gate.io public REST client")
        except Exception as e:
            self.logger.error(f"Error closing public REST client: {e}")
    
    def __repr__(self) -> str:
        return f"GateioPublicExchange(base_url={self.base_url})"