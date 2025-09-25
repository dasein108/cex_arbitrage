"""
Trading-Specific Error Handlers

Specialized error handling for trading operations, order management,
and exchange-specific trading errors in HFT arbitrage systems.
"""

import asyncio
from typing import Dict, Any, Optional
from decimal import Decimal

from infrastructure.logging.interfaces import HFTLoggerInterface
from .handlers import ComposableErrorHandler, ErrorContext, ErrorSeverity


class TradingErrorHandler(ComposableErrorHandler):
    """
    Specialized error handling for trading operations.
    
    Handles order placement, balance management, rate limiting,
    and exchange-specific trading errors with HFT performance requirements.
    """
    
    def __init__(self, logger: HFTLoggerInterface, max_retries: int = 2, base_delay: float = 0.5):
        super().__init__(logger, max_retries, base_delay, "TradingErrorHandler")
        self._register_trading_handlers()
        
        # Performance optimization: pre-compile rate limit delays
        self._rate_limit_delays = {
            "order_placement": 1.0,
            "balance_query": 0.5,
            "market_data": 0.1,
            "account_info": 2.0
        }
    
    def _register_trading_handlers(self) -> None:
        """Register trading-specific exception handlers."""
        # Import exchange exceptions dynamically to avoid circular imports
        try:
            # These would be defined in exchanges module
            from exchanges.exceptions import (
                InsufficientFundsError,
                OrderNotFoundError, 
                RateLimitExceededError,
                ExchangeMaintenanceError,
                InvalidOrderError,
                MarketClosedError,
                PriceOutOfRangeError
            )
            
            self.register_handler(InsufficientFundsError, self._handle_insufficient_funds)
            self.register_handler(OrderNotFoundError, self._handle_order_not_found)
            self.register_handler(RateLimitExceededError, self._handle_rate_limit)
            self.register_handler(ExchangeMaintenanceError, self._handle_maintenance)
            self.register_handler(InvalidOrderError, self._handle_invalid_order)
            self.register_handler(MarketClosedError, self._handle_market_closed)
            self.register_handler(PriceOutOfRangeError, self._handle_price_out_of_range)
            
        except ImportError:
            # If exchange exceptions don't exist yet, register generic handlers
            self.logger.info("Exchange-specific exceptions not available, using generic handlers",
                           component=self.component_name)
        
        # Standard Python exceptions common in trading operations
        self.register_handler(ValueError, self._handle_validation_error)
        self.register_handler(TypeError, self._handle_type_error)
        self.register_handler(ZeroDivisionError, self._handle_zero_division)
    
    async def _handle_insufficient_funds(
        self, 
        exception: Exception, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle insufficient funds with balance refresh."""
        required_amount = getattr(exception, 'required_amount', None)
        available_amount = getattr(exception, 'available_amount', None)
        asset = getattr(exception, 'asset', 'unknown')
        
        self.logger.warning("Insufficient funds for trading operation",
                          component=self.component_name,
                          operation=context.operation,
                          asset=asset,
                          required_amount=str(required_amount) if required_amount else None,
                          available_amount=str(available_amount) if available_amount else None,
                          attempt=context.attempt)
        
        # Track insufficient funds patterns for risk management
        self.logger.metric("trading_insufficient_funds", 1,
                         tags={
                             "component": self.component_name,
                             "asset": asset,
                             "operation": context.operation
                         })
        
        # Trigger balance refresh if callback available
        if context.balance_refresh_callback:
            try:
                await context.balance_refresh_callback()
                
                self.logger.info("Balance refresh triggered after insufficient funds",
                               component=self.component_name,
                               operation=context.operation,
                               asset=asset)
                
            except Exception as refresh_error:
                self.logger.error("Balance refresh failed after insufficient funds",
                                component=self.component_name,
                                refresh_error=str(refresh_error),
                                refresh_exception_type=type(refresh_error).__name__)
    
    async def _handle_order_not_found(
        self, 
        exception: Exception, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle order not found errors with order status refresh."""
        order_id = getattr(exception, 'order_id', 'unknown')
        
        self.logger.warning("Order not found in exchange",
                          component=self.component_name,
                          operation=context.operation,
                          order_id=str(order_id),
                          attempt=context.attempt)
        
        # Track order tracking issues
        self.logger.metric("trading_order_not_found", 1,
                         tags={
                             "component": self.component_name,
                             "operation": context.operation
                         })
    
    async def _handle_rate_limit(
        self, 
        exception: Exception, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle rate limits with intelligent backoff."""
        retry_after = getattr(exception, 'retry_after', None)
        request_type = context.metadata.get('request_type', 'unknown') if context.metadata else 'unknown'
        
        # Use provided retry time or calculate based on operation type
        if retry_after:
            delay = float(retry_after)
        else:
            delay = self._rate_limit_delays.get(request_type, 1.0)
        
        self.logger.warning("Rate limit exceeded for trading operation",
                          component=self.component_name,
                          operation=context.operation,
                          request_type=request_type,
                          retry_after=delay,
                          attempt=context.attempt)
        
        # Track rate limiting patterns for optimization
        self.logger.metric("trading_rate_limited", 1,
                         tags={
                             "component": self.component_name,
                             "request_type": request_type,
                             "operation": context.operation
                         })
        
        # Apply intelligent backoff
        await asyncio.sleep(delay)
    
    async def _handle_maintenance(
        self, 
        exception: Exception, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle exchange maintenance with longer backoff."""
        estimated_duration = getattr(exception, 'estimated_duration', None)
        maintenance_type = getattr(exception, 'maintenance_type', 'unknown')
        
        self.logger.error("Exchange maintenance detected",
                        component=self.component_name,
                        operation=context.operation,
                        maintenance_type=maintenance_type,
                        estimated_duration=estimated_duration,
                        attempt=context.attempt)
        
        # Track maintenance events for operational planning
        self.logger.metric("trading_exchange_maintenance", 1,
                         tags={
                             "component": self.component_name,
                             "maintenance_type": maintenance_type
                         })
        
        # Apply longer delay for maintenance
        delay = float(estimated_duration) if estimated_duration else 30.0
        await asyncio.sleep(min(delay, 300.0))  # Cap at 5 minutes
    
    async def _handle_invalid_order(
        self, 
        exception: Exception, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle invalid order parameters."""
        validation_error = getattr(exception, 'validation_error', str(exception))
        order_params = context.metadata if context.metadata else {}
        
        self.logger.error("Invalid order parameters",
                        component=self.component_name,
                        operation=context.operation,
                        validation_error=validation_error,
                        order_params=order_params,
                        attempt=context.attempt)
        
        # Track parameter validation issues
        self.logger.metric("trading_invalid_order", 1,
                         tags={
                             "component": self.component_name,
                             "operation": context.operation
                         })
    
    async def _handle_market_closed(
        self, 
        exception: Exception, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle market closed conditions."""
        market = getattr(exception, 'market', 'unknown')
        next_open_time = getattr(exception, 'next_open_time', None)
        
        self.logger.warning("Market closed for trading operation",
                          component=self.component_name,
                          operation=context.operation,
                          market=market,
                          next_open_time=str(next_open_time) if next_open_time else None,
                          attempt=context.attempt)
        
        # Track market status for scheduling
        self.logger.metric("trading_market_closed", 1,
                         tags={
                             "component": self.component_name,
                             "market": market
                         })
    
    async def _handle_price_out_of_range(
        self, 
        exception: Exception, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle price out of range errors."""
        price = getattr(exception, 'price', None)
        min_price = getattr(exception, 'min_price', None)
        max_price = getattr(exception, 'max_price', None)
        symbol = getattr(exception, 'symbol', 'unknown')
        
        self.logger.warning("Order price out of allowed range",
                          component=self.component_name,
                          operation=context.operation,
                          symbol=str(symbol),
                          price=str(price) if price else None,
                          min_price=str(min_price) if min_price else None,
                          max_price=str(max_price) if max_price else None,
                          attempt=context.attempt)
        
        # Track price validation issues
        self.logger.metric("trading_price_out_of_range", 1,
                         tags={
                             "component": self.component_name,
                             "symbol": str(symbol)
                         })
    
    async def _handle_validation_error(
        self, 
        exception: ValueError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle general validation errors in trading operations."""
        self.logger.warning("Trading operation validation error",
                          component=self.component_name,
                          operation=context.operation,
                          validation_error=str(exception),
                          attempt=context.attempt,
                          metadata=context.metadata)
        
        # Track validation patterns
        self.logger.metric("trading_validation_error", 1,
                         tags={"component": self.component_name})
    
    async def _handle_type_error(
        self, 
        exception: TypeError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle type errors in trading calculations."""
        self.logger.error("Trading operation type error",
                        component=self.component_name,
                        operation=context.operation,
                        type_error=str(exception),
                        attempt=context.attempt,
                        metadata=context.metadata)
        
        # Track type safety issues
        self.logger.metric("trading_type_error", 1,
                         tags={"component": self.component_name})
    
    async def _handle_zero_division(
        self, 
        exception: ZeroDivisionError, 
        context: ErrorContext, 
        severity: ErrorSeverity
    ) -> None:
        """Handle zero division in trading calculations."""
        self.logger.error("Zero division in trading calculation",
                        component=self.component_name,
                        operation=context.operation,
                        calculation_context=context.metadata,
                        attempt=context.attempt)
        
        # Track calculation safety issues
        self.logger.metric("trading_zero_division", 1,
                         tags={
                             "component": self.component_name,
                             "operation": context.operation
                         })