"""
Time Range Iterator Utilities

Simple time range iteration for batch data fetching with mandatory parameters.
Optimized for HFT performance with minimal complexity.
"""

from datetime import datetime
from typing import Tuple, Generator
from core.structs.common import KlineInterval
from core.exchanges.utils.kline_utils import get_interval_seconds

def time_range_iterator(
    date_from: datetime, 
    date_to: datetime, 
    limit: int,
    interval: KlineInterval
) -> Generator[Tuple[datetime, datetime], None, None]:
    """
    Simple time range iterator with fixed chunk size.
    
    Creates time ranges by moving forward from start to end with fixed-size chunks
    based on interval and limit.
    
    Args:
        date_from: Start datetime (mandatory)
        date_to: End datetime (mandatory)  
        limit: Number of items per chunk (mandatory)
        interval: Kline interval to determine chunk size (mandatory)

    Yields:
        Tuple of (chunk_start, chunk_end) for each time range
        
    Example:
        # For 1-minute klines with 500 items per chunk
        for start, end in time_range_iterator(date_from, date_to, 500, 60):
            klines = await get_klines(start, end)
    """

    interval_seconds = get_interval_seconds(interval)

    # Validate inputs
    if date_from >= date_to:
        return
    
    if limit <= 0 or interval_seconds <= 0:
        raise ValueError("limit and interval_seconds must be positive")
    
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
        
        yield current_start, chunk_end
        
        # Move to next chunk with precise stepping to avoid gaps/overlaps
        current_start = datetime.fromtimestamp(chunk_end.timestamp() + interval_seconds)
        
        # Stop if we've passed the end
        if current_start >= date_to:
            break