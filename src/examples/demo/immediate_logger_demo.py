import asyncio
import os

# Set dev environment
os.environ['ENVIRONMENT'] = 'dev'

from infrastructure.logging import get_logger
from infrastructure.logging.structs import LoggingConfig, ConsoleBackendConfig, PerformanceConfig, RouterConfig

# Create immediate logging config for dev environment
immediate_config = LoggingConfig(
    environment="dev",
    console=ConsoleBackendConfig(
        enabled=True,
        min_level="DEBUG",
        color=True,
        include_context=True
    ),
    performance=PerformanceConfig(
        buffer_size=1000,        # Smaller buffer
        batch_size=1,            # Process every message immediately
        dispatch_interval=0.001  # Very fast dispatch
    ),
    router=RouterConfig(
        default_backends=["console"]
    )
)

# Override factory config
from infrastructure.logging.factory import LoggerFactory
LoggerFactory._default_config = immediate_config

logger = get_logger("test_immediate")

async def main():
    logger.debug("test debug async - should appear immediately")
    logger.info("test info async - should appear immediately")
    logger.warning("test warning async - should appear immediately")
    logger.error("test error async - should appear immediately")
    
    # Small delay to let dispatch happen
    await asyncio.sleep(0.01)

print("Sync logs before async:")
logger.debug("test debug sync")
logger.info("test info sync")

print("\nRunning async logs:")
asyncio.run(main())
print("Done!")