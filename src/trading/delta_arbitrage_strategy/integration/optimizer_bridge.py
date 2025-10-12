"""
Optimizer Bridge for Delta Arbitrage Strategy

This module provides the bridge between the parameter optimization engine
and the live trading strategy, handling data fetching, optimization calls,
and parameter updates.
"""

import asyncio
import time
import sys
import os
import pandas as pd
from typing import Optional, Dict, Any

from ..optimization.parameter_optimizer import DeltaArbitrageOptimizer, OptimizationResult


class OptimizerBridge:
    """
    Bridge between optimization engine and live trading strategy.
    
    This class handles:
    - Fetching recent market data for optimization
    - Calling the optimizer with appropriate parameters
    - Validating optimization results
    - Providing optimization status and health checks
    """
    
    def __init__(self, 
                 optimizer: DeltaArbitrageOptimizer,
                 strategy_reference: Any = None):
        """
        Initialize optimizer bridge.
        
        Args:
            optimizer: Parameter optimizer instance
            strategy_reference: Reference to strategy for data access (optional)
        """
        self.optimizer = optimizer
        self.strategy_reference = strategy_reference
        
        # Bridge state
        self._last_optimization_time = 0.0
        self._last_optimization_result: Optional[OptimizationResult] = None
        self._optimization_count = 0
        self._failed_optimizations = 0
        
        # Performance tracking
        self._total_optimization_time = 0.0
        self._avg_optimization_time = 0.0
        
        print(f"🔗 OptimizerBridge initialized")
    
    async def update_strategy_parameters(self, 
                                       lookback_hours: int = 24,
                                       min_data_points: int = 100) -> bool:
        """
        Update strategy parameters using optimizer.
        
        This is the main method called by the strategy to update parameters.
        It fetches recent data, runs optimization, and returns success status.
        
        Args:
            lookback_hours: Hours of historical data to use
            min_data_points: Minimum data points required for optimization
            
        Returns:
            True if optimization succeeded and parameters were updated
        """
        try:
            start_time = time.time()
            self._optimization_count += 1
            
            print(f"🔄 Starting parameter optimization (#{self._optimization_count})...")
            
            # 1. Fetch recent market data
            market_data = await self.get_recent_market_data(lookback_hours)
            
            if len(market_data) < min_data_points:
                print(f"⚠️ Insufficient data for optimization: {len(market_data)} < {min_data_points}")
                self._failed_optimizations += 1
                return False
            
            print(f"   • Retrieved {len(market_data)} data points")
            
            # 2. Run optimization
            optimization_result = await self.optimizer.optimize_parameters(
                market_data, 
                lookback_hours=lookback_hours
            )
            
            # 3. Validate optimization result
            if not self._validate_optimization_result(optimization_result):
                print(f"❌ Optimization result validation failed")
                self._failed_optimizations += 1
                return False
            
            # 4. Store successful result
            self._last_optimization_time = time.time()
            self._last_optimization_result = optimization_result
            
            # 5. Update performance tracking
            optimization_time = time.time() - start_time
            self._total_optimization_time += optimization_time
            self._avg_optimization_time = self._total_optimization_time / self._optimization_count
            
            print(f"✅ Parameter optimization completed in {optimization_time:.3f}s")
            print(f"   • Entry threshold: {optimization_result.entry_threshold_pct:.4f}%")
            print(f"   • Exit threshold: {optimization_result.exit_threshold_pct:.4f}%")
            print(f"   • Confidence: {optimization_result.confidence_score:.3f}")
            
            return True
            
        except Exception as e:
            print(f"❌ Parameter optimization failed: {e}")
            self._failed_optimizations += 1
            return False
    
    async def get_recent_market_data(self, hours: int = 24) -> pd.DataFrame:
        """
        Get recent market data for optimization.
        
        In this PoC implementation, we get data from the strategy's mock data.
        In a real implementation, this would fetch from exchange APIs or database.
        
        Args:
            hours: Hours of data to retrieve
            
        Returns:
            DataFrame with market data
        """
        try:
            # Try to get data from strategy reference
            if self.strategy_reference and hasattr(self.strategy_reference, '_get_recent_market_data'):
                return await self.strategy_reference._get_recent_market_data()
            
            # Fallback: generate mock data
            return await self._generate_fallback_data(hours)
            
        except Exception as e:
            print(f"⚠️ Error fetching market data: {e}")
            # Return minimal valid data
            return await self._generate_minimal_data()
    
    def should_update_parameters(self, 
                               update_interval_seconds: int = 300) -> bool:
        """
        Check if parameters should be updated based on time interval.
        
        Args:
            update_interval_seconds: Minimum time between updates
            
        Returns:
            True if parameters should be updated
        """
        if self._last_optimization_time == 0.0:
            return True  # First optimization
        
        elapsed = time.time() - self._last_optimization_time
        return elapsed >= update_interval_seconds
    
    def get_last_optimization_result(self) -> Optional[OptimizationResult]:
        """Get the result of the most recent optimization."""
        return self._last_optimization_result
    
    def get_optimization_status(self) -> Dict[str, Any]:
        """
        Get comprehensive optimization status and health metrics.
        
        Returns:
            Dictionary with optimization status information
        """
        current_time = time.time()
        time_since_last = (current_time - self._last_optimization_time 
                          if self._last_optimization_time > 0 else 0)
        
        success_rate = ((self._optimization_count - self._failed_optimizations) / 
                       self._optimization_count if self._optimization_count > 0 else 0)
        
        return {
            'optimization_count': self._optimization_count,
            'failed_optimizations': self._failed_optimizations,
            'success_rate': success_rate,
            'last_optimization_time': self._last_optimization_time,
            'time_since_last_seconds': time_since_last,
            'avg_optimization_time_seconds': self._avg_optimization_time,
            'total_optimization_time_seconds': self._total_optimization_time,
            'last_result': {
                'entry_threshold_pct': (self._last_optimization_result.entry_threshold_pct 
                                      if self._last_optimization_result else None),
                'exit_threshold_pct': (self._last_optimization_result.exit_threshold_pct 
                                     if self._last_optimization_result else None),
                'confidence_score': (self._last_optimization_result.confidence_score 
                                   if self._last_optimization_result else None),
            } if self._last_optimization_result else None,
            'optimizer_stats': self.optimizer.get_optimization_stats()
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get health status of the optimization bridge.
        
        Returns:
            Dictionary with health indicators
        """
        status = self.get_optimization_status()
        
        # Determine health status
        is_healthy = True
        health_issues = []
        
        # Check success rate
        if status['success_rate'] < 0.8:
            is_healthy = False
            health_issues.append("Low optimization success rate")
        
        # Check if optimizations are taking too long
        if status['avg_optimization_time_seconds'] > 30.0:
            is_healthy = False
            health_issues.append("Optimization taking too long")
        
        # Check if we have recent optimization
        if status['time_since_last_seconds'] > 900:  # 15 minutes
            is_healthy = False
            health_issues.append("No recent optimization")
        
        # Check confidence score
        if (self._last_optimization_result and 
            self._last_optimization_result.confidence_score < 0.5):
            health_issues.append("Low confidence in optimization")
        
        return {
            'is_healthy': is_healthy,
            'health_issues': health_issues,
            'status': status
        }
    
    def reset_statistics(self) -> None:
        """Reset optimization statistics (for testing/debugging)."""
        self._optimization_count = 0
        self._failed_optimizations = 0
        self._total_optimization_time = 0.0
        self._avg_optimization_time = 0.0
        print("📊 Optimization statistics reset")
    
    def _validate_optimization_result(self, result: OptimizationResult) -> bool:
        """
        Validate optimization result before using it.
        
        Args:
            result: Optimization result to validate
            
        Returns:
            True if result is valid
        """
        try:
            # Basic sanity checks
            if result.entry_threshold_pct <= 0 or result.exit_threshold_pct <= 0:
                print(f"❌ Invalid thresholds: entry={result.entry_threshold_pct}, exit={result.exit_threshold_pct}")
                return False
            
            if result.entry_threshold_pct <= result.exit_threshold_pct:
                print(f"❌ Entry threshold must be > exit threshold")
                return False
            
            if result.entry_threshold_pct > 5.0:  # Sanity check: no more than 5%
                print(f"❌ Entry threshold too high: {result.entry_threshold_pct}%")
                return False
            
            if result.confidence_score < 0.0 or result.confidence_score > 1.0:
                print(f"❌ Invalid confidence score: {result.confidence_score}")
                return False
            
            # Use optimizer's built-in validation
            if not self.optimizer.validate_parameters(
                result.entry_threshold_pct, 
                result.exit_threshold_pct
            ):
                print(f"❌ Optimizer validation failed")
                return False
            
            return True
            
        except Exception as e:
            print(f"❌ Validation error: {e}")
            return False
    
    async def _generate_fallback_data(self, hours: int) -> pd.DataFrame:
        """Generate fallback market data when real data is unavailable."""
        import numpy as np
        
        # Generate basic mock data
        num_points = hours * 12  # 5-minute intervals
        timestamps = pd.date_range(
            start=pd.Timestamp.now() - pd.Timedelta(hours=hours),
            periods=num_points,
            freq='5T'
        )
        
        # Simple random walk with mean reversion
        base_price = 0.0001
        np.random.seed(int(time.time()) % 1000)  # Different seed each time
        
        prices = [base_price]
        for i in range(1, num_points):
            change = np.random.normal(-0.01 * (prices[-1] - base_price), 0.000005)
            prices.append(max(0.00001, prices[-1] + change))
        
        prices = np.array(prices)
        spread = prices * 0.002
        
        return pd.DataFrame({
            'timestamp': timestamps,
            'spot_ask_price': prices + spread/2,
            'spot_bid_price': prices - spread/2,
            'fut_ask_price': prices + spread/2 * 1.1,
            'fut_bid_price': prices - spread/2 * 1.1,
        })
    
    async def _generate_minimal_data(self) -> pd.DataFrame:
        """Generate minimal valid data for emergency fallback."""
        timestamps = pd.date_range(
            start=pd.Timestamp.now() - pd.Timedelta(hours=1),
            periods=12,  # 12 points = 1 hour of 5-minute data
            freq='5T'
        )
        
        base_price = 0.0001
        
        return pd.DataFrame({
            'timestamp': timestamps,
            'spot_ask_price': [base_price] * 12,
            'spot_bid_price': [base_price * 0.999] * 12,
            'fut_ask_price': [base_price * 1.001] * 12,
            'fut_bid_price': [base_price] * 12,
        })