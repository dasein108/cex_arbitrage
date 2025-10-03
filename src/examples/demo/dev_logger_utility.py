"""
Dev Logger Utility
Provides immediate console logging for development environment.
"""

import os
from infrastructure.logging import get_logger
from infrastructure.logging.factory import LoggerFactory
from infrastructure.logging.structs import (
    LoggingConfig, ConsoleBackendConfig, PerformanceConfig, RouterConfig
)

def get_immediate_logger(name: str):
    """Get logger with immediate console output for development."""
    
    # Set environment
    os.environ['ENVIRONMENT'] = 'dev'
    
    # Create immediate config
    immediate_config = LoggingConfig(
        environment="dev",
        console=ConsoleBackendConfig(
            enabled=True,
            min_level="DEBUG",
            color=True,
            include_context=True
        ),
        performance=PerformanceConfig(
            buffer_size=100,         # Very small buffer
            batch_size=1,            # Process immediately
            dispatch_interval=0.001  # Very fast dispatch
        ),
        router=RouterConfig(
            default_backends=["console"]
        )
    )
    
    # Override factory default
    LoggerFactory._default_config = immediate_config
    
    return get_logger(name)

# Example usage
if __name__ == "__main__":
    import asyncio
    
    logger = get_immediate_logger("dev_test")
    
    # Sync logging
    logger.info("Sync log - immediate")
    
    async def test_async():
        logger.info("Async log - immediate")
        logger.warning("Warning log - immediate")
        await asyncio.sleep(0.01)  # Tiny delay for dispatch
    
    asyncio.run(test_async())
    print("Done!")