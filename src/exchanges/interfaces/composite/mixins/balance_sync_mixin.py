"""
Balance Sync Mixin for Private Exchange Interfaces

This mixin provides automatic balance synchronization functionality for private
exchange interfaces. It handles periodic REST API balance fetching and publishing
balance snapshot events for data collection systems.

Key Features:
- Automatic balance sync with configurable intervals
- Balance snapshot event publishing
- Error resilient sync loop with retry logic
- Clean start/stop lifecycle management
- HFT compliant - no caching of real-time balance data

Usage:
    class MyPrivateExchange(BalanceSyncMixin, BasePrivateComposite):
        def __init__(self, ...):
            super().__init__(...)
            # Balance sync will be available automatically
"""

import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
from abc import ABC

from config.structs import ExchangeConfig
from exchanges.structs.types import AssetName
from exchanges.structs.common import AssetBalance
from infrastructure.networking.websocket.structs import PrivateWebsocketChannelType
from infrastructure.logging import HFTLoggerInterface


class BalanceSyncMixin(ABC):
    """
    Mixin providing automatic balance synchronization functionality.
    
    This mixin adds balance sync capabilities to private exchange interfaces:
    - Periodic balance fetching from REST API
    - Balance snapshot event publishing
    - Configurable sync intervals
    - Error handling and recovery
    
    Required dependencies (must be available in the class using this mixin):
    - self._balance_sync_interval: Optional[float]
    - self.logger: HFTLoggerInterface
    - self.config: ExchangeConfig (with has_credentials method)
    - self._load_balances(): async method to load balances
    - self.balances: property returning current balances
    - self.publish(): method to publish events
    """
    logger: 'HFTLoggerInterface'
    _balance_sync_interval: Optional[float]
    config: ExchangeConfig

    def __init__(self, *args, **kwargs):
        """Initialize balance sync mixin state."""
        super().__init__(*args, **kwargs)
        
        # Balance sync state
        self._balance_sync_task: Optional[asyncio.Task] = None
        self._balance_sync_enabled = False
        self._last_balance_sync: Optional[datetime] = None
    
    def start_balance_sync(self) -> bool:
        """
        Start automatic balance synchronization if configured.
        
        Returns:
            True if balance sync started, False if not configured or already running
        """
        if not self._balance_sync_interval or self._balance_sync_interval <= 0:
            self.logger.debug("Balance sync interval not configured, skipping auto-sync")
            return False
            
        if self._balance_sync_task and not self._balance_sync_task.done():
            self.logger.warning("Balance sync already running")
            return False
            
        if not self.config.has_credentials():
            self.logger.warning("No credentials available for balance sync")
            return False
            
        # Start the balance sync task
        self._balance_sync_task = asyncio.create_task(self._balance_sync_loop())
        self._balance_sync_enabled = True
        
        self.logger.info(f"Started balance sync with {self._balance_sync_interval}s interval")
        return True
    
    def stop_balance_sync(self) -> None:
        """Stop automatic balance synchronization."""
        if self._balance_sync_task and not self._balance_sync_task.done():
            self._balance_sync_task.cancel()
            self._balance_sync_enabled = False
            self.logger.info("Stopped balance sync")
    
    @property
    def balance_sync_enabled(self) -> bool:
        """Check if balance sync is currently enabled and running."""
        return (self._balance_sync_enabled and 
                self._balance_sync_task and 
                not self._balance_sync_task.done())
    
    @property
    def last_balance_sync(self) -> Optional[datetime]:
        """Get the timestamp of the last successful balance sync."""
        return self._last_balance_sync
    
    async def _balance_sync_loop(self) -> None:
        """
        Main balance synchronization loop.
        
        Fetches balances via REST and publishes balance snapshot events.
        """
        while self._balance_sync_enabled:
            try:
                # Fetch balances via REST
                await self._sync_balances_from_rest()
                
                # Update last sync time
                self._last_balance_sync = datetime.now()
                
                # Wait for next sync
                await asyncio.sleep(self._balance_sync_interval)
                
            except asyncio.CancelledError:
                self.logger.info("Balance sync loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Balance sync error: {e}", error=str(e))
                # Continue running despite errors, with shorter retry interval
                await asyncio.sleep(min(self._balance_sync_interval, 30.0))
    
    async def _sync_balances_from_rest(self) -> None:
        """
        Fetch current balances from REST API and publish balance snapshot event.
        
        This method fetches balances directly via REST (not WebSocket) and
        publishes a BALANCE_SNAPSHOT event with the collected data.
        """
        try:
            # Fetch balances using the existing load balances method
            await self._load_balances()
            
            # Get current balances
            current_balances = self.balances
            
            if current_balances:
                # Create balance snapshot data
                balance_snapshot_data = {
                    'exchange': self.config.exchange_enum,
                    'timestamp': datetime.now(),
                    'balances': current_balances,
                    'balance_count': len(current_balances)
                }
                
                # Publish balance snapshot event
                self.publish(PrivateWebsocketChannelType.BALANCE_SNAPSHOT, balance_snapshot_data)
                
                self.logger.debug(
                    f"Published balance snapshot: {len(current_balances)} assets",
                    exchange=self.config.name,
                    balance_count=len(current_balances)
                )
            else:
                self.logger.warning("No balances retrieved during sync")
                
        except Exception as e:
            self.logger.error(f"Failed to sync balances from REST: {e}", error=str(e))
            raise
    
    async def sync_balances_once(self) -> Dict[AssetName, AssetBalance]:
        """
        Perform a one-time balance sync and return the current balances.
        
        This method is useful for manual balance refresh without starting
        the automatic sync loop.
        
        Returns:
            Dictionary of current balances after sync
            
        Raises:
            Exception: If balance sync fails
        """
        try:
            await self._sync_balances_from_rest()
            self._last_balance_sync = datetime.now()
            
            current_balances = self.balances
            self.logger.info(f"Manual balance sync completed: {len(current_balances)} assets")
            return current_balances
            
        except Exception as e:
            self.logger.error(f"Manual balance sync failed: {e}")
            raise
    
    def _cleanup_balance_sync(self) -> None:
        """
        Clean up balance sync resources.
        
        Should be called during exchange close/cleanup.
        """
        self.stop_balance_sync()