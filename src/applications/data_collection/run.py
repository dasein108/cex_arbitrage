#!/usr/bin/env python3
"""
Data Collector Entry Point

Command-line interface for running the real-time data collection system.
Collects book ticker data from MEXC and Gate.io exchanges and stores in PostgreSQL.
"""

import asyncio
import argparse
import signal
import sys
import traceback
from pathlib import Path
from typing import Optional

from exchanges.structs import ExchangeEnum

sys.path.insert(0, str(Path(__file__).parent.parent))
from typing import List
from applications.data_collection.collector import DataCollector
# from config.config_manager import get_data_collector_config
from exchanges.structs.common import Symbol
from exchanges.structs.types import AssetName
from config import HftConfig

# HFT Logger Integration
from infrastructure.logging import get_logger


class DataCollectorCLI:
    """Command-line interface for the data collector."""

    def __init__(self):
        self.collector: Optional[DataCollector] = None
        self.logger = get_logger('data_collector.cli')
        self._shutdown_event = None  # Will be created in async context


    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            self.logger.info("Received shutdown signal",
                             signal_number=signum)
            if self._shutdown_event:
                self._shutdown_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def create_symbol(self, symbol_str: str) -> Symbol:
        """Create Symbol object from string."""
        base, quote = symbol_str.split("_", 1)

        return Symbol(
            base=AssetName(base.upper()),
            quote=AssetName(quote.upper()),
        )

    def create_symbol_list(self, symbols: List[str]) -> list[Symbol]:
        return [self.create_symbol(s) for s in symbols]

    async def run_collector(
            self,
            dry_run: bool = False
    ) -> None:
        """
        Run the data collector.
        
        Args:
            dry_run: Run without storing data to database
        """
        # Initialize shutdown event in async context
        self._shutdown_event = asyncio.Event()

        try:
            self.logger.info("Starting Data Collector")

            # Initialize core config manager (singleton)
            config = HftConfig()
            self.logger.info("Data collector configuration loaded",
                             environment=config.ENVIRONMENT,
                             dry_run=dry_run)

            exchanges = [ExchangeEnum.MEXC, ExchangeEnum.GATEIO, ExchangeEnum.GATEIO_FUTURES]
            symbol_list = ['ASP_USDT', 'AMZNX_USDT', 'U_USDT', 'METAX_USDT', 'GPS_USDT',
                           'VELO_USDT', 'ARIA_USDT', 'DF_USDT', 'FIO_USDT', 'IO_USDT']
            # symbol_list = ['ASP_USDT']

            symbols = self.create_symbol_list(symbol_list)
            self.collector = DataCollector(symbols=symbols, exchanges=exchanges)

            # Initialize components
            await self.collector.initialize()

            if dry_run:
                self.logger.warning("DRY RUN MODE: No data will be stored to database",
                                    dry_run=True)
                # In dry run mode, we could disable the database storage
                # For now, we'll just log the warning

            # Start collection
            collection_task = asyncio.create_task(self.collector.start())

            # Wait for shutdown signal
            await self._shutdown_event.wait()

            # Cancel collection
            collection_task.cancel()

            try:
                await collection_task
            except asyncio.CancelledError:
                pass

        except Exception as e:
            self.logger.error("Data collector error",
                              error_type=type(e).__name__,
                              error_message=str(e))
            traceback.print_exc()
            raise
        finally:
            if self.collector:
                await self.collector.stop()


    async def main(self) -> None:
        """Main entry point."""

        self.setup_signal_handlers()

        # Run collector
        try:
            await self.run_collector(dry_run=False)
        except KeyboardInterrupt:
            self.logger.info("Shutdown requested by user")
        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            sys.exit(1)


def main():
    """Entry point for command line execution."""
    cli = DataCollectorCLI()
    asyncio.run(cli.main())


if __name__ == "__main__":
    main()
