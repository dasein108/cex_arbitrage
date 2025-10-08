"""
Multi-Symbol Data Fetcher

High-performance data retrieval for arbitrage analytics across any trading symbol.
Provides real-time and historical book_ticker data across configurable exchanges
with support for spot and futures markets.

Optimized for HFT requirements with sub-10ms query latency.
"""

import sys
from pathlib import Path

# Add src to path for imports when running from anywhere
current_dir = Path(__file__).parent  # /Users/dasein/dev/cex_arbitrage/src/applications/tools/
project_root = current_dir.parent.parent.parent  # /Users/dasein/dev/cex_arbitrage/
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
import asyncio
import logging
from collections import defaultdict

import msgspec

# Direct imports from src (we're already in the src tree)
from db.connection import get_db_manager
from db.models import BookTickerSnapshot
from db.symbol_manager import get_symbol_id
from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName

logger = logging.getLogger(__name__)


class UnifiedSnapshot(msgspec.Struct):
    """
    Unified snapshot across multiple exchanges for any symbol.
    
    Optimized for cross-exchange spread analysis with zero-copy serialization.
    """
    symbol: str  # e.g., "NEIROETH/USDT"
    timestamp: datetime
    
    # Gate.io Spot data
    gateio_spot_bid: Optional[float] = None
    gateio_spot_ask: Optional[float] = None
    gateio_spot_bid_qty: Optional[float] = None
    gateio_spot_ask_qty: Optional[float] = None
    
    # Gate.io Futures data
    gateio_futures_bid: Optional[float] = None
    gateio_futures_ask: Optional[float] = None
    gateio_futures_bid_qty: Optional[float] = None
    gateio_futures_ask_qty: Optional[float] = None
    
    # MEXC Spot data
    mexc_spot_bid: Optional[float] = None
    mexc_spot_ask: Optional[float] = None
    mexc_spot_bid_qty: Optional[float] = None
    mexc_spot_ask_qty: Optional[float] = None
    
    def get_spreads(self) -> Dict[str, float]:
        """Calculate bid-ask spreads for each exchange."""
        spreads = {}
        
        if self.gateio_spot_bid and self.gateio_spot_ask:
            spreads['gateio_spot'] = self.gateio_spot_ask - self.gateio_spot_bid
            
        if self.gateio_futures_bid and self.gateio_futures_ask:
            spreads['gateio_futures'] = self.gateio_futures_ask - self.gateio_futures_bid
            
        if self.mexc_spot_bid and self.mexc_spot_ask:
            spreads['mexc_spot'] = self.mexc_spot_ask - self.mexc_spot_bid
            
        return spreads
    
    def get_cross_exchange_spreads(self) -> Dict[str, float]:
        """Calculate arbitrage spreads between exchanges."""
        spreads = {}
        
        # Gate.io Spot vs MEXC Spot arbitrage
        if (self.gateio_spot_bid and self.mexc_spot_ask and 
            self.mexc_spot_bid and self.gateio_spot_ask):
            # Sell Gate.io, Buy MEXC (when Gate.io higher)
            spreads['gateio_mexc_sell_buy'] = self.gateio_spot_bid - self.mexc_spot_ask
            # Buy Gate.io, Sell MEXC (when MEXC higher)  
            spreads['mexc_gateio_sell_buy'] = self.mexc_spot_bid - self.gateio_spot_ask
            
        # Gate.io Spot vs Gate.io Futures delta neutral
        if (self.gateio_spot_bid and self.gateio_futures_ask and
            self.gateio_futures_bid and self.gateio_spot_ask):
            # Long Spot, Short Futures
            spreads['spot_futures_long_short'] = self.gateio_spot_bid - self.gateio_futures_ask
            # Short Spot, Long Futures
            spreads['futures_spot_long_short'] = self.gateio_futures_bid - self.gateio_spot_ask
            
        return spreads
    
    def is_complete(self) -> bool:
        """Check if all exchange data is available."""
        return all([
            self.gateio_spot_bid, self.gateio_spot_ask,
            self.gateio_futures_bid, self.gateio_futures_ask,
            self.mexc_spot_bid, self.mexc_spot_ask
        ])


class MultiSymbolDataFetcher:
    """
    High-performance data fetcher for arbitrage analytics across any symbol.
    
    Manages symbol IDs, provides optimized queries, and caches static data
    while ensuring no real-time data caching (HFT safety compliance).
    """
    
    # Default exchange configuration (can be customized)
    DEFAULT_EXCHANGES = {
        'GATEIO_SPOT': 'GATEIO_SPOT',
        'GATEIO_FUTURES': 'GATEIO_FUTURES', 
        'MEXC_SPOT': 'MEXC_SPOT'
    }
    
    def __init__(self, symbol: Symbol, exchanges: Optional[Dict[str, str]] = None):
        """
        Initialize data fetcher for a specific symbol and exchanges.
        
        Args:
            symbol: Symbol object (base/quote pair)
            exchanges: Dictionary mapping exchange keys to exchange names
                      Defaults to GATEIO_SPOT, GATEIO_FUTURES, MEXC_SPOT
        """
        self.symbol = symbol
        self.exchanges = exchanges or self.DEFAULT_EXCHANGES
        self.symbol_str = f"{symbol.base}/{symbol.quote}"
        
        self.logger = logger.getChild(f"DataFetcher_{symbol.base}_{symbol.quote}")
        self._symbol_ids: Dict[str, Optional[int]] = {}
        self._initialized = False
    
    async def initialize(self) -> bool:
        """
        Initialize database connection and symbol IDs for all exchanges.
        
        Returns:
            True if all symbols initialized successfully
        """
        if self._initialized:
            return True
            
        self.logger.info(f"Initializing database and {self.symbol_str} symbol IDs...")
        
        try:
            # Initialize database connection using config manager pattern
            from config.config_manager import HftConfig
            from db.connection import get_db_manager
            
            # Load configuration
            config_manager = HftConfig()
            db_config = config_manager.get_database_config()
            
            # Initialize database manager
            db_manager = get_db_manager()
            if not db_manager.is_initialized:
                await db_manager.initialize(db_config)
                self.logger.info("Database connection pool initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            return False
        
        # Initialize symbol IDs for all exchanges
        success = True
        for exchange_key, exchange_name in self.exchanges.items():
            symbol_id = await get_symbol_id(exchange_name, self.symbol)
            if symbol_id:
                self._symbol_ids[exchange_key] = symbol_id
                self.logger.debug(f"✓ {exchange_name}: symbol_id={symbol_id}")
            else:
                self.logger.error(f"✗ Failed to get symbol_id for {exchange_name}")
                success = False
                
        self._initialized = success
        
        if success:
            self.logger.info(f"✅ Initialized {len(self._symbol_ids)} {self.symbol_str} symbols")
        else:
            self.logger.error(f"❌ Failed to initialize all {self.symbol_str} symbols")
            
        return success
    
    async def get_latest_snapshots(self) -> Optional[UnifiedSnapshot]:
        """
        Get latest book_ticker snapshots for all configured exchanges.
        
        Returns:
            Unified snapshot with latest data or None if failed
        """
        if not self._initialized:
            await self.initialize()
        
        if not all(self._symbol_ids.values()):
            self.logger.error("Not all symbol IDs available")
            return None
            
        db = get_db_manager()
        
        # Single query to get latest data for all symbols
        query = """
            SELECT DISTINCT ON (symbol_id)
                   symbol_id, bid_price, bid_qty, ask_price, ask_qty, timestamp
            FROM book_ticker_snapshots
            WHERE symbol_id = ANY($1)
            ORDER BY symbol_id, timestamp DESC
        """
        
        try:
            symbol_id_list = list(self._symbol_ids.values())
            rows = await db.fetch(query, symbol_id_list)
            
            if not rows:
                self.logger.warning(f"No recent snapshots found for {self.symbol_str}")
                return None
            
            # Map results by symbol_id
            results = {row['symbol_id']: row for row in rows}
            
            # Find the most recent timestamp across all exchanges
            latest_timestamp = max(row['timestamp'] for row in rows)
            
            # Build unified snapshot
            snapshot = UnifiedSnapshot(symbol=self.symbol_str, timestamp=latest_timestamp)
            
            # Map data by exchange
            for exchange_key, symbol_id in self._symbol_ids.items():
                if symbol_id in results:
                    row = results[symbol_id]
                    
                    if exchange_key == 'GATEIO_SPOT':
                        snapshot.gateio_spot_bid = float(row['bid_price'])
                        snapshot.gateio_spot_ask = float(row['ask_price'])
                        snapshot.gateio_spot_bid_qty = float(row['bid_qty'])
                        snapshot.gateio_spot_ask_qty = float(row['ask_qty'])
                        
                    elif exchange_key == 'GATEIO_FUTURES':
                        snapshot.gateio_futures_bid = float(row['bid_price'])
                        snapshot.gateio_futures_ask = float(row['ask_price'])
                        snapshot.gateio_futures_bid_qty = float(row['bid_qty'])
                        snapshot.gateio_futures_ask_qty = float(row['ask_qty'])
                        
                    elif exchange_key == 'MEXC_SPOT':
                        snapshot.mexc_spot_bid = float(row['bid_price'])
                        snapshot.mexc_spot_ask = float(row['ask_price'])
                        snapshot.mexc_spot_bid_qty = float(row['bid_qty'])
                        snapshot.mexc_spot_ask_qty = float(row['ask_qty'])
            
            self.logger.debug(f"Retrieved latest {self.symbol_str} snapshots at {latest_timestamp}")
            return snapshot
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve latest snapshots: {e}")
            return None
    
    async def get_historical_snapshots(
        self,
        hours_back: int = 24,
        sample_interval_minutes: int = 1
    ) -> List[UnifiedSnapshot]:
        """
        Get historical snapshots for arbitrage analysis.
        
        Args:
            hours_back: How many hours of history to retrieve
            sample_interval_minutes: Sampling interval for downsampling
            
        Returns:
            List of UnifiedSnapshot objects ordered by timestamp
        """
        if not self._initialized:
            await self.initialize()
            
        if not all(self._symbol_ids.values()):
            self.logger.error("Not all symbol IDs available for historical query")
            return []
            
        db = get_db_manager()
        timestamp_from = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        # Query with time-based sampling for all symbols
        query = """
            WITH sampled_data AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY 
                               symbol_id,
                               EXTRACT(EPOCH FROM DATE_TRUNC('minute', timestamp))::bigint / ($2 * 60)
                           ORDER BY timestamp DESC
                       ) as rn
                FROM book_ticker_snapshots
                WHERE symbol_id = ANY($1) 
                  AND timestamp >= $3
            )
            SELECT symbol_id, bid_price, bid_qty, ask_price, ask_qty, timestamp
            FROM sampled_data
            WHERE rn = 1
            ORDER BY timestamp ASC
        """
        
        try:
            symbol_id_list = list(self._symbol_ids.values())
            rows = await db.fetch(query, symbol_id_list, sample_interval_minutes, timestamp_from)
            
            if not rows:
                self.logger.warning(f"No historical data found for {self.symbol_str} ({hours_back}h)")
                return []
            
            # Group by timestamp and create unified snapshots
            snapshots_by_time: Dict[datetime, Dict[int, dict]] = defaultdict(dict)
            
            for row in rows:
                timestamp = row['timestamp']
                symbol_id = row['symbol_id']
                snapshots_by_time[timestamp][symbol_id] = row
            
            # Build unified snapshots
            unified_snapshots = []
            
            for timestamp, symbol_data in sorted(snapshots_by_time.items()):
                snapshot = UnifiedSnapshot(symbol=self.symbol_str, timestamp=timestamp)
                
                # Map data by exchange using symbol_id lookup
                for exchange_key, symbol_id in self._symbol_ids.items():
                    if symbol_id in symbol_data:
                        row = symbol_data[symbol_id]
                        
                        if exchange_key == 'GATEIO_SPOT':
                            snapshot.gateio_spot_bid = float(row['bid_price'])
                            snapshot.gateio_spot_ask = float(row['ask_price'])
                            snapshot.gateio_spot_bid_qty = float(row['bid_qty'])
                            snapshot.gateio_spot_ask_qty = float(row['ask_qty'])
                            
                        elif exchange_key == 'GATEIO_FUTURES':
                            snapshot.gateio_futures_bid = float(row['bid_price'])
                            snapshot.gateio_futures_ask = float(row['ask_price'])
                            snapshot.gateio_futures_bid_qty = float(row['bid_qty'])
                            snapshot.gateio_futures_ask_qty = float(row['ask_qty'])
                            
                        elif exchange_key == 'MEXC_SPOT':
                            snapshot.mexc_spot_bid = float(row['bid_price'])
                            snapshot.mexc_spot_ask = float(row['ask_price'])
                            snapshot.mexc_spot_bid_qty = float(row['bid_qty'])
                            snapshot.mexc_spot_ask_qty = float(row['ask_qty'])
                
                unified_snapshots.append(snapshot)
            
            self.logger.info(f"Retrieved {len(unified_snapshots)} historical {self.symbol_str} snapshots ({hours_back}h)")
            return unified_snapshots
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve historical snapshots: {e}")
            return []
    
    async def get_exchange_snapshots(
        self, 
        exchange_key: str,
        hours_back: int = 1
    ) -> List[BookTickerSnapshot]:
        """
        Get historical snapshots for a specific exchange.
        
        Args:
            exchange_key: Exchange key ('GATEIO_SPOT', 'GATEIO_FUTURES', 'MEXC_SPOT')
            hours_back: Hours of history to retrieve
            
        Returns:
            List of BookTickerSnapshot objects for the exchange
        """
        if not self._initialized:
            await self.initialize()
            
        if exchange_key not in self._symbol_ids:
            self.logger.error(f"Unknown exchange key: {exchange_key}")
            return []
            
        symbol_id = self._symbol_ids[exchange_key]
        if not symbol_id:
            self.logger.error(f"No symbol_id for exchange: {exchange_key}")
            return []
            
        db = get_db_manager()
        timestamp_from = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        query = """
            SELECT symbol_id, bid_price, bid_qty, ask_price, ask_qty, timestamp, created_at, id
            FROM book_ticker_snapshots
            WHERE symbol_id = $1 AND timestamp >= $2
            ORDER BY timestamp DESC
            LIMIT 10000
        """
        
        try:
            rows = await db.fetch(query, symbol_id, timestamp_from)
            
            snapshots = []
            for row in rows:
                snapshot = BookTickerSnapshot(
                    symbol_id=row['symbol_id'],
                    bid_price=float(row['bid_price']),
                    bid_qty=float(row['bid_qty']),
                    ask_price=float(row['ask_price']),
                    ask_qty=float(row['ask_qty']),
                    timestamp=row['timestamp'],
                    created_at=row['created_at'],
                    id=row['id'],
                    # Add transient fields for convenience
                    exchange=self.exchanges[exchange_key],
                    symbol_base=str(self.symbol.base),
                    symbol_quote=str(self.symbol.quote)
                )
                snapshots.append(snapshot)
            
            self.logger.debug(f"Retrieved {len(snapshots)} snapshots for {exchange_key}")
            return snapshots
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve {exchange_key} snapshots: {e}")
            return []
    
    def get_symbol_ids(self) -> Dict[str, Optional[int]]:
        """
        Get cached symbol IDs for all exchanges.
        
        Returns:
            Dictionary mapping exchange keys to symbol IDs
        """
        return self._symbol_ids.copy()
    
    async def health_check(self) -> Dict[str, any]:
        """
        Perform health check on data availability.
        
        Returns:
            Health status dictionary
        """
        if not self._initialized:
            await self.initialize()
            
        latest = await self.get_latest_snapshots()
        
        return {
            'initialized': self._initialized,
            'symbol_ids_available': len([sid for sid in self._symbol_ids.values() if sid]),
            'total_exchanges': len(self.DEFAULT_EXCHANGES),
            'latest_data_available': latest is not None,
            'latest_complete': latest.is_complete() if latest else False,
            'latest_timestamp': latest.timestamp if latest else None,
            'symbol_ids': self._symbol_ids
        }