from enum import Enum
from typing import Dict, Optional
import msgspec

class HTTPMethod(Enum):
    """HTTP methods with performance-optimized string values."""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class RestConfig(msgspec.Struct):
    """Ultra-simple configuration for REST client."""
    timeout: float = 10.0
    max_retries: int = 3
    retry_delay: float = 1.0
    max_concurrent: int = 50
    headers: Optional[Dict[str, str]] = None  # Custom headers to add/override