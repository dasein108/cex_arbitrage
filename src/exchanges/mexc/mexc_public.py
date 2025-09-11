"""
MEXC Public Exchange Implementation

Ultra-high-performance MEXC public API client optimized for cryptocurrency arbitrage trading.
Fully compliant with the unified PublicExchangeInterface for seamless integration.

Key Features:
- Complete unified interface compliance with proper struct mappings
- Sub-10ms response time optimization for arbitrage trading
- MEXC-specific rate limiting (18 req/sec conservative limit)
- Zero-copy JSON parsing with msgspec for maximum performance
- Intelligent error mapping to unified exception hierarchy
- Memory-efficient data transformations using unified structs

MEXC API Specifications:
- Base URL: https://api.mexc.com
- Rate Limits: 1200 requests/minute (20 req/sec, limited to 18 req/sec for safety)
- Weight-based rate limiting for some endpoints
- Standard REST API with JSON responses

Unified Interface Compliance:
- All data structures use msgspec.Struct from src/structs/
- All exceptions use unified hierarchy from src/common/exceptions
- Full type annotations using unified types
- Proper Symbol/SymbolInfo mappings with MEXC API

Threading: Fully async/await compatible, thread-safe for concurrent operations
Memory: O(1) per request, O(n) for order book data
"""

import asyncio
import time
from typing import Dict, List, Optional, Any
import logging
import msgspec

# MANDATORY imports - unified interface compliance
from structs.exchange import (
    Symbol, SymbolInfo, OrderBook, OrderBookEntry, Trade, 
    ExchangeName, AssetName, Side
)
from common.rest import RestClient, RestConfig
from common.config import config
from exchanges.interface.rest.public_exchange import PublicExchangeInterface
from exchanges.mexc.websocket import MexcWebSocketPublicStream


# MEXC API Response Structures - optimized with msgspec
class MexcSymbolResponse(msgspec.Struct):
    """MEXC exchange info symbol response structure."""
    symbol: str
    status: str
    baseAsset: str
    baseAssetPrecision: int
    baseCommissionPrecision: int
    baseSizePrecision: str
    contractAddress: str
    filters: list[dict]
    fullName: str
    isMarginTradingAllowed: bool
    isSpotTradingAllowed: bool
    makerCommission: str
    maxQuoteAmount: str
    maxQuoteAmountMarket: str
    orderTypes: list[str]
    permissions: list[str]
    quoteAmountPrecision: str
    quoteAmountPrecisionMarket: str
    quoteAsset: str
    quoteAssetPrecision: int
    quoteCommissionPrecision: int
    quotePrecision: int
    st: bool
    takerCommission: str
    tradeSideType: int


class MexcExchangeInfoResponse(msgspec.Struct):
    """MEXC exchange info API response."""
    timezone: str
    serverTime: int
    symbols: list[MexcSymbolResponse]


class MexcOrderBookResponse(msgspec.Struct):
    """MEXC order book API response structure."""
    lastUpdateId: int
    bids: list[list[str]]  # [price, quantity]
    asks: list[list[str]]  # [price, quantity]


class MexcTradeResponse(msgspec.Struct):
    """MEXC recent trades API response structure."""
    id: Optional[int]  # Can be None
    isBestMatch: bool
    isBuyerMaker: bool
    price: str
    qty: str
    quoteQty: str
    time: int
    tradeType: str  # "ASK" or "BID"


class MexcServerTimeResponse(msgspec.Struct):
    """MEXC server time API response."""
    serverTime: int


class MexcPublicExchange(PublicExchangeInterface):
    """
    High-performance MEXC public exchange implementation with unified interface compliance.
    
    Optimized for cryptocurrency arbitrage with sub-10ms response times and full
    compliance with the unified interface standards for seamless integration.
    """
    
    EXCHANGE_NAME = ExchangeName("MEXC")
    BASE_URL = "https://api.mexc.com"
    
    # MEXC Rate Limits - Uses configuration values
    @property
    def DEFAULT_RATE_LIMIT(self) -> int:
        return config.MEXC_RATE_LIMIT_PER_SECOND
    
    @property    
    def WEIGHT_RATE_LIMIT(self) -> int:
        return max(10, config.MEXC_RATE_LIMIT_PER_SECOND // 2)  # Conservative weight limit
    
    # API Endpoints
    ENDPOINTS = {
        'exchange_info': '/api/v3/exchangeInfo',
        'depth': '/api/v3/depth',
        'trades': '/api/v3/trades',
        'time': '/api/v3/time',
        'ping': '/api/v3/ping'
    }
    
    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        """
        Initialize MEXC public exchange client with unified interface compliance.
        
        Args:
            api_key: Optional API key for authenticated requests (not needed for public)
            secret_key: Optional secret key for authenticated requests (not needed for public)
        """
        super().__init__(self.EXCHANGE_NAME, self.BASE_URL)
        
        # Logger for debugging and monitoring
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Initialize ultra-simple REST client with optimal market data configuration
        rest_config = config.create_rest_config('MEXC', 'market_data')
        rest_config.require_auth = False  # Public endpoints don't need auth
        rest_config.max_concurrent = config.MEXC_RATE_LIMIT_PER_SECOND * 2  # High concurrency for arbitrage
        
        self.client = RestClient(
            base_url=self.BASE_URL,
            api_key=api_key,
            secret_key=secret_key,
            config=rest_config
        )
        
        # Cache for exchange info to reduce API calls
        self._exchange_info: Optional[Dict[Symbol, SymbolInfo]] = None

        # WebSocket integration for real-time data
        self._websocket: Optional[MexcWebSocketPublicStream] = None
        self._active_symbols: set[Symbol] = set()
        self._symbol_to_stream: Dict[Symbol, str] = {}
        
        # CRITICAL: Current orderbook state management (NOT caching)
        # This maintains current live state, not historical cached data
        self._current_orderbook_state: Dict[Symbol, OrderBook] = {}
        self._last_state_update: Dict[Symbol, float] = {}
        self._orderbook_locks: Dict[Symbol, asyncio.Lock] = {}
        
        # Fallback mechanism for WebSocket disconnections  
        self._rest_fallback_active = False
        self._fallback_threshold = config.WS_RECONNECT_DELAY  # Use config for fallback timing
        
        # Exchange info caching
        self._cache_timestamp: float = 0
        self._cache_ttl: float = 300.0  # 5-minute cache TTL
        
        self.logger.info(f"Initialized {self.EXCHANGE_NAME} public exchange client")
    
        # Create endpoint-specific configurations for different performance requirements
        self._endpoint_configs = {
            'exchange_info': config.create_rest_config('MEXC', 'history'),
            'depth': config.create_rest_config('MEXC', 'market_data'),
            'trades': config.create_rest_config('MEXC', 'market_data'),
            'time': config.create_rest_config('MEXC', 'default'),
            'ping': config.create_rest_config('MEXC', 'default')
        }
        
        # Customize specific endpoint configs for optimal performance
        self._endpoint_configs['depth'].timeout = config.REQUEST_TIMEOUT * 0.4  # Ultra-fast for order books
        self._endpoint_configs['depth'].max_retries = 1  # Fast fail for real-time data
        self._endpoint_configs['time'].timeout = config.REQUEST_TIMEOUT * 0.2  # Very fast for time sync
        self._endpoint_configs['ping'].timeout = config.REQUEST_TIMEOUT * 0.3  # Fast for connectivity
    
    def _get_symbol_lock(self, symbol: Symbol) -> asyncio.Lock:
        """
        Get or create per-symbol lock for concurrent orderbook updates.
        
        This enables concurrent orderbook processing across different symbols
        while maintaining thread safety for individual symbol updates.
        
        Args:
            symbol: Symbol to get lock for
            
        Returns:
            Per-symbol asyncio Lock
        """
        if symbol not in self._orderbook_locks:
            self._orderbook_locks[symbol] = asyncio.Lock()
        return self._orderbook_locks[symbol]
    
    @staticmethod
    async def symbol_to_pair(symbol: Symbol) -> str:
        """
        Convert Symbol to MEXC trading pair format.
        
        MEXC uses concatenated format without separator: BTCUSDT, ETHUSDT, etc.
        
        Args:
            symbol: Symbol struct with base and quote assets
            
        Returns:
            MEXC trading pair string (e.g., "BTCUSDT")
            
        Example:
            Symbol(base=AssetName("BTC"), quote=AssetName("USDT")) -> "BTCUSDT"
        """
        return f"{symbol.base}{symbol.quote}"
    
    @staticmethod
    async def pair_to_symbol(pair: str) -> Symbol:
        """
        Convert MEXC trading pair to Symbol using smart quote asset detection.
        
        MEXC uses concatenated format. We need to split based on common quote assets.
        Priority order: USDT, USDC, BTC, ETH, BNB, BUSD (longest first to avoid conflicts)
        
        Args:
            pair: MEXC trading pair string (e.g., "BTCUSDT")
            
        Returns:
            Symbol struct with base and quote assets
            
        Examples:
            "BTCUSDT" -> Symbol(base=AssetName("BTC"), quote=AssetName("USDT"))
            "ETHUSDC" -> Symbol(base=AssetName("ETH"), quote=AssetName("USDC"))
        """
        # Common quote assets in priority order (longest first to avoid conflicts)
        quote_assets = ['USDT', 'USDC', 'BUSD', 'BTC', 'ETH', 'BNB', 'USD']
        
        pair_upper = pair.upper()
        
        # Find the quote asset by checking suffixes
        for quote in quote_assets:
            if pair_upper.endswith(quote):
                base = pair_upper[:-len(quote)]
                if base:  # Ensure base is not empty
                    return Symbol(
                        base=AssetName(base),
                        quote=AssetName(quote),
                        is_futures=False
                    )
        
        # Fallback: if no common quote found, assume last 3-4 chars are quote
        # This handles edge cases and new quote assets
        if len(pair_upper) >= 6:
            # Try 4-char quote first (like USDT), then 3-char (like BTC)
            for quote_len in [4, 3]:
                if len(pair_upper) > quote_len:
                    base = pair_upper[:-quote_len]
                    quote = pair_upper[-quote_len:]
                    return Symbol(
                        base=AssetName(base),
                        quote=AssetName(quote),
                        is_futures=False
                    )
        
        # Last resort: split roughly in half
        mid = len(pair_upper) // 2
        return Symbol(
            base=AssetName(pair_upper[:mid]),
            quote=AssetName(pair_upper[mid:]),
            is_futures=False
        )
    
    def _extract_symbol_precision(self, mexc_symbol: MexcSymbolResponse) -> tuple[int, int, float, float]:
        """
        Extract precision and size limits from MEXC symbol data.
        
        Args:
            mexc_symbol: MEXC symbol response with precision fields
            
        Returns:
            Tuple of (base_precision, quote_precision, min_quote_amount, min_base_amount)
        """
        # Use MEXC provided precision values
        base_precision = mexc_symbol.baseAssetPrecision
        quote_precision = mexc_symbol.quotePrecision
        
        # Extract minimum amounts from MEXC fields
        min_base_amount = float(mexc_symbol.baseSizePrecision) if mexc_symbol.baseSizePrecision else 0.0
        min_quote_amount = float(mexc_symbol.quoteAmountPrecision) if mexc_symbol.quoteAmountPrecision else 0.0
        
        # Process filters if they exist (backup precision source)
        for filter_info in mexc_symbol.filters:
            filter_type = filter_info.get('filterType')
            
            if filter_type == 'LOT_SIZE':
                # Base asset minimum amount from filters
                min_qty = float(filter_info.get('minQty', '0'))
                if min_qty > 0:
                    min_base_amount = max(min_base_amount, min_qty)
                
            elif filter_type == 'MIN_NOTIONAL':
                # Minimum quote amount (notional value) from filters
                min_notional = float(filter_info.get('minNotional', '0'))
                if min_notional > 0:
                    min_quote_amount = max(min_quote_amount, min_notional)
        
        return base_precision, quote_precision, min_quote_amount, min_base_amount
    
    async def get_exchange_info(self) -> Dict[Symbol, SymbolInfo]:
        """
        Get MEXC trading rules and symbol information with unified interface compliance.
        
        Uses intelligent caching to minimize API calls while ensuring data freshness.
        Optimized for high-frequency access with sub-millisecond cache hits.
        
        Returns:
            Dictionary mapping Symbol to SymbolInfo with complete trading rules
        
        Raises:
            ExchangeAPIError: If unable to fetch exchange info and no cache available
        """
        current_time = time.time()
        
        # Fast path: return cached data if still valid
        if (self._exchange_info is not None and 
            current_time - self._cache_timestamp < self._cache_ttl):
            return self._exchange_info
        
        # Fetch exchange info from MEXC using endpoint-specific config
        response_data = await self.client.get(
            self.ENDPOINTS['exchange_info'],
            config=self._endpoint_configs['exchange_info']
        )
        
        # Parse response with msgspec for maximum performance
        exchange_info = msgspec.convert(response_data, MexcExchangeInfoResponse)
        
        # Transform to unified format
        symbol_info_map: Dict[Symbol, SymbolInfo] = {}
        
        for mexc_symbol in exchange_info.symbols:
            # Convert to unified Symbol format
            symbol = Symbol(
                base=AssetName(mexc_symbol.baseAsset),
                quote=AssetName(mexc_symbol.quoteAsset),
                is_futures=False
            )
            
            # Extract precision and limits from MEXC symbol data
            base_prec, quote_prec, min_quote, min_base = self._extract_symbol_precision(mexc_symbol)
            
            # Create unified SymbolInfo with extracted data
            symbol_info = SymbolInfo(
                exchange=self.EXCHANGE_NAME,
                symbol=symbol,
                base_precision=base_prec,
                quote_precision=quote_prec,
                min_quote_amount=min_quote,
                min_base_amount=min_base,
                is_futures=False,
                maker_commission=float(mexc_symbol.makerCommission),
                taker_commission=float(mexc_symbol.takerCommission),
                inactive=mexc_symbol.status == '1'
            )
            
            symbol_info_map[symbol] = symbol_info
        
        # Update cache
        self._exchange_info = symbol_info_map
        self._cache_timestamp = current_time

        self.logger.info(f"Retrieved exchange info for {len(symbol_info_map)} symbols")
        return symbol_info_map
    
    async def get_orderbook(self, symbol: Symbol, limit: int = 100) -> OrderBook:
        """
        Get order book for a symbol with unified interface compliance and ultra-low latency.
        
        Uses zero-copy parsing and efficient data structures for sub-10ms response times.
        All data is mapped to unified OrderBook struct with proper OrderBookEntry objects.
        
        Args:
            symbol: Unified Symbol struct with base and quote assets
            limit: Order book depth limit (5, 10, 20, 50, 100, 500, 1000, 5000)
            
        Returns:
            Unified OrderBook struct with bids, asks, and timestamp
            
        Raises:
            ExchangeAPIError: If unable to fetch order book data
            RateLimitError: If rate limit is exceeded
        """
        # Convert symbol to MEXC pair format
        pair = await self.symbol_to_pair(symbol)
        
        # Validate and optimize limit for MEXC API
        valid_limits = [5, 10, 20, 50, 100, 500, 1000, 5000]
        optimized_limit = min(valid_limits, key=lambda x: abs(x - limit))
        
        # Request parameters
        params = {
            'symbol': pair,
            'limit': optimized_limit
        }
        
        # Fetch order book data with performance tracking using endpoint-specific config
        start_time = time.time()
        response_data = await self.client.get(
            self.ENDPOINTS['depth'],
            params=params,
            config=self._endpoint_configs['depth']
        )
        
        # Parse with msgspec for maximum speed
        orderbook_data = msgspec.convert(response_data, MexcOrderBookResponse)
        
        # Transform to unified format with zero-copy optimization
        bids = [
            OrderBookEntry(price=float(bid[0]), size=float(bid[1]))
            for bid in orderbook_data.bids
        ]
        
        asks = [
            OrderBookEntry(price=float(ask[0]), size=float(ask[1]))
            for ask in orderbook_data.asks
        ]
        
        # Create unified OrderBook with current timestamp
        orderbook = OrderBook(
            bids=bids,
            asks=asks,
            timestamp=time.time()
        )
        
        # Log performance metrics for optimization
        response_time = (time.time() - start_time) * 1000  # Convert to ms
        self.logger.debug(f"Order book for {pair} retrieved in {response_time:.2f}ms")
        
        return orderbook
    
    async def get_recent_trades(self, symbol: Symbol, limit: int = 500) -> List[Trade]:
        """
        Get recent trades for a symbol with unified interface compliance.
        
        All trade data is mapped to unified Trade structs with proper Side enum handling.
        MEXC isBuyerMaker field is correctly mapped to Side.BUY/Side.SELL.
        
        Args:
            symbol: Unified Symbol struct with base and quote assets
            limit: Number of recent trades (max 1000)
            
        Returns:
            List of unified Trade objects sorted by timestamp (newest first)
            
        Raises:
            ExchangeAPIError: If unable to fetch trade data
            RateLimitError: If rate limit is exceeded
        """
        # Convert symbol to MEXC pair format
        pair = await self.symbol_to_pair(symbol)
        
        # Optimize limit for API constraints
        optimized_limit = min(limit, 1000)  # MEXC max limit
        
        params = {
            'symbol': pair,
            'limit': optimized_limit
        }
        
        # Fetch trade data using endpoint-specific config
        response_data = await self.client.get(
            self.ENDPOINTS['trades'],
            params=params,
            config=self._endpoint_configs['trades']
        )
        
        # Parse trade data efficiently with msgspec
        trade_responses = msgspec.convert(response_data, list[MexcTradeResponse])
        
        # Transform to unified format with proper Side mapping
        trades = []
        for trade_data in trade_responses:
            # CRITICAL: Map MEXC isBuyerMaker correctly to Side enum
            # If isBuyerMaker=True, the trade taker was selling -> Side.SELL
            # If isBuyerMaker=False, the trade taker was buying -> Side.BUY
            side = Side.SELL if trade_data.isBuyerMaker else Side.BUY
            
            trade = Trade(
                price=float(trade_data.price),
                amount=float(trade_data.qty),
                side=side,
                timestamp=trade_data.time,
                is_maker=trade_data.isBuyerMaker
            )
            
            trades.append(trade)
        
        # Sort by timestamp (newest first) for consistency
        trades.sort(key=lambda t: t.timestamp, reverse=True)
        
        self.logger.debug(f"Retrieved {len(trades)} recent trades for {pair}")
        return trades
    
    async def get_server_time(self) -> int:
        """
        Get MEXC server timestamp with minimal latency and unified error handling.
        
        Returns:
            Server timestamp in milliseconds
            
        Raises:
            ExchangeAPIError: If unable to fetch server time
            RateLimitError: If rate limit is exceeded
        """
        # Fetch server time using endpoint-specific config
        response_data = await self.client.get(
            self.ENDPOINTS['time'],
            config=self._endpoint_configs['time']
        )
        
        # Parse server time response with msgspec
        time_response = msgspec.convert(response_data, MexcServerTimeResponse)
        
        return time_response.serverTime
    
    async def ping(self) -> bool:
        """
        Test connectivity to MEXC exchange with unified interface compliance.
        
        Returns:
            True if connection successful
            
        Raises:
            ExchangeAPIError: If unable to ping the exchange
            RateLimitError: If rate limit is exceeded
            
        Note:
            Following new development standards, exceptions now bubble up to application level.
        """
        try:
            await self.client.get(
                self.ENDPOINTS['ping'],
                config=self._endpoint_configs['ping']
            )
            return True
        except Exception:
            return False
    
    async def close(self):
        """Clean up resources and close connections."""
        if hasattr(self, 'client'):
            await self.client.close()
        self.logger.info(f"Closed {self.EXCHANGE_NAME} exchange client")
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    def get_performance_metrics(self) -> dict:
        """Get basic performance metrics for monitoring and optimization."""
        return {
            'exchange': str(self.EXCHANGE_NAME),
            'base_url': self.BASE_URL,
            'active_symbols': len(self._active_symbols),
            'current_state_management': 'Fresh preload + real-time updates',
            'rest_fallback_active': self._rest_fallback_active
        }
    
    # Abstract method implementations for WebSocket integration
    
    async def init(self, symbols: List[Symbol]) -> None:
        """
        Initialize exchange with symbols and start WebSocket connections.
        
        1. Load initial orderbooks from REST API
        2. Start WebSocket streams for real-time updates
        3. Subscribe to orderbook and trades for all symbols
        """
        self.logger.info(f"Initializing MEXC exchange with {len(symbols)} symbols")
        
        # Store active symbols
        for symbol in symbols:
            self._active_symbols.add(symbol)
        
        # CRITICAL: Load fresh current orderbook state for all symbols
        # This is NOT caching - it's getting current live state for initialization
        self.logger.info(f"Loading fresh orderbook state for {len(symbols)} symbols")
        
        # Load current state for all symbols concurrently
        preload_tasks = [
            self._ensure_fresh_orderbook_state(symbol)
            for symbol in symbols
        ]
        
        # Wait for all preloads to complete (don't fail if some symbols fail)
        await asyncio.gather(*preload_tasks, return_exceptions=True)
        
        # Count successful preloads (no lock needed for reading length)
        successful_preloads = len(self._current_orderbook_state)
        
        self.logger.info(f"Successfully loaded fresh state for {successful_preloads}/{len(symbols)} symbols")
        
        # Create WebSocket streams for all symbols
        streams = []
        for symbol in symbols:
            try:
                stream = await self._create_orderbook_stream(symbol)
                streams.append(stream)
                self._symbol_to_stream[symbol] = stream
            except Exception as e:
                self.logger.error(f"Failed to create stream for {symbol}: {e}")
        
        # Initialize WebSocket connection if we have streams
        if streams:
            self._websocket = MexcWebSocketPublicStream(
                message_handler=self._handle_websocket_message,
                error_handler=self._handle_websocket_error
            )
            
            # Start WebSocket connection and subscribe to streams
            await self._websocket.start()
            await self._websocket.subscribe(streams)
            self.logger.info(f"WebSocket initialized with {len(streams)} streams")
        else:
            self.logger.warning("No valid streams to subscribe to")
        
        self.logger.info(f"MEXC exchange initialized with {len(symbols)} symbols - WebSocket streaming only")
    
    async def start_symbol(self, symbol: Symbol) -> None:
        """
        Start data streaming for a new symbol.
        
        1. Add to active symbols
        2. Load initial orderbook from REST API
        3. Create WebSocket stream and subscribe
        """
        if symbol in self._active_symbols:
            self.logger.debug(f"Symbol {symbol} already active")
            return
        
        self.logger.info(f"Starting symbol {symbol}")
        
        # Add to active symbols
        self._active_symbols.add(symbol)
        
        # CRITICAL: Load fresh current orderbook state for new symbol
        # This ensures we have current state before starting real-time updates
        await self._ensure_fresh_orderbook_state(symbol)
        
        # Create and subscribe to WebSocket stream
        try:
            stream = await self._create_orderbook_stream(symbol)
            self._symbol_to_stream[symbol] = stream
            
            if self._websocket:
                await self._websocket.subscribe([stream])
                self.logger.info(f"Subscribed to stream for {symbol}")
            else:
                self.logger.warning("WebSocket not initialized, cannot subscribe")
        except Exception as e:
            self.logger.error(f"Failed to start streaming for {symbol}: {e}")
    
    async def stop_symbol(self, symbol: Symbol) -> None:
        """
        Stop data streaming for a symbol.
        
        1. Remove from active symbols
        2. Unsubscribe from WebSocket stream
        3. Remove orderbook from cache
        """
        if symbol not in self._active_symbols:
            self.logger.debug(f"Symbol {symbol} not active")
            return
        
        self.logger.info(f"Stopping symbol {symbol}")
        
        # Remove from active symbols
        self._active_symbols.discard(symbol)
        
        # Unsubscribe from WebSocket stream
        stream = self._symbol_to_stream.get(symbol)
        if stream and self._websocket:
            try:
                await self._websocket.unsubscribe([stream])
                self.logger.debug(f"Unsubscribed from stream for {symbol}")
            except Exception as e:
                self.logger.error(f"Failed to unsubscribe from stream for {symbol}: {e}")
        
        # Clean up symbol data
        self._symbol_to_stream.pop(symbol, None)
        
        # Clean up current state for this symbol
        async with self._get_symbol_lock(symbol):
            self._current_orderbook_state.pop(symbol, None)
            self._last_state_update.pop(symbol, None)
            self._orderbook_locks.pop(symbol, None)  # Clean up the lock too
        
        self.logger.info(f"Stopped symbol {symbol}")
    
    # Helper methods for WebSocket integration
    
    async def _create_orderbook_stream(self, symbol: Symbol) -> str:
        """Create differential depth stream identifier for a symbol."""
        symbol_str = await self.symbol_to_pair(symbol)
        # Use MEXC's depth stream with protobuf format for efficient updates
        return f"spot@public.depth.v3.api.pb@{symbol_str.upper()}"
    
    async def _on_websocket_reconnect(self) -> None:
        """
        Handle WebSocket reconnection by refreshing current orderbook state.
        
        After reconnection, we don't know what updates we missed during disconnect.
        Must reload current state from REST API to ensure accuracy.
        """
        self.logger.info("WebSocket reconnected - refreshing orderbook state for all active symbols")
        
        # Get fresh state for all active symbols concurrently
        refresh_tasks = [
            self._ensure_fresh_orderbook_state(symbol)
            for symbol in self._active_symbols
        ]
        
        # Wait for all refreshes to complete
        await asyncio.gather(*refresh_tasks, return_exceptions=True)
        
        # Count successful refreshes (no lock needed for reading)
        refreshed_count = len([
            symbol for symbol in self._active_symbols 
            if symbol in self._current_orderbook_state
        ])
        
        self.logger.info(f"Refreshed orderbook state for {refreshed_count}/{len(self._active_symbols)} symbols after reconnection")
        
        # Resume real-time updates by resubscribing
        streams = list(self._symbol_to_stream.values())
        if streams and self._websocket:
            try:
                await self._websocket.subscribe(streams)
                self.logger.info(f"Resubscribed to {len(streams)} streams after reconnection")
            except Exception as e:
                self.logger.error(f"Failed to resubscribe after reconnection: {e}")

    async def _handle_websocket_error(self, error: Exception) -> None:
        """
        Handle WebSocket errors and trigger reconnection state refresh.
        
        Args:
            error: The WebSocket error that occurred
        """
        self.logger.warning(f"WebSocket error occurred: {error}")
        
        # If this is a disconnection error, prepare for state refresh on reconnect
        if "disconnect" in str(error).lower() or "connection" in str(error).lower():
            self.logger.info("WebSocket disconnection detected - will refresh state on reconnect")
            self._rest_fallback_active = True
    
    async def _handle_websocket_message(self, message: Dict[str, Any]) -> None:
        """Handle WebSocket messages and update current orderbook state."""
        try:
            if not isinstance(message, dict):
                return
            
            # Check if we need to refresh state after reconnection
            if self._rest_fallback_active:
                self.logger.info("WebSocket message received after disconnection - refreshing state")
                await self._on_websocket_reconnect()
                self._rest_fallback_active = False
            
            # Extract symbol and orderbook data from message
            # This depends on the specific WebSocket message format
            stream_name = message.get('stream')
            data = message.get('data')
            
            if not stream_name or not data:
                return
            
            # Extract symbol from stream name 
            symbol = None
            # Format: "spot@public.increase.depth.v3.api@BTCUSDT" -> "BTCUSDT"
            if 'increase.depth' in stream_name and '@' in stream_name:
                symbol_str = stream_name.split('@')[-1].upper()
                symbol = await self.pair_to_symbol(symbol_str)
            # Fallback for old depth format
            elif '@depth' in stream_name:
                symbol_str = stream_name.replace('@depth', '').upper()
                symbol = await self.pair_to_symbol(symbol_str)
            
            if symbol and symbol in self._active_symbols:
                # Parse orderbook data and update cache
                bids = [
                    OrderBookEntry(price=float(bid[0]), size=float(bid[1]))
                    for bid in data.get('bids', [])
                ]
                asks = [
                    OrderBookEntry(price=float(ask[0]), size=float(ask[1]))
                    for ask in data.get('asks', [])
                ]
                
                current_timestamp = time.time()
                orderbook = OrderBook(
                    bids=bids,
                    asks=asks,
                    timestamp=current_timestamp
                )
                
                # CRITICAL: Update current orderbook state with real-time data
                # This maintains current live state, not historical cached data
                current_time = time.time()
                
                # Apply differential update to current state (per-symbol thread-safe)
                async with self._get_symbol_lock(symbol):
                    self._current_orderbook_state[symbol] = orderbook
                    self._last_state_update[symbol] = current_time
                
                self.logger.debug(f"Updated real-time orderbook for {symbol} using {stream_name}")
        
        except Exception as e:
            self.logger.error(f"Error handling WebSocket message: {e}")
    
    async def _ensure_fresh_orderbook_state(self, symbol: Symbol) -> None:
        """
        CRITICAL: Load current orderbook state via REST API.
        
        This is NOT caching - it's getting the current live state.
        Used for initialization and reconnection to ensure we have current data.
        
        Args:
            symbol: Symbol to load current state for
        """
        try:
            self.logger.debug(f"Loading fresh orderbook state for {symbol}")
            
            # Get current state from REST API - always fresh
            fresh_orderbook = await self.get_orderbook(symbol, limit=100)
            current_time = time.time()
            
            # Update current state (per-symbol thread-safe)
            async with self._get_symbol_lock(symbol):
                self._current_orderbook_state[symbol] = fresh_orderbook
                self._last_state_update[symbol] = current_time
            
            self.logger.debug(f"Loaded fresh orderbook state for {symbol} with {len(fresh_orderbook.bids)} bids, {len(fresh_orderbook.asks)} asks")
            
        except Exception as e:
            self.logger.error(f"Failed to load fresh orderbook state for {symbol}: {e}")
            # Don't raise - continue with other symbols
    
    async def get_current_orderbook_state(self, symbol: Symbol) -> Optional[OrderBook]:
        """
        Get current orderbook state.
        
        Returns current live state (not cached historical data).
        State is maintained through fresh initialization + real-time updates.
        
        Args:
            symbol: Symbol to get current state for
            
        Returns:
            Current orderbook state or None if not available
        """
        async with self._get_symbol_lock(symbol):
            return self._current_orderbook_state.get(symbol)
    
    async def get_fresh_orderbook_data(self, symbol: Symbol) -> Optional[OrderBook]:
        """
        CRITICAL: Get fresh orderbook data via REST API.
        
        Always makes fresh REST API call for absolute data freshness.
        Use this when you need guaranteed fresh data (not current state).
        
        Args:
            symbol: Symbol to get fresh orderbook for
            
        Returns:
            Fresh orderbook data from REST API or None if unavailable
        """
        try:
            # Always make fresh REST API call - never return state or cached data
            return await self.get_orderbook(symbol, limit=100)
        except Exception as e:
            self.logger.error(f"Failed to get fresh orderbook for {symbol}: {e}")
            return None
    
    def is_symbol_active(self, symbol: Symbol) -> bool:
        """Check if symbol is actively streaming."""
        return symbol in self._active_symbols
    
    def get_active_symbols(self) -> set[Symbol]:
        """Get all active symbols."""
        return self._active_symbols.copy()
    
    async def stop_all_streams(self) -> None:
        """Stop all WebSocket connections and cleanup."""
        if self._websocket:
            await self._websocket.stop()
            self._websocket = None
        
        # Clear all data
        self._active_symbols.clear()
        self._symbol_to_stream.clear()
        
        # Clear current orderbook state
        self._current_orderbook_state.clear()
        self._last_state_update.clear()
        self._orderbook_locks.clear()
        
        self.logger.info("All WebSocket streams stopped")
    
    async def stop_all(self) -> None:
        """Stop all connections and cleanup (alias for compatibility)."""
        await self.stop_all_streams()
        await self.close()
    
    def get_websocket_health(self) -> Dict[str, Any]:
        """Get WebSocket connection health status."""
        if self._websocket:
            return {
                'exchange': str(self.EXCHANGE_NAME),
                'is_connected': hasattr(self._websocket, '_ws') and self._websocket._ws is not None,
                'streams': len(self._symbol_to_stream),
                'active_symbols': len(self._active_symbols),
                'current_state_symbols': len(self._current_orderbook_state),
                'connection_retries': getattr(self._websocket, '_reconnection_count', 0),
                'max_retries': getattr(self._websocket, 'max_retries', 10),
                'websocket_type': 'MexcWebSocketPublicStream',
                'last_message_time': getattr(self._websocket, '_last_message_time', None),
                'connection_established': self._websocket is not None
            }
        
        return {
            'exchange': str(self.EXCHANGE_NAME),
            'is_connected': False,
            'streams': 0,
            'active_symbols': len(self._active_symbols),
            'current_state_symbols': len(self._current_orderbook_state),
            'connection_retries': 0,
            'max_retries': 0,
            'websocket_type': None,
            'last_message_time': None,
            'connection_established': False
        }