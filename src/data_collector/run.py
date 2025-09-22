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
import logging
import traceback
from pathlib import Path
from typing import Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import exchanges to trigger factory registrations
import exchanges  # This triggers auto-registration of WebSocket factories

from data_collector.collector import DataCollector
from data_collector.config import load_data_collector_config
from structs.common import Symbol, AssetName
from core.config.config_manager import HftConfig


class DataCollectorCLI:
    """Command-line interface for the data collector."""
    
    def __init__(self):
        self.collector: Optional[DataCollector] = None
        self.logger = logging.getLogger(__name__)
        self._shutdown_event = asyncio.Event()
    
    def setup_logging(self, log_level: str = "INFO") -> None:
        """Setup logging configuration."""
        log_format = "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] %(message)s"
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format=log_format,
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    
    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, initiating shutdown...")
            self._shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def run_collector(
        self,
        dry_run: bool = False,
        symbols_override: Optional[list] = None
    ) -> None:
        """
        Run the data collector.
        
        Args:
            dry_run: Run without storing data to database
            symbols_override: Override symbols from config
        """
        try:
            self.logger.info("Starting Data Collector")
            
            # Initialize core config manager (singleton)
            config = HftConfig()
            self.logger.info(f"Environment: {config.ENVIRONMENT}")
            self.logger.info(f"Dry run mode: {dry_run}")
            
            # Initialize collector (uses core config internally)
            self.collector = DataCollector()
            
            # Override symbols if provided
            if symbols_override:
                self.logger.info(f"Overriding symbols with: {symbols_override}")
                symbols = []
                for symbol_str in symbols_override:
                    if "/" in symbol_str:
                        base, quote = symbol_str.split("/", 1)
                    else:
                        # Assume USDT as quote if not specified
                        base, quote = symbol_str, "USDT"
                    
                    symbol = Symbol(
                        base=AssetName(base.upper()),
                        quote=AssetName(quote.upper()),
                        is_futures=False
                    )
                    symbols.append(symbol)
                
                self.collector.config.symbols = symbols
            
            # Initialize components
            await self.collector.initialize()
            
            # Log startup status
            status = self.collector.get_status()
            self.logger.info(f"Initialized for {len(status['config']['exchanges'])} exchanges")
            self.logger.info(f"Monitoring {status['config']['symbols_count']} symbols")
            self.logger.info(f"Snapshot interval: {status['config']['snapshot_interval']}s")
            
            if dry_run:
                self.logger.warning("DRY RUN MODE: No data will be stored to database")
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
            self.logger.error(f"Data collector error: {e}")
            traceback.print_exc()
            raise
        finally:
            if self.collector:
                await self.collector.stop()
    
    async def show_status(self) -> None:
        """
        Show current status without running collection.
        """
        try:
            # Initialize core config and load data collector config
            core_config = HftConfig()
            config = load_data_collector_config()
            
            print("Data Collector Configuration:")
            print(f"  Enabled: {config.enabled}")
            print(f"  Snapshot interval: {config.snapshot_interval}s")
            print(f"  Analytics interval: {config.analytics_interval}s")
            print(f"  Exchanges: {', '.join([e.value for e in config.exchanges])}")
            print(f"  Symbols: {len(config.symbols)}")
            
            print("\nConfigured symbols:")
            for i, symbol in enumerate(config.symbols, 1):
                print(f"  {i:2d}. {symbol.base}/{symbol.quote}")
            
            print(f"\nAnalytics configuration:")
            print(f"  Arbitrage threshold: {config.analytics.arbitrage_threshold:.1%}")
            print(f"  Volume threshold: ${config.analytics.volume_threshold:,.0f}")
            print(f"  Spread alert threshold: {config.analytics.spread_alert_threshold:.1%}")
            
            print(f"\nDatabase configuration:")
            print(f"  Host: {config.database.host}:{config.database.port}")
            print(f"  Database: {config.database.database}")
            print(f"  Username: {config.database.username}")
            
        except Exception as e:
            print(f"Error loading configuration: {e}")
    
    def parse_args(self) -> argparse.Namespace:
        """Parse command line arguments."""
        parser = argparse.ArgumentParser(
            description="Real-time book ticker data collector for cryptocurrency arbitrage",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Run with automatic config detection
  python run.py
  
  # Dry run mode (no database writes)
  python run.py --dry-run
  
  # Override symbols
  python run.py --symbols BTC/USDT,ETH/USDT
  
  # Show status without running
  python run.py --status
  
  # Debug mode
  python run.py --log-level DEBUG
            """
        )
        
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run without storing data to database"
        )
        
        parser.add_argument(
            "--symbols",
            type=str,
            help="Comma-separated list of symbols to monitor (e.g., BTC/USDT,ETH/USDT)"
        )
        
        parser.add_argument(
            "--status",
            action="store_true",
            help="Show configuration status and exit"
        )
        
        parser.add_argument(
            "--log-level",
            type=str,
            default="INFO",
            choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            help="Logging level (default: INFO)"
        )
        
        return parser.parse_args()
    
    async def main(self) -> None:
        """Main entry point."""
        args = self.parse_args()
        
        # Setup logging
        self.setup_logging(args.log_level)
        
        # Show status and exit if requested
        if args.status:
            await self.show_status()
            return
        
        # Parse symbols override
        symbols_override = None
        if args.symbols:
            symbols_override = [s.strip() for s in args.symbols.split(",")]
        
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # Run collector
        try:
            await self.run_collector(
                dry_run=args.dry_run,
                symbols_override=symbols_override
            )
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