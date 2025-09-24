#!/usr/bin/env python3
"""
HFT Arbitrage Engine - Config-Driven Main Entry Point

Production-ready main entry point with clean architecture following SOLID principles.
All configuration loaded from config.yaml file, no command line arguments required.

Features:
- Clean separation of concerns with focused components
- Factory pattern for exchange creation
- Proper configuration management from config.yaml
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
    PYTHONPATH=src python src/main.py
    
Configuration:
    All settings loaded from config.yaml including:
    - Trading mode (dry_run vs live)
    - Log level (DEBUG, INFO, WARNING, ERROR)
    - Exchange credentials and settings
    - Risk limits and safety features
"""

import asyncio
import logging
import sys

# Factory system is now self-contained in core/

from trading.arbitrage import ArbitrageController

logger = logging.getLogger(__name__)


async def main() -> None:
    """
    Main entry point for HFT arbitrage engine.
    
    Config-driven implementation - all settings loaded from config.yaml.
    No command line arguments required.
    """
    # Initialize controller (will load and apply all config settings)
    controller = ArbitrageController()
    
    try:
        logger.info("Starting HFT Arbitrage Engine...")
        
        # Initialize all components (config will be loaded internally)
        await controller.initialize()
        
        # Log configuration details
        logger.info(f"Engine: {controller.config.engine_name}")
        logger.info(f"Mode: {'DRY RUN (SAFE)' if controller.config.enable_dry_run else 'LIVE TRADING'}")
        logger.info(f"Exchanges: {', '.join(controller.config.enabled_exchanges)}")
        logger.info(f"Opportunities: {', '.join([t.name for t in controller.config.enabled_opportunity_types])}")
        
        # Trading mode confirmation
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
        print("\nKeyboard interrupt - exiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)