#!/usr/bin/env python3
"""
HFT Arbitrage Engine - Refactored Main Entry Point

Production-ready main entry point with clean architecture following SOLID principles.
Eliminates all code smells and provides maintainable, testable, HFT-compliant design.

Features:
- Clean separation of concerns with focused components
- Factory pattern for exchange creation
- Proper configuration management
- Professional performance monitoring
- Graceful shutdown with resource cleanup
- HFT-compliant architecture (no real-time data caching)

Architecture:
- ConfigurationManager: Handles all configuration loading and validation
- ExchangeFactory: Creates and manages exchange instances
- PerformanceMonitor: Tracks performance metrics and HFT compliance
- ShutdownManager: Handles graceful shutdown and cleanup
- ArbitrageController: Orchestrates all components

Usage:
    PYTHONPATH=src python src/main.py          # Start in dry run mode
    PYTHONPATH=src python src/main.py --live   # Start in live trading mode
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from arbitrage.controller import ArbitrageController

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('arbitrage.log')
    ]
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """
    Main entry point for HFT arbitrage engine.
    
    Clean, focused implementation following Single Responsibility Principle.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='HFT Arbitrage Engine - Ultra-high-performance cryptocurrency arbitrage',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  PYTHONPATH=src python src/main.py          # Start in dry run mode (safe)
  PYTHONPATH=src python src/main.py --live   # Start in live trading mode
  
Configuration:
  All settings loaded from config.yaml file
  
Exchange API Credentials (environment variables):
  MEXC_API_KEY, MEXC_SECRET_KEY
  GATEIO_API_KEY, GATEIO_SECRET_KEY
        """
    )
    
    parser.add_argument(
        '--live', 
        action='store_true',
        help='Enable live trading mode (default: dry run mode for safety)'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Set logging level (default: INFO)'
    )
    
    args = parser.parse_args()
    
    # Configure logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Initialize controller
    controller = ArbitrageController()
    
    try:
        logger.info("Starting HFT Arbitrage Engine...")
        logger.info(f"Mode: {'LIVE TRADING' if args.live else 'DRY RUN (SAFE)'}")
        logger.info(f"Log Level: {args.log_level}")
        
        # Initialize all components
        await controller.initialize(dry_run=not args.live)
        
        # Log trading mode confirmation
        if controller.config.enable_dry_run:
            logger.info("Running in DRY RUN mode - safe for testing")
        else:
            logger.warning("Running in LIVE TRADING mode - real money at risk")
            private_exchanges = [
                name for name, exchange in controller.exchanges.items()
                if exchange and exchange.has_private
            ]
            logger.info(f"Private trading enabled on: {private_exchanges}")
        
        # Run the arbitrage session
        await controller.run()
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received - shutting down...")
    except Exception as e:
        logger.error(f"Critical error in main process: {e}")
        sys.exit(1)
    finally:
        # Graceful shutdown
        await controller.shutdown()
        logger.info("HFT Arbitrage Engine shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt - exiting...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)