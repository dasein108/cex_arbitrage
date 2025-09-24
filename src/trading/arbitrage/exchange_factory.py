"""
Exchange Factory

Factory pattern implementation for creating and managing exchange instances.
Eliminates code duplication and provides clean abstraction for exchange creation.

HFT COMPLIANT: Optimized exchange initialization with connection pooling.
"""

import asyncio
from infrastructure.logging import get_logger
import time
from typing import Dict, Any, List, Optional, Type
from dataclasses import dataclass

from infrastructure.config.config_manager import config
from infrastructure.exceptions.exchange import BaseExchangeError
from exchanges.mexc.private_exchange import MexcPrivateExchange as MexcExchange
from exchanges.gateio.gateio_exchange import GateioExchange
from infrastructure.data_structures.common import Symbol, AssetName, ExchangeStatus, ExchangeName
from interfaces.exchanges.base.base_private_exchange import BasePrivateExchangeInterface
from interfaces.factories.exchange_factory_interface import (
    ExchangeFactoryInterface, 
    InitializationStrategy as BaseInitializationStrategy
)

logger = get_logger('arbitrage.exchange_factory')


# Use the base InitializationStrategy from the interface
InitializationStrategy = BaseInitializationStrategy


@dataclass
class ExchangeCredentials:
    """Credentials for exchange API access."""
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    
    @property
    def has_private_access(self) -> bool:
        """Check if private API credentials are available."""
        return bool(self.api_key and self.secret_key)
    
    def validate(self) -> List[str]:
        """Validate credentials format."""
        errors = []
        
        if self.api_key:
            if len(self.api_key) < 10:
                errors.append("API key appears too short")
            if ' ' in self.api_key:
                errors.append("API key contains spaces")
        
        if self.secret_key:
            if len(self.secret_key) < 20:
                errors.append("Secret key appears too short")
            if ' ' in self.secret_key:
                errors.append("Secret key contains spaces")
        
        return errors


@dataclass
class ExchangeInitResult:
    """Result of exchange initialization attempt."""
    exchange_name: str
    success: bool
    exchange: Optional[BasePrivateExchangeInterface] = None
    error: Optional[Exception] = None
    attempts: int = 1
    initialization_time: float = 0.0
    
    @property
    def failed(self) -> bool:
        """Check if initialization failed."""
        return not self.success


class ExchangeFactory(ExchangeFactoryInterface):
    """
    Factory for creating and managing exchange instances.
    
    Implements ExchangeFactoryInterface for dependency injection capability.
    
    Responsibilities:
    - Create exchange instances with proper credentials
    - Initialize exchanges with BaseExchangeFactory infrastructure
    - Manage exchange lifecycle and operations
    - Provide unified interface for exchange operations
    """
    
    # Exchange class registry
    EXCHANGE_CLASSES: Dict[str, Type[BasePrivateExchangeInterface]] = {
        'MEXC': MexcExchange,
        'GATEIO': GateioExchange,
    }
    
    # Default symbols for initialization
    DEFAULT_SYMBOLS = [
        Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
        Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
    ]
    
    def __init__(self):
        self.exchanges: Dict[str, BasePrivateExchangeInterface] = {}
        self._initialization_timeout = 10.0  # seconds
        self._retry_attempts = 3
        self._retry_delay = 2.0  # seconds
        self._initialization_results: List[ExchangeInitResult] = []
        
    def _get_credentials(self, exchange_name: str) -> ExchangeCredentials:
        """
        Retrieve credentials for specified exchange.
        
        Args:
            exchange_name: Name of the exchange
            
        Returns:
            ExchangeCredentials instance
        """
        credentials = config.get_exchange_credentials(exchange_name.lower())
        return ExchangeCredentials(
            api_key=credentials.get('api_key', ''),
            secret_key=credentials.get('secret_key', '')
        )
    
    def _get_exchange_class(self, exchange_name: str) -> Type[BasePrivateExchangeInterface]:
        """
        Get exchange class for specified exchange name.
        
        Args:
            exchange_name: Name of the exchange
            
        Returns:
            Exchange class
            
        Raises:
            ValueError: If exchange is not supported
        """
        if exchange_name not in self.EXCHANGE_CLASSES:
            raise ValueError(f"Unsupported exchange: {exchange_name}")
        return self.EXCHANGE_CLASSES[exchange_name]
    
    async def create_exchange(
        self, 
        exchange_name: str,
        symbols: Optional[List[Symbol]] = None,
        max_attempts: Optional[int] = None,
    ) -> BasePrivateExchangeInterface:
        """
        Create and initialize exchange instance.
        
        Args:
            exchange_name: Name of the exchange
            symbols: Symbols to initialize (uses defaults if None)
            max_attempts: Maximum retry attempts (uses default if None)
            
        Returns:
            Initialized exchange instance
            
        Raises:
            ExchangeAPIError: If exchange creation fails after all retries
        """
        start_time = time.time()
        attempts = max_attempts or self._retry_attempts
        last_error = None
        
        for attempt in range(1, attempts + 1):
            try:
                logger.info(f"Creating {exchange_name} exchange (attempt {attempt}/{attempts})...")
                
                # Validate exchange name
                if exchange_name not in self.EXCHANGE_CLASSES:
                    available = list(self.EXCHANGE_CLASSES.keys())
                    raise ValueError(f"Unsupported exchange: {exchange_name}. Available: {available}")
                
                
                # Get and validate credentials
                credentials = self._get_credentials(exchange_name)
                credential_errors = credentials.validate()
                if credential_errors:
                    logger.warning(f"Credential validation issues for {exchange_name}: {', '.join(credential_errors)}")
                
                # Log credential availability
                if credentials.has_private_access:
                    logger.info(f"Private credentials available for {exchange_name}")
                    key_preview = self._get_key_preview(credentials.api_key)
                    logger.info(f"API Key: {key_preview}")
                else:
                    logger.warning(f"No private credentials for {exchange_name} - public mode only")
                
                # Get exchange class
                exchange_class = self._get_exchange_class(exchange_name)
                
                # Create exchange instance with enhanced validation
                exchange = await self._create_exchange_instance_enhanced(
                    exchange_class, 
                    credentials, 
                    exchange_name
                )
                
                # Initialize with symbols and validation
                await self._initialize_exchange_with_validation(
                    exchange, 
                    exchange_name, 
                    symbols or self.DEFAULT_SYMBOLS
                )
                
                # Store exchange instance
                self.exchanges[exchange_name] = exchange
                
                # Record successful initialization
                init_time = time.time() - start_time
                self._initialization_results.append(
                    ExchangeInitResult(
                        exchange_name=exchange_name,
                        success=True,
                        exchange=exchange,
                        attempts=attempt,
                        initialization_time=init_time
                    )
                )
                
                logger.info(f"Successfully created {exchange_name} exchange in {init_time:.2f}s")
                
                return exchange
                
            except Exception as e:
                last_error = e
                logger.error(f"Attempt {attempt} failed for {exchange_name}: {e}")
                
                if attempt < attempts:
                    wait_time = self._retry_delay * attempt
                    logger.info(f"Retrying {exchange_name} in {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time)
                else:
                    # Record failed initialization
                    init_time = time.time() - start_time
                    self._initialization_results.append(
                        ExchangeInitResult(
                            exchange_name=exchange_name,
                            success=False,
                            error=e,
                            attempts=attempt,
                            initialization_time=init_time
                        )
                    )
        
        # All attempts failed
        error_msg = f"Failed to create {exchange_name} after {attempts} attempts. Last error: {last_error}"
        logger.error(error_msg)
        raise BaseExchangeError(500, error_msg)
    
    async def _create_exchange_instance_enhanced(
        self,
        exchange_class: Type[BasePrivateExchangeInterface],
        credentials: ExchangeCredentials,
        exchange_name: str,
    ) -> BasePrivateExchangeInterface:
        """Create exchange instance."""
        try:
            # Create basic exchange instance
            if credentials.has_private_access:
                exchange = exchange_class(
                    api_key=credentials.api_key,
                    secret_key=credentials.secret_key
                )
            else:
                exchange = exchange_class()
            
            # Validate instance creation
            if not isinstance(exchange, BasePrivateExchangeInterface):
                raise ValueError(f"Exchange {exchange_name} does not implement BasePrivateExchangeInterface")
            
            return exchange
            
        except Exception as e:
            raise BaseExchangeError(500, f"Failed to instantiate {exchange_name}: {e}")
    
    async def _create_exchange_instance(
        self,
        exchange_class: Type[BasePrivateExchangeInterface],
        credentials: ExchangeCredentials,
        exchange_name: str
    ) -> BasePrivateExchangeInterface:
        """Create exchange instance with proper error handling (legacy method)."""
        return await self._create_exchange_instance_enhanced(
            exchange_class, credentials, exchange_name
        )
    
    async def _initialize_exchange_with_validation(
        self,
        exchange: BasePrivateExchangeInterface,
        name: str,
        symbols: List[Symbol]
    ) -> None:
        """Initialize exchange with comprehensive validation."""
        logger.info(f"Initializing {name} with {len(symbols)} symbols...")
        
        # Validate symbols
        if not symbols:
            raise ValueError(f"No symbols provided for {name} initialization")
        
        try:
            # Initialize exchange with timeout
            await asyncio.wait_for(
                exchange.initialize(symbols),
                timeout=self._initialization_timeout
            )
        except asyncio.TimeoutError:
            raise BaseExchangeError(504, f"{name} initialization timeout ({self._initialization_timeout}s)")
        except Exception as e:
            raise BaseExchangeError(500, f"{name} initialization failed: {e}")
        
        # Wait for connection establishment
        await asyncio.sleep(1)
        
        # Comprehensive status validation
        status = exchange.status
        logger.info(f"{name} initialized - Status: {status.name}")
        
        if status == ExchangeStatus.INACTIVE:
            raise BaseExchangeError(500, f"{name} failed to activate - check credentials and connectivity")
        elif status == ExchangeStatus.ERROR:
            raise BaseExchangeError(500, f"{name} entered error state during initialization")
        
        # Validate symbol loading
        active_symbols = getattr(exchange, 'active_symbols', [])
        if len(active_symbols) == 0:
            logger.warning(f"{name} has no active symbols after initialization")
        else:
            logger.info(f"{name} loaded {len(active_symbols)} active symbols")
    
    
    async def create_exchanges(
        self,
        exchange_names: List[str],
        strategy: InitializationStrategy = InitializationStrategy.CONTINUE_ON_ERROR,
        symbols: Optional[List[Symbol]] = None
    ) -> Dict[str, BasePrivateExchangeInterface]:
        """
        Create multiple exchanges with intelligent error handling.
        
        Args:
            exchange_names: List of exchange names to create
            strategy: How to handle initialization failures
            symbols: Symbols to initialize (uses defaults if None)
            
        Returns:
            Dictionary of successfully initialized exchanges
        """
        if not exchange_names:
            raise ValueError("No exchange names provided")
        
        logger.info(f"Creating {len(exchange_names)} exchanges with {strategy.value} strategy...")
        
        # Clear previous results
        self._initialization_results = []
        
        if strategy == InitializationStrategy.FAIL_FAST:
            return await self._create_exchanges_fail_fast(exchange_names, symbols)
        elif strategy == InitializationStrategy.CONTINUE_ON_ERROR:
            return await self._create_exchanges_continue(exchange_names, symbols)
        elif strategy == InitializationStrategy.RETRY_WITH_BACKOFF:
            return await self._create_exchanges_with_retry(exchange_names, symbols)
        else:
            raise ValueError(f"Unknown initialization strategy: {strategy}")
    
    async def _create_exchanges_fail_fast(
        self, 
        exchange_names: List[str],
        symbols: Optional[List[Symbol]]
    ) -> Dict[str, BasePrivateExchangeInterface]:
        """Create exchanges with fail-fast strategy."""
        for name in exchange_names:
            exchange = await self.create_exchange(name, symbols, max_attempts=1)
            self.exchanges[name] = exchange
        
        self._log_exchange_summary()
        return self.exchanges
    
    async def _create_exchanges_continue(
        self, 
        exchange_names: List[str],
        symbols: Optional[List[Symbol]]
    ) -> Dict[str, BasePrivateExchangeInterface]:
        """Create exchanges with continue-on-error strategy."""
        tasks = []
        for name in exchange_names:
            tasks.append(self._create_exchange_safe(name, symbols))
        
        # Create exchanges concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for name, result in zip(exchange_names, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to create {name}: {result}")
            elif result:
                self.exchanges[name] = result
        
        if not self.exchanges:
            raise BaseExchangeError(500, "No exchanges could be initialized")
        
        self._log_exchange_summary()
        return self.exchanges
    
    async def _create_exchanges_with_retry(
        self, 
        exchange_names: List[str],
        symbols: Optional[List[Symbol]]
    ) -> Dict[str, BasePrivateExchangeInterface]:
        """Create exchanges with retry strategy."""
        failed_exchanges = []
        
        # First attempt - concurrent
        await self._create_exchanges_continue(exchange_names, symbols)
        
        # Identify failures
        for name in exchange_names:
            if name not in self.exchanges:
                failed_exchanges.append(name)
        
        # Retry failed exchanges with backoff
        if failed_exchanges:
            logger.info(f"Retrying {len(failed_exchanges)} failed exchanges...")
            
            for attempt in range(2, self._retry_attempts + 1):
                if not failed_exchanges:
                    break
                
                retry_tasks = []
                for name in failed_exchanges:
                    retry_tasks.append(self._create_exchange_safe(name, symbols))
                
                # Wait with exponential backoff
                wait_time = self._retry_delay * (2 ** (attempt - 2))
                logger.info(f"Waiting {wait_time:.1f}s before retry attempt {attempt}...")
                await asyncio.sleep(wait_time)
                
                # Execute retries
                results = await asyncio.gather(*retry_tasks, return_exceptions=True)
                
                # Update failed list
                new_failed = []
                for name, result in zip(failed_exchanges, results):
                    if isinstance(result, Exception) or not result:
                        new_failed.append(name)
                    else:
                        self.exchanges[name] = result
                        logger.info(f"Successfully recovered {name} on attempt {attempt}")
                
                failed_exchanges = new_failed
        
        if not self.exchanges:
            raise BaseExchangeError(500, "No exchanges could be initialized after retries")
        
        self._log_exchange_summary()
        return self.exchanges
    
    async def _create_exchange_safe(
        self, 
        name: str, 
        symbols: Optional[List[Symbol]] = None
    ) -> Optional[BasePrivateExchangeInterface]:
        """
        Create exchange with comprehensive error handling.
        
        Args:
            name: Exchange name
            symbols: Symbols to initialize
            
        Returns:
            Exchange instance or None if failed
        """
        try:
            return await self.create_exchange(name, symbols)
        except Exception as e:
            logger.error(f"Safe creation failed for {name}: {e}")
            return None
    
    def _log_exchange_summary(self):
        """Log comprehensive summary of initialization results."""
        total_requested = len(self._initialization_results)
        successful = len([r for r in self._initialization_results if r.success])
        failed = total_requested - successful
        
        logger.info("Exchange Initialization Summary:")
        logger.info(f"  Requested: {total_requested}, Successful: {successful}, Failed: {failed}")
        logger.info(f"  Active exchanges: {list(self.exchanges.keys())}")
        
        # Log successful exchanges
        for name, exchange in self.exchanges.items():
            if exchange:
                status = exchange.status.name
                symbols = len(getattr(exchange, 'active_symbols', []))
                private = "Private" if exchange.has_private else "Public Only"
                
                # Find initialization result
                result = next((r for r in self._initialization_results if r.exchange_name == name), None)
                time_info = f" in {result.initialization_time:.2f}s" if result else ""
                attempts_info = f" (attempts: {result.attempts})" if result and result.attempts > 1 else ""
                
                logger.info(f"  ✅ {name}: {status} ({symbols} symbols, {private}){time_info}{attempts_info}")
        
        # Log failed exchanges
        for result in self._initialization_results:
            if result.failed:
                logger.error(f"  ❌ {result.exchange_name}: Failed after {result.attempts} attempts - {result.error}")
    
    def get_initialization_results(self) -> List[ExchangeInitResult]:
        """Get initialization results for monitoring and analysis."""
        return self._initialization_results.copy()
    
    def get_initialization_summary(self) -> Dict[str, Any]:
        """Get initialization summary as dictionary."""
        total_requested = len(self._initialization_results)
        successful = len([r for r in self._initialization_results if r.success])
        failed = total_requested - successful
        
        avg_init_time = 0.0
        if successful > 0:
            successful_results = [r for r in self._initialization_results if r.success]
            avg_init_time = sum(r.initialization_time for r in successful_results) / len(successful_results)
        
        return {
            'total_requested': total_requested,
            'successful': successful,
            'failed': failed,
            'success_rate': (successful / total_requested * 100) if total_requested > 0 else 0.0,
            'average_init_time': avg_init_time,
            'active_exchanges': list(self.exchanges.keys()),
            'initialization_results': [
                {
                    'exchange_name': r.exchange_name,
                    'success': r.success,
                    'attempts': r.attempts,
                    'initialization_time': r.initialization_time,
                    'error': str(r.error) if r.error else None
                }
                for r in self._initialization_results
            ]
        }
    
    def _get_key_preview(self, api_key: Optional[str]) -> str:
        """Get safe preview of API key for logging."""
        if not api_key:
            return "***"
        if len(api_key) > 8:
            return f"{api_key[:4]}...{api_key[-4:]}"
        return "***"
    
    async def close_all(self):
        """Close all exchange connections."""
        logger.info("Closing all exchange connections...")
        
        tasks = []
        for name, exchange in self.exchanges.items():
            if exchange:
                tasks.append(self._close_exchange(name, exchange))
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        self.exchanges.clear()
        logger.info("All exchanges closed")
    
    async def _close_exchange(self, name: str, exchange: BasePrivateExchangeInterface):
        """Close single exchange connection."""
        try:
            await exchange.close()
            logger.info(f"Closed {name} exchange")
        except Exception as e:
            logger.error(f"Error closing {name}: {e}")
    
    def get_exchange(self, name: str) -> Optional[BasePrivateExchangeInterface]:
        """Get exchange instance by name."""
        return self.exchanges.get(name)
    
    def get_active_exchanges(self) -> Dict[str, BasePrivateExchangeInterface]:
        """Get all active exchanges."""
        return {
            name: exchange
            for name, exchange in self.exchanges.items()
            if exchange and exchange.status == ExchangeStatus.ACTIVE
        }
    
    def get_factory_statistics(self) -> Dict[str, Any]:
        """Get comprehensive factory statistics."""
        return self.get_initialization_summary()

    # Interface implementation methods

    async def create_exchange(
        self,
        exchange_name: ExchangeName,
        symbols: Optional[List[Symbol]] = None
    ) -> BasePrivateExchangeInterface:
        """Create a single exchange instance."""
        exchanges = await self.create_exchanges([exchange_name], symbols=symbols)
        if str(exchange_name) not in exchanges:
            raise BaseExchangeError(f"Failed to create exchange: {exchange_name}")
        return exchanges[str(exchange_name)]

    def get_supported_exchanges(self) -> List[ExchangeName]:
        """Get list of supported exchange names."""
        return [ExchangeName("mexc"), ExchangeName("gateio")]

    def is_exchange_supported(self, exchange_name: ExchangeName) -> bool:
        """Check if an exchange is supported by this factory."""
        return str(exchange_name).lower() in ["mexc", "gateio"]

    async def health_check(self, exchange_name: ExchangeName) -> bool:
        """Perform health check on an exchange."""
        exchange = self.get_exchange(str(exchange_name))
        if not exchange:
            return False
        return exchange.status == ExchangeStatus.ACTIVE

    @property
    def managed_exchanges(self) -> Dict[str, BasePrivateExchangeInterface]:
        """Get currently managed exchange instances."""
        return self.exchanges.copy()