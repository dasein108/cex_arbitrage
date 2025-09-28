import time


def get_current_timestamp(self) -> int:
    """Get current timestamp in milliseconds."""
    return int(time.time() * 1000)