"""
Arbitrage Controller

Main controller that orchestrates all components of the arbitrage engine.
Follows SOLID principles with clear separation of concerns.

HFT COMPLIANT: Event-driven architecture with minimal latency.
"""

import asyncio
import logging
from typing import Dict, Optional, Any

from arbitrage.types import ArbitrageConfig
from arbitrage.configuration_manager import ConfigurationManager
from arbitrage.exchange_factory import ExchangeFactory
from arbitrage.performance_monitor import PerformanceMonitor
from arbitrage.shutdown_manager import ShutdownManager, ShutdownReason
from arbitrage.symbol_resolver import SymbolResolver
from core.cex.base.base_private_exchange import BasePrivateExchangeInterface

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
        self.exchanges: Dict[str, BasePrivateExchangeInterface] = {}
        self.symbol_resolver: Optional[SymbolResolver] = None
        self.engine: Optional[Any] = None  # Will be the actual engine
        self.running = False
        
    async def  initialize(self) -> None:
        """
        Initialize all components of the arbitrage system.
        
        All settings loaded from config.yaml including dry_run mode.
        """
        logger.info("Initializing arbitrage controller...")
        
        # Setup shutdown handlers
        self.shutdown_manager.setup_signal_handlers()
        
        # Load configuration (will get dry_run setting from config)
        self.config = await self.config_manager.load_configuration()
        
        # Configure logging based on config settings
        self._configure_logging()
        
        # Initialize performance monitor
        self.performance_monitor = PerformanceMonitor(self.config)
        
        # Register shutdown callbacks
        self.shutdown_manager.register_shutdown_callback(self._shutdown_components)
        
        # Extract symbols from arbitrage pairs for exchange initialization
        arbitrage_symbols = self.config_manager.extract_symbols_from_arbitrage_pairs()
        logger.info(f"Initializing exchanges with {len(arbitrage_symbols)} symbols from arbitrage configuration")
        
        # HFT OPTIMIZATION: Initialize exchanges with arbitrage symbols
        from arbitrage.exchange_factory import InitializationStrategy
        
        strategy = InitializationStrategy.CONTINUE_ON_ERROR if self.config.enable_dry_run else InitializationStrategy.RETRY_WITH_BACKOFF
        exchanges_task = self.exchange_factory.create_exchanges(
            self.config.enabled_exchanges,
            strategy=strategy,
            symbols=arbitrage_symbols
        )
        
        # Wait for exchanges to complete first (symbol resolver depends on them)
        self.exchanges = await exchanges_task
        
        # Initialize symbol resolver with exchange information
        await self._initialize_symbol_resolver()
        
        # Validate we have required resources
        self._validate_initialization()
        
        logger.info("Arbitrage controller initialized successfully")
    
    async def _initialize_symbol_resolver(self):
        """
        Initialize symbol resolver with exchange information.
        
        HFT COMPLIANT: Symbol info fetched once at startup.
        HFT OPTIMIZED: Performance timing for initialization monitoring.
        """
        import time
        start_time = time.perf_counter()
        
        logger.info("Initializing symbol resolver...")
        self.symbol_resolver = SymbolResolver(self.exchanges)
        await self.symbol_resolver.initialize()
        
        # Log common symbols with performance metrics
        common_symbols = self.symbol_resolver.get_common_symbols()
        elapsed = time.perf_counter() - start_time
        
        logger.info(f"Symbol resolver initialized in {elapsed*1000:.2f}ms")
        logger.info(f"Found {len(common_symbols)} symbols available on all exchanges")
        if common_symbols[:5]:  # Show first 5
            logger.info(f"Sample common symbols: {common_symbols[:5]}")
    
    def _configure_logging(self):
        """
        Configure logging based on config.yaml settings.
        """
        try:
            # Get log level from config
            from config import config as base_config
            
            # Get environment settings for log level
            log_level = base_config.LOG_LEVEL
            
            # Configure logging
            logging.basicConfig(
                level=getattr(logging, log_level),
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.StreamHandler(),
                    logging.FileHandler('arbitrage.log')
                ],
                force=True  # Override existing configuration
            )
            
            logger.info(f"Logging configured: level={log_level}")
            
        except Exception as e:
            logger.warning(f"Failed to configure logging from config: {e}")
            # Fall back to INFO level
            logging.basicConfig(level=logging.INFO, force=True)
    
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
        from arbitrage.engine_factory import EngineFactory
        
        # Get recommended engine type based on configuration
        engine_type = EngineFactory.get_recommended_engine_type(self.config)
        logger.info(f"Using {engine_type} engine based on configuration")
        
        # Create engine using factory
        self.engine = EngineFactory.create_engine(engine_type, self.config, self.exchanges)
        
        # CRITICAL FIX: Start the engine (was missing!)
        await self.engine.start()
        
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