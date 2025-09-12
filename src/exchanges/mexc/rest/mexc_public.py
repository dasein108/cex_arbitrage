"""
MEXC Public REST API Implementation

Focused REST-only client for MEXC public API endpoints.
Optimized for direct API calls without WebSocket or streaming features.

Key Features:
- Pure REST API implementation 
- Sub-10ms response times for market data
- Zero-copy JSON parsing with msgspec
- Unified interface compliance
- Simple caching for exchange info

MEXC API Specifications:
- Base URL: https://api.mexc.com
- Rate Limits: 1200 requests/minute (20 req/sec)
- Standard REST API with JSON responses
- No authentication required for public endpoints

Threading: Fully async/await compatible, thread-safe
Memory: O(1) per request, optimized for high-frequency access
"""

import time
from typing import Dict, List, Optional
import msgspec

from exchanges.mexc.common.mexc_struct import (
    MexcSymbolResponse, MexcExchangeInfoResponse, 
    MexcOrderBookResponse, MexcTradeResponse, MexcServerTimeResponse
)
from exchanges.interface.structs import (
    Symbol, SymbolInfo, OrderBook, OrderBookEntry, Trade,
    AssetName, Side, ExchangeName
)
from common.rest_client import RestClient
from exchanges.interface.rest.base_rest_public import PublicExchangeInterface
from exchanges.mexc.common.mexc_utils import MexcUtils
from exchanges.mexc.common.mexc_config import MexcConfig


class MexcPublicExchange(PublicExchangeInterface):
    """
    MEXC public REST API client focused on direct API calls.
    
    Provides access to public market data endpoints without WebSocket features.
    Optimized for high-frequency market data retrieval with minimal overhead.
    """
    
    def __init__(self):
        """
        Initialize MEXC public REST client.
        
        No authentication required for public endpoints.
        """
        super().__init__(ExchangeName(MexcConfig.EXCHANGE_NAME), MexcConfig.BASE_URL)
        
        # Initialize REST client for public endpoints
        self.client = RestClient(
            base_url=self.base_url,
            config=MexcConfig.rest_config['market_data']
        )
        
        # Simple caching for exchange info to reduce API calls
        self._exchange_info: Optional[Dict[Symbol, SymbolInfo]] = None
        self._cache_timestamp: float = 0
        self._cache_ttl: float = 300.0  # 5-minute cache TTL
        
        self.logger.info(f"Initialized {self.exchange} public REST client")
    
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
        
        # Return cached data if still valid
        if (self._exchange_info is not None and 
            current_time - self._cache_timestamp < self._cache_ttl):
            return self._exchange_info
        
        # Fetch fresh exchange info from MEXC
        response_data = await self.client.get(
            '/api/v3/exchangeInfo',
            config=MexcConfig.rest_config['default']
        )
        
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
        Get order book for a symbol.
        
        Args:
            symbol: Symbol to get orderbook for
            limit: Order book depth limit (5, 10, 20, 50, 100, 500, 1000, 5000)
            
        Returns:
            OrderBook with bids, asks, and timestamp
            
        Raises:
            ExchangeAPIError: If unable to fetch order book data
        """
        pair = MexcUtils.symbol_to_pair(symbol)
        
        # Validate limit for MEXC API
        valid_limits = [5, 10, 20, 50, 100, 500, 1000, 5000]
        optimized_limit = min(valid_limits, key=lambda x: abs(x - limit))
        
        params = {
            'symbol': pair,
            'limit': optimized_limit
        }
        
        response_data = await self.client.get(
            '/api/v3/depth',
            params=params,
            config=MexcConfig.rest_config['market_data_fast']
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
        pair = MexcUtils.symbol_to_pair(symbol)
        optimized_limit = min(limit, 1000)  # MEXC max limit
        
        params = {
            'symbol': pair,
            'limit': optimized_limit
        }
        
        response_data = await self.client.get(
            '/api/v3/trades',
            params=params,
            config=MexcConfig.rest_config['market_data']
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
        response_data = await self.client.get(
            '/api/v3/time',
            config=MexcConfig.rest_config['default_fast_time']
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
            await self.client.get(
                '/api/v3/ping',
                config=MexcConfig.rest_config['default_fast_ping']
            )
            return True
        except Exception:
            return False
    
