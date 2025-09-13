"""
Exchange Factory

Factory pattern implementation for creating and managing exchange instances.
Eliminates code duplication and provides clean abstraction for exchange creation.

HFT COMPLIANT: Optimized exchange initialization with connection pooling.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Type
from dataclasses import dataclass

from common.config import config
from common.exceptions import ExchangeAPIError
from exchanges.mexc.mexc_exchange import MexcExchange
from exchanges.gateio.gateio_exchange import GateioExchange
from exchanges.interface.structs import Symbol, AssetName, ExchangeStatus
from exchanges.interface.base_exchange import BaseExchangeInterface

logger = logging.getLogger(__name__)


@dataclass
class ExchangeCredentials:
    """Credentials for exchange API access."""
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    
    @property
    def has_private_access(self) -> bool:
        """Check if private API credentials are available."""
        return bool(self.api_key and self.secret_key)


class ExchangeFactory:
    """
    Factory for creating and managing exchange instances.
    
    Responsibilities:
    - Create exchange instances with proper credentials
    - Initialize exchanges with default symbols
    - Manage exchange lifecycle
    - Provide unified interface for exchange operations
    """
    
    # Exchange class registry
    EXCHANGE_CLASSES: Dict[str, Type[BaseExchangeInterface]] = {
        'MEXC': MexcExchange,
        'GATEIO': GateioExchange,
    }
    
    # Default symbols for initialization
    DEFAULT_SYMBOLS = [
        Symbol(base=AssetName("BTC"), quote=AssetName("USDT")),
        Symbol(base=AssetName("ETH"), quote=AssetName("USDT")),
    ]
    
    def __init__(self):
        self.exchanges: Dict[str, BaseExchangeInterface] = {}
        self._initialization_timeout = 5.0  # seconds
        
    def _get_credentials(self, exchange_name: str) -> ExchangeCredentials:
        """
        Retrieve credentials for specified exchange.
        
        Args:
            exchange_name: Name of the exchange
            
        Returns:
            ExchangeCredentials instance
        """
        if exchange_name == 'MEXC':
            return ExchangeCredentials(
                api_key=config.MEXC_API_KEY,
                secret_key=config.MEXC_SECRET_KEY
            )
        elif exchange_name == 'GATEIO':
            return ExchangeCredentials(
                api_key=config.GATEIO_API_KEY,
                secret_key=config.GATEIO_SECRET_KEY
            )
        else:
            return ExchangeCredentials()
    
    def _get_exchange_class(self, exchange_name: str) -> Type[BaseExchangeInterface]:
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
        symbols: Optional[List[Symbol]] = None
    ) -> BaseExchangeInterface:
        """
        Create and initialize exchange instance.
        
        Args:
            exchange_name: Name of the exchange
            symbols: Symbols to initialize (uses defaults if None)
            
        Returns:
            Initialized exchange instance
            
        Raises:
            ExchangeAPIError: If exchange creation fails
        """
        try:
            logger.info(f"Creating {exchange_name} exchange...")
            
            # Get credentials
            credentials = self._get_credentials(exchange_name)
            
            # Log credential availability
            if credentials.has_private_access:
                logger.info(f"Private credentials available for {exchange_name}")
                key_preview = self._get_key_preview(credentials.api_key)
                logger.info(f"API Key: {key_preview}")
            else:
                logger.warning(f"No private credentials for {exchange_name} - public mode only")
            
            # Get exchange class
            exchange_class = self._get_exchange_class(exchange_name)
            
            # Create exchange instance
            if credentials.has_private_access:
                exchange = exchange_class(
                    api_key=credentials.api_key,
                    secret_key=credentials.secret_key
                )
            else:
                exchange = exchange_class()
            
            # Initialize with symbols
            await self._initialize_exchange(
                exchange, 
                exchange_name, 
                symbols or self.DEFAULT_SYMBOLS
            )
            
            # Store exchange instance
            self.exchanges[exchange_name] = exchange
            
            return exchange
            
        except Exception as e:
            logger.error(f"Failed to create {exchange_name} exchange: {e}")
            raise ExchangeAPIError(500, f"Exchange creation failed: {e}")
    
    async def _initialize_exchange(
        self,
        exchange: BaseExchangeInterface,
        name: str,
        symbols: List[Symbol]
    ) -> None:
        """
        Initialize exchange with symbols and validate connection.
        
        Args:
            exchange: Exchange instance to initialize
            name: Exchange name for logging
            symbols: Symbols to subscribe to
        """
        logger.info(f"Initializing {name} with {len(symbols)} symbols...")
        
        # Initialize exchange
        await exchange.init(symbols)
        
        # Wait for connection establishment
        await asyncio.sleep(1)
        
        # Check status
        status = exchange.status
        logger.info(f"{name} initialized - Status: {status.name}")
        
        if status == ExchangeStatus.INACTIVE:
            raise ExchangeAPIError(500, f"{name} failed to activate")
    
    async def create_exchanges(
        self,
        exchange_names: List[str],
        dry_run: bool = True
    ) -> Dict[str, BaseExchangeInterface]:
        """
        Create multiple exchanges concurrently.
        
        Args:
            exchange_names: List of exchange names to create
            dry_run: Whether in dry run mode (affects error handling)
            
        Returns:
            Dictionary of initialized exchanges
        """
        logger.info(f"Creating {len(exchange_names)} exchanges...")
        
        tasks = []
        for name in exchange_names:
            tasks.append(self._create_exchange_safe(name, dry_run))
        
        # Create exchanges concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for name, result in zip(exchange_names, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to create {name}: {result}")
                if not dry_run:
                    raise result
            else:
                self.exchanges[name] = result
        
        if not self.exchanges:
            raise ExchangeAPIError(500, "No exchanges could be initialized")
        
        # Log summary
        self._log_exchange_summary()
        
        return self.exchanges
    
    async def _create_exchange_safe(
        self, 
        name: str, 
        dry_run: bool
    ) -> Optional[BaseExchangeInterface]:
        """
        Create exchange with error handling for dry run mode.
        
        Args:
            name: Exchange name
            dry_run: Whether in dry run mode
            
        Returns:
            Exchange instance or None if failed in dry run mode
        """
        try:
            return await self.create_exchange(name)
        except Exception as e:
            if dry_run:
                logger.warning(f"Continuing in dry run mode without {name}")
                return None
            raise
    
    def _log_exchange_summary(self):
        """Log summary of initialized exchanges."""
        logger.info("Exchange initialization complete:")
        logger.info(f"  Active exchanges: {list(self.exchanges.keys())}")
        
        for name, exchange in self.exchanges.items():
            if exchange:
                status = exchange.status.name
                symbols = len(exchange.active_symbols)
                private = "Private" if exchange.has_private else "Public Only"
                logger.info(f"  {name}: {status} ({symbols} symbols, {private})")
    
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
    
    async def _close_exchange(self, name: str, exchange: BaseExchangeInterface):
        """Close single exchange connection."""
        try:
            await exchange.close()
            logger.info(f"Closed {name} exchange")
        except Exception as e:
            logger.error(f"Error closing {name}: {e}")
    
    def get_exchange(self, name: str) -> Optional[BaseExchangeInterface]:
        """Get exchange instance by name."""
        return self.exchanges.get(name)
    
    def get_active_exchanges(self) -> Dict[str, BaseExchangeInterface]:
        """Get all active exchanges."""
        return {
            name: exchange
            for name, exchange in self.exchanges.items()
            if exchange and exchange.status == ExchangeStatus.ACTIVE
        }