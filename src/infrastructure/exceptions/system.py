

class BaseSystemError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
    """Default exception."""

class InitializationError(BaseSystemError):
    pass