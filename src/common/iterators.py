"""
Time Range Iterator Utilities

Provides flexible time range iteration helpers for batch data fetching.
These iterators can be used for various data types (klines, trades, etc.)
and work with or without specific timeframe intervals.

Key Features:
- Multiple iteration strategies (simple, adaptive)
- Works without timeframe for general time-based pagination
- Configurable chunk sizes and overlap handling
- Support for sparse data scenarios
- Performance optimized for HFT requirements
"""

from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Iterator, Generator
from enum import Enum

from structs.common import KlineInterval
from core.cex.utils import get_interval_seconds


class IteratorStrategy(Enum):
    """
    Available time range iteration strategies.
    """
    SIMPLE = "simple"      # Fixed chunk sizes, forward iteration
    ADAPTIVE = "adaptive"  # Dynamic chunk sizes, adjusts to data availability
    

def time_range_iterator_simple(
    date_from: datetime, 
    date_to: datetime, 
    limit: int,
    interval_seconds: Optional[int] = None
) -> Generator[Tuple[datetime, datetime], None, None]:
    """
    Simple forward iteration with fixed chunk size.
    
    Creates time ranges by moving forward from start to end with fixed-size chunks.
    Most straightforward implementation similar to range().
    
    Args:
        date_from: Start datetime
        date_to: End datetime  
        limit: Number of items per chunk (e.g., 500 for klines, 1000 for trades)
        interval_seconds: Optional seconds between items (e.g., 60 for 1m klines)
                         If not provided, divides time range equally
        
    Yields:
        Tuple of (chunk_start, chunk_end) for each time range
        
    Example:
        # For klines with known interval
        for start, end in time_range_iterator_simple(date_from, date_to, 500, 60):
            klines = await get_klines(start, end)
            
        # For trades without specific interval
        for start, end in time_range_iterator_simple(date_from, date_to, 1000):
            trades = await get_trades(start, end)
    """
    if not interval_seconds:
        # No interval specified - divide time range into chunks based on limit
        # Assume we want roughly 'limit' chunks
        total_seconds = int((date_to - date_from).total_seconds())
        if total_seconds <= 0:
            return
        
        # Calculate chunk duration to get approximately 'limit' items per chunk
        # This is a heuristic - adjust based on actual data density
        chunk_seconds = max(1, total_seconds // max(1, limit // 10))
    else:
        # Calculate chunk duration based on interval and limit
        chunk_seconds = limit * interval_seconds
    
    current_start = date_from
    
    while current_start < date_to:
        # Calculate chunk end, ensuring we don't exceed date_to
        chunk_end_timestamp = min(
            current_start.timestamp() + chunk_seconds, 
            date_to.timestamp()
        )
        chunk_end = datetime.fromtimestamp(chunk_end_timestamp)
        
        yield (current_start, chunk_end)
        
        # Move to next chunk
        if interval_seconds:
            # Use interval for precise stepping (avoid gaps/overlaps)
            current_start = datetime.fromtimestamp(chunk_end.timestamp() + interval_seconds)
        else:
            # Use 1 second offset to avoid overlap for non-interval data
            current_start = datetime.fromtimestamp(chunk_end.timestamp() + 1)
        
        # Stop if we've passed the end
        if current_start >= date_to:
            break


def time_range_iterator_adaptive(
    date_from: datetime,
    date_to: datetime,
    limit: int,
    interval_seconds: Optional[int] = None,
    min_chunk_size: Optional[int] = None,
    max_chunk_size: Optional[int] = None
) -> Generator[Tuple[datetime, datetime], None, None]:
    """
    Adaptive iteration that adjusts chunk sizes based on remaining time.
    
    Each iteration can be adjusted based on the remaining time range.
    Supports dynamic adjustment for sparse data or varying data density.
    
    Args:
        date_from: Start datetime
        date_to: End datetime
        limit: Target number of items per chunk
        interval_seconds: Optional seconds between items
        min_chunk_size: Minimum items per chunk (default: limit // 4)
        max_chunk_size: Maximum items per chunk (default: limit * 2)
        
    Yields:
        Tuple of (chunk_start, chunk_end) for each time range
        
    Example:
        # Adaptive iteration for sparse historical data
        for start, end in time_range_iterator_adaptive(date_from, date_to, 500):
            data = await fetch_data(start, end)
            if len(data) < 100:  # Sparse data
                # Next iteration will automatically use remaining time
                pass
    """
    if min_chunk_size is None:
        min_chunk_size = max(1, limit // 4)
    if max_chunk_size is None:
        max_chunk_size = limit * 2
    
    if not interval_seconds:
        # Estimate based on total time range
        total_seconds = int((date_to - date_from).total_seconds())
        if total_seconds <= 0:
            return
        
        # Start with conservative chunk size for unknown data density
        chunk_seconds = max(60, total_seconds // max(1, limit // 5))
    else:
        # Calculate based on interval
        chunk_seconds = limit * interval_seconds
    
    current_start = date_from
    
    while current_start < date_to:
        remaining_seconds = int((date_to - current_start).total_seconds())
        
        # Adaptive logic: adjust chunk size based on remaining time
        if remaining_seconds < chunk_seconds:
            # Last chunk - take everything remaining
            chunk_end = date_to
        else:
            # Calculate adaptive chunk size
            # Reduce chunk size as we approach the end for better granularity
            if remaining_seconds < chunk_seconds * 3:
                # Near the end - use smaller chunks
                adjusted_chunk_seconds = max(
                    chunk_seconds // 2,
                    (min_chunk_size * interval_seconds) if interval_seconds else 60
                )
            else:
                # Normal chunk
                adjusted_chunk_seconds = chunk_seconds
            
            chunk_end_timestamp = min(
                current_start.timestamp() + adjusted_chunk_seconds,
                date_to.timestamp()
            )
            chunk_end = datetime.fromtimestamp(chunk_end_timestamp)
        
        yield (current_start, chunk_end)
        
        # Move to next chunk with appropriate stepping
        if interval_seconds:
            # Use interval for precise stepping
            next_start = chunk_end.timestamp() + interval_seconds
        else:
            # For non-interval data, use small offset to prevent overlap
            # but not too large to avoid gaps
            next_start = chunk_end.timestamp() + 1
        
        current_start = datetime.fromtimestamp(next_start)
        
        # Early exit if next chunk would be too small
        if interval_seconds and (date_to.timestamp() - current_start.timestamp()) < interval_seconds:
            break


def choose_iterator(
    date_from: datetime,
    date_to: datetime,
    limit: int,
    interval: Optional[KlineInterval] = None,
    strategy: IteratorStrategy = IteratorStrategy.ADAPTIVE,
    **kwargs
) -> Generator[Tuple[datetime, datetime], None, None]:
    """
    Choose the best iterator based on parameters and strategy.
    
    This is a convenience function that selects the appropriate iterator
    based on the provided strategy and converts KlineInterval to seconds.
    
    Args:
        date_from: Start datetime
        date_to: End datetime
        limit: Number of items per chunk
        interval: Optional KlineInterval for klines (auto-converts to seconds)
        strategy: Which iteration strategy to use
        **kwargs: Additional arguments passed to the specific iterator
        
    Yields:
        Tuple of (chunk_start, chunk_end) for each time range
        
    Example:
        # For klines with automatic interval conversion
        for start, end in choose_iterator(date_from, date_to, 500, KlineInterval.MINUTE_1):
            klines = await get_klines(start, end)
            
        # For trades without interval
        for start, end in choose_iterator(date_from, date_to, 1000, strategy=IteratorStrategy.SIMPLE):
            trades = await get_trades(start, end)
    """
    # Convert KlineInterval to seconds if provided
    interval_seconds = None
    if interval:
        interval_seconds = get_interval_seconds(interval)
        if interval_seconds == 0:
            # Fallback for unknown intervals
            interval_seconds = 60
    
    # Select iterator based on strategy
    if strategy == IteratorStrategy.SIMPLE:
        yield from time_range_iterator_simple(
            date_from, date_to, limit, interval_seconds
        )
    elif strategy == IteratorStrategy.ADAPTIVE:
        yield from time_range_iterator_adaptive(
            date_from, date_to, limit, interval_seconds, **kwargs
        )
    else:
        # Default to adaptive
        yield from time_range_iterator_adaptive(
            date_from, date_to, limit, interval_seconds, **kwargs
        )


def calculate_optimal_chunk_size(
    date_from: datetime,
    date_to: datetime,
    max_items_per_request: int,
    estimated_data_density: Optional[float] = None,
    interval_seconds: Optional[int] = None
) -> int:
    """
    Calculate optimal chunk size based on time range and data characteristics.
    
    This helper function determines the best chunk size to use for iteration
    based on the total time range and estimated data density.
    
    Args:
        date_from: Start datetime
        date_to: End datetime
        max_items_per_request: Maximum items the API allows per request
        estimated_data_density: Items per second (e.g., 0.016 for 1-minute klines)
        interval_seconds: Known interval between items
        
    Returns:
        Optimal chunk size (number of items per request)
        
    Example:
        # For klines with known 1-minute interval
        chunk_size = calculate_optimal_chunk_size(
            date_from, date_to, 1000, interval_seconds=60
        )
        
        # For trades with estimated density
        chunk_size = calculate_optimal_chunk_size(
            date_from, date_to, 1000, estimated_data_density=10.0  # 10 trades per second
        )
    """
    total_seconds = int((date_to - date_from).total_seconds())
    
    if interval_seconds:
        # Known interval - calculate exact number of items
        total_items = total_seconds // interval_seconds
        
        # Use 80% of max to leave some headroom
        optimal_size = min(int(max_items_per_request * 0.8), total_items)
        
        # But not too small
        return max(10, optimal_size)
    
    elif estimated_data_density:
        # Estimate based on data density
        estimated_total_items = int(total_seconds * estimated_data_density)
        
        if estimated_total_items <= max_items_per_request:
            # Can fetch in one request
            return max_items_per_request
        
        # Calculate number of requests needed
        num_requests = (estimated_total_items + max_items_per_request - 1) // max_items_per_request
        
        # Distribute evenly across requests
        return min(max_items_per_request, max(10, estimated_total_items // num_requests))
    
    else:
        # No information - use conservative default
        # Assume we want roughly 10-20 requests for the range
        if total_seconds < 3600:  # Less than 1 hour
            return min(100, max_items_per_request)
        elif total_seconds < 86400:  # Less than 1 day
            return min(500, max_items_per_request)
        else:  # Multiple days
            return max_items_per_request


# Convenience functions for specific use cases

def kline_iterator(
    date_from: datetime,
    date_to: datetime,
    interval: KlineInterval,
    chunk_size: int = 500,
    strategy: IteratorStrategy = IteratorStrategy.ADAPTIVE
) -> Generator[Tuple[datetime, datetime], None, None]:
    """
    Specialized iterator for kline/candlestick data.
    
    Automatically handles interval conversion and optimal chunk sizing for klines.
    """
    yield from choose_iterator(date_from, date_to, chunk_size, interval, strategy)


def trade_iterator(
    date_from: datetime,
    date_to: datetime,
    chunk_size: int = 1000,
    estimated_trades_per_second: float = 1.0,
    strategy: IteratorStrategy = IteratorStrategy.ADAPTIVE
) -> Generator[Tuple[datetime, datetime], None, None]:
    """
    Specialized iterator for trade data.
    
    Optimized for trade data which typically has variable density.
    """
    # Calculate interval estimate based on trade density
    interval_estimate = int(1.0 / estimated_trades_per_second) if estimated_trades_per_second > 0 else None
    
    yield from choose_iterator(date_from, date_to, chunk_size, None, strategy)