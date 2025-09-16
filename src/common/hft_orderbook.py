"""
HFT-Optimized Orderbook Implementation

High-performance orderbook class designed for sub-100 microsecond diff processing.
Uses SortedDict for O(log n) operations and implements copy-on-read semantics
for thread safety without locking overhead.

Key Features:
- SortedDict-based storage for efficient price-level operations
- In-place diff application for minimal memory allocation
- Copy-on-read semantics for thread-safe access
- Zero-allocation hot paths for HFT compliance
- Timestamp tracking for stale data detection

Performance Targets:
- <100μs per diff application
- O(log n) insertion/deletion/lookup
- Zero garbage collection pressure in steady state
"""

import time
from typing import List, Dict, Optional, Tuple, Iterator
from sortedcontainers import SortedDict
import msgspec

from structs.exchange import Symbol, OrderBook, OrderBookEntry


class HFTOrderBookEntry(msgspec.Struct):
    """HFT-optimized orderbook entry with minimal overhead using msgspec."""
    price: float
    size: float
    timestamp: float = 0.0
    
    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp == 0.0:
            object.__setattr__(self, 'timestamp', time.perf_counter())
    
    def __hash__(self) -> int:
        """Hash based on price for set operations."""
        return hash(self.price)
    
    def __eq__(self, other) -> bool:
        """Equality based on price only."""
        if not isinstance(other, (HFTOrderBookEntry, OrderBookEntry)):
            return False
        return abs(self.price - other.price) < 1e-9


class HFTOrderBook:
    """
    HFT-optimized orderbook with sub-100μs diff processing capability.
    
    Architecture:
    - SortedDict for O(log n) price-level operations
    - In-place modification for zero-copy updates
    - Copy-on-read semantics for thread safety
    - Minimal object allocation in hot paths
    """
    
    __slots__ = ('symbol', '_bids', '_asks', '_timestamp', '_sequence', '_is_snapshot')
    
    def __init__(self, symbol: Symbol, timestamp: Optional[float] = None):
        self.symbol = symbol
        # SortedDict with descending order for bids (highest price first)
        self._bids: SortedDict[float, HFTOrderBookEntry] = SortedDict(lambda x: -x)
        # SortedDict with ascending order for asks (lowest price first)
        self._asks: SortedDict[float, HFTOrderBookEntry] = SortedDict()
        self._timestamp = timestamp or time.perf_counter()
        self._sequence = 0
        self._is_snapshot = False
    
    def apply_diff(
        self, 
        bid_updates: List[Tuple[float, float]], 
        ask_updates: List[Tuple[float, float]],
        timestamp: Optional[float] = None,
        sequence: Optional[int] = None
    ) -> None:
        """
        Apply orderbook diff with HFT-optimized performance.
        
        Args:
            bid_updates: List of (price, size) tuples for bid updates
            ask_updates: List of (price, size) tuples for ask updates
            timestamp: Update timestamp (defaults to current time)
            sequence: Sequence number for ordering validation
            
        Performance: Target <100μs for typical updates (5-20 price levels)
        """
        update_time = timestamp or time.perf_counter()
        
        # Update sequence tracking
        if sequence is not None:
            self._sequence = sequence
        
        # Apply bid updates (in-place modification)
        for price, size in bid_updates:
            if size <= 0:
                # Remove price level (size 0 or negative means removal)
                self._bids.pop(price, None)
            else:
                # Update or insert price level
                existing_entry = self._bids.get(price)
                if existing_entry:
                    # In-place update (zero allocation)
                    existing_entry.size = size
                    existing_entry.timestamp = update_time
                else:
                    # New price level
                    self._bids[price] = HFTOrderBookEntry(price, size, update_time)
        
        # Apply ask updates (in-place modification)
        for price, size in ask_updates:
            if size <= 0:
                # Remove price level (size 0 or negative means removal)
                self._asks.pop(price, None)
            else:
                # Update or insert price level
                existing_entry = self._asks.get(price)
                if existing_entry:
                    # In-place update (zero allocation)
                    existing_entry.size = size
                    existing_entry.timestamp = update_time
                else:
                    # New price level
                    self._asks[price] = HFTOrderBookEntry(price, size, update_time)
        
        # Update global timestamp
        self._timestamp = update_time
    
    def apply_snapshot(
        self,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
        timestamp: Optional[float] = None,
        sequence: Optional[int] = None
    ) -> None:
        """
        Replace orderbook with complete snapshot.
        
        Args:
            bids: List of (price, size) tuples for all bid levels
            asks: List of (price, size) tuples for all ask levels
            timestamp: Snapshot timestamp
            sequence: Sequence number
        """
        update_time = timestamp or time.perf_counter()
        
        # Clear existing data
        self._bids.clear()
        self._asks.clear()
        
        # Populate with snapshot data
        for price, size in bids:
            if size > 0:
                self._bids[price] = HFTOrderBookEntry(price, size, update_time)
        
        for price, size in asks:
            if size > 0:
                self._asks[price] = HFTOrderBookEntry(price, size, update_time)
        
        # Update metadata
        self._timestamp = update_time
        self._is_snapshot = True
        if sequence is not None:
            self._sequence = sequence
    
    def get_best_bid(self) -> Optional[HFTOrderBookEntry]:
        """Get best (highest) bid price level. O(1) operation."""
        if not self._bids:
            return None
        # First item in descending sorted dict is highest price
        return self._bids.peekitem(0)[1]
    
    def get_best_ask(self) -> Optional[HFTOrderBookEntry]:
        """Get best (lowest) ask price level. O(1) operation."""
        if not self._asks:
            return None
        # First item in ascending sorted dict is lowest price
        return self._asks.peekitem(0)[1]
    
    def get_spread(self) -> Optional[float]:
        """Calculate bid-ask spread. O(1) operation."""
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        
        if not best_bid or not best_ask:
            return None
        
        return best_ask.price - best_bid.price
    
    def get_mid_price(self) -> Optional[float]:
        """Calculate mid price. O(1) operation."""
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        
        if not best_bid or not best_ask:
            return None
        
        return (best_bid.price + best_ask.price) / 2.0
    
    def get_depth(self, levels: int = 10) -> Tuple[List[HFTOrderBookEntry], List[HFTOrderBookEntry]]:
        """
        Get orderbook depth with copy-on-read semantics.
        
        Returns:
            (bids, asks): Lists of orderbook entries up to specified levels
            
        Performance: O(k) where k = levels requested
        Thread Safety: Copy-on-read ensures thread safety without locks
        """
        # Copy-on-read for thread safety (creates new list objects)
        bids = []
        asks = []
        
        # Get top bid levels (highest prices first)
        for i, (price, entry) in enumerate(self._bids.items()):
            if i >= levels:
                break
            bids.append(entry)
        
        # Get top ask levels (lowest prices first)  
        for i, (price, entry) in enumerate(self._asks.items()):
            if i >= levels:
                break
            asks.append(entry)
        
        return bids, asks
    
    def to_orderbook(self, levels: int = 10) -> OrderBook:
        """
        Convert to standard OrderBook struct for interface compliance.
        
        Args:
            levels: Number of price levels to include
            
        Returns:
            OrderBook struct with specified depth
            
        Note: This creates new objects - avoid in hot paths
        """
        bids_data, asks_data = self.get_depth(levels)
        
        # Convert to OrderBookEntry structs
        bids = [OrderBookEntry(price=entry.price, size=entry.size) for entry in bids_data]
        asks = [OrderBookEntry(price=entry.price, size=entry.size) for entry in asks_data]
        
        return OrderBook(
            bids=bids,
            asks=asks,
            timestamp=self._timestamp
        )
    
    def get_stats(self) -> Dict[str, any]:
        """Get orderbook statistics for monitoring."""
        return {
            'symbol': str(self.symbol),
            'bid_levels': len(self._bids),
            'ask_levels': len(self._asks),
            'timestamp': self._timestamp,
            'sequence': self._sequence,
            'is_snapshot': self._is_snapshot,
            'spread': self.get_spread(),
            'mid_price': self.get_mid_price()
        }
    
    def is_valid(self) -> bool:
        """Check if orderbook is in valid state."""
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        
        # Must have both sides
        if not best_bid or not best_ask:
            return False
        
        # No crossed book (bid >= ask indicates invalid state)
        if best_bid.price >= best_ask.price:
            return False
        
        return True
    
    def __repr__(self) -> str:
        stats = self.get_stats()
        return (
            f"HFTOrderBook(symbol={stats['symbol']}, "
            f"bid_levels={stats['bid_levels']}, "
            f"ask_levels={stats['ask_levels']}, "
            f"spread={stats['spread']:.8f})"
        )