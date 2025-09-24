from infrastructure.data_structures.common import KlineInterval


def get_interval_seconds(self, interval: KlineInterval) -> int:
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