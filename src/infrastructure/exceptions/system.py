from typing import Optional


class BaseSystemError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
    """Default exception."""

class InitializationError(BaseSystemError):
    pass


class ConfigurationError(Exception):
    """Configuration-specific exception for setup errors."""

    def __init__(self, message: str, setting_name: Optional[str] = None):
        self.setting_name = setting_name
        super().__init__(message)
