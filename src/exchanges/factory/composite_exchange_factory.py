"""
Composite Exchange Factory.

Factory for creating composite exchanges with REST+WebSocket integration.
Supports both public and private exchange creation with proper initialization
and error handling.
"""

import asyncio
from typing import Dict, List, Optional
from config.config_manager import HftConfig
from exchanges.structs.common import Symbol
from exchanges.interfaces.composite.spot.base_public_spot_composite import CompositePublicExchange
from exchanges.interfaces.composite.spot.base_private_spot_composite import CompositePrivateExchange
from infrastructure.logging import HFTLoggerFactory, HFTLoggerInterface
from infrastructure.exceptions.system import InitializationError

from .exchange_registry import ExchangeRegistry, ExchangePair, get_exchange_implementation


class CompositeExchangeFactory:
    """Factory for creating composite exchanges with REST+WS integration."""
    
    def __init__(self, config_manager: Optional[HftConfig] = None, logger: Optional[HFTLoggerInterface] = None):
        """
        Initialize composite exchange factory.
        
        Args:
            config_manager: Configuration manager instance
            logger: Optional logger instance
        """
        self.config_manager = config_manager or HftConfig()
        self.logger = logger or HFTLoggerFactory.create_logger("CompositeExchangeFactory", "INFO")
        self._exchange_registry = ExchangeRegistry()
        
        # Performance tracking
        self._created_exchanges: Dict[str, ExchangePair] = {}
        self._initialization_times: Dict[str, float] = {}
    
    async def create_public_exchange(self, 
                                   exchange_name: str, 
                                   symbols: Optional[List[Symbol]] = None) -> CompositePublicExchange:
        """
        Create public exchange for market data operations.
        
        Args:
            exchange_name: Name of the exchange (e.g., 'mexc_spot', 'gateio_spot')
            symbols: Optional list of symbols to initialize
            
        Returns:
            Initialized public exchange instance
            
        Raises:
            ValueError: If exchange name is unknown
            InitializationError: If exchange initialization fails
        """
        try:
            # Get implementation
            implementation = get_exchange_implementation(exchange_name)
            
            # Get configuration
            config = self.config_manager.get_exchange_config(exchange_name)
            
            # Create logger for this exchange
            exchange_logger = HFTLoggerFactory.create_logger(f"{exchange_name}_public", "INFO")
            
            # Create public exchange instance
            public_exchange = implementation.public_class(config, exchange_logger)
            
            # Initialize with symbols if provided
            if symbols:
                await public_exchange.initialize(symbols)
            else:
                await public_exchange.initialize()
            
            self.logger.info("Public exchange created successfully",
                           exchange=exchange_name,
                           symbols_count=len(symbols) if symbols else 0,
                           has_websocket=hasattr(public_exchange, '_public_ws'))
            
            return public_exchange
            
        except Exception as e:
            self.logger.error("Failed to create public exchange",
                            exchange=exchange_name,
                            error=str(e))
            raise InitializationError(f"Failed to create public exchange {exchange_name}: {e}")
    
    async def create_private_exchange(self, 
                                    exchange_name: str,
                                    symbols_info: Optional[object] = None) -> CompositePrivateExchange:
        """
        Create private exchange for trading operations.
        
        Args:
            exchange_name: Name of the exchange
            symbols_info: Optional symbols info object for initialization
            
        Returns:
            Initialized private exchange instance
            
        Raises:
            ValueError: If exchange name is unknown or credentials missing
            InitializationError: If exchange initialization fails
        """
        try:
            # Get implementation
            implementation = get_exchange_implementation(exchange_name)
            
            # Get configuration
            config = self.config_manager.get_exchange_config(exchange_name)
            
            # Check if credentials are available
            if not config.has_credentials():
                raise ValueError(f"No credentials configured for {exchange_name}")
            
            # Create logger for this exchange
            exchange_logger = HFTLoggerFactory.create_logger(f"{exchange_name}_private", "INFO")
            
            # Create private exchange instance
            private_exchange = implementation.private_class(config, exchange_logger)
            
            # Initialize with symbols info if provided
            if symbols_info:
                await private_exchange.initialize(symbols_info)
            else:
                await private_exchange.initialize()
            
            self.logger.info("Private exchange created successfully",
                           exchange=exchange_name,
                           has_websocket=hasattr(private_exchange, '_private_ws'),
                           has_credentials=True)
            
            return private_exchange
            
        except Exception as e:
            self.logger.error("Failed to create private exchange",
                            exchange=exchange_name,
                            error=str(e))
            raise InitializationError(f"Failed to create private exchange {exchange_name}: {e}")
    
    async def create_exchange_pair(self, 
                                 exchange_name: str,
                                 symbols: Optional[List[Symbol]] = None,
                                 private_enabled: bool = True) -> ExchangePair:
        """
        Create both public and private exchanges as a pair.
        
        Args:
            exchange_name: Name of the exchange
            symbols: Symbols to initialize public exchange with
            private_enabled: Whether to create private exchange
            
        Returns:
            ExchangePair with public and optionally private exchange
        """
        try:
            start_time = asyncio.get_event_loop().time()
            
            # Create public exchange
            public = await self.create_public_exchange(exchange_name, symbols)
            
            # Create private exchange if enabled and credentials available
            private = None
            if private_enabled:
                try:
                    # Pass symbols info from public exchange to private
                    symbols_info = getattr(public, 'symbols_info', None)
                    private = await self.create_private_exchange(exchange_name, symbols_info)
                except ValueError as e:
                    # No credentials available - this is okay for public-only usage
                    self.logger.info("Private exchange not created (no credentials)",
                                   exchange=exchange_name,
                                   reason=str(e))
                except Exception as e:
                    # Other initialization errors
                    self.logger.warning("Private exchange creation failed",
                                      exchange=exchange_name,
                                      error=str(e))
            
            # Create exchange pair
            pair = ExchangePair(public=public, private=private)
            
            # Track performance
            elapsed_time = asyncio.get_event_loop().time() - start_time
            self._initialization_times[exchange_name] = elapsed_time
            self._created_exchanges[exchange_name] = pair
            
            self.logger.info("Exchange pair created successfully",
                           exchange=exchange_name,
                           has_public=True,
                           has_private=private is not None,
                           symbols_count=len(symbols) if symbols else 0,
                           init_time_ms=round(elapsed_time * 1000, 2))
            
            return pair
            
        except Exception as e:
            self.logger.error("Failed to create exchange pair",
                            exchange=exchange_name,
                            error=str(e))
            raise InitializationError(f"Failed to create exchange pair {exchange_name}: {e}")
    
    async def create_multiple_exchanges(self, 
                                      exchange_names: List[str],
                                      symbols: Optional[List[Symbol]] = None,
                                      private_enabled: bool = True) -> Dict[str, ExchangePair]:
        """
        Create multiple exchanges concurrently for improved performance.
        
        Args:
            exchange_names: List of exchange names to create
            symbols: Symbols to initialize exchanges with
            private_enabled: Whether to create private exchanges
            
        Returns:
            Dictionary mapping exchange names to ExchangePair instances
        """
        self.logger.info("Creating multiple exchanges concurrently",
                        exchanges=exchange_names,
                        count=len(exchange_names))
        
        # Create tasks for concurrent execution
        tasks = [
            asyncio.create_task(
                self.create_exchange_pair(name, symbols, private_enabled),
                name=f"create_{name}"
            )
            for name in exchange_names
        ]
        
        # Wait for all exchanges to be created
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        exchange_map = {}
        successful_count = 0
        
        for exchange_name, result in zip(exchange_names, results):
            if isinstance(result, Exception):
                self.logger.error("Failed to create exchange",
                                exchange=exchange_name,
                                error=str(result))
                continue
            
            exchange_map[exchange_name] = result
            successful_count += 1
        
        self.logger.info("Multiple exchange creation completed",
                        requested=len(exchange_names),
                        successful=successful_count,
                        failed=len(exchange_names) - successful_count)
        
        return exchange_map
    
    def get_exchange_info(self, exchange_name: str) -> Dict:
        """Get information about an exchange."""
        implementation = ExchangeRegistry.get_implementation(exchange_name)
        if not implementation:
            return {}
        
        return {
            "name": exchange_name,
            "type": implementation.exchange_type.value,
            "features": list(implementation.features),
            "rate_limits": implementation.rate_limits,
            "supported_order_types": list(implementation.supported_order_types),
            "created": exchange_name in self._created_exchanges,
            "init_time_ms": self._initialization_times.get(exchange_name)
        }
    
    def list_available_exchanges(self) -> List[str]:
        """List all available exchanges."""
        return ExchangeRegistry.list_exchanges()
    
    def list_spot_exchanges(self) -> List[str]:
        """List available spot exchanges."""
        return ExchangeRegistry.list_spot_exchanges()
    
    
    async def close_all_exchanges(self):
        """Close all created exchanges."""
        if not self._created_exchanges:
            return
        
        self.logger.info("Closing all exchanges", count=len(self._created_exchanges))
        
        close_tasks = [
            pair.close() for pair in self._created_exchanges.values()
        ]
        
        await asyncio.gather(*close_tasks, return_exceptions=True)
        self._created_exchanges.clear()
        
        self.logger.info("All exchanges closed")
    
    def get_performance_stats(self) -> Dict:
        """Get factory performance statistics."""
        if not self._initialization_times:
            return {"exchanges_created": 0}
        
        times = list(self._initialization_times.values())
        return {
            "exchanges_created": len(times),
            "avg_init_time_ms": round(sum(times) / len(times) * 1000, 2),
            "min_init_time_ms": round(min(times) * 1000, 2),
            "max_init_time_ms": round(max(times) * 1000, 2),
            "total_init_time_ms": round(sum(times) * 1000, 2)
        }