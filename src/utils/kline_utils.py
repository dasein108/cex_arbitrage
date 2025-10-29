from datetime import datetime, timezone
from typing import Union, Dict

from exchanges.structs.enums import KlineInterval


def get_interval_seconds(interval: KlineInterval) -> int:
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


def round_datetime_to_interval(dt: datetime, interval: Union[KlineInterval | int]) -> datetime:
    """Round datetime down to the nearest interval boundary.
    
    Examples:
        2025-10-20 10:44:55 with MINUTE_15 -> 2025-10-20 10:30:00
        2025-10-20 10:44:55 with HOUR_1 -> 2025-10-20 10:00:00
        2025-10-20 10:44:55 with MINUTE_1 -> 2025-10-20 10:44:00
        2025-10-20 10:44:55 with DAY_1 -> 2025-10-20 00:00:00
    
    Args:
        dt: The datetime to round
        interval: The KlineInterval to round to
        
    Returns:
        datetime rounded down to the nearest interval boundary
    """
    # Ensure we're working with timezone-aware datetime
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Get timestamp in seconds
    timestamp = int(dt.timestamp())
    
    # Get interval duration in seconds
    if isinstance(interval, KlineInterval):
        interval_seconds = get_interval_seconds(interval)

        # Special handling for month interval (approximate to start of month)
        if interval == KlineInterval.MONTH_1:
            return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Special handling for week interval (round to Monday 00:00)
        if interval == KlineInterval.WEEK_1:
            # Get days since Monday (0 = Monday, 6 = Sunday)
            days_since_monday = dt.weekday()
            # Calculate seconds to subtract to get to Monday 00:00
            seconds_since_monday = (days_since_monday * 86400 +
                                    dt.hour * 3600 +
                                    dt.minute * 60 +
                                    dt.second)
            rounded_timestamp = timestamp - seconds_since_monday
            return datetime.fromtimestamp(rounded_timestamp, tz=timezone.utc).replace(microsecond=0)

    else:
        interval_seconds = interval
    
    if interval_seconds == 0:
        return dt

    # Round down to nearest interval boundary
    rounded_timestamp = (timestamp // interval_seconds) * interval_seconds
    
    # Convert back to datetime
    return datetime.fromtimestamp(rounded_timestamp, tz=timezone.utc)



TIMEFRAME_MAP: Dict[str, KlineInterval] = {
    '1m': KlineInterval.MINUTE_1,
    '5m': KlineInterval.MINUTE_5,
    '15m': KlineInterval.MINUTE_15,
    '30m': KlineInterval.MINUTE_30,
    '1h': KlineInterval.HOUR_1,
    '4h': KlineInterval.HOUR_4,
    '12h': KlineInterval.HOUR_12,
    '1d': KlineInterval.DAY_1,
    '1w': KlineInterval.WEEK_1,
    '1M': KlineInterval.MONTH_1,
}

def kline_interval_to_timeframe(interval: KlineInterval) -> str:
    """
    Convert a KlineInterval to its timeframe string (reverse of `TIMEFRAME_MAP`).
    Builds the reverse map locally so it does not rely on `globals()`.
    """
    reverse_map = {v: k for k, v in TIMEFRAME_MAP.items()}
    try:
        return reverse_map[interval]
    except KeyError:
        raise ValueError(f"No timeframe string for interval: {interval!r}")
