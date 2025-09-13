"""
Arbitrage Controller

Main controller that orchestrates all components of the arbitrage engine.
Follows SOLID principles with clear separation of concerns.

HFT COMPLIANT: Event-driven architecture with minimal latency.
"""

import asyncio
import logging
from typing import Dict, Optional, Any

from arbitrage.types import ArbitrageConfig, EngineStatistics
from arbitrage.configuration_manager import ConfigurationManager
from arbitrage.exchange_factory import ExchangeFactory
from arbitrage.performance_monitor import PerformanceMonitor
from arbitrage.shutdown_manager import ShutdownManager, ShutdownReason
from exchanges.interface.base_exchange import BaseExchangeInterface

logger = logging.getLogger(__name__)


class ArbitrageController:
    """
    Main controller for the HFT arbitrage engine.
    
    Coordinates all components while maintaining clear separation of concerns.
    Each component has a single responsibility, making the system maintainable
    and testable.
    """
    
    def __init__(self):
        # Component instances
        self.config_manager = ConfigurationManager()
        self.exchange_factory = ExchangeFactory()
        self.performance_monitor: Optional[PerformanceMonitor] = None
        self.shutdown_manager = ShutdownManager()
        
        # State
        self.config: Optional[ArbitrageConfig] = None
        self.exchanges: Dict[str, BaseExchangeInterface] = {}
        self.engine: Optional[Any] = None  # Will be the actual engine
        self.running = False
        
    async def initialize(self, dry_run: bool = True) -> None:
        """
        Initialize all components of the arbitrage system.
        
        Args:
            dry_run: Whether to run in dry run mode
        """
        logger.info("Initializing arbitrage controller...")
        
        # Setup shutdown handlers
        self.shutdown_manager.setup_signal_handlers()
        
        # Load configuration
        self.config = await self.config_manager.load_configuration(dry_run)
        
        # Initialize performance monitor
        self.performance_monitor = PerformanceMonitor(self.config)
        
        # Register shutdown callbacks
        self.shutdown_manager.register_shutdown_callback(self._shutdown_components)
        
        # Initialize exchanges
        self.exchanges = await self.exchange_factory.create_exchanges(
            self.config.enabled_exchanges,
            self.config.enable_dry_run
        )
        
        # Validate we have required resources
        self._validate_initialization()
        
        logger.info("Arbitrage controller initialized successfully")
    
    def _validate_initialization(self):
        """Validate that initialization was successful."""
        if not self.exchanges:
            raise RuntimeError("No exchanges available - cannot proceed")
        
        # Check for private access in live mode
        if not self.config.enable_dry_run:
            private_available = any(
                exchange.has_private for exchange in self.exchanges.values()
                if exchange
            )
            if not private_available:
                raise RuntimeError(
                    "No private exchange credentials available for live trading. "
                    "Either provide API credentials or enable dry run mode."
                )
    
    async def run(self) -> None:
        """
        Run the main arbitrage session.
        
        This is the main entry point for the trading logic.
        """
        if self.running:
            logger.warning("Controller already running")
            return
            
        self.running = True
        logger.info("Starting arbitrage session...")
        
        try:
            # Start performance monitoring
            self.performance_monitor.start(self._get_engine_statistics)
            
            # Create and run engine
            await self._run_engine_session()
            
        except Exception as e:
            logger.error(f"Critical error in arbitrage session: {e}")
            self.shutdown_manager.initiate_shutdown(ShutdownReason.ERROR_CRITICAL)
            raise
        finally:
            self.running = False
    
    async def _run_engine_session(self):
        """Run the engine trading session."""
        # Import here to avoid circular dependency
        from arbitrage.simple_engine import SimpleArbitrageEngine
        
        # Create engine
        self.engine = SimpleArbitrageEngine(self.config, self.exchanges)
        
        logger.info("Arbitrage engine operational and monitoring opportunities...")
        
        # Main event loop
        while self.running and not self.shutdown_manager.is_shutdown_requested():
            try:
                # Check engine health
                if not self.engine.is_healthy():
                    logger.warning("Engine health check failed - checking exchanges...")
                    self._log_exchange_health()
                
                # Let engine process (in production, this would be event-driven)
                await asyncio.sleep(1)
                
                # Check for shutdown
                if await self.shutdown_manager.wait_for_shutdown(timeout=0.1):
                    break
                    
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                
                if self.config.enable_recovery_mode:
                    logger.info("Recovery mode enabled - attempting to continue...")
                    await asyncio.sleep(5)
                else:
                    logger.error("Recovery mode disabled - shutting down...")
                    break
    
    def _log_exchange_health(self):
        """Log health status of all exchanges."""
        for name, exchange in self.exchanges.items():
            if exchange:
                status = exchange.status
                logger.info(f"  {name}: {status.name}")
    
    def _get_engine_statistics(self) -> Optional[Dict[str, Any]]:
        """Get statistics from engine for performance monitoring."""
        if self.engine and hasattr(self.engine, 'get_statistics'):
            return self.engine.get_statistics()
        return None
    
    async def _shutdown_components(self):
        """Shutdown all components gracefully."""
        logger.info("Shutting down components...")
        
        # Stop performance monitor
        if self.performance_monitor:
            await self.performance_monitor.stop()
        
        # Stop engine
        if self.engine:
            try:
                await self.engine.stop()
            except Exception as e:
                logger.error(f"Error stopping engine: {e}")
        
        # Close exchanges
        await self.exchange_factory.close_all()
        
        logger.info("All components shut down")
    
    async def shutdown(self):
        """Execute graceful shutdown."""
        await self.shutdown_manager.execute_shutdown()