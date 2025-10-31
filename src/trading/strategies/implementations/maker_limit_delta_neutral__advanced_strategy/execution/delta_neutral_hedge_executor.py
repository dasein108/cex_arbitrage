"""
Delta-Neutral Hedge Executor for Maker Limit Strategy

Executes immediate futures hedges to maintain delta neutrality when spot orders fill.
Optimized for HFT performance with <100ms hedge execution targets and comprehensive
position tracking for delta-neutral market making.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Optional, Dict
from enum import Enum

from exchanges.structs import Side, Order, OrderStatus, OrderType, TimeInForce
from exchanges.interfaces.composite.base_private_composite import BasePrivateComposite
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.config.maker_limit_config import MakerLimitConfig
from trading.strategies.implementations.maker_limit_delta_neutral__advanced_strategy.execution.maker_limit_engine import OrderFillEvent, OrderPlacementParams
from infrastructure.logging import HFTLoggerInterface


class HedgeExecutionStatus(Enum):
    """Hedge execution status types"""
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"


@dataclass
class HedgeResult:
    """Result of hedge execution"""
    success: bool
    status: HedgeExecutionStatus
    hedge_order: Optional[Order] = None
    execution_time_ms: float = 0.0
    net_position_delta: float = 0.0
    error: Optional[str] = None
    requires_manual_intervention: bool = False
    
    # Execution details
    hedge_price: Optional[float] = None
    hedge_quantity: float = 0.0
    slippage_bps: float = 0.0
    
    def is_critical_failure(self) -> bool:
        """Check if this is a critical hedge failure requiring immediate attention"""
        return self.requires_manual_intervention or self.status == HedgeExecutionStatus.FAILED


@dataclass
class PositionSnapshot:
    """Snapshot of current position state"""
    timestamp: float
    net_spot_position: float
    net_futures_position: float
    net_delta: float
    total_spot_volume: float
    total_futures_volume: float
    is_delta_neutral: bool
    
    def calculate_exposure_ratio(self, base_position_size: float) -> float:
        """Calculate position exposure as ratio of base position size"""
        if base_position_size == 0:
            return 0.0
        return abs(self.net_delta) / base_position_size


class DeltaNeutralHedgeExecutor:
    """Execute immediate futures hedges to maintain delta neutrality"""
    
    def __init__(self, futures_exchange: BasePrivateComposite,
                 config: MakerLimitConfig, logger: HFTLoggerInterface):
        self.futures_exchange = futures_exchange
        self.config = config
        self.logger = logger
        
        # Position tracking
        self.net_spot_position = 0.0
        self.net_futures_position = 0.0
        self.total_spot_volume = 0.0
        self.total_futures_volume = 0.0
        
        # Hedge execution parameters
        self.hedge_execution_timeout = config.hedge_execution_timeout_ms / 1000  # Convert to seconds
        self.max_slippage_bps = 100  # 1% max acceptable slippage
        
        # Performance tracking
        self.hedge_attempts = 0
        self.successful_hedges = 0
        self.failed_hedges = 0
        self.total_execution_time = 0.0
        self.critical_failures = 0
        
        # Position history for analysis
        self.position_history: list[PositionSnapshot] = []
        self.hedge_history: list[HedgeResult] = []
        
        # Emergency state
        self.emergency_mode = False
        self.last_critical_failure = 0.0
        
    async def execute_hedge(self, fill_event: OrderFillEvent) -> HedgeResult:
        """Execute immediate futures hedge for spot fill with HFT optimization"""
        
        hedge_start_time = time.time()
        self.hedge_attempts += 1
        
        try:
            # Calculate hedge parameters
            hedge_side = Side.SELL if fill_event.side == Side.BUY else Side.BUY
            hedge_quantity = fill_event.fill_quantity
            
            # Update spot position tracking
            spot_position_delta = (
                fill_event.fill_quantity if fill_event.side == Side.BUY 
                else -fill_event.fill_quantity
            )
            self.net_spot_position += spot_position_delta
            self.total_spot_volume += fill_event.fill_quantity
            
            # Log hedge initiation
            self.logger.info("Initiating hedge execution", extra={
                'spot_fill_side': fill_event.side.name,
                'spot_fill_price': fill_event.fill_price,
                'spot_fill_quantity': fill_event.fill_quantity,
                'hedge_side': hedge_side.name,
                'hedge_quantity': hedge_quantity,
                'current_spot_position': self.net_spot_position
            })
            
            # Execute market hedge order with timeout
            hedge_result = await self._execute_market_hedge(
                hedge_side, hedge_quantity, fill_event.fill_price
            )
            
            if hedge_result.success:
                # Update futures position tracking
                futures_position_delta = (
                    hedge_quantity if hedge_side == Side.BUY 
                    else -hedge_quantity
                )
                self.net_futures_position += futures_position_delta
                self.total_futures_volume += hedge_quantity
                
                # Calculate final metrics
                hedge_result.net_position_delta = self._calculate_net_delta()
                hedge_result.execution_time_ms = (time.time() - hedge_start_time) * 1000
                
                # Check delta neutrality
                is_neutral = self.config.is_within_delta_tolerance(
                    hedge_result.net_position_delta, 
                    self.config.position_size_usd / fill_event.fill_price
                )
                
                self.successful_hedges += 1
                self.total_execution_time += hedge_result.execution_time_ms
                
                self.logger.info("Hedge executed successfully", extra={
                    'hedge_price': hedge_result.hedge_price,
                    'hedge_quantity': hedge_result.hedge_quantity,
                    'execution_time_ms': hedge_result.execution_time_ms,
                    'net_delta': hedge_result.net_position_delta,
                    'is_delta_neutral': is_neutral,
                    'slippage_bps': hedge_result.slippage_bps,
                    'success_rate': self.get_success_rate()
                })
                
            else:
                # Handle hedge failure
                self.failed_hedges += 1
                hedge_result.execution_time_ms = (time.time() - hedge_start_time) * 1000
                
                if hedge_result.is_critical_failure():
                    self.critical_failures += 1
                    self.last_critical_failure = time.time()
                    self.emergency_mode = True
                
                self.logger.error("Hedge execution failed", extra={
                    'error': hedge_result.error,
                    'status': hedge_result.status.name,
                    'execution_time_ms': hedge_result.execution_time_ms,
                    'requires_intervention': hedge_result.requires_manual_intervention,
                    'net_unhedged_position': self.net_spot_position,
                    'failure_rate': self.get_failure_rate()
                })
            
            # Record position snapshot
            self._record_position_snapshot(hedge_result.success)
            
            # Add to hedge history
            self.hedge_history.append(hedge_result)
            if len(self.hedge_history) > 1000:  # Keep last 1000 hedges
                self.hedge_history = self.hedge_history[-1000:]
            
            return hedge_result
            
        except Exception as e:
            execution_time = (time.time() - hedge_start_time) * 1000
            self.failed_hedges += 1
            
            error_result = HedgeResult(
                success=False,
                status=HedgeExecutionStatus.FAILED,
                error=str(e),
                execution_time_ms=execution_time,
                requires_manual_intervention=True
            )
            
            self.logger.critical("Critical hedge execution error", extra={
                'error': str(e),
                'execution_time_ms': execution_time,
                'spot_fill_details': {
                    'side': fill_event.side.name,
                    'price': fill_event.fill_price,
                    'quantity': fill_event.fill_quantity
                }
            })
            
            return error_result
    
    async def _execute_market_hedge(self, side: Side, quantity: float, 
                                  reference_price: float) -> HedgeResult:
        """Execute market hedge order with timeout and slippage monitoring"""
        
        try:
            # Place market order
            hedge_params = OrderPlacementParams(
                symbol=str(self.config.symbol),
                side=side,
                quantity=quantity,
                price=0.0,  # Market order
                order_type=OrderType.MARKET,
                time_in_force=TimeInForce.IOC
            )
            
            hedge_order = await self.futures_exchange.place_order(
                symbol=hedge_params.symbol,
                side=hedge_params.side,
                order_type=hedge_params.order_type,
                quantity=hedge_params.quantity,
                time_in_force=hedge_params.time_in_force
            )
            
            if not hedge_order:
                return HedgeResult(
                    success=False,
                    status=HedgeExecutionStatus.FAILED,
                    error="Order placement returned None",
                    requires_manual_intervention=True
                )
            
            # Wait for hedge confirmation with timeout
            confirmation_result = await self._wait_for_hedge_confirmation(
                hedge_order.order_id, reference_price
            )
            
            return confirmation_result
            
        except Exception as e:
            return HedgeResult(
                success=False,
                status=HedgeExecutionStatus.FAILED,
                error=f"Market hedge execution failed: {e}",
                requires_manual_intervention=True
            )
    
    async def _wait_for_hedge_confirmation(self, order_id: str, 
                                         reference_price: float) -> HedgeResult:
        """Wait for hedge order confirmation with timeout and slippage monitoring"""
        
        start_time = time.time()
        check_interval = 0.01  # 10ms check interval for HFT
        
        while (time.time() - start_time) < self.hedge_execution_timeout:
            try:
                order_status = await self.futures_exchange.get_order_status(order_id)
                
                if order_status.status == OrderStatus.FILLED:
                    # Calculate slippage
                    execution_price = order_status.average_price or order_status.price
                    slippage_bps = self._calculate_slippage_bps(
                        reference_price, execution_price
                    )
                    
                    # Check if slippage is acceptable
                    if slippage_bps <= self.max_slippage_bps:
                        return HedgeResult(
                            success=True,
                            status=HedgeExecutionStatus.SUCCESS,
                            hedge_order=order_status,
                            hedge_price=execution_price,
                            hedge_quantity=order_status.filled_quantity,
                            slippage_bps=slippage_bps
                        )
                    else:
                        self.logger.warning(f"High slippage hedge: {slippage_bps:.2f}bps")
                        return HedgeResult(
                            success=True,  # Still successful but with high slippage
                            status=HedgeExecutionStatus.SUCCESS,
                            hedge_order=order_status,
                            hedge_price=execution_price,
                            hedge_quantity=order_status.filled_quantity,
                            slippage_bps=slippage_bps
                        )
                
                elif order_status.status == OrderStatus.PARTIALLY_FILLED:
                    # Handle partial fills - continue waiting
                    filled_quantity = order_status.filled_quantity
                    remaining_quantity = order_status.quantity - filled_quantity
                    
                    self.logger.warning(f"Partial hedge fill: {filled_quantity}/{order_status.quantity}")
                    
                    # For now, accept partial fills as success
                    if filled_quantity > 0:
                        execution_price = order_status.average_price or order_status.price
                        slippage_bps = self._calculate_slippage_bps(
                            reference_price, execution_price
                        )
                        
                        return HedgeResult(
                            success=True,
                            status=HedgeExecutionStatus.PARTIAL,
                            hedge_order=order_status,
                            hedge_price=execution_price,
                            hedge_quantity=filled_quantity,
                            slippage_bps=slippage_bps,
                            requires_manual_intervention=remaining_quantity > filled_quantity * 0.1  # >10% remaining
                        )
                
                elif order_status.status in [OrderStatus.CANCELLED, OrderStatus.REJECTED]:
                    return HedgeResult(
                        success=False,
                        status=HedgeExecutionStatus.REJECTED,
                        error=f"Hedge order {order_status.status.name}",
                        requires_manual_intervention=True
                    )
                
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                self.logger.warning(f"Error checking hedge status: {e}")
                await asyncio.sleep(check_interval)
        
        # Timeout reached
        return HedgeResult(
            success=False,
            status=HedgeExecutionStatus.TIMEOUT,
            error=f"Hedge confirmation timeout after {self.hedge_execution_timeout}s",
            requires_manual_intervention=True
        )
    
    def _calculate_slippage_bps(self, reference_price: float, 
                               execution_price: float) -> float:
        """Calculate slippage in basis points"""
        if reference_price == 0:
            return 0.0
        
        slippage = abs(execution_price - reference_price) / reference_price
        return slippage * 10000  # Convert to basis points
    
    def _calculate_net_delta(self) -> float:
        """Calculate net delta exposure (should be close to 0 for delta neutral)"""
        return self.net_spot_position + self.net_futures_position
    
    def _record_position_snapshot(self, hedge_success: bool):
        """Record current position snapshot for analysis"""
        net_delta = self._calculate_net_delta()
        is_neutral = self.config.is_within_delta_tolerance(
            net_delta, 
            self.config.position_size_usd / 100.0  # Approximate for tolerance
        )
        
        snapshot = PositionSnapshot(
            timestamp=time.time(),
            net_spot_position=self.net_spot_position,
            net_futures_position=self.net_futures_position,
            net_delta=net_delta,
            total_spot_volume=self.total_spot_volume,
            total_futures_volume=self.total_futures_volume,
            is_delta_neutral=is_neutral
        )
        
        self.position_history.append(snapshot)
        
        # Keep only last 500 snapshots
        if len(self.position_history) > 500:
            self.position_history = self.position_history[-500:]
    
    def get_success_rate(self) -> float:
        """Get hedge execution success rate"""
        if self.hedge_attempts == 0:
            return 0.0
        return self.successful_hedges / self.hedge_attempts
    
    def get_failure_rate(self) -> float:
        """Get hedge execution failure rate"""
        if self.hedge_attempts == 0:
            return 0.0
        return self.failed_hedges / self.hedge_attempts
    
    def get_average_execution_time(self) -> float:
        """Get average hedge execution time in milliseconds"""
        if self.successful_hedges == 0:
            return 0.0
        return self.total_execution_time / self.successful_hedges
    
    def get_current_position_summary(self) -> Dict[str, any]:
        """Get current position summary"""
        net_delta = self._calculate_net_delta()
        is_neutral = abs(net_delta) <= 0.001  # 0.001 tolerance
        
        return {
            'net_spot_position': self.net_spot_position,
            'net_futures_position': self.net_futures_position,
            'net_delta': net_delta,
            'is_delta_neutral': is_neutral,
            'total_spot_volume': self.total_spot_volume,
            'total_futures_volume': self.total_futures_volume,
            'position_snapshots': len(self.position_history)
        }
    
    def get_performance_stats(self) -> Dict[str, any]:
        """Get comprehensive hedge executor performance statistics"""
        return {
            'hedge_attempts': self.hedge_attempts,
            'successful_hedges': self.successful_hedges,
            'failed_hedges': self.failed_hedges,
            'critical_failures': self.critical_failures,
            'success_rate': self.get_success_rate(),
            'failure_rate': self.get_failure_rate(),
            'average_execution_time_ms': self.get_average_execution_time(),
            'emergency_mode': self.emergency_mode,
            'last_critical_failure': self.last_critical_failure,
            'position_summary': self.get_current_position_summary()
        }
    
    def reset_emergency_mode(self):
        """Reset emergency mode (admin function)"""
        self.emergency_mode = False
        self.logger.info("Emergency mode reset - hedge executor operational")
    
    def force_position_reset(self):
        """Force reset position tracking (admin function - use with caution)"""
        self.net_spot_position = 0.0
        self.net_futures_position = 0.0
        self.total_spot_volume = 0.0
        self.total_futures_volume = 0.0
        
        self.logger.warning("Position tracking forcibly reset")
    
    async def emergency_flatten_position(self) -> HedgeResult:
        """Emergency function to flatten all positions"""
        net_delta = self._calculate_net_delta()
        
        if abs(net_delta) < 0.001:
            return HedgeResult(
                success=True,
                status=HedgeExecutionStatus.SUCCESS,
                error="No position to flatten"
            )
        
        # Determine side to flatten
        flatten_side = Side.SELL if net_delta > 0 else Side.BUY
        flatten_quantity = abs(net_delta)
        
        self.logger.critical("Emergency position flattening initiated", extra={
            'net_delta': net_delta,
            'flatten_side': flatten_side.name,
            'flatten_quantity': flatten_quantity
        })
        
        # Execute emergency flatten
        return await self._execute_market_hedge(
            flatten_side, flatten_quantity, 0.0  # Use 0 as reference for emergency
        )