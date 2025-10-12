"""
Parameter Scheduler for Delta Arbitrage Strategy

This module provides scheduled parameter updates for the live trading strategy,
handling the timing and coordination of regular optimization cycles.
"""

import asyncio
import time
import sys
import os
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum

from .optimizer_bridge import OptimizerBridge


class SchedulerStatus(Enum):
    """Scheduler status enumeration"""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class UpdateStatus:
    """Status of parameter update operation"""
    success: bool
    timestamp: float
    duration_seconds: float
    error_message: Optional[str] = None
    optimization_result: Optional[Any] = None


class ParameterScheduler:
    """
    Handles scheduled parameter updates for delta arbitrage strategy.
    
    This class manages the timing and execution of parameter optimization
    updates, providing features like:
    - Scheduled updates at regular intervals
    - Manual update triggers
    - Error handling and retry logic
    - Health monitoring and status reporting
    """
    
    def __init__(self, 
                 optimizer_bridge: OptimizerBridge,
                 update_callback: Optional[Callable] = None):
        """
        Initialize parameter scheduler.
        
        Args:
            optimizer_bridge: Bridge to optimization engine
            update_callback: Optional callback function for update notifications
        """
        self.optimizer_bridge = optimizer_bridge
        self.update_callback = update_callback
        
        # Scheduler state
        self.status = SchedulerStatus.STOPPED
        self.interval_minutes = 5  # Default 5-minute intervals
        self.lookback_hours = 24   # Default 24-hour lookback
        self.min_data_points = 100 # Minimum data points for optimization
        
        # Update tracking
        self._last_update_status: Optional[UpdateStatus] = None
        self._update_count = 0
        self._successful_updates = 0
        self._failed_updates = 0
        
        # Scheduler task
        self._scheduler_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        
        # Error handling
        self.max_consecutive_failures = 3
        self._consecutive_failures = 0
        self.retry_delay_seconds = 60  # Wait 1 minute before retry after failure
        
        print(f"⏰ ParameterScheduler initialized")
        print(f"   • Default interval: {self.interval_minutes} minutes")
        print(f"   • Default lookback: {self.lookback_hours} hours")
    
    async def start_scheduled_updates(self, 
                                    interval_minutes: int = 5,
                                    lookback_hours: int = 24,
                                    min_data_points: int = 100) -> None:
        """
        Start scheduled parameter updates.
        
        Args:
            interval_minutes: Minutes between parameter updates
            lookback_hours: Hours of data to use for optimization
            min_data_points: Minimum data points required
        """
        if self.status == SchedulerStatus.RUNNING:
            print("⚠️ Scheduler already running")
            return
        
        self.interval_minutes = interval_minutes
        self.lookback_hours = lookback_hours
        self.min_data_points = min_data_points
        
        print(f"🚀 Starting parameter scheduler...")
        print(f"   • Update interval: {interval_minutes} minutes")
        print(f"   • Data lookback: {lookback_hours} hours")
        print(f"   • Min data points: {min_data_points}")
        
        self.status = SchedulerStatus.RUNNING
        self._stop_event.clear()
        
        # Start scheduler task
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        
        print("✅ Parameter scheduler started")
    
    async def stop_scheduled_updates(self) -> None:
        """Stop scheduled parameter updates."""
        if self.status == SchedulerStatus.STOPPED:
            print("⚠️ Scheduler already stopped")
            return
        
        print("🛑 Stopping parameter scheduler...")
        
        self.status = SchedulerStatus.STOPPED
        self._stop_event.set()
        
        # Cancel scheduler task
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        
        print("✅ Parameter scheduler stopped")
    
    async def pause_scheduled_updates(self) -> None:
        """Pause scheduled updates (can be resumed)."""
        if self.status == SchedulerStatus.RUNNING:
            self.status = SchedulerStatus.PAUSED
            print("⏸️ Parameter scheduler paused")
        else:
            print("⚠️ Scheduler not running, cannot pause")
    
    async def resume_scheduled_updates(self) -> None:
        """Resume paused scheduled updates."""
        if self.status == SchedulerStatus.PAUSED:
            self.status = SchedulerStatus.RUNNING
            print("▶️ Parameter scheduler resumed")
        else:
            print("⚠️ Scheduler not paused, cannot resume")
    
    async def perform_parameter_update(self) -> UpdateStatus:
        """
        Perform a single parameter update.
        
        This method can be called manually or by the scheduler.
        
        Returns:
            UpdateStatus with operation results
        """
        start_time = time.time()
        self._update_count += 1
        
        try:
            print(f"🔄 Performing parameter update #{self._update_count}...")
            
            # Perform optimization
            success = await self.optimizer_bridge.update_strategy_parameters(
                lookback_hours=self.lookback_hours,
                min_data_points=self.min_data_points
            )
            
            duration = time.time() - start_time
            
            if success:
                self._successful_updates += 1
                self._consecutive_failures = 0
                
                # Get optimization result
                optimization_result = self.optimizer_bridge.get_last_optimization_result()
                
                status = UpdateStatus(
                    success=True,
                    timestamp=time.time(),
                    duration_seconds=duration,
                    optimization_result=optimization_result
                )
                
                print(f"✅ Parameter update completed successfully in {duration:.3f}s")
                
                # Call update callback if provided
                if self.update_callback:
                    try:
                        await self.update_callback(optimization_result)
                    except Exception as e:
                        print(f"⚠️ Update callback failed: {e}")
                
            else:
                self._failed_updates += 1
                self._consecutive_failures += 1
                
                status = UpdateStatus(
                    success=False,
                    timestamp=time.time(),
                    duration_seconds=duration,
                    error_message="Optimization failed"
                )
                
                print(f"❌ Parameter update failed after {duration:.3f}s")
                
                # Check if we should pause due to consecutive failures
                if self._consecutive_failures >= self.max_consecutive_failures:
                    self.status = SchedulerStatus.ERROR
                    print(f"🚨 Too many consecutive failures ({self._consecutive_failures}), switching to error state")
            
            self._last_update_status = status
            return status
            
        except Exception as e:
            duration = time.time() - start_time
            self._failed_updates += 1
            self._consecutive_failures += 1
            
            error_msg = f"Update error: {str(e)}"
            
            status = UpdateStatus(
                success=False,
                timestamp=time.time(),
                duration_seconds=duration,
                error_message=error_msg
            )
            
            self._last_update_status = status
            
            print(f"❌ Parameter update error: {e}")
            
            # Check error state
            if self._consecutive_failures >= self.max_consecutive_failures:
                self.status = SchedulerStatus.ERROR
                print(f"🚨 Scheduler entering error state due to consecutive failures")
            
            return status
    
    async def force_update_now(self) -> UpdateStatus:
        """Force an immediate parameter update regardless of schedule."""
        print("⚡ Forcing immediate parameter update...")
        return await self.perform_parameter_update()
    
    def get_update_status(self) -> Dict[str, Any]:
        """
        Get comprehensive update status and statistics.
        
        Returns:
            Dictionary with update status information
        """
        success_rate = (self._successful_updates / self._update_count 
                       if self._update_count > 0 else 0)
        
        time_until_next = self._calculate_time_until_next_update()
        
        return {
            'scheduler_status': self.status.value,
            'configuration': {
                'interval_minutes': self.interval_minutes,
                'lookback_hours': self.lookback_hours,
                'min_data_points': self.min_data_points,
                'max_consecutive_failures': self.max_consecutive_failures,
            },
            'statistics': {
                'total_updates': self._update_count,
                'successful_updates': self._successful_updates,
                'failed_updates': self._failed_updates,
                'success_rate': success_rate,
                'consecutive_failures': self._consecutive_failures,
            },
            'timing': {
                'time_until_next_update_seconds': time_until_next,
                'last_update_timestamp': (self._last_update_status.timestamp 
                                        if self._last_update_status else None),
            },
            'last_update': {
                'success': self._last_update_status.success if self._last_update_status else None,
                'duration_seconds': (self._last_update_status.duration_seconds 
                                   if self._last_update_status else None),
                'error_message': (self._last_update_status.error_message 
                                if self._last_update_status else None),
            } if self._last_update_status else None,
            'bridge_status': self.optimizer_bridge.get_optimization_status()
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of the parameter scheduler."""
        status = self.get_update_status()
        
        is_healthy = True
        health_issues = []
        
        # Check scheduler status
        if self.status == SchedulerStatus.ERROR:
            is_healthy = False
            health_issues.append("Scheduler in error state")
        
        # Check success rate
        if status['statistics']['success_rate'] < 0.7:
            is_healthy = False
            health_issues.append("Low update success rate")
        
        # Check consecutive failures
        if self._consecutive_failures >= 2:
            health_issues.append("Multiple consecutive failures")
        
        # Check if updates are overdue
        if (self.status == SchedulerStatus.RUNNING and 
            status['timing']['time_until_next_update_seconds'] < -300):  # 5 minutes overdue
            is_healthy = False
            health_issues.append("Updates overdue")
        
        # Check bridge health
        bridge_health = self.optimizer_bridge.get_health_status()
        if not bridge_health['is_healthy']:
            is_healthy = False
            health_issues.extend([f"Bridge: {issue}" for issue in bridge_health['health_issues']])
        
        return {
            'is_healthy': is_healthy,
            'health_issues': health_issues,
            'status': status
        }
    
    def reset_error_state(self) -> None:
        """Reset error state and consecutive failure count (manual intervention)."""
        if self.status == SchedulerStatus.ERROR:
            self.status = SchedulerStatus.STOPPED
            self._consecutive_failures = 0
            print("✅ Error state reset - scheduler can be restarted")
        else:
            print("⚠️ Scheduler not in error state")
    
    def reset_statistics(self) -> None:
        """Reset all statistics (for testing/debugging)."""
        self._update_count = 0
        self._successful_updates = 0
        self._failed_updates = 0
        self._consecutive_failures = 0
        self._last_update_status = None
        print("📊 Scheduler statistics reset")
    
    async def _scheduler_loop(self) -> None:
        """Main scheduler loop that runs scheduled updates."""
        try:
            print("🔄 Scheduler loop started")
            
            while not self._stop_event.is_set():
                try:
                    # Check if we should run an update
                    if self.status == SchedulerStatus.RUNNING:
                        if self._should_run_update():
                            await self.perform_parameter_update()
                        
                        # If we're in error state after update, wait for retry
                        if self.status == SchedulerStatus.ERROR:
                            print(f"⏳ Waiting {self.retry_delay_seconds}s before retry...")
                            await asyncio.sleep(self.retry_delay_seconds)
                            # Reset to running state for retry
                            if self._consecutive_failures < self.max_consecutive_failures * 2:
                                self.status = SchedulerStatus.RUNNING
                                print("🔄 Retrying after error state...")
                    
                    # Wait a bit before next check (don't busy-wait)
                    await asyncio.sleep(10)  # Check every 10 seconds
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"❌ Scheduler loop error: {e}")
                    await asyncio.sleep(30)  # Wait before continuing
            
        except asyncio.CancelledError:
            print("🛑 Scheduler loop cancelled")
        except Exception as e:
            print(f"❌ Fatal scheduler error: {e}")
            self.status = SchedulerStatus.ERROR
        finally:
            print("✅ Scheduler loop ended")
    
    def _should_run_update(self) -> bool:
        """Check if it's time to run a parameter update."""
        if not self._last_update_status:
            return True  # First update
        
        elapsed_minutes = (time.time() - self._last_update_status.timestamp) / 60
        return elapsed_minutes >= self.interval_minutes
    
    def _calculate_time_until_next_update(self) -> float:
        """Calculate seconds until next scheduled update."""
        if not self._last_update_status:
            return 0.0  # Update immediately
        
        elapsed_seconds = time.time() - self._last_update_status.timestamp
        interval_seconds = self.interval_minutes * 60
        return interval_seconds - elapsed_seconds