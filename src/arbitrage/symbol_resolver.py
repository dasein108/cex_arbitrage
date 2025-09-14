"""
Symbol Resolver and Auto-Discovery System

Automatically fetches and maps symbol information from exchanges using get_exchange_info().
Eliminates need for manual configuration of symbol details.

HFT COMPLIANT: Symbol info cached at startup, no runtime API calls.
"""

import logging
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass, field

from exchanges.interface.base_exchange import BaseExchangeInterface
from exchanges.interface.structs import Symbol, SymbolInfo
from arbitrage.types import ExchangePairConfig, ArbitragePair, OpportunityType

logger = logging.getLogger(__name__)


@dataclass
class SymbolMatch:
    """Result of symbol matching across exchanges."""
    base_asset: str
    quote_asset: str
    exchanges: Dict[str, SymbolInfo] = field(default_factory=dict)
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    
    def to_exchange_configs(self) -> Dict[str, ExchangePairConfig]:
        """Convert matched symbols to exchange pair configurations."""
        configs = {}
        
        for exchange_name, symbol_info in self.exchanges.items():
            # Generate exchange-specific symbol string
            symbol_str = f"{symbol_info.symbol.base}{symbol_info.symbol.quote}"
            if exchange_name.upper() == "GATEIO":
                symbol_str = f"{symbol_info.symbol.base}_{symbol_info.symbol.quote}"
            
            configs[exchange_name] = ExchangePairConfig(
                symbol=symbol_str,
                min_amount=Decimal(str(symbol_info.min_base_amount)) if symbol_info.min_base_amount else Decimal('0.0001'),
                max_amount=Decimal('1000000'),  # Default max, exchanges rarely provide this
                min_notional=Decimal(str(symbol_info.min_quote_amount)) if symbol_info.min_quote_amount else None,
                price_precision=symbol_info.quote_precision,
                amount_precision=symbol_info.base_precision,
                maker_fee_bps=int(symbol_info.maker_commission * 10000) if symbol_info.maker_commission else 20,
                taker_fee_bps=int(symbol_info.taker_commission * 10000) if symbol_info.taker_commission else 20,
                is_active=not symbol_info.inactive
            )
        
        return configs


class SymbolResolver:
    """
    Resolves and auto-discovers symbol information from exchanges.
    
    HFT COMPLIANT: All symbol info fetched once at startup and cached.
    """
    
    def __init__(self, exchanges: Dict[str, BaseExchangeInterface]):
        self.exchanges = exchanges
        self._symbol_cache: Dict[str, Dict[Symbol, SymbolInfo]] = {}
        
        # HFT Performance Optimizations - O(1) lookup tables
        self._symbol_lookup: Dict[Tuple[str, str], Dict[str, SymbolInfo]] = {}  # (base,quote) -> {exchange: info}
        self._common_symbols_cache: Optional[List[Tuple[str, str]]] = None
        
        self._initialized = False
        
    async def initialize(self) -> None:
        """
        Fetch and cache all symbol information from exchanges.
        
        HFT COMPLIANT: One-time initialization, no runtime API calls.
        Uses the get_exchange_info() method from exchanges.
        """
        if self._initialized:
            logger.debug("Symbol resolver already initialized")
            return
            
        logger.info("Initializing symbol resolver - getting exchange symbol info...")
        
        for exchange_name, exchange in self.exchanges.items():
            try:
                if exchange and hasattr(exchange, 'symbol_info'):
                    logger.info(f"Getting symbol info from {exchange_name}...")
                    
                    # Get symbol info through standard interface property
                    symbol_info = exchange.symbol_info
                    self._symbol_cache[exchange_name] = symbol_info
                    logger.info(f"Cached {len(symbol_info)} symbols from {exchange_name}")
                else:
                    logger.warning(f"Exchange {exchange_name} has no symbol_info property")
                    self._symbol_cache[exchange_name] = {}
                    
            except Exception as e:
                logger.error(f"Failed to get symbol info from {exchange_name}: {e}")
                self._symbol_cache[exchange_name] = {}
        
        # HFT OPTIMIZATION: Build O(1) lookup tables
        self._build_performance_caches()
        
        self._initialized = True
        logger.info(f"Symbol resolver initialized with {len(self._symbol_cache)} exchanges, "
                   f"{len(self._symbol_lookup)} unique symbols, "
                   f"{len(self._common_symbols_cache or [])} common symbols")
    
    def _build_performance_caches(self) -> None:
        """
        Build O(1) lookup tables for HFT performance.
        
        HFT CRITICAL: Pre-compute all lookups to eliminate runtime complexity.
        """
        import time
        start_time = time.perf_counter()
        
        # Clear existing caches
        self._symbol_lookup.clear()
        
        # Build (base, quote) -> {exchange: SymbolInfo} lookup table
        for exchange_name, symbol_cache in self._symbol_cache.items():
            for symbol, info in symbol_cache.items():
                # Normalize key for case-insensitive O(1) lookup
                key = (symbol.base.upper(), symbol.quote.upper())
                
                if key not in self._symbol_lookup:
                    self._symbol_lookup[key] = {}
                
                self._symbol_lookup[key][exchange_name] = info
        
        # Pre-compute common symbols using optimized set operations
        self._common_symbols_cache = self._compute_common_symbols_optimized()
        
        elapsed = time.perf_counter() - start_time
        logger.info(f"HFT optimization caches built in {elapsed*1000:.2f}ms")
    
    def _compute_common_symbols_optimized(self) -> List[Tuple[str, str]]:
        """
        HFT OPTIMIZED: Pre-compute common symbols using set operations.
        
        Complexity: O(n) instead of O(n²)
        """
        if not self._symbol_lookup:
            return []
        
        # Get all symbols that appear on exactly len(exchanges) exchanges
        required_exchange_count = len([ex for ex in self.exchanges.values() if ex is not None])
        
        common_pairs = []
        for (base, quote), exchanges_info in self._symbol_lookup.items():
            # Only include active symbols
            active_exchanges = {
                ex_name: info for ex_name, info in exchanges_info.items() 
                if not info.inactive
            }
            
            if len(active_exchanges) >= required_exchange_count:
                common_pairs.append((base, quote))
        
        return sorted(common_pairs)
    
    def resolve_symbol(self, base_asset: str, quote_asset: str) -> SymbolMatch:
        """
        Resolve a trading pair across all exchanges.
        
        HFT OPTIMIZED: O(1) lookup using pre-computed hash table.
        
        Args:
            base_asset: Base asset (e.g., "BTC")
            quote_asset: Quote asset (e.g., "USDT")
            
        Returns:
            SymbolMatch with info from all exchanges that support this pair
        """
        if not self._initialized:
            raise RuntimeError("Symbol resolver not initialized - call initialize() first")
        
        match = SymbolMatch(base_asset=base_asset, quote_asset=quote_asset)
        
        # HFT CRITICAL: O(1) lookup using pre-computed hash table
        key = (base_asset.upper(), quote_asset.upper())
        exchanges_info = self._symbol_lookup.get(key, {})
        
        if exchanges_info:
            match.exchanges = exchanges_info.copy()
            logger.debug(f"Found {base_asset}/{quote_asset} on {len(exchanges_info)} exchanges: {list(exchanges_info.keys())}")
        else:
            logger.debug(f"Symbol {base_asset}/{quote_asset} not found on any exchange")
        
        # Validate we have at least 2 exchanges for arbitrage
        if len(match.exchanges) < 2:
            match.is_valid = False
            match.errors.append(
                f"Symbol {base_asset}/{quote_asset} only available on {len(match.exchanges)} exchange(s), "
                f"need at least 2 for arbitrage"
            )
        
        return match
    
    def _find_symbol(self, symbol_cache: Dict[Symbol, SymbolInfo], 
                     base_asset: str, quote_asset: str) -> Optional[SymbolInfo]:
        """
        Find a symbol in the cache for a specific exchange.
        
        Matches by base/quote assets from Symbol struct.
        """
        # Try matching by base/quote assets from Symbol struct
        for symbol, info in symbol_cache.items():
            if (symbol.base.upper() == base_asset.upper() and 
                symbol.quote.upper() == quote_asset.upper()):
                return info
        
        return None
    
    def get_common_symbols(self) -> List[Tuple[str, str]]:
        """
        Get list of symbols available on ALL exchanges.
        
        HFT OPTIMIZED: O(1) lookup using pre-computed cache.
        
        Returns:
            List of (base_asset, quote_asset) tuples
        """
        if not self._initialized:
            return []
        
        # HFT CRITICAL: Return pre-computed cache (O(1) operation)
        return self._common_symbols_cache or []
    
    async def build_arbitrage_pair(self, pair_config: Dict) -> Optional[ArbitragePair]:
        """
        Build an ArbitragePair from simplified config using auto-discovered symbol info.
        
        Args:
            pair_config: Simple config with just base/quote assets
            
        Returns:
            Fully configured ArbitragePair or None if symbol not available
        """
        base_asset = pair_config.get('base_asset')
        quote_asset = pair_config.get('quote_asset')
        
        if not base_asset or not quote_asset:
            logger.error(f"Invalid pair config: missing base_asset or quote_asset")
            return None
        
        # Resolve symbol across exchanges
        match = self.resolve_symbol(base_asset, quote_asset)
        
        if not match.is_valid:
            logger.warning(f"Cannot create arbitrage pair: {match.errors}")
            return None
        
        # Convert to exchange configs
        exchange_configs = match.to_exchange_configs()
        
        # Build ArbitragePair with auto-discovered info
        return ArbitragePair(
            id=pair_config.get('id', f"{base_asset.lower()}_{quote_asset.lower()}_arb"),
            base_asset=base_asset,
            quote_asset=quote_asset,
            exchanges=exchange_configs,
            opportunity_type=OpportunityType[pair_config.get('opportunity_type', 'SPOT_SPOT')],
            min_profit_bps=pair_config.get('min_profit_bps', 30),
            max_exposure_usd=Decimal(str(pair_config.get('max_exposure_usd', 10000))),
            is_enabled=pair_config.get('is_enabled', True),
            priority=pair_config.get('priority', 1)
        )
    
    def get_exchange_symbol(self, exchange_name: str, base_asset: str, quote_asset: str) -> Optional[str]:
        """
        Get the exchange-specific symbol string for a trading pair.
        
        HFT OPTIMIZED: O(1) lookup using pre-computed hash table.
        
        Args:
            exchange_name: Name of the exchange
            base_asset: Base asset
            quote_asset: Quote asset
            
        Returns:
            Exchange-specific symbol string (e.g., "BTCUSDT" or "BTC_USDT")
        """
        if not self._initialized:
            return None
            
        # HFT CRITICAL: O(1) lookup using pre-computed hash table
        key = (base_asset.upper(), quote_asset.upper())
        exchanges_info = self._symbol_lookup.get(key, {})
        symbol_info = exchanges_info.get(exchange_name)
        
        if symbol_info:
            # Generate exchange-specific symbol string using optimized formatter
            return self._format_exchange_symbol(exchange_name, symbol_info.symbol.base, symbol_info.symbol.quote)
        return None
    
    def _format_exchange_symbol(self, exchange_name: str, base: str, quote: str) -> str:
        """
        HFT OPTIMIZED: Fast exchange-specific symbol formatting.
        
        Uses lookup table instead of conditional logic for maximum performance.
        """
        # Static formatter lookup table for O(1) performance
        formatters = {
            "GATEIO": lambda b, q: f"{b}_{q}",
            "MEXC": lambda b, q: f"{b}{q}",
        }
        
        formatter = formatters.get(exchange_name.upper())
        if formatter:
            return formatter(base, quote)
        
        # Default format for unknown exchanges
        return f"{base}{quote}"