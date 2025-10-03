import asyncio

from infrastructure.logging import get_logger


logger = get_logger("test")

logger.debug("test debug")
logger.info("test info")
logger.warning("test warning")
logger.error("test error")

async def main():
    logger.debug("test debug async")
    logger.info("test info async")
    logger.warning("test warning async")
    logger.error("test error async")


    # await asyncio.sleep(0.1)
    #
    # # OR ADD THIS: Explicit flush if the logger supports it
    # if hasattr(logger, 'flush'):
    #     await logger.flush()

asyncio.run(main())