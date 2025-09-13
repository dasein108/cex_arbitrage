"""
Simple Arbitrage Engine

Simplified arbitrage engine for demonstration and testing.
This replaces the MockArbitrageEngine with a cleaner implementation.

HFT COMPLIANT: Event-driven with proper abstractions.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional

from arbitrage.types import ArbitrageConfig, EngineStatistics
from exchanges.interface.base_exchange import BaseExchangeInterface
from exchanges.interface.structs import ExchangeStatus

logger = logging.getLogger(__name__)


class SimpleArbitrageEngine:
    """
    Simple arbitrage engine implementation.
    
    This is a simplified version for demonstration purposes.
    In production, you would use the full engine from arbitrage/engine.py
    """
    
    def __init__(
        self,
        config: ArbitrageConfig,
        exchanges: Dict[str, BaseExchangeInterface]
    ):
        self.config = config
        self.exchanges = exchanges
        self.statistics = EngineStatistics()
        self.running = False
        self._start_time: Optional[float] = None
        self._simulation_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start the engine."""
        if self.running:
            return
            
        self.running = True
        self._start_time = time.time()
        
        # Start simulation in dry run mode
        if self.config.enable_dry_run:
            self._simulation_task = asyncio.create_task(self._simulation_loop())
        
        logger.info("Simple arbitrage engine started")
    
    async def stop(self):
        """Stop the engine."""
        if not self.running:
            return
            
        self.running = False
        
        # Cancel simulation task
        if self._simulation_task:
            self._simulation_task.cancel()
            try:
                await self._simulation_task
            except asyncio.CancelledError:
                pass
        
        # Close exchanges
        for name, exchange in self.exchanges.items():
            try:
                if exchange:
                    await exchange.close()
                    logger.debug(f"Closed {name} exchange")
            except Exception as e:
                logger.error(f"Error closing {name}: {e}")
        
        logger.info("Simple arbitrage engine stopped")
    
    async def _simulation_loop(self):
        """Simulation loop for dry run mode."""
        simulation_count = 0
        max_simulations = 20  # Run for a limited time
        
        while self.running and simulation_count < max_simulations:
            try:
                await asyncio.sleep(3)  # Simulate processing time
                
                # Simulate opportunity detection
                if simulation_count % 2 == 0:
                    await self._simulate_opportunity()
                
                simulation_count += 1
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in simulation: {e}")
                await asyncio.sleep(5)
    
    async def _simulate_opportunity(self):
        """Simulate detecting and processing an opportunity."""
        self.statistics.opportunities_detected += 1
        
        # Simulate execution decision
        if self.statistics.opportunities_detected % 3 != 0:
            self.statistics.opportunities_executed += 1
            profit = 1.25 * self.statistics.opportunities_executed
            self.statistics.total_realized_profit += profit
            
            logger.info(
                f"Simulated opportunity #{self.statistics.opportunities_detected} "
                f"(DRY RUN) - Profit: ${profit:.2f}"
            )
        else:
            logger.info(
                f"Simulated opportunity #{self.statistics.opportunities_detected} "
                f"(DRY RUN) - Skipped due to risk checks"
            )
        
        # Update execution metrics
        self._update_execution_metrics()
    
    def _update_execution_metrics(self):
        """Update execution time and success rate metrics."""
        # Simulate execution time with slight variance
        base_time = 25.5
        variance = self.statistics.opportunities_detected * 0.1
        self.statistics.average_execution_time_ms = base_time + variance
        
        # Calculate success rate
        if self.statistics.opportunities_detected > 0:
            self.statistics.success_rate = (
                self.statistics.opportunities_executed / 
                self.statistics.opportunities_detected * 100
            )
        
        # Update uptime
        if self._start_time:
            self.statistics.uptime_seconds = time.time() - self._start_time
    
    def is_healthy(self) -> bool:
        """
        Check if engine is healthy.
        
        Returns:
            True if at least one exchange is active
        """
        active_count = sum(
            1 for exchange in self.exchanges.values()
            if exchange and exchange.status == ExchangeStatus.ACTIVE
        )
        return active_count > 0 and self.running
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get current engine statistics.
        
        Returns:
            Dictionary of statistics
        """
        # Update uptime
        if self._start_time:
            self.statistics.uptime_seconds = time.time() - self._start_time
        
        return self.statistics.to_dict()